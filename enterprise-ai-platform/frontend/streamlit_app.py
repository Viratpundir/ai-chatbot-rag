"""
Enterprise AI — Knowledge & Document Intelligence
==================================================
Streamlit frontend for the FastAPI backend. Structured in five sections:

  1. CONFIG & STATE      - constants, session defaults
  2. THEME               - CSS tokens for light/dark + component styles
  3. API LAYER           - every call to the FastAPI backend lives here
  4. UI COMPONENTS       - small reusable render helpers (cards, pills, ...)
  5. PAGES               - one function per screen
  6. MAIN                - routes to the right page

Run with:  streamlit run app.py
"""

import base64
import html
import json
import os
from urllib.parse import urlsplit

import requests
import streamlit as st
import streamlit.components.v1 as components

# ============================================================================
# 1. CONFIG & STATE
# ============================================================================

API_BASE_URL = os.getenv("API_BASE_URL", "").rstrip("/")
REQUEST_TIMEOUT = 30

PAGES = ["Dashboard", "Documents", "AI Chat", "AI Guide", "History"]
ADMIN_PAGE = "Admin Dashboard"
NAV_ICONS = {
    "Dashboard": "grid_view", "Documents": "folder", "AI Chat": "chat",
    "AI Guide": "explore", "History": "history", ADMIN_PAGE: "tune",
}

st.set_page_config(page_title="Enterprise AI", page_icon="✨", layout="wide", initial_sidebar_state="auto")

SESSION_DEFAULTS = {
    "token": None, "refresh_token": None, "user": None, "messages": [],
    "conversation_id": None, "otp_requested": False, "guide_result": None,
    "theme": "light", "nav": PAGES[0],
}
for _key, _val in SESSION_DEFAULTS.items():
    st.session_state.setdefault(_key, _val)

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


def go(page: str) -> None:
    """Navigate to a page (used as a button on_click callback)."""
    st.session_state.nav = page
    st.session_state["navigation_selection"] = page


def ask_about_document(document_id: str) -> None:
    st.session_state.chat_docs = [document_id]
    st.session_state[f"chatdoc_{document_id}"] = True
    go("AI Chat")


# ============================================================================
# 2. THEME
# ============================================================================

LIGHT_TOKENS = dict(
    bg="#f8f9fa", surface="#ffffff", surface2="#f5f6fa", border="#e5e7eb",
    ink="#202124", muted="#6b7280", primary="#635bff", primary2="#6d5bff",
    on_primary="#ffffff", chip="#eeebff", chip_ink="#4f46e5",
    ok="#eaf7ee", ok_ink="#188038", warn="#fff4e5", warn_ink="#b06000",
    err="#fcebea", err_ink="#d93025", hero="linear-gradient(120deg,#4d37e6,#5b47f5 55%,#006b5c)",
)
DARK_TOKENS = dict(
    bg="#0b1020", surface="#111827", surface2="#172033", border="#263244",
    ink="#f8fafc", muted="#94a3b8", primary="#8b7cff", primary2="#a296ff",
    on_primary="#171513", chip="#29235f", chip_ink="#c4baff",
    ok="#123524", ok_ink="#22c55e", warn="#332a12", warn_ink="#f59e0b",
    err="#3a1a1c", err_ink="#ef4444", hero="linear-gradient(120deg,#151d3b,#4d37e6 55%,#006b5c)",
)
T = DARK_TOKENS if st.session_state.theme == "dark" else LIGHT_TOKENS

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

:root{{
  --bg:{T['bg']}; --surface:{T['surface']}; --surface2:{T['surface2']}; --border:{T['border']};
  --ink:{T['ink']}; --muted:{T['muted']}; --primary:{T['primary']}; --primary2:{T['primary2']};
  --on-primary:{T['on_primary']}; --chip:{T['chip']}; --chip-ink:{T['chip_ink']};
  --ok:{T['ok']}; --ok-ink:{T['ok_ink']}; --warn:{T['warn']}; --warn-ink:{T['warn_ink']};
  --err:{T['err']}; --err-ink:{T['err_ink']}; --hero:{T['hero']};
}}
.msi{{font-family:'Material Symbols Outlined';font-weight:400;font-style:normal;font-size:20px;line-height:1;
 display:inline-block;vertical-align:middle;-webkit-font-feature-settings:'liga'}}
.msi.fill{{font-variation-settings:'FILL' 1}}

html,body,[class*="css"],.stApp{{font-family:'Inter',sans-serif}}
.stApp{{background:var(--bg);color:var(--ink)}}
#MainMenu,footer,[data-testid="stToolbar"],[data-testid="stDecoration"]{{display:none!important}}
header[data-testid="stHeader"]{{background:transparent}}
.block-container{{padding-top:1.2rem;max-width:1220px}}
section[data-testid="stSidebar"]{{background:var(--surface);border-right:1px solid var(--border)}}
h1,h2,h3{{letter-spacing:-.02em;color:var(--ink)}}
p,span,div,label{{color:var(--ink)}}

/* ---- top bar: title + search-look breadcrumb + status + theme toggle ---- */
.topbar{{position:sticky;top:0;z-index:5;display:flex;align-items:center;justify-content:space-between;
 background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:10px 16px;margin-bottom:18px;
 box-shadow:0 1px 6px rgba(0,0,0,.04)}}
.topbar .crumb{{font-size:14px;color:var(--muted)}}.topbar .crumb b{{color:var(--ink)}}
.topbar .status{{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--ok-ink);
 background:var(--ok);padding:4px 12px;border-radius:999px}}
.statusdot{{width:6px;height:6px;border-radius:50%;background:var(--ok-ink)}}

/* ---- hero banner ---- */
.hero{{position:relative;overflow:hidden;border-radius:20px;padding:28px 30px;margin-bottom:20px;color:#fff;background:var(--hero)}}
.hero:after{{content:"";position:absolute;right:-60px;top:-60px;width:220px;height:220px;border-radius:50%;
 background:rgba(255,255,255,.18);filter:blur(30px)}}
.hero:before{{content:"";position:absolute;left:20%;bottom:-90px;width:200px;height:200px;border-radius:50%;
 background:rgba(0,0,0,.15);filter:blur(30px)}}
.hero .eyebrow{{position:relative;z-index:1;display:inline-flex;align-items:center;gap:6px;padding:4px 12px;
 border-radius:999px;background:rgba(255,255,255,.18);font-size:11.5px;font-weight:700;letter-spacing:.03em;text-transform:uppercase}}
.hero h1{{position:relative;z-index:1;font-size:30px;font-weight:800;margin:12px 0 6px;color:#fff}}
.hero p{{position:relative;z-index:1;font-size:14.5px;color:rgba(255,255,255,.92);margin:0;max-width:640px}}

/* ---- metric cards ---- */
.metric{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:18px;
 display:flex;flex-direction:column;justify-content:space-between;min-height:108px}}
.metric .head{{display:flex;align-items:flex-start;justify-content:space-between}}
.metric .lbl{{color:var(--muted);font-size:11px;letter-spacing:.05em;text-transform:uppercase;font-weight:700}}
.metric .ico{{width:38px;height:38px;border-radius:11px;background:var(--chip);color:var(--chip-ink);
 display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.metric .num{{font-size:28px;font-weight:800;line-height:1;margin-top:10px}}
.metric .tag{{font-size:11px;font-weight:700;color:var(--muted);margin-top:4px}}
.metric .tag.ok{{color:var(--ok-ink)}}

/* ---- feature / get-started cards ---- */
.feature{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px;
 display:flex;flex-direction:column;gap:10px;height:100%}}
.feature .ico{{width:42px;height:42px;border-radius:12px;background:var(--chip);color:var(--chip-ink);
 display:flex;align-items:center;justify-content:center;font-size:20px}}
.feature .t{{font-weight:700;font-size:15.5px}}
.feature .d{{color:var(--muted);font-size:13px;line-height:1.5}}

/* ---- document cards ---- */
.doccard{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:14px 16px;
 margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;gap:12px}}
.doccard .left{{display:flex;align-items:center;gap:12px;min-width:0}}
.doccard .ico{{width:36px;height:36px;border-radius:10px;background:var(--chip);color:var(--chip-ink);
 display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.doccard .name{{font-weight:600;font-size:14px;word-break:break-all}}
.doccard .meta{{color:var(--muted);font-size:12px;margin-top:1px}}

/* ---- status pills ---- */
.pill{{display:inline-flex;align-items:center;gap:5px;padding:3px 11px;border-radius:999px;font-size:11.5px;font-weight:700;white-space:nowrap}}
.p-ready{{background:var(--ok);color:var(--ok-ink)}}
.p-proc{{background:var(--warn);color:var(--warn-ink)}}
.p-fail{{background:var(--err);color:var(--err-ink)}}
.p-other{{background:var(--chip);color:var(--muted)}}
.dot{{width:6px;height:6px;border-radius:50%}}
.dot-ready{{background:var(--ok-ink)}}.dot-proc{{background:var(--warn-ink)}}.dot-fail{{background:var(--err-ink)}}.dot-other{{background:var(--muted)}}

/* ---- sidebar profile & nav ---- */
.brand{{font-size:17px;font-weight:800}}.brand span{{color:var(--muted);font-weight:500;font-size:11.5px;display:block;margin-top:1px}}
.sideprofile{{display:flex;gap:10px;align-items:center;padding:12px;border-radius:14px;background:var(--surface2);border:1px solid var(--border)}}
.sideavatar{{width:38px;height:38px;border-radius:50%;background:var(--primary);color:var(--on-primary);font-weight:800;font-size:15px;
 display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.role{{display:inline-block;padding:2px 10px;border-radius:999px;font-size:10.5px;font-weight:700;background:var(--chip);color:var(--chip-ink)}}
.sidestatus{{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;font-weight:600;color:var(--ok-ink);
 background:var(--ok);padding:5px 12px;border-radius:999px;width:100%;justify-content:center}}

/* ---- empty state ---- */
.empty{{text-align:center;color:var(--muted);border:1.5px dashed var(--border);border-radius:16px;padding:38px 20px;background:var(--surface2)}}
.empty b{{display:block;color:var(--ink);font-size:15px;margin-bottom:3px}}

/* ---- chat bubbles & citations ---- */
.bubble-user{{background:var(--primary);color:var(--on-primary);border:1px solid var(--primary);border-radius:16px 16px 3px 16px;padding:12px 15px;
 max-width:80%;margin-left:auto;font-size:14.5px;line-height:1.5}}
.bubble-ai{{background:var(--surface);border:1px solid var(--border);border-radius:16px 16px 16px 3px;padding:15px;font-size:14.5px;line-height:1.55}}
.citebox{{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:10px 12px;margin-top:8px}}
.citecard{{background:var(--surface);border:1px solid var(--border);border-radius:9px;padding:8px 11px;margin-top:6px;
 display:flex;justify-content:space-between;align-items:center;gap:8px}}
.citecard .fn{{font-weight:600;font-size:12.5px}}
.citecard .pg{{font-size:10.5px;background:var(--chip);color:var(--chip-ink);padding:2px 8px;border-radius:6px;white-space:nowrap}}

/* ---- guide steps ---- */
.step{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:18px;margin-bottom:12px}}
.step .idx{{width:30px;height:30px;border-radius:50%;background:var(--primary);color:var(--on-primary);font-weight:700;font-size:13px;
 display:flex;align-items:center;justify-content:center;flex-shrink:0}}

/* ---- widgets ---- */
.stButton>button,.stFormSubmitButton>button{{border-radius:11px;border:1px solid var(--border);
 background:var(--surface);color:var(--ink);font-weight:600;padding:.5rem 1rem;transition:.15s}}
.stButton>button:hover{{border-color:var(--primary);color:var(--primary)}}
.stButton>button[kind="primary"],.stButton>button[data-testid="stBaseButton-primary"]{{
 background:var(--primary);border:1px solid var(--primary);color:var(--on-primary);
 box-shadow:0 4px 14px rgba(99,91,255,.25)}}
.stButton>button[kind="primary"]:hover,.stButton>button[data-testid="stBaseButton-primary"]:hover{{filter:brightness(1.08);border-color:var(--primary2);color:var(--on-primary)}}
.stTextInput input,.stTextArea textarea,div[data-baseweb="select"]>div{{background:var(--surface2)!important;
 border:1px solid var(--border)!important;border-radius:11px!important;color:var(--ink)!important}}
.stTextInput input:focus,.stTextArea textarea:focus{{border-color:var(--primary)!important;box-shadow:0 0 0 3px rgba(83,62,229,.15)!important}}
[data-testid="stVerticalBlockBorderWrapper"]{{border-radius:16px;border-color:var(--border);background:var(--surface)}}
[data-testid="stFileUploaderDropzone"]{{background:var(--surface2);border:1.5px dashed var(--border);border-radius:14px}}
.stTabs [data-baseweb="tab-list"]{{gap:4px}}.stTabs [data-baseweb="tab"]{{border-radius:9px;padding:7px 14px;color:var(--muted)}}
.stTabs [aria-selected="true"]{{background:var(--chip);color:var(--chip-ink)!important}}
section[data-testid="stSidebar"] [role="radiogroup"] label{{padding:8px 11px;border-radius:10px;margin-bottom:2px}}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover{{background:var(--surface2)}}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){{background:var(--chip);color:var(--chip-ink)}}
section[data-testid="stSidebar"] [role="radiogroup"] label>div:first-child{{display:none}}
.stCaption,[data-testid="stCaptionContainer"]{{color:var(--muted)!important}}
</style>
""", unsafe_allow_html=True)


def msi(name: str, fill: bool = False) -> str:
    """Render a Material Symbols icon span."""
    return f'<span class="msi{" fill" if fill else ""}">{name}</span>'


def toggle_theme_button(button_column=None) -> None:
    """Small icon button, top-right of the page, that flips light/dark."""
    if button_column is None:
        _, button_column = st.columns([12, 1])
    icon = "🌙" if st.session_state.theme == "light" else "☀️"
    label = "Switch to dark mode" if st.session_state.theme == "light" else "Switch to light mode"
    if button_column.button(icon, key=f"theme_toggle_{st.session_state.nav}", help=label):
        theme = "dark" if st.session_state.theme == "light" else "light"
        st.session_state.theme = theme
        st.query_params["theme"] = theme
        st.rerun()


# ============================================================================
# 3. API LAYER
# ============================================================================

def api_call(method: str, path: str, **kwargs):
    """Low-level request wrapper. Returns the Response, or None if unreachable."""
    api_base = API_BASE_URL
    if not api_base:
        try:
            request_headers = st.context.headers
            request_host = urlsplit(f"//{request_headers.get('Host', '')}").hostname
            scheme = request_headers.get("X-Forwarded-Proto", "http").split(",")[0].strip()
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
        return requests.request(method, f"{api_base}{path}", headers=headers, timeout=REQUEST_TIMEOUT, **kwargs)
    except requests.RequestException:
        return None


def api_error(response, default: str) -> str:
    try:
        body = response.json()
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


def backend_is_online() -> bool:
    r = api_call("get", "/api/v1/health")
    return r is not None and r.status_code == 200


@st.fragment(run_every="15s")
def render_backend_status() -> None:
    online = backend_is_online()
    color = "#0f8f5f" if online else "#ba1a1a"
    label = "Backend online" if online else "Backend offline"
    st.markdown(
        f'<div class="status"><span class="statusdot" style="background:{color}"></span>{label}</div>',
        unsafe_allow_html=True,
    )


def decode_jwt(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception:
        return {}


def start_session(auth_response: dict) -> None:
    """Store the token and build a full user profile from whatever the API gave us."""
    st.session_state.token = auth_response.get("access_token") or auth_response.get("token")
    st.session_state.refresh_token = auth_response.get("refresh_token")
    user = dict(auth_response.get("user") or auth_response.get("data") or {})

    if not (user.get("name") or user.get("full_name")):
        r = api_call("get", "/api/v1/auth/me")
        if r is not None and r.status_code == 200:
            try:
                user.update(r.json())
            except Exception:
                pass

    claims = decode_jwt(st.session_state.token or "")
    subject = str(claims.get("sub", ""))
    user["email"] = user.get("email") or claims.get("email") or (subject if "@" in subject else "")
    user["role"] = user.get("role") or claims.get("role") or "EMPLOYEE"
    user["name"] = (
        user.get("name") or user.get("full_name") or claims.get("name")
        or (user["email"].split("@")[0].replace(".", " ").title() if user["email"] else "User")
    )
    st.session_state.user = user


def try_auth(path: str, payload: dict, fail_message: str):
    """POST an auth request; show an error and return None on failure."""
    r = api_call("post", path, json=payload)
    if r is None:
        st.error("Authentication service is offline. Start the FastAPI backend and retry.")
        return None
    if r.status_code not in (200, 201):
        st.error(api_error(r, fail_message))
        return None
    return r


def fetch_documents() -> list:
    documents = []
    page = 1
    while True:
        response = api_call("get", "/api/v1/documents", params={"page": page, "page_size": 100})
        if response is None or response.status_code != 200:
            return documents
        try:
            data = response.json()
            if isinstance(data, list):
                return data
            page_items = data.get("documents", data.get("data", []))
            documents.extend(page_items)
            if len(documents) >= int(data.get("total", len(documents))) or not page_items:
                return documents
            page += 1
        except (ValueError, AttributeError, TypeError):
            return documents


def ask_ai(question: str, document_ids: list, conversation_id: str | None = None):
    payload = {"question": question, "document_ids": document_ids}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    r = api_call("post", "/api/v1/chat/ask", json=payload)
    if r is None:
        return None
    if r.status_code != 200:
        return {"error": api_error(r, "Unable to process the question.")}
    return r.json()


def ask_guide(message: str, document_ids: list):
    r = api_call("post", "/api/v1/chat/agent", json={
        "message": message,
        "document_ids": document_ids,
        "all_authorized": False,
    })
    if r is None:
        return {"error": "AI Guide could not connect to the backend."}
    if r.status_code != 200:
        return {"error": api_error(r, "Unable to generate guidance.")}
    return r.json()


def fetch_chat_stats():
    r = api_call("get", "/api/v1/chat/stats")
    if r is None or r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def fetch_history() -> list:
    conversations = []
    page = 1
    while True:
        response = api_call("get", "/api/v1/chat/conversations", params={"page": page, "page_size": 100})
        if response is None or response.status_code != 200:
            return conversations
        try:
            data = response.json()
            page_items = data.get("conversations", [])
            conversations.extend(page_items)
            if len(conversations) >= int(data.get("total", len(conversations))) or not page_items:
                break
            page += 1
        except (ValueError, AttributeError, TypeError):
            return conversations
    records = []
    for conversation in conversations:
        conversation_id = conversation.get("conversation_id")
        if not conversation_id:
            continue
        detail = api_call("get", f"/api/v1/chat/conversations/{conversation_id}")
        if detail is not None and detail.status_code == 200:
            records.append(detail.json())
    return records


def doc_id(d: dict):
    return d.get("id") or d.get("document_id")


def doc_status(d: dict) -> str:
    return str(d.get("status", "UNKNOWN")).upper()


def answer_text(result: dict) -> str:
    return result.get("answer") or result.get("response") or result.get("message") or "No answer returned."


# ============================================================================
# 4. UI COMPONENTS
# ============================================================================

def render_topbar(page_label: str) -> None:
    user = st.session_state.user or {}
    title, email, status, theme = st.columns([5, 3, 1.8, 0.7], vertical_alignment="center")
    title.markdown(
        f'<div class="topbar"><div class="crumb"><b>Enterprise AI</b> &nbsp;/&nbsp; {html.escape(page_label)}</div></div>',
        unsafe_allow_html=True,
    )
    email.caption(html.escape(user.get("email", "")))
    with status:
        render_backend_status()
    toggle_theme_button(theme)


def render_hero(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(f'''<div class="hero"><span class="eyebrow">{msi("auto_awesome")} {html.escape(eyebrow)}</span>
        <h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>''', unsafe_allow_html=True)


def render_metric(icon: str, value, label: str, tag: str = None, ok: bool = False) -> str:
    tag_html = f'<div class="tag{" ok" if ok else ""}">{html.escape(tag)}</div>' if tag else ""
    return f'''<div class="metric"><div class="head"><div class="lbl">{html.escape(label)}</div>
        <div class="ico">{msi(icon)}</div></div><div><div class="num">{value}</div>{tag_html}</div></div>'''


def render_pill(status: str) -> str:
    mapping = {
        "READY": ("p-ready", "dot-ready", "Ready"),
        "PROCESSING": ("p-proc", "dot-proc", "Processing"),
        "UPLOADED": ("p-proc", "dot-proc", "Processing"),
        "PENDING": ("p-proc", "dot-proc", "Processing"),
        "FAILED": ("p-fail", "dot-fail", "Failed"),
    }
    css_class, dot_class, label = mapping.get(status, ("p-other", "dot-other", status.title()))
    return f'<span class="pill {css_class}"><span class="dot {dot_class}"></span>{label}</span>'


def render_empty(icon: str, title: str, text: str) -> None:
    st.markdown(f'<div class="empty">{msi(icon)}<b>{html.escape(title)}</b>{html.escape(text)}</div>', unsafe_allow_html=True)


def render_source_cards(sources) -> None:
    for source in sources:
        if not isinstance(source, dict):
            st.write(str(source))
            continue
        with st.container(border=True):
            filename = html.escape(str(source.get("filename", "Document")))
            page = source.get("page") or source.get("page_number")
            section = source.get("section") or source.get("subsection")
            st.markdown(f"**{msi('description')} {filename}**" + (f" · Page {page}" if page else ""), unsafe_allow_html=True)
            if section:
                st.caption(str(section))
            if source.get("excerpt"):
                st.write(f"“{source['excerpt']}”")
            for field, label in (("vector_score", "Vector"), ("hybrid_score", "Hybrid"), ("rerank_score", "Rerank")):
                if source.get(field) is not None:
                    st.caption(f"{label} score: {float(source[field]):.3f}")


def render_sources(sources, expandable: bool = True) -> None:
    if not sources:
        return
    if expandable:
        with st.expander(f"📚 Sources used ({len(sources)})"):
            render_source_cards(sources)
    else:
        st.markdown(f"**📚 Sources used ({len(sources)})**")
        render_source_cards(sources)


# ============================================================================
# 5. PAGES
# ============================================================================

def page_auth() -> None:
    toggle_theme_button()
    online = backend_is_online()
    left, right = st.columns([1.15, 1], gap="large")

    with left:
        st.markdown(f'''
        <div style="background:#14121a;border-radius:20px;padding:40px 34px;height:100%;color:#fff">
          <div style="display:flex;align-items:center;gap:8px;font-weight:800;font-size:18px;margin-bottom:26px">
            ✨ Enterprise AI</div>
          <span style="display:inline-block;background:rgba(83,62,229,.30);color:#c9c1ff;font-size:11.5px;font-weight:700;
            padding:5px 12px;border-radius:999px;margin-bottom:18px">● AI KNOWLEDGE WORKSPACE</span>
          <h1 style="font-size:42px;font-weight:800;line-height:1.12;margin:0 0 16px;color:#fff">
            Turn your document library into an expert that never sleeps.</h1>
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
        </div>''', unsafe_allow_html=True)
        if not online:
            st.code("uvicorn app.main:app --reload", language="powershell")

    with right:
        with st.container(border=True):
            st.markdown("### Welcome back")
            st.caption("Sign in to your workspace")
            tab_password, tab_otp, tab_register = st.tabs(["Password", "Email code", "Register"])

            with tab_password:
                email = st.text_input("Email", key="login_email", placeholder="you@company.com")
                password = st.text_input("Password", type="password", key="login_password")
                if st.button("Sign in", type="primary", use_container_width=True):
                    if not email or not password:
                        st.warning("Enter your email and password.")
                    else:
                        r = try_auth("/api/v1/auth/login", {"email": email, "password": password},
                                     "Invalid email or password.")
                        if r is not None:
                            start_session(r.json())
                            st.rerun()

            with tab_otp:
                email = st.text_input("Email", key="otp_email")
                if not st.session_state.otp_requested:
                    if st.button("Send code", use_container_width=True):
                        if not email:
                            st.warning("Enter your email.")
                        elif try_auth("/api/v1/auth/request-otp", {"email": email}, "Unable to send the code."):
                            st.session_state.otp_requested = True
                            st.rerun()
                else:
                    st.success("Code sent. Check your inbox.")
                    otp = st.text_input("6-digit code", max_chars=6, key="otp_value")
                    if st.button("Verify and sign in", type="primary", use_container_width=True):
                        r = try_auth("/api/v1/auth/verify-otp", {"email": email, "otp": otp}, "Invalid or expired code.")
                        if r is not None:
                            st.session_state.otp_requested = False
                            start_session(r.json())
                            st.rerun()
                    if st.button("Send a new code"):
                        try_auth("/api/v1/auth/request-otp", {"email": email}, "Unable to send the code.")

            with tab_register:
                name = st.text_input("Full name", key="register_name")
                email = st.text_input("Email", key="register_email")
                password = st.text_input("Password", type="password", key="register_password")
                role = st.selectbox("Account type", ["EMPLOYEE", "STUDENT"])
                if st.button("Create account", type="primary", use_container_width=True):
                    if not (name and email and password):
                        st.warning("Complete all fields.")
                    elif try_auth("/api/v1/auth/register",
                                  {"name": name, "email": email, "password": password, "role": role},
                                  "Registration failed."):
                        st.success("Account created. Switch to the Password tab to sign in.")


def render_sidebar() -> None:
    user = st.session_state.user or {}
    role = str(user.get("role", "EMPLOYEE")).upper()
    is_admin = role in ("ADMIN", "SUPER_ADMIN")

    with st.sidebar:
        st.markdown('<div class="brand">✨ Enterprise AI<span>Knowledge &amp; Document Intelligence</span></div>',
                    unsafe_allow_html=True)
        st.write("")
        st.markdown(f'''<div class="sideprofile"><div class="sideavatar">{html.escape(user.get("name", "U")[:1].upper())}</div>
            <div style="min-width:0"><b style="font-size:13.5px">{html.escape(user.get("name", "User"))}</b>
            <div style="color:var(--muted);font-size:11.5px;overflow:hidden;text-overflow:ellipsis">{html.escape(user.get("email", ""))}</div>
            <span class="role" style="margin-top:5px">{role.replace("_", " ").title()}</span></div></div>''',
                    unsafe_allow_html=True)
        st.write("")

        options = PAGES + ([ADMIN_PAGE] if is_admin else [])
        labels = [f"{p}" for p in options]
        current_index = options.index(st.session_state.nav) if st.session_state.nav in options else 0
        st.session_state.setdefault("navigation_selection", labels[current_index])
        picked = st.radio(
            "Navigation",
            labels,
            index=current_index,
            key="navigation_selection",
            label_visibility="collapsed",
        )
        st.session_state.nav = options[labels.index(picked)]

        st.write("")
        online = backend_is_online()
        st.markdown(f'<span class="sidestatus"><span class="statusdot"></span>'
                    f'{"Backend online" if online else "Backend offline"}</span>', unsafe_allow_html=True)
        st.write("")
        if st.button("Sign out", use_container_width=True):
            if st.session_state.refresh_token:
                api_call("post", "/api/v1/auth/logout", json={"refresh_token": st.session_state.refresh_token})
            theme = st.session_state.theme
            st.session_state.clear()
            st.session_state.theme = theme
            st.rerun()


def page_dashboard() -> None:
    render_topbar("Dashboard")
    user = st.session_state.user or {}
    first_name = str(user.get("name", "there")).split()[0]
    render_hero("Knowledge vector engine", f"Welcome back, {first_name}",
                "Upload documents, ask questions and get answers with sources — all in one secure workspace.")

    documents = fetch_documents()
    ready_count = sum(doc_status(d) == "READY" for d in documents)
    processing_count = sum(doc_status(d) in {"UPLOADED", "PROCESSING", "PENDING"} for d in documents)
    chat_stats = fetch_chat_stats()
    question_count = chat_stats.get("questions_asked", "—") if chat_stats else "—"

    metrics = [
        ("description", len(documents), "Documents", None, False),
        ("verified", ready_count, "Ready to query", None, True),
        ("sync", processing_count, "Processing", "In progress" if processing_count else None, False),
        ("forum", question_count, "Questions asked", None, False),
    ]
    for col, (icon, value, label, tag, ok) in zip(st.columns(4), metrics):
        col.markdown(render_metric(icon, value, label, tag, ok), unsafe_allow_html=True)

    st.write("")
    st.markdown("##### Get started")
    features = [
        ("cloud_upload", "Upload documents", "Add PDFs and we index them for search.", "Go to Documents", "Documents"),
        ("chat", "Ask your documents", "Get direct answers with page-level sources.", "Start chatting", "AI Chat"),
        ("explore", "Get guided", "Walk through processes and policies step by step.", "Open AI Guide", "AI Guide"),
    ]
    for col, (icon, title, desc, button_label, target_page) in zip(st.columns(3), features):
        with col:
            st.markdown(f'<div class="feature"><div class="ico">{msi(icon)}</div>'
                        f'<div class="t">{title}</div><div class="d">{desc}</div></div>', unsafe_allow_html=True)
            st.write("")
            st.button(button_label, key=f"getstarted_{target_page}", use_container_width=True, on_click=go, args=(target_page,))

    if documents:
        st.write("")
        st.markdown(f"##### Recent documents &nbsp;·&nbsp; {len(documents)} total")
        for d in documents[:5]:
            st.markdown(f'<div class="doccard"><div class="left"><div class="ico">{msi("picture_as_pdf")}</div>'
                        f'<div class="name">{html.escape(d.get("filename", "Document"))}</div></div>'
                        f'{render_pill(doc_status(d))}</div>', unsafe_allow_html=True)


@st.fragment(run_every="3s")
def document_list() -> None:
    """Auto-refreshing list so 'Processing' documents flip to 'Ready' live."""
    documents = fetch_documents()
    st.markdown("##### Your documents")
    if not documents:
        render_empty("folder_open", "No documents yet", "Upload your first PDF above to get started.")
        return

    for d in documents:
        status = doc_status(d)
        filename = html.escape(d.get("filename", "Unknown document"))
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
            details.append(str(d["created_at"])[:19].replace("T", " "))
        meta = " · ".join(details)
        error_html = (f'<div class="meta" style="color:var(--err-ink)">{html.escape(str(d.get("error_message")))}</div>'
                     if status == "FAILED" and d.get("error_message") else "")
        left_col, ask_col, delete_col = st.columns([8, 1, 1], vertical_alignment="center")
        with left_col:
            st.markdown(f'''<div class="doccard"><div class="left"><div class="ico">{msi("picture_as_pdf")}</div>
                <div><div class="name">{filename}</div><div class="meta">{meta}{status.title()}</div>{error_html}</div>
                </div>{render_pill(status)}</div>''', unsafe_allow_html=True)
        document_id = doc_id(d)
        if document_id:
            ask_col.button(
                "Ask",
                key=f"ask-document-{document_id}",
                help="Ask about this document",
                on_click=ask_about_document,
                args=(document_id,),
            )
        if document_id and delete_col.button("Delete", key=f"delete_{document_id}", help="Delete document"):
            response = api_call("delete", f"/api/v1/documents/{document_id}")
            if response is not None and response.status_code in (200, 204):
                st.rerun()
            else:
                st.error(api_error(response, "You are not authorized to delete this document.") if response else "Document service is offline.")


def page_documents() -> None:
    render_topbar("Documents")
    render_hero("Vector index engine", "Documents",
                "Upload PDFs to build your searchable knowledge base. Text is extracted per page, so every answer can cite its source.")

    uploaded_files = st.file_uploader(
        "Drag & drop PDFs here, or browse",
        type=["pdf"],
        accept_multiple_files=True,
        key="document-upload",
    )
    st.caption("Multiple files welcome. PDFs are parsed page by page and indexed for search.")
    removed_files = st.session_state.setdefault("removed_uploads", set())
    selected_files = [file for file in (uploaded_files or []) if (file.name, file.size) not in removed_files]
    for index, file in enumerate(selected_files):
        file_col, remove_col = st.columns([9, 1], vertical_alignment="center")
        file_col.markdown(
            f'<div class="doccard"><div class="left"><div class="ico">{msi("picture_as_pdf")}</div>'
            f'<div><div class="name">{html.escape(file.name)}</div>'
            f'<div class="meta">{file.size / 1024:.0f} KB · PDF</div></div></div></div>',
            unsafe_allow_html=True,
        )
        if remove_col.button("Remove", key=f"remove-upload-{index}", help=f"Remove {file.name}"):
            removed_files.add((file.name, file.size))
            st.rerun()

    if selected_files and st.button("Upload & Index", key="upload-index", type="primary", use_container_width=True):
        progress = st.progress(0, text="Preparing uploads")
        accepted = 0
        failures = []
        for index, file in enumerate(selected_files, 1):
            progress.progress((index - 1) / len(selected_files), text=f"Uploading {index} of {len(selected_files)}")
            response = api_call(
                "post",
                "/api/v1/documents",
                files={"file": (file.name, file.getvalue(), "application/pdf")},
            )
            if response is not None and response.status_code in (200, 201, 202):
                accepted += 1
            else:
                message = api_error(response, "Upload failed.") if response else "Document service is offline."
                failures.append((file.name, message))
        progress.progress(1.0, text="Upload requests complete")
        st.session_state.removed_uploads = set()
        for filename, message in failures:
            st.error(f"{filename}: {message}")
        if accepted:
            st.toast(f"{accepted} document(s) accepted for indexing", icon="✅")
            st.rerun()

    document_list()


def page_chat() -> None:
    render_topbar("AI Chat")
    render_hero("Semantic knowledge engine", "AI Document Chat",
                "Ask complex questions and get synthesized, auditable answers grounded in your verified documents.")

    documents = fetch_documents()
    if not documents:
        render_empty("chat", "Nothing to search yet", "Upload at least one PDF, then come back to ask questions.")
        return
    ready_docs = {doc_id(d): d for d in documents if doc_status(d) == "READY" and doc_id(d)}

    left_col, right_col = st.columns([1, 2.4], gap="medium")

    with left_col:
        with st.container(border=True):
            st.markdown("**Search in**")
            st.session_state.setdefault("chat_docs", list(ready_docs))
            st.session_state.chat_docs = [i for i in st.session_state.chat_docs if i in ready_docs]
            select_col, clear_col = st.columns(2)
            if select_col.button("Select all", use_container_width=True):
                st.session_state.chat_docs = list(ready_docs)
                st.rerun()
            if clear_col.button("Clear", use_container_width=True):
                st.session_state.chat_docs = []
                st.rerun()

            for doc_key, d in ready_docs.items():
                checked = st.checkbox(d.get("filename", "Document"), value=doc_key in st.session_state.chat_docs,
                                      key=f"chatdoc_{doc_key}")
                if checked and doc_key not in st.session_state.chat_docs:
                    st.session_state.chat_docs.append(doc_key)
                elif not checked and doc_key in st.session_state.chat_docs:
                    st.session_state.chat_docs.remove(doc_key)
            if not ready_docs:
                st.caption("No ready documents yet.")
            st.caption(f"{len(st.session_state.chat_docs)} of {len(ready_docs)} ready documents selected")

    with right_col:
        with st.container(border=True):
            st.markdown(f"**{msi('chat')} AI Document Chat**", unsafe_allow_html=True)
            st.caption("Answers are grounded in the selected documents and cite file + page")

            if not st.session_state.messages:
                render_empty("chat_bubble", "Ask your first question", "For example: What is our annual leave policy?")
            selected_names = [ready_docs[doc_key].get("filename", "Document") for doc_key in st.session_state.chat_docs]
            if selected_names:
                st.caption("Searching in: " + " · ".join(selected_names))
            for m in st.session_state.messages:
                st.markdown(f'<div class="bubble-user">{html.escape(m["question"])}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="bubble-ai">{msi("smart_toy")} {html.escape(m["answer"])}</div>', unsafe_allow_html=True)
                render_sources(m.get("citations", []))
                st.write("")

            question = st.chat_input("Ask a question about your documents...")
            if question:
                if not st.session_state.chat_docs:
                    st.warning("Select at least one document.")
                else:
                    with st.spinner("Searching your documents..."):
                        result = ask_ai(question, st.session_state.chat_docs, st.session_state.conversation_id)
                    if result is None:
                        st.error("Unable to connect to the AI backend.")
                    elif "error" in result:
                        st.error(result["error"])
                    else:
                        st.session_state.conversation_id = result.get("conversation_id")
                        answer = answer_text(result)
                        if not result.get("has_answer", True):
                            answer = "I couldn't find a sufficiently relevant answer in the selected documents."
                        st.session_state.messages.append({
                            "question": question, "answer": answer, "citations": result.get("citations", []),
                        })
                        st.rerun()


def page_guide() -> None:
    render_topbar("AI Guide")
    render_hero("Autonomous synthesis", "AI Guide",
                "Describe what you need to do and get step-by-step guidance grounded in your company's documents.")

    st.markdown("**Quick presets**")
    presets = [
        "Guide me through employee onboarding",
        "How do I request leave?",
        "Summarize our security policy",
    ]
    for col, prompt in zip(st.columns(len(presets)), presets):
        if col.button(prompt, key=f"preset_{prompt}", use_container_width=True):
            st.session_state.guide_q = prompt

    question = st.text_area("Describe your task or scenario", key="guide_q", height=110,
                            placeholder="Example: Guide me through the employee onboarding process.")

    if st.button("Get guidance", type="primary", use_container_width=True):
        if not question.strip():
            st.warning("Tell the AI what you need help with.")
            return
        documents = fetch_documents()
        ready_ids = [doc_id(d) for d in documents if doc_status(d) == "READY" and doc_id(d)]
        if not ready_ids:
            st.warning("No ready documents are available to guide you yet.")
            return
        with st.spinner("Analyzing your documents..."):
            result = ask_guide(question, ready_ids)
        if "error" in result:
            st.error(result["error"])
        else:
            st.session_state.guide_result = result

    result = st.session_state.guide_result
    if result:
        st.write("")
        st.markdown(f'''<div class="step"><div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
            <div class="idx">{msi("explore")}</div><b style="font-size:15px">Guidance</b></div>
            {html.escape(result.get("reply", "No guidance returned."))}</div>''', unsafe_allow_html=True)
        if result.get("pending_confirmation"):
            st.info("This request needs your confirmation before the backend can perform the action.")
        citations = []
        for tool_call in result.get("tool_calls", []):
            tool_result = tool_call.get("result")
            if isinstance(tool_result, dict):
                citations.extend(tool_result.get("citations", []))
        render_sources(citations)


def page_history() -> None:
    render_topbar("History")
    render_hero("Session log", "Conversation history", "Everything you have asked, with the sources behind each answer.")
    conversations = fetch_history()
    if not conversations:
        render_empty("history", "No conversations yet", "Your saved questions and answers will appear here.")
        return
    for conversation in conversations:
        title = conversation.get("title") or "Untitled conversation"
        updated = conversation.get("updated_at") or conversation.get("created_at")
        with st.expander(f"{title} · {str(updated or '')[:19]}"):
            for message in conversation.get("messages", []):
                if message.get("role") == "user":
                    st.markdown("**Question**")
                    st.write(message.get("content", ""))
                elif message.get("role") == "assistant":
                    st.markdown("**Answer**")
                    st.markdown(message.get("content", ""))
                    render_sources(message.get("citations") or [], expandable=False)


def page_admin() -> None:
    role = str((st.session_state.user or {}).get("role", "")).upper()
    if role not in ("ADMIN", "SUPER_ADMIN"):
        st.error("You are not authorized to access the Admin Dashboard.")
        return

    render_topbar("Admin Dashboard")
    render_hero("System control", "Admin dashboard", "Monitor document processing and backend health.")
    stats_response = api_call("get", "/api/v1/admin/dashboard")
    health_response = api_call("get", "/api/v1/admin/health")
    if stats_response is None or stats_response.status_code != 200:
        st.error(api_error(stats_response, "Admin statistics are unavailable.") if stats_response else "Backend offline.")
        return
    stats = stats_response.json()
    metrics = [
        ("description", stats.get("total_documents", 0), "Documents", None, False),
        ("verified", stats.get("ready_documents", 0), "Ready", None, True),
        ("sync", stats.get("processing_documents", 0), "Processing", None, False),
        ("warning", stats.get("failed_documents", 0), "Failed", None, False),
    ]
    for col, (icon, value, label, tag, ok) in zip(st.columns(4), metrics):
        col.markdown(render_metric(icon, value, label, tag, ok), unsafe_allow_html=True)

    st.markdown("##### Knowledge base")
    knowledge = [
        ("menu_book", stats.get("total_pages", 0), "Pages", None, False),
        ("view_agenda", stats.get("total_chunks", 0), "Chunks", None, False),
        ("database", stats.get("searchable_documents", 0), "Searchable documents", None, False),
    ]
    for col, (icon, value, label, tag, ok) in zip(st.columns(3), knowledge):
        col.markdown(render_metric(icon, value, label, tag, ok), unsafe_allow_html=True)

    st.write("")
    st.markdown("##### System health")
    if health_response is None or health_response.status_code != 200:
        st.warning(api_error(health_response, "System health details are unavailable.") if health_response else "System health details are unavailable.")
    else:
        health = health_response.json()
        health_items = [
            ("Backend", health.get("status", "unknown")),
            ("Database", health.get("database", "unknown")),
            ("Vector store", health.get("vector_store", "unknown")),
            ("AI model", health.get("llm", "unknown")),
        ]
        with st.container(border=True):
            for col, (label, value) in zip(st.columns(4), health_items):
                col.caption(label)
                col.markdown(f"**{str(value).replace('_', ' ').title()}**")

    st.markdown("##### Knowledge documents")
    documents = []
    total_documents = 0
    page = 1
    while True:
        response = api_call("get", "/api/v1/admin/documents", params={"page": page, "page_size": 100})
        if response is None or response.status_code != 200:
            if page == 1:
                st.error(api_error(response, "Document inventory is unavailable.") if response else "Document inventory is unavailable.")
                return
            st.warning("Some document pages could not be loaded.")
            break
        try:
            data = response.json()
        except ValueError:
            st.warning("The document inventory response could not be read.")
            break
        page_documents = data.get("documents", [])
        documents.extend(page_documents)
        total_documents = int(data.get("total", len(documents)))
        if len(documents) >= total_documents or not page_documents:
            break
        page += 1
    st.caption(f"Showing {len(documents)} of {total_documents} documents")
    headers = st.columns([3, 2, 0.7, 0.7, 1, 1.3, 0.8])
    for col, label in zip(headers, ["Document", "Owner", "Pages", "Chunks", "Status", "Uploaded", ""]):
        col.caption(label)
    for document in documents:
        row = st.columns([3, 2, 0.7, 0.7, 1, 1.3, 0.8], vertical_alignment="center")
        row[0].write(document.get("filename", "Document"))
        row[1].caption(f"{document.get('owner_name', '')}\n{document.get('owner_email', '')}")
        row[2].write(document.get("page_count") if document.get("page_count") is not None else "")
        row[3].write(document.get("chunk_count") if document.get("chunk_count") is not None else "")
        row[4].markdown(render_pill(doc_status(document)), unsafe_allow_html=True)
        row[5].caption(str(document.get("created_at", ""))[:19])
        document_id = document.get("document_id")
        if document_id and row[6].button("Delete", key=f"admin-delete-{document_id}", help="Delete document"):
            delete_response = api_call("delete", f"/api/v1/documents/{document_id}")
            if delete_response is not None and delete_response.status_code in (200, 204):
                st.rerun()
            st.error(api_error(delete_response, "Unable to delete document.") if delete_response else "Document service is offline.")


# ============================================================================
# 6. MAIN
# ============================================================================

PAGE_RENDERERS = {
    "Dashboard": page_dashboard,
    "Documents": page_documents,
    "AI Chat": page_chat,
    "AI Guide": page_guide,
    "History": page_history,
    ADMIN_PAGE: page_admin,
}


def main() -> None:
    if not st.session_state.token:
        page_auth()
        return
    render_sidebar()
    PAGE_RENDERERS.get(st.session_state.nav, page_dashboard)()


if __name__ == "__main__":
    main()