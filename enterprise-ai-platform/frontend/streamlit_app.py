import base64
import html
import json
import os
from urllib.parse import urlsplit

import requests
import streamlit as st
import streamlit.components.v1 as components

API = os.getenv("API_BASE_URL", "").rstrip("/")
TIMEOUT = 30

st.set_page_config(page_title="Enterprise AI", page_icon="✨", layout="wide", initial_sidebar_state="expanded")

# ============================================================ STATE
DEFAULTS = {"token": None, "refresh_token": None, "user": None, "messages": [],
            "conversation_id": None, "otp_requested": False, "guide_result": None, "theme": "light"}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)

try:
        saved_theme = st.context.cookies.get("enterprise-ai-theme", "")
except Exception:
        saved_theme = ""
requested_theme = str(st.query_params.get("theme", saved_theme or st.session_state.theme)).lower()
if requested_theme in {"light", "dark"}:
        st.session_state.theme = requested_theme
components.html("""
<script>
try {
    const queryTheme = new URLSearchParams(window.parent.location.search).get("theme");
    const theme = queryTheme === "light" || queryTheme === "dark"
        ? queryTheme
        : window.parent.localStorage.getItem("enterprise-ai-theme");
    if (theme === "light" || theme === "dark") {
        window.parent.localStorage.setItem("enterprise-ai-theme", theme);
        window.parent.document.cookie = `enterprise-ai-theme=${theme}; path=/; max-age=31536000; SameSite=Lax`;
    }
} catch (_) {}
</script>
""", height=0)

PAGES = ["Dashboard", "Documents", "AI Chat", "AI Guide", "History"]
ADMIN_PAGE = "Admin"
ICONS_NAV = {"Dashboard": "▦", "Documents": "▤", "AI Chat": "💬", "AI Guide": "🧭", "History": "🕘", "Admin": "⚙️"}
st.session_state.setdefault("nav", PAGES[0])


def go(page):
    st.session_state.nav = page


# ============================================================ THEME
LIGHT = dict(bg="#f8f9fc", surface="#ffffff", surface2="#f5f6fa", border="#e5e7eb", ink="#202124",
            muted="#6b7280", primary="#635bff", primary_ink="#ffffff", chip="#eeebff", ok="#eaf7ee", ok_ink="#188038",
            warn="#fff4e5", warn_ink="#b06000", err="#fcebea", err_ink="#d93025", hero="linear-gradient(120deg,#f5f4ff,#eefbf8)")
DARK = dict(bg="#0b1020", surface="#111827", surface2="#172033", border="#263244", ink="#f8fafc",
           muted="#94a3b8", primary="#8b7cff", primary_ink="#ffffff", chip="#29235f", ok="#123524", ok_ink="#22c55e",
           warn="#332a12", warn_ink="#f59e0b", err="#3a1a1c", err_ink="#ef4444", hero="linear-gradient(120deg,#151d3b,#122a2a)")

T = DARK if st.session_state.theme == "dark" else LIGHT

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
:root{{--bg:{T['bg']};--surface:{T['surface']};--surface2:{T['surface2']};--border:{T['border']};--ink:{T['ink']};
 --muted:{T['muted']};--primary:{T['primary']};--pink:{T['primary_ink']};--chip:{T['chip']};
 --ok:{T['ok']};--ok-ink:{T['ok_ink']};--warn:{T['warn']};--warn-ink:{T['warn_ink']};--err:{T['err']};--err-ink:{T['err_ink']};--hero:{T['hero']}}}
html,body,[class*="css"],.stApp{{font-family:'Inter',sans-serif}}
.stApp{{background:var(--bg);color:var(--ink)}}
#MainMenu,footer,[data-testid="stToolbar"],[data-testid="stDecoration"]{{display:none!important}}
header[data-testid="stHeader"]{{background:transparent}}
.block-container{{padding-top:1.4rem;max-width:1180px}}
section[data-testid="stSidebar"]{{background:var(--surface);border-right:1px solid var(--border)}}
h1,h2,h3{{letter-spacing:-.02em;color:var(--ink)}}
p,span,div,label{{color:var(--ink)}}

.crumb{{display:flex;align-items:center;justify-content:space-between;padding:2px 2px 14px;border-bottom:1px solid var(--border);margin-bottom:18px}}
.crumb .path{{font-size:14px;color:var(--muted)}}.crumb .path b{{color:var(--ink);font-weight:700}}
.crumb .right{{display:flex;align-items:center;gap:10px}}
.connected{{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ok-ink);
 background:var(--ok);padding:4px 12px;border-radius:999px;font-weight:600}}
.dot{{width:6px;height:6px;border-radius:50%;background:var(--ok-ink)}}

.hero{{background:var(--hero);border:1px solid var(--border);border-radius:18px;padding:26px 28px;margin-bottom:18px}}
.hero h1{{font-size:30px;font-weight:800;margin:0 0 6px}}
.hero p{{color:var(--muted);font-size:14.5px;margin:0;max-width:640px}}

.metric{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px}}
.metric .ico{{width:36px;height:36px;border-radius:11px;background:var(--chip);color:var(--primary);
 display:flex;align-items:center;justify-content:center;font-size:17px;margin-bottom:12px}}
.metric .num{{font-size:26px;font-weight:800;line-height:1}}
.metric .lbl{{color:var(--muted);font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;margin-top:5px;font-weight:600}}

.gscard{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px;height:100%}}
.gscard .ico{{width:38px;height:38px;border-radius:11px;background:var(--chip);color:var(--primary);
 display:flex;align-items:center;justify-content:center;font-size:18px;margin-bottom:14px}}
.gscard .t{{font-weight:700;font-size:15.5px;margin-bottom:4px}}
.gscard .d{{color:var(--muted);font-size:13px;line-height:1.5}}

.doccard{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:15px 18px;
 margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;gap:12px}}
.doccard .left{{display:flex;align-items:center;gap:12px;min-width:0}}
.doccard .ico{{width:34px;height:34px;border-radius:9px;background:var(--chip);color:var(--primary);
 display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.doccard .name{{font-weight:600;font-size:14px;word-break:break-all}}
.doccard .meta{{color:var(--muted);font-size:12px;margin-top:1px}}

.pill{{display:inline-flex;align-items:center;gap:5px;padding:3px 11px;border-radius:999px;font-size:11.5px;font-weight:700;white-space:nowrap}}
.p-ready{{background:var(--ok);color:var(--ok-ink)}}
.p-proc{{background:var(--warn);color:var(--warn-ink)}}
.p-fail{{background:var(--err);color:var(--err-ink)}}
.p-other{{background:var(--chip);color:var(--muted)}}

.role{{display:inline-block;padding:2px 11px;border-radius:999px;font-size:11px;font-weight:700;background:var(--chip);color:var(--primary)}}
.sideprofile{{display:flex;gap:10px;align-items:center;padding:12px;border-radius:14px;background:var(--surface2);border:1px solid var(--border)}}
.sideavatar{{width:38px;height:38px;border-radius:50%;background:var(--primary);color:#fff;font-weight:800;font-size:15px;
 display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.brand{{font-size:17px;font-weight:800}}.brand span{{color:var(--muted);font-weight:500;font-size:11.5px;display:block;margin-top:1px}}

.empty{{text-align:center;color:var(--muted);border:1.5px dashed var(--border);border-radius:16px;padding:40px 20px;background:var(--surface2)}}
.empty b{{display:block;color:var(--ink);font-size:15.5px;margin-bottom:3px}}

.bubble-user{{background:var(--primary);color:#fff;border-radius:16px 16px 3px 16px;padding:12px 15px;
 max-width:80%;margin-left:auto;font-size:14.5px;line-height:1.5}}
.bubble-ai{{background:var(--surface);border:1px solid var(--border);border-radius:16px 16px 16px 3px;padding:15px;font-size:14.5px;line-height:1.55}}
.citebox{{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:10px 12px;margin-top:8px}}
.citecard{{background:var(--surface);border:1px solid var(--border);border-radius:9px;padding:8px 11px;margin-top:6px;
 display:flex;justify-content:space-between;align-items:center}}
.citecard .fn{{font-weight:600;font-size:12.5px}}
.citecard .pg{{font-size:10.5px;background:var(--chip);color:var(--primary);padding:2px 8px;border-radius:6px}}

.stButton>button,.stFormSubmitButton>button{{border-radius:10px;border:1px solid var(--border);
 background:var(--surface);color:var(--ink);font-weight:600;padding:.5rem 1rem;transition:.15s}}
.stButton>button:hover{{border-color:var(--primary);color:var(--primary)}}
.stButton>button[kind="primary"],.stButton>button[data-testid="stBaseButton-primary"]{{
 background:var(--primary);border:0;color:#fff}}
.stButton>button[kind="primary"]:hover,.stButton>button[data-testid="stBaseButton-primary"]:hover{{filter:brightness(1.08);color:#fff}}
.stTextInput input,.stTextArea textarea,div[data-baseweb="select"]>div{{background:var(--surface2)!important;
 border:1px solid var(--border)!important;border-radius:10px!important;color:var(--ink)!important}}
.stTextInput input:focus,.stTextArea textarea:focus{{border-color:var(--primary)!important;box-shadow:0 0 0 3px rgba(109,91,255,.15)!important}}
[data-testid="stVerticalBlockBorderWrapper"]{{border-radius:16px;border-color:var(--border);background:var(--surface)}}
[data-testid="stFileUploaderDropzone"]{{background:var(--surface2);border:1.5px dashed var(--border);border-radius:14px}}
.stTabs [data-baseweb="tab-list"]{{gap:4px}}.stTabs [data-baseweb="tab"]{{border-radius:8px;padding:7px 14px;color:var(--muted)}}
.stTabs [aria-selected="true"]{{background:var(--chip);color:var(--primary)!important}}
section[data-testid="stSidebar"] [role="radiogroup"] label{{padding:8px 11px;border-radius:10px;margin-bottom:2px}}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover{{background:var(--surface2)}}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){{background:var(--chip);color:var(--primary)}}
section[data-testid="stSidebar"] [role="radiogroup"] label>div:first-child{{display:none}}
.stCaption,[data-testid="stCaptionContainer"]{{color:var(--muted)!important}}
.msi{{font-family:'Material Symbols Outlined';font-weight:400;font-style:normal;font-size:20px;line-height:1;
 display:inline-block;vertical-align:middle;-webkit-font-feature-settings:'liga';font-feature-settings:'liga'}}
.metric .ico .msi,.gscard .ico .msi,.doccard .ico .msi{{font-size:21px}}
</style>
""", unsafe_allow_html=True)


def msi(name: str, fill: bool = False) -> str:
    class_name = "msi fill" if fill else "msi"
    return f'<span class="{class_name}">{html.escape(name)}</span>'


def theme_toggle(button_column=None):
    if button_column is None:
        _, button_column = st.columns([10, 1])
    icon = "🌙" if st.session_state.theme == "light" else "☀️"
    label = "Switch to dark mode" if st.session_state.theme == "light" else "Switch to light mode"
    if button_column.button(icon, key="theme_toggle", help=label):
        theme = "dark" if st.session_state.theme == "light" else "light"
        st.session_state.theme = theme
        st.query_params["theme"] = theme
        st.rerun()


# ============================================================ API
def call(method, path, **kw):
    api_base = API
    if not api_base:
        try:
            headers_context = st.context.headers
            request_host = urlsplit(f"//{headers_context.get('Host', '')}").hostname
            scheme = headers_context.get("X-Forwarded-Proto", "http").split(",")[0].strip()
            if request_host:
                formatted_host = f"[{request_host}]" if ":" in request_host else request_host
                api_base = f"{scheme}://{formatted_host}:8000"
        except Exception:
            api_base = ""
    if not api_base:
        return None
    headers = {"Accept": "application/json"}
    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        return requests.request(method, f"{api_base}{path}", headers=headers, timeout=TIMEOUT, **kw)
    except requests.RequestException:
        return None


def err(resp, default):
    try:
        body = resp.json()
        if body.get("detail"):
            return str(body["detail"])
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str):
            return error
        return default
    except Exception:
        return default


def backend_online():
    r = call("get", "/api/v1/health")
    return r is not None and r.status_code == 200


@st.fragment(run_every="15s")
def connection_status():
    online = backend_online()
    color = "#188038" if online else "#d93025"
    label = "Connected" if online else "Offline"
    st.markdown(
        f'<span class="connected"><span class="dot" style="background:{color}"></span>{label}</span>',
        unsafe_allow_html=True,
    )


def jwt_claims(token):
    try:
        p = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    except Exception:
        return {}


def start_session(data):
    st.session_state.token = data.get("access_token") or data.get("token")
    st.session_state.refresh_token = data.get("refresh_token")
    user = dict(data.get("user") or data.get("data") or {})
    if not (user.get("name") or user.get("full_name")):
        r = call("get", "/api/v1/auth/me")
        if r is not None and r.status_code == 200:
            try:
                user.update(r.json())
            except Exception:
                pass
    claims = jwt_claims(st.session_state.token or "")
    sub = str(claims.get("sub", ""))
    user["email"] = user.get("email") or claims.get("email") or (sub if "@" in sub else "")
    user["role"] = user.get("role") or claims.get("role") or "EMPLOYEE"
    user["name"] = (user.get("name") or user.get("full_name") or claims.get("name")
                    or (user["email"].split("@")[0].replace(".", " ").title() if user["email"] else "User"))
    st.session_state.user = user


def auth_request(path, payload, fail_msg):
    r = call("post", path, json=payload)
    if r is None:
        st.error("Authentication service is offline. Start the FastAPI backend and retry.")
        return None
    if r.status_code not in (200, 201):
        st.error(err(r, fail_msg))
        return None
    return r


def load_documents():
    documents = []
    page = 1
    while True:
        r = call("get", "/api/v1/documents", params={"page": page, "page_size": 100})
        if r is None or r.status_code != 200:
            return documents
        try:
            data = r.json()
            if isinstance(data, list):
                return data
            page_documents = data.get("documents", data.get("data", []))
            documents.extend(page_documents)
            if len(documents) >= int(data.get("total", len(documents))) or not page_documents:
                return documents
            page += 1
        except (ValueError, AttributeError, TypeError):
            return documents


def ask_ai(question, ids, conversation_id=None):
    payload = {"question": question, "document_ids": ids}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    r = call("post", "/api/v1/chat/ask", json=payload)
    if r is None:
        return None
    if r.status_code != 200:
        return {"error": err(r, "Unable to process the question.")}
    return r.json()


def ask_guide(message, ids):
    r = call("post", "/api/v1/chat/agent", json={
        "message": message,
        "document_ids": ids,
        "all_authorized": False,
    })
    if r is None:
        return {"error": "AI Guide could not connect to the backend."}
    if r.status_code != 200:
        return {"error": err(r, "Unable to generate guidance.")}
    return r.json()


def load_chat_stats():
    r = call("get", "/api/v1/chat/stats")
    if r is None or r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def load_conversations():
    conversations = []
    page = 1
    while True:
        r = call("get", "/api/v1/chat/conversations", params={"page": page, "page_size": 100})
        if r is None or r.status_code != 200:
            return conversations
        try:
            data = r.json()
            page_items = data.get("conversations", [])
            conversations.extend(page_items)
            if len(conversations) >= int(data.get("total", len(conversations))) or not page_items:
                return conversations
            page += 1
        except (ValueError, AttributeError, TypeError):
            return conversations


def load_conversation(conversation_id):
    r = call("get", f"/api/v1/chat/conversations/{conversation_id}")
    if r is None or r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def load_history_records():
    records = []
    for conversation in load_conversations():
        conversation_id = conversation.get("conversation_id")
        if conversation_id:
            detail = load_conversation(conversation_id)
            if detail:
                records.append(detail)
    return records


def did(d):
    return d.get("id") or d.get("document_id")


def status_of(d):
    return str(d.get("status", "UNKNOWN")).upper()


def answer_of(res):
    return res.get("answer") or res.get("response") or res.get("message") or "No answer returned."


def display_timestamp(value):
    return str(value).replace("T", " ").replace("Z", " UTC")[:19] if value else ""


# ============================================================ UI HELPERS
def crumb(page_label):
    u = st.session_state.user or {}
    title, email, status, theme = st.columns([5, 3, 1.4, 0.6], vertical_alignment="center")
    title.markdown(
        f'<div class="crumb"><div class="path"><b>Enterprise AI</b> / {html.escape(page_label)}</div></div>',
        unsafe_allow_html=True,
    )
    email.caption(html.escape(u.get("email", "")))
    with status:
        connection_status()
    theme_toggle(theme)


def hero(title, sub):
    st.markdown(f'<div class="hero"><h1>{html.escape(title)}</h1><p>{html.escape(sub)}</p></div>', unsafe_allow_html=True)


def metric(icon, value, label):
    return f'<div class="metric"><div class="ico">{msi(icon)}</div><div class="num">{value}</div><div class="lbl">{html.escape(str(label))}</div></div>'


def pill(status):
    m = {
        "READY": ("p-ready", "Ready"),
        "PROCESSING": ("p-proc", "Processing"),
        "UPLOADED": ("p-proc", "Processing"),
        "PENDING": ("p-proc", "Processing"),
        "FAILED": ("p-fail", "Failed"),
    }
    cls, label = m.get(status, ("p-other", status.title()))
    return f'<span class="pill {cls}">{label}</span>'


def empty(title, text):
    st.markdown(f'<div class="empty"><b>{title}</b>{text}</div>', unsafe_allow_html=True)


def show_sources(sources):
    if not sources:
        return
    with st.expander(f"📚 Sources used ({len(sources)})"):
        for source in sources:
            if not isinstance(source, dict):
                st.write(str(source))
                continue
            with st.container(border=True):
                filename = html.escape(str(source.get("filename", "Document")))
                page = source.get("page") or source.get("page_number")
                section = source.get("section") or source.get("subsection")
                st.markdown(f"**📄 {filename}**" + (f" · Page {page}" if page else ""))
                if section:
                    st.caption(str(section))
                if source.get("excerpt"):
                    st.write(f"“{source['excerpt']}”")
                for field, label in (("vector_score", "Vector"), ("hybrid_score", "Hybrid"), ("rerank_score", "Rerank")):
                    if source.get(field) is not None:
                        st.caption(f"{label} score: {float(source[field]):.3f}")


# ============================================================ AUTH
def auth_page():
    theme_toggle()
    online = backend_online()
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown(f"""
                <div style="background:radial-gradient(circle at 18% 25%,rgba(109,91,255,.22),transparent 45%),radial-gradient(circle at 80% 75%,rgba(0,194,168,.12),transparent 40%),#0d1226;border:1px solid #263244;border-radius:20px;padding:40px 34px;height:100%;color:#fff">
          <div style="display:flex;align-items:center;gap:8px;font-weight:800;font-size:18px;margin-bottom:26px">
                        <span style="display:inline-flex;width:38px;height:38px;align-items:center;justify-content:center;border-radius:11px;background:linear-gradient(135deg,#6d5bff,#00c2a8);font-size:20px">✦</span> Enterprise AI</div>
          <span style="display:inline-block;background:rgba(109,91,255,.25);color:#c7c1ff;font-size:11.5px;font-weight:700;
            padding:5px 12px;border-radius:999px;margin-bottom:18px">● AI KNOWLEDGE WORKSPACE</span>
                    <h1 style="font-size:42px;font-weight:800;line-height:1.12;margin:0 0 16px;color:#fff">
                        Turn your document library into an expert <span style="color:#65fade">that never sleeps.</span></h1>
          <p style="color:#b7b9c9;font-size:15.5px;max-width:480px;margin-bottom:26px">Upload your policies, handbooks
            and reports. Ask a question and get a sourced answer, with access limited to what you are allowed to see.</p>
          <div style="display:flex;gap:12px;margin:16px 0"><div style="font-size:18px">🔒</div>
            <div><b style="color:#fff">Role-based access</b><div style="color:#9295ad;font-size:13.5px">Every answer respects permissions and security classifications.</div></div></div>
          <div style="display:flex;gap:12px;margin:16px 0"><div style="font-size:18px">📖</div>
            <div><b style="color:#fff">Cited answers</b><div style="color:#9295ad;font-size:13.5px">See the source file, section, and page behind each response.</div></div></div>
          <div style="display:flex;gap:12px;margin:16px 0 26px"><div style="font-size:18px">⚡</div>
            <div><b style="color:#fff">Ready in minutes</b><div style="color:#9295ad;font-size:13.5px">Index PDFs and start asking with grounded answers.</div></div></div>
          <div style="color:{'#4ade80' if online else '#ff8a8a'};font-size:13px;font-weight:600">
            ● {"Backend online" if online else "Backend offline"}</div>
        </div>""", unsafe_allow_html=True)
        if not online:
            st.code("uvicorn app.main:app --reload", language="powershell")

    with right:
        with st.container(border=True):
            st.markdown("### Welcome back")
            st.caption("Sign in to your workspace")
            t_pw, t_otp, t_reg = st.tabs(["Password", "Email code", "Register"])

            with t_pw:
                email = st.text_input("Email", key="login_email", placeholder="you@company.com")
                pw = st.text_input("Password", type="password", key="login_password")
                if st.button("Sign in", type="primary", use_container_width=True):
                    if not email or not pw:
                        st.warning("Enter your email and password.")
                    else:
                        r = auth_request("/api/v1/auth/login", {"email": email, "password": pw}, "Invalid email or password.")
                        if r is not None:
                            start_session(r.json())
                            st.rerun()

            with t_otp:
                email = st.text_input("Email", key="otp_email")
                if not st.session_state.otp_requested:
                    if st.button("Send code", use_container_width=True):
                        if not email:
                            st.warning("Enter your email.")
                        elif auth_request("/api/v1/auth/request-otp", {"email": email}, "Unable to send the code."):
                            st.session_state.otp_requested = True
                            st.rerun()
                else:
                    st.success("Code sent. Check your inbox.")
                    otp = st.text_input("6-digit code", max_chars=6, key="otp_value")
                    if st.button("Verify and sign in", type="primary", use_container_width=True):
                        r = auth_request("/api/v1/auth/verify-otp", {"email": email, "otp": otp}, "Invalid or expired code.")
                        if r is not None:
                            st.session_state.otp_requested = False
                            start_session(r.json())
                            st.rerun()
                    if st.button("Send a new code"):
                        auth_request("/api/v1/auth/request-otp", {"email": email}, "Unable to send the code.")

            with t_reg:
                name = st.text_input("Full name", key="register_name")
                email = st.text_input("Email", key="register_email")
                pw = st.text_input("Password", type="password", key="register_password")
                role = st.selectbox("Account type", ["EMPLOYEE", "STUDENT"])
                if st.button("Create account", type="primary", use_container_width=True):
                    if not (name and email and pw):
                        st.warning("Complete all fields.")
                    elif auth_request("/api/v1/auth/register",
                                      {"name": name, "email": email, "password": pw, "role": role}, "Registration failed."):
                        st.success("Account created. Switch to the Password tab to sign in.")


# ============================================================ SIDEBAR
def sidebar():
    u = st.session_state.user or {}
    role = str(u.get("role", "EMPLOYEE")).upper()
    is_admin = role in ("ADMIN", "SUPER_ADMIN")
    with st.sidebar:
        st.markdown('<div class="brand">✨ Enterprise AI<span>Knowledge &amp; Document Intelligence</span></div>', unsafe_allow_html=True)
        st.write("")
        st.markdown(f"""<div class="sideprofile"><div class="sideavatar">{html.escape(u.get('name', 'U')[:1].upper())}</div>
            <div style="min-width:0"><b style="font-size:13.5px">{html.escape(u.get('name', 'User'))}</b>
            <div style="color:var(--muted);font-size:11.5px;overflow:hidden;text-overflow:ellipsis">{html.escape(u.get('email', ''))}</div>
            <span class="role" style="margin-top:5px">{role.title()}</span></div></div>""", unsafe_allow_html=True)
        st.write("")
        options = PAGES + ([ADMIN_PAGE] if is_admin else [])
        labels = [f"{ICONS_NAV[p]}  {p}" for p in options]
        picked = st.radio("Navigation", labels, index=options.index(st.session_state.nav)
                          if st.session_state.nav in options else 0, label_visibility="collapsed")
        st.session_state.nav = options[labels.index(picked)]
        st.divider()
        if st.button("↩ Sign out", use_container_width=True):
            if st.session_state.refresh_token:
                call("post", "/api/v1/auth/logout", json={"refresh_token": st.session_state.refresh_token})
            theme = st.session_state.theme
            st.session_state.clear()
            st.session_state.theme = theme
            st.rerun()


# ============================================================ PAGES
def dashboard_page():
    crumb("Dashboard")
    u = st.session_state.user or {}
    first = str(u.get("name", "there")).split()[0]
    hero(f"Welcome back, {first}", "Upload documents, ask questions and get answers with sources — all in one secure workspace.")

    docs = load_documents()
    ready = sum(status_of(d) == "READY" for d in docs)
    busy = sum(status_of(d) in {"UPLOADED", "PROCESSING", "PENDING"} for d in docs)
    chat_stats = load_chat_stats()
    questions = chat_stats.get("questions_asked", "—") if chat_stats else "—"
    cols = st.columns(4)
    data = [("description", len(docs), "Documents"), ("verified", ready, "Ready to query"),
            ("sync", busy, "Processing"), ("forum", questions, "Questions asked")]
    for col, (i, v, l) in zip(cols, data):
        col.markdown(metric(i, v, l), unsafe_allow_html=True)

    st.write("")
    st.markdown("##### Get started")
    cards = [("cloud_upload", "Upload documents", "Add PDFs and we index them page by page for search.", "Go to Documents", "Documents"),
            ("chat", "Ask your documents", "Get direct answers with page-level citations.", "Open AI Chat", "AI Chat"),
            ("explore", "Get guided", "Walk through processes and policies step by step.", "Open AI Guide", "AI Guide")]
    for col, (icon, t, d, btn, page) in zip(st.columns(3), cards):
        with col:
            st.markdown(f'<div class="gscard"><div class="ico">{msi(icon)}</div><div class="t">{html.escape(t)}</div><div class="d">{html.escape(d)}</div></div>',
                       unsafe_allow_html=True)
            st.write("")
            st.button(btn, key=f"qa_{page}", use_container_width=True, on_click=go, args=(page,))

    if docs:
        st.write("")
        st.markdown("##### Recent documents")
        for d in docs[:4]:
            metadata = []
            if d.get("file_size") is not None:
                metadata.append(f"{d['file_size'] / (1024 * 1024):.1f} MB")
            if d.get("page_count") is not None:
                metadata.append(f"{d['page_count']} pages")
            if d.get("chunk_count") is not None:
                metadata.append(f"{d['chunk_count']} chunks")
            if d.get("created_at"):
                metadata.append(display_timestamp(d["created_at"]))
            st.markdown(f'<div class="doccard"><div class="left"><div class="ico">{msi("picture_as_pdf")}</div>'
                        f'<div><div class="name">{html.escape(d.get("filename", "Document"))}</div>'
                        f'<div class="meta">{html.escape(" · ".join(metadata))}</div></div></div>{pill(status_of(d))}</div>',
                        unsafe_allow_html=True)


@st.fragment(run_every="3s")
def document_list():
    docs = load_documents()
    st.markdown("##### Your documents")
    if not docs:
        empty("No documents yet", "Upload your first PDF above to get started.")
        return
    for d in docs:
        status = status_of(d)
        name = html.escape(d.get("filename", "Unknown document"))
        details = []
        if d.get("file_size") is not None:
            details.append(f"{d['file_size'] / (1024 * 1024):.1f} MB")
        if d.get("page_count") is not None:
            details.append(f"{d['page_count']} pages")
        if d.get("chunk_count") is not None:
            details.append(f"{d['chunk_count']} chunks")
        if d.get("classification"):
            details.append(str(d["classification"]).title())
        if d.get("owner_id"):
            user_id = (st.session_state.user or {}).get("user_id")
            details.append("Owner: you" if d["owner_id"] == user_id else f"Owner: {str(d['owner_id'])[:8]}")
        if d.get("created_at"):
            details.append(f"Uploaded {display_timestamp(d['created_at'])}")
        meta = " · ".join(details)
        errmsg = (f'<div class="meta" style="color:var(--err-ink)">{html.escape(str(d.get("error_message")))}</div>'
                 if status == "FAILED" and d.get("error_message") else "")
        c1, ask_col, delete_col = st.columns([8, 1, 1], vertical_alignment="center")
        with c1:
            st.markdown(f'''<div class="doccard"><div class="left"><div class="ico">{msi("picture_as_pdf")}</div>
                <div><div class="name">{name}</div><div class="meta">{meta}</div>{errmsg}</div>
                </div>{pill(status)}</div>''', unsafe_allow_html=True)
        document_id = did(d)
        if document_id and ask_col.button("Ask", key=f"ask-document-{document_id}", help="Ask about this document"):
            st.session_state.chat_docs = [document_id]
            st.session_state[f"document-scope-{document_id}"] = True
            st.session_state.nav = "AI Chat"
            st.rerun()
        if document_id and delete_col.button("🗑", key=f"delete-document-{document_id}", help="Delete document"):
            response = call("delete", f"/api/v1/documents/{document_id}")
            if response is not None and response.status_code in (200, 204):
                st.rerun()
            else:
                st.error(err(response, "You are not authorized to delete this document.") if response else "Document service is offline.")


def documents_page():
    crumb("Documents")
    hero("Documents", "Upload PDFs to build your searchable knowledge base. Text is extracted per page so answers can cite their source.")
    files = st.file_uploader(
        "Drag and drop PDF files here, or browse",
        type=["pdf"],
        accept_multiple_files=True,
        key="document-upload",
    )
    st.caption("Multiple files welcome. Files are parsed page by page and indexed for search.")
    removed = st.session_state.setdefault("removed_uploads", set())
    selected_files = [file for file in (files or []) if file.name not in removed]
    for index, file in enumerate(selected_files):
        file_col, remove_col = st.columns([9, 1], vertical_alignment="center")
        file_col.markdown(
            f'<div class="doccard"><div class="left"><div class="ico">{msi("picture_as_pdf")}</div>'
            f'<div><div class="name">{html.escape(file.name)}</div>'
            f'<div class="meta">{file.size / 1024:.0f} KB · PDF</div></div></div></div>',
            unsafe_allow_html=True,
        )
        if remove_col.button("Remove", key=f"remove-upload-{index}", help=f"Remove {file.name}"):
            removed.add(file.name)
            st.rerun()
    if selected_files and st.button("Upload & Index", key="upload-index", type="primary", use_container_width=True):
        progress = st.progress(0, text="Preparing uploads")
        accepted = 0
        failures = []
        for index, file in enumerate(selected_files, 1):
            progress.progress((index - 1) / len(selected_files), text=f"Uploading {index} of {len(selected_files)}")
            response = call(
                "post",
                "/api/v1/documents",
                files={"file": (file.name, file.getvalue(), "application/pdf")},
            )
            if response is not None and response.status_code in (200, 201, 202):
                accepted += 1
            else:
                failure = err(response, "Upload failed.") if response else "Document service is offline."
                failures.append((file.name, failure))
        progress.progress(1.0, text="Upload requests complete")
        st.session_state.removed_uploads = set()
        for filename, message in failures:
            st.error(f"{filename}: {message}")
        if accepted:
            st.toast(f"{accepted} document(s) accepted for indexing", icon="✅")
            st.rerun()
    document_list()


def chat_page():
    crumb("AI Chat")
    docs = load_documents()
    if not docs:
        st.markdown("### AI Document Chat")
        empty("Nothing to search yet", "Upload at least one PDF, then come back to ask questions.")
        return
    ready = {did(d): d for d in docs if status_of(d) == "READY" and did(d)}
    if not ready:
        st.warning("Your documents are still processing or have failed. Ready documents will appear here.")
        return
    st.session_state.setdefault("chat_docs", list(ready))
    st.session_state.chat_docs = [doc_id for doc_id in st.session_state.chat_docs if doc_id in ready]

    left, right = st.columns([4, 8], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### Search in")
            st.caption(f"{len(st.session_state.chat_docs)} of {len(ready)} ready documents selected")
            c1, c2 = st.columns(2)
            if c1.button("Select all", key="select-all-documents", use_container_width=True):
                st.session_state.chat_docs = list(ready)
                for doc_id in ready:
                    st.session_state[f"document-scope-{doc_id}"] = True
                st.rerun()
            if c2.button("Clear", key="clear-documents", use_container_width=True):
                st.session_state.chat_docs = []
                for doc_id in ready:
                    st.session_state[f"document-scope-{doc_id}"] = False
                st.rerun()
            for doc_id, document in ready.items():
                checkbox_key = f"document-scope-{doc_id}"
                st.session_state.setdefault(checkbox_key, doc_id in st.session_state.chat_docs)
                st.checkbox(document.get("filename", "Document"), key=checkbox_key)
            selected = [
                doc_id for doc_id in ready
                if st.session_state.get(f"document-scope-{doc_id}", False)
            ]
            st.session_state.chat_docs = selected

    with right:
        st.markdown("### AI Document Chat")
        selected_names = [ready[doc_id].get("filename", "Document") for doc_id in selected]
        st.caption("Answers are grounded in the selected documents and cite file + page.")
        if selected_names:
            st.markdown("**Searching in:** " + " · ".join(html.escape(name) for name in selected_names))
        else:
            st.warning("Select at least one ready document to start searching.")
        top_actions, _ = st.columns([2, 8])
        if top_actions.button("New conversation", key="new-conversation"):
            st.session_state.conversation_id = None
            st.session_state.messages = []
            st.rerun()
        if not st.session_state.messages:
            empty("Ask your first question", "Your answer will be grounded only in the selected documents.")
        for message in st.session_state.messages:
            with st.chat_message("user"):
                st.write(message["question"])
            with st.chat_message("assistant", avatar="✦"):
                st.markdown(message["answer"])
                show_sources(message.get("citations", []))

        question = st.chat_input("Ask a question about your documents...", key="chat-input")
        if question:
            if not selected:
                st.warning("Select at least one document.")
                return
            with st.spinner("Searching the selected documents..."):
                response = ask_ai(question, selected, st.session_state.conversation_id)
            if response is None:
                st.error("The AI service is offline. Your question has not been sent.")
            elif "error" in response:
                st.error(response["error"])
            else:
                st.session_state.conversation_id = response.get("conversation_id")
                answer = answer_of(response)
                if not response.get("has_answer", True):
                    answer = "I couldn't find a sufficiently relevant answer in the selected documents."
                st.session_state.messages.append({
                    "question": question,
                    "answer": answer,
                    "citations": response.get("citations", []),
                })
                st.rerun()


def guide_page():
    crumb("AI Guide")
    hero("AI Guide", "Describe what you need to do and receive guidance grounded in your authorized documents.")
    ideas = [
        "Guide me through employee onboarding",
        "How do I request leave?",
        "Summarize our security policy",
    ]
    for index, (column, prompt) in enumerate(zip(st.columns(3), ideas)):
        if column.button(prompt, key=f"guide-preset-{index}", use_container_width=True):
            st.session_state.guide_q = prompt
    question = st.text_area(
        "Describe your task or scenario",
        key="guide_q",
        height=120,
        placeholder="What process or policy do you need help with?",
    )
    if st.button("Get guidance", key="get-guidance", type="primary", use_container_width=True):
        if not question.strip():
            st.warning("Tell the AI what you need help with.")
            return
        documents = load_documents()
        ready_ids = [did(doc) for doc in documents if status_of(doc) == "READY" and did(doc)]
        if not ready_ids:
            st.warning("No ready documents are available to guide you yet.")
            return
        with st.spinner("Searching authorized documents for guidance..."):
            result = ask_guide(question, ready_ids)
        if "error" in result:
            st.error(result["error"])
        else:
            st.session_state.guide_result = result
    result = st.session_state.guide_result
    if result:
        with st.container(border=True):
            st.markdown("### Guidance")
            st.markdown(result.get("reply", "No guidance returned."))
            pending = result.get("pending_confirmation")
            if pending:
                st.info("This request requires confirmation before the backend can perform the action.")
            citations = []
            for tool_call in result.get("tool_calls", []):
                tool_result = tool_call.get("result")
                if isinstance(tool_result, dict):
                    citations.extend(tool_result.get("citations", []))
            show_sources(citations)


def history_page():
    crumb("History")
    hero("Conversation history", "Everything you have asked, with the sources behind each answer.")
    conversations = load_history_records()
    if not conversations:
        empty("No conversations yet", "Your saved questions and answers will appear here.")
        return
    for conversation in conversations:
        title = conversation.get("title") or "Untitled conversation"
        updated = display_timestamp(conversation.get("updated_at") or conversation.get("created_at"))
        with st.expander(f"{title} · {updated}"):
            for message in conversation.get("messages", []):
                if message.get("role") == "user":
                    st.markdown("**Question**")
                    st.write(message.get("content", ""))
                elif message.get("role") == "assistant":
                    st.markdown("**Answer**")
                    st.markdown(message.get("content", ""))
                    show_sources(message.get("citations") or [])


def admin_page():
    if str((st.session_state.user or {}).get("role", "")).upper() not in ("ADMIN", "SUPER_ADMIN"):
        st.error("You are not authorized to access the Admin Dashboard.")
        return
    crumb("Admin")
    hero("Admin dashboard", "Monitor ingestion, system health, and searchable knowledge-base coverage.")
    stats_response = call("get", "/api/v1/admin/dashboard")
    health_response = call("get", "/api/v1/admin/health")
    if stats_response is None or stats_response.status_code != 200:
        st.error(err(stats_response, "Admin statistics are unavailable.") if stats_response else "Backend offline. Retry when the service is available.")
        return
    stats = stats_response.json()
    metrics = [
        ("description", stats.get("total_documents", 0), "Documents"),
        ("verified", stats.get("ready_documents", 0), "Ready"),
        ("sync", stats.get("processing_documents", 0), "Processing"),
        ("warning", stats.get("failed_documents", 0), "Failed"),
    ]
    for column, (icon, value, label) in zip(st.columns(4), metrics):
        column.markdown(metric(icon, value, label), unsafe_allow_html=True)

    st.markdown("##### Knowledge base")
    knowledge = [
        ("menu_book", stats.get("total_pages", 0), "Pages"),
        ("view_agenda", stats.get("total_chunks", 0), "Chunks"),
        ("database", stats.get("searchable_documents", 0), "Searchable documents"),
    ]
    for column, (icon, value, label) in zip(st.columns(3), knowledge):
        column.markdown(metric(icon, value, label), unsafe_allow_html=True)

    st.markdown("##### System health")
    if health_response is None or health_response.status_code != 200:
        st.warning(err(health_response, "System health details are unavailable.") if health_response else "System health details are unavailable.")
    else:
        health = health_response.json()
        health_items = [
            ("Backend", health.get("status", "unknown")),
            ("Database", health.get("database", "unknown")),
            ("Vector store", health.get("vector_store", "unknown")),
            ("AI model", health.get("llm", "unknown")),
        ]
        with st.container(border=True):
            for column, (label, value) in zip(st.columns(4), health_items):
                column.caption(label)
                column.markdown(f"**{str(value).replace('_', ' ').title()}**")

    st.markdown("##### Knowledge documents")
    documents = []
    total_documents = 0
    page = 1
    inventory_complete = True
    while True:
        response = call("get", "/api/v1/admin/documents", params={"page": page, "page_size": 100})
        if response is None or response.status_code != 200:
            if page == 1:
                st.error(err(response, "Document inventory is unavailable.") if response else "Document inventory is unavailable.")
                return
            inventory_complete = False
            break
        try:
            data = response.json()
        except ValueError:
            inventory_complete = False
            break
        page_documents = data.get("documents", [])
        documents.extend(page_documents)
        total_documents = int(data.get("total", len(documents)))
        if len(documents) >= total_documents or not page_documents:
            break
        page += 1
    st.caption(f"Showing {len(documents)} of {total_documents} documents")
    if not inventory_complete:
        st.warning("Some pages of the document inventory could not be loaded.")
    headings = st.columns([3, 2, 0.7, 0.7, 1, 1.3, 0.8])
    for column, label in zip(headings, ["Document", "Owner", "Pages", "Chunks", "Status", "Uploaded", ""]):
        column.caption(label)
    for document in documents:
        row = st.columns([3, 2, 0.7, 0.7, 1, 1.3, 0.8], vertical_alignment="center")
        row[0].write(document.get("filename", "Document"))
        row[1].caption(f"{document.get('owner_name', '')}\n{document.get('owner_email', '')}")
        row[2].write(document.get("page_count") if document.get("page_count") is not None else "")
        row[3].write(document.get("chunk_count") if document.get("chunk_count") is not None else "")
        row[4].markdown(pill(status_of(document)), unsafe_allow_html=True)
        row[5].caption(display_timestamp(document.get("created_at")))
        document_id = document.get("document_id")
        if document_id and row[6].button("Delete", key=f"admin-delete-{document_id}"):
            delete_response = call("delete", f"/api/v1/documents/{document_id}")
            if delete_response is not None and delete_response.status_code in (200, 204):
                st.rerun()
            st.error(err(delete_response, "Unable to delete document.") if delete_response else "Document service is offline.")


# ============================================================ MAIN
def main():
    if not st.session_state.token:
        auth_page()
        return
    sidebar()
    {"Dashboard": dashboard_page, "Documents": documents_page, "AI Chat": chat_page,
     "AI Guide": guide_page, "History": history_page, ADMIN_PAGE: admin_page}.get(st.session_state.nav, dashboard_page)()


if __name__ == "__main__":
    main()