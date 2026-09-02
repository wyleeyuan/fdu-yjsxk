@echo off
chcp 65001 >nul
REM 开抢前先跑这个做自检（Windows 版）
REM 检查 Cookie 是否有效、课程代码是否正确，不会提交任何选课请求
cd /d "%~dp0"

set PY=python

python -c "import requests, browser_cookie3" >nul 2>&1
if errorlevel 1 (
  echo [提示] 未检测到依赖，先安装 requests 和 browser-cookie3 ...
  python -m pip install -r requirements.txt
  echo.
)

python grab.py --dry-run

echo.
echo 按任意键关闭窗口...
pause >nul
