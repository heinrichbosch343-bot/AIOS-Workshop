@echo off
echo Starting AIOS Paperwork-to-Data Demo...
pip install -r requirements.txt -q
streamlit run dashboard.py --server.port 8503 --browser.gatherUsageStats false
