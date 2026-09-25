import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.embeddings import get_embeddings
from src.llm import get_llm
from src.loader import load_documents
from src.rag_chain import build_local_rag_chain, build_rag_chain
from src.splitter import split_docs
from src.vector_store import create_vector_store


BASE_DIR = Path(__file__).resolve().parent
PDF_PATH = BASE_DIR / "data" / "sample.pdf"

load_dotenv(BASE_DIR / ".env", override=True)

app = FastAPI(title="AI Chatbot RAG API")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)


class AskResponse(BaseModel):
    answer: str
    mode: str


def has_valid_api_key():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(api_key and api_key.startswith(("sk-", "sk-proj-")) and len(api_key) > 20)


def build_pipeline(use_openai):
    docs = load_documents(PDF_PATH)
    chunks = split_docs(docs)

    if not use_openai:
        return build_local_rag_chain(chunks), "local"

    embeddings = get_embeddings()
    vector_db = create_vector_store(chunks, embeddings)
    llm = get_llm()
    return build_rag_chain(llm, vector_db), "openai"


@lru_cache(maxsize=2)
def get_pipeline(use_openai):
    return build_pipeline(use_openai)


@app.get("/")
def root():
    return {
        "name": "AI Chatbot RAG API",
        "docs": "/docs",
        "ask": "/ask",
        "mode": "openai" if has_valid_api_key() else "local",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    use_openai = has_valid_api_key()

    try:
        chain, mode = get_pipeline(use_openai)
        return AskResponse(answer=chain.invoke(request.question), mode=mode)
    except Exception as exc:
        if not use_openai:
            raise

        chain, mode = get_pipeline(False)
        answer = (
            "OpenAI could not be used, so I searched the PDF locally.\n\n"
            f"OpenAI error: {exc}\n\n"
            f"{chain.invoke(request.question)}"
        )
        return AskResponse(answer=answer, mode=mode)
