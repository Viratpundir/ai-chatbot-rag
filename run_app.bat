@echo off
cd /d "%~dp0"

set "PYTHON_EXE=..\.venv\Scripts\python.exe"
set "APP_URL=http://localhost:8501"

echo Starting Streamlit. If port 8501 is busy, Streamlit may choose the next available port.
echo Open the Local URL shown below in your browser.
echo.

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -m streamlit run app.py
) else (
    python -m streamlit run app.py
)

echo.
echo Streamlit stopped. If the browser shows "Connection error", run this file again.
pause
