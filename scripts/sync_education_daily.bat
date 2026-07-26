@echo off
set "REPO_ROOT=%~dp0.."
"%REPO_ROOT%\venv\Scripts\python.exe" "%~dp0sync_education_daily.py"
