@echo off
title C.F.C.S - Cash Flow Control System
set DIR=%~dp0
set VENV=%DIR%.venv

if not exist "%VENV%" (
    python -m venv "%VENV%"
)

call "%VENV%\Scripts\pip" install -q -r "%DIR%requirements.txt"
start "" "%VENV%\Scripts\pythonw" "%DIR%app.py"
