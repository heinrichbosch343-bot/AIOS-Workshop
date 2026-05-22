@echo off
cd /d "c:\Users\gamin\BoschAI\BoschAI\aios-starter-kit"

:restart
echo [%date% %time%] Starting CommandOS... >> "data\command-startup.log"
"venv\Scripts\python.exe" -m apps.command.main >> "data\command-startup.log" 2>&1
echo [%date% %time%] Bot exited (code %errorlevel%), restarting in 10 seconds... >> "data\command-startup.log"
timeout /t 10 /nobreak > nul
goto restart
