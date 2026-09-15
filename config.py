import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your_api_key_here")
if OPENAI_API_KEY and OPENAI_API_KEY != "your_api_key_here":
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY