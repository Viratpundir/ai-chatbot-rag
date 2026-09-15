import streamlit as st
from pathlib import Path

from src.embeddings import get_embeddings
from src.llm import get_llm
from src.loader import load_documents
from src.rag_chain import build_rag_chain
from src.splitter import split_docs
from src.vector_store import create_vector_store


st.set_page_config(page_title="RAG Chatbot", page_icon=":robot_face:")

BASE_DIR = Path(__file__).resolve().parent
PDF_PATH = BASE_DIR / "data" / "sample.pdf"

st.title("AI Chatbot (RAG)")
st.write("Ask questions from your PDF")


@st.cache_resource
def load_pipeline():
    # Load and split documents
    docs = load_documents(PDF_PATH)
    chunks = split_docs(docs)

    # Create embeddings (HuggingFace)
    embeddings = get_embeddings()

    # Create vector DB (FAISS)
    vector_db = create_vector_store(chunks, embeddings)

    # Load local LLM (Ollama)
    llm = get_llm()

    # Build RAG chain
    return build_rag_chain(llm, vector_db)


# Load pipeline
try:
    qa_chain = load_pipeline()
    st.success("Running on local AI model (Ollama) 🚀")
except Exception as e:
    st.error(f"Error starting pipeline: {e}")
    st.stop()


# User input
query = st.text_input("Ask a question:")

if query:
    try:
        response = qa_chain.invoke(query)
        st.success(response)
    except Exception as e:
        st.error(f"Error: {e}")
