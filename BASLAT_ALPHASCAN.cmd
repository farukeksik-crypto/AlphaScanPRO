@echo off
cd /d "%~dp0"
py -3.13 -m streamlit run app.py
pause
