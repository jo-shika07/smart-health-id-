from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os, uuid, bcrypt, jwt, logging, json, asyncio, mimetypes, secrets, re
import resend
try:
    from openai import AsyncOpenAI as _AsyncOpenAI
    _openai_available = True
except ImportError:
    _openai_available = False

ROOT_DIR = Path(__file__).parent
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev").strip() or "onboarding@resend.dev"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
FRONTEND_URL = os.environ.get("FRONTEND_URL", "").strip()
IS_PRODUCTION = os.environ.get("PRODUCTION", "").lower() in ("1", "true", "yes")
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

app = FastAPI(title="Smart Health ID API")
api = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart-health-id")

DEMO_PASSWORD = "Demo@123"
ALLOWED_UPLOAD_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg", "image/webp"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
HOSPITAL_NAME_DEFAULT = "CityCare Hospital"

# Specialty keyword mapping for AI suggestions
SPECIALTY_KEYWORDS = {
    "Cardiology": ["heart", "chest pain", "chest tight", "palpitat", "blood pressure", "bp ", "cardiac"],
    "Dermatology": ["skin", "rash", "acne", "itch", "eczema", "psorias", "hives", "hair loss"],
    "Orthopedics": ["joint", "bone", "fracture", "back pain", "knee", "shoulder", "sprain", "muscle"],
    "Pediatrics": ["child", "kid", "baby", "toddler", "infant", "my son", "my daughter"],
    "Neurology": ["migraine", "seizure", "numb", "tingling", "dizzy", "vertigo", "memory loss"],
    "General Medicine": ["fever", "cough", "cold", "flu", "throat", "stomach", "nausea", "diarr", "fatigue", "headache", "tired"],
}

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def public_user(user: dict) -> dict:
    return {k: v for k, v in user.items() if k not in {"_id", "password_hash"}}

def create_token(user: dict) -> str:
    return jwt.encode({"sub": str(user["email"]), "role": user["role"], "exp": datetime.now(timezone.utc) + timedelta(hours=8), "type": "access"}, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def current_user(request: Request) -> dict:
    token = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(401, "Please sign in to continue")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"email": payload.get("sub")}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(401, "Session expired")
        return user
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Session expired")

async def require_role(user: dict, roles: List[str]):
    if user["role"] not in roles:
        raise HTTPException(403, "You do not have access to this area")

async def _notify(email: str, kind: str, title: str, text: str, meta: Optional[dict] = None):
    """Insert a notification for a user. Fire-and-forget: exceptions are swallowed to avoid breaking main flow."""
    try:
        await db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "email": email,
            "kind": kind,
            "title": title,
            "text": text,
            "meta": meta or {},
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        logger.exception("notify failed for %s", email)

# -------- Models --------

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str  # PATIENT | DOCTOR | HOSPITAL
    specialty: Optional[str] = None
    hospital: Optional[str] = None
    # Extended patient profile (all optional)
    dob: Optional[str] = None
    gender: Optional[str] = None
    blood: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    occupation: Optional[str] = None
    marital: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    emergency: Optional[str] = None

class ForgotInput(BaseModel):
    email: EmailStr

class ResetInput(BaseModel):
    token: str
    password: str

class AppointmentInput(BaseModel):
    doctor_id: str
    date: str
    time: str
    reason: str

ALLOWED_STATUSES = {"Upcoming", "Attended", "Not attended", "Cancelled", "Completed"}

class ProfileInput(BaseModel):
    name: str
    phone: str
    occupation: str
    marital: str
    address: str
    height: str
    weight: str
    emergency: str

class SymptomInput(BaseModel):
    message: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

class MedicalRecordInput(BaseModel):
    patient_email: str
    patient_name: str
    diagnosis: str
    symptoms: str
    notes: str = ""
    treatment: str = ""
    prescription: str = ""
    follow_up: str = ""
    report_id: Optional[str] = None

class DutyInput(BaseModel):
    on_duty: bool

class VaccinationInput(BaseModel):
    patient_email: str
    patient_name: str
    vaccine: str
    dose: str
    date: str
    next_due: Optional[str] = None

# -------- Root & auth --------

@api.get("/")
async def root():
    return {
        "service": "Smart Health ID",
        "status": "healthy",
        "email_configured": bool(RESEND_API_KEY),
        "ai_configured": bool(OPENAI_API_KEY and _openai_available),
    }

@api.post("/auth/register")
async def register(payload: RegisterInput):
    email = payload.email.lower().strip()
    role = payload.role.upper()
    if role not in {"PATIENT", "DOCTOR", "HOSPITAL"}:
        raise HTTPException(400, "Role must be PATIENT, DOCTOR or HOSPITAL")
    if len(payload.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(409, "An account with this email already exists")
    doc = {
        "email": email,
        "name": payload.name.strip(),
        "role": role,
        "password_hash": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if role == "PATIENT":
        count = await db.users.count_documents({"role": "PATIENT"})
        doc["patient_id"] = f"SHID-{10001 + count:05d}"
        doc["hospital"] = payload.hospital or HOSPITAL_NAME_DEFAULT
    elif role == "DOCTOR":
        count = await db.users.count_documents({"role": "DOCTOR"})
        doc["doctor_id"] = f"DOC-{2049 + count}"
        doc["specialty"] = payload.specialty or "General Medicine"
        doc["hospital"] = payload.hospital or HOSPITAL_NAME_DEFAULT
        doc["on_duty"] = True
        doc["fee"] = 900
        doc["experience"] = "0 yrs"
    else:  # HOSPITAL
        count = await db.users.count_documents({"role": "HOSPITAL"})
        doc["hospital_id"] = f"HSP-{301 + count}"
    await db.users.insert_one(doc)
    # For patients, save extended profile fields
    if role == "PATIENT":
        profile_fields = {k: getattr(payload, k) for k in ["dob", "gender", "blood", "phone", "address", "occupation", "marital", "height", "weight", "emergency"] if getattr(payload, k)}
        if profile_fields:
            await db.profiles.replace_one(
                {"email": email},
                {"email": email, "name": doc["name"], "patient_id": doc.get("patient_id"), **profile_fields, "updated_at": datetime.now(timezone.utc).isoformat()},
                upsert=True,
            )
    token = create_token(doc)
    result = public_user(doc) | {"token": token}
    response = JSONResponse(result)
    response.set_cookie("access_token", token, httponly=True, secure=IS_PRODUCTION, samesite="none" if IS_PRODUCTION else "lax", max_age=28800, path="/")
    return response

@api.post("/auth/login")
async def login(payload: LoginInput):
    email = payload.email.strip().lower()
    user = await db.users.find_one({"email": email})
    if not user or not check_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    result = public_user(user) | {"token": create_token(user)}
    response = JSONResponse(result)
    response.set_cookie("access_token", result["token"], httponly=True, secure=IS_PRODUCTION, samesite="none" if IS_PRODUCTION else "lax", max_age=28800, path="/")
    return response

@api.post("/auth/logout")
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("access_token", path="/")
    return response

@api.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return user

@api.post("/auth/forgot-password")
async def forgot_password(payload: ForgotInput):
    email = payload.email.strip().lower()
    user = await db.users.find_one({"email": email})
    # Always return success shape to avoid user enumeration; but return the demo token for known emails.
    if not user:
        return {"ok": True, "demo_token": None, "message": "If this email is registered, a reset code has been sent."}
    token = secrets.token_urlsafe(12)
    await db.password_resets.replace_one(
        {"email": email},
        {"email": email, "token": token, "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()},
        upsert=True,
    )
    logger.info("[password-reset] token for %s: %s", email, token)
    # Send email if Resend is configured
    if RESEND_API_KEY:
        html = f"""<div style="font-family:Arial;padding:24px"><h2>Smart Health ID · Password reset</h2>
        <p>Use this code to reset your password. It expires in 30 minutes.</p>
        <p style="font-size:22px;font-weight:800;letter-spacing:1px;background:#eef6f9;padding:12px 16px;border-radius:8px;display:inline-block">{token}</p></div>"""
        try:
            await asyncio.to_thread(resend.Emails.send, {"from": SENDER_EMAIL, "to": [email], "subject": "Smart Health ID reset code", "html": html})
        except Exception:
            logger.exception("Reset email failed")
    return {"ok": True, "demo_token": token, "message": "Reset code generated. In demo mode we show it on-screen."}

@api.post("/auth/reset-password")
async def reset_password(payload: ResetInput):
    if len(payload.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    doc = await db.password_resets.find_one({"token": payload.token})
    if not doc:
        raise HTTPException(400, "Invalid or expired reset code")
    if datetime.fromisoformat(doc["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(400, "Reset code has expired")
    await db.users.update_one({"email": doc["email"]}, {"$set": {"password_hash": hash_password(payload.password)}})
    await db.password_resets.delete_one({"token": payload.token})
    return {"ok": True, "email": doc["email"]}

# -------- Dashboard --------

@api.get("/dashboard")
async def dashboard(user: dict = Depends(current_user)):
    if user["role"] == "PATIENT":
        appointments = await db.appointments.find({"patient_email": user["email"]}, {"_id": 0}).sort("date", 1).to_list(20)
        return {"user": user, "appointments": appointments}
    if user["role"] == "DOCTOR":
        appointments = await db.appointments.find({"doctor_id": user.get("doctor_id")}, {"_id": 0}).sort("date", 1).to_list(20)
        patients = await _doctor_patient_emails(user.get("doctor_id"), user["email"])
        return {"user": user, "appointments": appointments, "patient_count": len(patients), "on_duty": user.get("on_duty", True)}
    hosp = user.get("name") or HOSPITAL_NAME_DEFAULT
    doctors = await db.users.count_documents({"role": "DOCTOR", "hospital": hosp})
    patients = await db.users.count_documents({"role": "PATIENT", "hospital": hosp})
    appts = await db.appointments.count_documents({"hospital": hosp})
    return {"user": user, "doctor_count": doctors, "patient_count": patients, "appointment_count": appts}

# -------- Appointments --------

@api.get("/appointments")
async def appointments(user: dict = Depends(current_user)):
    if user["role"] == "PATIENT":
        query = {"patient_email": user["email"]}
    elif user["role"] == "DOCTOR":
        query = {"doctor_id": user.get("doctor_id")}
    else:
        query = {"hospital": user.get("name", HOSPITAL_NAME_DEFAULT)}
    return await db.appointments.find(query, {"_id": 0}).sort("date", 1).to_list(200)

@api.post("/appointments")
async def book_appointment(payload: AppointmentInput, user: dict = Depends(current_user)):
    await require_role(user, ["PATIENT"])
    doctor = await db.users.find_one({"doctor_id": payload.doctor_id, "role": "DOCTOR"}, {"_id": 0, "password_hash": 0})
    if not doctor:
        raise HTTPException(404, "Doctor not found")
    if not doctor.get("on_duty", True):
        raise HTTPException(400, "This doctor is currently off duty. Please choose another doctor.")
    appointment = {
        "id": str(uuid.uuid4()),
        "doctor_id": doctor["doctor_id"],
        "doctor_name": doctor["name"],
        "domain": doctor.get("specialty", "General Medicine"),
        "hospital": doctor.get("hospital", HOSPITAL_NAME_DEFAULT),
        "fee": doctor.get("fee", 900),
        "date": payload.date,
        "time": payload.time,
        "reason": payload.reason,
        "patient_email": user["email"],
        "patient_name": user["name"],
        "status": "Upcoming",
        "reminder_sent": False,
        "booked_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.appointments.insert_one(appointment)
    await _notify(user["email"], "appointment_confirmed", "Appointment confirmed",
                  f"Your visit with {doctor['name']} on {payload.date} at {payload.time} is booked.",
                  {"appointment_id": appointment["id"]})
    return {k: v for k, v in appointment.items() if k != "_id"}

class AppointmentUpdateInput(BaseModel):
    status: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None

@api.patch("/appointments/{appointment_id}")
async def update_appointment(appointment_id: str, payload: AppointmentUpdateInput, user: dict = Depends(current_user)):
    apt = await db.appointments.find_one({"id": appointment_id}, {"_id": 0})
    if not apt:
        raise HTTPException(404, "Appointment not found")
    if user["role"] == "PATIENT" and apt.get("patient_email") != user["email"]:
        raise HTTPException(403, "You cannot modify another patient's appointment")
    if user["role"] == "DOCTOR" and apt.get("doctor_id") != user.get("doctor_id"):
        raise HTTPException(403, "You cannot modify an appointment outside your care")
    if user["role"] == "HOSPITAL":
        raise HTTPException(403, "Hospitals cannot mutate patient appointments directly")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    if "status" in updates:
        if updates["status"] not in ALLOWED_STATUSES:
            raise HTTPException(400, f"Status must be one of {sorted(ALLOWED_STATUSES)}")
        if user["role"] == "PATIENT" and updates["status"] not in {"Cancelled"}:
            raise HTTPException(403, "Patients can only cancel their own appointments")
        if user["role"] == "DOCTOR" and updates["status"] not in {"Attended", "Not attended", "Completed"}:
            raise HTTPException(403, "Doctors can only mark Attended, Not attended, or Completed")
    await db.appointments.update_one({"id": appointment_id}, {"$set": updates})
    # Notify patient of status/date changes triggered by doctor
    if user["role"] == "DOCTOR":
        if "status" in updates:
            await _notify(apt["patient_email"], "appointment_status", f"Appointment marked {updates['status']}",
                          f"{user['name']} updated your appointment with status: {updates['status']}.", {"appointment_id": apt["id"]})
        if "date" in updates or "time" in updates:
            await _notify(apt["patient_email"], "appointment_rescheduled", "Appointment rescheduled",
                          f"{user['name']} rescheduled your visit to {updates.get('date', apt['date'])} at {updates.get('time', apt['time'])}.",
                          {"appointment_id": apt["id"]})
    return {"ok": True, **updates}

@api.post("/appointments/{appointment_id}/send-reminder")
async def send_reminder_now(appointment_id: str, user: dict = Depends(current_user)):
    apt = await db.appointments.find_one({"id": appointment_id}, {"_id": 0})
    if not apt:
        raise HTTPException(404, "Appointment not found")
    if user["role"] == "PATIENT" and apt.get("patient_email") != user["email"]:
        raise HTTPException(403, "You cannot trigger reminders for another patient")
    if user["role"] == "DOCTOR" and apt.get("doctor_id") != user.get("doctor_id"):
        raise HTTPException(403, "You cannot trigger reminders outside your care")
    if user["role"] == "HOSPITAL":
        raise HTTPException(403, "Hospitals cannot send patient reminders directly")
    ok = await _send_reminder_email(apt)
    await db.appointments.update_one({"id": appointment_id}, {"$set": {"reminder_sent": True, "reminder_sent_at": datetime.now(timezone.utc).isoformat()}})
    await _notify(apt["patient_email"], "reminder_sent", "Appointment reminder sent",
                  f"A reminder for your {apt.get('date','')} visit with {apt.get('doctor_name','')} was sent.",
                  {"appointment_id": appointment_id})
    return {"ok": True, "delivered": ok, "email_configured": bool(RESEND_API_KEY)}

# -------- Profile --------

@api.get("/profile")
async def profile(user: dict = Depends(current_user)):
    if user["role"] != "PATIENT":
        return user
    profile_data = await db.profiles.find_one({"email": user["email"]}, {"_id": 0})
    return profile_data or {"email": user["email"], "name": user["name"], "phone": "+91 98765 43210", "occupation": "Product Designer", "marital": "Single", "address": "Bengaluru, Karnataka", "height": "178 cm", "weight": "72 kg", "emergency": "Meera Sharma · +91 98111 22334", "dob": "12 Aug 1996", "gender": "Male", "blood": "O+", "patient_id": user.get("patient_id", "SHID-10001")}

@api.put("/profile")
async def update_profile(payload: ProfileInput, user: dict = Depends(current_user)):
    await require_role(user, ["PATIENT"])
    data = payload.model_dump() | {"email": user["email"], "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.profiles.replace_one({"email": user["email"]}, data, upsert=True)
    return {k: v for k, v in data.items() if k != "_id"}

# -------- Health ID verification --------

@api.post("/verify-health-id")
async def verify_health_id(health_id: str, user: dict = Depends(current_user)):
    await require_role(user, ["DOCTOR", "HOSPITAL"])
    patient = await db.users.find_one({"patient_id": health_id.strip().upper(), "role": "PATIENT"}, {"_id": 0, "password_hash": 0})
    if not patient:
        raise HTTPException(404, "Health ID not found")
    prof = await db.profiles.find_one({"email": patient["email"]}, {"_id": 0}) or {}
    await _notify(patient["email"], "health_id_verified", "Health ID verified",
                  f"{user['name']} accessed your basic identity via Health ID verification.",
                  {"accessed_by": user["name"], "role": user["role"]})
    return {
        "health_id": patient.get("patient_id"),
        "name": patient["name"],
        "dob": prof.get("dob", "—"),
        "gender": prof.get("gender", "—"),
        "blood": prof.get("blood", "—"),
        "status": "Verified",
        "consent": "Basic identity shared",
        "accessed_by": user["name"],
        "accessed_at": datetime.now(timezone.utc).isoformat(),
    }

# -------- Search --------

@api.get("/search")
async def search(q: str, user: dict = Depends(current_user)):
    term = q.lower().strip()
    if not term:
        return []
    doctors = await db.users.find({"role": "DOCTOR"}, {"_id": 0, "password_hash": 0}).to_list(50)
    results = []
    for d in doctors:
        if term in f"{d.get('name','')} {d.get('specialty','')} {d.get('hospital','')}".lower():
            results.append({"type": "Doctor", "title": d["name"], "meta": f"{d.get('specialty','')} · {d.get('hospital','')}"})
    return results

# -------- Doctors directory --------

@api.get("/doctors")
async def doctors_list(user: dict = Depends(current_user)):
    docs = await db.users.find({"role": "DOCTOR"}, {"_id": 0, "password_hash": 0}).to_list(100)
    return docs

@api.put("/doctor/duty")
async def toggle_duty(payload: DutyInput, user: dict = Depends(current_user)):
    await require_role(user, ["DOCTOR"])
    await db.users.update_one({"email": user["email"]}, {"$set": {"on_duty": payload.on_duty}})
    return {"ok": True, "on_duty": payload.on_duty}

async def _doctor_patient_emails(doctor_id: str, doctor_email: str) -> List[str]:
    apt_emails = await db.appointments.distinct("patient_email", {"doctor_id": doctor_id, "status": {"$in": ["Attended", "Completed", "Not attended", "Upcoming"]}})
    rec_emails = await db.medical_records.distinct("patient_email", {"doctor_email": doctor_email})
    return sorted(set(apt_emails) | set(rec_emails))

@api.get("/doctor/patients")
async def doctor_patients(user: dict = Depends(current_user)):
    await require_role(user, ["DOCTOR"])
    emails = await _doctor_patient_emails(user.get("doctor_id"), user["email"])
    if not emails:
        return []
    patients = await db.users.find({"email": {"$in": emails}, "role": "PATIENT"}, {"_id": 0, "password_hash": 0}).to_list(100)
    out = []
    for p in patients:
        prof = await db.profiles.find_one({"email": p["email"]}, {"_id": 0}) or {}
        last_visit = await db.appointments.find_one({"patient_email": p["email"], "doctor_id": user.get("doctor_id")}, {"_id": 0}, sort=[("date", -1)])
        report_count = await db.reports.count_documents({"patient_email": p["email"]})
        record_count = await db.medical_records.count_documents({"patient_email": p["email"], "doctor_email": user["email"]})
        out.append({**p, "profile": prof, "last_visit": last_visit, "report_count": report_count, "record_count": record_count})
    return out

@api.get("/patients/{email}/detail")
async def patient_detail(email: str, user: dict = Depends(current_user)):
    await require_role(user, ["DOCTOR", "HOSPITAL"])
    p = await db.users.find_one({"email": email.lower(), "role": "PATIENT"}, {"_id": 0, "password_hash": 0})
    if not p:
        raise HTTPException(404, "Patient not found")
    prof = await db.profiles.find_one({"email": p["email"]}, {"_id": 0}) or {}
    reports = await db.reports.find({"patient_email": p["email"]}, {"_id": 0}).sort("uploaded_at", -1).to_list(50)
    records = await db.medical_records.find({"patient_email": p["email"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    vaccinations = await db.vaccinations.find({"patient_email": p["email"]}, {"_id": 0}).sort("date", -1).to_list(50)
    appts = await db.appointments.find({"patient_email": p["email"]}, {"_id": 0}).sort("date", -1).to_list(50)
    return {"patient": p, "profile": prof, "reports": reports, "records": records, "vaccinations": vaccinations, "appointments": appts}

# -------- Reports --------

@api.get("/reports")
async def list_reports(user: dict = Depends(current_user)):
    if user["role"] == "PATIENT":
        query = {"patient_email": user["email"]}
    elif user["role"] == "HOSPITAL":
        hosp = user.get("name", HOSPITAL_NAME_DEFAULT)
        # Match either the report's hospital field OR reports for patients registered at this hospital
        hospital_patients = await db.users.distinct("email", {"role": "PATIENT", "hospital": hosp})
        query = {"$or": [{"hospital": hosp}, {"patient_email": {"$in": hospital_patients}}]}
    else:
        query = {}
    return await db.reports.find(query, {"_id": 0}).sort("uploaded_at", -1).to_list(200)

@api.post("/reports")
async def upload_report(
    file: UploadFile = File(...),
    name: str = Form(...),
    report_type: str = Form("Lab report"),
    provider: str = Form("Uploaded by patient"),
    patient_email: Optional[str] = Form(None),
    user: dict = Depends(current_user),
):
    await require_role(user, ["PATIENT", "DOCTOR"])
    if file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(400, "Only PDF or image files (PNG/JPG/WEBP) are supported")
    body = await file.read()
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File is larger than 8 MB")
    file_id = str(uuid.uuid4())
    ext = Path(file.filename or "").suffix.lower() or (mimetypes.guess_extension(file.content_type) or "")
    stored = UPLOAD_DIR / f"{file_id}{ext}"
    stored.write_bytes(body)
    now = datetime.now(timezone.utc)
    target_email = user["email"] if user["role"] == "PATIENT" else (patient_email or "").lower().strip()
    if user["role"] == "DOCTOR" and not target_email:
        raise HTTPException(400, "patient_email is required when a doctor uploads a report")
    doc = {
        "id": file_id,
        "name": name.strip() or (file.filename or "Untitled report"),
        "type": report_type,
        "provider": provider,
        "patient_email": target_email,
        "uploaded_by": user["name"],
        "uploader_role": user["role"],
        "hospital": user.get("hospital", HOSPITAL_NAME_DEFAULT),
        "status": "Verified" if user["role"] == "DOCTOR" else "Pending review",
        "content_type": file.content_type,
        "size_bytes": len(body),
        "stored_name": stored.name,
        "uploaded_at": now.isoformat(),
        "date": now.strftime("%d %b %Y"),
    }
    await db.reports.insert_one(doc)
    await _notify(doc["patient_email"], "report_uploaded", "New report available",
                  f"{doc['name']} was added by {doc['uploaded_by']}.",
                  {"report_id": file_id})
    return {k: v for k, v in doc.items() if k != "_id"}

@api.get("/reports/{report_id}/file")
async def download_report(report_id: str, user: dict = Depends(current_user)):
    doc = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Report not found")
    if user["role"] == "PATIENT" and doc.get("patient_email") != user["email"]:
        raise HTTPException(403, "You cannot access this report")
    path = UPLOAD_DIR / doc["stored_name"]
    if not path.exists():
        raise HTTPException(404, "Stored file missing")
    return FileResponse(path, media_type=doc.get("content_type", "application/octet-stream"), filename=doc["name"])

# -------- Medical records --------

@api.get("/medical-records")
async def list_records(user: dict = Depends(current_user)):
    if user["role"] == "PATIENT":
        query = {"patient_email": user["email"]}
    elif user["role"] == "DOCTOR":
        query = {"doctor_email": user["email"]}
    else:
        query = {}
    return await db.medical_records.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)

@api.post("/medical-records")
async def create_record(payload: MedicalRecordInput, user: dict = Depends(current_user)):
    await require_role(user, ["DOCTOR"])
    doc = payload.model_dump() | {
        "id": str(uuid.uuid4()),
        "doctor_email": user["email"],
        "doctor_name": user["name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "Verified",
    }
    await db.medical_records.insert_one(doc)
    await _notify(doc["patient_email"], "record_created", "New medical record",
                  f"{user['name']} added a record for you: {doc['diagnosis']}.",
                  {"record_id": doc["id"]})
    return {k: v for k, v in doc.items() if k != "_id"}

# -------- Vaccinations --------

@api.get("/vaccinations")
async def list_vaccinations(user: dict = Depends(current_user)):
    if user["role"] == "PATIENT":
        query = {"patient_email": user["email"]}
    elif user["role"] == "HOSPITAL":
        query = {"provider": user.get("name", HOSPITAL_NAME_DEFAULT)}
    else:
        query = {}
    return await db.vaccinations.find(query, {"_id": 0}).sort("date", -1).to_list(200)

@api.post("/vaccinations")
async def add_vaccination(payload: VaccinationInput, user: dict = Depends(current_user)):
    await require_role(user, ["DOCTOR", "HOSPITAL"])
    doc = payload.model_dump() | {
        "id": str(uuid.uuid4()),
        "provider": user.get("name") if user["role"] == "HOSPITAL" else user.get("hospital", HOSPITAL_NAME_DEFAULT),
        "recorded_by": user["name"],
        "status": "Completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.vaccinations.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}

# -------- Hospital views --------

@api.get("/hospital/doctors")
async def hospital_doctors(user: dict = Depends(current_user)):
    await require_role(user, ["HOSPITAL"])
    hosp = user.get("name", HOSPITAL_NAME_DEFAULT)
    return await db.users.find({"role": "DOCTOR", "hospital": hosp}, {"_id": 0, "password_hash": 0}).to_list(100)

@api.get("/hospital/patients")
async def hospital_patients(user: dict = Depends(current_user)):
    await require_role(user, ["HOSPITAL"])
    hosp = user.get("name", HOSPITAL_NAME_DEFAULT)
    patients = await db.users.find({"role": "PATIENT", "hospital": hosp}, {"_id": 0, "password_hash": 0}).to_list(200)
    out = []
    for p in patients:
        prof = await db.profiles.find_one({"email": p["email"]}, {"_id": 0}) or {}
        appt_count = await db.appointments.count_documents({"patient_email": p["email"], "hospital": hosp})
        out.append({**p, "profile": prof, "appointment_count": appt_count})
    return out

# -------- AI Symptom Specialist --------

@api.post("/ai/symptoms")
async def symptom_stream(payload: SymptomInput, user: dict = Depends(current_user)):
    await require_role(user, ["PATIENT"])
    await db.ai_messages.insert_one({"session_id": payload.session_id, "email": user["email"], "role": "user", "text": payload.message, "created_at": datetime.now(timezone.utc).isoformat()})
    FALLBACK_TEXT = (
        "I can share general educational information, but I cannot diagnose symptoms. "
        "For safety, note when this started, how severe it feels, and any fever or breathing changes. "
        "Please contact a qualified clinician if symptoms are concerning or worsening."
    )
    async def generate():
        if _openai_available and OPENAI_API_KEY:
            try:
                system = (
                    "You are Smart Health ID's careful educational symptom assistant. "
                    "Never diagnose. Give concise possible general explanations, safe next steps, "
                    "and urgency level. Always say this is educational and not medical diagnosis. "
                    "Encourage professional care for worsening symptoms."
                )
                client_ai = _AsyncOpenAI(api_key=OPENAI_API_KEY)
                collected = ""
                stream = await client_ai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": payload.message},
                    ],
                    stream=True,
                    max_tokens=500,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        collected += delta
                        yield "data: " + json.dumps({"text": delta}) + "\n\n"
                await db.ai_messages.insert_one({"session_id": payload.session_id, "email": user["email"], "role": "assistant", "text": collected, "created_at": datetime.now(timezone.utc).isoformat()})
                yield "data: [DONE]\n\n"
                return
            except Exception:
                logger.exception("AI stream failed, using fallback")
        # Fallback — no AI key or AI unavailable
        await db.ai_messages.insert_one({"session_id": payload.session_id, "email": user["email"], "role": "assistant", "text": FALLBACK_TEXT, "created_at": datetime.now(timezone.utc).isoformat()})
        yield "data: " + json.dumps({"text": FALLBACK_TEXT, "fallback": True}) + "\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

class SuggestInput(BaseModel):
    symptoms: str

def _classify_specialty(text: str) -> str:
    t = text.lower()
    scores = {sp: sum(1 for kw in kws if kw in t) for sp, kws in SPECIALTY_KEYWORDS.items()}
    top = max(scores, key=scores.get)
    return top if scores[top] > 0 else "General Medicine"

@api.post("/ai/suggest-specialist")
async def suggest_specialist(payload: SuggestInput, user: dict = Depends(current_user)):
    await require_role(user, ["PATIENT"])
    specialty = _classify_specialty(payload.symptoms)
    doctors = await db.users.find({"role": "DOCTOR", "specialty": specialty, "on_duty": True}, {"_id": 0, "password_hash": 0}).to_list(20)
    if not doctors:
        # Fall back to any on-duty doctor in that specialty (including off-duty), then to General Medicine
        doctors = await db.users.find({"role": "DOCTOR", "specialty": specialty}, {"_id": 0, "password_hash": 0}).to_list(20)
    if not doctors and specialty != "General Medicine":
        doctors = await db.users.find({"role": "DOCTOR", "specialty": "General Medicine"}, {"_id": 0, "password_hash": 0}).to_list(20)
        specialty = "General Medicine"
    return {"specialty": specialty, "doctors": doctors[:4]}

# -------- Reminders --------

def _reminder_html(apt: dict) -> str:
    name = apt.get("patient_name", "there").split(" ")[0]
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,Helvetica,sans-serif;background:#f4f8fb;padding:24px">
      <tr><td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:14px;overflow:hidden">
          <tr><td style="background:#0f4078;color:#ffffff;padding:22px 28px">
            <div style="font-size:13px;letter-spacing:2px;opacity:.75">SMART HEALTH ID</div>
            <div style="font-size:22px;font-weight:700;margin-top:6px">Appointment tomorrow</div>
          </td></tr>
          <tr><td style="padding:28px">
            <p style="margin:0 0 14px;color:#334155;font-size:16px">Hi {name},</p>
            <p style="margin:0 0 18px;color:#475569;font-size:15px;line-height:1.55">Friendly reminder about your upcoming visit. Please arrive 10 minutes early with any recent reports.</p>
            <table width="100%" cellpadding="10" cellspacing="0" style="background:#f1f5f9;border-radius:10px;color:#0f172a;font-size:14px">
              <tr><td><b>Doctor</b></td><td>{apt.get('doctor_name','')}</td></tr>
              <tr><td><b>Specialty</b></td><td>{apt.get('domain','')}</td></tr>
              <tr><td><b>Hospital</b></td><td>{apt.get('hospital','')}</td></tr>
              <tr><td><b>Date</b></td><td>{apt.get('date','')}</td></tr>
              <tr><td><b>Time</b></td><td>{apt.get('time','')}</td></tr>
              <tr><td><b>Reason</b></td><td>{apt.get('reason','')}</td></tr>
            </table>
          </td></tr>
          <tr><td style="padding:16px 28px;background:#f8fafc;color:#94a3b8;font-size:12px" align="center">© Smart Health ID · Trusted care, connected</td></tr>
        </table>
      </td></tr>
    </table>
    """

async def _send_reminder_email(apt: dict) -> bool:
    subject = f"Reminder: {apt.get('doctor_name','your visit')} on {apt.get('date','')}"
    html = _reminder_html(apt)
    to_email = apt.get("patient_email")
    if not RESEND_API_KEY:
        logger.info("[reminder-skip] Resend key not configured. Would email %s: %s", to_email, subject)
        return False
    try:
        params = {"from": SENDER_EMAIL, "to": [to_email], "subject": subject, "html": html}
        await asyncio.to_thread(resend.Emails.send, params)
        logger.info("[reminder-sent] appointment=%s to=%s", apt.get("id"), to_email)
        return True
    except Exception as exc:
        logger.exception("[reminder-error] %s", exc)
        return False

def _parse_appointment_dt(apt: dict) -> Optional[datetime]:
    date_str = apt.get("date")
    if not date_str:
        return None
    try:
        base = datetime.fromisoformat(date_str)
    except ValueError:
        return None
    time_str = (apt.get("time") or "").strip()
    hour, minute = 9, 0
    if time_str:
        try:
            parsed = datetime.strptime(time_str.upper().replace(".", ""), "%I:%M %p")
            hour, minute = parsed.hour, parsed.minute
        except ValueError:
            try:
                parsed = datetime.strptime(time_str, "%H:%M")
                hour, minute = parsed.hour, parsed.minute
            except ValueError:
                pass
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=timezone.utc)

async def reminder_loop():
    while True:
        try:
            now = datetime.now(timezone.utc)
            candidates = await db.appointments.find({"status": "Upcoming", "reminder_sent": {"$ne": True}}, {"_id": 0}).to_list(500)
            for apt in candidates:
                try:
                    apt_dt = _parse_appointment_dt(apt)
                    if not apt_dt:
                        continue
                    delta_hours = (apt_dt - now).total_seconds() / 3600.0
                    if 20.0 <= delta_hours <= 28.0:
                        ok = await _send_reminder_email(apt)
                        await db.appointments.update_one(
                            {"id": apt["id"]},
                            {"$set": {"reminder_sent": True, "reminder_sent_at": now.isoformat(), "reminder_delivered": ok}},
                        )
                        await _notify(apt["patient_email"], "reminder_sent", "Appointment reminder",
                                      f"Your {apt.get('date','')} visit with {apt.get('doctor_name','')} is tomorrow at {apt.get('time','')}.",
                                      {"appointment_id": apt["id"]})
                except Exception:
                    logger.exception("Reminder scan failed for one appointment")
        except Exception:
            logger.exception("Reminder loop iteration failed")
        await asyncio.sleep(300)

# -------- Notifications --------

@api.get("/notifications")
async def list_notifications(user: dict = Depends(current_user)):
    items = await db.notifications.find({"email": user["email"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"items": items, "unread": sum(1 for i in items if not i.get("read"))}

@api.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user: dict = Depends(current_user)):
    result = await db.notifications.update_one({"id": notification_id, "email": user["email"]}, {"$set": {"read": True}})
    if not result.matched_count:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}

@api.post("/notifications/mark-all-read")
async def mark_all_read(user: dict = Depends(current_user)):
    result = await db.notifications.update_many({"email": user["email"], "read": False}, {"$set": {"read": True}})
    return {"ok": True, "updated": result.modified_count}

@api.delete("/notifications/{notification_id}")
async def delete_notification(notification_id: str, user: dict = Depends(current_user)):
    result = await db.notifications.delete_one({"id": notification_id, "email": user["email"]})
    if not result.deleted_count:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}

# -------- Seed --------

async def seed():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("patient_id")
    await db.users.create_index("doctor_id")

    demo_doctors = [
        {"email": "doctor@example.com", "name": "Dr. Ananya Rao", "role": "DOCTOR", "doctor_id": "DOC-2048", "specialty": "Cardiology", "hospital": HOSPITAL_NAME_DEFAULT, "fee": 1200, "experience": "14 yrs", "rating": 4.9, "on_duty": True},
        {"email": "rahul.mehta@example.com", "name": "Dr. Rahul Mehta", "role": "DOCTOR", "doctor_id": "DOC-1190", "specialty": "General Medicine", "hospital": HOSPITAL_NAME_DEFAULT, "fee": 800, "experience": "10 yrs", "rating": 4.8, "on_duty": True},
        {"email": "priya.nair@example.com", "name": "Dr. Priya Nair", "role": "DOCTOR", "doctor_id": "DOC-8821", "specialty": "Dermatology", "hospital": HOSPITAL_NAME_DEFAULT, "fee": 1000, "experience": "8 yrs", "rating": 4.9, "on_duty": False},
        {"email": "vikram.singh@example.com", "name": "Dr. Vikram Singh", "role": "DOCTOR", "doctor_id": "DOC-4472", "specialty": "Orthopedics", "hospital": HOSPITAL_NAME_DEFAULT, "fee": 1400, "experience": "16 yrs", "rating": 4.7, "on_duty": True},
        {"email": "karan.reddy@example.com", "name": "Dr. Karan Reddy", "role": "DOCTOR", "doctor_id": "DOC-6003", "specialty": "Pediatrics", "hospital": HOSPITAL_NAME_DEFAULT, "fee": 900, "experience": "6 yrs", "rating": 4.6, "on_duty": True},
        {"email": "sneha.iyer@example.com", "name": "Dr. Sneha Iyer", "role": "DOCTOR", "doctor_id": "DOC-5711", "specialty": "Neurology", "hospital": HOSPITAL_NAME_DEFAULT, "fee": 1500, "experience": "12 yrs", "rating": 4.8, "on_duty": False},
    ]

    demo_patients = [
        {"email": "patient@example.com", "name": "Aarav Sharma", "role": "PATIENT", "patient_id": "SHID-10001", "hospital": HOSPITAL_NAME_DEFAULT},
        {"email": "riya@example.com", "name": "Riya Kapoor", "role": "PATIENT", "patient_id": "SHID-10002", "hospital": HOSPITAL_NAME_DEFAULT},
        {"email": "karthik@example.com", "name": "Karthik Iyer", "role": "PATIENT", "patient_id": "SHID-10003", "hospital": HOSPITAL_NAME_DEFAULT},
        {"email": "simran@example.com", "name": "Simran Kaur", "role": "PATIENT", "patient_id": "SHID-10004", "hospital": HOSPITAL_NAME_DEFAULT},
        {"email": "arjun@example.com", "name": "Arjun Verma", "role": "PATIENT", "patient_id": "SHID-10005", "hospital": HOSPITAL_NAME_DEFAULT},
    ]

    demo_hospitals = [
        {"email": "hospital@example.com", "name": HOSPITAL_NAME_DEFAULT, "role": "HOSPITAL", "hospital_id": "HSP-301"},
    ]

    for item in demo_doctors + demo_patients + demo_hospitals:
        user = await db.users.find_one({"email": item["email"]})
        if not user:
            await db.users.insert_one({**item, "password_hash": hash_password(DEMO_PASSWORD), "created_at": datetime.now(timezone.utc).isoformat()})
        else:
            # Backfill new schema fields on existing demo accounts without touching password_hash
            patch = {k: v for k, v in item.items() if k != "email"}
            await db.users.update_one({"email": item["email"]}, {"$set": patch})

    # Seed profiles for demo patients
    demo_profiles = {
        "patient@example.com": {"phone": "+91 98765 43210", "occupation": "Product Designer", "marital": "Single", "address": "Bengaluru, Karnataka", "height": "178 cm", "weight": "72 kg", "emergency": "Meera Sharma · +91 98111 22334", "dob": "12 Aug 1996", "gender": "Male", "blood": "O+"},
        "riya@example.com": {"phone": "+91 90000 11122", "occupation": "Software Engineer", "marital": "Single", "address": "Bengaluru, Karnataka", "height": "165 cm", "weight": "56 kg", "emergency": "Ritu Kapoor · +91 90000 22233", "dob": "04 Jun 1998", "gender": "Female", "blood": "A+"},
        "karthik@example.com": {"phone": "+91 88888 12345", "occupation": "Teacher", "marital": "Married", "address": "Chennai, Tamil Nadu", "height": "172 cm", "weight": "78 kg", "emergency": "Meena Iyer · +91 88888 54321", "dob": "17 Feb 1985", "gender": "Male", "blood": "B+"},
        "simran@example.com": {"phone": "+91 77777 12312", "occupation": "Architect", "marital": "Single", "address": "Delhi", "height": "168 cm", "weight": "60 kg", "emergency": "Harpreet Kaur · +91 77777 21213", "dob": "22 Nov 1992", "gender": "Female", "blood": "O-"},
        "arjun@example.com": {"phone": "+91 66666 99991", "occupation": "Chef", "marital": "Single", "address": "Mumbai, Maharashtra", "height": "175 cm", "weight": "70 kg", "emergency": "Neha Verma · +91 66666 88881", "dob": "09 May 1990", "gender": "Male", "blood": "AB+"},
    }
    for email, data in demo_profiles.items():
        existing = await db.profiles.find_one({"email": email})
        if not existing:
            await db.profiles.insert_one({"email": email, "name": next((p["name"] for p in demo_patients if p["email"] == email), ""), **data, "patient_id": next((p["patient_id"] for p in demo_patients if p["email"] == email), "")})

    if await db.appointments.count_documents({}) == 0:
        base_appts = [
            {"id": "apt-001", "patient_email": "patient@example.com", "patient_name": "Aarav Sharma", "doctor_id": "DOC-2048", "doctor_name": "Dr. Ananya Rao", "domain": "Cardiology", "hospital": HOSPITAL_NAME_DEFAULT, "date": "2026-04-14", "time": "10:30 AM", "reason": "Routine follow-up", "fee": 1200, "status": "Upcoming", "reminder_sent": False},
            {"id": "apt-002", "patient_email": "patient@example.com", "patient_name": "Aarav Sharma", "doctor_id": "DOC-1190", "doctor_name": "Dr. Rahul Mehta", "domain": "General Medicine", "hospital": HOSPITAL_NAME_DEFAULT, "date": "2026-04-22", "time": "04:00 PM", "reason": "Annual health review", "fee": 800, "status": "Upcoming", "reminder_sent": False},
            {"id": "apt-003", "patient_email": "riya@example.com", "patient_name": "Riya Kapoor", "doctor_id": "DOC-2048", "doctor_name": "Dr. Ananya Rao", "domain": "Cardiology", "hospital": HOSPITAL_NAME_DEFAULT, "date": "2026-04-16", "time": "11:00 AM", "reason": "Palpitations", "fee": 1200, "status": "Upcoming", "reminder_sent": False},
            {"id": "apt-004", "patient_email": "karthik@example.com", "patient_name": "Karthik Iyer", "doctor_id": "DOC-2048", "doctor_name": "Dr. Ananya Rao", "domain": "Cardiology", "hospital": HOSPITAL_NAME_DEFAULT, "date": "2026-03-04", "time": "09:00 AM", "reason": "Chest tightness review", "fee": 1200, "status": "Attended", "reminder_sent": True},
            {"id": "apt-005", "patient_email": "simran@example.com", "patient_name": "Simran Kaur", "doctor_id": "DOC-4472", "doctor_name": "Dr. Vikram Singh", "domain": "Orthopedics", "hospital": HOSPITAL_NAME_DEFAULT, "date": "2026-03-19", "time": "02:30 PM", "reason": "Knee pain", "fee": 1400, "status": "Completed", "reminder_sent": True},
            {"id": "apt-006", "patient_email": "arjun@example.com", "patient_name": "Arjun Verma", "doctor_id": "DOC-1190", "doctor_name": "Dr. Rahul Mehta", "domain": "General Medicine", "hospital": HOSPITAL_NAME_DEFAULT, "date": "2026-04-20", "time": "05:30 PM", "reason": "Persistent fatigue", "fee": 800, "status": "Upcoming", "reminder_sent": False},
        ]
        await db.appointments.insert_many(base_appts)

    if await db.vaccinations.count_documents({}) == 0:
        await db.vaccinations.insert_many([
            {"id": str(uuid.uuid4()), "patient_email": "patient@example.com", "patient_name": "Aarav Sharma", "vaccine": "Influenza", "dose": "Annual dose", "date": "2026-01-04", "next_due": "2027-01-04", "provider": HOSPITAL_NAME_DEFAULT, "status": "Completed", "recorded_by": "Dr. Ananya Rao"},
            {"id": str(uuid.uuid4()), "patient_email": "patient@example.com", "patient_name": "Aarav Sharma", "vaccine": "COVID-19", "dose": "Booster dose", "date": "2025-10-14", "next_due": None, "provider": HOSPITAL_NAME_DEFAULT, "status": "Completed", "recorded_by": "Dr. Rahul Mehta"},
            {"id": str(uuid.uuid4()), "patient_email": "riya@example.com", "patient_name": "Riya Kapoor", "vaccine": "HPV", "dose": "Second dose", "date": "2026-02-11", "next_due": "2026-08-11", "provider": HOSPITAL_NAME_DEFAULT, "status": "Completed", "recorded_by": "Dr. Priya Nair"},
            {"id": str(uuid.uuid4()), "patient_email": "arjun@example.com", "patient_name": "Arjun Verma", "vaccine": "Hepatitis B", "dose": "Booster", "date": "2026-01-24", "next_due": "2031-01-24", "provider": HOSPITAL_NAME_DEFAULT, "status": "Completed", "recorded_by": "Dr. Rahul Mehta"},
            {"id": str(uuid.uuid4()), "patient_email": "karthik@example.com", "patient_name": "Karthik Iyer", "vaccine": "Typhoid", "dose": "Single dose", "date": "2026-02-05", "next_due": "2029-02-05", "provider": HOSPITAL_NAME_DEFAULT, "status": "Completed", "recorded_by": "Dr. Rahul Mehta"},
        ])

    if await db.medical_records.count_documents({}) == 0:
        await db.medical_records.insert_many([
            {"id": str(uuid.uuid4()), "patient_email": "karthik@example.com", "patient_name": "Karthik Iyer", "doctor_email": "doctor@example.com", "doctor_name": "Dr. Ananya Rao", "diagnosis": "Stable angina", "symptoms": "Chest tightness on exertion", "notes": "Advised stress test.", "treatment": "Lifestyle changes", "prescription": "Aspirin 75mg", "follow_up": "2026-06-04", "status": "Verified", "created_at": "2026-03-04T09:30:00+00:00"},
            {"id": str(uuid.uuid4()), "patient_email": "simran@example.com", "patient_name": "Simran Kaur", "doctor_email": "vikram.singh@example.com", "doctor_name": "Dr. Vikram Singh", "diagnosis": "Meniscus strain", "symptoms": "Knee pain", "notes": "Physiotherapy referral.", "treatment": "Ice + NSAID", "prescription": "Ibuprofen 400mg", "follow_up": "2026-04-19", "status": "Verified", "created_at": "2026-03-19T15:00:00+00:00"},
        ])

    if await db.reports.count_documents({"hospital": HOSPITAL_NAME_DEFAULT}) == 0:
        seed_reports = [
            {"patient_email": "patient@example.com", "patient_name": "Aarav Sharma", "name": "Complete Blood Count", "type": "Lab report", "date": "02 Feb 2026"},
            {"patient_email": "karthik@example.com", "patient_name": "Karthik Iyer", "name": "Stress test report", "type": "Imaging", "date": "05 Mar 2026"},
            {"patient_email": "riya@example.com", "patient_name": "Riya Kapoor", "name": "Dermatology biopsy", "type": "Lab report", "date": "12 Feb 2026"},
            {"patient_email": "simran@example.com", "patient_name": "Simran Kaur", "name": "Knee X-ray", "type": "Imaging", "date": "19 Mar 2026"},
        ]
        for r in seed_reports:
            file_id = str(uuid.uuid4())
            stored = UPLOAD_DIR / f"{file_id}.pdf"
            stored.write_bytes(b"%PDF-1.4\n% Smart Health ID demo report\n%%EOF")
            await db.reports.insert_one({
                "id": file_id,
                "name": r["name"],
                "type": r["type"],
                "provider": HOSPITAL_NAME_DEFAULT,
                "patient_email": r["patient_email"],
                "uploaded_by": "CityCare Diagnostics",
                "uploader_role": "HOSPITAL",
                "hospital": HOSPITAL_NAME_DEFAULT,
                "status": "Verified",
                "content_type": "application/pdf",
                "size_bytes": stored.stat().st_size,
                "stored_name": stored.name,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "date": r["date"],
            })

app.include_router(api)

# Build CORS origins list from FRONTEND_URL env var.
# In production: set FRONTEND_URL=https://your-frontend.vercel.app
# Multiple origins can be comma-separated: FRONTEND_URL=https://app.example.com,https://www.example.com
_cors_origins: list[str] = []
if FRONTEND_URL:
    _cors_origins = [u.strip() for u in FRONTEND_URL.split(",") if u.strip()]

if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Development fallback — allow everything (no credentials via cookies, token-in-header still works)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.on_event("startup")
async def startup():
    await seed()
    asyncio.create_task(reminder_loop())

@app.on_event("shutdown")
async def shutdown():
    client.close()
