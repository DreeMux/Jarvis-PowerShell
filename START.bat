@echo off
rem ===== Jarvis PowerShell - doppio click per aprire =====
rem Autore: DreeMux
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
title Jarvis PowerShell

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
    echo  Python 3 non trovato. Installalo da https://www.python.org/downloads/
    echo  ^(spunta "Add python.exe to PATH"^) e rifai doppio click su START.bat.
    echo.
    pause
    exit /b 1
)

rem --- allinea i moduli (src\) con pwsh.py: 0 = ok, 1 = errore, 2 = avviso
%PY% build.py --auto
if errorlevel 2 (
    echo.
    pause
    goto run
)
if errorlevel 1 (
    echo.
    echo  Jarvis NON si avvia: correggi l'errore qui sopra e rifai doppio click.
    echo.
    pause
    exit /b 1
)

:run
%PY% pwsh.py
if errorlevel 1 (
    echo.
    echo  Jarvis si e' chiuso con un errore ^(codice %errorlevel%^).
    pause
)
endlocal
