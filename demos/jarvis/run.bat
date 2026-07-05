@echo off
cd /d %~dp0
echo Starting BoschAI Johan Demo...
pip install -r requirements.txt -q
start "" http://localhost:8505
uvicorn server:app --port 8505 --host 127.0.0.1
