from langchain_community.llms import Ollama

def get_llm():
    return Ollama(model="llama3")