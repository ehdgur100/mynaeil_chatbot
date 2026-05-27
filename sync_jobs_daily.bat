@echo off
cd /d "%~dp0"
venv\Scripts\python.exe sync_jobs_daily.py
