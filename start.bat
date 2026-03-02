@echo off
setlocal
chcp 65001 >nul
echo ================================================
echo Starting Mini-RAG
echo ================================================
echo.
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" run.py
) else (
    python run.py
)
pause
