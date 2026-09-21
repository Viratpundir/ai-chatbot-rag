from langchain_community.llms import Ollama


def get_llm():
    return Ollama(
        model="llama3.2:3b",
        temperature=0.2
    )