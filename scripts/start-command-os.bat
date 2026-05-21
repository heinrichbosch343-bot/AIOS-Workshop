@echo off
cd /d "c:\Users\gamin\BoschAI\BoschAI\aios-starter-kit"
"venv\Scripts\python.exe" -m apps.command.main >> "data\command-startup.log" 2>&1
