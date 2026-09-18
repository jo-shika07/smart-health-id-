"""Massive-scope regression tests for registration, password reset, duty, AI suggestions, role-scoped views, and appointment body PATCH."""

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
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

credentials_text = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
password_match = re.search(r"accounts use[^\n]*password:\s*`([^`]+)`", credentials_text, re.I)
role_matches = {
    role.lower(): re.search(rf"(?im)^- {role}:\s*([^\s·]+)", credentials_text)
    for role in ("Patient", "Doctor", "Hospital")
}
if not password_match or any(match is None for match in role_matches.values()):
    pytest.skip("Demo credentials are incomplete in test_credentials.md", allow_module_level=True)
DEMO_PASSWORD = password_match.group(1)
CREDS = {role: (match.group(1), DEMO_PASSWORD) for role, match in role_matches.items()}


def request(method, path, **kwargs):
    kwargs.setdefault("timeout", 30)
    return requests.request(method, f"{BASE_URL}/api{path}", **kwargs)


def login(role, password=None):
    email, expected_password = CREDS[role]
    response = request("POST", "/auth/login", json={"email": email, "password": password or expected_password})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == email
    assert data["role"] == role.upper()
    assert isinstance(data["token"], str) and data["token"]
    return {"Authorization": f"Bearer {data['token']}"}, data


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(backend_env["MONGO_URL"])
    database = client[backend_env["DB_NAME"]]
    yield database
    client.close()


@pytest.fixture
def cleanup(mongo_db):
    tracked = {"users": [], "appointments": [], "reports": [], "medical_records": [], "reset_tokens": []}
    yield tracked
    if tracked["users"]:
        mongo_db.users.delete_many({"email": {"$in": tracked["users"]}})
        mongo_db.profiles.delete_many({"email": {"$in": tracked["users"]}})
        mongo_db.password_resets.delete_many({"email": {"$in": tracked["users"]}})
    for collection in ("appointments", "reports", "medical_records"):
        if tracked[collection]:
            mongo_db[collection].delete_many({"id": {"$in": tracked[collection]}})
    if tracked["reset_tokens"]:
        mongo_db.password_resets.delete_many({"token": {"$in": tracked["reset_tokens"]}})


# Registration for all roles, role-specific fields, validation, persistence, and bcrypt storage.
def test_registration_all_roles_duplicate_and_short_password(mongo_db, cleanup):
    suffix = uuid.uuid4().hex[:10]
    cases = [
        ("PATIENT", {"name": "TEST Patient", "specialty": None, "hospital": "CityCare Hospital"}),
        ("DOCTOR", {"name": "TEST Doctor", "specialty": "Neurology", "hospital": "TEST QA Hospital"}),
        ("HOSPITAL", {"name": "TEST QA Hospital", "specialty": None, "hospital": None}),
    ]
    created = []
    for role, fields in cases:
        email = f"test_{role.lower()}_{suffix}@example.com"
        cleanup["users"].append(email)
        payload = {"email": email, "password": "TEST@123", "role": role, **fields}
        response = request("POST", "/auth/register", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        created.append((role, email, data))
        assert data["email"] == email
        assert data["name"] == fields["name"]
        assert data["role"] == role
        assert isinstance(data["token"], str) and data["token"]
        assert "password_hash" not in data and "_id" not in data
        if role == "PATIENT":
            assert data["patient_id"].startswith("SHID-")
        elif role == "DOCTOR":
            assert data["doctor_id"].startswith("DOC-")
            assert data["specialty"] == "Neurology"
            assert data["hospital"] == "TEST QA Hospital"
        else:
            assert data["hospital_id"].startswith("HSP-")

        saved = mongo_db.users.find_one({"email": email})
        assert saved["role"] == role
        assert saved["password_hash"].startswith("$2b$")

    duplicate = request("POST", "/auth/register", json={
        "email": created[0][1], "password": "TEST@123", "name": "TEST Duplicate", "role": "PATIENT"
    })
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]

    short_email = f"test_short_{suffix}@example.com"
    short = request("POST", "/auth/register", json={
        "email": short_email, "password": "12345", "name": "TEST Short", "role": "PATIENT"
    })
    assert short.status_code == 400
    assert short.json()["detail"] == "Password must be at least 6 characters"
    assert mongo_db.users.find_one({"email": short_email}) is None


# Forgot/reset lifecycle including one-use, invalid, expired token, and login with the replacement password.
def test_forgot_reset_password_lifecycle(mongo_db, cleanup):
    email = f"test_reset_{uuid.uuid4().hex[:10]}@example.com"
    cleanup["users"].append(email)
    registered = request("POST", "/auth/register", json={
        "email": email, "password": "TEST@123", "name": "TEST Reset User", "role": "PATIENT"
    })
    assert registered.status_code == 200, registered.text

    forgot = request("POST", "/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    token = forgot.json()["demo_token"]
    assert forgot.json()["ok"] is True
    assert isinstance(token, str) and len(token) >= 12

    reset = request("POST", "/auth/reset-password", json={"token": token, "password": "TEST@456"})
    assert reset.status_code == 200
    assert reset.json() == {"ok": True, "email": email}

    signed_in = request("POST", "/auth/login", json={"email": email, "password": "TEST@456"})
    assert signed_in.status_code == 200
    assert signed_in.json()["email"] == email

    reused = request("POST", "/auth/reset-password", json={"token": token, "password": "TEST@789"})
    assert reused.status_code == 400
    assert "Invalid or expired" in reused.json()["detail"]

    invalid = request("POST", "/auth/reset-password", json={"token": "TEST-invalid-token", "password": "TEST@789"})
    assert invalid.status_code == 400

    expired_token = f"TEST-expired-{uuid.uuid4()}"
    cleanup["reset_tokens"].append(expired_token)
    mongo_db.password_resets.insert_one({
        "email": email,
        "token": expired_token,
        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    })
    expired = request("POST", "/auth/reset-password", json={"token": expired_token, "password": "TEST@789"})
    assert expired.status_code == 400
    assert expired.json()["detail"] == "Reset code has expired"


# Doctor duty state is reflected in the directory and blocks/allows patient bookings.
def test_doctor_duty_toggle_booking_guard_and_persistence(mongo_db, cleanup):
    doctor_headers, doctor = login("doctor")
    patient_headers, _ = login("patient")
    payload = {
        "doctor_id": doctor["doctor_id"], "doctor_name": doctor["name"], "domain": doctor["specialty"],
        "hospital": doctor["hospital"], "date": "2026-11-18", "time": "10:30 AM",
        "reason": "TEST duty guard", "fee": doctor["fee"],
    }
    try:
        off = request("PUT", "/doctor/duty", headers=doctor_headers, json={"on_duty": False})
        assert off.status_code == 200 and off.json() == {"ok": True, "on_duty": False}
        assert mongo_db.users.find_one({"email": CREDS["doctor"][0]})["on_duty"] is False

        listed = request("GET", "/doctors", headers=patient_headers)
        assert listed.status_code == 200
        directory_doctor = next(item for item in listed.json() if item["email"] == CREDS["doctor"][0])
        assert directory_doctor["on_duty"] is False

        blocked = request("POST", "/appointments", headers=patient_headers, json=payload)
        assert blocked.status_code == 400
        assert "off duty" in blocked.json()["detail"].lower()

        on = request("PUT", "/doctor/duty", headers=doctor_headers, json={"on_duty": True})
        assert on.status_code == 200 and on.json()["on_duty"] is True
        booked = request("POST", "/appointments", headers=patient_headers, json=payload)
        assert booked.status_code == 200, booked.text
        appointment = booked.json()
        cleanup["appointments"].append(appointment["id"])
        assert appointment["status"] == "Upcoming"
        assert appointment["doctor_id"] == doctor["doctor_id"]
    finally:
        request("PUT", "/doctor/duty", headers=doctor_headers, json={"on_duty": True})


# Deterministic AI specialty classifier and matching seeded doctor suggestions.
@pytest.mark.parametrize("symptoms,specialty,doctor_name", [
    ("I have chest pain and palpitations", "Cardiology", "Dr. Ananya Rao"),
    ("itchy skin rash", "Dermatology", "Dr. Priya Nair"),
    ("knee joint hurts", "Orthopedics", "Dr. Vikram Singh"),
])
def test_ai_specialist_suggestions(symptoms, specialty, doctor_name):
    headers, _ = login("patient")
    response = request("POST", "/ai/suggest-specialist", headers=headers, json={"symptoms": symptoms})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["specialty"] == specialty
    assert isinstance(data["doctors"], list) and data["doctors"]
    assert any(item["name"] == doctor_name and item["specialty"] == specialty for item in data["doctors"])
    assert all("password_hash" not in item and "_id" not in item for item in data["doctors"])


# Doctor patient list and full patient detail aggregate contract.
def test_doctor_patients_and_patient_detail_contract():
    headers, _ = login("doctor")
    response = request("GET", "/doctor/patients", headers=headers)
    assert response.status_code == 200
    patients = response.json()
    assert isinstance(patients, list) and patients
    assert all(isinstance(item["report_count"], int) and isinstance(item["record_count"], int) for item in patients)
    assert {"patient@example.com"}.issubset({item["email"] for item in patients})

    target = next(item for item in patients if item["email"] == "patient@example.com")
    detail = request("GET", f"/patients/{target['email']}/detail", headers=headers)
    assert detail.status_code == 200
    data = detail.json()
    assert data["patient"]["email"] == target["email"]
    assert data["patient"]["name"] == "Aarav Sharma"
    for key in ("profile", "reports", "records", "vaccinations", "appointments"):
        assert key in data
    assert isinstance(data["profile"], dict)
    assert all(isinstance(data[key], list) for key in ("reports", "records", "vaccinations", "appointments"))
    assert data["records"]
    assert data["appointments"]


# Appointment PATCH consumes JSON, persists patient rescheduling and doctor status, and rejects hospitals.
def test_appointment_json_patch_role_workflow(mongo_db, cleanup):
    patient_headers, _ = login("patient")
    doctor_headers, doctor = login("doctor")
    hospital_headers, _ = login("hospital")
    created = request("POST", "/appointments", headers=patient_headers, json={
        "doctor_id": doctor["doctor_id"], "doctor_name": doctor["name"], "domain": doctor["specialty"],
        "hospital": doctor["hospital"], "date": "2026-11-20", "time": "09:00 AM",
        "reason": "TEST JSON PATCH", "fee": doctor["fee"],
    })
    assert created.status_code == 200, created.text
    appointment_id = created.json()["id"]
    cleanup["appointments"].append(appointment_id)

    patient_patch = request("PATCH", f"/appointments/{appointment_id}", headers=patient_headers, json={
        "date": "2026-11-21", "time": "02:30 PM"
    })
    assert patient_patch.status_code == 200
    assert patient_patch.json() == {"ok": True, "date": "2026-11-21", "time": "02:30 PM"}
    saved = mongo_db.appointments.find_one({"id": appointment_id})
    assert saved["date"] == "2026-11-21" and saved["time"] == "02:30 PM"

    doctor_patch = request("PATCH", f"/appointments/{appointment_id}", headers=doctor_headers, json={"status": "Attended"})
    assert doctor_patch.status_code == 200
    assert doctor_patch.json() == {"ok": True, "status": "Attended"}
    assert mongo_db.appointments.find_one({"id": appointment_id})["status"] == "Attended"

    forbidden = request("PATCH", f"/appointments/{appointment_id}", headers=hospital_headers, json={"status": "Completed"})
    assert forbidden.status_code == 403
    assert "Hospitals cannot mutate" in forbidden.json()["detail"]
    assert mongo_db.appointments.find_one({"id": appointment_id})["status"] == "Attended"


# Hospital pages are name-scoped and return seeded doctor/patient/appointment/vaccination data.
def test_hospital_scoped_endpoints_seeded_data():
    headers, hospital = login("hospital")
    doctors = request("GET", "/hospital/doctors", headers=headers)
    patients = request("GET", "/hospital/patients", headers=headers)
    appointments = request("GET", "/appointments", headers=headers)
    vaccinations = request("GET", "/vaccinations", headers=headers)
    reports = request("GET", "/reports", headers=headers)
    for response in (doctors, patients, appointments, vaccinations, reports):
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    assert len(doctors.json()) == 6
    assert all(item["hospital"] == hospital["name"] for item in doctors.json())
    assert len(patients.json()) == 5
    assert all(item["hospital"] == hospital["name"] for item in patients.json())
    assert all(isinstance(item["profile"], dict) and isinstance(item["appointment_count"], int) for item in patients.json())
    assert len(appointments.json()) >= 1
    assert all(item["hospital"] == hospital["name"] for item in appointments.json())
    assert len(vaccinations.json()) == 5
    assert all(item["provider"] == hospital["name"] for item in vaccinations.json())
    report_data = reports.json()
    assert len(report_data) >= 4
    mandatory_reports = {
        "Knee X-ray": "simran@example.com",
        "Dermatology biopsy": "riya@example.com",
        "Stress test report": "karthik@example.com",
        "Complete Blood Count": "patient@example.com",
    }
    by_name = {item["name"]: item for item in report_data}
    assert mandatory_reports.keys() <= by_name.keys()
    for name, patient_email in mandatory_reports.items():
        item = by_name[name]
        assert item["hospital"] == hospital["name"]
        assert item["patient_email"] == patient_email
        downloaded = request("GET", f"/reports/{item['id']}/file", headers=headers)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.headers["Content-Type"].startswith("application/pdf")
        assert downloaded.content.startswith(b"%PDF")

    # Patient report lists remain strictly self-scoped after broadening the hospital query.
    for email, expected_name in (
        ("riya@example.com", "Dermatology biopsy"),
        ("karthik@example.com", "Stress test report"),
    ):
        signed_in = request("POST", "/auth/login", json={"email": email, "password": DEMO_PASSWORD})
        assert signed_in.status_code == 200, signed_in.text
        patient_headers = {"Authorization": f"Bearer {signed_in.json()['token']}"}
        patient_reports = request("GET", "/reports", headers=patient_headers)
        assert patient_reports.status_code == 200, patient_reports.text
        patient_data = patient_reports.json()
        assert expected_name in {item["name"] for item in patient_data}
        assert all(item["patient_email"] == email for item in patient_data)


# Database-backed verification finds both seeded patients and returns 404 for unknown IDs.
@pytest.mark.parametrize("role", ["doctor", "hospital"])
def test_verify_health_id_seeded_patients_and_unknown(role):
    headers, _ = login(role)
    for health_id, expected_name in (("SHID-10001", "Aarav Sharma"), ("SHID-10002", "Riya Kapoor")):
        response = request("POST", f"/verify-health-id?health_id={health_id}", headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["health_id"] == health_id
        assert data["name"] == expected_name
        assert data["status"] == "Verified"
    missing = request("POST", "/verify-health-id?health_id=SHID-99999", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Health ID not found"
