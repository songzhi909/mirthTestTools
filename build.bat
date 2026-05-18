@echo off
cd /d "%~dp0"
echo [1/2] Cleaning...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo [2/2] Building...
buildenv\Scripts\python.exe -m PyInstaller MirthTools.spec
if %errorlevel% equ 0 (
    echo.
    echo Success: dist\MirthTools.exe
) else (
    echo.
    echo Failed, check errors above
)
pause
