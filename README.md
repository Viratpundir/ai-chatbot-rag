# AI Chatbot with LLM + RAG

This project loads a PDF, splits it into chunks, creates vector embeddings, and uses a Retrieval-Augmented Generation (RAG) chain to answer questions with a Streamlit UI.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your OpenAI API key:
   ```bash
   set OPENAI_API_KEY=your_api_key_here
   ```
   or update `config.py`.
3. Place your PDF at `data/sample.pdf` or change the path in `app.py`.

## Run

```bash
streamlit run app.py
```

## Files

- `app.py` - Streamlit front-end and pipeline loader
- `src/loader.py` - PDF loading
- `src/splitter.py` - document chunking
- `src/embeddings.py` - OpenAI embeddings
- `src/vector_store.py` - FAISS vector store creation
- `src/retriever.py` - retriever configuration
- `src/rag_chain.py` - RAG QA chain setup
- `src/llm.py` - LLM model configuration
