set PYTHONUTF8=1
set PYTHONIOENCODING=UTF-8
@echo off
chcp 65001 >nul
setlocal ENABLEDELAYEDEXPANSION

REM ===== Mermaid NetDocs — SCAN TEST =====
REM Порядок: scan -> textfsm -> normalize -> render (инвентарь пустой)

pushd "%~dp0"
if exist "config\config.json" (
  REM уже в корне
) else if exist "..\config\config.json" (
  cd ..
) else (
  echo [ERROR] Не найден config\config.json ни в текущей папке, ни на уровень выше.
  goto :fail
)

REM --- Пути ---
set CFG=config\config.json
set INV=data\input\inventory.empty.json
set LOGS=data\output\logs
set OUTMMD=data\output\network.mmd
set RUNLOG=%LOGS%\scan_test.log

REM --- Python ---
python -V >nul 2>&1 || (echo [ERROR] Python не найден в PATH. & goto :fail)

REM --- Каталоги (включая сырые выводы) ---
if not exist "data\output" mkdir "data\output"
if not exist "%LOGS%" mkdir "%LOGS%"
if not exist "data\raw" mkdir "data\raw"
if not exist "data\input\cli" mkdir "data\input\cli"
echo ===== SCAN TEST START %DATE% %TIME% ===== > "%RUNLOG%" 2>&1

REM --- textfsm для парсинга CLI (если не установлен) ---
python -c "import textfsm" 2>nul || (
  echo [INFO] Устанавливаю textfsm ... >> "%RUNLOG%"
  python -m pip install --upgrade pip >> "%RUNLOG%" 2>&1
  pip install textfsm >> "%RUNLOG%" 2>&1 || (echo [ERROR] Не удалось установить textfsm & goto :fail)
)
set NET_USER=zhiltsov_a
set NET_PASS=Sasha255255sasha
set NET_ENABLE=
echo.
echo [STEP 1] СКАН подсетей (stage1_collect.py)
REM ВАШИ CIDR для скана:
REM ---- ШАГ 2 (после успешного шага 1): расширяем до /24 (разкомментировать при готовности) ----
REM ---- СЕРЬЁЗНЫЙ СКАН: все MGMT-подсети /24 ----
python stage1_collect.py --max-workers 32 ^
  --tcp-timeout 0.8 --conn-timeout 3 --auth-timeout 12 --cidr ^
  10.20.99.0/24 ^
  10.20.98.0/24 ^
  10.20.97.0/24 ^
  10.2.99.0/24 ^
  10.0.2.0/24
REM при желании жёстко валиться на ошибках:
REM if errorlevel 1 goto :fail

echo.
echo [STEP 2] PARSE CLI (textfsm -> parsed_textfsm.json)
python -m src --run textfsm --config "%CFG%" >> "%RUNLOG%" 2>&1 || goto :fail

echo.
echo [STEP 3] NORMALIZE (с пустым инвентарём)
python -m src --run normalize --config "%CFG%" --inventory "%INV%" >> "%RUNLOG%" 2>&1 || goto :fail

echo.
echo [STEP 4] RENDER (Mermaid -> "%OUTMMD%")
python -m src --run render --config "%CFG%" --normalized "%LOGS%\normalized.json" --out "%OUTMMD%" >> "%RUNLOG%" 2>&1 || goto :fail

echo.
echo [OK] Готово: "%OUTMMD%"
echo [LOG] %RUNLOG%
echo.
type "%RUNLOG%"
echo.
pause
goto :end

:fail
echo.
echo [ERROR] Сбой. Смотри логи: "%RUNLOG%"
echo.
type "%RUNLOG%"
echo.
pause
:end
popd
endlocal