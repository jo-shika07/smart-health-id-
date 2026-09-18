"""Regression tests for Smart Health ID auth, reports, medical records, reminders, and existing patient/provider APIs."""

import os
import re
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing")

CREDENTIALS_FILE = Path("/app/memory/test_credentials.md")
UPLOAD_DIR = Path("/app/backend/uploads")
PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _credentials():
    if not CREDENTIALS_FILE.exists():
        pytest.skip("Missing /app/memory/test_credentials.md", allow_module_level=True)
    text = CREDENTIALS_FILE.read_text(encoding="utf-8")
    password_match = re.search(r"accounts use[^\n]*password:\s*`([^`]+)`", text, re.I)
    role_matches = {
        role.lower(): re.search(rf"(?im)^- {role}:\s*([^\s·]+)", text)
        for role in ("Patient", "Doctor", "Hospital")
    }
    if not password_match or any(match is None for match in role_matches.values()):
        pytest.skip("Demo credentials are incomplete in test_credentials.md", allow_module_level=True)
    password = password_match.group(1)
    return {
        role: (match.group(1), password)
        for role, match in role_matches.items()
    }


CREDS = _credentials()


def login(role, session=None):
    session = session or requests.Session()
    email, password = CREDS[role]
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == email
    assert data["role"] == role.upper()
    assert isinstance(data["token"], str) and data["token"]
    assert "password_hash" not in data and "_id" not in data
    return data["token"], response


def auth_headers(role):
    token, _ = login(role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(backend_env["MONGO_URL"])
    database = client[backend_env["DB_NAME"]]
    yield database
    client.close()


@pytest.fixture
def created_ids(mongo_db):
    tracked = {"appointments": [], "reports": [], "medical_records": []}
    yield tracked
    for collection, ids in tracked.items():
        if ids:
            mongo_db[collection].delete_many({"id": {"$in": ids}})
    for report_id in tracked["reports"]:
        for candidate in UPLOAD_DIR.glob(f"{report_id}.*"):
            candidate.unlink(missing_ok=True)


# Authentication and cookie lifecycle regression.
def test_auth_me_logout_and_http_only_cookie():
    session = requests.Session()
    token, login_response = login("patient", session)
    set_cookie = login_response.headers.get("Set-Cookie", "")
    assert "access_token=" in set_cookie
    assert "HttpOnly" in set_cookie

    bearer_me = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    assert bearer_me.status_code == 200
    assert bearer_me.json()["email"] == CREDS["patient"][0]

    cookie_me = session.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert cookie_me.status_code == 200
    assert cookie_me.json()["role"] == "PATIENT"

    logout = session.post(f"{BASE_URL}/api/auth/logout", timeout=30)
    assert logout.status_code == 200 and logout.json() == {"ok": True}
    assert "access_token=" in logout.headers.get("Set-Cookie", "")
    after_logout = session.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert after_logout.status_code == 401
    assert "detail" in after_logout.json()


# Report upload, persistence, byte-identical download, validation, and authorization.
def test_report_pdf_upload_list_download_and_validation(created_ids):
    headers = auth_headers("patient")
    report_name = f"TEST_CBC_{uuid.uuid4().hex[:8]}"
    uploaded = requests.post(
        f"{BASE_URL}/api/reports",
        headers=headers,
        data={"name": report_name, "report_type": "Lab report", "provider": "TEST QA Lab"},
        files={"file": ("tiny.pdf", PDF_BYTES, "application/pdf")},
        timeout=30,
    )
    assert uploaded.status_code == 200, uploaded.text
    data = uploaded.json()
    created_ids["reports"].append(data["id"])
    assert data["name"] == report_name
    assert data["patient_email"] == CREDS["patient"][0]
    assert data["content_type"] == "application/pdf"
    assert data["size_bytes"] == len(PDF_BYTES)
    assert isinstance(data["stored_name"], str) and data["stored_name"].endswith(".pdf")
    assert "_id" not in data

    listed = requests.get(f"{BASE_URL}/api/reports", headers=headers, timeout=30)
    assert listed.status_code == 200
    listed_data = listed.json()
    assert isinstance(listed_data, list)
    assert any(item["id"] == data["id"] and item["name"] == report_name for item in listed_data)

    downloaded = requests.get(f"{BASE_URL}/api/reports/{data['id']}/file", headers=headers, timeout=30)
    assert downloaded.status_code == 200
    assert downloaded.headers["Content-Type"].startswith("application/pdf")
    assert downloaded.content == PDF_BYTES

    rejected_type = requests.post(
        f"{BASE_URL}/api/reports",
        headers=headers,
        data={"name": "TEST bad type"},
        files={"file": ("bad.txt", b"plain text", "text/plain")},
        timeout=30,
    )
    assert rejected_type.status_code == 400
    assert "Only PDF or image" in rejected_type.json()["detail"]

    rejected_size = requests.post(
        f"{BASE_URL}/api/reports",
        headers=headers,
        data={"name": "TEST oversized"},
        files={"file": ("large.pdf", b"x" * (8 * 1024 * 1024 + 1), "application/pdf")},
        timeout=60,
    )
    assert rejected_size.status_code == 400
    assert "larger than 8 MB" in rejected_size.json()["detail"]


def test_patient_cannot_download_another_patients_report(mongo_db, created_ids):
    foreign_id = str(uuid.uuid4())
    stored_name = f"{foreign_id}.pdf"
    (UPLOAD_DIR / stored_name).write_bytes(PDF_BYTES)
    mongo_db.reports.insert_one({
        "id": foreign_id,
        "name": "TEST_Foreign_Report",
        "patient_email": "another.patient@example.test",
        "stored_name": stored_name,
        "content_type": "application/pdf",
        "uploaded_at": "2026-07-01T00:00:00+00:00",
    })
    created_ids["reports"].append(foreign_id)
    denied = requests.get(
        f"{BASE_URL}/api/reports/{foreign_id}/file",
        headers=auth_headers("patient"),
        timeout=30,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "You cannot access this report"


# Doctor record creation, patient scoping, persistence, and role restriction.
def test_doctor_medical_record_create_and_patient_scope(created_ids):
    doctor_headers = auth_headers("doctor")
    diagnosis = f"TEST_Mild hypertension {uuid.uuid4().hex[:6]}"
    payload = {
        "patient_email": CREDS["patient"][0],
        "patient_name": "Aarav Sharma",
        "diagnosis": diagnosis,
        "symptoms": "Occasional headache",
        "notes": "TEST automated record",
        "treatment": "Lifestyle changes",
        "prescription": "Amlodipine 2.5mg",
        "follow_up": "2026-08-01",
    }
    created = requests.post(f"{BASE_URL}/api/medical-records", headers=doctor_headers, json=payload, timeout=30)
    assert created.status_code == 200, created.text
    record = created.json()
    created_ids["medical_records"].append(record["id"])
    assert record["diagnosis"] == diagnosis
    assert record["prescription"] == "Amlodipine 2.5mg"
    assert record["status"] == "Verified"
    assert record["doctor_email"] == CREDS["doctor"][0]
    assert isinstance(record["id"], str) and record["id"]
    assert "_id" not in record

    doctor_list = requests.get(f"{BASE_URL}/api/medical-records", headers=doctor_headers, timeout=30)
    assert doctor_list.status_code == 200
    assert any(item["id"] == record["id"] for item in doctor_list.json())

    patient_headers = auth_headers("patient")
    patient_list = requests.get(f"{BASE_URL}/api/medical-records", headers=patient_headers, timeout=30)
    assert patient_list.status_code == 200
    assert any(item["id"] == record["id"] for item in patient_list.json())
    assert all(item["patient_email"] == CREDS["patient"][0] for item in patient_list.json())

    denied = requests.post(f"{BASE_URL}/api/medical-records", headers=patient_headers, json=payload, timeout=30)
    assert denied.status_code == 403
    assert "access" in denied.json()["detail"].lower()


# Reminder endpoint's intentional no-key response and persisted appointment state.
def test_manual_reminder_no_key_and_persistence(created_ids):
    headers = auth_headers("patient")
    appointment_id = str(uuid.uuid4())
    payload = {
        "doctor_id": "DOC-2048",
        "doctor_name": "Dr. Ananya Rao",
        "domain": "Cardiology",
        "hospital": "CityCare Hospital",
        "date": "2026-08-20",
        "time": "10:30 AM",
        "reason": "TEST reminder appointment",
        "fee": 1200,
    }
    created = requests.post(f"{BASE_URL}/api/appointments", headers=headers, json=payload, timeout=30)
    assert created.status_code == 200, created.text
    appointment_id = created.json()["id"]
    created_ids["appointments"].append(appointment_id)
    assert created.json()["reminder_sent"] is False

    reminded = requests.post(
        f"{BASE_URL}/api/appointments/{appointment_id}/send-reminder",
        headers=headers,
        timeout=30,
    )
    assert reminded.status_code == 200, reminded.text
    assert reminded.json() == {"ok": True, "delivered": False, "email_configured": False}

    listed = requests.get(f"{BASE_URL}/api/appointments", headers=headers, timeout=30)
    assert listed.status_code == 200
    saved = next(item for item in listed.json() if item["id"] == appointment_id)
    assert saved["reminder_sent"] is True
    assert isinstance(saved["reminder_sent_at"], str) and saved["reminder_sent_at"]


# Existing appointment CRUD and authorization regression.
def test_existing_appointment_create_list_patch_and_cross_user_protection(created_ids):
    patient_headers = auth_headers("patient")
    payload = {
        "doctor_id": "DOC-1190",
        "doctor_name": "Dr. Rahul Mehta",
        "domain": "General Medicine",
        "hospital": "Apollo Health Center",
        "date": "2026-09-01",
        "time": "04:00 PM",
        "reason": "TEST CRUD appointment",
        "fee": 800,
    }
    created = requests.post(f"{BASE_URL}/api/appointments", headers=patient_headers, json=payload, timeout=30)
    assert created.status_code == 200
    appointment_id = created.json()["id"]
    created_ids["appointments"].append(appointment_id)
    assert created.json()["patient_email"] == CREDS["patient"][0]

    listed = requests.get(f"{BASE_URL}/api/appointments", headers=patient_headers, timeout=30)
    assert listed.status_code == 200
    assert any(item["id"] == appointment_id for item in listed.json())

    updated = requests.patch(
        f"{BASE_URL}/api/appointments/{appointment_id}",
        headers=patient_headers,
        json={"status": "Cancelled"},
        timeout=30,
    )
    assert updated.status_code == 200
    assert updated.json() == {"ok": True, "status": "Cancelled"}
    persisted = requests.get(f"{BASE_URL}/api/appointments", headers=patient_headers, timeout=30).json()
    assert next(item for item in persisted if item["id"] == appointment_id)["status"] == "Cancelled"

    # A hospital is unrelated to this patient's appointment and must not mutate it.
    forbidden = requests.patch(
        f"{BASE_URL}/api/appointments/{appointment_id}",
        headers=auth_headers("hospital"),
        json={"status": "Completed"},
        timeout=30,
    )
    assert forbidden.status_code == 403


# Unrelated providers must not trigger email state changes for a patient's appointment.
def test_cross_user_reminder_protection(created_ids):
    patient_headers = auth_headers("patient")
    payload = {
        "doctor_id": "DOC-1190",
        "doctor_name": "Dr. Rahul Mehta",
        "domain": "General Medicine",
        "hospital": "Apollo Health Center",
        "date": "2026-09-02",
        "time": "04:00 PM",
        "reason": "TEST reminder authorization",
        "fee": 800,
    }
    created = requests.post(f"{BASE_URL}/api/appointments", headers=patient_headers, json=payload, timeout=30)
    assert created.status_code == 200
    appointment_id = created.json()["id"]
    created_ids["appointments"].append(appointment_id)

    forbidden = requests.post(
        f"{BASE_URL}/api/appointments/{appointment_id}/send-reminder",
        headers=auth_headers("hospital"),
        timeout=30,
    )
    assert forbidden.status_code == 403


# Existing provider verification, profile update persistence, and AI streaming regression.
def test_health_id_verification_roles():
    patient_denied = requests.post(
        f"{BASE_URL}/api/verify-health-id?health_id=SHID-10001",
        headers=auth_headers("patient"),
        timeout=30,
    )
    assert patient_denied.status_code == 403
    for role in ("doctor", "hospital"):
        verified = requests.post(
            f"{BASE_URL}/api/verify-health-id?health_id=SHID-10001",
            headers=auth_headers(role),
            timeout=30,
        )
        assert verified.status_code == 200
        data = verified.json()
        assert data["health_id"] == "SHID-10001"
        assert data["status"] == "Verified"
        assert data["name"] == "Aarav Sharma"


def test_profile_get_put_and_restore():
    headers = auth_headers("patient")
    original_response = requests.get(f"{BASE_URL}/api/profile", headers=headers, timeout=30)
    assert original_response.status_code == 200
    original = original_response.json()
    required = ["name", "phone", "occupation", "marital", "address", "height", "weight", "emergency"]
    payload = {key: original[key] for key in required}
    changed = dict(payload)
    changed["phone"] = "+91 91111 11111"
    saved = requests.put(f"{BASE_URL}/api/profile", headers=headers, json=changed, timeout=30)
    assert saved.status_code == 200
    assert saved.json()["phone"] == changed["phone"]
    fetched = requests.get(f"{BASE_URL}/api/profile", headers=headers, timeout=30)
    assert fetched.status_code == 200 and fetched.json()["phone"] == changed["phone"]
    restored = requests.put(f"{BASE_URL}/api/profile", headers=headers, json=payload, timeout=30)
    assert restored.status_code == 200 and restored.json()["phone"] == payload["phone"]


def test_ai_symptom_stream_patient_200_and_doctor_403():
    patient = requests.post(
        f"{BASE_URL}/api/ai/symptoms",
        headers=auth_headers("patient"),
        json={"message": "TEST mild headache", "session_id": f"TEST-{uuid.uuid4()}"},
        timeout=120,
    )
    assert patient.status_code == 200, patient.text
    assert patient.headers["Content-Type"].startswith("text/event-stream")
    assert "data:" in patient.text
    assert "[DONE]" in patient.text

    doctor = requests.post(
        f"{BASE_URL}/api/ai/symptoms",
        headers=auth_headers("doctor"),
        json={"message": "headache"},
        timeout=30,
    )
    assert doctor.status_code == 403


# Auth playbook configuration checks: explicit credentialed CORS and bcrypt storage.
def test_auth_security_configuration_and_bcrypt_hash(mongo_db):
    user = mongo_db.users.find_one({"email": CREDS["patient"][0]})
    assert user and isinstance(user.get("password_hash"), str)
    assert user["password_hash"].startswith("$2b$")

    origin = BASE_URL
    preflight = requests.options(
        f"{BASE_URL}/api/auth/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
        timeout=30,
    )
    assert preflight.status_code in (200, 204)
    assert preflight.headers.get("Access-Control-Allow-Origin") == origin
    assert preflight.headers.get("Access-Control-Allow-Credentials") == "true"


# Auth playbook requires rate limiting after five failed attempts.
def test_zz_brute_force_lockout_after_five_failures():
    email, _ = CREDS["hospital"]
    responses = [
        requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": f"TEST_wrong_{attempt}"},
            timeout=30,
        )
        for attempt in range(6)
    ]
    assert all(response.status_code == 401 for response in responses[:5])
    assert responses[5].status_code == 429
    assert "detail" in responses[5].json()


# Focused ownership matrix for appointment status mutations added in iteration 3.
def test_appointment_patch_complete_ownership_matrix(mongo_db, created_ids):
    patient_headers = auth_headers("patient")
    doctor_headers = auth_headers("doctor")
    hospital_headers = auth_headers("hospital")

    foreign_patient_id = str(uuid.uuid4())
    doctor_mismatch_id = str(uuid.uuid4())
    owning_patient_id = str(uuid.uuid4())
    base = {
        "patient_name": "TEST Ownership Patient",
        "doctor_name": "TEST Doctor",
        "domain": "General Medicine",
        "hospital": "TEST Hospital",
        "date": "2026-10-10",
        "time": "10:30 AM",
        "reason": "TEST ownership matrix",
        "fee": 800,
        "status": "Upcoming",
        "reminder_sent": False,
    }
    documents = [
        base | {"id": foreign_patient_id, "patient_email": "another.patient@example.test", "doctor_id": "DOC-2048"},
        base | {"id": doctor_mismatch_id, "patient_email": CREDS["patient"][0], "doctor_id": "DOC-OTHER"},
        base | {"id": owning_patient_id, "patient_email": CREDS["patient"][0], "doctor_id": "DOC-2048"},
    ]
    mongo_db.appointments.insert_many(documents)
    created_ids["appointments"].extend([foreign_patient_id, doctor_mismatch_id, owning_patient_id])

    cases = [
        (foreign_patient_id, patient_headers, "Completed", "another patient's"),
        (doctor_mismatch_id, doctor_headers, "Completed", "outside your care"),
        (owning_patient_id, hospital_headers, "Completed", "Hospitals cannot mutate"),
    ]
    for appointment_id, headers, status, expected_detail in cases:
        denied = requests.patch(
            f"{BASE_URL}/api/appointments/{appointment_id}",
            headers=headers,
            json={"status": status},
            timeout=30,
        )
        assert denied.status_code == 403, denied.text
        assert expected_detail in denied.json()["detail"]
        assert mongo_db.appointments.find_one({"id": appointment_id})["status"] == "Upcoming"

    allowed = requests.patch(
        f"{BASE_URL}/api/appointments/{owning_patient_id}",
        headers=patient_headers,
        json={"status": "Cancelled"},
        timeout=30,
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json() == {"ok": True, "status": "Cancelled"}
    assert mongo_db.appointments.find_one({"id": owning_patient_id})["status"] == "Cancelled"


# Focused ownership matrix and persistence for manual appointment reminders.
def test_send_reminder_complete_ownership_matrix(mongo_db, created_ids):
    patient_headers = auth_headers("patient")
    doctor_headers = auth_headers("doctor")
    hospital_headers = auth_headers("hospital")

    foreign_patient_id = str(uuid.uuid4())
    doctor_mismatch_id = str(uuid.uuid4())
    owning_patient_id = str(uuid.uuid4())
    base = {
        "patient_name": "TEST Ownership Patient",
        "doctor_name": "TEST Doctor",
        "domain": "General Medicine",
        "hospital": "TEST Hospital",
        "date": "2026-10-11",
        "time": "10:30 AM",
        "reason": "TEST reminder ownership matrix",
        "fee": 800,
        "status": "Upcoming",
        "reminder_sent": False,
    }
    documents = [
        base | {"id": foreign_patient_id, "patient_email": "another.patient@example.test", "doctor_id": "DOC-2048"},
        base | {"id": doctor_mismatch_id, "patient_email": CREDS["patient"][0], "doctor_id": "DOC-OTHER"},
        base | {"id": owning_patient_id, "patient_email": CREDS["patient"][0], "doctor_id": "DOC-2048"},
    ]
    mongo_db.appointments.insert_many(documents)
    created_ids["appointments"].extend([foreign_patient_id, doctor_mismatch_id, owning_patient_id])

    cases = [
        (foreign_patient_id, patient_headers, "another patient"),
        (doctor_mismatch_id, doctor_headers, "outside your care"),
        (owning_patient_id, hospital_headers, "Hospitals cannot send"),
    ]
    for appointment_id, headers, expected_detail in cases:
        denied = requests.post(
            f"{BASE_URL}/api/appointments/{appointment_id}/send-reminder",
            headers=headers,
            timeout=30,
        )
        assert denied.status_code == 403, denied.text
        assert expected_detail in denied.json()["detail"]
        saved = mongo_db.appointments.find_one({"id": appointment_id})
        assert saved["reminder_sent"] is False
        assert "reminder_sent_at" not in saved

    allowed = requests.post(
        f"{BASE_URL}/api/appointments/{owning_patient_id}/send-reminder",
        headers=patient_headers,
        timeout=30,
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json() == {"ok": True, "delivered": False, "email_configured": False}
    saved = mongo_db.appointments.find_one({"id": owning_patient_id})
    assert saved["reminder_sent"] is True
    assert isinstance(saved["reminder_sent_at"], str) and saved["reminder_sent_at"]


# Reminder scheduler date/time parsing regression.
def test_parse_appointment_datetime_uses_12_hour_time():
    import sys

    os.environ.update({key: value for key, value in backend_env.items() if value is not None})
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from server import _parse_appointment_dt

    parsed = _parse_appointment_dt({"date": "2026-04-14", "time": "10:30 AM"})
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == (2026, 4, 14)
    assert (parsed.hour, parsed.minute, parsed.second) == (10, 30, 0)
    assert parsed.utcoffset().total_seconds() == 0

