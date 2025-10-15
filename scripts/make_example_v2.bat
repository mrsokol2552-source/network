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

REM --- Load .env (optional) for NET_USER/NET_PASS/NET_ENABLE ---
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%K in (".env") do (
    if not "%%K"=="" if not "%%K:~0,1"=="#" set "%%K=%%L"
  )
)

REM Restore exclusions by IP/CIDR for scan
set EXCLUDE_IPS=10.12.0.0/24,10.10.0.0/24,10.0.2.31/24,10.0.2.91/24,10.0.2.27/24,10.0.2.28/24,10.0.2.126/24,10.0.2.20/24,10.0.2.137/24,10.20.99.201,10.20.99.140

REM Default parallelism for TextFSM parsing if not provided
if "%PARSE_WORKERS%"=="" set PARSE_WORKERS=16

REM Default parallelism for device collection (SSH/Telnet) if not provided
if "%MAX_WORKERS%"=="" set MAX_WORKERS=4
REM Default parallelism for TCP 22/23 probing if not provided
if "%TCP_WORKERS%"=="" set TCP_WORKERS=128
REM Connection timeouts tuning (seconds)
if "%CONNECT_TIMEOUT%"=="" set CONNECT_TIMEOUT=2
if "%AUTH_TIMEOUT%"=="" set AUTH_TIMEOUT=6
REM Low-level tuning for TCP and command read deadlines
if "%TCP_TIMEOUT%"=="" set TCP_TIMEOUT=0.8
if "%SENDCMD_TIMEOUT%"=="" set SENDCMD_TIMEOUT=30
if "%HOST_DEADLINE%"=="" set HOST_DEADLINE=90

REM --- Stage 1: collect with real-time tee via PowerShell ---
echo [STEP 1] Collect CLI (stage1_collect.py) >> "%RUNLOG%"
powershell -NoProfile -Command ^
  "$env:PYTHONUNBUFFERED='1'; $env:CONNECT_TIMEOUT='%CONNECT_TIMEOUT%'; $env:AUTH_TIMEOUT='%AUTH_TIMEOUT%'; $env:TCP_TIMEOUT='%TCP_TIMEOUT%'; $env:SENDCMD_TIMEOUT='%SENDCMD_TIMEOUT%'; $env:HOST_DEADLINE='%HOST_DEADLINE%'; python -u stage1_collect.py --max-workers %MAX_WORKERS% --tcp-timeout %TCP_TIMEOUT% --conn-timeout %CONNECT_TIMEOUT% --auth-timeout %AUTH_TIMEOUT% --cidr 10.20.98.0/24 10.20.99.0/24 10.20.97.0/24 10.2.99.0/24 10.0.2.0/24 2>&1 | Tee-Object -FilePath '%RUNLOG%' -Append; exit $LASTEXITCODE" 
if errorlevel 1 goto :fail

REM --- Stage 2+: pipeline (skip collect) ---
REM Call the unified Python pipeline. Adjust CIDR/targets as needed or pass via %*
python -m src.pipeline --config config\config.json --env .env --log-file "%RUNLOG%" --steps parse,split,merge,safety,normalize,render --max-workers %MAX_WORKERS% --tcp-workers %TCP_WORKERS% --parse-workers %PARSE_WORKERS% %*
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
