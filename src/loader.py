import os
from langchain_community.document_loaders import PyPDFLoader

def load_documents(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"❌ File not found: {path}")

    if os.path.getsize(path) == 0:
        raise ValueError(f"❌ File is empty: {path}")

    loader = PyPDFLoader(path)
    docs = loader.load()

    if not docs:
        raise ValueError("❌ No content found inside PDF")

    return docs