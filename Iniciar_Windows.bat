@echo off
title C.F.C.S - Iniciador do Sistema
color 0A
echo.
echo   ============================================================
echo     C.F.C.S // CASH FLOW CONTROL SYSTEM
echo     BY OCTO
echo   ============================================================
echo.

set DIR=%~dp0
set VENV=%DIR%.venv

if not exist "%VENV%" (
    echo   [-] Ambiente virtual nao encontrado. Criando ambiente...
    python -m venv "%VENV%"
)

echo   [-] Verificando dependencias...
call "%VENV%\Scripts\pip" install -q -r "%DIR%requirements.txt"

echo   [-] Iniciando o servidor web...
echo   [-] O seu navegador sera aberto automaticamente em instantes.
echo.
call "%VENV%\Scripts\python" "%DIR%app.py"
pause
