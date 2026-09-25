@echo off
REM Run the AI chatbot from the workspace root
cd /d "%~dp0ai-chatbot-rag" || exit /b 1
python -m pip install -r requirements.txt
streamlit run app.py
