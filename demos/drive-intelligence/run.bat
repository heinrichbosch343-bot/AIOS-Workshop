@echo off
echo Starting AIOS Data Pool Demo Dashboard...
pip install -r requirements.txt -q
streamlit run dashboard.py --server.port 8502 --browser.gatherUsageStats false
