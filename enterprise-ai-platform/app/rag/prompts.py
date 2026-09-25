"""
app/rag/prompts.py
------------------
Prompt templates for the RAG pipeline.

Design principles
-----------------
1. Anti-hallucination: the LLM is explicitly told to use ONLY the
   provided context and to say "I don't know" when the context is
   insufficient.  This is the primary hallucination control mechanism.

2. Citation: the LLM is instructed to reference the source document
   and page number for every factual claim.

3. Role-awareness: the system prompt can be tailored per user role so
   answers are appropriately scoped (e.g., student vs employee).

4. Clarity: instructions are in plain English, not in prompt-engineering
   jargon, so they survive fine-tuned / quantised models.
"""

from __future__ import annotations

from string import Template
from typing import List, Optional

from langchain_core.documents import Document

# ---------------------------------------------------------------------------
# System prompt (injected once per conversation)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are an AI Knowledge Assistant for an enterprise organisation.
Your role is to help employees, students, and staff find accurate \
information from authorised company documents.

STRICT RULES — follow these without exception:
1. Answer ONLY based on the context documents provided below.
2. If the context does not contain enough information to answer the \
question, respond with exactly:
   "I couldn't find enough information in the documents available to \
me to answer this question."
3. Do NOT invent, assume, or extrapolate facts that are not present \
in the context.
4. Prefer exact clauses, exceptions, dates, numbers, requirements, and \
    conditions over generic summaries. Cite your sources at the end of every answer using the format shown \
in the output instructions.
5. Be concise and professional.  Avoid unnecessary preamble.
6. If the question is ambiguous, answer the most reasonable \
interpretation and note the assumption.
"""

# ---------------------------------------------------------------------------
# RAG answer prompt
# ---------------------------------------------------------------------------
_RAG_TEMPLATE = Template("""\
$system_prompt

---
CONTEXT DOCUMENTS
$context
---

CONVERSATION HISTORY
$history

USER QUESTION
$question

ANSWER INSTRUCTIONS
- Write your answer first.
- Then list the sources you used under a "Sources:" heading.
- For each source include: filename, page number (if available), and a \
one-sentence description of what the source says.
- If you used no context (e.g., the question is a greeting), skip the \
Sources section.

Answer:""")


def build_rag_prompt(
    question: str,
    context_docs: List[Document],
    history: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> str:
    """
    Build the full RAG prompt string.

    Args:
        question:      The user's question.
        context_docs:  Retrieved and reranked Document chunks.
        history:       Optional serialised conversation history string.
        system_prompt: Override the default SYSTEM_PROMPT if provided.

    Returns:
        A single prompt string ready to pass to the LLM.
    """
    context_str = _format_context(context_docs)
    history_str = history or "No previous conversation."

    return _RAG_TEMPLATE.substitute(
        system_prompt=system_prompt or SYSTEM_PROMPT,
        context=context_str,
        history=history_str,
        question=question,
    )


def _format_context(docs: List[Document]) -> str:
    """
    Serialise context documents into a numbered, citation-friendly block.

    Output format::

        [1] Employee_Handbook.pdf — Page 12
        The employee leave policy provides 15 days of annual leave...

        [2] HR_Policy.pdf — Page 4
        Sick leave requests must be submitted within 24 hours...
    """
    if not docs:
        return "No context documents available."

    parts: List[str] = []
    for i, doc in enumerate(docs, start=1):
        filename = doc.metadata.get("source_filename", "Unknown document")
        page = doc.metadata.get("page_number", doc.metadata.get("page", ""))
        page_str = f" — Page {page}" if page else ""
        section = doc.metadata.get("section") or doc.metadata.get("subsection")
        section_str = f" — Section: {section}" if section else ""
        heading = f"[{i}] {filename}{page_str}{section_str}"
        parts.append(f"{heading}\n{doc.page_content.strip()}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Citation extraction helper
# ---------------------------------------------------------------------------
def build_citations(docs: List[Document]) -> List[dict]:
    """
    Build a structured list of citation objects from context documents.

    Used by the API response to return machine-readable source metadata
    alongside the answer text.

    Returns a list of dicts::

        [
            {
                "index": 1,
                "filename": "Employee_Handbook.pdf",
                "page": 12,
                "document_id": "uuid",
                "excerpt": "first 200 chars of the chunk..."
            },
            ...
        ]
    """
    citations = []
    for i, doc in enumerate(docs, start=1):
        citations.append(
            {
                "index": i,
                "filename": doc.metadata.get("source_filename", "Unknown"),
                "page": doc.metadata.get("page_number", doc.metadata.get("page")),
                "document_id": doc.metadata.get("document_id"),
                "section": doc.metadata.get("section") or None,
                "subsection": doc.metadata.get("subsection") or None,
                "excerpt": doc.page_content.strip()[:200],
                "vector_score": doc.metadata.get("vector_score"),
                "bm25_score": doc.metadata.get("bm25_score"),
                "hybrid_score": doc.metadata.get("hybrid_score"),
                "rerank_score": doc.metadata.get("rerank_score"),
            }
        )
    return citations


# ---------------------------------------------------------------------------
# No-answer sentinel
# ---------------------------------------------------------------------------
NO_ANSWER_RESPONSE = (
    "I couldn't find enough information in the documents available "
    "to me to answer this question."
)

def is_no_answer(response: str) -> bool:
    """Return True if the LLM returned the no-answer sentinel."""
    return NO_ANSWER_RESPONSE.lower() in response.lower()
