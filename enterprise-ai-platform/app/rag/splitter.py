"""
app/rag/splitter.py
-------------------
Smart document chunking with metadata injection.

Extends the original src/splitter.py by:
  - Injecting rich metadata into every chunk (source, page, document_id,
    chunk_index, chunk_total) so citations can be generated accurately.
  - Keeping chunk_size / chunk_overlap configurable via settings.
  - Providing a markdown-aware splitter that respects heading boundaries.
  - Preserving the original split_docs() and split_documents() signatures
    for backward compatibility.
"""

from __future__ import annotations

import re
from typing import List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Headers that the Markdown splitter uses to identify section boundaries
_MD_HEADERS = [
    ("#", "heading_1"),
    ("##", "heading_2"),
    ("###", "heading_3"),
]


def split_docs(
    documents: List[Document],
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[Document]:
    """
    Split *documents* into overlapping chunks and inject metadata.

    This is the primary splitting function used by the ingestion pipeline.

    Args:
        documents:     List of LangChain Document objects from the loader.
        chunk_size:    Override settings.CHUNK_SIZE if provided.
        chunk_overlap: Override settings.CHUNK_OVERLAP if provided.

    Returns:
        Flat list of chunk Documents, each carrying enriched metadata.
    """
    cs = chunk_size or settings.CHUNK_SIZE
    co = chunk_overlap or settings.CHUNK_OVERLAP

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=cs,
        chunk_overlap=co,
        # Prefer splitting on paragraph / sentence boundaries before
        # falling back to arbitrary character cuts.
        separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
        length_function=len,
        is_separator_regex=False,
    )

    all_chunks: List[Document] = []
    for doc in documents:
        prepared = _add_section_context(doc)
        chunks = splitter.split_documents([prepared])

        all_chunks.extend(chunks)

    # Inject positional metadata AFTER all chunks are collected
    total = len(all_chunks)
    for idx, chunk in enumerate(all_chunks):
        chunk.metadata["chunk_index"] = idx
        chunk.metadata["chunk_total"] = total
        # Ensure source_filename is always present for citations
        if "source_filename" not in chunk.metadata:
            src = chunk.metadata.get("source", "unknown")
            chunk.metadata["source_filename"] = src

    logger.info(
        "Document split complete",
        extra={"input_docs": len(documents), "chunks_produced": total},
    )
    return all_chunks


_HEADING_RE = re.compile(
    r"^\s*(?:(#{1,6})\s+|((?:\d+(?:\.\d+)*)[.)]?\s+))?(?P<title>[A-Z][^\n]{2,120})\s*$"
)


def _add_section_context(doc: Document) -> Document:
    """Carry the latest heading into chunk text and citation metadata."""
    section = str(doc.metadata.get("section") or "")
    subsection = str(doc.metadata.get("subsection") or "")
    body_lines: List[str] = []
    for line in doc.page_content.splitlines():
        match = _HEADING_RE.match(line)
        marked_heading = match and (match.group(1) or match.group(2))
        uppercase_heading = line.strip() and line.strip().isupper() and len(line.split()) <= 12
        if not match or not (marked_heading or uppercase_heading):
            body_lines.append(line)
            continue
        marker = match.group(1) or match.group(2) or ""
        title = match.group("title").strip()
        level = len(marker) if marker.startswith("#") else marker.count(".") + 1
        if level <= 1:
            section, subsection = title, ""
        else:
            subsection = title
        body_lines.append(line)

    metadata = dict(doc.metadata)
    metadata["section"] = section
    metadata["subsection"] = subsection
    heading_context = " | ".join(value for value in (section, subsection) if value)
    content = "\n".join(body_lines).strip()
    if heading_context and heading_context.lower() not in content[: len(heading_context) + 4].lower():
        content = f"Section: {heading_context}\n{content}"
    return Document(page_content=content, metadata=metadata)


def _split_markdown(
    doc: Document,
    chunk_size: int,
    chunk_overlap: int,
) -> List[Document]:
    """
    Split a Markdown document respecting heading boundaries, then apply
    character-level splitting for oversized sections.
    """
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=_MD_HEADERS,
        strip_headers=False,
    )
    header_chunks = md_splitter.split_text(doc.page_content)

    # Carry the parent document's metadata into every header chunk
    for chunk in header_chunks:
        chunk.metadata.update(
            {k: v for k, v in doc.metadata.items() if k not in chunk.metadata}
        )

    # Further split header chunks that exceed chunk_size
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return char_splitter.split_documents(header_chunks)


# ---------------------------------------------------------------------------
# Backward-compatible alias (preserved from original src/splitter.py)
# ---------------------------------------------------------------------------
def split_documents(documents: List[Document]) -> List[Document]:
    """Alias for split_docs() — kept for backward compatibility."""
    return split_docs(documents)
