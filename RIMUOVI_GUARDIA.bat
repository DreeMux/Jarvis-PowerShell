@echo off
rem ===== Jarvis - toglie la guardia =====
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo  Python 3 non trovato.
    pause
    exit /b 1
)
%PY% build.py --auto
%PY% pwsh.py --guard-remove
echo.
pause
endlocal
