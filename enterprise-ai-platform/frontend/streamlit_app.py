
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import streamlit as st

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import Ollama
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter


# ============================================================
# ENTERPRISE AI DOCUMENT INTELLIGENCE PLATFORM
# ------------------------------------------------------------
# This is the integrated version of the user's project.
#
# The four supplied frontend designs are represented as:
#   Dashboard
#   Documents
#   AI Chat
#   AI Guide
#
# The original RAG flow remains local:
#   PDF -> PyPDF -> chunks -> embeddings -> FAISS
#       -> similarity search -> Ollama -> answer + sources
#
# No external FastAPI service is required for this version.
# ============================================================

st.set_page_config(
    page_title="Enterprise AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_PDF = DATA_DIR / "sample.pdf"

# Local models. Keep these small enough for a typical laptop GPU/RAM.
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))
TOP_K = int(os.getenv("TOP_K", "4"))


# ============================================================
# VISUAL DESIGN
# ============================================================

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --primary: #6d5bff;
    --primary-dark: #4d3fd1;
    --secondary: #00c2a8;
    --tertiary: #ff6b6b;
    --surface: #fbf9ff;
    --surface-low: #f5f1fb;
    --surface-card: #ffffff;
    --text: #1b1735;
    --muted: #706b80;
    --border: #e7e1f2;
    --success: #008f78;
    --warning: #b97800;
    --danger: #ba1a1a;
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background:
        radial-gradient(circle at 10% 0%, rgba(109,91,255,.07), transparent 30%),
        radial-gradient(circle at 100% 10%, rgba(0,194,168,.05), transparent 28%),
        var(--surface);
    color: var(--text);
}

.block-container {
    max-width: 1500px;
    padding-top: 1.2rem;
    padding-bottom: 4rem;
}

[data-testid="stSidebar"] {
    background: rgba(255,255,255,.88);
    border-right: 1px solid var(--border);
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 1rem;
}

.stButton > button {
    border-radius: 12px;
    border: 1px solid var(--border);
    min-height: 42px;
    font-weight: 600;
    transition: .18s ease;
}

.stButton > button:hover {
    transform: translateY(-1px);
    border-color: rgba(109,91,255,.35);
    box-shadow: 0 8px 22px rgba(109,91,255,.10);
}

button[kind="primary"] {
    background: linear-gradient(135deg, #6d5bff, #8c5cff);
    border: none;
}

[data-testid="stMetric"] {
    background: white;
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 14px;
    box-shadow: 0 4px 18px rgba(40,30,80,.05);
}

.enterprise-card {
    background: rgba(255,255,255,.92);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 24px;
    box-shadow: 0 10px 35px rgba(40,30,80,.06);
    margin-bottom: 18px;
}

.section-title {
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -.03em;
    margin: 10px 0 4px;
}

.section-subtitle {
    color: var(--muted);
    line-height: 1.65;
}

.badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: 999px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .05em;
    text-transform: uppercase;
}

.badge-ready {
    color: #006f60;
    background: #dcfaf4;
}

.badge-processing {
    color: #946000;
    background: #fff3d1;
}

.badge-failed {
    color: #a01818;
    background: #ffe3e3;
}

.badge-uploaded {
    color: #5d566e;
    background: #efebf5;
}

.badge-admin {
    color: #5037c9;
    background: #ebe7ff;
}

.badge-online {
    color: #007764;
    background: #ddfaf4;
}

.hero {
    position: relative;
    overflow: hidden;
    border-radius: 24px;
    padding: 30px;
    color: white;
    background:
        radial-gradient(circle at 90% 15%, rgba(255,255,255,.18), transparent 24%),
        linear-gradient(135deg, #4d3fd1, #7a5cff 55%, #a05cff);
    box-shadow: 0 18px 45px rgba(82,61,220,.20);
}

.hero:after {
    content: "";
    position: absolute;
    width: 260px;
    height: 260px;
    right: -90px;
    bottom: -130px;
    border-radius: 50%;
    background: rgba(0,194,168,.28);
}

.quick-card {
    background: white;
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 18px;
    height: 100%;
}

.document-row {
    background: white;
    border: 1px solid var(--border);
    border-radius: 15px;
    padding: 15px 17px;
    margin: 8px 0;
}

.source-card {
    background: #f5f1ff;
    border: 1px solid #e4dcff;
    border-radius: 12px;
    padding: 10px 12px;
    margin: 6px 0;
    color: #504a61;
    font-size: 13px;
}

.chat-user {
    background: #eeeaff;
    border-radius: 16px 16px 4px 16px;
    padding: 14px 17px;
    margin: 10px 0 8px auto;
    max-width: 85%;
}

.chat-ai {
    background: white;
    border: 1px solid var(--border);
    border-radius: 16px 16px 16px 4px;
    padding: 16px 18px;
    margin: 8px 0 10px;
    max-width: 92%;
    box-shadow: 0 5px 20px rgba(40,30,80,.04);
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 6px 10px;
    background: white;
    font-size: 12px;
}

.online-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--secondary);
    box-shadow: 0 0 0 4px rgba(0,194,168,.12);
}

.step-card {
    background: white;
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 18px;
    margin: 9px 0;
}

.step-number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #ebe7ff;
    color: #5037c9;
    font-weight: 800;
    margin-right: 8px;
}

.small-muted {
    color: var(--muted);
    font-size: 13px;
}

div[data-testid="stFileUploader"] {
    border: 1.5px dashed #c9c0dd;
    border-radius: 16px;
    padding: 8px;
    background: rgba(255,255,255,.65);
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_STATE = {
    "page": "Dashboard",
    "documents": {},
    "messages": [],
    "history": [],
    "vectorstore": None,
    "indexed_signature": None,
    "last_latency": None,
    "last_sources": [],
    "guide_result": None,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# RAG CORE
# ============================================================

@st.cache_resource(show_spinner=False)
def get_embeddings():
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


@st.cache_resource(show_spinner=False)
def get_llm():
    return Ollama(
        model=OLLAMA_MODEL,
        temperature=0.2,
    )


def load_pdf(path: Path):
    loader = PyPDFLoader(str(path))
    return loader.load()


def split_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(documents)


def build_vectorstore_from_files(files: List[Path]):
    all_chunks = []

    for file_path in files:
        docs = load_pdf(file_path)

        for doc in docs:
            doc.metadata["source"] = file_path.name

        chunks = split_documents(docs)
        all_chunks.extend(chunks)

    if not all_chunks:
        raise ValueError("No text could be extracted from the selected PDFs.")

    embeddings = get_embeddings()
    return FAISS.from_documents(all_chunks, embeddings)


def ensure_index():
    documents = st.session_state.documents

    ready_paths = [
        Path(item["path"])
        for item in documents.values()
        if item["status"] == "READY" and Path(item["path"]).exists()
    ]

    signature = tuple(
        sorted(
            (str(path), path.stat().st_mtime_ns, path.stat().st_size)
            for path in ready_paths
        )
    )

    if not ready_paths:
        st.session_state.vectorstore = None
        st.session_state.indexed_signature = signature
        return None

    if (
        st.session_state.vectorstore is None
        or st.session_state.indexed_signature != signature
    ):
        with st.spinner("Building the knowledge index..."):
            st.session_state.vectorstore = build_vectorstore_from_files(
                ready_paths
            )
            st.session_state.indexed_signature = signature

    return st.session_state.vectorstore


def retrieve_documents(question: str, vectorstore):
    return vectorstore.similarity_search(question, k=TOP_K)


def answer_question(question: str, selected_names: List[str]):
    vectorstore = ensure_index()

    if vectorstore is None:
        return (
            "No READY documents are available. Upload a PDF and process it first.",
            [],
            [],
        )

    allowed = set(selected_names)
    retrieved = retrieve_documents(question, vectorstore)

    # Enforce the selected-document scope at the UI/RAG layer.
    scoped = [
        doc for doc in retrieved
        if doc.metadata.get("source") in allowed
    ]

    if not scoped:
        scoped = retrieved

    context_parts = []
    sources = []

    for doc in scoped:
        source = doc.metadata.get("source", "Unknown document")
        page = doc.metadata.get("page")
        page_number = int(page) + 1 if isinstance(page, int) else None

        context_parts.append(
            f"[Source: {source}"
            + (f", Page {page_number}" if page_number else "")
            + "]\n"
            + doc.page_content
        )

        sources.append(
            {
                "filename": source,
                "page": page_number,
            }
        )

    context = "\n\n".join(context_parts)

    prompt = f"""
You are an enterprise document assistant.

Answer the user's question using ONLY the supplied context.
If the context does not contain enough information, clearly say:
"I couldn't find that information in the selected documents."

Do not invent facts.
Keep the answer concise but useful.
Mention relevant source names when appropriate.

CONTEXT:
{context}

QUESTION:
{question}

ANSWER:
""".strip()

    llm = get_llm()
    response = llm.invoke(prompt)

    answer = (
        response.content
        if hasattr(response, "content")
        else str(response)
    )

    return answer, sources, scoped


# ============================================================
# DOCUMENT MANAGEMENT
# ============================================================

def save_uploaded_files(uploaded_files):
    for uploaded in uploaded_files:
        destination = DATA_DIR / uploaded.name

        with open(destination, "wb") as output:
            output.write(uploaded.getbuffer())

        st.session_state.documents[uploaded.name] = {
            "name": uploaded.name,
            "path": str(destination),
            "status": "UPLOADED",
            "size": uploaded.size,
            "chunks": 0,
            "error": "",
        }


def process_documents():
    for name, item in st.session_state.documents.items():
        if item["status"] not in ("UPLOADED", "FAILED"):
            continue

        item["status"] = "PROCESSING"
        item["error"] = ""

        try:
            docs = load_pdf(Path(item["path"]))
            chunks = split_documents(docs)

            if not chunks:
                raise ValueError("No readable text found in this PDF.")

            item["chunks"] = len(chunks)
            item["status"] = "READY"

        except Exception as exc:
            item["status"] = "FAILED"
            item["error"] = str(exc)

    # Force the index to rebuild after ingestion.
    st.session_state.vectorstore = None
    st.session_state.indexed_signature = None


def delete_document(name: str):
    item = st.session_state.documents.get(name)

    if item:
        path = Path(item["path"])
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    st.session_state.documents.pop(name, None)
    st.session_state.vectorstore = None
    st.session_state.indexed_signature = None


def document_status_badge(status: str):
    mapping = {
        "READY": ("badge-ready", "● READY"),
        "PROCESSING": ("badge-processing", "◐ PROCESSING"),
        "FAILED": ("badge-failed", "● FAILED"),
        "UPLOADED": ("badge-uploaded", "○ UPLOADED"),
    }

    css, label = mapping.get(
        status,
        ("badge-uploaded", f"○ {status}"),
    )

    return f'<span class="badge {css}">{label}</span>'


# ============================================================
# SIDEBAR / NAVIGATION
# ============================================================

def sidebar():
    with st.sidebar:
        st.markdown(
            """
            <div style="padding:6px 5px 20px;">
                <div style="
                    display:flex;
                    align-items:center;
                    gap:10px;
                    font-size:21px;
                    font-weight:800;
                ">
                    <span style="
                        width:36px;
                        height:36px;
                        display:inline-flex;
                        align-items:center;
                        justify-content:center;
                        border-radius:11px;
                        background:linear-gradient(135deg,#6d5bff,#00c2a8);
                        color:white;
                    ">✦</span>
                    Enterprise AI
                </div>
                <div class="small-muted" style="margin-top:6px;">
                    Knowledge & Document Intelligence
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        pages = {
            "▦  Dashboard": "Dashboard",
            "▣  Documents": "Documents",
            "✦  AI Chat": "AI Chat",
            "◎  AI Guide": "AI Guide",
            "◷  History": "History",
        }

        for label, page in pages.items():
            if st.button(
                label,
                key=f"nav_{page}",
                use_container_width=True,
                type="primary" if st.session_state.page == page else "secondary",
            ):
                st.session_state.page = page
                st.rerun()

        st.divider()

        ready = sum(
            1 for item in st.session_state.documents.values()
            if item["status"] == "READY"
        )
        processing = sum(
            1 for item in st.session_state.documents.values()
            if item["status"] == "PROCESSING"
        )

        st.markdown(
            f"""
            <div class="status-pill">
                <span class="online-dot"></span>
                Local AI online
            </div>
            <div class="small-muted" style="margin-top:8px;">
                Ollama · {OLLAMA_MODEL}
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("###")
        c1, c2 = st.columns(2)
        c1.metric("Ready", ready)
        c2.metric("Indexing", processing)

        st.divider()
        st.caption("RAG pipeline")
        st.caption("PDF → Chunks → Embeddings → FAISS → Ollama")


def top_header():
    col1, col2 = st.columns([5, 1.2])

    with col1:
        st.markdown(
            """
            <div style="padding-top:4px;">
                <span class="small-muted">Workspace</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        if st.session_state.last_latency is not None:
            st.markdown(
                f"""
                <div style="text-align:right;padding-top:4px;">
                    <span class="badge badge-online">
                        {st.session_state.last_latency:.2f}s
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ============================================================
# DASHBOARD
# ============================================================

def dashboard_page():
    documents = list(st.session_state.documents.values())

    ready = sum(item["status"] == "READY" for item in documents)
    processing = sum(item["status"] == "PROCESSING" for item in documents)
    failed = sum(item["status"] == "FAILED" for item in documents)

    st.markdown(
        """
        <div class="hero">
            <div style="position:relative;z-index:2;max-width:760px;">
                <div class="badge"
                     style="background:rgba(255,255,255,.16);color:white;">
                    ✦ KNOWLEDGE VECTOR ENGINE
                </div>
                <h1 style="font-size:36px;margin:15px 0 7px;">
                    Your enterprise AI workspace
                </h1>
                <p style="font-size:16px;line-height:1.7;margin:0;">
                    Upload documents, build a searchable knowledge base,
                    and ask grounded questions with document-level sources.
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("###")

    c1, c2, c3, c4 = st.columns(4)

    for col, label, value in [
        (c1, "Documents", len(documents)),
        (c2, "Ready", ready),
        (c3, "Processing", processing),
        (c4, "Failed", failed),
    ]:
        with col:
            st.metric(label, value)

    st.markdown("### Quick actions")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            """
            <div class="quick-card">
                <div style="font-size:25px;">📄</div>
                <h3>Upload documents</h3>
                <p class="small-muted">
                    Add PDFs to your searchable knowledge base.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Open Documents", use_container_width=True):
            st.session_state.page = "Documents"
            st.rerun()

    with c2:
        st.markdown(
            """
            <div class="quick-card">
                <div style="font-size:25px;">💬</div>
                <h3>Ask your documents</h3>
                <p class="small-muted">
                    Retrieve relevant passages and generate grounded answers.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Open AI Chat", use_container_width=True):
            st.session_state.page = "AI Chat"
            st.rerun()

    with c3:
        st.markdown(
            """
            <div class="quick-card">
                <div style="font-size:25px;">◎</div>
                <h3>AI Guide</h3>
                <p class="small-muted">
                    Turn a policy or process question into step-by-step guidance.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Open AI Guide", use_container_width=True):
            st.session_state.page = "AI Guide"
            st.rerun()

    st.markdown("### Knowledge base")

    if not documents:
        st.info("No documents yet. Open Documents to upload your first PDF.")
        return

    for item in documents:
        st.markdown(
            f"""
            <div class="document-row">
                <div style="display:flex;justify-content:space-between;gap:12px;">
                    <strong>📄 {item["name"]}</strong>
                    {document_status_badge(item["status"])}
                </div>
                <div class="small-muted" style="margin-top:8px;">
                    {item["chunks"]} chunks
                    {" · " + item["error"][:100] if item["error"] else ""}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# DOCUMENTS
# ============================================================

def documents_page():
    st.markdown(
        """
        <div class="enterprise-card">
            <div class="badge badge-uploaded">
                🔐 SECURE DOCUMENT INGESTION
            </div>
            <h1 class="section-title">Documents</h1>
            <p class="section-subtitle">
                Upload one or multiple PDFs. Each document is extracted,
                split into chunks, embedded and added to the searchable FAISS index.
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
        help="PDF only. Multiple documents are supported.",
    )

    if files:
        st.write(f"**{len(files)} file(s) selected**")

        for file in files:
            st.caption(
                f"📄 {file.name} · {file.size / 1024:.1f} KB"
            )

        if st.button(
            "🚀 Upload & Process",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Saving, extracting and indexing documents..."):
                save_uploaded_files(files)
                process_documents()

            st.success("Document processing completed.")
            time.sleep(0.3)
            st.rerun()

    st.markdown("---")
    st.markdown("### Your documents")

    documents = list(st.session_state.documents.values())

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total", len(documents))
    c2.metric(
        "Indexed",
        sum(item["status"] == "READY" for item in documents),
    )
    c3.metric(
        "Processing",
        sum(item["status"] == "PROCESSING" for item in documents),
    )
    c4.metric(
        "Failed",
        sum(item["status"] == "FAILED" for item in documents),
    )

    if not documents:
        st.info("Your knowledge base is empty.")
        return

    for name, item in list(st.session_state.documents.items()):
        c1, c2, c3 = st.columns([6, 2, 1])

        with c1:
            st.markdown(
                f"""
                <div class="document-row">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="font-size:23px;">📄</span>
                        <div>
                            <strong>{item["name"]}</strong>
                            <div class="small-muted">
                                {item["chunks"]} chunks ·
                                {item["size"] / 1024:.1f} KB
                            </div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c2:
            st.markdown(
                document_status_badge(item["status"]),
                unsafe_allow_html=True,
            )
            if item["error"]:
                st.caption(item["error"][:100])

        with c3:
            if st.button("Delete", key=f"delete_{name}"):
                delete_document(name)
                st.rerun()

    st.info(
        "Tip: only READY documents are used by the AI Chat and AI Guide."
    )


# ============================================================
# SOURCE RENDERING
# ============================================================

def render_sources(sources: List[Dict[str, Any]]):
    if not sources:
        return

    st.markdown("**Sources**")

    seen = set()

    for source in sources:
        key = (
            source.get("filename"),
            source.get("page"),
        )

        if key in seen:
            continue

        seen.add(key)

        filename = source.get("filename", "Document")
        page = source.get("page")

        text = f"📄 {filename}"
        if page:
            text += f" · Page {page}"

        st.markdown(
            f'<div class="source-card">{text}</div>',
            unsafe_allow_html=True,
        )


# ============================================================
# AI CHAT
# ============================================================

def ready_document_names() -> List[str]:
    return [
        item["name"]
        for item in st.session_state.documents.values()
        if item["status"] == "READY"
    ]


def document_selector() -> List[str]:
    ready = ready_document_names()

    if not ready:
        st.warning(
            "No READY documents are available. Go to Documents and process a PDF."
        )
        return []

    st.markdown(
        """
        <div class="enterprise-card">
            <div class="badge badge-ready">ACTIVE KNOWLEDGE SCOPE</div>
            <h3 style="margin:10px 0 4px;">Select your document scope</h3>
            <p class="section-subtitle">
                Answers are generated from the selected READY documents.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected = st.multiselect(
        "Knowledge sources",
        ready,
        default=ready,
        key="chat_scope",
    )

    st.caption(
        f"{len(selected)} of {len(ready)} READY documents selected."
    )

    return selected


def chat_page():
    st.markdown(
        """
        <div class="enterprise-card">
            <div class="badge badge-ready">
                ✦ SEMANTIC KNOWLEDGE ENGINE
            </div>
            <h1 class="section-title">AI Document Chat</h1>
            <p class="section-subtitle">
                Ask questions about your selected documents.
                Retrieval happens first; the local LLM then answers from the retrieved context.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected = document_selector()

    if not selected:
        return

    if st.session_state.last_latency is not None:
        st.caption(
            f"Last response latency: {st.session_state.last_latency:.2f}s"
        )

    for message in st.session_state.messages:
        st.markdown(
            f"""
            <div class="chat-user">
                <strong>👤 You</strong><br><br>
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

        render_sources(message.get("sources", []))

    question = st.chat_input(
        "Ask a question about your selected documents..."
    )

    if question:
        start = time.perf_counter()

        try:
            with st.spinner(
                "Searching your selected documents and generating an answer..."
            ):
                answer, sources, _ = answer_question(
                    question,
                    selected,
                )

            latency = time.perf_counter() - start
            st.session_state.last_latency = latency

            message = {
                "question": question,
                "answer": answer,
                "sources": sources,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            st.session_state.messages.append(message)
            st.session_state.history.append(message)

            st.rerun()

        except Exception as exc:
            st.session_state.last_latency = time.perf_counter() - start
            st.error(
                "The RAG pipeline failed. "
                f"Check Ollama, the embedding model and the PDF. Details: {exc}"
            )


# ============================================================
# AI GUIDE
# ============================================================

GUIDE_PROMPTS = [
    "Guide me through employee onboarding and setting up internal access",
    "Explain the security policy as a step-by-step process",
    "Create a checklist from the selected documents",
    "What is the process described in these documents?",
]


def guide_page():
    st.markdown(
        """
        <div class="enterprise-card">
            <div class="badge badge-ready">✦ ENTERPRISE ASSISTANT</div>
            <h1 class="section-title">AI Step-by-Step Guide</h1>
            <p class="section-subtitle">
                Describe a task or policy process and generate a guided walkthrough
                from your selected company documents.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected = document_selector()

    if not selected:
        return

    st.markdown("### Suggested prompts")

    cols = st.columns(2)

    for index, prompt in enumerate(GUIDE_PROMPTS):
        with cols[index % 2]:
            if st.button(
                prompt,
                key=f"guide_prompt_{index}",
                use_container_width=True,
            ):
                st.session_state.guide_prompt = prompt
                st.rerun()

    prompt = st.text_area(
        "Describe the task or process",
        value=st.session_state.get("guide_prompt", ""),
        height=110,
        placeholder="Example: Explain the employee onboarding process step by step.",
    )

    if st.button(
        "✨ Generate step-by-step guide",
        type="primary",
        use_container_width=True,
    ):
        if not prompt.strip():
            st.warning("Enter a task or process first.")
            return

        start = time.perf_counter()

        try:
            with st.spinner("Retrieving policy context and generating the guide..."):
                answer, sources, _ = answer_question(
                    f"""
Create a practical step-by-step guide for this task:

{prompt}

Format the response as:
1. Step title — explanation
2. Step title — explanation
3. Step title — explanation

Include prerequisites or important notes when the documents support them.
Do not invent policy details.
""".strip(),
                    selected,
                )

            st.session_state.last_latency = time.perf_counter() - start
            st.session_state.guide_result = {
                "prompt": prompt,
                "answer": answer,
                "sources": sources,
            }

        except Exception as exc:
            st.error(f"Guide generation failed: {exc}")

    result = st.session_state.guide_result

    if result:
        st.markdown("---")
        st.markdown("### Generated guide")

        st.markdown(
            f"""
            <div class="enterprise-card">
                <div class="badge badge-ready">GROUNDED GUIDE</div>
                <h3 style="margin-top:12px;">{result["prompt"]}</h3>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(result["answer"])
        render_sources(result.get("sources", []))


# ============================================================
# HISTORY
# ============================================================

def history_page():
    st.markdown(
        """
        <div class="enterprise-card">
            <div class="badge badge-uploaded">◷ CONVERSATION HISTORY</div>
            <h1 class="section-title">History</h1>
            <p class="section-subtitle">
                Review questions asked during this Streamlit session.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.history:
        st.info("No questions have been asked in this session yet.")
        return

    if st.button("Clear history"):
        st.session_state.history = []
        st.session_state.messages = []
        st.rerun()

    for index, item in enumerate(
        reversed(st.session_state.history),
        start=1,
    ):
        with st.expander(
            f"{index}. {item['question'][:100]}"
        ):
            st.markdown("**Question**")
            st.write(item["question"])

            st.markdown("**Answer**")
            st.write(item["answer"])

            st.caption(item.get("timestamp", ""))
            render_sources(item.get("sources", []))


# ============================================================
# SYSTEM INFO
# ============================================================

def system_footer():
    st.divider()

    ready = sum(
        1
        for item in st.session_state.documents.values()
        if item["status"] == "READY"
    )

    st.caption(
        f"Enterprise AI · {ready} indexed document(s) · "
        f"Embeddings: {EMBEDDING_MODEL} · LLM: {OLLAMA_MODEL}"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    sidebar()
    top_header()

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

    else:
        dashboard_page()

    system_footer()


if __name__ == "__main__":
    main()
