"""Tests for Bug #12, #14, #15, #16.

Covers:
- Bug #12: Phone number validation in CreateCompanyRequest, UpdateCompanyRequest, LeadCreateRequest
- Bug #14: Team permission validation in CreateSubUserRequest, UpdateSubUserPermissionsRequest, endpoints
- Bug #15: Credit adjustments bounds and ceiling cap in admin_adjust_credits and update_company
- Bug #16: Redaction of provider_used and internal messages in question processing & evaluation
"""

import sys
from pathlib import Path
from unittest import mock
import pytest
from pydantic import ValidationError
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.auth.models import (
    CreateCompanyRequest,
    UpdateCompanyRequest,
    CreateSubUserRequest,
    UpdateSubUserPermissionsRequest,
    AdjustCreditsRequest,
    VALID_PERMISSIONS,
    MAX_CREDIT_ADJUSTMENT,
    CREDIT_CAP_MULTIPLIER,
    PHONE_RE,
)
from backend.leads.routes import LeadCreateRequest
import backend.admin.routes as admin_routes
import backend.main as main


# ── Bug #12: Phone Number Validation ───────────────────────────────────────

def test_phone_valid_formats():
    valid_numbers = [
        "",
        "+1 (555) 123-4567",
        "+44 20 7946 0958",
        "9876543210",
        "+91 98765 43210",
        "+1-800-555-0199",
    ]
    for num in valid_numbers:
        req = CreateCompanyRequest(
            company_name="Acme Inc",
            contact_email="admin@acme.com",
            contact_phone=num,
            admin_email="owner@acme.com",
            admin_name="Owner",
            admin_password="Password123!",
        )
        assert req.contact_phone == num.strip()

        up = UpdateCompanyRequest(contact_phone=num)
        assert up.contact_phone == num.strip()

        lead = LeadCreateRequest(
            company_name="Acme Lead",
            contact_name="Lead Contact",
            work_email="lead@acme.com",
            phone=num,
        )
        assert lead.phone == num.strip()


def test_phone_invalid_formats_rejected():
    invalid_numbers = [
        "abc",
        "12345",  # too short (< 7 chars)
        "phone12345678",
        "+++12345678",
        "123456789012345678901",  # > 20 chars
    ]
    for num in invalid_numbers:
        with pytest.raises(ValidationError):
            CreateCompanyRequest(
                company_name="Acme Inc",
                contact_email="admin@acme.com",
                contact_phone=num,
                admin_email="owner@acme.com",
                admin_name="Owner",
                admin_password="Password123!",
            )

        with pytest.raises(ValidationError):
            UpdateCompanyRequest(contact_phone=num)

        with pytest.raises(ValidationError):
            LeadCreateRequest(
                company_name="Acme Lead",
                contact_name="Lead Contact",
                work_email="lead@acme.com",
                phone=num,
            )


# ── Bug #14: Team Permission Validation ───────────────────────────────────

def test_manage_users_removed_from_valid_permissions():
    assert "manage_users" not in VALID_PERMISSIONS
    assert "conduct_interviews" in VALID_PERMISSIONS
    assert "view_pipeline" in VALID_PERMISSIONS


def test_create_sub_user_rejects_empty_permissions():
    with pytest.raises(ValidationError) as exc:
        CreateSubUserRequest(
            email="sub@acme.com",
            full_name="Sub User",
            password="Password123!",
            permissions=[],
        )
    assert "Select at least one permission" in str(exc.value)


def test_create_sub_user_rejects_manage_users():
    with pytest.raises(ValidationError) as exc:
        CreateSubUserRequest(
            email="sub@acme.com",
            full_name="Sub User",
            password="Password123!",
            permissions=["manage_users"],
        )
    assert "Invalid permissions" in str(exc.value)


def test_update_sub_user_permissions_rejects_invalid():
    with pytest.raises(ValidationError):
        UpdateSubUserPermissionsRequest(permissions=[])

    with pytest.raises(ValidationError):
        UpdateSubUserPermissionsRequest(permissions=["manage_users"])


def test_create_sub_user_endpoint_validation():
    user = {"_id": "u1", "company_id": "c1", "role": "company_admin"}

    with mock.patch("backend.admin.routes.database.get_company_by_id", return_value={"_id": "c1", "plan": "starter"}), \
         mock.patch("backend.admin.routes.database.count_company_users", return_value=0), \
         mock.patch("backend.admin.routes.database.get_user_by_email", return_value=None):

        # Test empty permissions rejected with 400
        req_empty = mock.MagicMock(permissions=[], email="new@acme.com", password="Password123!", full_name="New")
        with pytest.raises(HTTPException) as exc:
            admin_routes.create_sub_user(req_empty, user=user)
        assert exc.value.status_code == 400
        assert "Select at least one permission" in exc.value.detail

        # Test invalid permission rejected with 400
        req_invalid = mock.MagicMock(permissions=["manage_users"], email="new@acme.com", password="Password123!", full_name="New")
        with pytest.raises(HTTPException) as exc:
            admin_routes.create_sub_user(req_invalid, user=user)
        assert exc.value.status_code == 400
        assert "Invalid permissions" in exc.value.detail


# ── Bug #15: Bounded Credit Adjustments ────────────────────────────────────

def test_credit_adjustment_model_bounds():
    assert MAX_CREDIT_ADJUSTMENT == 50000
    assert CREDIT_CAP_MULTIPLIER == 2

    # Within bounds succeeds
    req_pos = AdjustCreditsRequest(delta=50000)
    assert req_pos.delta == 50000

    req_neg = AdjustCreditsRequest(delta=-50000)
    assert req_neg.delta == -50000

    # Exceeding bounds fails
    with pytest.raises(ValidationError):
        AdjustCreditsRequest(delta=50001)

    with pytest.raises(ValidationError):
        AdjustCreditsRequest(delta=-50001)

    with pytest.raises(ValidationError):
        UpdateCompanyRequest(credits_adjustment=50001)


def test_credit_adjustment_cap_rejection():
    user = {"_id": "s1", "email": "super@admin.com", "role": "super_admin"}
    # starter plan has max_credits=500 -> cap = 2 * 500 = 1000
    company = {
        "_id": "c1",
        "name": "Acme Corp",
        "plan": "starter",
        "credits": {"allowance": 500, "adjustments": 400, "remaining": 900},
    }

    with mock.patch("backend.admin.routes.database.get_company_by_id", return_value=company):
        # Adding 200 would make total 500 + 400 + 200 = 1100 > 1000 -> 400
        req = AdjustCreditsRequest(delta=200)
        with pytest.raises(HTTPException) as exc:
            admin_routes.admin_adjust_credits("c1", req, user=user)
        assert exc.value.status_code == 400
        assert "Adjustment would exceed maximum allowed credits" in exc.value.detail

        # Adding 100 would make total 1000 <= 1000 -> succeeds
        with mock.patch("backend.admin.routes.database.adjust_company_credits", return_value={"remaining": 1000, "allowance": 500}), \
             mock.patch("backend.admin.routes._find_company_admin", return_value=None), \
             mock.patch("backend.admin.routes.database.log_usage"), \
             mock.patch("backend.admin.routes.log_activity"):
            res = admin_routes.admin_adjust_credits("c1", AdjustCreditsRequest(delta=100), user=user)
            assert res is not None


# ── Bug #16: No Provider Leak in Question Endpoints ───────────────────────

def test_process_questions_text_does_not_leak_provider():
    user = {"_id": "u1", "role": "company_admin"}
    payload = main.ProcessQuestionsPayload(text="1. Write a function to reverse a string.")

    with mock.patch.object(main.question_processor, "process_text", return_value=[{"question": "Reverse a string"}]), \
         mock.patch.object(main.question_processor, "last_provider_used", "gemini"), \
         mock.patch.object(main.question_processor, "last_error", "gemini internal error 500"):

        res = main.process_questions_text(payload, user=user)

        assert "questions" in res
        assert "fallback_used" in res
        assert "provider_used" not in res
        assert "message" not in res
        assert "gemini" not in str(res)
        assert "internal error" not in str(res)
