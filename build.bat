@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo [2/2] PyInstaller 打包中...
buildenv\Scripts\python.exe -m PyInstaller MirthTools.spec
if %errorlevel% equ 0 (
    echo.
    echo 打包成功: dist\MirthTools.exe
) else (
    echo.
    echo 打包失败，请检查错误信息
)
pause
