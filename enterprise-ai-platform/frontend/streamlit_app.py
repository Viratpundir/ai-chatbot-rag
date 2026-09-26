import base64
import html
import json
import os
from urllib.parse import urlsplit

import requests
import streamlit as st

API = os.getenv("API_BASE_URL", "").rstrip("/")
TIMEOUT = 30

st.set_page_config(page_title="Enterprise AI", page_icon="✨", layout="wide", initial_sidebar_state="expanded")

# ============================================================ STATE
DEFAULTS = {"token": None, "user": None, "messages": [], "otp_requested": False, "guide_result": None, "theme": "light"}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)

PAGES = ["Dashboard", "Documents", "AI Chat", "AI Guide", "History"]
ADMIN_PAGE = "Admin"
ICONS_NAV = {"Dashboard": "▦", "Documents": "▤", "AI Chat": "💬", "AI Guide": "🧭", "History": "🕘", "Admin": "⚙️"}
st.session_state.setdefault("nav", PAGES[0])


def go(page):
    st.session_state.nav = page


# ============================================================ THEME
LIGHT = dict(bg="#faf6f0", surface="#fffdfa", surface2="#f6f1ea", border="#ece4d8", ink="#211c14",
            muted="#8a7f6e", primary="#6d5bff", primary_ink="#ffffff", chip="#f1ecff", ok="#eaf6ec", ok_ink="#1a9a52",
            warn="#fdf3e3", warn_ink="#b37700", err="#fbeae8", err_ink="#d1373f", hero="linear-gradient(120deg,#f3efff,#f2f7ef)")
DARK = dict(bg="#0e0f17", surface="#161826", surface2="#12141f", border="#272a3a", ink="#f2f2f8",
           muted="#9298b0", primary="#8677ff", primary_ink="#ffffff", chip="#232544", ok="#123524", ok_ink="#4ade80",
           warn="#332a12", warn_ink="#ffc966", err="#3a1a1c", err_ink="#ff8a8a", hero="linear-gradient(120deg,#1c1a35,#122a2a)")

T = DARK if st.session_state.theme == "dark" else LIGHT

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
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
</style>
""", unsafe_allow_html=True)


def theme_toggle():
    c1, c2 = st.columns([10, 1])
    with c2:
        icon = "🌙" if st.session_state.theme == "light" else "☀️"
        if st.button(icon, key="theme_toggle", help="Switch theme"):
            st.session_state.theme = "dark" if st.session_state.theme == "light" else "light"
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
        return str(resp.json().get("detail", default))
    except Exception:
        return default


def backend_online():
    r = call("get", "/api/v1/health")
    return r is not None and r.status_code == 200


def jwt_claims(token):
    try:
        p = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    except Exception:
        return {}


def start_session(data):
    st.session_state.token = data.get("access_token") or data.get("token")
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
    r = call("get", "/api/v1/documents")
    if r is None or r.status_code != 200:
        return []
    try:
        d = r.json()
        return d if isinstance(d, list) else d.get("documents", d.get("data", []))
    except Exception:
        return []


def ask_ai(question, ids):
    r = call("post", "/api/v1/chat/ask", json={"question": question, "document_ids": ids})
    if r is None:
        return None
    if r.status_code != 200:
        return {"error": err(r, "Unable to process the question.")}
    return r.json()


def did(d):
    return d.get("id") or d.get("document_id")


def status_of(d):
    return str(d.get("status", "UNKNOWN")).upper()


def answer_of(res):
    return res.get("answer") or res.get("response") or res.get("message") or "No answer returned."


# ============================================================ UI HELPERS
def crumb(page_label):
    u = st.session_state.user or {}
    online = backend_online()
    st.markdown(f'''<div class="crumb"><div class="path"><b>Enterprise AI</b> / {html.escape(page_label)}</div>
        <div class="right"><span style="color:var(--muted);font-size:13px">{html.escape(u.get("email", ""))}</span>
        <span class="connected"><span class="dot"></span>{"Connected" if online else "Offline"}</span></div></div>''',
               unsafe_allow_html=True)
    theme_toggle()


def hero(title, sub):
    st.markdown(f'<div class="hero"><h1>{html.escape(title)}</h1><p>{html.escape(sub)}</p></div>', unsafe_allow_html=True)


def metric(icon, value, label):
    return f'<div class="metric"><div class="ico">{icon}</div><div class="num">{value}</div><div class="lbl">{label}</div></div>'


def pill(status):
    m = {"READY": ("p-ready", "Ready"), "PROCESSING": ("p-proc", "Processing"), "FAILED": ("p-fail", "Failed")}
    cls, label = m.get(status, ("p-other", status.title()))
    return f'<span class="pill {cls}">{label}</span>'


def empty(title, text):
    st.markdown(f'<div class="empty"><b>{title}</b>{text}</div>', unsafe_allow_html=True)


def show_sources(sources):
    if not sources:
        return
    rows = ""
    for s in sources:
        if isinstance(s, dict):
            fn, pg = html.escape(s.get("filename", "Document")), s.get("page_number")
            pg_html = f'<span class="pg">Page {pg}</span>' if pg else ""
        else:
            fn, pg_html = html.escape(str(s)), ""
        rows += f'<div class="citecard"><span class="fn">📄 {fn}</span>{pg_html}</div>'
    st.markdown(f'<div class="citebox"><b style="font-size:12.5px">📚 {len(sources)} source(s) used</b>{rows}</div>',
               unsafe_allow_html=True)


# ============================================================ AUTH
def auth_page():
    theme_toggle()
    online = backend_online()
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown(f"""
        <div style="background:#17141a;border-radius:20px;padding:40px 34px;height:100%;color:#fff">
          <div style="display:flex;align-items:center;gap:8px;font-weight:800;font-size:18px;margin-bottom:26px">
            ✨ Enterprise AI</div>
          <span style="display:inline-block;background:rgba(109,91,255,.25);color:#c7c1ff;font-size:11.5px;font-weight:700;
            padding:5px 12px;border-radius:999px;margin-bottom:18px">● AI KNOWLEDGE WORKSPACE</span>
          <h1 style="font-size:42px;font-weight:800;line-height:1.12;margin:0 0 16px;color:#fff">
            Answers from your company's documents, in seconds.</h1>
          <p style="color:#b7b9c9;font-size:15.5px;max-width:480px;margin-bottom:26px">Upload your policies, handbooks
            and reports. Ask a question and get a sourced answer, with access limited to what you are allowed to see.</p>
          <div style="display:flex;gap:12px;margin:16px 0"><div style="font-size:18px">🔒</div>
            <div><b style="color:#fff">Role-based access</b><div style="color:#9295ad;font-size:13.5px">Every answer respects document permissions.</div></div></div>
          <div style="display:flex;gap:12px;margin:16px 0"><div style="font-size:18px">📖</div>
            <div><b style="color:#fff">Cited answers</b><div style="color:#9295ad;font-size:13.5px">See the exact file and page behind each response.</div></div></div>
          <div style="display:flex;gap:12px;margin:16px 0 26px"><div style="font-size:18px">⚡</div>
            <div><b style="color:#fff">Ready in minutes</b><div style="color:#9295ad;font-size:13.5px">Drop in PDFs and start asking right away.</div></div></div>
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
    busy = sum(status_of(d) == "PROCESSING" for d in docs)
    cols = st.columns(4)
    data = [("📄", len(docs), "Documents"), ("✅", ready, "Ready to query"),
           ("⏳", busy, "Processing"), ("💬", len(st.session_state.messages), "Questions asked")]
    for col, (i, v, l) in zip(cols, data):
        col.markdown(metric(i, v, l), unsafe_allow_html=True)

    st.write("")
    st.markdown("##### Get started")
    cards = [("⬆️", "Upload documents", "Add PDFs and we index them page by page for search.", "Go to Documents", "Documents"),
            ("💬", "Ask your documents", "Get direct answers with page-level citations.", "Open AI Chat", "AI Chat"),
            ("🧭", "Get guided", "Walk through processes and policies step by step.", "Open AI Guide", "AI Guide")]
    for col, (icon, t, d, btn, page) in zip(st.columns(3), cards):
        with col:
            st.markdown(f'<div class="gscard"><div class="ico">{icon}</div><div class="t">{t}</div><div class="d">{d}</div></div>',
                       unsafe_allow_html=True)
            st.write("")
            st.button(btn, key=f"qa_{page}", use_container_width=True, on_click=go, args=(page,))

    if docs:
        st.write("")
        st.markdown("##### Recent documents")
        for d in docs[:4]:
            st.markdown(f'<div class="doccard"><div class="left"><div class="ico">📄</div>'
                        f'<div class="name">{html.escape(d.get("filename", "Document"))}</div></div>{pill(status_of(d))}</div>',
                       unsafe_allow_html=True)


@st.fragment(run_every="5s")
def document_list():
    docs = load_documents()
    st.markdown("##### Your documents")
    if not docs:
        empty("No documents yet", "Upload your first PDF above to get started.")
        return
    for d in docs:
        status, pages, name = status_of(d), d.get("page_count"), html.escape(d.get("filename", "Unknown document"))
        meta = f'{pages} pages · ' if pages else ""
        errmsg = (f'<div class="meta" style="color:var(--err-ink)">{html.escape(str(d.get("error_message")))}</div>'
                 if status == "FAILED" and d.get("error_message") else "")
        c1, c2 = st.columns([9, 1], vertical_alignment="center")
        with c1:
            st.markdown(f'''<div class="doccard"><div class="left"><div class="ico">📄</div>
                <div><div class="name">{name}</div><div class="meta">{meta}{status.title()}</div>{errmsg}</div>
                </div>{pill(status)}</div>''', unsafe_allow_html=True)
        with c2:
            if did(d) and st.button("🗑", key=f"del_{did(d)}", help="Delete"):
                r = call("delete", f"/api/v1/documents/{did(d)}")
                if r is not None and r.status_code in (200, 204):
                    st.rerun()
                else:
                    st.error("You are not authorized to delete this document.")


def documents_page():
    crumb("Documents")
    hero("Documents", "Upload PDFs to build your searchable knowledge base. Text is extracted per page, so every answer can cite its source.")
    files = st.file_uploader("Drag & drop PDFs here, or browse", type=["pdf"], accept_multiple_files=True)
    if files:
        st.caption(f"{len(files)} file(s) selected: " + ", ".join(f"{f.name} ({f.size / 1024:.0f} KB)" for f in files))
        if st.button("Upload and index", type="primary", use_container_width=True):
            with st.spinner("Uploading and processing..."):
                r = call("post", "/api/v1/documents/upload",
                         files=[("files", (f.name, f.getvalue(), "application/pdf")) for f in files])
            if r is None:
                st.error("Could not connect to the document service.")
            elif r.status_code not in (200, 201, 202):
                st.error(err(r, "Document upload failed."))
            else:
                st.toast(f"{len(files)} document(s) uploaded", icon="✅")
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

    left, right = st.columns([1, 2.4], gap="medium")
    with left:
        with st.container(border=True):
            st.markdown(f"**Search in**")
            st.caption(f"{len(st.session_state.get('chat_docs', []))} of {len(ready)} ready documents selected")
            c1, c2 = st.columns(2)
            if c1.button("Select all", use_container_width=True):
                st.session_state.chat_docs = list(ready)
                st.rerun()
            if c2.button("Clear", use_container_width=True):
                st.session_state.chat_docs = []
                st.rerun()
            st.session_state.setdefault("chat_docs", list(ready))
            st.session_state.chat_docs = [i for i in st.session_state.chat_docs if i in ready]
            for i, d in ready.items():
                checked = st.checkbox(d.get("filename", "Document"), value=i in st.session_state.chat_docs, key=f"cd_{i}")
                if checked and i not in st.session_state.chat_docs:
                    st.session_state.chat_docs.append(i)
                elif not checked and i in st.session_state.chat_docs:
                    st.session_state.chat_docs.remove(i)
            if not ready:
                st.caption("No ready documents yet.")

    with right:
        with st.container(border=True):
            st.markdown("**💬 AI Document Chat**")
            st.caption("Answers are grounded in the selected documents and cite file + page")
            if not st.session_state.messages:
                empty("Ask your first question", "For example: What is our annual leave policy?")
            for m in st.session_state.messages:
                st.markdown(f'<div class="bubble-user">{html.escape(m["question"])}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="bubble-ai">🤖 {m["answer"]}</div>', unsafe_allow_html=True)
                show_sources(m.get("sources"))
                st.write("")
            q = st.chat_input("Ask a question about your documents...")
            if q:
                if not st.session_state.chat_docs:
                    st.warning("Select at least one document.")
                else:
                    with st.spinner("Searching your documents..."):
                        res = ask_ai(q, st.session_state.chat_docs)
                    if res is None:
                        st.error("Unable to connect to the AI backend.")
                    elif "error" in res:
                        st.error(res["error"])
                    else:
                        st.session_state.messages.append({"question": q, "answer": answer_of(res), "sources": res.get("sources", [])})
                        st.rerun()


def guide_page():
    crumb("AI Guide")
    st.markdown("### AI Guide")
    st.caption("Describe what you need to do and get step-by-step guidance grounded in your company's documents.")
    st.write("")
    st.markdown("**TRY ONE OF THESE**")
    ideas = [("Guide me through employee onboarding",), ("How do I request leave?",), ("Summarize our security policy",)]
    cols = st.columns(len(ideas))
    for col, (prompt,) in zip(cols, ideas):
        if col.button(f"✨ {prompt}", key=f"idea_{prompt}", use_container_width=True):
            st.session_state.guide_q = prompt
    question = st.text_area("What do you need help with?", key="guide_q", height=110,
                            placeholder="Example: Guide me through the employee onboarding process.")
    if st.button("☰  Get guidance", type="primary", use_container_width=True):
        if not question.strip():
            st.warning("Tell the AI what you need help with.")
            return
        ids = [did(d) for d in load_documents() if status_of(d) == "READY" and did(d)]
        with st.spinner("Analyzing your documents..."):
            res = ask_ai(question, ids)
        if res is None:
            st.error("AI Guide could not connect to the backend.")
        elif "error" in res:
            st.error(res["error"])
        else:
            st.session_state.guide_result = res
    res = st.session_state.guide_result
    if res:
        st.write("")
        with st.container(border=True):
            st.markdown("**🧭 Guidance**")
            st.markdown(res.get("answer") or res.get("response") or "No guidance returned.")
            show_sources(res.get("sources"))


def history_page():
    crumb("History")
    st.markdown("### Conversation history")
    st.caption("Everything you have asked, with the sources behind each answer.")
    st.write("")
    if not st.session_state.messages:
        empty("No conversations yet", "Your questions and answers will appear here.")
        return
    for m in reversed(st.session_state.messages):
        with st.container(border=True):
            st.markdown(f"**{m['question']}**")
            st.markdown(m["answer"])
            show_sources(m.get("sources"))


def admin_page():
    if str((st.session_state.user or {}).get("role", "")).upper() not in ("ADMIN", "SUPER_ADMIN"):
        st.error("You are not authorized to access the Admin Dashboard.")
        return
    crumb("Admin")
    hero("Admin dashboard", "Monitor document processing and system health.")
    docs = load_documents()
    count = lambda s: sum(status_of(d) == s for d in docs)
    cols = st.columns(4)
    data = [("📄", len(docs), "Documents"), ("✅", count("READY"), "Ready"),
           ("⏳", count("PROCESSING"), "Processing"), ("⚠️", count("FAILED"), "Failed")]
    for col, (i, v, l) in zip(cols, data):
        col.markdown(metric(i, v, l), unsafe_allow_html=True)
    st.write("")
    online = backend_online()
    st.markdown(f'<span class="connected"><span class="dot"></span>{"Backend online" if online else "Backend offline"} · {html.escape(API)}</span>',
               unsafe_allow_html=True)


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