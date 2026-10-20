"""Tests for the self-service password reset flow.

Covers:
- Token generation: raw/hash properties, single-use semantics
- forgot-password: generic response (no enumeration), eligibility, cooldown,
  rate limiting
- reset-password: invalid/expired token rejection, successful reset kills
  sessions and consumes the token, suspension guards
- change-password: clears a pending reset token, sends notification
- admin reset_user_password: kills sessions, clears reset token, notifies

Runs without pytest::

    python tests/test_password_reset.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.auth import security
from backend.auth.models import (
    ForgotPasswordRequest,
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    ResetPasswordRequest,
)
import backend.auth.routes as auth_routes
import backend.admin.routes as admin_routes


# ── Helpers ──────────────────────────────────────────────────────────────────

VALID_PW = "Password123!"


def _clear_rate_limiters():
    """Reset in-memory rate limiter stores between tests."""
    security._forgot_attempts.clear()
    security._login_attempts.clear()


def _make_user(user_id="u1", email="user@acme.com", role="sub_user",
               company_id="c1", status="active"):
    return {
        "_id": user_id,
        "email": email,
        "full_name": "Test User",
        "role": role,
        "company_id": company_id,
        "status": status,
        "permissions": ["view_pipeline"],
        "password_hash": "old-hash",
        "active_session_token": "old-session",
    }


class _FakeRequest:
    """Minimal stand-in for starlette Request (client.host only)."""

    def __init__(self, ip="10.0.0.1"):
        self.client = mock.MagicMock(host=ip)
        self.headers = {}


# ── Token generation ─────────────────────────────────────────────────────────

def test_generate_reset_token_raw_and_hash():
    raw, token_hash = security.generate_password_reset_token()
    assert len(raw) >= 32, "raw token must be high-entropy"
    assert len(token_hash) == 64, "SHA-256 hex digest"
    # Hash is deterministic for the same raw input
    import hashlib
    assert token_hash == hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_generate_reset_token_unique():
    raw1, hash1 = security.generate_password_reset_token()
    raw2, hash2 = security.generate_password_reset_token()
    assert raw1 != raw2
    assert hash1 != hash2


# ── Request model validation ─────────────────────────────────────────────────

def test_forgot_password_request_validates_email():
    with pytest.raises(ValidationError):
        ForgotPasswordRequest(email="not-an-email")
    ok = ForgotPasswordRequest(email="User@Acme.COM")
    assert ok.email == "user@acme.com", "emails are normalized to lowercase"


def test_reset_password_request_enforces_strength():
    with pytest.raises(ValidationError):
        ResetPasswordRequest(token="a" * 32, new_password="weak")
    ok = ResetPasswordRequest(token="a" * 32, new_password=VALID_PW)
    assert ok.new_password == VALID_PW


def test_reset_password_request_requires_token():
    with pytest.raises(ValidationError):
        ResetPasswordRequest(token="", new_password=VALID_PW)


# ── forgot-password ──────────────────────────────────────────────────────────

def test_forgot_password_unknown_email_generic_response():
    """Unknown email must return the SAME success response (no enumeration)."""
    _clear_rate_limiters()
    req = _FakeRequest()
    with mock.patch.object(auth_routes.database, "find_recent_email_log", return_value=None), \
         mock.patch.object(auth_routes.database, "get_user_by_email", return_value=None), \
         mock.patch.object(auth_routes.email_service, "send_email") as send_mock:
        body = ForgotPasswordRequest(email="nobody@nowhere.com")
        resp = auth_routes.forgot_password(body, request=req)
    assert resp["ok"] is True
    assert "If an account exists" in resp["message"]
    send_mock.assert_not_called()


def test_forgot_password_inactive_user_no_email():
    _clear_rate_limiters()
    req = _FakeRequest()
    inactive = _make_user(status="suspended")
    with mock.patch.object(auth_routes.database, "find_recent_email_log", return_value=None), \
         mock.patch.object(auth_routes.database, "get_user_by_email", return_value=inactive), \
         mock.patch.object(auth_routes.email_service, "send_email") as send_mock:
        body = ForgotPasswordRequest(email=inactive["email"])
        resp = auth_routes.forgot_password(body, request=req)
    assert resp["ok"] is True
    send_mock.assert_not_called()


def test_forgot_password_suspended_company_no_email():
    _clear_rate_limiters()
    req = _FakeRequest()
    user = _make_user()
    with mock.patch.object(auth_routes.database, "find_recent_email_log", return_value=None), \
         mock.patch.object(auth_routes.database, "get_user_by_email", return_value=user), \
         mock.patch.object(auth_routes.database, "get_company_by_id",
                           return_value={"_id": "c1", "status": "suspended"}), \
         mock.patch.object(auth_routes.email_service, "send_email") as send_mock:
        body = ForgotPasswordRequest(email=user["email"])
        resp = auth_routes.forgot_password(body, request=req)
    assert resp["ok"] is True
    send_mock.assert_not_called()


def test_forgot_password_active_user_stores_token_and_sends():
    _clear_rate_limiters()
    req = _FakeRequest()
    user = _make_user()
    captured = {}

    def fake_set(user_id, token_hash, expires_at):
        captured["user_id"] = user_id
        captured["token_hash"] = token_hash
        captured["expires_at"] = expires_at

    with mock.patch.object(auth_routes.database, "find_recent_email_log", return_value=None), \
         mock.patch.object(auth_routes.database, "get_user_by_email", return_value=user), \
         mock.patch.object(auth_routes.database, "get_company_by_id",
                           return_value={"_id": "c1", "status": "active"}), \
         mock.patch.object(auth_routes.database, "set_user_password_reset_token", side_effect=fake_set), \
         mock.patch.object(auth_routes.email_service, "send_email",
                           return_value={"ok": True, "error": None}) as send_mock, \
         mock.patch.object(auth_routes.email_service, "log_email_send"), \
         mock.patch.object(auth_routes, "log_activity"):
        body = ForgotPasswordRequest(email=user["email"])
        resp = auth_routes.forgot_password(body, request=req)

    assert resp["ok"] is True
    assert captured["user_id"] == "u1"
    assert captured["token_hash"] and len(captured["token_hash"]) == 64
    # Expiry is ~30 minutes out
    delta = captured["expires_at"] - datetime.now(timezone.utc)
    assert timedelta(minutes=29) < delta <= timedelta(minutes=31)
    send_mock.assert_called_once()
    # The emailed URL must contain the raw token, never the hash alone is enough
    # (send_email is called with html/plain built from the raw token — we just
    # assert one send happened for the right address)
    assert send_mock.call_args[0][0] == user["email"]


def test_forgot_password_cooldown_blocks_resend():
    """A second request within 60s of a successful send must not re-send."""
    _clear_rate_limiters()
    req = _FakeRequest()
    user = _make_user()
    with mock.patch.object(auth_routes.database, "find_recent_email_log",
                           return_value={"_id": "log1"}), \
         mock.patch.object(auth_routes.database, "get_user_by_email", return_value=user), \
         mock.patch.object(auth_routes.email_service, "send_email") as send_mock, \
         mock.patch.object(auth_routes.database, "set_user_password_reset_token") as set_mock:
        body = ForgotPasswordRequest(email=user["email"])
        resp = auth_routes.forgot_password(body, request=req)
    assert resp["ok"] is True
    send_mock.assert_not_called()
    set_mock.assert_not_called()


def test_forgot_password_rate_limited():
    _clear_rate_limiters()
    req = _FakeRequest(ip="9.9.9.9")
    body = ForgotPasswordRequest(email="user@acme.com")
    with mock.patch.object(auth_routes.database, "find_recent_email_log", return_value=None), \
         mock.patch.object(auth_routes.database, "get_user_by_email", return_value=None):
        for _ in range(security.FORGOT_RATE_LIMIT):
            auth_routes.forgot_password(body, request=req)
        with pytest.raises(HTTPException) as exc:
            auth_routes.forgot_password(body, request=req)
    assert exc.value.status_code == 429
    _clear_rate_limiters()


def test_forgot_password_super_admin_eligible():
    """Super admins (no company_id) can also self-serve a reset."""
    _clear_rate_limiters()
    req = _FakeRequest()
    admin = _make_user(user_id="sa1", email="sa@platform.com",
                       role="super_admin", company_id=None)
    with mock.patch.object(auth_routes.database, "find_recent_email_log", return_value=None), \
         mock.patch.object(auth_routes.database, "get_user_by_email", return_value=admin), \
         mock.patch.object(auth_routes.database, "set_user_password_reset_token") as set_mock, \
         mock.patch.object(auth_routes.email_service, "send_email",
                           return_value={"ok": True, "error": None}), \
         mock.patch.object(auth_routes.email_service, "log_email_send"), \
         mock.patch.object(auth_routes, "log_activity"):
        body = ForgotPasswordRequest(email=admin["email"])
        resp = auth_routes.forgot_password(body, request=req)
    assert resp["ok"] is True
    set_mock.assert_called_once()


# ── reset-password ───────────────────────────────────────────────────────────

def test_reset_password_invalid_token():
    req = _FakeRequest()
    body = ResetPasswordRequest(token="f" * 43, new_password=VALID_PW)
    with mock.patch.object(auth_routes.database, "get_user_by_reset_token_hash",
                           return_value=None):
        with pytest.raises(HTTPException) as exc:
            auth_routes.reset_password(body, request=req)
    assert exc.value.status_code == 400
    assert "Invalid or expired" in exc.value.detail


def test_reset_password_expired_token():
    req = _FakeRequest()
    user = _make_user()
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    cleared = []
    body = ResetPasswordRequest(token="f" * 43, new_password=VALID_PW)
    with mock.patch.object(auth_routes.database, "get_user_by_reset_token_hash",
                           return_value={**user, "password_reset_expires_at": expired}), \
         mock.patch.object(auth_routes.database, "clear_user_password_reset_token",
                           side_effect=lambda uid: cleared.append(uid)):
        with pytest.raises(HTTPException) as exc:
            auth_routes.reset_password(body, request=req)
    assert exc.value.status_code == 400
    assert "expired" in exc.value.detail.lower()
    assert cleared == ["u1"], "expired token must be consumed"


def test_reset_password_naive_expired_datetime():
    """pymongo returns naive UTC datetimes — must not raise TypeError."""
    req = _FakeRequest()
    user = _make_user()
    naive_expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None)
    body = ResetPasswordRequest(token="f" * 43, new_password=VALID_PW)
    with mock.patch.object(auth_routes.database, "get_user_by_reset_token_hash",
                           return_value={**user, "password_reset_expires_at": naive_expired}), \
         mock.patch.object(auth_routes.database, "clear_user_password_reset_token"):
        with pytest.raises(HTTPException) as exc:
            auth_routes.reset_password(body, request=req)
    assert exc.value.status_code == 400
    assert "expired" in exc.value.detail.lower()


def test_reset_password_naive_future_datetime_valid():
    """A naive future datetime (as stored by pymongo) must be accepted."""
    req = _FakeRequest()
    user = _make_user()
    naive_future = (datetime.now(timezone.utc) + timedelta(minutes=20)).replace(tzinfo=None)
    calls = {}
    body = ResetPasswordRequest(token="f" * 43, new_password=VALID_PW)

    def fake_update(user_id, pw_hash):
        calls["password_updated"] = (user_id, pw_hash)

    with mock.patch.object(auth_routes.database, "get_user_by_reset_token_hash",
                           return_value={**user, "password_reset_expires_at": naive_future}), \
         mock.patch.object(auth_routes.database, "get_company_by_id",
                           return_value={"_id": "c1", "status": "active"}), \
         mock.patch.object(auth_routes.database, "update_user_password", side_effect=fake_update), \
         mock.patch.object(auth_routes.database, "clear_user_password_reset_token") as clear_mock, \
         mock.patch.object(auth_routes.database, "update_user_session") as session_mock, \
         mock.patch.object(auth_routes, "log_activity"), \
         mock.patch.object(auth_routes, "_send_password_change_notification",
                           return_value=True):
        resp = auth_routes.reset_password(body, request=req)

    assert resp["ok"] is True
    assert "password_updated" in calls
    assert calls["password_updated"][0] == "u1"
    clear_mock.assert_called_once_with("u1")
    session_mock.assert_called_once_with("u1", refresh_token=None)


def test_reset_password_suspended_account():
    req = _FakeRequest()
    user = _make_user(status="suspended")
    future = datetime.now(timezone.utc) + timedelta(minutes=20)
    body = ResetPasswordRequest(token="f" * 43, new_password=VALID_PW)
    with mock.patch.object(auth_routes.database, "get_user_by_reset_token_hash",
                           return_value={**user, "password_reset_expires_at": future}), \
         mock.patch.object(auth_routes.database, "clear_user_password_reset_token") as clear_mock, \
         mock.patch.object(auth_routes.database, "update_user_password") as pw_mock:
        with pytest.raises(HTTPException) as exc:
            auth_routes.reset_password(body, request=req)
    assert exc.value.status_code == 403
    pw_mock.assert_not_called()
    clear_mock.assert_called_once_with("u1")


def test_reset_password_suspended_company():
    req = _FakeRequest()
    user = _make_user()
    future = datetime.now(timezone.utc) + timedelta(minutes=20)
    body = ResetPasswordRequest(token="f" * 43, new_password=VALID_PW)
    with mock.patch.object(auth_routes.database, "get_user_by_reset_token_hash",
                           return_value={**user, "password_reset_expires_at": future}), \
         mock.patch.object(auth_routes.database, "get_company_by_id",
                           return_value={"_id": "c1", "status": "suspended"}), \
         mock.patch.object(auth_routes.database, "clear_user_password_reset_token"), \
         mock.patch.object(auth_routes.database, "update_user_password") as pw_mock:
        with pytest.raises(HTTPException) as exc:
            auth_routes.reset_password(body, request=req)
    assert exc.value.status_code == 403
    pw_mock.assert_not_called()


# ── change-password clears pending reset token ───────────────────────────────

def test_change_password_clears_pending_reset_token():
    user = _make_user()
    full_user = {**user, "password_hash": security.hash_password(VALID_PW)}
    body = mock.MagicMock(current_password=VALID_PW, new_password="NewPass123!")
    cleared = []
    with mock.patch.object(auth_routes.database, "get_user_by_id", return_value=full_user), \
         mock.patch.object(auth_routes.database, "update_user_password") as pw_mock, \
         mock.patch.object(auth_routes.database, "clear_user_password_reset_token",
                           side_effect=lambda uid: cleared.append(uid)), \
         mock.patch.object(auth_routes, "log_activity"), \
         mock.patch.object(auth_routes, "_send_password_change_notification",
                           return_value=True):
        resp = auth_routes.change_password(body, user=user, request=_FakeRequest())
    assert resp["ok"] is True
    pw_mock.assert_called_once()
    assert cleared == ["u1"], "pending reset token must be consumed on self-change"


def test_change_password_wrong_current_rejected():
    user = _make_user()
    full_user = {**user, "password_hash": security.hash_password(VALID_PW)}
    body = mock.MagicMock(current_password="WrongPass1!", new_password="NewPass123!")
    with mock.patch.object(auth_routes.database, "get_user_by_id", return_value=full_user), \
         mock.patch.object(auth_routes.database, "update_user_password") as pw_mock:
        with pytest.raises(HTTPException) as exc:
            auth_routes.change_password(body, user=user, request=_FakeRequest())
    assert exc.value.status_code == 400
    pw_mock.assert_not_called()


# ── Admin reset_user_password ────────────────────────────────────────────────

def test_admin_reset_kills_session_clears_token_and_notifies():
    target = _make_user()
    admin = {"_id": "sa1", "email": "sa@platform.com", "role": "super_admin",
             "full_name": "Super Admin"}
    body = mock.MagicMock(new_password="Reset123!")
    with mock.patch.object(admin_routes.database, "get_user_by_id", return_value=target), \
         mock.patch.object(admin_routes.database, "update_user_password") as pw_mock, \
         mock.patch.object(admin_routes.database, "update_user_session") as session_mock, \
         mock.patch.object(admin_routes.database, "clear_user_password_reset_token") as clear_mock, \
         mock.patch.object(admin_routes, "log_activity"), \
         mock.patch.object(admin_routes.email_service, "send_email",
                           return_value={"ok": True, "error": None}) as send_mock, \
         mock.patch.object(admin_routes.email_service, "log_email_send"), \
         mock.patch.object(admin_routes, "frontend_base_url", return_value="http://localhost:5173"):
        resp = admin_routes.reset_user_password("u1", body, user=admin, request=_FakeRequest())

    assert resp["ok"] is True
    assert resp["email_sent"] is True
    pw_mock.assert_called_once()
    session_mock.assert_called_once_with("u1", refresh_token=None)
    clear_mock.assert_called_once_with("u1")
    send_mock.assert_called_once()
    assert send_mock.call_args[0][0] == target["email"]


def test_admin_reset_cannot_reset_super_admin():
    target = _make_user(role="super_admin")
    admin = {"_id": "sa1", "email": "sa@platform.com", "role": "super_admin"}
    body = mock.MagicMock(new_password="Reset123!")
    with mock.patch.object(admin_routes.database, "get_user_by_id", return_value=target), \
         mock.patch.object(admin_routes.database, "update_user_password") as pw_mock:
        with pytest.raises(HTTPException) as exc:
            admin_routes.reset_user_password("u1", body, user=admin, request=_FakeRequest())
    assert exc.value.status_code == 400
    pw_mock.assert_not_called()


def test_admin_reset_notification_failure_still_resets():
    """Notification email failure must never fail the reset itself."""
    target = _make_user()
    admin = {"_id": "sa1", "email": "sa@platform.com", "role": "super_admin"}
    body = mock.MagicMock(new_password="Reset123!")
    with mock.patch.object(admin_routes.database, "get_user_by_id", return_value=target), \
         mock.patch.object(admin_routes.database, "update_user_password") as pw_mock, \
         mock.patch.object(admin_routes.database, "update_user_session"), \
         mock.patch.object(admin_routes.database, "clear_user_password_reset_token"), \
         mock.patch.object(admin_routes, "log_activity"), \
         mock.patch.object(admin_routes.email_service, "send_email",
                           side_effect=Exception("SMTP down")), \
         mock.patch.object(admin_routes.email_service, "log_email_send"):
        resp = admin_routes.reset_user_password("u1", body, user=admin, request=_FakeRequest())
    assert resp["ok"] is True
    assert resp["email_sent"] is False
    pw_mock.assert_called_once()


# ── Email templates render ───────────────────────────────────────────────────

def test_password_reset_email_template():
    from backend.services.email_templates import password_reset_email
    url = "http://localhost:5173/reset-password?token=RAW123"
    subject, html, plain = password_reset_email("Test User", url, 30)
    assert "RAW123" in url
    assert url in html
    assert url in plain
    assert "30 minutes" in html
    assert "Test User" in plain
    # No plaintext password placeholder of any kind
    assert "Password    :" not in plain


def test_password_changed_notification_template():
    from backend.services.email_templates import password_changed_notification_email
    subject, html, plain = password_changed_notification_email(
        "Test User", "You changed your own password", "http://localhost:5173/login",
    )
    assert "You changed your own password" in plain
    assert "You changed your own password" in html
    assert "http://localhost:5173/login" in html
    assert "didn't change" in html.lower() or "Didn't change" in html


if __name__ == "__main__":
    import traceback
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except Exception:
                failures += 1
                print(f"FAIL  {name}")
                traceback.print_exc()
    total = sum(1 for n, f in globals().items() if n.startswith("test_") and callable(f))
    print(f"\n{total - failures}/{total} passed")
    sys.exit(1 if failures else 0)
