from langchain_openai import ChatOpenAI

from src.loader import load_documents
from src.splitter import split_documents
from src.embeddings import get_embeddings
from src.vector_store import create_vector_store


class RAGChain:
    """Custom RAG chain to replace RetrievalQA"""
    def __init__(self, llm, vectorstore):
        self.llm = llm
        self.vectorstore = vectorstore
    
    def run(self, query: str) -> str:
        # Retrieve relevant documents
        docs = self.vectorstore.similarity_search(query, k=4)
        
        # Build context from retrieved docs
        context = "\n\n".join([doc.page_content for doc in docs])
        
        # Create prompt
        prompt = f"""Based on the following context, answer the question.

Context:
{context}

Question: {query}

Answer:"""
        
        # Get response from LLM
        response = self.llm.invoke(prompt)
        return response.content if hasattr(response, 'content') else str(response)


def build_pipeline(pdf_path: str):
    # Load
    docs = load_documents(pdf_path)

    # Split
    chunks = split_documents(docs)

    # Embeddings
    embeddings = get_embeddings()

    # Vector DB
    vectorstore = create_vector_store(chunks, embeddings)

    # LLM
    llm = ChatOpenAI(
        temperature=0,
        model="gpt-3.5-turbo"
    )

    # QA Chain
    qa_chain = RAGChain(llm=llm, vectorstore=vectorstore)

    return qa_chain