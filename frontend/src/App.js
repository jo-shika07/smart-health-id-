import { useEffect, useState, useCallback } from "react";
import { BrowserRouter, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Activity, AlertCircle, ArrowRight, Bell, CalendarDays, Check, ChevronRight, ClipboardList, Clock3, Download, FileCheck2, FileText, HeartPulse, Home, LogOut, MailCheck, Menu, Paperclip, Plus, Search, Settings, ShieldCheck, Sparkles, Stethoscope, Syringe, ToggleLeft, ToggleRight, Upload, UserRound, Users, X } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { format, parseISO } from "date-fns";
import { Popover, PopoverContent, PopoverTrigger } from "./components/ui/popover";
import { Calendar } from "./components/ui/calendar";
import "@/App.css";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://smart-health-id.onrender.com";
const API = `${BACKEND_URL}/api`;
const demoUsers = {
  PATIENT: { email: "patient@example.com", name: "Aarav Sharma", label: "Patient" },
  DOCTOR: { email: "doctor@example.com", name: "Dr. Ananya Rao", label: "Doctor" },
  HOSPITAL: { email: "hospital@example.com", name: "CityCare Hospital", label: "Hospital" },
};
const SPECIALTIES = ["Cardiology", "General Medicine", "Dermatology", "Orthopedics", "Pediatrics", "Neurology"];

const navByRole = {
  PATIENT: [
    ["Dashboard", "/patient/dashboard", Home],
    ["My Health ID", "/patient/health-id", ShieldCheck],
    ["Health records", "/patient/records", ClipboardList],
    ["Reports", "/patient/reports", FileText],
    ["Vaccinations", "/patient/vaccinations", Syringe],
    ["Appointments", "/patient/appointments", CalendarDays],
    ["Doctors", "/patient/doctors", Stethoscope],
    ["AI specialist", "/patient/ai-specialist", Sparkles],
    ["Notifications", "/patient/notifications", Bell],
  ],
  DOCTOR: [
    ["Dashboard", "/doctor/dashboard", Home],
    ["Patients", "/doctor/patients", Users],
    ["Appointments", "/doctor/appointments", CalendarDays],
    ["Medical records", "/doctor/records", ClipboardList],
  ],
  HOSPITAL: [
    ["Dashboard", "/hospital/dashboard", Home],
    ["Doctors", "/hospital/doctors", Stethoscope],
    ["Patients", "/hospital/patients", Users],
    ["Appointments", "/hospital/appointments", CalendarDays],
    ["Vaccinations", "/hospital/vaccinations", Syringe],
    ["Reports", "/hospital/reports", FileText],
    ["Verification", "/hospital/verification", ShieldCheck],
  ],
};

const apiCall = (method, url, data, token) => axios({ method, url: `${API}${url}`, data, headers: token ? { Authorization: `Bearer ${token}` } : {} });

// Shadcn calendar wrapper — YYYY-MM-DD string I/O to keep backend integration unchanged
function DatePickerField({ label, value, onChange, testId, wide }) {
  const [open, setOpen] = useState(false);
  const parsed = value ? (() => { try { return parseISO(value); } catch { return null; } })() : null;
  const display = parsed && !isNaN(parsed) ? format(parsed, "PPP") : "Pick a date";
  return <label className={wide ? "wide" : ""}>{label}
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" data-testid={testId} className="date-picker-trigger">
          <CalendarDays size={15} />
          <span className={parsed ? "" : "muted"}>{display}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="date-picker-content" align="start">
        <Calendar
          mode="single"
          selected={parsed || undefined}
          onSelect={(d) => { if (d) { onChange(format(d, "yyyy-MM-dd")); setOpen(false); } }}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  </label>;
}

// ================================================================================
// Login + Register + Forgot password
// ================================================================================

function Login({ onLogin }) {
  const [role, setRole] = useState("PATIENT");
  const [email, setEmail] = useState(demoUsers.PATIENT.email);
  const [password, setPassword] = useState("Demo@123");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState(null); // null | 'register' | 'forgot'

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true); setError("");
    try {
      const { data } = await apiCall("post", "/auth/login", { email, password });
      localStorage.setItem("shid_token", data.token);
      onLogin(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Unable to sign in.");
    } finally { setLoading(false); }
  };
  const quick = async (nextRole) => {
    const demo = demoUsers[nextRole];
    setRole(nextRole); setEmail(demo.email); setPassword("Demo@123"); setLoading(true);
    try {
      const { data } = await apiCall("post", "/auth/login", { email: demo.email, password: "Demo@123" });
      localStorage.setItem("shid_token", data.token);
      onLogin(data);
    } catch { setError("Demo sign-in is temporarily unavailable."); }
    finally { setLoading(false); }
  };

  return <main className="login-page">
    <section className="login-visual">
      <div className="brand lock-brand"><div className="brand-mark"><HeartPulse size={22} /></div><div><strong>Smart Health ID</strong><span>Trusted care, connected</span></div></div>
      <div className="visual-copy">
        <div className="eyebrow"><span className="live-dot" /> HEALTH DATA, VERIFIED</div>
        <h1>Your health story,<br /><em>always within reach.</em></h1>
        <p>One secure place for your records, care team, and the decisions that keep you well.</p>
      </div>
      <div className="security-note"><ShieldCheck size={17} /><span>Built around your privacy and consent</span></div>
    </section>
    <section className="login-panel">
      <div className="login-form-wrap">
        <div className="mobile-brand"><div className="brand-mark"><HeartPulse size={20} /></div><strong>Smart Health ID</strong></div>
        <div className="form-heading">
          <p className="eyebrow">WELCOME BACK</p>
          <h2>Care starts with<br /><span>knowing your health.</span></h2>
          <p>Sign in to access your connected care experience.</p>
        </div>
        <div className="role-tabs" role="tablist">
          {Object.entries(demoUsers).map(([key, item]) => (
            <button data-testid={`login-role-${key.toLowerCase()}`} key={key} className={role === key ? "active" : ""} onClick={() => { setRole(key); setEmail(item.email); }} role="tab">
              {key === "PATIENT" ? <UserRound size={16} /> : key === "DOCTOR" ? <Stethoscope size={16} /> : <Activity size={16} />}
              {item.label}
            </button>
          ))}
        </div>
        <form onSubmit={submit}>
          <label>Email or Health ID
            <input data-testid="login-email-input" value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="email" required />
          </label>
          <label>Password
            <div className="password-field">
              <input data-testid="login-password-input" value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" required />
              <button type="button" data-testid="login-forgot-button" className="field-action" onClick={() => setMode("forgot")}>Forgot?</button>
            </div>
          </label>
          <div className="form-meta">
            <label className="check-label"><input data-testid="login-remember-checkbox" type="checkbox" defaultChecked /> <span>Remember me</span></label>
            <span className="secure-label"><ShieldCheck size={14} /> Secure sign in</span>
          </div>
          {error && <div className="form-error" data-testid="login-error"><AlertCircle size={16} />{error}</div>}
          <button data-testid="login-submit-button" className="primary-button full" disabled={loading}>{loading ? "Signing you in…" : "Sign in"}<ArrowRight size={17} /></button>
        </form>
        <div className="demo-divider"><span>QUICK DEMO ACCESS</span></div>
        <div className="quick-access">
          {Object.entries(demoUsers).map(([key, item]) => (
            <button data-testid={`quick-login-${key.toLowerCase()}`} key={key} onClick={() => quick(key)}>
              <span className={`mini-avatar ${key.toLowerCase()}`}>{item.name.split(" ").map((n) => n[0]).slice(0, 2).join("")}</span>
              <span><b>{item.label}</b><small>{item.email}</small></span>
              <ChevronRight size={16} />
            </button>
          ))}
        </div>
        <div className="login-footer">
          <span>New to Smart Health ID?</span>
          <button data-testid="create-account-button" onClick={() => setMode("register")}>Create an account</button>
        </div>
      </div>
      <footer className="legal">
        <span>© 2026 Smart Health ID</span>
        <span>
          <button data-testid="privacy-link" onClick={() => toast.info("Your health data is always treated as private.")}>Privacy</button>
          <button data-testid="support-link" onClick={() => toast.info("Support: care@smarthealthid.demo")}>Help & support</button>
        </span>
      </footer>
    </section>
    {mode === "register" && <RegisterDialog onClose={() => setMode(null)} onSuccess={(u) => { localStorage.setItem("shid_token", u.token); onLogin(u); }} />}
    {mode === "forgot" && <ForgotDialog onClose={() => setMode(null)} />}
  </main>;
}

function RegisterDialog({ onClose, onSuccess }) {
  const [form, setForm] = useState({
    name: "", email: "", password: "", role: "PATIENT",
    specialty: "General Medicine", hospital: "CityCare Hospital",
    dob: "", gender: "Male", blood: "O+", phone: "", address: "",
    occupation: "", marital: "Single", height: "", weight: "", emergency: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const payload = { ...form, email: form.email.trim().toLowerCase() };
      const { data } = await apiCall("post", "/auth/register", payload);
      toast.success("Account created — welcome to Smart Health ID");
      onSuccess(data);
    } catch (e) {
      setErr(e.response?.data?.detail || "Could not create your account");
    } finally { setBusy(false); }
  };
  const isPatient = form.role === "PATIENT";
  return <div className="modal-backdrop" role="dialog" aria-modal="true">
    <div className="booking-modal wide-modal">
      <div className="modal-heading">
        <div><p className="eyebrow">JOIN SMART HEALTH ID</p><h2>Create your account</h2><span>Choose a role — patients can share detailed health info now for faster care later.</span></div>
        <button data-testid="register-close-button" className="icon-button" onClick={onClose}><X size={18} /></button>
      </div>
      <form onSubmit={submit} className="booking-form">
        <label className="wide">I am a
          <div className="role-tabs" style={{ marginTop: 8 }}>
            {["PATIENT", "DOCTOR", "HOSPITAL"].map((r) => (
              <button type="button" key={r} data-testid={`register-role-${r.toLowerCase()}`} className={form.role === r ? "active" : ""} onClick={() => setForm({ ...form, role: r })}>{r === "PATIENT" ? <UserRound size={14} /> : r === "DOCTOR" ? <Stethoscope size={14} /> : <Activity size={14} />}{r === "PATIENT" ? "Patient" : r === "DOCTOR" ? "Doctor" : "Hospital"}</button>
            ))}
          </div>
        </label>
        <label>Full name<input data-testid="register-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label>
        <label>Email<input data-testid="register-email-input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label>
        <label>Password<input data-testid="register-password-input" type="password" minLength={6} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required /></label>
        {form.role === "DOCTOR" && <label>Specialty<select data-testid="register-specialty-select" value={form.specialty} onChange={(e) => setForm({ ...form, specialty: e.target.value })}>{SPECIALTIES.map((s) => <option key={s}>{s}</option>)}</select></label>}
        {form.role !== "HOSPITAL" && <label>Hospital<input data-testid="register-hospital-input" value={form.hospital} onChange={(e) => setForm({ ...form, hospital: e.target.value })} /></label>}
        {isPatient && <>
          <div className="wide section-divider"><span>PERSONAL DETAILS</span></div>
          <DatePickerField testId="register-dob-input" label="Date of birth" value={form.dob} onChange={(v) => setForm({ ...form, dob: v })} />
          <label>Gender<select data-testid="register-gender-select" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}><option>Male</option><option>Female</option><option>Other</option><option>Prefer not to say</option></select></label>
          <label>Blood group<select data-testid="register-blood-select" value={form.blood} onChange={(e) => setForm({ ...form, blood: e.target.value })}>{["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"].map(b => <option key={b}>{b}</option>)}</select></label>
          <label>Phone<input data-testid="register-phone-input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+91 98765 43210" /></label>
          <label className="wide">Address<input data-testid="register-address-input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} placeholder="City, State" /></label>
          <label>Height<input data-testid="register-height-input" value={form.height} onChange={(e) => setForm({ ...form, height: e.target.value })} placeholder="178 cm" /></label>
          <label>Weight<input data-testid="register-weight-input" value={form.weight} onChange={(e) => setForm({ ...form, weight: e.target.value })} placeholder="72 kg" /></label>
          <label>Occupation<input data-testid="register-occupation-input" value={form.occupation} onChange={(e) => setForm({ ...form, occupation: e.target.value })} placeholder="e.g. Software Engineer" /></label>
          <label>Marital status<select data-testid="register-marital-select" value={form.marital} onChange={(e) => setForm({ ...form, marital: e.target.value })}><option>Single</option><option>Married</option><option>Divorced</option><option>Widowed</option><option>Prefer not to say</option></select></label>
          <label className="wide">Emergency contact<input data-testid="register-emergency-input" value={form.emergency} onChange={(e) => setForm({ ...form, emergency: e.target.value })} placeholder="Name · +91 XXXXX" /></label>
        </>}
        {err && <div className="form-error wide" data-testid="register-error"><AlertCircle size={16} />{err}</div>}
        <div className="modal-actions">
          <button data-testid="register-cancel-button" type="button" className="outline-button" onClick={onClose}>Cancel</button>
          <button data-testid="register-submit-button" className="primary-button" disabled={busy}>{busy ? "Creating…" : "Create account"} <ArrowRight size={16} /></button>
        </div>
      </form>
    </div>
  </div>;
}

function ForgotDialog({ onClose }) {
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [demoToken, setDemoToken] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const request = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const { data } = await apiCall("post", "/auth/forgot-password", { email: email.trim().toLowerCase() });
      setDemoToken(data.demo_token);
      setStep(2);
      toast.success(data.demo_token ? "Reset code generated" : "If this email is registered, a code has been sent");
    } catch (e) {
      setErr(e.response?.data?.detail || "Could not start password reset");
    } finally { setBusy(false); }
  };
  const reset = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await apiCall("post", "/auth/reset-password", { token: token.trim(), password });
      toast.success("Password updated — sign in with your new password");
      onClose();
    } catch (e) {
      setErr(e.response?.data?.detail || "Reset failed");
    } finally { setBusy(false); }
  };
  return <div className="modal-backdrop" role="dialog" aria-modal="true">
    <div className="booking-modal">
      <div className="modal-heading">
        <div><p className="eyebrow">ACCOUNT RECOVERY</p><h2>{step === 1 ? "Reset your password" : "Enter your reset code"}</h2><span>{step === 1 ? "We'll generate a one-time code for you." : "Codes expire after 30 minutes."}</span></div>
        <button data-testid="forgot-close-button" className="icon-button" onClick={onClose}><X size={18} /></button>
      </div>
      {step === 1 ? (
        <form onSubmit={request} className="booking-form">
          <label className="wide">Email<input data-testid="forgot-email-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          {err && <div className="form-error wide"><AlertCircle size={16} />{err}</div>}
          <div className="modal-actions">
            <button type="button" className="outline-button" onClick={onClose}>Cancel</button>
            <button data-testid="forgot-request-button" className="primary-button" disabled={busy}>{busy ? "Sending…" : "Send code"}</button>
          </div>
        </form>
      ) : (
        <form onSubmit={reset} className="booking-form">
          {demoToken && <div className="wide demo-token" data-testid="forgot-demo-token"><b>Demo reset code:</b> <code>{demoToken}</code><small>In production this arrives by email.</small></div>}
          <label className="wide">Reset code<input data-testid="forgot-token-input" value={token} onChange={(e) => setToken(e.target.value)} required /></label>
          <label className="wide">New password<input data-testid="forgot-password-input" type="password" minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {err && <div className="form-error wide"><AlertCircle size={16} />{err}</div>}
          <div className="modal-actions">
            <button type="button" className="outline-button" onClick={() => setStep(1)}>Back</button>
            <button data-testid="forgot-reset-button" className="primary-button" disabled={busy}>{busy ? "Updating…" : "Update password"} <Check size={16} /></button>
          </div>
        </form>
      )}
    </div>
  </div>;
}

// ================================================================================
// Shell + shared
// ================================================================================

function Shell({ user, children, onLogout, unread, refreshUnread }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const nav = navByRole[user.role] || navByRole.PATIENT;
  const active = (path) => location.pathname === path;
  const go = (path) => { navigate(path); setMobileOpen(false); };
  useEffect(() => { refreshUnread(); }, [location.pathname, refreshUnread]);
  const submitSearch = async (e) => {
    e.preventDefault();
    if (!search.trim()) return;
    try {
      const { data } = await apiCall("get", `/search?q=${encodeURIComponent(search)}`, null, user.token);
      if (data.length) toast.success(`${data.length} result${data.length > 1 ? "s" : ""} found`);
      else toast.info("No matching care records found");
    } catch { toast.error("Search is unavailable right now"); }
  };
  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
      <div className="brand sidebar-brand">
        <div className="brand-mark"><HeartPulse size={20} /></div>
        <div><strong>Smart Health ID</strong><span>Connected care</span></div>
        <button data-testid="close-mobile-nav" className="close-mobile" onClick={() => setMobileOpen(false)}><X size={19} /></button>
      </div>
      <div className="workspace-label">YOUR WORKSPACE</div>
      <nav>
        {nav.map(([label, path, Icon]) => (
          <button data-testid={`nav-${label.toLowerCase().replaceAll(" ", "-")}`} key={path} className={active(path) ? "active" : ""} onClick={() => go(path)}>
            <Icon size={18} /><span>{label}</span>{label === "Notifications" && unread > 0 && <i className="nav-count" data-testid="sidebar-notification-badge">{unread}</i>}
          </button>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <button data-testid="nav-profile" className={active(`/${user.role.toLowerCase()}/profile`) ? "active" : ""} onClick={() => go(`/${user.role.toLowerCase()}/profile`)}><UserRound size={18} /><span>Profile</span></button>
        <button data-testid="nav-settings" onClick={() => toast.info("Settings are ready for your preferences.")}><Settings size={18} /><span>Settings</span></button>
        <div className="mini-account">
          <span className="avatar">{user.name.split(" ").map((n) => n[0]).slice(0, 2).join("")}</span>
          <div><b>{user.name}</b><small>{user.role.toLowerCase()}</small></div>
          <button data-testid="sidebar-logout-button" onClick={onLogout} aria-label="Log out"><LogOut size={16} /></button>
        </div>
      </div>
    </aside>
    {mobileOpen && <div className="nav-scrim" onClick={() => setMobileOpen(false)} />}
    <section className="main-area">
      <header className="topbar">
        <button data-testid="open-mobile-nav" className="mobile-menu" onClick={() => setMobileOpen(true)}><Menu size={21} /></button>
        <form className="global-search" onSubmit={submitSearch}>
          <Search size={18} />
          <input data-testid="global-search-input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search doctors, records, IDs..." />
          <kbd>⌘ K</kbd>
        </form>
        <div className="topbar-actions">
          <button data-testid="header-notifications-button" className={`icon-button ${unread ? "has-badge" : ""}`} onClick={() => go(`/${user.role.toLowerCase()}/notifications`)}><Bell size={19} />{unread > 0 && <i />}</button>
          <div className="top-profile">
            <span className="avatar">{user.name.split(" ").map((n) => n[0]).slice(0, 2).join("")}</span>
            <span className="top-profile-name">{user.name.split(" ").slice(0, 2).join(" ")}</span>
            <ChevronRight size={15} />
          </div>
        </div>
      </header>
      <div className="page-content">{children}</div>
    </section>
  </div>;
}

const Header = ({ eyebrow, title, subtitle, action }) => <div className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{subtitle && <p className="page-subtitle">{subtitle}</p>}</div>{action}</div>;
const Status = ({ children, tone = "green" }) => <span data-testid={`status-${String(children).toLowerCase().replaceAll(" ", "-")}`} className={`status ${tone}`}><span />{children}</span>;
const Stat = ({ label, value, detail, icon: Icon, tone = "blue" }) => <div className="stat-card" data-testid={`stat-${label.toLowerCase().replaceAll(" ", "-")}`}><div className={`stat-icon ${tone}`}><Icon size={18} /></div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></div>;
const EmptyState = ({ text }) => <div className="empty-state"><ClipboardList size={20} /><span>{text}</span></div>;

function useDoctors(user) {
  const [doctors, setDoctors] = useState([]);
  useEffect(() => { apiCall("get", "/doctors", null, user.token).then((r) => setDoctors(r.data)).catch(() => {}); }, [user.token]);
  return doctors;
}

// ================================================================================
// PATIENT PAGES
// ================================================================================

function PatientDashboard({ user, go }) {
  const [appointments, setAppointments] = useState([]);
  useEffect(() => { apiCall("get", "/appointments", null, user.token).then((r) => setAppointments(r.data)).catch(() => {}); }, [user.token]);
  return <>
    <Header eyebrow="PATIENT OVERVIEW" title={`Good morning, ${user.name.split(" ")[0]}.`} subtitle="Here's a clear view of your health, care, and next steps." action={<button data-testid="dashboard-book-appointment" className="primary-button" onClick={() => go("/patient/doctors")}><CalendarDays size={17} />Book appointment</button>} />
    <div className="welcome-strip">
      <div className="welcome-icon"><HeartPulse size={25} /></div>
      <div><b>Your health ID is verified</b><p>All your essential health information is up to date and protected.</p></div>
      <button data-testid="dashboard-view-health-id" onClick={() => go("/patient/health-id")}>View Health ID <ArrowRight size={16} /></button>
    </div>
    <div className="stat-grid">
      <Stat label="Health ID" value={user.patient_id || "SHID-10001"} detail="Verified" icon={ShieldCheck} />
      <Stat label="Blood group" value="O+" detail="Last checked 02 Feb 2026" icon={HeartPulse} tone="teal" />
      <Stat label="Appointments" value={appointments.filter(a => a.status === "Upcoming").length} detail="Upcoming visits" icon={CalendarDays} tone="gold" />
      <Stat label="Vaccinations" value="8 / 9" detail="One due soon" icon={Syringe} tone="green" />
    </div>
    <div className="content-grid dashboard-grid">
      <section className="panel activity-panel">
        <div className="panel-heading"><div><p className="eyebrow">CARE TIMELINE</p><h2>Recent activity</h2></div><button data-testid="dashboard-view-records" className="text-button" onClick={() => go("/patient/records")}>View all <ArrowRight size={15} /></button></div>
        <div className="timeline">
          <ActivityItem icon={FileCheck2} tone="green" title="Blood test report added" meta="CityCare Diagnostics · 02 Feb 2026" label="New report" />
          <ActivityItem icon={Stethoscope} tone="blue" title="Consultation completed" meta="Dr. Rahul Mehta · 18 Jan 2026" label="Consultation" />
          <ActivityItem icon={Syringe} tone="teal" title="Influenza vaccine recorded" meta="CityCare Hospital · 04 Jan 2026" label="Vaccination" />
        </div>
      </section>
      <section className="panel appointment-panel">
        <div className="panel-heading"><div><p className="eyebrow">UP NEXT</p><h2>Appointments</h2></div><button data-testid="dashboard-manage-appointments" className="icon-button" onClick={() => go("/patient/appointments")}><ArrowRight size={17} /></button></div>
        {appointments.slice(0, 2).map((apt) => <AppointmentRow key={apt.id} appointment={apt} />)}
        {!appointments.length && <EmptyState text="No upcoming appointments" />}
      </section>
    </div>
    <section className="care-insight">
      <div className="insight-icon"><Sparkles size={20} /></div>
      <div><p className="eyebrow">CARE INSIGHT</p><h3>Small habits, meaningful change</h3><p>A 20-minute walk today can support heart health, sleep quality, and stress regulation.</p></div>
      <button data-testid="dashboard-ai-specialist" onClick={() => go("/patient/ai-specialist")}>Talk to AI specialist <ArrowRight size={16} /></button>
    </section>
  </>;
}

function ActivityItem({ icon: Icon, tone, title, meta, label }) {
  return <div className="activity-item"><div className={`activity-icon ${tone}`}><Icon size={17} /></div><div><b>{title}</b><span>{meta}</span></div><small>{label}</small></div>;
}

function AppointmentRow({ appointment }) {
  return <div className="appointment-row">
    <div className="date-tile"><b>{new Date(appointment.date).toLocaleDateString("en-US", { day: "2-digit" })}</b><span>{new Date(appointment.date).toLocaleDateString("en-US", { month: "short" })}</span></div>
    <div><b>{appointment.doctor_name}</b><span>{appointment.domain} · {appointment.time}</span></div>
    <Status>{appointment.status}</Status>
  </div>;
}

function HealthIdPage({ user }) {
  const [id, setId] = useState(user.patient_id || "SHID-10001");
  const qrPayload = JSON.stringify({ shid: user.patient_id || "SHID-10001", name: user.name, issuer: "Smart Health ID", v: 1 });
  return <>
    <Header eyebrow="IDENTITY & ACCESS" title="My Health ID" subtitle="Your verified health identity, ready when care needs it." action={<button data-testid="health-id-download-button" className="outline-button" onClick={() => toast.success("Health ID PDF prepared for download")}>Download <ArrowRight size={15} /></button>} />
    <div className="health-id-layout">
      <section className="health-card">
        <div className="health-card-top"><div className="brand-mark"><HeartPulse size={20} /></div><span><ShieldCheck size={15} /> VERIFIED IDENTITY</span></div>
        <div className="health-card-main">
          <div><p className="eyebrow">SMART HEALTH ID</p><h2>{user.patient_id || "SHID-10001"}</h2><b>{user.name}</b><span>Care ID · verified</span></div>
          <div className="qr-box" data-testid="health-id-qr-visual"><QRCodeSVG value={qrPayload} size={104} bgColor="#ffffff" fgColor="#0f4078" level="M" includeMargin={false} /><small>Scan to verify</small></div>
        </div>
        <div className="health-card-bottom"><span>Issued 12 Mar 2024</span><span>Valid & verified</span></div>
      </section>
      <section className="panel verification-panel">
        <div className="panel-heading"><div><p className="eyebrow">SHARING CONTROL</p><h2>Verification status</h2></div><Status>Verified</Status></div>
        <p>Your basic identity details can be verified by an authorized care provider. Private medical records remain protected until you consent.</p>
        <div className="access-row"><ShieldCheck size={17} /><div><b>Basic identity</b><span>Visible for care coordination</span></div><Status>Authorized</Status></div>
        <div className="access-row"><FileText size={17} /><div><b>Medical records</b><span>Consent required every time</span></div><Status tone="orange">Restricted</Status></div>
        <div className="button-row">
          <button data-testid="health-id-print-button" className="outline-button" onClick={() => window.print()}>Print</button>
          <button data-testid="health-id-share-button" className="primary-button" onClick={() => { navigator.clipboard?.writeText(qrPayload).catch(() => {}); toast.success("Secure sharing link copied"); }}>Share ID <ArrowRight size={16} /></button>
        </div>
      </section>
    </div>
    <section className="panel verify-tool">
      <div><p className="eyebrow">PROVIDER TOOL</p><h2>Verify a Health ID</h2><p>Are you a doctor or care provider? Confirm a patient's basic identity before a visit.</p></div>
      <div className="verify-form">
        <input data-testid="health-id-verify-input" value={id} onChange={(e) => setId(e.target.value)} placeholder="Enter Health ID" />
        <button data-testid="health-id-verify-button" className="primary-button" onClick={() => toast.success(id.trim().toUpperCase() === (user.patient_id || "SHID-10001") ? "Health ID verified" : "Sign in as a doctor to verify others")}>Verify <ShieldCheck size={16} /></button>
      </div>
    </section>
  </>;
}

function RecordsPage({ user }) {
  const [records, setRecords] = useState([]);
  useEffect(() => { apiCall("get", "/medical-records", null, user.token).then((r) => setRecords(r.data)).catch(() => {}); }, [user.token]);
  return <>
    <Header eyebrow="YOUR HEALTH" title="Health records" subtitle="Consultations and clinical notes your doctors have shared with you." />
    <section className="panel records-list-panel" data-testid="patient-records-list">
      {!records.length && <EmptyState text="No medical records yet. Your doctors will add them here after visits." />}
      {records.map((r) => <article className="record-card" key={r.id}>
        <header><div><b>{r.doctor_name}</b><small>{new Date(r.created_at).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })}</small></div><Status>{r.status}</Status></header>
        <div className="record-body">
          <div><span className="eyebrow">DIAGNOSIS</span><p>{r.diagnosis}</p></div>
          <div><span className="eyebrow">SYMPTOMS</span><p>{r.symptoms || "—"}</p></div>
          <div><span className="eyebrow">TREATMENT</span><p>{r.treatment || "—"}</p></div>
          <div><span className="eyebrow">PRESCRIPTION</span><p>{r.prescription || "—"}</p></div>
          {r.notes && <div className="wide"><span className="eyebrow">NOTES</span><p>{r.notes}</p></div>}
        </div>
        {r.follow_up && <footer><span><CalendarDays size={14} /> Follow-up: {r.follow_up}</span></footer>}
      </article>)}
    </section>
  </>;
}

function ReportsPage({ user }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", report_type: "Lab report", provider: "CityCare Diagnostics", file: null });
  const load = useCallback(() => apiCall("get", "/reports", null, user.token).then((r) => setReports(r.data)).catch(() => {}).finally(() => setLoading(false)), [user.token]);
  useEffect(() => { load(); }, [load]);
  const submit = async (e) => {
    e.preventDefault();
    if (!form.file) return toast.error("Choose a PDF or image to upload");
    if (!form.name.trim()) return toast.error("Give this report a name");
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", form.file);
      fd.append("name", form.name);
      fd.append("report_type", form.report_type);
      fd.append("provider", form.provider);
      await axios.post(`${API}/reports`, fd, { headers: { Authorization: `Bearer ${user.token}` } });
      toast.success("Report uploaded");
      setShowForm(false);
      setForm({ name: "", report_type: "Lab report", provider: "CityCare Diagnostics", file: null });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally { setUploading(false); }
  };
  const openReport = (r) => window.open(`${API}/reports/${r.id}/file`, "_blank", "noopener,noreferrer");
  return <>
    <Header eyebrow="DOCUMENTS" title="Medical reports" subtitle="Review, upload, and keep every important result together." action={<button data-testid="upload-report-button" className="primary-button" onClick={() => setShowForm(true)}><Upload size={16} />Upload report</button>} />
    <div className="report-summary">
      <div><FileCheck2 size={22} /><b>{reports.length} report{reports.length === 1 ? "" : "s"}</b><span>{reports.filter(r => r.status === "Verified").length} verified</span></div>
      <div><Clock3 size={22} /><b>{reports.filter(r => r.status === "Pending review").length} pending review</b><span>Uploads awaiting a clinician</span></div>
      <div><ShieldCheck size={22} /><b>Private & secure</b><span>Consent controlled access</span></div>
    </div>
    <section className="panel reports-list" data-testid="reports-list">
      {loading && <EmptyState text="Loading your reports…" />}
      {!loading && !reports.length && <EmptyState text="No reports yet — upload your first PDF or image." />}
      {reports.map((r) => <div className="report-row" key={r.id}>
        <div className="report-file-icon"><FileText size={20} /></div>
        <div><b>{r.name}</b><span>{r.type} · {r.provider}</span></div>
        <span>{r.date}</span>
        <Status tone={r.status === "Verified" ? "green" : "orange"}>{r.status}</Status>
        <button data-testid={`report-view-${r.id}`} className="outline-button compact" onClick={() => openReport(r)}>View</button>
        <button data-testid={`report-download-${r.id}`} className="icon-button" onClick={() => openReport(r)}><Download size={16} /></button>
      </div>)}
    </section>
    {showForm && <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="booking-modal">
        <div className="modal-heading"><div><p className="eyebrow">NEW UPLOAD</p><h2>Upload a medical report</h2><span>PDF, PNG, JPG or WEBP · up to 8&nbsp;MB</span></div><button data-testid="upload-close-button" className="icon-button" onClick={() => setShowForm(false)}><X size={18} /></button></div>
        <form onSubmit={submit} className="booking-form">
          <label className="wide">Report name<input data-testid="upload-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Complete Blood Count" required /></label>
          <label>Type<select data-testid="upload-type-select" value={form.report_type} onChange={(e) => setForm({ ...form, report_type: e.target.value })}><option>Lab report</option><option>Imaging</option><option>Prescription</option><option>Discharge summary</option><option>Consultation note</option></select></label>
          <label>Provider<input data-testid="upload-provider-input" value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })} /></label>
          <label className="wide">File<input data-testid="upload-file-input" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={(e) => setForm({ ...form, file: e.target.files?.[0] || null })} required /></label>
          <div className="modal-actions">
            <button data-testid="upload-cancel-button" type="button" className="outline-button" onClick={() => setShowForm(false)}>Cancel</button>
            <button data-testid="upload-submit-button" className="primary-button" disabled={uploading}>{uploading ? "Uploading…" : "Upload report"} <Upload size={16} /></button>
          </div>
        </form>
      </div>
    </div>}
  </>;
}

function VaccinationsPage({ user }) {
  const [vaccines, setVaccines] = useState([]);
  useEffect(() => { apiCall("get", "/vaccinations", null, user.token).then((r) => setVaccines(r.data)).catch(() => {}); }, [user.token]);
  const completed = vaccines.filter(v => v.status === "Completed").length;
  return <>
    <Header eyebrow="PREVENTIVE CARE" title="Vaccinations" subtitle="Stay ahead of preventable illness with a clear immunization timeline." />
    <div className="vaccine-banner">
      <div className="vaccine-progress"><span>{completed} of {vaccines.length || completed || 9} vaccinations recorded</span><div><i style={{ width: `${Math.min(100, Math.round((completed / Math.max(vaccines.length || 9, 1)) * 100))}%` }} /></div></div>
      <Status tone="green">Up to date</Status>
    </div>
    <section className="panel vaccine-list" data-testid="vaccinations-list">
      {!vaccines.length && <EmptyState text="No vaccinations recorded yet." />}
      {vaccines.map((v) => <div className="vaccine-row" key={v.id || v.vaccine + v.date}>
        <div className="vaccine-icon"><Syringe size={18} /></div>
        <div><b>{v.vaccine}</b><span>{v.dose}</span></div>
        <span>{v.date}</span>
        <span>{v.provider}</span>
        <span>{v.next_due || "—"}</span>
        <Status>{v.status}</Status>
      </div>)}
    </section>
  </>;
}

function AppointmentsPage({ user, go }) {
  const [appointments, setAppointments] = useState([]);
  const [tab, setTab] = useState("Upcoming");
  const [rescheduleFor, setRescheduleFor] = useState(null);
  const load = useCallback(() => apiCall("get", "/appointments", null, user.token).then((r) => setAppointments(r.data)).catch(() => {}), [user.token]);
  useEffect(() => { load(); }, [load]);
  const patch = async (id, updates) => {
    try {
      await apiCall("patch", `/appointments/${id}`, updates, user.token);
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Could not update appointment"); }
  };
  const remind = async (id) => {
    try {
      const { data } = await apiCall("post", `/appointments/${id}/send-reminder`, null, user.token);
      setAppointments((prev) => prev.map((a) => a.id === id ? { ...a, reminder_sent: true } : a));
      toast.success(data.delivered ? "Reminder email sent" : "Reminder queued (add RESEND_API_KEY to deliver)");
    } catch { toast.error("Could not send reminder"); }
  };
  const filtered = appointments.filter((a) => a.status === tab || (tab === "Completed" && (a.status === "Attended" || a.status === "Completed")));
  return <>
    <Header eyebrow="YOUR CARE PLAN" title="Appointments" subtitle="Reminders go out automatically 24 hours before each visit." action={<button data-testid="appointments-book-button" className="primary-button" onClick={() => go("/patient/doctors")}><CalendarDays size={17} />Book appointment</button>} />
    <div className="filter-bar tabs-bar">
      {["Upcoming", "Completed", "Cancelled"].map((t) => (
        <button data-testid={`appointments-tab-${t.toLowerCase()}`} className={`filter-pill ${tab === t ? "active" : ""}`} onClick={() => setTab(t)} key={t}>{t}<span>{appointments.filter((a) => a.status === t || (t === "Completed" && (a.status === "Attended" || a.status === "Completed"))).length}</span></button>
      ))}
    </div>
    <div className="appointment-cards">
      {filtered.map((a) => <div className="panel appointment-card" key={a.id}>
        <div className="appointment-card-top">
          <div className="date-tile large"><b>{new Date(a.date).toLocaleDateString("en-US", { day: "2-digit" })}</b><span>{new Date(a.date).toLocaleDateString("en-US", { month: "short" })}</span></div>
          <div><Status>{a.status}</Status><h3>{a.doctor_name}</h3><p>{a.domain} · {a.hospital}</p></div>
        </div>
        <div className="appointment-details">
          <span><Clock3 size={15} />{a.time}</span>
          <span><ClipboardList size={15} />{a.reason}</span>
          <span><b>₹{a.fee}</b> consultation</span>
          {a.reminder_sent ? <span className="reminder-chip sent" data-testid={`reminder-sent-${a.id}`}><MailCheck size={13} /> Reminder sent</span> : <span className="reminder-chip pending" data-testid={`reminder-pending-${a.id}`}><Bell size={13} /> Auto reminder 24h before</span>}
        </div>
        {a.status === "Upcoming" && <div className="button-row">
          <button data-testid={`appointment-reschedule-${a.id}`} className="outline-button compact" onClick={() => setRescheduleFor(a)}>Reschedule</button>
          <button data-testid={`appointment-remind-${a.id}`} className="outline-button compact" onClick={() => remind(a.id)}><MailCheck size={14} />Send reminder now</button>
          <button data-testid={`appointment-cancel-${a.id}`} className="text-button danger" onClick={() => patch(a.id, { status: "Cancelled" })}>Cancel appointment</button>
        </div>}
      </div>)}
      {!filtered.length && <EmptyState text={`No ${tab.toLowerCase()} appointments`} />}
    </div>
    {rescheduleFor && <RescheduleDialog appointment={rescheduleFor} onClose={() => setRescheduleFor(null)} onSaved={() => { setRescheduleFor(null); load(); }} user={user} />}
  </>;
}

function RescheduleDialog({ appointment, onClose, onSaved, user }) {
  const [date, setDate] = useState(appointment.date);
  const [time, setTime] = useState(appointment.time);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await apiCall("patch", `/appointments/${appointment.id}`, { date, time }, user.token);
      toast.success("Appointment rescheduled");
      onSaved();
    } catch (err) { toast.error(err.response?.data?.detail || "Could not reschedule"); }
    finally { setBusy(false); }
  };
  return <div className="modal-backdrop" role="dialog" aria-modal="true">
    <div className="booking-modal">
      <div className="modal-heading"><div><p className="eyebrow">RESCHEDULE</p><h2>Change appointment time</h2><span>{appointment.doctor_name} · {appointment.hospital}</span></div><button className="icon-button" onClick={onClose}><X size={18} /></button></div>
      <form onSubmit={submit} className="booking-form">
        <DatePickerField testId="reschedule-date-input" label="Date" value={date} onChange={setDate} />
        <label>Time<select data-testid="reschedule-time-select" value={time} onChange={(e) => setTime(e.target.value)}><option>09:00 AM</option><option>10:30 AM</option><option>12:00 PM</option><option>02:30 PM</option><option>04:00 PM</option><option>05:30 PM</option></select></label>
        <div className="modal-actions">
          <button type="button" className="outline-button" onClick={onClose}>Cancel</button>
          <button data-testid="reschedule-save-button" className="primary-button" disabled={busy}>{busy ? "Saving…" : "Save changes"} <Check size={16} /></button>
        </div>
      </form>
    </div>
  </div>;
}

function DoctorsPage({ go, user }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const doctors = useDoctors(user);
  const list = doctors.filter((d) => `${d.name} ${d.specialty} ${d.hospital}`.toLowerCase().includes(query.toLowerCase()));
  return <>
    <Header eyebrow="CARE NETWORK" title="Find your doctor" subtitle="Trusted specialists, available when you need thoughtful care." />
    <div className="directory-controls">
      <div className="directory-search"><Search size={17} /><input data-testid="doctor-search-input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by name, specialty, or hospital" /></div>
    </div>
    <div className="doctor-grid">
      {list.map((d) => {
        const initials = d.name.split(" ").map(n => n[0]).slice(0, 2).join("");
        const color = ["blue", "teal", "coral", "gold"][d.doctor_id?.charCodeAt(d.doctor_id.length - 1) % 4 || 0];
        return <div className="doctor-card" key={d.doctor_id || d.email}>
          <div className={`doctor-photo ${color}`}>{initials}</div>
          <div className="doctor-card-body">
            <div className="doctor-rating">★ {d.rating || 4.7} <span className={d.on_duty ? "on" : "off"}>{d.on_duty ? "On duty" : "Off duty"}</span></div>
            <h3>{d.name}</h3>
            <p>{d.specialty}</p>
            <small>{d.hospital}</small>
            <div className="doctor-meta"><span>{d.experience || "—"} experience</span><b>₹{d.fee || 900}</b></div>
            <button data-testid={`doctor-book-${d.doctor_id}`} className="primary-button full" disabled={!d.on_duty} onClick={() => setSelected(d)}>{d.on_duty ? "Book appointment" : "Off duty"} <ArrowRight size={15} /></button>
          </div>
        </div>;
      })}
      {!list.length && <EmptyState text="No doctors match your search yet." />}
    </div>
    {selected && <BookingDialog doctor={selected} user={user} close={() => setSelected(null)} go={go} />}
  </>;
}

function BookingDialog({ doctor, user, close, go }) {
  const [date, setDate] = useState("2026-04-28");
  const [time, setTime] = useState("10:30 AM");
  const [reason, setReason] = useState("Routine consultation");
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await apiCall("post", "/appointments", { doctor_id: doctor.doctor_id, date, time, reason }, user.token);
      toast.success("Appointment confirmed");
      close(); go("/patient/appointments");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not book this appointment");
    } finally { setSaving(false); }
  };
  return <div className="modal-backdrop" role="dialog" aria-modal="true">
    <div className="booking-modal">
      <div className="modal-heading"><div><p className="eyebrow">NEW APPOINTMENT</p><h2>Book with {doctor.name}</h2><span>{doctor.specialty} · {doctor.hospital}</span></div><button data-testid="booking-close-button" className="icon-button" onClick={close}><X size={18} /></button></div>
      <form onSubmit={submit} className="booking-form">
        <DatePickerField testId="booking-date-input" label="Date" value={date} onChange={setDate} />
        <label>Available time<select data-testid="booking-time-select" value={time} onChange={(e) => setTime(e.target.value)}><option>10:30 AM</option><option>12:00 PM</option><option>04:00 PM</option><option>05:30 PM</option></select></label>
        <label className="wide">Reason for visit<input data-testid="booking-reason-input" value={reason} onChange={(e) => setReason(e.target.value)} required /></label>
        <div className="modal-actions">
          <button data-testid="booking-cancel-button" type="button" className="outline-button" onClick={close}>Cancel</button>
          <button data-testid="booking-confirm-button" className="primary-button" disabled={saving}>{saving ? "Confirming…" : "Confirm booking"} <Check size={16} /></button>
        </div>
      </form>
    </div>
  </div>;
}

function AiPage({ user, go }) {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([{ role: "assistant", text: `Hi ${user.name.split(" ")[0]} — I can help you understand symptoms and decide on sensible next steps. What are you experiencing today?` }]);
  const [loading, setLoading] = useState(false);
  const [suggestion, setSuggestion] = useState(null);
  const ask = async (text = message) => {
    if (!text.trim()) return;
    setMessages((m) => [...m, { role: "user", text }, { role: "assistant", text: "" }]);
    setMessage(""); setLoading(true); setSuggestion(null);
    try {
      const token = user.token || localStorage.getItem("shid_token");
      const response = await fetch(`${API}/ai/symptoms`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: text, session_id: "patient-demo-session" }),
      });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let full = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        chunk.split("\n\n").forEach((line) => {
          if (line.startsWith("data: ") && line.slice(6) !== "[DONE]") {
            try {
              const item = JSON.parse(line.slice(6));
              full += item.text || "";
              setMessages((m) => m.map((x, i) => i === m.length - 1 ? { ...x, text: full } : x));
            } catch {}
          }
        });
      }
      // After stream ends, ask for a specialist suggestion
      try {
        const { data } = await apiCall("post", "/ai/suggest-specialist", { symptoms: text }, token);
        if (data.doctors?.length) setSuggestion(data);
      } catch {}
    } catch {
      setMessages((m) => m.map((x, i) => i === m.length - 1 ? { ...x, text: "I'm unable to connect right now. Please contact a qualified clinician if you are concerned." } : x));
    } finally { setLoading(false); }
  };
  return <>
    <Header eyebrow="EDUCATIONAL SUPPORT" title="AI symptom specialist" subtitle="Understand what your symptoms may mean — without replacing your care team." />
    <div className="ai-disclaimer"><AlertCircle size={18} /><span><b>Important:</b> This is educational information, not a medical diagnosis. Seek professional care for concerning or worsening symptoms.</span></div>
    <div className="ai-layout">
      <section className="panel chat-panel">
        <div className="chat-header"><div className="ai-avatar"><Sparkles size={17} /></div><div><b>Smart Health Guide</b><span>Educational support · Always on</span></div><Status>Safe mode</Status></div>
        <div className="chat-messages">
          {messages.map((m, i) => <div data-testid={`ai-message-${i}`} className={`chat-bubble ${m.role}`} key={i}>
            {m.role === "assistant" && <div className="bubble-icon"><Sparkles size={13} /></div>}
            <p>{m.text}{m.role === "assistant" && loading && i === messages.length - 1 && <span className="typing">•••</span>}</p>
          </div>)}
        </div>
        {suggestion && <div className="ai-suggestion" data-testid="ai-suggestion-panel">
          <div className="ai-suggestion-head"><Stethoscope size={17} /><div><b>Suggested specialty: {suggestion.specialty}</b><small>Based on what you shared — you can book directly.</small></div></div>
          <div className="ai-doctor-list">
            {suggestion.doctors.map((d) => <div className="ai-doctor-item" key={d.doctor_id}>
              <div className="mini-avatar doctor">{d.name.split(" ").map(n => n[0]).slice(0, 2).join("")}</div>
              <div><b>{d.name}</b><small>{d.specialty} · ₹{d.fee}</small></div>
              <span className={`duty-pill ${d.on_duty ? "on" : "off"}`}>{d.on_duty ? "On duty" : "Off duty"}</span>
              <button data-testid={`ai-book-${d.doctor_id}`} className="outline-button compact" disabled={!d.on_duty} onClick={() => go("/patient/doctors")}>Book</button>
            </div>)}
          </div>
        </div>}
        <div className="suggested">
          <span>Try asking</span>
          {["I have chest pain and palpitations", "Itchy skin rash for 3 days", "My knee joint hurts"].map((s) => <button data-testid={`ai-suggestion-${s.toLowerCase().replaceAll(" ", "-")}`} key={s} onClick={() => ask(s)}>{s}</button>)}
        </div>
        <form className="chat-input" onSubmit={(e) => { e.preventDefault(); ask(); }}>
          <input data-testid="ai-symptom-input" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Describe what you're feeling..." />
          <button data-testid="ai-send-button" className="primary-button" disabled={loading || !message.trim()}><ArrowRight size={17} /></button>
        </form>
      </section>
      <aside className="ai-side">
        <div className="panel urgency-panel">
          <p className="eyebrow">WHEN TO GET HELP</p>
          <h3>Trust your instincts.</h3>
          <p>If symptoms are severe, sudden, or getting worse, contact local emergency services or a clinician now.</p>
          <div className="urgency-row"><span className="urgency-dot green" /><span>General information</span></div>
          <div className="urgency-row"><span className="urgency-dot orange" /><span>Book a clinician soon</span></div>
          <div className="urgency-row"><span className="urgency-dot red" /><span>Seek urgent medical care</span></div>
        </div>
        <div className="panel privacy-panel"><ShieldCheck size={20} /><b>Your conversation is private</b><span>Saved securely so you can revisit it, and never shared without your consent.</span></div>
      </aside>
    </div>
  </>;
}

function ProfilePage({ user }) {
  const [form, setForm] = useState({ name: user.name, phone: "", occupation: "", marital: "", address: "", height: "", weight: "", emergency: "" });
  useEffect(() => { if (user.role === "PATIENT") apiCall("get", "/profile", null, user.token).then((r) => setForm((f) => ({ ...f, ...r.data }))).catch(() => {}); }, [user]);
  const save = async (e) => {
    e.preventDefault();
    try { await apiCall("put", "/profile", form, user.token); toast.success("Profile changes saved"); }
    catch { toast.error("Could not save profile"); }
  };
  return <>
    <Header eyebrow="YOUR ACCOUNT" title="Profile" subtitle="Keep your personal and emergency information current." action={<button data-testid="profile-save-header-button" className="primary-button" onClick={save}>Save changes <Check size={16} /></button>} />
    <div className="profile-layout">
      <section className="panel profile-card">
        <div className="profile-hero">
          <div className="profile-avatar">{user.name.split(" ").map(n => n[0]).slice(0, 2).join("")}</div>
          <div><h2>{form.name}</h2><span>Health ID · {user.patient_id || "SHID-10001"}</span><Status>Verified</Status></div>
        </div>
        <div className="profile-section">
          <p className="eyebrow">PERSONAL INFORMATION</p>
          <div className="form-grid">
            <label>Full name<input data-testid="profile-name-input" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label>Email<input data-testid="profile-email-input" value={user.email} readOnly /></label>
            <label>Phone<input data-testid="profile-phone-input" value={form.phone || ""} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
            <label>Occupation<input data-testid="profile-occupation-input" value={form.occupation || ""} onChange={(e) => setForm({ ...form, occupation: e.target.value })} /></label>
            <label>Address<input data-testid="profile-address-input" value={form.address || ""} onChange={(e) => setForm({ ...form, address: e.target.value })} /></label>
            <label>Emergency contact<input data-testid="profile-emergency-input" value={form.emergency || ""} onChange={(e) => setForm({ ...form, emergency: e.target.value })} /></label>
            <label>Height<input data-testid="profile-height-input" value={form.height || ""} onChange={(e) => setForm({ ...form, height: e.target.value })} /></label>
            <label>Weight<input data-testid="profile-weight-input" value={form.weight || ""} onChange={(e) => setForm({ ...form, weight: e.target.value })} /></label>
            <label>Marital<input data-testid="profile-marital-input" value={form.marital || ""} onChange={(e) => setForm({ ...form, marital: e.target.value })} /></label>
          </div>
        </div>
        <div className="profile-actions"><button data-testid="profile-save-button" className="primary-button" onClick={save}>Save changes <Check size={16} /></button></div>
      </section>
      <aside>
        <div className="panel profile-side"><ShieldCheck size={21} /><h3>Your profile is protected</h3><p>Only information you choose to share is visible to authorized care providers.</p></div>
      </aside>
    </div>
  </>;
}

function NotificationsPage({ user, refreshUnread }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const load = useCallback(() => apiCall("get", "/notifications", null, user.token).then((r) => setItems(r.data.items)).catch(() => {}).finally(() => setLoading(false)), [user.token]);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);
  const markRead = async (id) => { await apiCall("post", `/notifications/${id}/read`, null, user.token); await load(); refreshUnread(); };
  const markAll = async () => { await apiCall("post", "/notifications/mark-all-read", null, user.token); toast.success("All caught up"); await load(); refreshUnread(); };
  const remove = async (id) => { await apiCall("delete", `/notifications/${id}`, null, user.token); await load(); refreshUnread(); };
  const iconFor = (kind) => ({
    appointment_confirmed: CalendarDays,
    appointment_status: Check,
    appointment_rescheduled: Clock3,
    reminder_sent: MailCheck,
    report_uploaded: FileText,
    record_created: ClipboardList,
    health_id_verified: ShieldCheck,
  }[kind] || Bell);
  const filtered = filter === "unread" ? items.filter((i) => !i.read) : items;
  const unread = items.filter((i) => !i.read).length;
  return <>
    <Header eyebrow="STAY INFORMED" title="Notifications" subtitle="The updates that help you stay one step ahead of your care." action={<button data-testid="mark-all-read-button" className="outline-button" disabled={!unread} onClick={markAll}>Mark all as read</button>} />
    <div className="notification-toolbar">
      <span data-testid="notification-unread-count">{unread} unread notification{unread === 1 ? "" : "s"}</span>
      <button data-testid="notification-unread-filter" className={`filter-pill ${filter === "unread" ? "active" : ""}`} onClick={() => setFilter("unread")}>Unread</button>
      <button data-testid="notification-all-filter" className={`filter-pill ${filter === "all" ? "active" : ""}`} onClick={() => setFilter("all")}>All</button>
    </div>
    <section className="panel notification-list" data-testid="notifications-list">
      {loading && <EmptyState text="Loading notifications…" />}
      {!loading && !filtered.length && <EmptyState text={filter === "unread" ? "No unread notifications" : "No notifications yet"} />}
      {filtered.map((n, i) => {
        const Icon = iconFor(n.kind);
        return <div className={`notification-row ${n.read ? "read" : ""}`} key={n.id} data-testid={`notification-${n.id}`}>
          <div className="notification-icon"><Icon size={18} /></div>
          <div><b>{n.title}</b><p>{n.text}</p><small>{new Date(n.created_at).toLocaleString("en-US", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</small></div>
          {!n.read && <button data-testid={`notification-read-${n.id}`} className="text-button" onClick={() => markRead(n.id)}>Mark read</button>}
          <button data-testid={`notification-delete-${n.id}`} className="icon-button" onClick={() => remove(n.id)} aria-label="Delete"><X size={15} /></button>
        </div>;
      })}
    </section>
  </>;
}

// ================================================================================
// DOCTOR PAGES
// ================================================================================

function DoctorDashboard({ user, go, setUser }) {
  const [appointments, setAppointments] = useState([]);
  const [patients, setPatients] = useState([]);
  const [onDuty, setOnDuty] = useState(user.on_duty ?? true);
  useEffect(() => {
    apiCall("get", "/appointments", null, user.token).then((r) => setAppointments(r.data)).catch(() => {});
    apiCall("get", "/doctor/patients", null, user.token).then((r) => setPatients(r.data)).catch(() => {});
  }, [user.token]);
  const toggleDuty = async () => {
    const next = !onDuty;
    setOnDuty(next);
    try {
      await apiCall("put", "/doctor/duty", { on_duty: next }, user.token);
      setUser({ ...user, on_duty: next });
      toast.success(next ? "You are now on duty — hospital and patients notified" : "You are off duty — new bookings paused");
    } catch { setOnDuty(!next); toast.error("Could not update duty state"); }
  };
  const today = appointments.filter(a => a.status === "Upcoming");
  return <>
    <Header eyebrow="DOCTOR PORTAL" title={`Good morning, ${user.name.split(" ")[1] || user.name}.`} subtitle="Your care queue and patient follow-ups for today." action={
      <button data-testid="duty-toggle-button" className={`duty-toggle ${onDuty ? "on" : "off"}`} onClick={toggleDuty}>
        {onDuty ? <ToggleRight size={22} /> : <ToggleLeft size={22} />}<span>{onDuty ? "On duty" : "Off duty"}</span>
      </button>
    } />
    <div className="stat-grid">
      <Stat label="Today's appointments" value={String(today.length).padStart(2, "0")} detail="Care queue" icon={CalendarDays} />
      <Stat label="Patients seen" value={patients.length} detail="Across all visits" icon={Users} tone="teal" />
      <Stat label="Records created" value={patients.reduce((s, p) => s + (p.record_count || 0), 0)} detail="Documented visits" icon={ClipboardList} tone="gold" />
      <Stat label="Duty state" value={onDuty ? "Active" : "Paused"} detail={onDuty ? "Accepting bookings" : "Bookings paused"} icon={ShieldCheck} tone="green" />
    </div>
    <div className="content-grid dashboard-grid">
      <section className="panel activity-panel">
        <div className="panel-heading"><div><p className="eyebrow">CARE QUEUE</p><h2>Upcoming today</h2></div><button data-testid="doctor-view-all" className="text-button" onClick={() => go("/doctor/appointments")}>View all <ArrowRight size={15} /></button></div>
        {!today.length && <EmptyState text="No upcoming appointments" />}
        {today.slice(0, 4).map((a) => <ActivityItem key={a.id} icon={CalendarDays} tone="blue" title={`${a.patient_name} · ${a.reason}`} meta={`${a.date} · ${a.time}`} label={a.domain} />)}
      </section>
      <section className="panel quick-panel">
        <p className="eyebrow">QUICK ACTIONS</p><h2>Keep care moving</h2>
        <button data-testid="doctor-action-patients" onClick={() => go("/doctor/patients")}><Users size={18} /><span><b>Review patients</b><small>See who you've attended</small></span><ArrowRight size={15} /></button>
        <button data-testid="doctor-action-record" onClick={() => go("/doctor/records")}><ClipboardList size={18} /><span><b>Create medical record</b><small>Document a consultation</small></span><ArrowRight size={15} /></button>
        <button data-testid="doctor-action-appointments" onClick={() => go("/doctor/appointments")}><CalendarDays size={18} /><span><b>Manage appointments</b><small>Reschedule or mark attended</small></span><ArrowRight size={15} /></button>
      </section>
    </div>
  </>;
}

function DoctorPatientsPage({ user }) {
  const [patients, setPatients] = useState([]);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");
  useEffect(() => { apiCall("get", "/doctor/patients", null, user.token).then((r) => setPatients(r.data)).catch(() => {}); }, [user.token]);
  const filtered = patients.filter((p) => `${p.name} ${p.email} ${p.patient_id}`.toLowerCase().includes(query.toLowerCase()));
  return <>
    <Header eyebrow="MY CARE" title="Patients" subtitle="Everyone you've attended so far, with quick access to their history." />
    <div className="directory-controls">
      <div className="directory-search"><Search size={17} /><input data-testid="doctor-patient-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search patients by name or Health ID" /></div>
    </div>
    <section className="panel patients-table" data-testid="doctor-patients-list">
      <div className="table-heading"><span>PATIENT</span><span>HEALTH ID</span><span>LAST VISIT</span><span>REPORTS</span><span>RECORDS</span><span></span></div>
      {!filtered.length && <EmptyState text="No patients attended yet." />}
      {filtered.map((p) => <div className="record-line" key={p.email} data-testid={`patient-row-${p.email}`}>
        <div><b>{p.name}</b><small>{p.email}</small></div>
        <span>{p.patient_id}</span>
        <span>{p.last_visit ? `${p.last_visit.date}` : "—"}</span>
        <span>{p.report_count}</span>
        <span>{p.record_count}</span>
        <button data-testid={`patient-view-${p.email}`} className="outline-button compact" onClick={() => setSelected(p.email)}>Open</button>
      </div>)}
    </section>
    {selected && <PatientDetailDialog email={selected} onClose={() => setSelected(null)} user={user} />}
  </>;
}

function PatientDetailDialog({ email, onClose, user }) {
  const [detail, setDetail] = useState(null);
  useEffect(() => { apiCall("get", `/patients/${encodeURIComponent(email)}/detail`, null, user.token).then((r) => setDetail(r.data)).catch(() => {}); }, [email, user.token]);
  const open = (r) => window.open(`${API}/reports/${r.id}/file`, "_blank", "noopener,noreferrer");
  return <div className="modal-backdrop" role="dialog" aria-modal="true">
    <div className="booking-modal wide-modal patient-detail" data-testid="patient-detail-dialog">
      <div className="modal-heading"><div><p className="eyebrow">PATIENT DETAIL</p><h2>{detail?.patient?.name || "Loading…"}</h2><span>{email}</span></div><button className="icon-button" onClick={onClose}><X size={18} /></button></div>
      {detail && <div className="patient-detail-body">
        <div className="detail-chips">
          <span><b>{detail.patient?.patient_id}</b> Health ID</span>
          <span><b>{detail.profile?.blood || "—"}</b> Blood</span>
          <span><b>{detail.profile?.gender || "—"}</b> Gender</span>
          <span><b>{detail.profile?.dob || "—"}</b> DOB</span>
          <span><b>{detail.profile?.phone || "—"}</b> Phone</span>
        </div>
        <div className="detail-section"><h3>Reports ({detail.reports.length})</h3>
          {!detail.reports.length && <span className="muted">No reports on file.</span>}
          {detail.reports.map((r) => <div className="detail-line" key={r.id}><FileText size={16} /><span>{r.name}</span><small>{r.date}</small><button className="outline-button compact" onClick={() => open(r)}>View</button></div>)}
        </div>
        <div className="detail-section"><h3>Vaccinations ({detail.vaccinations.length})</h3>
          {!detail.vaccinations.length && <span className="muted">No vaccinations recorded.</span>}
          {detail.vaccinations.map((v) => <div className="detail-line" key={v.id}><Syringe size={16} /><span>{v.vaccine} · {v.dose}</span><small>{v.date}</small></div>)}
        </div>
        <div className="detail-section"><h3>Medical records ({detail.records.length})</h3>
          {!detail.records.length && <span className="muted">No records yet.</span>}
          {detail.records.map((r) => <div className="detail-line" key={r.id}><ClipboardList size={16} /><span><b>{r.diagnosis}</b> — {r.doctor_name}</span><small>{new Date(r.created_at).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })}</small></div>)}
        </div>
        <div className="detail-section"><h3>Appointments ({detail.appointments.length})</h3>
          {detail.appointments.map((a) => <div className="detail-line" key={a.id}><CalendarDays size={16} /><span>{a.doctor_name} · {a.domain}</span><small>{a.date} · {a.time}</small><Status tone={a.status === "Upcoming" ? "blue" : a.status === "Cancelled" ? "red" : "green"}>{a.status}</Status></div>)}
        </div>
      </div>}
    </div>
  </div>;
}

function DoctorAppointmentsPage({ user }) {
  const [appointments, setAppointments] = useState([]);
  const [rescheduleFor, setRescheduleFor] = useState(null);
  const load = useCallback(() => apiCall("get", "/appointments", null, user.token).then((r) => setAppointments(r.data)).catch(() => {}), [user.token]);
  useEffect(() => { load(); }, [load]);
  const setStatus = async (id, status) => {
    try { await apiCall("patch", `/appointments/${id}`, { status }, user.token); toast.success(`Marked ${status}`); load(); }
    catch (err) { toast.error(err.response?.data?.detail || "Could not update"); }
  };
  return <>
    <Header eyebrow="CARE SCHEDULE" title="Appointments" subtitle="Your assigned patients — reschedule or mark attendance." />
    <section className="panel doctor-appointments" data-testid="doctor-appointments-list">
      <div className="table-heading five-col"><span>DATE</span><span>PATIENT</span><span>REASON</span><span>STATUS</span><span></span></div>
      {!appointments.length && <EmptyState text="No appointments assigned yet." />}
      {appointments.map((a) => <div className="record-line five-col" key={a.id}>
        <div><b>{a.date}</b><small>{a.time}</small></div>
        <div><b>{a.patient_name}</b><small>{a.patient_email}</small></div>
        <span>{a.reason}</span>
        <Status tone={a.status === "Upcoming" ? "blue" : a.status === "Cancelled" || a.status === "Not attended" ? "red" : "green"}>{a.status}</Status>
        <div className="button-row">
          {a.status === "Upcoming" && <>
            <button data-testid={`doctor-reschedule-${a.id}`} className="outline-button compact" onClick={() => setRescheduleFor(a)}>Reschedule</button>
            <button data-testid={`doctor-attended-${a.id}`} className="outline-button compact" onClick={() => setStatus(a.id, "Attended")}><Check size={14} />Attended</button>
            <button data-testid={`doctor-not-attended-${a.id}`} className="text-button danger" onClick={() => setStatus(a.id, "Not attended")}>Not attended</button>
          </>}
        </div>
      </div>)}
    </section>
    {rescheduleFor && <RescheduleDialog appointment={rescheduleFor} onClose={() => setRescheduleFor(null)} onSaved={() => { setRescheduleFor(null); load(); }} user={user} />}
  </>;
}

function DoctorRecordsPage({ user }) {
  const [records, setRecords] = useState([]);
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const empty = { patient_email: "", patient_name: "", diagnosis: "", symptoms: "", notes: "", treatment: "", prescription: "", follow_up: "" };
  const [form, setForm] = useState(empty);
  const [file, setFile] = useState(null);
  const load = useCallback(() => apiCall("get", "/medical-records", null, user.token).then((r) => setRecords(r.data)).catch(() => {}).finally(() => setLoading(false)), [user.token]);
  useEffect(() => { load(); apiCall("get", "/doctor/patients", null, user.token).then((r) => setPatients(r.data)).catch(() => {}); }, [load, user.token]);
  const submit = async (e) => {
    e.preventDefault();
    if (!form.patient_email.trim() || !form.diagnosis.trim()) return toast.error("Patient and diagnosis are required");
    setSaving(true);
    try {
      let report_id = null;
      if (file) {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("name", `${form.diagnosis} — attached report`);
        fd.append("report_type", "Consultation note");
        fd.append("provider", user.hospital || "CityCare Hospital");
        fd.append("patient_email", form.patient_email);
        const { data } = await axios.post(`${API}/reports`, fd, { headers: { Authorization: `Bearer ${user.token}` } });
        report_id = data.id;
      }
      await apiCall("post", "/medical-records", { ...form, report_id }, user.token);
      toast.success("Medical record saved");
      setShowForm(false); setForm(empty); setFile(null); load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not save record");
    } finally { setSaving(false); }
  };
  const pickPatient = (email) => {
    const p = patients.find(x => x.email === email);
    setForm({ ...form, patient_email: email, patient_name: p ? p.name : "" });
  };
  return <>
    <Header eyebrow="CLINICAL WORKSPACE" title="Medical records" subtitle="Document a consultation and optionally attach a report file." action={<button data-testid="create-record-button" className="primary-button" onClick={() => setShowForm(true)}><Plus size={16} />New record</button>} />
    <section className="panel records-list-panel" data-testid="doctor-records-list">
      {loading && <EmptyState text="Loading records…" />}
      {!loading && !records.length && <EmptyState text="No records yet — create one to get started." />}
      {records.map((r) => <article className="record-card" key={r.id} data-testid={`doctor-record-${r.id}`}>
        <header><div><b>{r.patient_name}</b><small>{r.patient_email}</small></div><Status>{r.status}</Status></header>
        <div className="record-body">
          <div><span className="eyebrow">DIAGNOSIS</span><p>{r.diagnosis}</p></div>
          <div><span className="eyebrow">SYMPTOMS</span><p>{r.symptoms || "—"}</p></div>
          <div><span className="eyebrow">TREATMENT</span><p>{r.treatment || "—"}</p></div>
          <div><span className="eyebrow">PRESCRIPTION</span><p>{r.prescription || "—"}</p></div>
          {r.notes && <div className="wide"><span className="eyebrow">NOTES</span><p>{r.notes}</p></div>}
        </div>
        <footer>
          <span><Clock3 size={14} /> {new Date(r.created_at).toLocaleString("en-US", { day: "2-digit", month: "short", year: "numeric" })}</span>
          {r.follow_up && <span><CalendarDays size={14} /> Follow-up: {r.follow_up}</span>}
          {r.report_id && <button className="text-button" onClick={() => window.open(`${API}/reports/${r.report_id}/file`, "_blank", "noopener,noreferrer")}><Paperclip size={13} /> View attached report</button>}
        </footer>
      </article>)}
    </section>
    {showForm && <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="booking-modal wide-modal">
        <div className="modal-heading"><div><p className="eyebrow">CONSULTATION</p><h2>Create medical record</h2><span>Shared securely with the patient</span></div><button data-testid="record-close-button" className="icon-button" onClick={() => setShowForm(false)}><X size={18} /></button></div>
        <form onSubmit={submit} className="booking-form">
          <label>Patient
            <select data-testid="record-patient-select" value={form.patient_email} onChange={(e) => pickPatient(e.target.value)} required>
              <option value="">Select a patient</option>
              {patients.map(p => <option key={p.email} value={p.email}>{`${p.name} — ${p.patient_id}`}</option>)}
            </select>
          </label>
          <label>Or type email<input data-testid="record-patient-email" value={form.patient_email} onChange={(e) => setForm({ ...form, patient_email: e.target.value })} placeholder="patient@example.com" /></label>
          <label className="wide">Patient name<input data-testid="record-patient-name" value={form.patient_name} onChange={(e) => setForm({ ...form, patient_name: e.target.value })} required /></label>
          <label className="wide">Diagnosis<input data-testid="record-diagnosis" value={form.diagnosis} onChange={(e) => setForm({ ...form, diagnosis: e.target.value })} placeholder="e.g. Mild hypertension" required /></label>
          <label className="wide">Symptoms<input data-testid="record-symptoms" value={form.symptoms} onChange={(e) => setForm({ ...form, symptoms: e.target.value })} placeholder="Fatigue, occasional headaches" /></label>
          <label>Treatment<input data-testid="record-treatment" value={form.treatment} onChange={(e) => setForm({ ...form, treatment: e.target.value })} placeholder="Lifestyle changes" /></label>
          <DatePickerField testId="record-follow-up" label="Follow-up date" value={form.follow_up} onChange={(v) => setForm({ ...form, follow_up: v })} />
          <label className="wide">Prescription<textarea data-testid="record-prescription" rows={2} value={form.prescription} onChange={(e) => setForm({ ...form, prescription: e.target.value })} placeholder="Amlodipine 2.5mg · once daily" /></label>
          <label className="wide">Clinical notes<textarea data-testid="record-notes" rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="BP 138/90; discussed low-sodium diet." /></label>
          <label className="wide">Attach report (optional)<input data-testid="record-file-input" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
          <div className="modal-actions">
            <button data-testid="record-cancel-button" type="button" className="outline-button" onClick={() => setShowForm(false)}>Cancel</button>
            <button data-testid="record-save-button" className="primary-button" disabled={saving}>{saving ? "Saving…" : "Save record"} <Check size={16} /></button>
          </div>
        </form>
      </div>
    </div>}
  </>;
}

// ================================================================================
// HOSPITAL PAGES
// ================================================================================

function HospitalDashboard({ user, go }) {
  const [overview, setOverview] = useState({ doctor_count: 0, patient_count: 0, appointment_count: 0 });
  useEffect(() => { apiCall("get", "/dashboard", null, user.token).then((r) => setOverview(r.data)).catch(() => {}); }, [user.token]);
  return <>
    <Header eyebrow="PROVIDER PORTAL" title={`Welcome, ${user.name}.`} subtitle="A clear operational view of your care network." action={<button data-testid="hospital-verify-button" className="primary-button" onClick={() => go("/hospital/verification")}><ShieldCheck size={17} />Verify Health ID</button>} />
    <div className="stat-grid">
      <Stat label="Total doctors" value={overview.doctor_count} detail="Across specialties" icon={Stethoscope} />
      <Stat label="Total patients" value={overview.patient_count} detail="Registered at hospital" icon={Users} tone="teal" />
      <Stat label="Appointments" value={overview.appointment_count} detail="All time" icon={CalendarDays} tone="gold" />
      <Stat label="Verified records" value="98.4%" detail="Across your network" icon={ShieldCheck} tone="green" />
    </div>
    <div className="content-grid dashboard-grid">
      <section className="panel quick-panel">
        <p className="eyebrow">HOSPITAL WORKSPACE</p><h2>Jump into the day</h2>
        <button onClick={() => go("/hospital/doctors")}><Stethoscope size={18} /><span><b>Doctors on duty</b><small>See who is available now</small></span><ArrowRight size={15} /></button>
        <button onClick={() => go("/hospital/patients")}><Users size={18} /><span><b>Patients</b><small>Recently attended</small></span><ArrowRight size={15} /></button>
        <button onClick={() => go("/hospital/appointments")}><CalendarDays size={18} /><span><b>Appointments</b><small>Today's schedule across teams</small></span><ArrowRight size={15} /></button>
        <button onClick={() => go("/hospital/reports")}><FileText size={18} /><span><b>Reports</b><small>Patient reports at your hospital</small></span><ArrowRight size={15} /></button>
      </section>
      <section className="panel activity-panel">
        <div className="panel-heading"><div><p className="eyebrow">RECENT</p><h2>Activity</h2></div></div>
        <div className="timeline">
          <ActivityItem icon={ShieldCheck} tone="green" title="Health ID verified" meta="Aarav Sharma · 9 min ago" label="Authorized" />
          <ActivityItem icon={CalendarDays} tone="blue" title="New appointment booked" meta="Riya Kapoor · 25 min ago" label="Upcoming" />
          <ActivityItem icon={FileText} tone="gold" title="Report uploaded" meta="Karthik Iyer · 1 hr ago" label="Review" />
        </div>
      </section>
    </div>
  </>;
}

function HospitalDoctorsPage({ user }) {
  const [doctors, setDoctors] = useState([]);
  useEffect(() => { apiCall("get", "/hospital/doctors", null, user.token).then((r) => setDoctors(r.data)).catch(() => {}); }, [user.token]);
  return <>
    <Header eyebrow="HOSPITAL NETWORK" title="Doctors" subtitle="Your care team and their duty status." />
    <section className="panel patients-table" data-testid="hospital-doctors-list">
      <div className="table-heading five-col"><span>DOCTOR</span><span>SPECIALTY</span><span>EXPERIENCE</span><span>FEE</span><span>STATUS</span></div>
      {!doctors.length && <EmptyState text="No doctors registered yet." />}
      {doctors.map((d) => <div className="record-line five-col" key={d.doctor_id || d.email} data-testid={`hospital-doctor-${d.doctor_id}`}>
        <div><b>{d.name}</b><small>{d.email}</small></div>
        <span>{d.specialty}</span>
        <span>{d.experience || "—"}</span>
        <span>₹{d.fee || "—"}</span>
        <span className={`duty-pill ${d.on_duty ? "on" : "off"}`}>{d.on_duty ? "On duty" : "Off duty"}</span>
      </div>)}
    </section>
  </>;
}

function HospitalPatientsPage({ user }) {
  const [patients, setPatients] = useState([]);
  const [selected, setSelected] = useState(null);
  useEffect(() => { apiCall("get", "/hospital/patients", null, user.token).then((r) => setPatients(r.data)).catch(() => {}); }, [user.token]);
  return <>
    <Header eyebrow="HOSPITAL NETWORK" title="Patients" subtitle="Everyone registered at your hospital, with quick access to their file." />
    <section className="panel patients-table" data-testid="hospital-patients-list">
      <div className="table-heading"><span>PATIENT</span><span>HEALTH ID</span><span>PHONE</span><span>BLOOD</span><span>APPOINTMENTS</span><span></span></div>
      {!patients.length && <EmptyState text="No patients registered yet." />}
      {patients.map((p) => <div className="record-line" key={p.email} data-testid={`hospital-patient-${p.email}`}>
        <div><b>{p.name}</b><small>{p.email}</small></div>
        <span>{p.patient_id}</span>
        <span>{p.profile?.phone || "—"}</span>
        <span>{p.profile?.blood || "—"}</span>
        <span>{p.appointment_count}</span>
        <button className="outline-button compact" onClick={() => setSelected(p.email)}>Open</button>
      </div>)}
    </section>
    {selected && <PatientDetailDialog email={selected} onClose={() => setSelected(null)} user={user} />}
  </>;
}

function HospitalAppointmentsPage({ user }) {
  const [appts, setAppts] = useState([]);
  useEffect(() => { apiCall("get", "/appointments", null, user.token).then((r) => setAppts(r.data)).catch(() => {}); }, [user.token]);
  return <>
    <Header eyebrow="OPERATIONS" title="Appointments" subtitle="Every appointment scheduled across your hospital." />
    <section className="panel patients-table" data-testid="hospital-appointments-list">
      <div className="table-heading five-col"><span>DATE</span><span>PATIENT</span><span>DOCTOR</span><span>REASON</span><span>STATUS</span></div>
      {!appts.length && <EmptyState text="No appointments yet." />}
      {appts.map((a) => <div className="record-line five-col" key={a.id}>
        <div><b>{a.date}</b><small>{a.time}</small></div>
        <div><b>{a.patient_name}</b><small>{a.patient_email}</small></div>
        <div><b>{a.doctor_name}</b><small>{a.domain}</small></div>
        <span>{a.reason}</span>
        <Status tone={a.status === "Upcoming" ? "blue" : a.status === "Cancelled" || a.status === "Not attended" ? "red" : "green"}>{a.status}</Status>
      </div>)}
    </section>
  </>;
}

function HospitalVaccinationsPage({ user }) {
  const [items, setItems] = useState([]);
  useEffect(() => { apiCall("get", "/vaccinations", null, user.token).then((r) => setItems(r.data)).catch(() => {}); }, [user.token]);
  return <>
    <Header eyebrow="PREVENTIVE CARE" title="Vaccinations" subtitle="Everything administered at your hospital." />
    <section className="panel vaccine-list" data-testid="hospital-vaccinations-list">
      {!items.length && <EmptyState text="No vaccinations recorded." />}
      {items.map((v) => <div className="vaccine-row" key={v.id}>
        <div className="vaccine-icon"><Syringe size={18} /></div>
        <div><b>{v.patient_name}</b><span>{v.vaccine} · {v.dose}</span></div>
        <span>{v.date}</span>
        <span>{v.recorded_by || v.provider}</span>
        <span>{v.next_due || "—"}</span>
        <Status>{v.status}</Status>
      </div>)}
    </section>
  </>;
}

function HospitalReportsPage({ user }) {
  const [reports, setReports] = useState([]);
  useEffect(() => { apiCall("get", "/reports", null, user.token).then((r) => setReports(r.data)).catch(() => {}); }, [user.token]);
  const open = (r) => window.open(`${API}/reports/${r.id}/file`, "_blank", "noopener,noreferrer");
  return <>
    <Header eyebrow="DOCUMENTS" title="Reports" subtitle="Every patient report at your hospital, one click away." />
    <section className="panel reports-list" data-testid="hospital-reports-list">
      {!reports.length && <EmptyState text="No reports uploaded yet." />}
      {reports.map((r) => <div className="report-row" key={r.id}>
        <div className="report-file-icon"><FileText size={20} /></div>
        <div><b>{r.name}</b><span>{r.type} · {r.patient_email}</span></div>
        <span>{r.date}</span>
        <Status tone={r.status === "Verified" ? "green" : "orange"}>{r.status}</Status>
        <button className="outline-button compact" onClick={() => open(r)}>View</button>
        <button className="icon-button" onClick={() => open(r)}><Download size={16} /></button>
      </div>)}
    </section>
  </>;
}

function VerificationPage({ user }) {
  const [id, setId] = useState("SHID-10001");
  const [result, setResult] = useState(null);
  const verify = async () => {
    try {
      const { data } = await apiCall("post", `/verify-health-id?health_id=${encodeURIComponent(id)}`, null, user.token);
      setResult(data);
    } catch (err) { setResult({ error: err.response?.data?.detail || "Health ID not found. Check the ID and try again." }); }
  };
  return <>
    <Header eyebrow="TRUST & CONSENT" title="Health ID verification" subtitle="Confirm basic identity before care — never expose more than necessary." />
    <section className="verify-hero panel">
      <div><p className="eyebrow">PROVIDER VERIFICATION</p><h2>Is this patient who they say they are?</h2><p>Enter a Smart Health ID to verify public identity information. Medical records remain restricted until the patient gives consent.</p></div>
      <div className="provider-verify-form">
        <label>Health ID<input data-testid="provider-health-id-input" value={id} onChange={(e) => setId(e.target.value)} /></label>
        <button data-testid="provider-health-id-verify-button" className="primary-button" onClick={verify}>Verify identity <ShieldCheck size={16} /></button>
      </div>
    </section>
    {result && <section className={`panel verification-result ${result.error ? "error" : ""}`} data-testid="verification-result">
      {result.error ? <><AlertCircle size={21} /><b>{result.error}</b></> : <>
        <div className="result-icon"><Check size={20} /></div>
        <div>
          <Status>Verified</Status>
          <h2>{result.name}</h2>
          <p>{result.health_id} · {result.dob} · {result.gender} · Blood group {result.blood}</p>
          <span>Basic identity shared · {result.accessed_by} · just now</span>
        </div>
        <div className="consent-box"><ShieldCheck size={17} /><b>Consent status</b><span>{result.consent}</span></div>
      </>}
    </section>}
  </>;
}

// ================================================================================
// Router
// ================================================================================

function AppContent() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [unread, setUnread] = useState(0);
  const navigate = useNavigate();
  const location = useLocation();
  const refreshUnread = useCallback(() => {
    if (!user?.token) return;
    apiCall("get", "/notifications", null, user.token).then((r) => setUnread(r.data.unread)).catch(() => {});
  }, [user?.token]);
  useEffect(() => {
    const token = localStorage.getItem("shid_token");
    if (token) apiCall("get", "/auth/me", null, token).then((r) => setUser({ ...r.data, token })).catch(() => localStorage.removeItem("shid_token")).finally(() => setChecking(false));
    else setChecking(false);
  }, []);
  useEffect(() => { if (!user) return; refreshUnread(); const t = setInterval(refreshUnread, 20000); return () => clearInterval(t); }, [user, refreshUnread]);
  const logout = async () => {
    try { await apiCall("post", "/auth/logout", null, user?.token); } catch {}
    localStorage.removeItem("shid_token");
    setUser(null);
    navigate("/");
  };
  if (checking) return <div className="loading-screen"><div className="brand-mark"><HeartPulse size={22} /></div><span>Opening your secure workspace…</span></div>;
  if (!user) return <Login onLogin={(u) => { setUser(u); navigate(`/${u.role.toLowerCase()}/dashboard`); }} />;
  const go = (path) => navigate(path);
  const path = location.pathname;
  const roleRoute = path.startsWith("/patient") ? "PATIENT" : path.startsWith("/doctor") ? "DOCTOR" : path.startsWith("/hospital") ? "HOSPITAL" : null;
  let page = null;
  if (roleRoute && roleRoute !== user.role) {
    page = <div className="panel provider-placeholder"><div className="provider-placeholder-icon"><ShieldCheck size={25} /></div><h2>Access restricted</h2><p>This workspace is limited to your signed-in role.</p><button className="primary-button" onClick={() => go(`/${user.role.toLowerCase()}/dashboard`)}>Return to your dashboard <ArrowRight size={16} /></button></div>;
  } else if (user.role === "PATIENT") {
    if (path.includes("health-id")) page = <HealthIdPage user={user} />;
    else if (path.includes("records")) page = <RecordsPage user={user} />;
    else if (path.includes("reports")) page = <ReportsPage user={user} />;
    else if (path.includes("vaccinations")) page = <VaccinationsPage user={user} />;
    else if (path.includes("appointments")) page = <AppointmentsPage user={user} go={go} />;
    else if (path.includes("doctors")) page = <DoctorsPage go={go} user={user} />;
    else if (path.includes("ai-specialist")) page = <AiPage user={user} go={go} />;
    else if (path.includes("notifications")) page = <NotificationsPage user={user} refreshUnread={refreshUnread} />;
    else if (path.includes("profile")) page = <ProfilePage user={user} />;
    else page = <PatientDashboard user={user} go={go} />;
  } else if (user.role === "DOCTOR") {
    if (path.includes("patients")) page = <DoctorPatientsPage user={user} />;
    else if (path.includes("appointments")) page = <DoctorAppointmentsPage user={user} />;
    else if (path.includes("records")) page = <DoctorRecordsPage user={user} />;
    else if (path.includes("profile")) page = <ProfilePage user={user} />;
    else page = <DoctorDashboard user={user} go={go} setUser={setUser} />;
  } else {
    if (path.includes("doctors")) page = <HospitalDoctorsPage user={user} />;
    else if (path.includes("patients")) page = <HospitalPatientsPage user={user} />;
    else if (path.includes("appointments")) page = <HospitalAppointmentsPage user={user} />;
    else if (path.includes("vaccinations")) page = <HospitalVaccinationsPage user={user} />;
    else if (path.includes("reports")) page = <HospitalReportsPage user={user} />;
    else if (path.includes("verification")) page = <VerificationPage user={user} />;
    else if (path.includes("profile")) page = <ProfilePage user={user} />;
    else page = <HospitalDashboard user={user} go={go} />;
  }
  return <Shell user={user} onLogout={logout} unread={unread} refreshUnread={refreshUnread}>{page}</Shell>;
}

export default function App() {
  return <BrowserRouter><AppContent /><Toaster position="top-right" richColors /></BrowserRouter>;
}
