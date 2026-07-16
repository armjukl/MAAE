@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem 优先使用 Windows Python Launcher，未安装时回退到 python 命令。
where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON=py -3"
) else (
    set "PYTHON=python"
)

echo [1/2] 正在安装 Python 依赖...
%PYTHON% -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/2] 正在安装 Playwright Chromium 浏览器...
%PYTHON% -m playwright install chromium
if errorlevel 1 goto :error

echo.
echo 环境准备完成。可运行 python main.py 启动项目。
pause
exit /b 0

:error
echo.
echo 环境准备失败。请确认已安装 Python 3，并且网络可以访问 Python 软件源。
pause
exit /b 1
