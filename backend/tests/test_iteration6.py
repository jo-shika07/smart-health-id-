"""Iteration 6 tests for booking guards, status locks, notifications, uploads, records, Health ID, and extended registration."""

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

credentials_path = Path("/app/memory/test_credentials.md")
if not credentials_path.exists():
    pytest.skip("Missing test_credentials.md", allow_module_level=True)
credentials_text = credentials_path.read_text(encoding="utf-8")
password_match = re.search(r"password:\s*`([^`]+)`", credentials_text, re.I)
role_matches = {
    role.lower(): re.search(rf"(?im)^- {role}:\s*([^\s·]+)", credentials_text)
    for role in ("Patient", "Doctor", "Hospital")
}
if not password_match or any(match is None for match in role_matches.values()):
    pytest.skip("Demo credentials are incomplete", allow_module_level=True)
PASSWORD = password_match.group(1)
CREDS = {role: match.group(1) for role, match in role_matches.items()}
PDF_BYTES = b"%PDF-1.4\n% TEST iteration 6\n%%EOF\n"
UPLOAD_DIR = Path("/app/backend/uploads")


def api(method, path, **kwargs):
    kwargs.setdefault("timeout", 30)
    return requests.request(method, f"{BASE_URL}/api{path}", **kwargs)


def login(role):
    response = api("POST", "/auth/login", json={"email": CREDS[role], "password": PASSWORD})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == CREDS[role]
    assert data["role"] == role.upper()
    return {"Authorization": f"Bearer {data['token']}"}, data


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(backend_env["MONGO_URL"])
    yield client[backend_env["DB_NAME"]]
    client.close()


@pytest.fixture
def cleanup(mongo_db):
    tracked = {"users": [], "appointments": [], "reports": [], "medical_records": []}
    yield tracked
    if tracked["users"]:
        emails = tracked["users"]
        mongo_db.users.delete_many({"email": {"$in": emails}})
        mongo_db.profiles.delete_many({"email": {"$in": emails}})
        mongo_db.notifications.delete_many({"email": {"$in": emails}})
    for collection in ("appointments", "reports", "medical_records"):
        if tracked[collection]:
            mongo_db[collection].delete_many({"id": {"$in": tracked[collection]}})
    if tracked["appointments"]:
        mongo_db.notifications.delete_many({"meta.appointment_id": {"$in": tracked["appointments"]}})
    if tracked["reports"]:
        mongo_db.notifications.delete_many({"meta.report_id": {"$in": tracked["reports"]}})
    if tracked["medical_records"]:
        mongo_db.notifications.delete_many({"meta.record_id": {"$in": tracked["medical_records"]}})
    for report_id in tracked["reports"]:
        for path in UPLOAD_DIR.glob(f"{report_id}.*"):
            path.unlink(missing_ok=True)


def register_patient(cleanup, **overrides):
    suffix = uuid.uuid4().hex[:10]
    payload = {
        "email": f"test_iteration6_{suffix}@example.com",
        "password": "TEST@123",
        "name": "TEST Iteration Six",
        "role": "PATIENT",
        "hospital": "CityCare Hospital",
        "dob": "1993-07-19",
        "gender": "Female",
        "blood": "AB-",
        "phone": "+91 90000 60006",
        "address": "TEST Six Street, Bengaluru",
        "occupation": "QA Engineer",
        "marital": "Married",
        "height": "167 cm",
        "weight": "61 kg",
        "emergency": "TEST Contact · +91 98888 60006",
    }
    payload.update(overrides)
    response = api("POST", "/auth/register", json=payload)
    assert response.status_code == 200, response.text
    cleanup["users"].append(payload["email"])
    data = response.json()
    headers = {"Authorization": f"Bearer {data['token']}"}
    return payload, data, headers


# Server derives all doctor details and rejects unknown/off-duty doctors.
def test_booking_guard_server_values_unknown_and_off_duty(cleanup):
    headers, _ = login("patient")
    payload = {
        "doctor_id": "DOC-2048",
        "date": "2026-12-16",
        "time": "10:30 AM",
        "reason": "TEST booking guard",
        "doctor_name": "TEST Spoofed Doctor",
        "domain": "TEST Fake Specialty",
        "hospital": "TEST Fake Hospital",
        "fee": 1,
    }
    booked = api("POST", "/appointments", headers=headers, json=payload)
    assert booked.status_code == 200, booked.text
    item = booked.json()
    cleanup["appointments"].append(item["id"])
    assert item["doctor_id"] == "DOC-2048"
    assert item["doctor_name"] == "Dr. Ananya Rao"
    assert item["domain"] == "Cardiology"
    assert item["hospital"] == "CityCare Hospital"
    assert item["fee"] == 1200
    assert item["reason"] == payload["reason"]

    listed = api("GET", "/appointments", headers=headers)
    assert listed.status_code == 200
    persisted = next(a for a in listed.json() if a["id"] == item["id"])
    assert persisted["doctor_name"] == "Dr. Ananya Rao" and persisted["fee"] == 1200

    unknown = api("POST", "/appointments", headers=headers, json={
        "doctor_id": "DOC-UNKNOWN", "date": "2026-12-17", "time": "12:00 PM", "reason": "TEST unknown"
    })
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Doctor not found"

    off_duty = api("POST", "/appointments", headers=headers, json={
        "doctor_id": "DOC-8821", "date": "2026-12-17", "time": "12:00 PM", "reason": "TEST off duty"
    })
    assert off_duty.status_code == 400
    assert "off duty" in off_duty.json()["detail"].lower()


# Exact seeded appointment cases: invalid status, patient restriction, cancellation, and owning-doctor attendance.
def test_seeded_status_enum_and_role_cases(mongo_db):
    patient_headers, _ = login("patient")
    doctor_headers, _ = login("doctor")
    originals = {
        apt_id: mongo_db.appointments.find_one({"id": apt_id})["status"]
        for apt_id in ("apt-001", "apt-002")
    }
    original_notification_ids = [
        item["id"]
        for item in mongo_db.notifications.find(
            {"meta.appointment_id": {"$in": ["apt-001", "apt-002"]}}, {"id": 1}
        )
    ]
    try:
        bogus = api("PATCH", "/appointments/apt-002", headers=patient_headers, json={"status": "Bogus"})
        assert bogus.status_code == 400
        detail = bogus.json()["detail"]
        assert "Status must be one of" in detail
        for allowed in ("Upcoming", "Attended", "Not attended", "Cancelled", "Completed"):
            assert allowed in detail

        forbidden = api("PATCH", "/appointments/apt-002", headers=patient_headers, json={"status": "Attended"})
        assert forbidden.status_code == 403
        assert forbidden.json()["detail"] == "Patients can only cancel their own appointments"

        cancelled = api("PATCH", "/appointments/apt-002", headers=patient_headers, json={"status": "Cancelled"})
        assert cancelled.status_code == 200
        assert cancelled.json() == {"ok": True, "status": "Cancelled"}
        assert mongo_db.appointments.find_one({"id": "apt-002"})["status"] == "Cancelled"

        attended = api("PATCH", "/appointments/apt-001", headers=doctor_headers, json={"status": "Attended"})
        assert attended.status_code == 200
        assert attended.json() == {"ok": True, "status": "Attended"}
        assert mongo_db.appointments.find_one({"id": "apt-001"})["status"] == "Attended"
    finally:
        for apt_id, status in originals.items():
            mongo_db.appointments.update_one({"id": apt_id}, {"$set": {"status": status}})
        notification_query = {"meta.appointment_id": {"$in": ["apt-001", "apt-002"]}}
        if original_notification_ids:
            notification_query["id"] = {"$nin": original_notification_ids}
        mongo_db.notifications.delete_many(notification_query)


# Doctors may only use the three clinical outcomes, not Upcoming or Cancelled.
@pytest.mark.parametrize("disallowed_status", ["Upcoming", "Cancelled"])
def test_doctor_status_subset_is_locked(disallowed_status, cleanup):
    patient_headers, _ = login("patient")
    doctor_headers, _ = login("doctor")
    booked = api("POST", "/appointments", headers=patient_headers, json={
        "doctor_id": "DOC-2048", "date": "2026-12-18", "time": "10:30 AM", "reason": "TEST doctor status subset"
    })
    assert booked.status_code == 200, booked.text
    appointment_id = booked.json()["id"]
    cleanup["appointments"].append(appointment_id)
    response = api("PATCH", f"/appointments/{appointment_id}", headers=doctor_headers, json={"status": disallowed_status})
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Doctors can only mark Attended, Not attended, or Completed"
    persisted = api("GET", "/appointments", headers=patient_headers)
    assert persisted.status_code == 200
    item = next(a for a in persisted.json() if a["id"] == appointment_id)
    assert item["status"] == "Upcoming"


# Owning doctors can set each permitted clinical outcome.
def test_doctor_allowed_clinical_outcomes(cleanup):
    patient_headers, _ = login("patient")
    doctor_headers, _ = login("doctor")
    booked = api("POST", "/appointments", headers=patient_headers, json={
        "doctor_id": "DOC-2048", "date": "2026-12-19", "time": "10:30 AM", "reason": "TEST allowed doctor outcomes"
    })
    assert booked.status_code == 200, booked.text
    appointment_id = booked.json()["id"]
    cleanup["appointments"].append(appointment_id)
    for status in ("Attended", "Not attended", "Completed"):
        response = api("PATCH", f"/appointments/{appointment_id}", headers=doctor_headers, json={"status": status})
        assert response.status_code == 200, response.text
        assert response.json() == {"ok": True, "status": status}



# Appointment events create notifications, and read/all-read/delete operations persist.
def test_notification_appointment_lifecycle(cleanup):
    patient_payload, patient, patient_headers = register_patient(cleanup)
    doctor_headers, _ = login("doctor")
    booked = api("POST", "/appointments", headers=patient_headers, json={
        "doctor_id": "DOC-2048", "date": "2026-12-20", "time": "10:30 AM", "reason": "TEST notification lifecycle"
    })
    assert booked.status_code == 200, booked.text
    appointment_id = booked.json()["id"]
    cleanup["appointments"].append(appointment_id)

    attended = api("PATCH", f"/appointments/{appointment_id}", headers=doctor_headers, json={"status": "Attended"})
    assert attended.status_code == 200, attended.text
    reminder = api("POST", f"/appointments/{appointment_id}/send-reminder", headers=patient_headers)
    assert reminder.status_code == 200
    assert reminder.json() == {"ok": True, "delivered": False, "email_configured": False}

    notifications = api("GET", "/notifications", headers=patient_headers)
    assert notifications.status_code == 200
    body = notifications.json()
    assert body["unread"] == 3
    assert {item["kind"] for item in body["items"]} == {
        "appointment_confirmed", "appointment_status", "reminder_sent"
    }
    assert all(item["email"] == patient_payload["email"] for item in body["items"])

    first_id = body["items"][0]["id"]
    marked = api("POST", f"/notifications/{first_id}/read", headers=patient_headers)
    assert marked.status_code == 200 and marked.json() == {"ok": True}
    after_one = api("GET", "/notifications", headers=patient_headers).json()
    assert after_one["unread"] == 2
    assert next(item for item in after_one["items"] if item["id"] == first_id)["read"] is True

    marked_all = api("POST", "/notifications/mark-all-read", headers=patient_headers)
    assert marked_all.status_code == 200
    assert marked_all.json() == {"ok": True, "updated": 2}
    assert api("GET", "/notifications", headers=patient_headers).json()["unread"] == 0

    deleted = api("DELETE", f"/notifications/{first_id}", headers=patient_headers)
    assert deleted.status_code == 200 and deleted.json() == {"ok": True}
    ids = {item["id"] for item in api("GET", "/notifications", headers=patient_headers).json()["items"]}
    assert first_id not in ids


# Patient and doctor report uploads notify the target patient.
def test_report_upload_notifications_for_patient_and_doctor(cleanup):
    payload, _, patient_headers = register_patient(cleanup)
    doctor_headers, _ = login("doctor")

    patient_upload = api(
        "POST", "/reports", headers=patient_headers,
        data={"name": "TEST Patient Upload", "report_type": "Lab report", "provider": "TEST Lab"},
        files={"file": ("patient.pdf", PDF_BYTES, "application/pdf")},
    )
    assert patient_upload.status_code == 200, patient_upload.text
    cleanup["reports"].append(patient_upload.json()["id"])

    doctor_upload = api(
        "POST", "/reports", headers=doctor_headers,
        data={"name": "TEST Doctor Upload", "report_type": "Consultation note", "provider": "Dr. Ananya Rao", "patient_email": payload["email"]},
        files={"file": ("doctor.pdf", PDF_BYTES, "application/pdf")},
    )
    assert doctor_upload.status_code == 200, doctor_upload.text
    cleanup["reports"].append(doctor_upload.json()["id"])
    assert doctor_upload.json()["patient_email"] == payload["email"]

    body = api("GET", "/notifications", headers=patient_headers).json()
    report_items = [item for item in body["items"] if item["kind"] == "report_uploaded"]
    assert len(report_items) == 2
    assert {item["title"] for item in report_items} == {"New report available"}
    assert {item["meta"]["report_id"] for item in report_items} == set(cleanup["reports"])


# Medical-record creation and Health ID verification notify the patient.
def test_record_and_health_id_verification_notifications(cleanup):
    payload, patient, patient_headers = register_patient(cleanup)
    doctor_headers, _ = login("doctor")
    record = api("POST", "/medical-records", headers=doctor_headers, json={
        "patient_email": payload["email"],
        "patient_name": payload["name"],
        "diagnosis": "TEST healthy review",
        "symptoms": "TEST none",
        "notes": "TEST iteration 6",
        "treatment": "Observation",
        "prescription": "None",
        "follow_up": "2027-01-10",
    })
    assert record.status_code == 200, record.text
    cleanup["medical_records"].append(record.json()["id"])

    verified = api("POST", f"/verify-health-id?health_id={patient['patient_id']}", headers=doctor_headers)
    assert verified.status_code == 200, verified.text
    assert verified.json()["health_id"] == patient["patient_id"]
    assert verified.json()["name"] == payload["name"]

    notifications = api("GET", "/notifications", headers=patient_headers).json()["items"]
    assert {item["kind"] for item in notifications} == {"record_created", "health_id_verified"}
    record_notification = next(item for item in notifications if item["kind"] == "record_created")
    assert record_notification["meta"]["record_id"] == record.json()["id"]
    verified_notification = next(item for item in notifications if item["kind"] == "health_id_verified")
    assert verified_notification["meta"]["accessed_by"] == "Dr. Ananya Rao"


# Every extended registration field survives login and profile retrieval.
def test_extended_patient_registration_login_profile_round_trip(cleanup):
    payload, registered, _ = register_patient(cleanup)
    assert registered["email"] == payload["email"]
    signed_in = api("POST", "/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert signed_in.status_code == 200, signed_in.text
    token = signed_in.json()["token"]
    profile = api("GET", "/profile", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200, profile.text
    data = profile.json()
    for field in ("dob", "gender", "blood", "phone", "address", "occupation", "marital", "height", "weight", "emergency"):
        assert data[field] == payload[field]
    assert data["email"] == payload["email"]
    assert data["name"] == payload["name"]
    assert data["patient_id"] == registered["patient_id"]
