@echo off
setlocal

chcp 65001 >nul
pushd "%~dp0"

set "APP_NAME=Epub工具箱"
set "ENTRY=main.py"
set "ICON=logo\logo.ico"
set "DATA_FILE=tiku_config.json"
set "PY=.venv\Scripts\python.exe"

title Build Epub Toolbox

echo ======================================================
echo                  Build Epub工具箱
echo ======================================================
echo.

if not exist "%ENTRY%" (
    echo [ERROR] Entry file not found: %ENTRY%
    echo.
    pause
    exit /b 1
)

if not exist "%ICON%" (
    echo [ERROR] Icon not found: %ICON%
    echo.
    pause
    exit /b 1
)

if not exist "%PY%" (
    echo [ERROR] Python not found: %PY%
    echo.
    pause
    exit /b 1
)

echo [INFO] App name: %APP_NAME%
echo [INFO] Entry: %ENTRY%
echo [INFO] Icon: %ICON%
echo.

if exist build rd /s /q build
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"
if exist "dist\Epub_Helper.exe" del /q "dist\Epub_Helper.exe"

"%PY%" -m PyInstaller --clean --noconsole --onefile --icon="%ICON%" --name "%APP_NAME%" --hidden-import edge_tts --hidden-import tkinterdnd2 --collect-data tkinterdnd2 "%ENTRY%"

echo.
if %errorlevel% neq 0 (
    echo [ERROR] Build failed.
    echo.
    pause
    exit /b 1
)

if exist "%DATA_FILE%" (
    copy /Y "%DATA_FILE%" "dist\%DATA_FILE%" >nul
    echo [INFO] Copied %DATA_FILE% to dist.
)

echo [DONE] Build succeeded: dist\%APP_NAME%.exe
echo.
popd
pause
