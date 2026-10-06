@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
    echo Install uv first. See README.md for Windows setup.
    pause
    exit /b 1
)
set "PHOTO_INPUT=%~1"
if not defined PHOTO_INPUT set /p "PHOTO_INPUT=Photo folder: "
if not defined PHOTO_INPUT exit /b 1
uv run photo-group-picker "%PHOTO_INPUT%" --output "%~dp0output"
if errorlevel 1 (
    pause
    exit /b 1
)
start "" "%~dp0output\index.html"
pause
