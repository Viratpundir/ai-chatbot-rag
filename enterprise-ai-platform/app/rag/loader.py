"""
app/rag/loader.py
-----------------
Multi-format document loader.

Extends the original src/loader.py (PDF only) to support:
  PDF   → PyPDFLoader   (original, preserved)
  DOCX  → Docx2txtLoader
  TXT   → TextLoader
  MD    → UnstructuredMarkdownLoader
  HTML  → BSHTMLLoader

Each loader returns a list of LangChain Document objects with
page_content and metadata.  The metadata is enriched here with:
  - source_filename
  - file_type
  - file_size_bytes
  - document_id   (injected by the caller / ingestion worker)

Validation mirrors the original: file-must-exist, file-must-be-non-empty.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from langchain_core.documents import Document

from app.core.logging import get_logger

logger = get_logger(__name__)

# Supported extension → loader factory mapping
_LOADER_MAP = {
    "pdf": "_load_pdf",
    "docx": "_load_docx",
    "txt": "_load_txt",
    "md": "_load_md",
    "html": "_load_html",
    "htm": "_load_html",
}


class DocumentLoadError(Exception):
    """Raised when a document cannot be loaded."""


def load_documents(
    path: str | Path,
    document_id: Optional[str] = None,
) -> List[Document]:
    """
    Load a document from *path* and return a list of LangChain Documents.

    Args:
        path:        Absolute path to the file.
        document_id: Optional UUID injected into every chunk's metadata.
                     Populated by the ingestion worker (Stage 8).

    Raises:
        DocumentLoadError: If the file is missing, empty, or unsupported.
    """
    path = Path(path)

    # --- basic validation (preserved from original) ---
    if not path.exists():
        raise DocumentLoadError(f"File not found: {path}")
    if path.stat().st_size == 0:
        raise DocumentLoadError(f"File is empty: {path}")

    ext = path.suffix.lstrip(".").lower()
    loader_method = _LOADER_MAP.get(ext)
    if loader_method is None:
        raise DocumentLoadError(
            f"Unsupported file type '.{ext}'. "
            f"Supported: {', '.join(_LOADER_MAP.keys())}"
        )

    logger.info(
        "Loading document",
        extra={"path": str(path), "ext": ext, "document_id": document_id},
    )

    load_fn = globals()[loader_method]
    docs: List[Document] = load_fn(path)

    if not docs:
        raise DocumentLoadError(f"No content extracted from: {path}")

    # --- enrich metadata on every page/chunk ---
    file_size = path.stat().st_size
    for doc in docs:
        doc.metadata.setdefault("source_filename", path.name)
        doc.metadata["file_type"] = ext
        doc.metadata["file_size_bytes"] = file_size
        doc.metadata.setdefault("page_number", 1)
        doc.metadata.setdefault("section", "")
        doc.metadata.setdefault("subsection", "")
        if document_id:
            doc.metadata["document_id"] = document_id

    logger.info(
        "Document loaded",
        extra={"pages": len(docs), "path": str(path)},
    )
    return docs


# ---------------------------------------------------------------------------
# Per-format loaders
# ---------------------------------------------------------------------------

def _load_pdf(path: Path) -> List[Document]:
    from langchain_community.document_loaders import PyPDFLoader  # lazy

    loader = PyPDFLoader(str(path))
    docs = loader.load()
    # Normalise page number to 1-based for citations
    for doc in docs:
        if "page" in doc.metadata:
            doc.metadata["page_number"] = doc.metadata["page"] + 1
    return docs


def _load_docx(path: Path) -> List[Document]:
    try:
        from langchain_community.document_loaders import Docx2txtLoader  # lazy
    except ImportError as exc:
        raise DocumentLoadError(
            "DOCX support requires 'docx2txt'. Run: pip install docx2txt"
        ) from exc

    loader = Docx2txtLoader(str(path))
    return loader.load()


def _load_txt(path: Path) -> List[Document]:
    from langchain_community.document_loaders import TextLoader  # lazy

    loader = TextLoader(str(path), encoding="utf-8", autodetect_encoding=True)
    return loader.load()


def _load_md(path: Path) -> List[Document]:
    # Use TextLoader as a reliable fallback; UnstructuredMarkdownLoader
    # requires the 'unstructured' extra which is heavy.
    from langchain_community.document_loaders import TextLoader  # lazy

    loader = TextLoader(str(path), encoding="utf-8", autodetect_encoding=True)
    docs = loader.load()
    for doc in docs:
        doc.metadata["content_type"] = "markdown"
    return docs


def _load_html(path: Path) -> List[Document]:
    try:
        from langchain_community.document_loaders import BSHTMLLoader  # lazy
    except ImportError as exc:
        raise DocumentLoadError(
            "HTML support requires 'beautifulsoup4'. Run: pip install beautifulsoup4"
        ) from exc

    loader = BSHTMLLoader(str(path))
    return loader.load()
