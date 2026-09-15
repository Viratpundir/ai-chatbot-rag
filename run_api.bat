@echo off
cd /d "%~dp0"

set "PYTHON_EXE=..\.venv\Scripts\python.exe"

echo Starting FastAPI.
echo Open http://localhost:8000/docs in your browser.
echo.

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -m uvicorn api:app --host 127.0.0.1 --port 8000
) else (
    python -m uvicorn api:app --host 127.0.0.1 --port 8000
)

echo.
echo FastAPI stopped. Run this file again to restart it.
pause
