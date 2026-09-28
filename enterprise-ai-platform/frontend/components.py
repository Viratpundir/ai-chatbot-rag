"""Shared rendering components used by every Streamlit page."""

import html

import streamlit as st

from frontend.api import api_call, backend_is_online
from frontend.constants import ADMIN_PAGE, PAGES


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


@st.fragment(run_every="15s")
def render_backend_status() -> None:
    online = backend_is_online()
    color = "#0f8f5f" if online else "#ba1a1a"
    label = "Backend online" if online else "Backend offline"
    st.markdown(
        f'<div class="status"><span class="statusdot" style="background:{color}"></span>{label}</div>',
        unsafe_allow_html=True,
    )


def render_topbar(page_label: str) -> None:
    user = st.session_state.user or {}
    crumb_col, status_col, theme_col = st.columns([7, 3, 0.8], vertical_alignment="center")
    with crumb_col:
        st.markdown(
            f'<div class="topbar">'
            f'<div class="crumb"><b>Enterprise AI</b> &nbsp;/&nbsp; {html.escape(page_label)}</div>'
            f'<div style="font-size:12.5px;color:var(--muted);display:flex;align-items:center;gap:6px">'
            f'{msi("search")} Search document citations, vectors, insights...</div></div>',
            unsafe_allow_html=True,
        )
    with status_col:
        render_backend_status()
    toggle_theme_button(theme_col)


def render_hero(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(
        f'''<div class="hero">
            <span class="eyebrow">{msi("auto_awesome")} {html.escape(eyebrow)}</span>
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(subtitle)}</p>
        </div>''',
        unsafe_allow_html=True,
    )


def render_metric(icon: str, value, label: str, tag: str = None, ok: bool = False, bg_gradient: str = None) -> str:
    tag_html = f'<div class="tag{" ok" if ok else ""}">{html.escape(tag)}</div>' if tag else ""
    icon_style = f' style="background:{bg_gradient}"' if bg_gradient else ''
    return f'''<div class="metric">
        <div class="head">
            <div class="lbl">{html.escape(label)}</div>
            <div class="ico"{icon_style}>{msi(icon)}</div>
        </div>
        <div>
            <div class="num">{value}</div>
            {tag_html}
        </div>
    </div>'''


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
    st.markdown(
        f'<div class="empty">{msi(icon)}<b style="font-size:16px;margin-top:8px">{html.escape(title)}</b>'
        f'<div style="font-size:13.5px;color:var(--muted);margin-top:4px">{html.escape(text)}</div></div>',
        unsafe_allow_html=True,
    )


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


def render_sidebar() -> None:
    user = st.session_state.user or {}
    role = str(user.get("role", "EMPLOYEE")).upper()
    is_admin = role in ("ADMIN", "SUPER_ADMIN")

    with st.sidebar:
        st.markdown(
            '<div class="brand" style="display:flex;align-items:center;gap:10px;padding:6px 0 12px">'
            '<div style="width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,var(--primary) 0%,#00c2a8 100%);color:#fff;'
            'display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(109,91,255,0.3)">'
            + msi("auto_awesome") +
            '</div>'
            '<div><div style="font-weight:800;font-size:16px;line-height:1.2">Enterprise AI</div>'
            '<span style="font-size:11px;color:var(--muted);display:block">Knowledge & Document Intelligence</span></div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.write("")
        st.markdown(
            f'''<div class="sideprofile">
                <div class="sideavatar">{html.escape(user.get("name", "U")[:1].upper())}</div>
                <div style="min-width:0;flex:1">
                    <div style="display:flex;align-items:center;justify-content:space-between">
                        <b style="font-size:13.5px;font-weight:700;overflow:hidden;text-overflow:ellipsis">{html.escape(user.get("name", "User"))}</b>
                        <span class="role">{role.replace("_", " ").title()}</span>
                    </div>
                    <div style="color:var(--muted);font-size:11.5px;overflow:hidden;text-overflow:ellipsis">{html.escape(user.get("email", ""))}</div>
                </div>
            </div>''',
            unsafe_allow_html=True,
        )
        st.write("")

        options = PAGES + ([ADMIN_PAGE] if is_admin else [])
        labels = [f"{page}" for page in options]
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
        st.markdown(
            f'<span class="sidestatus"><span class="statusdot"></span>'
            f'{"Backend online · http://127.0.0.1:8000" if online else "Backend offline"}</span>',
            unsafe_allow_html=True,
        )
        st.write("")
        if st.button("Sign out", use_container_width=True):
            if st.session_state.refresh_token:
                api_call("post", "/api/v1/auth/logout", json={"refresh_token": st.session_state.refresh_token})
            theme = st.session_state.theme
            st.session_state.clear()
            st.session_state.theme = theme
            st.rerun()


def render_app_shell() -> str:
    """Render the shared authenticated sidebar and topbar, then return the selected page."""
    render_sidebar()
    page = st.session_state.nav
    user = st.session_state.user or {}
    role = str(user.get("role", "")).upper()
    if page == ADMIN_PAGE and role not in ("ADMIN", "SUPER_ADMIN"):
        return page
    render_topbar(page)
    return page
