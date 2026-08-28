import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-smoke-tests-only-32b")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")

from backend.main import app
from backend.storage import database
from backend.core.sample_data import DEFAULT_JOB
from backend.core.models import JobDescription

client = TestClient(app)


def _login(email: str, password: str) -> str:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(email: str, password: str) -> dict:
    return {"Authorization": f"Bearer {_login(email, password)}"}


def _job_payload(title: str, job_id=None) -> dict:
    d = {
        "title": title,
        "department": "Eng",
        "location": "Remote",
        "experience_years": 2,
        "required_skills": ["Python"],
        "nice_to_have_skills": [],
        "education": "BS",
        "description": "Test role",
        "threshold": 70,
        "hr_interview_duration": 7,
        "technical_interview_duration": 5,
        "custom_questions": [],
    }
    if job_id is not None:
        d["job_id"] = job_id
    return d


def test_multi_drive_smoke():
    sa_headers = _auth(
        os.getenv("SUPER_ADMIN_EMAIL", "admin@aihiring.com"),
        os.getenv("SUPER_ADMIN_PASSWORD", "Admin@123456"),
    )
    suffix = uuid4().hex[:8]
    admin_email = f"driveadmin{suffix}@test.com"
    admin_pass = "Admin@123456"

    r = client.post(
        "/api/admin/companies",
        headers=sa_headers,
        json={
            "company_name": f"DriveTest {suffix}",
            "contact_email": f"contact{suffix}@test.com",
            "plan": "starter",
            "admin_email": admin_email,
            "admin_name": "Drive Admin",
            "admin_password": admin_pass,
        },
    )
    assert r.status_code == 200, r.text
    company_id = r.json()["company_id"]
    admin_headers = _auth(admin_email, admin_pass)

    job_ids = []
    for i in range(3):
        r = client.put("/api/job", headers=admin_headers, json=_job_payload(f"Drive {i}"))
        assert r.status_code == 200, r.text
        jid = r.json()["job_id"]
        assert jid
        job_ids.append(jid)

    assert database.count_jobs(company_id) == 3

    r = client.put("/api/job", headers=admin_headers, json=_job_payload("Drive 4"))
    assert r.status_code == 403
    assert "Job drive limit reached" in r.json()["detail"]

    r = client.get(f"/api/workspace?job_id={job_ids[0]}", headers=admin_headers)
    assert r.status_code == 200
    ws = r.json()
    assert ws["job_id"] == job_ids[0]
    assert ws["job"]["title"] == "Drive 0"

    r = client.post(
        "/api/resumes/manual",
        headers=admin_headers,
        json={"file_name": "a.txt", "text": "Name: Alice\nEmail: alice@test.com\nSkills: Python"},
    )
    assert r.status_code == 200

    client.put("/api/job", headers=admin_headers, json=_job_payload("Drive 1", job_ids[1]))
    r = client.post(
        "/api/resumes/manual",
        headers=admin_headers,
        json={"file_name": "b.txt", "text": "Name: Alice\nEmail: alice@test.com\nSkills: Python"},
    )
    assert r.status_code == 200

    assert database.count_jobs(company_id) == 3
    c1 = len(database.load_candidates(company_id, job_id=job_ids[0]))
    c2 = len(database.load_candidates(company_id, job_id=job_ids[1]))
    assert c1 >= 1 and c2 >= 1

    r = client.get(f"/api/workspace?job_id={job_ids[1]}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["job_id"] == job_ids[1]
    assert database.get_active_drive(company_id) == job_ids[1]

    r = client.delete(f"/api/job/{job_ids[0]}", headers=admin_headers)
    assert r.status_code == 200
    assert database.get_job_by_id(company_id, job_ids[0]) is None
    assert len(database.load_candidates(company_id, job_id=job_ids[0])) == 0
    assert database.count_jobs(company_id) == 2

    sub_email = f"sub{suffix}@test.com"
    r = client.post(
        "/api/company/team",
        headers=admin_headers,
        json={
            "email": sub_email,
            "full_name": "Sub User",
            "password": "SubUser@123",
            "permissions": ["conduct_interviews", "view_pipeline"],
        },
    )
    assert r.status_code == 200
    sub_headers = _auth(sub_email, "SubUser@123")
    r = client.put("/api/job", headers=sub_headers, json=_job_payload("Blocked"))
    assert r.status_code == 403

    mgr_email = f"mgr{suffix}@test.com"
    r = client.post(
        "/api/company/team",
        headers=admin_headers,
        json={
            "email": mgr_email,
            "full_name": "Mgr",
            "password": "SubUser@123",
            "permissions": ["manage_jobs"],
        },
    )
    assert r.status_code == 200
    mgr_headers = _auth(mgr_email, "SubUser@123")
    target = job_ids[1] if database.get_job_by_id(company_id, job_ids[1]) else database.list_jobs(company_id)[0]["job_id"]
    r = client.delete(f"/api/job/{target}", headers=mgr_headers)
    assert r.status_code == 403

    del_email = f"del{suffix}@test.com"
    r = client.post(
        "/api/company/team",
        headers=admin_headers,
        json={
            "email": del_email,
            "full_name": "Deleter",
            "password": "SubUser@123",
            "permissions": ["manage_jobs", "manage_drive_delete"],
        },
    )
    assert r.status_code == 200
    del_headers = _auth(del_email, "SubUser@123")
    remaining = database.list_jobs(company_id)
    if remaining:
        r = client.delete(f"/api/job/{remaining[0]['job_id']}", headers=del_headers)
        assert r.status_code == 200

    leftover = database.list_jobs(company_id)
    if leftover:
        r = client.delete(
            f"/api/job/{leftover[0]['job_id']}",
            headers=sa_headers,
            params={"company_id": company_id},
        )
        assert r.status_code == 200

    legacy_cid = f"legacy{suffix}"
    from bson import ObjectId
    from datetime import datetime, timezone
    database._companies.insert_one({
        "_id": ObjectId(),
        "name": f"Legacy {suffix}",
        "slug": f"legacy-{suffix}",
        "plan": "starter",
        "max_users": 5,
        "max_jobs": 3,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    })
    leg_company = database.get_company_by_slug(f"legacy-{suffix}")
    leg_id = str(leg_company["_id"])
    database._jobs.insert_one({
        "company_id": leg_id,
        "title": "Legacy Job",
        "department": "X",
        "location": "Y",
        "experience_years": 1,
        "required_skills": ["Python"],
        "nice_to_have_skills": [],
        "education": "BS",
        "description": "legacy",
        "threshold": 70,
        "hr_interview_duration": 7,
        "technical_interview_duration": 5,
        "custom_questions": [],
    })
    database._candidates.insert_one({
        "company_id": leg_id,
        "email": f"legacy{suffix}@test.com",
        "full_name": "Legacy Cand",
        "file_name": "l.txt",
        "skills": ["Python"],
        "experience_years": 1,
        "education": "BS",
        "raw_text": "legacy",
        "uploaded_at": datetime.now(timezone.utc),
        "pipelineStage": "uploaded",
    })
    pre_jobs = database.count_jobs(leg_id)
    pre_cands = database._candidates.count_documents({"company_id": leg_id})
    database.backfill_job_drives()
    assert database.count_jobs(leg_id) >= 1
    assert database._candidates.count_documents({"company_id": leg_id, "job_id": {"$exists": True}}) == pre_cands
    assert database.get_active_drive(leg_id) is not None

    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    test_multi_drive_smoke()
