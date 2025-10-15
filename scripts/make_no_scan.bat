@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

REM ===== Mermaid NetDocs: pipeline without network scan =====
pushd "%~dp0\.."
set "ROOT=%CD%"
set "LOGS=%ROOT%\data\output\logs"
set "RUNLOG=%LOGS%\run.log"
if not exist "%LOGS%" mkdir "%LOGS%"
echo ===== RUN START %DATE% %TIME% (NO-SCAN) ===== > "%RUNLOG%" 2>&1

REM Python presence check
python -V >nul 2>&1 || (echo [ERROR] Python not found in PATH>>"%RUNLOG%" & goto :fail)

REM --- Load .env (optional) for NET_USER/NET_PASS/NET_ENABLE ---
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%K in (".env") do (
    if not "%%K"=="" if not "%%K:~0,1"=="#" set "%%K=%%L"
  )
)

REM Default parallelism for TextFSM parsing if not provided
if "%PARSE_WORKERS%"=="" set PARSE_WORKERS=16

REM --- Single pipeline run without collect (no subnet scan) ---
python -m src.pipeline --config config\config.json --env .env --log-file "%RUNLOG%" --steps parse,split,merge,safety,normalize,render --parse-workers %PARSE_WORKERS% %*
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

