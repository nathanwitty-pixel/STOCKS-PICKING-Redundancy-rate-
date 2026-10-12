@echo off
rem Stocks Picking (Redundancy rate) - Streamlit app on http://localhost:8502
cd /d "%~dp0"
"C:\ProgramData\anaconda3\python.exe" -m streamlit run streamlit_app.py
