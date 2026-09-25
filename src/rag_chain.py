import re


class RAGChain:
    def __init__(self, llm, vector_db, k=3):
        self.llm = llm
        self.vector_db = vector_db
        self.k = k

    def invoke(self, query):
        docs = self.vector_db.similarity_search(query, k=self.k)
        context = "\n\n".join(doc.page_content for doc in docs)
        prompt = (
            "You are an AI assistant. Use the following context to answer the question.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {query}\n\n"
            "Answer in a concise and helpful way."
        )

        response = self.llm.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)

    def run(self, query):
        return self.invoke(query)


def build_rag_chain(llm, vector_db):
    return RAGChain(llm, vector_db)


class LocalRAGChain:
    def __init__(self, docs, k=3, reason=None):
        self.docs = docs
        self.k = k
        self.reason = reason or "I searched the PDF locally."

    def invoke(self, query):
        query_terms = set(_tokenize(query))
        if not query_terms:
            return "Please ask a question about the PDF."

        ranked_docs = sorted(
            self.docs,
            key=lambda doc: _score_doc(doc.page_content, query_terms),
            reverse=True,
        )
        best_docs = [
            doc for doc in ranked_docs[: self.k]
            if _score_doc(doc.page_content, query_terms) > 0
        ]

        if not best_docs:
            return "I could not find a matching section in the PDF."

        excerpts = "\n\n".join(_shorten(doc.page_content) for doc in best_docs)
        return (
            f"{self.reason}\n\n"
            f"Most relevant text:\n\n{excerpts}"
        )

    def run(self, query):
        return self.invoke(query)


def build_local_rag_chain(docs, reason=None):
    return LocalRAGChain(docs, reason=reason)


def _tokenize(text):
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _score_doc(text, query_terms):
    doc_terms = set(_tokenize(text))
    return len(query_terms.intersection(doc_terms))


def _shorten(text, max_chars=900):
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars].rstrip()}..."
