"""
Enterprise AI — Knowledge & Document Intelligence
==================================================
Streamlit entry point for the FastAPI frontend, organized into three sections:

    1. CONFIG & STATE      - Streamlit setup and session defaults
    2. THEME               - centralized light/dark tokens and shared styles
    3. MAIN                - routes pages inside the shared application shell

Run with:  streamlit run frontend/streamlit_app.py
"""

import streamlit as st
import streamlit.components.v1 as components
from frontend.components import render_app_shell
from frontend.constants import SESSION_DEFAULTS
from frontend.pages import PAGE_RENDERERS, page_auth, page_dashboard

# ============================================================================
# 1. CONFIG & STATE
# ============================================================================

st.set_page_config(page_title="Enterprise AI", page_icon="✨", layout="wide", initial_sidebar_state="auto")
for _key, _val in SESSION_DEFAULTS.items():
    st.session_state.setdefault(_key, _val)

try:
    saved_theme = st.context.cookies.get("enterprise-ai-theme", "")
except Exception:
    saved_theme = ""
requested_theme = str(st.query_params.get("theme", saved_theme or st.session_state.theme)).lower()
if requested_theme in {"light", "dark"}:
    st.session_state.theme = requested_theme
theme_storage_bridge = """
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
"""
components.html(theme_storage_bridge + f"<!-- theme:{st.session_state.theme} -->", height=0)


# ============================================================================
# 2. THEME
# ============================================================================

LIGHT_TOKENS = dict(
    bg="#fdf8ff", surface="#ffffff", surface2="#f7f1ff", input="#ffffff", border="#e7e4fb",
    ink="#1b1735", muted="#474555", secondary="#006b5c", primary="#6d5bff", primary2="#533ee5",
    on_primary="#ffffff", chip="#e4dfff", chip_ink="#3c1bcf",
    ok="#e4fbf6", ok_ink="#008f7c", warn="#fff4e0", warn_ink="#a66b00",
    err="#fdebeb", err_ink="#d93838", hero="linear-gradient(135deg, #7a5cff 0%, #8f5bff 50%, #00c2a8 100%)",
)
DARK_TOKENS = dict(
    bg="#12101e", surface="#1b172e", surface2="#1e1a33", input="#19152b", border="#363056",
    ink="#f4eeff", muted="#9d97bf", secondary="#41ddc2", primary="#8b7cff", primary2="#9e91ff",
    on_primary="#12101e", chip="#342c5b", chip_ink="#e4dfff",
    ok="#10362c", ok_ink="#41ddc2", warn="#382a12", warn_ink="#ffb020",
    err="#3d1a1e", err_ink="#ff7a70", hero="linear-gradient(135deg, #2b1f5c 0%, #4d37e6 50%, #006b5c 100%)",
)
T = DARK_TOKENS if st.session_state.theme == "dark" else LIGHT_TOKENS

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

:root {{
  --bg:{T['bg']}; --surface:{T['surface']}; --surface2:{T['surface2']}; --border:{T['border']};
  --ink:{T['ink']}; --muted:{T['muted']}; --secondary:{T['secondary']}; --primary:{T['primary']}; --primary2:{T['primary2']};
  --input-bg:{T['input']}; --on-primary:{T['on_primary']}; --chip:{T['chip']}; --chip-ink:{T['chip_ink']};
  --ok:{T['ok']}; --ok-ink:{T['ok_ink']}; --warn:{T['warn']}; --warn-ink:{T['warn_ink']};
  --err:{T['err']}; --err-ink:{T['err_ink']}; --hero:{T['hero']};
}}

.msi {{
  font-family: 'Material Symbols Outlined';
  font-weight: 400;
  font-style: normal;
  font-size: 20px;
  line-height: 1;
  display: inline-block;
  vertical-align: middle;
  -webkit-font-feature-settings: 'liga';
}}
.msi.fill {{ font-variation-settings: 'FILL' 1; }}

html, body, [class*="css"], .stApp {{
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}}
.stApp {{
  background: var(--bg);
  color: var(--ink);
}}

#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {{
  display: none !important;
}}
header[data-testid="stHeader"] {{
  background: transparent;
}}
.block-container {{
  padding-top: 1.2rem;
  max-width: 1400px;
}}

/* Sidebar Styling */
section[data-testid="stSidebar"] {{
  background: var(--surface2);
  border-right: 1px solid var(--border);
  box-shadow: 0 1px 8px rgba(0, 0, 0, 0.04);
}}
h1, h2, h3, h4 {{
  letter-spacing: -0.02em;
  color: var(--ink);
  font-weight: 700;
}}
p, span, div, label {{
  color: var(--ink);
}}

/* ---- Topbar Header ---- */
.topbar {{
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 10px 20px;
  margin-bottom: 24px;
  box-shadow: 0 2px 10px -2px rgba(109, 91, 255, 0.04), 0 1px 3px 0 rgba(28, 24, 54, 0.02);
}}
.topbar .crumb {{
  font-size: 14px;
  color: var(--muted);
  font-weight: 500;
}}
.topbar .crumb b {{
  color: var(--ink);
  font-weight: 700;
}}
.topbar .status {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ok-ink);
  background: var(--ok);
  padding: 4px 12px;
  border-radius: 999px;
}}
.statusdot {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #00c2a8;
  box-shadow: 0 0 8px #00c2a8;
}}

/* ---- Hero Banner ---- */
.hero {{
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 20px;
  padding: 32px 36px;
  margin-bottom: 24px;
  color: #ffffff;
  background: var(--hero);
  box-shadow: 0 12px 28px -6px rgba(109, 91, 255, 0.28);
}}
.hero:after {{
  content: "";
  position: absolute;
  right: -40px;
  top: -40px;
  width: 240px;
  height: 240px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.18);
  filter: blur(40px);
  pointer-events: none;
}}
.hero:before {{
  content: "";
  position: absolute;
  left: 25%;
  bottom: -80px;
  width: 220px;
  height: 220px;
  border-radius: 50%;
  background: rgba(0, 194, 168, 0.25);
  filter: blur(40px);
  pointer-events: none;
}}
.hero .eyebrow {{
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(8px);
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #ffffff;
}}
.hero h1 {{
  position: relative;
  z-index: 1;
  font-size: 32px;
  font-weight: 800;
  margin: 14px 0 8px;
  color: #ffffff;
  line-height: 1.15;
}}
.hero p {{
  position: relative;
  z-index: 1;
  font-size: 15px;
  color: rgba(255, 255, 255, 0.92);
  margin: 0;
  max-width: 680px;
  line-height: 1.6;
}}

/* ---- Metric Cards ---- */
.metric {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 116px;
  box-shadow: 0 2px 10px -2px rgba(109, 91, 255, 0.04), 0 1px 3px 0 rgba(28, 24, 54, 0.02);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
.metric:hover {{
  transform: translateY(-2px);
  box-shadow: 0 8px 20px -4px rgba(109, 91, 255, 0.1);
}}
.metric .head {{
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}}
.metric .lbl {{
  color: var(--muted);
  font-size: 11.5px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  font-weight: 700;
}}
.metric .ico {{
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--primary) 0%, #00c2a8 100%);
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 4px 12px rgba(109, 91, 255, 0.2);
}}
.metric .num {{
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
  margin-top: 12px;
  letter-spacing: -0.02em;
}}
.metric .tag {{
  font-size: 11.5px;
  font-weight: 600;
  color: var(--muted);
  margin-top: 6px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}}
.metric .tag.ok {{
  color: var(--ok-ink);
}}

/* ---- Feature Cards ---- */
.feature {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  box-shadow: 0 2px 10px -2px rgba(109, 91, 255, 0.04);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
.feature:hover {{
  transform: translateY(-2px);
  box-shadow: 0 10px 24px -4px rgba(109, 91, 255, 0.12);
}}
.feature .ico {{
  width: 46px;
  height: 46px;
  border-radius: 12px;
  background: var(--surface2);
  color: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}}
.feature .t {{
  font-weight: 700;
  font-size: 16px;
}}
.feature .d {{
  color: var(--muted);
  font-size: 13.5px;
  line-height: 1.55;
}}

/* ---- Document Cards ---- */
.doccard {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px 18px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02);
  transition: background-color 0.15s ease;
}}
.doccard:hover {{
  background: var(--surface2);
}}
.doccard .left {{
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}}
.doccard .ico {{
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--surface2);
  color: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}}
.doccard .name {{
  font-weight: 600;
  font-size: 14.5px;
  word-break: break-all;
}}
.doccard .meta {{
  color: var(--muted);
  font-size: 12px;
  margin-top: 2px;
}}

/* ---- Status Pills ---- */
.pill {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 700;
  white-space: nowrap;
}}
.p-ready {{
  background: var(--ok);
  color: var(--ok-ink);
}}
.p-proc {{
  background: var(--warn);
  color: var(--warn-ink);
}}
.p-fail {{
  background: var(--err);
  color: var(--err-ink);
}}
.p-other {{
  background: var(--chip);
  color: var(--chip-ink);
}}
.dot {{
  width: 6px;
  height: 6px;
  border-radius: 50%;
}}
.dot-ready {{ background: var(--ok-ink); }}
.dot-proc {{ background: var(--warn-ink); animation: pulse 1.5s infinite; }}
.dot-fail {{ background: var(--err-ink); }}
.dot-other {{ background: var(--chip-ink); }}

@keyframes pulse {{
  0% {{ opacity: 0.4; }}
  50% {{ opacity: 1; }}
  100% {{ opacity: 0.4; }}
}}

/* ---- Sidebar & Nav ---- */
.brand {{
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.02em;
  display: flex;
  flex-direction: column;
  gap: 2px;
}}
.brand span {{
  color: var(--muted);
  font-weight: 500;
  font-size: 11.5px;
  letter-spacing: 0em;
}}
.sideprofile {{
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--surface2);
  border: 1px solid var(--border);
}}
.sideavatar {{
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary2) 100%);
  color: #ffffff;
  font-weight: 800;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 4px 10px rgba(109, 91, 255, 0.25);
}}
.role {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 700;
  background: var(--chip);
  color: var(--chip-ink);
}}
.sidestatus {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--ok-ink);
  background: var(--ok);
  padding: 6px 14px;
  border-radius: 999px;
  width: 100%;
  justify-content: center;
}}

/* ---- Chat Bubbles & Citations ---- */
.bubble-user {{
  background: var(--primary);
  color: #ffffff;
  border-radius: 18px 18px 4px 18px;
  padding: 14px 18px;
  max-width: 82%;
  margin-left: auto;
  font-size: 14.5px;
  line-height: 1.55;
  box-shadow: 0 4px 14px rgba(109, 91, 255, 0.2);
}}
.bubble-ai {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px 18px 18px 4px;
  padding: 18px;
  font-size: 14.5px;
  line-height: 1.6;
  box-shadow: 0 2px 10px -2px rgba(109, 91, 255, 0.04);
}}
.citebox {{
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 14px;
  margin-top: 10px;
}}
.citecard {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}}
.citecard .fn {{
  font-weight: 600;
  font-size: 13px;
}}
.citecard .pg {{
  font-size: 11px;
  background: var(--chip);
  color: var(--chip-ink);
  padding: 3px 9px;
  border-radius: 6px;
  font-weight: 600;
  white-space: nowrap;
}}

/* ---- Guide Step Card ---- */
.step {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
  margin-bottom: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02);
}}
.step .idx {{
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: var(--primary);
  color: #ffffff;
  font-weight: 700;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}}

/* ---- Streamlit Widget Overrides ---- */
.stButton > button, .stFormSubmitButton > button {{
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--ink);
  font-weight: 600;
  padding: 0.5rem 1.1rem;
  transition: all 0.15s ease;
}}
.stButton > button:hover {{
  border-color: var(--primary);
  color: var(--primary);
  box-shadow: 0 4px 12px rgba(109, 91, 255, 0.1);
}}
.stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"] {{
  background: var(--primary);
  border: 1px solid var(--primary);
  color: #ffffff;
  box-shadow: 0 4px 14px rgba(109, 91, 255, 0.28);
}}
.stButton > button[kind="primary"]:hover, .stButton > button[data-testid="stBaseButton-primary"]:hover {{
  background: var(--primary2);
  border-color: var(--primary2);
  color: #ffffff;
  box-shadow: 0 6px 18px rgba(109, 91, 255, 0.35);
}}
.stTextInput input, .stTextArea textarea, [data-testid="stChatInput"] textarea, div[data-baseweb="select"] > div {{
  background: var(--input-bg) !important;
  border: 1px solid var(--border) !important;
  border-radius: 12px !important;
  color: var(--ink) !important;
}}
.stTextInput input:focus, .stTextArea textarea:focus {{
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px rgba(109, 91, 255, 0.18) !important;
}}
[data-testid="stVerticalBlockBorderWrapper"] {{
  border-radius: 16px;
  border-color: var(--border);
  background: var(--surface);
  box-shadow: 0 2px 8px rgba(0,0,0,0.02);
}}
[data-testid="stFileUploaderDropzone"] {{
  background: var(--surface2);
  border: 1.5px dashed var(--border);
  border-radius: 16px;
}}
.stTabs [data-baseweb="tab-list"] {{
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 4px;
  background: var(--surface2);
}}
.stTabs [data-baseweb="tab"] {{
  border: 1px solid transparent;
  border-radius: 9px;
  padding: 8px 16px;
  color: var(--muted);
  font-weight: 600;
}}
.stTabs [aria-selected="true"] {{
  background: var(--surface);
  color: var(--primary) !important;
  border-color: var(--border);
  box-shadow: 0 2px 6px rgba(0,0,0,0.04);
}}
section[data-testid="stSidebar"] [role="radiogroup"] label {{
  padding: 10px 14px;
  border: 1px solid transparent;
  border-radius: 10px;
  margin-bottom: 3px;
  transition: all 0.15s ease;
}}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover {{
  background: var(--surface2);
}}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
  background: var(--primary);
  color: #ffffff;
  border-color: var(--primary);
  box-shadow: 0 4px 12px rgba(109, 91, 255, 0.25);
}}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) span {{
  color: #ffffff !important;
  font-weight: 600 !important;
}}
section[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child {{
  display: none;
}}
.stCheckbox input[type="checkbox"], .stRadio input[type="radio"] {{
  accent-color: var(--primary);
  border: 1px solid var(--border);
}}
.stButton > button:disabled, .stFormSubmitButton > button:disabled {{
  opacity: 0.58;
  border-color: var(--border);
  color: var(--muted);
  cursor: not-allowed;
}}
.stCaption, [data-testid="stCaptionContainer"] {{
  color: var(--muted) !important;
}}
</style>
""", unsafe_allow_html=True)


# ============================================================================
# 3. MAIN
# ============================================================================

def main() -> None:
    if not st.session_state.token:
        page_auth()
        return
    page = render_app_shell()
    PAGE_RENDERERS.get(page, page_dashboard)()


if __name__ == "__main__":
    main()