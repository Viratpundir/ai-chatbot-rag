# AI Chatbot Project

This workspace contains the AI chatbot app in the nested folder `ai-chatbot-rag`.

## Quick start

From the workspace root, run:

```cmd
run_app.cmd
```

Or manually:

```cmd
cd ai-chatbot-rag
python -m pip install -r requirements.txt
streamlit run app.py
```

If you want to run directly from the workspace root, use:

```cmd
streamlit run app.py
```

## Notes

- The app is located in `ai-chatbot-rag/app.py`
- Put your PDF in `ai-chatbot-rag/data/sample.pdf`
- Set `OPENAI_API_KEY` in your environment before running the app
