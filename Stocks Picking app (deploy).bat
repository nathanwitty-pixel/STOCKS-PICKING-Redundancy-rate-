@echo off
rem Stocks Picking app with Streamlit's Deploy button (http://localhost:8503) - to deploy this repo yourself
cd /d "%~dp0"
set SPR_SHOW_DEPLOY=1
"C:\ProgramData\anaconda3\python.exe" -m streamlit run streamlit_app.py --server.port 8503 --client.toolbarMode auto
