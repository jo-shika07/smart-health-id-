# Smart Health ID — PRD

## Original problem
Modern, responsive healthcare app for Patients, Doctors, Hospitals with role-based dashboards, appointments, records, verification, and AI symptom support.

## Users
- Patient — own records/appointments/health ID, AI specialist
- Doctor — patients attended, appointments (attend / reschedule), medical records with attachments, duty toggle
- Hospital — network view (doctors, patients, appointments, vaccinations, reports), verification

## Tech stack
- Frontend: React (CRA), Tailwind, sonner, lucide-react, qrcode.react
- Backend: FastAPI + Motor (MongoDB), JWT cookie + Bearer, Resend for reminders + reset codes, Emergent LLM (OpenAI GPT-5.4)
- Storage: Local disk `/app/backend/uploads`

## Implemented (Feb 2026 — iteration 5)
- Real email/password auth for all 3 roles + self registration
- Forgot password with one-time reset token (returned on-screen in demo, emailed when RESEND_API_KEY set)
- QR-code Health ID (`qrcode.react`)
- Reports upload / download (PDF/PNG/JPG/WEBP up to 8 MB) served via `/api/reports/{id}/file`
- Doctor duty toggle (on/off), off-duty disables new bookings in the UI + server-side check
- Doctor Patients view (attended so far) + full patient detail dialog (reports/vaccinations/records/appointments)
- Doctor Appointments with Reschedule / Mark Attended / Not attended, JSON body PATCH
- Doctor Medical Records with optional attached PDF/image (report_id linkage)
- AI Symptom Specialist streams response and suggests a matching Specialty + on-duty doctors
- Hospital views: Doctors (with duty pill), Patients (with detail dialog), Appointments, Vaccinations, Reports
- Appointment reminder loop parses `date + time`, sends via Resend if key configured
- Ownership matrix enforced on appointment mutations

## Backlog / next
- P1 Server-side canonical booking (derive doctor_name/specialty/hospital/fee from doctor_id)
- P1 Restrict appointment status enum (Upcoming/Attended/Not attended/Cancelled/Completed)
- P2 Shared calendar component (replace native date inputs)
- P2 Notifications backed by DB events (appointment/report/record)
- P2 Split App.js into pages/components (monolith)
- P2 Production hardening: cookie Secure, CORS explicit origins, brute-force lockout
