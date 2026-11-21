@echo off
rem ===== Jarvis - doppio click per aprire =====
rem Autore: DreeMux
setlocal
cd /d "%~dp0All Process"
chcp 65001 >nul
set PYTHONUTF8=1
title Jarvis

rem --- trova Python 3 (prima il launcher "py", poi "python")
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo.
    echo  Python 3 not found. Install it from https://www.python.org/downloads/
    echo  ^(tick "Add python.exe to PATH"^) and double-click start.bat again.
    echo.
    pause
    exit /b 1
)

%PY% launcher.py
if errorlevel 1 (
    echo.
    echo  Something went wrong ^(code %errorlevel%^).
    pause
)
endlocal
