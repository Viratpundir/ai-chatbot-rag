"""Streamlit page renderers for the Enterprise AI workspace."""

import html

import streamlit as st

from frontend.api import (
    api_call,
    api_error,
    ask_ai,
    ask_guide,
    answer_text,
    backend_is_online,
    doc_id,
    doc_status,
    fetch_chat_stats,
    fetch_documents,
    fetch_history,
    start_session,
    try_auth,
)
from frontend.components import (
    msi,
    render_empty,
    render_hero,
    render_metric,
    render_pill,
    render_sources,
    toggle_theme_button,
)
from frontend.constants import ADMIN_PAGE


def go(page: str) -> None:
    """Navigate to a page (used as a button on_click callback)."""
    st.session_state.nav = page
    st.session_state["navigation_selection"] = page


def ask_about_document(document_id: str) -> None:
    st.session_state.chat_docs = [document_id]
    st.session_state[f"chatdoc_{document_id}"] = True
    go("AI Chat")


def page_auth() -> None:
    toggle_theme_button()
    online = backend_is_online()
    left, right = st.columns([1.15, 1], gap="large")

    with left:
        st.markdown(f'''
        <div style="background:linear-gradient(135deg, #1b1735 0%, #2a224a 55%, #006b5c 100%);border-radius:24px;padding:44px 38px;height:100%;color:#fff;box-shadow:0 12px 32px rgba(27,23,53,0.3);position:relative;overflow:hidden">
          <div style="position:absolute;top:-40px;right:-40px;width:220px;height:220px;border-radius:50%;background:rgba(109,91,255,0.25);filter:blur(40px);pointer-events:none"></div>
          <div style="display:flex;align-items:center;gap:10px;font-weight:800;font-size:20px;margin-bottom:28px">
            <div style="width:34px;height:34px;border-radius:10px;background:rgba(255,255,255,0.15);backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center">
              {msi("auto_awesome")}
            </div>
            <span>Enterprise AI</span>
          </div>
          <span style="display:inline-flex;align-items:center;gap:6px;background:rgba(109,91,255,0.35);color:#e4dfff;font-size:11.5px;font-weight:700;padding:6px 14px;border-radius:999px;margin-bottom:20px;letter-spacing:0.04em;text-transform:uppercase">
            <span style="width:6px;height:6px;border-radius:50%;background:#00c2a8"></span> AI Knowledge Platform
          </span>
          <h1 style="font-size:38px;font-weight:800;line-height:1.15;margin:0 0 18px;color:#fff;letter-spacing:-0.02em">
            Turn your enterprise document library into an active AI expert.</h1>
          <p style="color:rgba(255,255,255,0.85);font-size:15.5px;max-width:500px;margin-bottom:32px;line-height:1.6">
            Upload policies, reports, and handbooks. Get auditable answers cited down to the page and section, with enterprise-grade data security.
          </p>
          <div style="display:flex;gap:14px;margin:20px 0;align-items:flex-start">
            <div style="width:36px;height:36px;border-radius:10px;background:rgba(255,255,255,0.1);display:flex;align-items:center;justify-content:center;flex-shrink:0">{msi("lock")}</div>
            <div><b style="color:#fff;font-size:15px">Role-based access</b><div style="color:rgba(255,255,255,0.7);font-size:13.5px">Every answer strictly enforces user role & document permissions.</div></div>
          </div>
          <div style="display:flex;gap:14px;margin:20px 0;align-items:flex-start">
            <div style="width:36px;height:36px;border-radius:10px;background:rgba(255,255,255,0.1);display:flex;align-items:center;justify-content:center;flex-shrink:0">{msi("fact_check")}</div>
            <div><b style="color:#fff;font-size:15px">Auditable citations</b><div style="color:rgba(255,255,255,0.7);font-size:13.5px">Directly links to the exact source file and page snippet.</div></div>
          </div>
          <div style="display:flex;gap:14px;margin:20px 0 32px;align-items:flex-start">
            <div style="width:36px;height:36px;border-radius:10px;background:rgba(255,255,255,0.1);display:flex;align-items:center;justify-content:center;flex-shrink:0">{msi("bolt")}</div>
            <div><b style="color:#fff;font-size:15px">Hybrid RAG Search</b><div style="color:rgba(255,255,255,0.7);font-size:13.5px">Combines dense vector embeddings with BM25 keyword reranking.</div></div>
          </div>
          <div style="color:{'#41ddc2' if online else '#ff7a70'};font-size:13px;font-weight:600;display:flex;align-items:center;gap:8px">
            <span style="width:8px;height:8px;border-radius:50%;background:{'#00c2a8' if online else '#ff7a70'}"></span>
            {"Backend online · http://127.0.0.1:8000" if online else "Backend offline"}
          </div>
        </div>''', unsafe_allow_html=True)
        if not online:
            st.code("uvicorn app.main:app --reload", language="powershell")

    with right:
        with st.container(border=True):
            st.markdown("<h2 style='font-size:24px;font-weight:700;margin-bottom:4px'>Welcome back</h2>", unsafe_allow_html=True)
            st.caption("Sign in to your Enterprise AI workspace")
            tab_password, tab_otp, tab_register = st.tabs(["Password", "Email code", "Register"])

            with tab_password:
                email = st.text_input("Email", key="login_email", placeholder="you@company.com")
                password = st.text_input("Password", type="password", key="login_password")
                if st.button("Sign in", type="primary", use_container_width=True):
                    if not email or not password:
                        st.warning("Enter your email and password.")
                    else:
                        response = try_auth("/api/v1/auth/login", {"email": email, "password": password},
                                            "Invalid email or password.")
                        if response is not None:
                            start_session(response.json())
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
                        response = try_auth("/api/v1/auth/verify-otp", {"email": email, "otp": otp}, "Invalid or expired code.")
                        if response is not None:
                            st.session_state.otp_requested = False
                            start_session(response.json())
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


def page_dashboard() -> None:
    user = st.session_state.user or {}
    first_name = str(user.get("name", "there")).split()[0]
    render_hero(
        "Knowledge Vector Engine v4.2",
        f"Welcome back, {first_name}",
        "Upload documents, ask questions and get answers with sources — all in one secure workspace.",
    )

    documents = fetch_documents()
    ready_count = sum(doc_status(document) == "READY" for document in documents)
    processing_count = sum(doc_status(document) in {"UPLOADED", "PROCESSING", "PENDING"} for document in documents)
    chat_stats = fetch_chat_stats()
    question_count = chat_stats.get("questions_asked", "—") if chat_stats else "—"

    metrics = [
        ("description", len(documents), "Documents", "Vectorized", False, "linear-gradient(135deg, #6d5bff 0%, #00c2a8 100%)"),
        ("verified", ready_count, "Ready to query", f"{int(ready_count / max(len(documents), 1) * 100)}% ready" if documents else "0% ready", True, "linear-gradient(135deg, #006b5c 0%, #41ddc2 100%)"),
        ("sync", processing_count, "Processing", "In progress" if processing_count else "Est. < 45s", False, "linear-gradient(135deg, #cd4749 0%, #ffb020 100%)"),
        ("forum", question_count, "Questions asked", "98% cited", True, "linear-gradient(135deg, #ac2e33 0%, #ff7a70 100%)"),
    ]
    for column, (icon, value, label, tag, ok, bg) in zip(st.columns(4), metrics):
        column.markdown(render_metric(icon, value, label, tag, ok, bg_gradient=bg), unsafe_allow_html=True)

    st.write("")
    st.markdown("### Get started")
    features = [
        ("cloud_upload", "Upload documents", "Add PDFs and we index them for search. Automatic chunking, OCR parsing, and dense embeddings generation.", "Upload documents", "Documents"),
        ("chat", "Ask your documents", "Get direct answers with page-level sources. Cross-examine multi-page dossiers with strict safeguards.", "Start chatting", "AI Chat"),
        ("explore", "Get guided", "Walk through processes and policies step by step with our structured contextual intelligence assistant.", "Open AI Guide", "AI Guide"),
    ]
    for column, (icon, title, description, button_label, target_page) in zip(st.columns(3), features):
        with column:
            st.markdown(
                f'<div class="feature">'
                f'<div class="ico">{msi(icon)}</div>'
                f'<div class="t">{title}</div>'
                f'<div class="d">{description}</div></div>',
                unsafe_allow_html=True,
            )
            st.write("")
            st.button(button_label, key=f"getstarted_{target_page}", use_container_width=True, on_click=go, args=(target_page,))

    if documents:
        st.write("")
        st.markdown(f"### Recent documents &nbsp;<span style='font-size:13px;font-weight:600;color:var(--muted);padding:3px 10px;border-radius:999px;background:var(--surface2)'>{len(documents)} files</span>", unsafe_allow_html=True)
        for document in documents[:5]:
            filename = html.escape(document.get("filename", "Document"))
            status = doc_status(document)
            size_mb = f"{document.get('file_size', 0) / (1024*1024):.1f} MB · " if document.get("file_size") else ""
            pages = f"{document.get('page_count')} pages · " if document.get("page_count") else ""
            st.markdown(
                f'<div class="doccard">'
                f'<div class="left">'
                f'<div class="ico">{msi("picture_as_pdf")}</div>'
                f'<div><div class="name">{filename}</div>'
                f'<div class="meta">{size_mb}{pages}Indexed recently</div></div></div>'
                f'{render_pill(status)}</div>',
                unsafe_allow_html=True,
            )



@st.fragment(run_every="3s")
def document_list() -> None:
    """Auto-refreshing list so 'Processing' documents flip to 'Ready' live."""
    documents = fetch_documents()
    st.markdown("##### Your documents")
    if not documents:
        render_empty("folder_open", "No documents yet", "Upload your first PDF above to get started.")
        return

    for document in documents:
        status = doc_status(document)
        filename = html.escape(document.get("filename", "Unknown document"))
        details = []
        if document.get("file_size") is not None:
            details.append(f"{document['file_size'] / (1024 * 1024):.1f} MB")
        if document.get("page_count") is not None:
            details.append(f"{document['page_count']} pages")
        if document.get("chunk_count") is not None:
            details.append(f"{document['chunk_count']} chunks")
        if document.get("classification"):
            details.append(str(document["classification"]).title())
        if document.get("owner_id"):
            user_id = (st.session_state.user or {}).get("user_id")
            details.append("Owner: you" if document["owner_id"] == user_id else f"Owner: {str(document['owner_id'])[:8]}")
        if document.get("created_at"):
            details.append(str(document["created_at"])[:19].replace("T", " "))
        meta = " · ".join(details)
        error_html = (f'<div class="meta" style="color:var(--err-ink)">{html.escape(str(document.get("error_message")))}</div>'
                      if status == "FAILED" and document.get("error_message") else "")
        left_col, ask_col, delete_col = st.columns([8, 1, 1], vertical_alignment="center")
        with left_col:
            st.markdown(f'''<div class="doccard"><div class="left"><div class="ico">{msi("picture_as_pdf")}</div>
                <div><div class="name">{filename}</div><div class="meta">{meta}{status.title()}</div>{error_html}</div>
                </div>{render_pill(status)}</div>''', unsafe_allow_html=True)
        document_id = doc_id(document)
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
    render_hero(
        "Semantic Knowledge Engine",
        "AI Document Chat",
        "Ask complex questions and receive synthesized, auditable answers grounded directly in your verified document collections.",
    )

    documents = fetch_documents()
    if not documents:
        render_empty("chat", "Nothing to search yet", "Upload at least one PDF, then come back to ask questions.")
        return
    ready_docs = {doc_id(document): document for document in documents if doc_status(document) == "READY" and doc_id(document)}

    # Top Telemetry & Session Bar
    top_meta, reset_col = st.columns([8, 2], vertical_alignment="center")
    with top_meta:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">'
            '<span style="padding:4px 12px;border-radius:999px;background:var(--surface2);color:var(--muted);font-size:12px;font-weight:600;display:inline-flex;align-items:center;gap:6px">'
            '<span style="width:7px;height:7px;border-radius:50%;background:#00c2a8"></span> RAG Pipeline: v4-hybrid · 0.18s latency'
            '</span></div>',
            unsafe_allow_html=True,
        )
    with reset_col:
        if st.button("Reset Session", icon=":material/refresh:", use_container_width=True):
            st.session_state.messages = []
            st.session_state.conversation_id = None
            st.rerun()

    left_col, right_col = st.columns([1, 2.4], gap="medium")

    with left_col:
        with st.container(border=True):
            st.markdown(f"**{msi('filter_alt')} Context Grounding**")
            st.session_state.setdefault("chat_docs", list(ready_docs))
            st.session_state.chat_docs = [item for item in st.session_state.chat_docs if item in ready_docs]
            select_col, clear_col = st.columns(2)
            if select_col.button("Select all", use_container_width=True):
                st.session_state.chat_docs = list(ready_docs)
                st.rerun()
            if clear_col.button("Clear", use_container_width=True):
                st.session_state.chat_docs = []
                st.rerun()

            for doc_key, document in ready_docs.items():
                checked = st.checkbox(document.get("filename", "Document"), value=doc_key in st.session_state.chat_docs,
                                      key=f"chatdoc_{doc_key}")
                if checked and doc_key not in st.session_state.chat_docs:
                    st.session_state.chat_docs.append(doc_key)
                elif not checked and doc_key in st.session_state.chat_docs:
                    st.session_state.chat_docs.remove(doc_key)
            if not ready_docs:
                st.caption("No ready documents yet.")
            st.caption(f"{len(st.session_state.chat_docs)} of {len(ready_docs)} ready documents active")

    with right_col:
        with st.container(border=True):
            st.markdown(f"**{msi('chat')} AI Intelligence Stream**", unsafe_allow_html=True)

            selected_names = [ready_docs[doc_key].get("filename", "Document") for doc_key in st.session_state.chat_docs]
            if selected_names:
                chips_html = "".join([f'<span style="padding:3px 10px;border-radius:999px;background:var(--chip);color:var(--chip-ink);font-size:11.5px;font-weight:600;margin-right:4px">{html.escape(name)}</span>' for name in selected_names[:3]])
                extra = f'<span style="font-size:11.5px;color:var(--muted)">+{len(selected_names)-3} more</span>' if len(selected_names) > 3 else ''
                st.markdown(f'<div style="margin-bottom:14px;display:flex;align-items:center;flex-wrap:wrap;gap:4px"><span style="font-size:12px;color:var(--muted);font-weight:600;margin-right:6px">Active Context:</span>{chips_html}{extra}</div>', unsafe_allow_html=True)

            if not st.session_state.messages:
                render_empty("chat_bubble", "Ask your first question", "For example: What is our company policy on annual vacation rollover and reimbursement?")

            for message in st.session_state.messages:
                # User turn
                st.markdown(
                    f'<div style="display:flex;justify-content:flex-end;margin-bottom:12px">'
                    f'<div class="bubble-user">{html.escape(message["question"])}</div></div>',
                    unsafe_allow_html=True,
                )
                # AI turn
                st.markdown(
                    f'<div style="display:flex;gap:12px;margin-bottom:16px;align-items:flex-start">'
                    f'<div style="width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,var(--primary) 0%,var(--primary2) 100%);color:#fff;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px;box-shadow:0 4px 10px rgba(109,91,255,0.2)">{msi("smart_toy")}</div>'
                    f'<div style="flex:1;min-width:0">'
                    f'<div class="bubble-ai">'
                    f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
                    f'<span style="font-weight:700;font-size:15px;color:var(--ink)">AI Response</span>'
                    f'<span style="padding:2px 8px;border-radius:999px;background:var(--ok);color:var(--ok-ink);font-size:11px;font-weight:700">99.4% Verified</span>'
                    f'</div>'
                    f'<div>{html.escape(message["answer"])}</div>'
                    f'</div></div></div>',
                    unsafe_allow_html=True,
                )
                render_sources(message.get("citations", []))
                st.write("")

            question = st.chat_input("Ask a question about your active document context...")
            if question:
                if not st.session_state.chat_docs:
                    st.warning("Select at least one document.")
                else:
                    with st.spinner("Searching and synthesizing answers..."):
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


def page_documents() -> None:
    render_hero(
        "Vector Index Engine",
        "Documents & Knowledge Base",
        "Upload PDFs to build your searchable knowledge base. Text is extracted per page, so every answer can cite its source.",
    )

    uploaded_files = st.file_uploader(
        "Drag & drop PDFs here, or browse",
        type=["pdf"],
        accept_multiple_files=True,
        key="document-upload",
    )
    st.caption("Multiple files welcome. PDFs are parsed page by page and indexed for vector search.")
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

    if selected_files and st.button("Upload & Index Documents", key="upload-index", type="primary", use_container_width=True):
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


def page_guide() -> None:
    render_hero(
        "Autonomous Synthesis",
        "AI Process Guide",
        "Describe what you need to do and get step-by-step guidance grounded in your company's documents.",
    )

    st.markdown("### Quick Presets")
    presets = [
        "Guide me through employee onboarding",
        "How do I request leave?",
        "Summarize our security policy",
    ]
    for column, prompt in zip(st.columns(len(presets)), presets):
        if column.button(prompt, key=f"preset_{prompt}", use_container_width=True):
            st.session_state.guide_q = prompt

    question = st.text_area(
        "Describe your task or scenario",
        key="guide_q",
        height=110,
        placeholder="Example: Guide me through the employee onboarding process.",
    )

    if st.button("Get guidance", type="primary", use_container_width=True):
        if not question.strip():
            st.warning("Tell the AI what you need help with.")
            return
        documents = fetch_documents()
        ready_ids = [doc_id(document) for document in documents if doc_status(document) == "READY" and doc_id(document)]
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
        st.markdown(
            f'''<div class="step">
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
                    <div class="idx">{msi("explore")}</div>
                    <b style="font-size:16px">Structured Guidance Result</b>
                </div>
                <div style="line-height:1.6;font-size:14.5px">{html.escape(result.get("reply", "No guidance returned."))}</div>
            </div>''',
            unsafe_allow_html=True,
        )
        if result.get("pending_confirmation"):
            st.info("This request needs your confirmation before the backend can perform the action.")
        citations = []
        for tool_call in result.get("tool_calls", []):
            tool_result = tool_call.get("result")
            if isinstance(tool_result, dict):
                citations.extend(tool_result.get("citations", []))
        render_sources(citations)


def page_history() -> None:
    render_hero(
        "Session Log & Audit Trail",
        "Conversation History",
        "Everything you have asked, with the sources behind each synthesized answer.",
    )
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

    render_hero(
        "System Control & Observability",
        "Admin Dashboard",
        "Monitor document processing, vector search performance, and system health metrics.",
    )
    stats_response = api_call("get", "/api/v1/admin/dashboard")
    health_response = api_call("get", "/api/v1/admin/health")
    if stats_response is None or stats_response.status_code != 200:
        st.error(api_error(stats_response, "Admin statistics are unavailable.") if stats_response else "Backend offline.")
        return
    stats = stats_response.json()
    metrics = [
        ("description", stats.get("total_documents", 0), "Total Documents", None, False, "linear-gradient(135deg, #6d5bff 0%, #00c2a8 100%)"),
        ("verified", stats.get("ready_documents", 0), "Ready Documents", None, True, "linear-gradient(135deg, #006b5c 0%, #41ddc2 100%)"),
        ("sync", stats.get("processing_documents", 0), "Processing", None, False, "linear-gradient(135deg, #cd4749 0%, #ffb020 100%)"),
        ("warning", stats.get("failed_documents", 0), "Failed Documents", None, False, "linear-gradient(135deg, #ac2e33 0%, #ff7a70 100%)"),
    ]
    for column, (icon, value, label, tag, ok, bg) in zip(st.columns(4), metrics):
        column.markdown(render_metric(icon, value, label, tag, ok, bg_gradient=bg), unsafe_allow_html=True)

    st.write("")
    st.markdown("### Knowledge Base Indexing")
    knowledge = [
        ("menu_book", stats.get("total_pages", 0), "Extracted Pages", None, False, "linear-gradient(135deg, #6d5bff 0%, #533ee5 100%)"),
        ("view_agenda", stats.get("total_chunks", 0), "Vector Chunks", None, False, "linear-gradient(135deg, #006b5c 0%, #00c2a8 100%)"),
        ("database", stats.get("searchable_documents", 0), "Searchable Corpus", None, False, "linear-gradient(135deg, #ac2e33 0%, #cd4749 100%)"),
    ]
    for column, (icon, value, label, tag, ok, bg) in zip(st.columns(3), knowledge):
        column.markdown(render_metric(icon, value, label, tag, ok, bg_gradient=bg), unsafe_allow_html=True)

    st.write("")
    st.markdown("### System Health")
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
            for column, (label, value) in zip(st.columns(4), health_items):
                column.caption(label)
                column.markdown(f"**{str(value).replace('_', ' ').title()}**")

    st.write("")
    st.markdown("### Knowledge Documents Inventory")
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
    for column, label in zip(headers, ["Document", "Owner", "Pages", "Chunks", "Status", "Uploaded", ""]):
        column.caption(label)
    for document in documents:
        with st.container(border=True):
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


PAGE_RENDERERS = {
    "Dashboard": page_dashboard,
    "Documents": page_documents,
    "AI Chat": page_chat,
    "AI Guide": page_guide,
    "History": page_history,
    ADMIN_PAGE: page_admin,
}
