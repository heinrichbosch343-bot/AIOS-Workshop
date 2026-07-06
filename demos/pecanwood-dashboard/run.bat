@echo off
cd /d "%~dp0"
..\..\venv\Scripts\python.exe -m uvicorn server:app --port 8509
