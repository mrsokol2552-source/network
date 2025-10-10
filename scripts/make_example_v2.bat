@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

REM ===== Mermaid NetDocs: minimal batch wrapper =====
pushd "%~dp0\.."
set "ROOT=%CD%"
set "LOGS=%ROOT%\data\output\logs"
set "RUNLOG=%LOGS%\run.log"
if not exist "%LOGS%" mkdir "%LOGS%"
echo ===== RUN START %DATE% %TIME% ===== > "%RUNLOG%" 2>&1

REM Python presence check
python -V >nul 2>&1 || (echo [ERROR] Python not found in PATH>>"%RUNLOG%" & goto :fail)

REM Call the unified Python pipeline. Adjust CIDR/targets as needed or pass via %*
python -m src.pipeline --config config\config.json --env .env --cidr 10.20.98.0/24 10.20.99.0/24 10.20.97.0/24 10.2.99.0/24 10.0.2.0/24 %* >> "%RUNLOG%" 2>&1
if errorlevel 1 goto :fail

echo [OK] Done. Output: data\output\network.mmd>>"%RUNLOG%"
type "%RUNLOG%"
echo.
pause
goto :end

:fail
echo.
echo [ERROR] See log: "%RUNLOG%"
echo.
type "%RUNLOG%"
echo.
pause
:end
popd
endlocal
