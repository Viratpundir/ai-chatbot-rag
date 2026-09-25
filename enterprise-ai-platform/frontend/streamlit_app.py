import os
import time
from typing import Any, Dict, List, Optional

import requests
import streamlit as st


# ============================================================
# ENTERPRISE AI KNOWLEDGE PLATFORM - STREAMLIT FRONTEND
# ============================================================
#
# Backend expected:
#   FastAPI: http://127.0.0.1:8000
#
# Authentication:
#   POST /api/v1/auth/login
#   POST /api/v1/auth/request-otp
#   POST /api/v1/auth/verify-otp
#   POST /api/v1/auth/register
#
# Documents:
#   GET  /api/v1/documents
#   POST /api/v1/documents/upload
#   GET  /api/v1/documents/{id}
#   DELETE /api/v1/documents/{id}
#
# AI:
#   POST /api/v1/chat
#   POST /api/v1/guide
#
# System:
#   GET /api/v1/health
#
# If your backend uses different routes, change only the
# ENDPOINTS dictionary below.
# ============================================================


st.set_page_config(
    page_title="Enterprise AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CONFIGURATION
# ============================================================

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

ENDPOINTS = {
    "health": "/api/v1/health",

    "login": "/api/v1/auth/login",
    "request_otp": "/api/v1/auth/request-otp",
    "verify_otp": "/api/v1/auth/verify-otp",
    "register": "/api/v1/auth/register",

    "documents": "/api/v1/documents",
    "upload": "/api/v1/documents/upload",

    "chat": "/api/v1/chat",
    "guide": "/api/v1/guide",
}

REQUEST_TIMEOUT = 45
POLL_SECONDS = 3
MAX_STATUS_POLLS = 20


# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_STATE = {
    "token": None,
    "user": None,
    "page": "Dashboard",
    "documents": [],
    "selected_documents": [],
    "messages": [],
    "history": [],
    "otp_requested": False,
    "backend_online": False,
    "last_latency": None,
    "last_sources": [],
    "last_retrieval_debug": [],
    "pending_upload": False,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --primary: #533ee5;
    --primary-2: #7a5cff;
    --secondary: #00a88f;
    --surface: #fdf8ff;
    --surface-low: #f7f1ff;
    --surface-card: #ffffff;
    --text: #1b1735;
    --muted: #6c687b;
    --border: #e7e1f2;
    --danger: #ba1a1a;
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background:
        radial-gradient(circle at 80% 0%, rgba(122,92,255,.10), transparent 28%),
        radial-gradient(circle at 100% 70%, rgba(0,194,168,.07), transparent 25%),
        #fdf8ff;
    color: var(--text);
}

[data-testid="stHeader"] {
    background: rgba(253,248,255,.75);
}

[data-testid="stSidebar"] {
    background: #f7f1ff;
    border-right: 1px solid rgba(80,70,120,.08);
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 1rem;
}

.block-container {
    max-width: 1440px;
    padding-top: 1.5rem;
    padding-bottom: 3rem;
}

h1, h2, h3, h4 {
    color: var(--text) !important;
    letter-spacing: -.02em;
}

p, label, .stCaption {
    color: var(--muted);
}

div[data-testid="stButton"] > button {
    border-radius: 10px;
    border: 1px solid var(--border);
    font-weight: 600;
    min-height: 42px;
    transition: .2s ease;
}

div[data-testid="stButton"] > button:hover {
    border-color: #b8aceb;
    transform: translateY(-1px);
}

div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, var(--primary), var(--primary-2));
    color: white;
    border: none;
}

.enterprise-card {
    background: var(--surface-card);
    border: 1px solid rgba(80,70,120,.08);
    border-radius: 16px;
    padding: 22px;
    box-shadow: 0 5px 24px rgba(39,25,90,.05);
}

.hero {
    position: relative;
    overflow: hidden;
    border-radius: 18px;
    padding: 34px;
    color: white;
    background: linear-gradient(105deg, #7458ff 0%, #8e5bff 50%, #00bfa5 100%);
    box-shadow: 0 18px 45px rgba(83,62,229,.18);
}

.hero h1, .hero p {
    color: white !important;
}

.hero:after {
    content: "";
    position: absolute;
    width: 360px;
    height: 360px;
    right: -100px;
    bottom: -180px;
    border-radius: 50%;
    background: rgba(255,255,255,.15);
    filter: blur(25px);
}

.metric {
    background: white;
    border: 1px solid rgba(80,70,120,.08);
    border-radius: 15px;
    padding: 18px;
    min-height: 105px;
    box-shadow: 0 5px 22px rgba(39,25,90,.04);
}

.metric-value {
    font-size: 28px;
    font-weight: 800;
    color: var(--text);
}

.metric-label {
    font-size: 12px;
    color: var(--muted);
    margin-top: 3px;
}

.badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: 999px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 700;
}

.badge-ready {
    background: #e3faf4;
    color: #006b5c;
}

.badge-processing {
    background: #fff4d9;
    color: #936000;
}

.badge-failed {
    background: #ffe7e5;
    color: #a71922;
}

.badge-uploaded {
    background: #ece9ff;
    color: #4a39bb;
}

.badge-admin {
    background: #e6e0ff;
    color: #402bb6;
}

.badge-employee {
    background: #e7ecff;
    color: #3947a6;
}

.badge-student {
    background: #def8f2;
    color: #006b5c;
}

.document-row {
    background: white;
    border: 1px solid var(--border);
    border-radius: 13px;
    padding: 14px 16px;
    margin-bottom: 9px;
}

.source-card {
    background: #faf8ff;
    border: 1px solid var(--border);
    border-radius: 11px;
    padding: 11px 13px;
    margin: 6px 0;
}

.chat-user {
    background: #eeeaff;
    border-radius: 14px 14px 4px 14px;
    padding: 13px 16px;
    margin: 12px 0 8px auto;
    max-width: 85%;
}

.chat-ai {
    background: white;
    border: 1px solid var(--border);
    border-radius: 14px 14px 14px 4px;
    padding: 16px;
    margin: 8px 0 14px 0;
    max-width: 92%;
    box-shadow: 0 4px 18px rgba(39,25,90,.04);
}

.small-muted {
    font-size: 12px;
    color: var(--muted);
}

.auth-card {
    max-width: 540px;
    margin: 8vh auto 0 auto;
    background: white;
    border: 1px solid var(--border);
    border-radius: 22px;
    padding: 34px;
    box-shadow: 0 20px 70px rgba(39,25,90,.10);
}

.login-logo {
    width: 58px;
    height: 58px;
    border-radius: 17px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, var(--primary), #8d5bff);
    color: white;
    font-size: 28px;
    box-shadow: 0 10px 25px rgba(83,62,229,.22);
}

.section-title {
    margin-top: 10px;
    margin-bottom: 8px;
}

.guide-step {
    background: white;
    border: 1px solid var(--border);
    border-radius: 13px;
    padding: 15px;
    margin: 8px 0;
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 6px 10px;
    border-radius: 999px;
    background: white;
    border: 1px solid var(--border);
    font-size: 11px;
    font-weight: 600;
}

.online-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #00a88f;
    box-shadow: 0 0 0 4px rgba(0,168,143,.12);
}

.offline-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #d64545;
    box-shadow: 0 0 0 4px rgba(214,69,69,.12);
}

div[data-testid="stFileUploader"] {
    background: #f6f3ff;
    border: 1px dashed #b7a9ec;
    border-radius: 14px;
    padding: 8px;
}

div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
    border-radius: 10px;
}

@media (max-width: 900px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }
    .hero {
        padding: 24px;
    }
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# HELPERS
# ============================================================

def user_data() -> Dict[str, Any]:
    return st.session_state.user or {}


def current_role() -> str:
    return str(
        user_data().get("role")
        or user_data().get("user_role")
        or "EMPLOYEE"
    ).upper()


def current_name() -> str:
    return (
        user_data().get("name")
        or user_data().get("full_name")
        or user_data().get("username")
        or "User"
    )


def current_email() -> str:
    return str(user_data().get("email") or "")


def auth_headers() -> Dict[str, str]:
    headers = {"Accept": "application/json"}

    if st.session_state.token:
        headers["Authorization"] = (
            f"Bearer {st.session_state.token}"
        )

    return headers


def parse_response(response: Optional[requests.Response]) -> Any:
    if response is None:
        return None

    try:
        return response.json()
    except Exception:
        return {}


def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None):
    try:
        return requests.get(
            f"{API_BASE_URL}{endpoint}",
            headers=auth_headers(),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return None


def api_post(
    endpoint: str,
    json_data: Optional[Dict[str, Any]] = None,
    files=None,
):
    try:
        return requests.post(
            f"{API_BASE_URL}{endpoint}",
            headers=auth_headers(),
            json=json_data if files is None else None,
            files=files,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return None


def api_delete(endpoint: str):
    try:
        return requests.delete(
            f"{API_BASE_URL}{endpoint}",
            headers=auth_headers(),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return None


def error_message(response: Optional[requests.Response], fallback: str) -> str:
    if response is None:
        return fallback

    data = parse_response(response)

    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, str):
            return detail

        message = data.get("message")
        if isinstance(message, str):
            return message

    return fallback


def normalize_documents(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("documents", "data", "items", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]

    return []


def document_id(doc: Dict[str, Any]) -> Optional[str]:
    value = doc.get("id") or doc.get("document_id")
    return str(value) if value is not None else None


def document_name(doc: Dict[str, Any]) -> str:
    return (
        doc.get("filename")
        or doc.get("file_name")
        or doc.get("name")
        or "Unnamed document"
    )


def document_status(doc: Dict[str, Any]) -> str:
    return str(
        doc.get("status")
        or doc.get("processing_status")
        or "UNKNOWN"
    ).upper()


def is_ready(doc: Dict[str, Any]) -> bool:
    return document_status(doc) == "READY"


def status_badge(status: str) -> str:
    status = status.upper()

    mapping = {
        "READY": ("badge-ready", "● READY"),
        "PROCESSING": ("badge-processing", "◐ PROCESSING"),
        "FAILED": ("badge-failed", "● FAILED"),
        "UPLOADED": ("badge-uploaded", "○ UPLOADED"),
    }

    css, label = mapping.get(
        status,
        ("badge-uploaded", f"○ {status}")
    )

    return f'<span class="badge {css}">{label}</span>'


def role_badge(role: str) -> str:
    role = role.upper()

    css = {
        "SUPER_ADMIN": "badge-admin",
        "ADMIN": "badge-admin",
        "EMPLOYEE": "badge-employee",
        "STUDENT": "badge-student",
    }.get(role, "badge-employee")

    return f'<span class="badge {css}">{role}</span>'


def load_documents(show_error: bool = False) -> List[Dict[str, Any]]:
    response = api_get(ENDPOINTS["documents"])

    if response is None:
        if show_error:
            st.error("Could not connect to the document service.")
        return []

    if response.status_code != 200:
        if show_error:
            st.error(
                error_message(
                    response,
                    "Unable to load documents."
                )
            )
        return []

    docs = normalize_documents(parse_response(response))
    st.session_state.documents = docs
    return docs


def check_backend() -> bool:
    response = api_get(ENDPOINTS["health"])

    online = (
        response is not None
        and response.status_code == 200
    )

    st.session_state.backend_online = online
    return online


def logout():
    for key, value in DEFAULT_STATE.items():
        st.session_state[key] = value
    st.rerun()


# ============================================================
# AUTHENTICATION
# ============================================================

def perform_login(email: str, password: str) -> bool:
    response = api_post(
        ENDPOINTS["login"],
        json_data={
            "email": email,
            "password": password,
        },
    )

    if response is None:
        st.error(
            "Authentication service is offline. "
            "Start FastAPI first."
        )
        return False

    if response.status_code not in (200, 201):
        st.error(
            error_message(
                response,
                "Invalid email or password."
            )
        )
        return False

    data = parse_response(response)

    if not isinstance(data, dict):
        st.error("Invalid authentication response.")
        return False

    st.session_state.token = (
        data.get("access_token")
        or data.get("token")
        or data.get("jwt")
    )

    st.session_state.user = (
        data.get("user")
        or data.get("data")
        or {}
    )

    if not st.session_state.token:
        st.error(
            "Login succeeded but no access token was returned."
        )
        return False

    return True


def request_otp(email: str) -> bool:
    response = api_post(
        ENDPOINTS["request_otp"],
        json_data={"email": email},
    )

    if response is None:
        st.error("Authentication service is offline.")
        return False

    if response.status_code not in (200, 201):
        st.error(
            error_message(
                response,
                "Unable to send OTP."
            )
        )
        return False

    st.session_state.otp_requested = True
    return True


def verify_otp(email: str, otp: str) -> bool:
    response = api_post(
        ENDPOINTS["verify_otp"],
        json_data={
            "email": email,
            "otp": otp,
        },
    )

    if response is None:
        st.error("Authentication service is offline.")
        return False

    if response.status_code not in (200, 201):
        st.error(
            error_message(
                response,
                "Invalid or expired OTP."
            )
        )
        return False

    data = parse_response(response)

    st.session_state.token = (
        data.get("access_token")
        or data.get("token")
        or data.get("jwt")
    )

    st.session_state.user = (
        data.get("user")
        or data.get("data")
        or {}
    )

    return bool(st.session_state.token)


def register(
    name: str,
    email: str,
    password: str,
    role: str,
) -> bool:
    response = api_post(
        ENDPOINTS["register"],
        json_data={
            "name": name,
            "email": email,
            "password": password,
            "role": role,
        },
    )

    if response is None:
        st.error("Authentication service is offline.")
        return False

    if response.status_code not in (200, 201):
        st.error(
            error_message(
                response,
                "Registration failed."
            )
        )
        return False

    return True


def authentication_page():
    st.markdown(
        """
        <div class="auth-card">
            <div class="login-logo">✦</div>
            <h1 style="margin-top:18px;">Enterprise AI</h1>
            <p>
                Secure knowledge and document intelligence
                for enterprise teams.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    online = check_backend()

    if online:
        st.success("FastAPI backend is online.")
    else:
        st.error(
            "API Offline — start the FastAPI backend."
        )
        st.code(
            "uvicorn app.main:app --reload",
            language="powershell",
        )

    st.markdown("### Sign in to continue")

    password_tab, otp_tab, register_tab = st.tabs(
        ["Password", "Email OTP", "Create account"]
    )

    with password_tab:
        email = st.text_input(
            "Work / student email",
            key="login_email",
        )

        password = st.text_input(
            "Password",
            type="password",
            key="login_password",
        )

        if st.button(
            "Sign in",
            type="primary",
            use_container_width=True,
        ):
            if not email or not password:
                st.warning(
                    "Enter both email and password."
                )
            elif perform_login(email, password):
                st.success("Signed in successfully.")
                st.rerun()

    with otp_tab:
        email = st.text_input(
            "Email",
            key="otp_email",
        )

        if not st.session_state.otp_requested:
            if st.button(
                "Send OTP",
                use_container_width=True,
            ):
                if not email:
                    st.warning("Enter your email.")
                elif request_otp(email):
                    st.success(
                        "OTP sent. Check your email."
                    )
                    st.rerun()
        else:
            otp = st.text_input(
                "6-digit OTP",
                max_chars=6,
                key="otp_value",
            )

            if st.button(
                "Verify OTP",
                type="primary",
                use_container_width=True,
            ):
                if not otp:
                    st.warning("Enter the OTP.")
                elif verify_otp(email, otp):
                    st.success("OTP verified.")
                    st.session_state.otp_requested = False
                    st.rerun()

            if st.button("Send OTP again"):
                request_otp(email)

    with register_tab:
        name = st.text_input(
            "Full name",
            key="register_name",
        )

        email = st.text_input(
            "Email",
            key="register_email",
        )

        password = st.text_input(
            "Password",
            type="password",
            key="register_password",
        )

        role = st.selectbox(
            "Account type",
            ["EMPLOYEE", "STUDENT"],
            key="register_role",
        )

        if st.button(
            "Create account",
            type="primary",
            use_container_width=True,
        ):
            if not all([name, email, password]):
                st.warning("Complete all fields.")
            elif register(name, email, password, role):
                st.success(
                    "Account created. Please sign in."
                )


# ============================================================
# SIDEBAR
# ============================================================

def sidebar():
    role = current_role()

    with st.sidebar:
        st.markdown(
            """
            <div style="
                display:flex;
                align-items:center;
                gap:10px;
                padding:8px 4px 14px 4px;
            ">
                <div style="
                    width:36px;
                    height:36px;
                    border-radius:11px;
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    color:white;
                    font-size:20px;
                    background:linear-gradient(135deg,#533ee5,#8d5bff);
                ">✦</div>
                <div>
                    <div style="font-weight:800;">Enterprise AI</div>
                    <div style="font-size:11px;color:#6c687b;">
                        Knowledge & Document Intelligence
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="enterprise-card" style="padding:13px;">
                <div style="font-weight:700;">
                    {current_name()}
                </div>
                <div class="small-muted">
                    {current_email()}
                </div>
                <div style="margin-top:8px;">
                    {role_badge(role)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### Workspace")

        pages = [
            "Dashboard",
            "Documents",
            "AI Chat",
            "AI Guide",
            "History",
        ]

        if role in ("ADMIN", "SUPER_ADMIN"):
            pages.append("Admin Dashboard")

        selected = st.radio(
            "Navigation",
            pages,
            index=pages.index(
                st.session_state.page
            ) if st.session_state.page in pages else 0,
            label_visibility="collapsed",
        )

        st.session_state.page = selected

        st.divider()

        online = check_backend()

        if online:
            st.markdown(
                """
                <div class="status-pill">
                    <span class="online-dot"></span>
                    Backend online
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="status-pill">
                    <span class="offline-dot"></span>
                    Backend offline
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.caption(API_BASE_URL)

        if st.button(
            "Sign out",
            use_container_width=True,
        ):
            logout()


# ============================================================
# HEADER
# ============================================================

def top_header():
    col1, col2 = st.columns([6, 1])

    with col1:
        st.text_input(
            "Search",
            placeholder=(
                "Search documents, citations, insights..."
            ),
            label_visibility="collapsed",
        )

    with col2:
        st.markdown(
            f"""
            <div style="
                text-align:right;
                padding-top:9px;
            ">
                {role_badge(current_role())}
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# DASHBOARD
# ============================================================

def dashboard_page():
    docs = load_documents()

    ready = sum(
        1 for d in docs if is_ready(d)
    )
    processing = sum(
        1 for d in docs
        if document_status(d) == "PROCESSING"
    )
    failed = sum(
        1 for d in docs
        if document_status(d) == "FAILED"
    )

    st.markdown(
        f"""
        <div class="hero">
            <div style="position:relative;z-index:2;max-width:720px;">
                <div class="badge"
                     style="background:rgba(255,255,255,.15);color:white;">
                    ✦ KNOWLEDGE VECTOR ENGINE
                </div>
                <h1 style="font-size:34px;margin:15px 0 5px;">
                    Welcome back, {current_name()}
                </h1>
                <p style="font-size:16px;line-height:1.6;">
                    Upload documents, select your authorized knowledge
                    sources, ask questions and receive grounded answers
                    with citations.
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("###")

    c1, c2, c3, c4 = st.columns(4)

    metrics = [
        ("Documents", len(docs)),
        ("Ready", ready),
        ("Processing", processing),
        ("Failed", failed),
    ]

    for col, (label, value) in zip(
        [c1, c2, c3, c4],
        metrics,
    ):
        with col:
            st.markdown(
                f"""
                <div class="metric">
                    <div class="metric-value">{value}</div>
                    <div class="metric-label">{label}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("### Quick Actions")

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button(
            "📄 Upload documents",
            use_container_width=True,
        ):
            st.session_state.page = "Documents"
            st.rerun()

    with c2:
        if st.button(
            "💬 New AI query",
            use_container_width=True,
        ):
            st.session_state.page = "AI Chat"
            st.rerun()

    with c3:
        if st.button(
            "🧭 Open AI Guide",
            use_container_width=True,
        ):
            st.session_state.page = "AI Guide"
            st.rerun()

    st.markdown("### Recent Documents")

    if not docs:
        st.info(
            "No documents yet. Upload your first PDF."
        )
        return

    for doc in docs[:5]:
        st.markdown(
            f"""
            <div class="document-row">
                <div style="
                    display:flex;
                    justify-content:space-between;
                    align-items:center;
                    gap:12px;
                ">
                    <div>
                        <strong>📄 {document_name(doc)}</strong>
                        <div class="small-muted">
                            {doc.get("page_count", "—")} pages
                        </div>
                    </div>
                    {status_badge(document_status(doc))}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# DOCUMENTS
# ============================================================

def upload_documents(files) -> bool:
    if not files:
        return False

    multipart = [
        (
            "files",
            (
                file.name,
                file.getvalue(),
                "application/pdf",
            ),
        )
        for file in files
    ]

    response = api_post(
        ENDPOINTS["upload"],
        files=multipart,
    )

    if response is None:
        st.error(
            "Document service is offline."
        )
        return False

    if response.status_code not in (200, 201, 202):
        st.error(
            error_message(
                response,
                "Upload failed."
            )
        )
        return False

    return True


def documents_page():
    st.markdown(
        """
        <div class="enterprise-card">
            <div class="badge badge-uploaded">
                🔐 SECURE DOCUMENT INGESTION
            </div>
            <h1 class="section-title">Documents</h1>
            <p>
                Upload PDFs to build your searchable enterprise
                knowledge base. Multiple files are supported.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Ingest new documents")

    files = st.file_uploader(
        "Drop PDF files here",
        type=["pdf"],
        accept_multiple_files=True,
        help="Upload one or multiple PDF documents.",
    )

    if files:
        st.write(
            f"**{len(files)} file(s) selected**"
        )

        for file in files:
            st.caption(
                f"📄 {file.name} · "
                f"{file.size / 1024:.1f} KB"
            )

        if st.button(
            "🚀 Upload & Process",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner(
                "Uploading documents..."
            ):
                if upload_documents(files):
                    st.success(
                        "Upload accepted. Document processing has started."
                    )
                    st.session_state.page = "Documents"
                    time.sleep(.5)
                    st.rerun()

    st.markdown("---")
    st.markdown("### Your knowledge base")

    docs = load_documents(
        show_error=True
    )

    if not docs:
        st.info(
            "No documents available."
        )
        return

    ready = sum(
        1 for d in docs if is_ready(d)
    )
    processing = sum(
        1 for d in docs
        if document_status(d) == "PROCESSING"
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Total", len(docs))

    with c2:
        st.metric("Ready", ready)

    with c3:
        st.metric("Processing", processing)

    for doc in docs:
        did = document_id(doc)
        name = document_name(doc)
        status = document_status(doc)

        c1, c2, c3 = st.columns([5, 1.5, 1])

        with c1:
            st.markdown(
                f"""
                <div class="document-row">
                    <strong>📄 {name}</strong>
                    <div style="margin-top:6px;">
                        {status_badge(status)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c2:
            if status == "PROCESSING":
                st.caption(
                    "Indexing..."
                )
            elif status == "READY":
                st.caption(
                    f"{doc.get('chunk_count', '—')} chunks"
                )
            elif status == "FAILED":
                st.caption(
                    str(
                        doc.get(
                            "error_message",
                            "Processing failed"
                        )
                    )[:80]
                )

        with c3:
            if (
                did
                and status in ("READY", "FAILED")
                and current_role() in (
                    "ADMIN",
                    "SUPER_ADMIN",
                )
            ):
                if st.button(
                    "Delete",
                    key=f"delete_{did}",
                ):
                    response = api_delete(
                        f"{ENDPOINTS['documents']}/{did}"
                    )

                    if response is not None and response.status_code in (200, 204):
                        st.success("Deleted.")
                        st.rerun()
                    else:
                        st.error(
                            error_message(
                                response,
                                "Delete failed."
                            )
                        )

    if processing:
        st.info(
            "Some documents are still being indexed. "
            "They will become selectable in AI Chat once "
            "their status changes to READY."
        )

        if st.button(
            "↻ Refresh processing status",
            use_container_width=True,
        ):
            st.rerun()


# ============================================================
# DOCUMENT SELECTOR
# ============================================================

def document_selector() -> List[str]:
    docs = load_documents()

    ready_docs = [
        d for d in docs
        if is_ready(d) and document_id(d)
    ]

    processing_docs = [
        d for d in docs
        if document_status(d) == "PROCESSING"
    ]

    failed_docs = [
        d for d in docs
        if document_status(d) == "FAILED"
    ]

    if processing_docs:
        st.warning(
            f"{len(processing_docs)} document(s) are still processing."
        )

    if failed_docs:
        st.error(
            f"{len(failed_docs)} document(s) failed processing."
        )

    if not ready_docs:
        st.info(
            "No READY documents are available for AI search yet."
        )
        return []

    options = {
        document_name(d): document_id(d)
        for d in ready_docs
    }

    names = list(options.keys())

    st.markdown(
        "### Select knowledge sources"
    )

    selected_names = st.multiselect(
        "Only READY and authorized documents can be selected.",
        names,
        default=[
            name
            for name in names
            if options[name] in st.session_state.selected_documents
        ],
        key="document_multiselect",
    )

    selected_ids = [
        options[name]
        for name in selected_names
    ]

    st.session_state.selected_documents = selected_ids

    c1, c2 = st.columns(2)

    with c1:
        if st.button(
            "Select all READY",
            use_container_width=True,
        ):
            st.session_state.selected_documents = list(
                options.values()
            )
            st.rerun()

    with c2:
        if st.button(
            "Clear selection",
            use_container_width=True,
        ):
            st.session_state.selected_documents = []
            st.rerun()

    st.caption(
        f"{len(selected_ids)} of {len(ready_docs)} "
        "READY documents selected."
    )

    return selected_ids


# ============================================================
# CHAT
# ============================================================

def ask_chat(
    question: str,
    document_ids: List[str],
):
    start = time.perf_counter()

    response = api_post(
        ENDPOINTS["chat"],
        json_data={
            "question": question,
            "document_ids": document_ids,
        },
    )

    latency = time.perf_counter() - start
    st.session_state.last_latency = latency

    if response is None:
        return {
            "error": "Unable to connect to the AI backend."
        }

    if response.status_code != 200:
        return {
            "error": error_message(
                response,
                "The AI service could not process your question."
            )
        }

    data = parse_response(response)

    if not isinstance(data, dict):
        return {
            "error": "Invalid AI response."
        }

    return data


def render_sources(sources: Any):
    if not sources:
        return

    st.markdown(
        "**Sources**"
    )

    if not isinstance(sources, list):
        sources = [sources]

    for source in sources:
        if isinstance(source, dict):
            filename = (
                source.get("filename")
                or source.get("file_name")
                or source.get("document")
                or "Document"
            )

            page = (
                source.get("page_number")
                or source.get("page")
            )

            section = (
                source.get("section")
                or source.get("subsection")
            )

            details = f"📄 {filename}"

            if page:
                details += f" · Page {page}"

            if section:
                details += f" · {section}"

            st.markdown(
                f"""
                <div class="source-card">
                    {details}
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="source-card">
                    📄 {str(source)}
                </div>
                """,
                unsafe_allow_html=True,
            )


def chat_page():
    st.markdown(
        """
        <div class="enterprise-card">
            <div class="badge badge-ready">
                ✦ SEMANTIC KNOWLEDGE ENGINE
            </div>
            <h1 class="section-title">AI Document Chat</h1>
            <p>
                Ask complex questions and receive answers grounded
                in your selected and authorized document collection.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.last_latency is not None:
        st.caption(
            f"Last response: "
            f"{st.session_state.last_latency:.2f}s"
        )

    selected_ids = document_selector()

    if not selected_ids:
        return

    st.markdown("---")

    for message in st.session_state.messages:
        st.markdown(
            f"""
            <div class="chat-user">
                <strong>👤 You</strong><br>
                {message["question"]}
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="chat-ai">
                <strong>🤖 Enterprise AI</strong><br><br>
                {message["answer"]}
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_sources(
            message.get("sources")
        )

    question = st.chat_input(
        "Ask a question about your selected documents..."
    )

    if question:
        with st.spinner(
            "Searching authorized documents and generating an answer..."
        ):
            result = ask_chat(
                question,
                selected_ids,
            )

        if "error" in result:
            st.error(result["error"])
            return

        answer = (
            result.get("answer")
            or result.get("response")
            or result.get("message")
            or "No answer was returned."
        )

        sources = (
            result.get("sources")
            or result.get("citations")
            or []
        )

        st.session_state.messages.append(
            {
                "question": question,
                "answer": answer,
                "sources": sources,
                "document_ids": selected_ids,
                "timestamp": time.time(),
            }
        )

        st.session_state.history.append(
            {
                "question": question,
                "answer": answer,
                "sources": sources,
                "document_ids": selected_ids,
                "timestamp": time.time(),
            }
        )

        st.rerun()

    if st.session_state.messages:
        if st.button(
            "Reset chat",
            use_container_width=True,
        ):
            st.session_state.messages = []
            st.rerun()


# ============================================================
# AI GUIDE
# ============================================================

def ask_guide(
    request: str,
    document_ids: List[str],
):
    start = time.perf_counter()

    response = api_post(
        ENDPOINTS["guide"],
        json_data={
            "request": request,
            "question": request,
            "document_ids": document_ids,
        },
    )

    st.session_state.last_latency = (
        time.perf_counter() - start
    )

    if response is None:
        return {
            "error": "Unable to connect to the AI Guide backend."
        }

    if response.status_code != 200:
        return {
            "error": error_message(
                response,
                "AI Guide could not process your request."
            )
        }

    data = parse_response(response)

    return data if isinstance(data, dict) else {
        "error": "Invalid AI Guide response."
    }


def guide_page():
    st.markdown(
        """
        <div class="enterprise-card">
            <div class="badge badge-ready">
                ✦ AUTONOMOUS KNOWLEDGE GUIDE
            </div>
            <h1 class="section-title">AI Guide</h1>
            <p>
                Describe what you need to accomplish and the AI will
                create step-by-step guidance grounded in your
                authorized documents.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_ids = document_selector()

    if not selected_ids:
        return

    request = st.text_area(
        "What do you need help with?",
        placeholder=(
            "Example: Guide me through the employee onboarding "
            "process using the selected documents."
        ),
        height=130,
    )

    if st.button(
        "🧭 Generate Guide",
        type="primary",
        use_container_width=True,
    ):
        if not request.strip():
            st.warning(
                "Describe what you need help with."
            )
            return

        with st.spinner(
            "AI Guide is analyzing the selected documents..."
        ):
            result = ask_guide(
                request,
                selected_ids,
            )

        if "error" in result:
            st.error(result["error"])
            return

        answer = (
            result.get("answer")
            or result.get("guide")
            or result.get("response")
            or "No guidance was returned."
        )

        st.markdown("### 🧭 Guidance")

        st.markdown(
            f"""
            <div class="enterprise-card">
                {answer}
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_sources(
            result.get("sources")
            or result.get("citations")
            or []
        )


# ============================================================
# HISTORY
# ============================================================

def history_page():
    st.markdown(
        """
        <div class="enterprise-card">
            <div class="badge badge-uploaded">
                ◷ CONVERSATION HISTORY
            </div>
            <h1 class="section-title">History</h1>
            <p>
                Review questions and answers from this session.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.history:
        st.info(
            "No conversation history in this session."
        )
        return

    for index, item in enumerate(
        reversed(st.session_state.history),
        start=1,
    ):
        with st.expander(
            f"{index}. {item['question'][:90]}"
        ):
            st.markdown("**Question**")
            st.write(item["question"])

            st.markdown("**Answer**")
            st.write(item["answer"])

            render_sources(
                item.get("sources")
            )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

def admin_page():
    if current_role() not in (
        "ADMIN",
        "SUPER_ADMIN",
    ):
        st.error(
            "You are not authorized to access this page."
        )
        return

    docs = load_documents()

    ready = sum(
        1 for d in docs if is_ready(d)
    )
    processing = sum(
        1 for d in docs
        if document_status(d) == "PROCESSING"
    )
    failed = sum(
        1 for d in docs
        if document_status(d) == "FAILED"
    )

    st.markdown(
        """
        <div class="enterprise-card">
            <div class="badge badge-admin">
                ⚙ ADMIN CONTROL CENTER
            </div>
            <h1 class="section-title">
                Admin Dashboard
            </h1>
            <p>
                Monitor knowledge ingestion and system status.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)

    for col, label, value in [
        (c1, "Documents", len(docs)),
        (c2, "Ready", ready),
        (c3, "Processing", processing),
        (c4, "Failed", failed),
    ]:
        with col:
            st.metric(label, value)

    st.markdown("### System")

    if check_backend():
        st.success(
            f"FastAPI online · {API_BASE_URL}"
        )
    else:
        st.error(
            "FastAPI backend offline."
        )

    st.markdown("### Retrieval configuration")

    st.info(
        "The frontend sends selected document IDs to the backend. "
        "The backend should enforce authorization, perform hybrid "
        "retrieval, reranking, and source citation generation."
    )

    st.markdown(
        """
        **Recommended backend pipeline**

        Query → authorization → vector retrieval + BM25 →
        hybrid fusion → reranker → context → LLM → citations
        """
    )


# ============================================================
# MAIN
# ============================================================

def main():
    if not st.session_state.token:
        authentication_page()
        return

    sidebar()
    top_header()

    st.divider()

    page = st.session_state.page

    if page == "Dashboard":
        dashboard_page()

    elif page == "Documents":
        documents_page()

    elif page == "AI Chat":
        chat_page()

    elif page == "AI Guide":
        guide_page()

    elif page == "History":
        history_page()

    elif page == "Admin Dashboard":
        admin_page()


if __name__ == "__main__":
    main()
