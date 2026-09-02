@echo off
chcp 65001 >nul
REM 一键抢课 —— 双击即可运行（Windows 版）
cd /d "%~dp0"

set PY=python

python -c "import requests, browser_cookie3" >nul 2>&1
if errorlevel 1 (
  echo [提示] 未检测到依赖，先安装 requests 和 browser-cookie3 ...
  python -m pip install -r requirements.txt
  echo.
)

python grab.py
set CODE=%ERRORLEVEL%

echo.
echo ==================================
echo  脚本结束（退出码 %CODE%）
echo  退出码 0 = 全部拿下；1 = 有课没抢到
echo ==================================
echo.
echo 按任意键关闭窗口...
pause >nul
