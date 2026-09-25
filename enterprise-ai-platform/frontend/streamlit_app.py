import base64
import html
import json
import os

import requests
import streamlit as st

API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = 30

st.set_page_config(page_title="Enterprise AI Knowledge Platform", page_icon="🤖",
                   layout="wide", initial_sidebar_state="expanded")

# ============================================================ THEME
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{--a:#6d5bff;--b:#00c2a8;--c:#ff6b6b;--d:#ffb020;--bg:#f5f4ff;--card:#ffffff;--line:#e7e4fb;
 --ink:#1c1836;--mut:#6b6590;--shadow:0 10px 30px rgba(76,59,196,.08)}
html,body,[class*="css"],.stApp{font-family:'Inter',sans-serif}
.stApp{background:radial-gradient(1000px 560px at 6% -8%,rgba(109,91,255,.16),transparent 55%),
 radial-gradient(900px 560px at 100% 0%,rgba(0,194,168,.14),transparent 55%),
 radial-gradient(800px 500px at 50% 120%,rgba(255,107,107,.10),transparent 55%),var(--bg);color:var(--ink)}
#MainMenu,footer,[data-testid="stToolbar"],[data-testid="stDecoration"]{display:none!important}
header[data-testid="stHeader"]{background:transparent}
.block-container{padding-top:2.2rem;max-width:1200px}
section[data-testid="stSidebar"]{background:#ffffff;border-right:1px solid var(--line)}
h1,h2,h3{letter-spacing:-.02em;color:var(--ink)}
p,span,div,label{color:var(--ink)}
::selection{background:rgba(109,91,255,.25)}

/* hero */
.hero{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:22px;padding:34px 38px;margin-bottom:26px;
 background:linear-gradient(120deg,#7a5cff,#8f5bff 35%,#00c2a8 100%);box-shadow:var(--shadow)}
.hero:after{content:"";position:absolute;right:-50px;top:-70px;width:260px;height:260px;border-radius:50%;
 background:radial-gradient(circle,rgba(255,208,90,.55),transparent 70%)}
.hero:before{content:"";position:absolute;left:30%;bottom:-90px;width:200px;height:200px;border-radius:50%;
 background:radial-gradient(circle,rgba(255,107,107,.35),transparent 70%)}
.hero h1{font-size:34px;font-weight:800;margin:0 0 6px;position:relative;z-index:1;color:#fff}
.hero p{color:rgba(255,255,255,.92);margin:0;font-size:15.5px;max-width:640px;position:relative;z-index:1}

/* cards */
.metric{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:var(--shadow)}
.metric .ico{width:42px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:19px;
 background:linear-gradient(135deg,var(--a),var(--b));margin-bottom:14px}
.metric .num{font-size:32px;font-weight:800;line-height:1;color:var(--ink)}
.metric .lbl{color:var(--mut);font-size:13.5px;margin-top:6px}
.feature{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;margin-bottom:10px;min-height:128px;box-shadow:var(--shadow)}
.feature h4{margin:0 0 6px;font-size:17px;color:var(--ink)}.feature p{margin:0;color:var(--mut);font-size:14px;line-height:1.5}
.doc{display:flex;align-items:center;gap:14px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 18px;margin-bottom:8px;box-shadow:var(--shadow)}
.doc .name{font-weight:600;flex:1;word-break:break-all;color:var(--ink)}.doc .meta{color:var(--mut);font-size:13px}
.pill{padding:4px 12px;border-radius:999px;font-size:12px;font-weight:700;border:1px solid}
.p-ready{color:#0a9b6f;background:#e3faf1;border-color:#b9f0da}
.p-proc{color:#b4790a;background:#fff4de;border-color:#ffe2a8}
.p-fail{color:#e0455a;background:#ffe9ec;border-color:#ffc7cf}
.p-other{color:var(--mut);background:#f1effc;border-color:var(--line)}
.role{display:inline-block;padding:3px 12px;border-radius:999px;font-size:12px;font-weight:700;background:#ece8ff;
 color:#5b3fe0;border:1px solid #d9d0ff}
.role.admin{background:#ffe9d6;color:#c9660a;border-color:#ffd2a8}
.role.student{background:#d7f7f0;color:#0a9b8a;border-color:#b6efe2}
.avatar{width:46px;height:46px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:19px;
 background:linear-gradient(135deg,var(--a),var(--c));color:#fff}
.brand{font-size:20px;font-weight:800;letter-spacing:-.02em;color:var(--ink)}
.brand span{color:var(--mut);font-weight:500;font-size:12.5px;display:block;margin-top:2px}
.status{display:inline-flex;align-items:center;gap:8px;padding:6px 14px;border-radius:999px;font-size:13px;border:1px solid var(--line);background:var(--card)}
.dot{width:8px;height:8px;border-radius:50%}
.empty{text-align:center;color:var(--mut);border:1.5px dashed #cfc7ff;border-radius:18px;padding:44px 20px;background:#fbfaff}
.empty b{display:block;color:var(--ink);font-size:17px;margin-bottom:4px}
.bullet{display:flex;gap:14px;margin:18px 0}.bullet i{font-style:normal;font-size:20px}
.bullet b{display:block;color:var(--ink)}.bullet span{color:var(--mut);font-size:14px}

/* widgets */
.stButton>button,.stFormSubmitButton>button{border-radius:12px;border:1px solid var(--line);background:#fff;
 color:var(--ink);font-weight:600;padding:.55rem 1rem;transition:.15s}
.stButton>button:hover{border-color:var(--a);color:var(--a);background:#f4f2ff}
.stButton>button[kind="primary"],.stButton>button[data-testid="stBaseButton-primary"]{
 background:linear-gradient(135deg,#7a5cff,#ff6b6b 130%);border:0;color:#fff;box-shadow:0 10px 24px rgba(122,92,255,.35)}
.stButton>button[kind="primary"]:hover,.stButton>button[data-testid="stBaseButton-primary"]:hover{filter:brightness(1.07);color:#fff}
.stTextInput input,.stTextArea textarea,div[data-baseweb="select"]>div{background:#fbfaff!important;
 border:1px solid var(--line)!important;border-radius:12px!important;color:var(--ink)!important}
.stTextInput input:focus,.stTextArea textarea:focus{border-color:var(--a)!important;box-shadow:0 0 0 3px rgba(109,91,255,.18)!important}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:20px;border-color:var(--line);background:#fff;box-shadow:var(--shadow)}
[data-testid="stFileUploaderDropzone"]{background:#f4f2ff;border:1.5px dashed #b7a8ff;border-radius:16px}
[data-testid="stChatMessage"]{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px 18px;box-shadow:var(--shadow)}
[data-testid="stChatInput"]{border-radius:14px}
.stTabs [data-baseweb="tab-list"]{gap:6px}.stTabs [data-baseweb="tab"]{border-radius:10px;padding:8px 16px;color:var(--mut)}
.stTabs [aria-selected="true"]{background:#efeaff;color:var(--a)!important}
section[data-testid="stSidebar"] [role="radiogroup"] label{padding:9px 12px;border-radius:12px;margin-bottom:2px;transition:.15s;color:var(--ink)}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover{background:#f4f2ff}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:linear-gradient(90deg,#efeaff,#dcfbf5);color:var(--a)}
section[data-testid="stSidebar"] [role="radiogroup"] label>div:first-child{display:none}
[data-testid="stMetricValue"]{color:var(--ink)}
.stCaption,[data-testid="stCaptionContainer"]{color:var(--mut)!important}
</style>
""", unsafe_allow_html=True)

# ============================================================ STATE
DEFAULTS = {"token": None, "user": None, "messages": [], "otp_requested": False, "guide_result": None}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)

PAGES = ["🏠 Dashboard", "📄 Documents", "💬 AI Chat", "🧭 AI Guide", "📜 History"]
ADMIN_PAGE = "⚙️ Admin Dashboard"
st.session_state.setdefault("nav", PAGES[0])


def go(page):
    st.session_state.nav = page


# ============================================================ API
def call(method, path, **kw):
    headers = {"Accept": "application/json"}
    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        return requests.request(method, f"{API}{path}", headers=headers, timeout=TIMEOUT, **kw)
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
    """Store token and build a complete user profile (fixes the 'User' placeholder)."""
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
def hero(title, sub):
    st.markdown(f'<div class="hero"><h1>{html.escape(title)}</h1><p>{html.escape(sub)}</p></div>', unsafe_allow_html=True)


def metric(icon, value, label):
    return (f'<div class="metric"><div class="ico">{icon}</div>'
            f'<div class="num">{value}</div><div class="lbl">{label}</div></div>')


def pill(status):
    cls, label = {"READY": ("p-ready", "Ready"), "PROCESSING": ("p-proc", "Processing"),
                  "FAILED": ("p-fail", "Failed")}.get(status, ("p-other", status.title()))
    return f'<span class="pill {cls}">{label}</span>'


def empty(title, text):
    st.markdown(f'<div class="empty"><b>{title}</b>{text}</div>', unsafe_allow_html=True)


def show_sources(sources):
    if not sources:
        return
    with st.expander(f"📚 {len(sources)} source(s) used"):
        for s in sources:
            if isinstance(s, dict):
                pg = s.get("page_number")
                st.markdown(f"📄 **{s.get('filename', 'Document')}**" + (f" · page {pg}" if pg else ""))
            else:
                st.markdown(f"📄 {s}")


# ============================================================ AUTH
def auth_page():
    left, right = st.columns([1.15, 1], gap="large")
    online = backend_online()
    with left:
        st.markdown(f"""
        <div style="padding-top:40px">
          <div class="brand" style="font-size:22px">🤖 Enterprise AI</div>
          <h1 style="font-size:50px;font-weight:800;line-height:1.08;margin:26px 0 14px;
            background:linear-gradient(120deg,#6d5bff,#ff6b6b 60%,#00c2a8);-webkit-background-clip:text;-webkit-text-fill-color:transparent">
            Answers from your company's documents, in seconds.</h1>
          <p style="color:var(--mut);font-size:17px;max-width:520px">Upload your policies, handbooks and reports.
            Ask a question and get a sourced answer, with access limited to what you are allowed to see.</p>
          <div class="bullet"><i>🔒</i><div><b>Role-based access</b><span>Every answer respects document permissions.</span></div></div>
          <div class="bullet"><i>📚</i><div><b>Cited answers</b><span>See the exact file and page behind each response.</span></div></div>
          <div class="bullet"><i>⚡</i><div><b>Ready in minutes</b><span>Drop in PDFs and start asking right away.</span></div></div>
          <span class="status"><span class="dot" style="background:{'#0a9b6f' if online else '#e0455a'}"></span>
            {'Backend online' if online else 'Backend offline'}</span>
        </div>""", unsafe_allow_html=True)
        if not online:
            st.code("uvicorn app.main:app --reload", language="powershell")

    with right:
        with st.container(border=True):
            st.markdown("### Welcome back")
            st.caption("Sign in to your workspace")
            t_pw, t_otp, t_reg = st.tabs(["Password", "Email code", "Register"])

            with t_pw:
                email = st.text_input("Email", key="login_email")
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
    cls = "admin" if is_admin else "student" if role == "STUDENT" else ""
    with st.sidebar:
        st.markdown('<div class="brand">🤖 Enterprise AI<span>Knowledge &amp; Document Intelligence</span></div>', unsafe_allow_html=True)
        st.write("")
        st.markdown(f"""<div style="display:flex;gap:12px;align-items:center;padding:14px;border:1px solid var(--line);
            border-radius:16px;background:var(--card)"><div class="avatar">{html.escape(u.get('name', 'U')[:1].upper())}</div>
            <div style="min-width:0"><b>{html.escape(u.get('name', 'User'))}</b>
            <div style="color:var(--mut);font-size:12px;overflow:hidden;text-overflow:ellipsis">{html.escape(u.get('email', ''))}</div>
            <span class="role {cls}" style="margin-top:6px">{role.replace('_', ' ').title()}</span></div></div>""",
                    unsafe_allow_html=True)
        st.write("")
        st.radio("Navigation", PAGES + ([ADMIN_PAGE] if is_admin else []), key="nav", label_visibility="collapsed")
        st.divider()
        if st.button("Sign out", use_container_width=True):
            st.session_state.clear()
            st.rerun()


# ============================================================ PAGES
def dashboard_page():
    u = st.session_state.user or {}
    first = str(u.get("name", "there")).split()[0]
    hero(f"Welcome back, {first}", "Upload documents, ask questions and get answers with sources, all in one secure workspace.")
    docs = load_documents()
    ready = sum(status_of(d) == "READY" for d in docs)
    busy = sum(status_of(d) == "PROCESSING" for d in docs)
    for col, (i, v, l) in zip(st.columns(4), [("📄", len(docs), "Documents"), ("✅", ready, "Ready to query"),
                                              ("⏳", busy, "Processing"), ("💬", len(st.session_state.messages), "Questions asked")]):
        col.markdown(metric(i, v, l), unsafe_allow_html=True)

    st.markdown("### Get started")
    cards = [("📄 Upload documents", "Add PDFs and we index them for search.", "Upload documents", "📄 Documents"),
             ("💬 Ask your documents", "Get direct answers with page-level sources.", "Start chatting", "💬 AI Chat"),
             ("🧭 Get guided", "Walk through processes and policies step by step.", "Open AI Guide", "🧭 AI Guide")]
    for col, (t, d, btn, page) in zip(st.columns(3), cards):
        with col:
            st.markdown(f'<div class="feature"><h4>{t}</h4><p>{d}</p></div>', unsafe_allow_html=True)
            st.button(btn, key=f"qa_{page}", use_container_width=True, on_click=go, args=(page,))

    if docs:
        st.markdown("### Recent documents")
        for d in docs[:4]:
            st.markdown(f'<div class="doc"><span class="name">📄 {html.escape(d.get("filename", "Document"))}</span>'
                        f'{pill(status_of(d))}</div>', unsafe_allow_html=True)


@st.fragment(run_every="5s")
def document_list():
    docs = load_documents()
    st.markdown("### Your documents")
    if not docs:
        empty("No documents yet", "Upload your first PDF above to get started.")
        return
    for d in docs:
        c1, c2 = st.columns([8, 1.3], vertical_alignment="center")
        status, pages = status_of(d), d.get("page_count")
        extra = f'<span class="meta">{pages} pages</span>' if pages else ""
        errmsg = f'<div class="meta" style="color:#e0455a">{html.escape(str(d.get("error_message")))}</div>' \
            if status == "FAILED" and d.get("error_message") else ""
        c1.markdown(f'<div class="doc"><div class="name">📄 {html.escape(d.get("filename", "Unknown document"))}{errmsg}</div>'
                    f'{extra}{pill(status)}</div>', unsafe_allow_html=True)
        if did(d) and c2.button("Delete", key=f"del_{did(d)}", use_container_width=True):
            r = call("delete", f"/api/v1/documents/{did(d)}")
            if r is not None and r.status_code in (200, 204):
                st.rerun()
            else:
                st.error("You are not authorized to delete this document.")


def documents_page():
    hero("Documents", "Upload PDFs to build your searchable knowledge base.")
    files = st.file_uploader("Drag and drop PDF files here", type=["pdf"], accept_multiple_files=True)
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
    hero("AI Document Chat", "Ask a question and get an answer grounded in your selected documents.")
    docs = load_documents()
    if not docs:
        empty("Nothing to search yet", "Upload at least one PDF, then come back to ask questions.")
        return
    ready = {did(d): d for d in docs if status_of(d) == "READY" and did(d)}
    if not ready:
        st.warning("Your documents are still processing or have failed.")
        return
    st.session_state.setdefault("chat_docs", list(ready))
    st.session_state.chat_docs = [i for i in st.session_state.chat_docs if i in ready]
    selected = st.multiselect("Search in", list(ready), key="chat_docs",
                              format_func=lambda i: ready[i].get("filename", "Document"))

    if not st.session_state.messages:
        empty("Ask your first question", "For example: What is our annual leave policy?")
    for m in st.session_state.messages:
        with st.chat_message("user"):
            st.write(m["question"])
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(m["answer"])
            show_sources(m.get("sources"))

    q = st.chat_input("Ask a question about your documents")
    if q:
        if not selected:
            st.warning("Select at least one document.")
            return
        with st.spinner("Searching your documents..."):
            res = ask_ai(q, selected)
        if res is None:
            st.error("Unable to connect to the AI backend.")
        elif "error" in res:
            st.error(res["error"])
        else:
            st.session_state.messages.append({"question": q, "answer": answer_of(res), "sources": res.get("sources", [])})
            st.rerun()


def guide_page():
    hero("AI Guide", "Describe what you need to do and get step-by-step guidance from your company's documents.")
    st.caption("Try one of these")
    ideas = ["Guide me through employee onboarding", "How do I request leave?", "Summarize our security policy"]
    for col, idea in zip(st.columns(3), ideas):
        col.button(idea, key=f"idea_{idea}", use_container_width=True, on_click=lambda i=idea: st.session_state.update(guide_q=i))
    question = st.text_area("What do you need help with?", key="guide_q", height=110,
                            placeholder="Example: Guide me through the employee onboarding process.")
    if st.button("Get guidance", type="primary", use_container_width=True):
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
        with st.container(border=True):
            st.markdown("### 🧭 Guidance")
            st.markdown(res.get("answer") or res.get("response") or "No guidance returned.")
            show_sources(res.get("sources"))


def history_page():
    hero("Conversation history", "Everything you have asked in this session.")
    if not st.session_state.messages:
        empty("No conversations yet", "Your questions and answers will appear here.")
        return
    for i, m in enumerate(reversed(st.session_state.messages), 1):
        with st.expander(f"{i}. {m['question'][:70]}"):
            st.markdown("**Question**")
            st.write(m["question"])
            st.markdown("**Answer**")
            st.markdown(m["answer"])
            show_sources(m.get("sources"))


def admin_page():
    if str((st.session_state.user or {}).get("role", "")).upper() not in ("ADMIN", "SUPER_ADMIN"):
        st.error("You are not authorized to access the Admin Dashboard.")
        return
    hero("Admin dashboard", "Monitor document processing and system health.")
    docs = load_documents()
    count = lambda s: sum(status_of(d) == s for d in docs)
    for col, (i, v, l) in zip(st.columns(4), [("📄", len(docs), "Documents"), ("✅", count("READY"), "Ready"),
                                              ("⏳", count("PROCESSING"), "Processing"), ("⚠️", count("FAILED"), "Failed")]):
        col.markdown(metric(i, v, l), unsafe_allow_html=True)
    st.markdown("### System")
    online = backend_online()
    st.markdown(f'<span class="status"><span class="dot" style="background:{"#0a9b6f" if online else "#e0455a"}"></span>'
                f'{"Backend online" if online else "Backend offline"} · {html.escape(API)}</span>', unsafe_allow_html=True)


# ============================================================ MAIN
def main():
    if not st.session_state.token:
        auth_page()
        return
    sidebar()
    {"🏠 Dashboard": dashboard_page, "📄 Documents": documents_page, "💬 AI Chat": chat_page,
     "🧭 AI Guide": guide_page, "📜 History": history_page, ADMIN_PAGE: admin_page}.get(st.session_state.nav, dashboard_page)()


if __name__ == "__main__":
    main()