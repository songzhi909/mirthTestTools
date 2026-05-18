@echo off
cd /d "%~dp0"
echo [1/3] Cleaning...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo [2/3] Building...
buildenv\Scripts\python.exe -m PyInstaller MirthTools.spec
if %errorlevel% neq 0 (
    echo.
    echo Failed, check errors above
    pause
    exit /b 1
)
echo [3/3] Copying config files...
copy /y config.ini dist\ >nul
copy /y message_types.json dist\ >nul
copy /y sql_templates.json dist\ >nul
echo.
echo Success: dist\MirthTools.exe
echo Config files copied to dist\
pause
