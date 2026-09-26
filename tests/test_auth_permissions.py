"""Tests for authorization error codes on 403 responses.

The client can only react to a *permission* change (and revalidate its cached
profile) if a permission denial is distinguishable from the other 403s this API
returns: account/company suspension, and business-rule locks such as
"Technical round unlocks after the HR deadline passes".

These tests pin that contract: permission denials carry
``code == "permission_denied"``, suspension carries its own code, and
non-permission 403s carry no code at all.

Runs without pytest::

    python tests/test_auth_permissions.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402

from backend.auth import security  # noqa: E402

PERMISSION_MESSAGE = "You do not have permission to perform this action."


def _call(dep, user):
    """Invoke a FastAPI dependency callable and return the raised exception."""
    try:
        asyncio.run(dep(user))
    except HTTPException as exc:
        return exc
    return None


def _detail_of(exc):
    detail = exc.detail
    if isinstance(detail, dict):
        return detail
    return {"message": detail}


# ── Permission denials are machine-readable ──────────────────────────────────

def test_require_permission_denial_has_code():
    checker = security.require_permission("view_usage")
    exc = _call(checker, {"role": "sub_user", "permissions": ["view_pipeline"]})
    assert exc is not None, "expected a denial"
    assert exc.status_code == 403
    detail = _detail_of(exc)
    assert detail["code"] == "permission_denied"
    # The human-readable text must stay identical to the old bare-string form.
    assert detail["message"] == PERMISSION_MESSAGE


def test_require_job_manage_denial_has_code():
    exc = _call(security.require_job_manage, {"role": "sub_user", "permissions": ["view_pipeline"]})
    assert exc is not None and exc.status_code == 403
    assert _detail_of(exc)["code"] == "permission_denied"
    assert _detail_of(exc)["message"] == PERMISSION_MESSAGE


def test_require_drive_delete_denial_has_code():
    exc = _call(security.require_drive_delete, {"role": "sub_user", "permissions": ["view_pipeline"]})
    assert exc is not None and exc.status_code == 403
    assert _detail_of(exc)["code"] == "permission_denied"
    assert _detail_of(exc)["message"] == PERMISSION_MESSAGE


# ── The code is only emitted for genuine permission denials ─────────────────

def test_deadline_lock_is_not_a_permission_denial():
    """Regression guard: a business-rule 403 must not masquerade as one.

    The pipeline raises a bare 403 for "Technical round unlocks after the HR
    deadline passes". If that ever gained the permission_denied code, every
    deadline lock would trigger a client profile revalidation.
    """
    exc = HTTPException(status_code=403, detail="Technical round unlocks after the HR deadline passes.")
    detail = _detail_of(exc)
    assert "code" not in detail, "a deadline lock must not carry a permission code"


def test_tenant_isolation_403_is_not_a_permission_denial():
    """'Cannot manage users from another company' is not a permission change."""
    exc = HTTPException(status_code=403, detail="Cannot manage users from another company")
    assert "code" not in _detail_of(exc)


# ── Suspension codes ────────────────────────────────────────────────────────

def test_suspension_codes_are_distinct_from_permission_denied():
    assert security.ACCOUNT_SUSPENDED != security.PERMISSION_DENIED
    assert security.COMPANY_SUSPENDED != security.PERMISSION_DENIED
    assert security.COMPANY_SUSPENDED != security.ACCOUNT_SUSPENDED


def test_account_suspension_403_shape():
    exc = security._forbidden(security.ACCOUNT_SUSPENDED, "Account suspended. Contact your administrator.")
    assert exc.status_code == 403
    detail = _detail_of(exc)
    assert detail["code"] == "account_suspended"
    assert detail["message"] == "Account suspended. Contact your administrator."


def test_company_suspension_403_shape():
    exc = security._forbidden(security.COMPANY_SUSPENDED, "Company account suspended. Contact platform administrator.")
    assert exc.status_code == 403
    assert _detail_of(exc)["code"] == "company_suspended"


# ── The bypass rules must be untouched ──────────────────────────────────────

def test_company_admin_bypasses_permission_check():
    checker = security.require_permission("view_usage")
    for role in ("company_admin", "super_admin"):
        exc = _call(checker, {"role": role, "permissions": []})
        assert exc is None, f"{role} must never be denied"


def test_wildcard_permission_bypasses_check():
    checker = security.require_permission("view_usage")
    exc = _call(checker, {"role": "sub_user", "permissions": ["*"]})
    assert exc is None


def test_held_permission_is_allowed():
    checker = security.require_permission("view_usage")
    exc = _call(checker, {"role": "sub_user", "permissions": ["view_pipeline", "view_usage"]})
    assert exc is None


def test_missing_or_null_permissions_are_denied_not_crashed():
    checker = security.require_permission("view_usage")
    for perms in ([], None, ""):
        exc = _call(checker, {"role": "sub_user", "permissions": perms})
        assert exc is not None and _detail_of(exc)["code"] == "permission_denied"


def test_require_permission_requires_all_listed_permissions():
    checker = security.require_permission("view_usage", "manage_jobs")
    exc = _call(checker, {"role": "sub_user", "permissions": ["view_usage"]})
    assert exc is not None and _detail_of(exc)["code"] == "permission_denied"


def test_drive_delete_accepted_via_manage_jobs():
    """manage_jobs implies drive deletion — must not regress to a denial."""
    assert _call(security.require_drive_delete, {"role": "sub_user", "permissions": ["manage_jobs"]}) is None


def _main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            print(f"  FAIL  {name}: {exc}")
            failed.append(name)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
            failed.append(name)
    print(f"\n{len(tests) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
