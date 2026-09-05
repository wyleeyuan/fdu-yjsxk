@echo off
chcp 65001 >nul
REM ============================================================
REM 复旦研究生选课助手（Windows 版）—— 自检 / 预选课 / 抢课 三合一
REM   1) 自检     检查登录态与课程配置，不发任何选课请求（可反复跑）
REM   2) 预选课   拉取课程列表，生成 / 更新 config.json（顺序即抢课优先级）
REM   3) 开始抢课 按 config.json 自动抢（会等到 start_time 再开抢）
REM   0) 退出
REM   建议顺序：先 1 自检 -> 2 预选课 -> 3 抢课，菜单可随时切换
REM
REM ⚠ 读不到浏览器 Cookie / 报 "This operation requires admin" 时：
REM   先【完全退出 Chrome / Edge】（含托盘 / 后台进程）再重跑，或右键管理员运行。
REM ============================================================
cd /d "%~dp0.."
title 复旦研究生选课助手

REM ---- ① 定位 Python：依次试 python / py -3，取第一个依赖齐全的 ----
set "PYCMD="
python -c "import requests, browser_cookie3" >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD py -3 -c "import requests, browser_cookie3" >nul 2>&1 && set "PYCMD=py -3"
if defined PYCMD goto ready

REM ---- ② 没有依赖齐全的解释器：区分「缺 Python」还是「缺依赖」 ----
set "PIPCMD="
python -c "import sys" >nul 2>&1 && set "PIPCMD=python -m pip"
if not defined PIPCMD py -3 -c "import sys" >nul 2>&1 && set "PIPCMD=py -3 -m pip"

if not defined PIPCMD (
  echo.
  echo [提示] 未找到 Python 3。
  echo   Windows 请安装 python.org 官方版，安装时勾选 "Add python.exe to PATH"
  echo   （会自带 py 启动器）：https://www.python.org/downloads/
  echo   装完重开本窗口即可。
  echo.
  pause
  exit /b 1
)

echo.
echo [提示] Python 已就绪但缺少依赖，正在安装 requests 和 browser-cookie3 ...
%PIPCMD% install -r requirements.txt
echo.

REM ---- ③ 复查依赖；仍不可用就给出手动命令 ----
set "PYCMD="
python -c "import requests, browser_cookie3" >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD py -3 -c "import requests, browser_cookie3" >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD (
  echo [错误] 依赖安装后仍不可用，请手动运行：
  echo     %PIPCMD% install -r requirements.txt
  echo   排查报错后重新双击本脚本。
  echo.
  pause
  exit /b 1
)

:ready
echo.
echo 提示：读不到 Cookie / 报 "This operation requires admin" 时，
echo   先完全退出 Chrome / Edge（含后台进程）再重跑；或右键管理员运行。
echo.

:menu
echo.
echo ==================================================
echo   复旦研究生选课助手（Windows）
echo   ------------------------------------------------
echo     1. 自检      -- 检查登录态与课程配置（不发选课请求）
echo     2. 预选课    -- 拉课程列表，生成/更新 config.json
echo     3. 开始抢课  -- 按 config.json 自动抢（到点开抢）
echo     0. 退出
echo ==================================================
set "choice="
set /p choice=请输入编号并回车：
if "%choice%"=="1" goto check
if "%choice%"=="2" goto preselect
if "%choice%"=="3" goto grab
if "%choice%"=="0" goto end
echo 无效输入，请输入 0~3
goto menu

:check
%PYCMD% src\grab.py --dry-run
echo.
echo 按任意键返回菜单...
pause >nul
goto menu

:preselect
%PYCMD% src\preselect.py
echo.
echo 按任意键返回菜单...
pause >nul
goto menu

:grab
%PYCMD% src\grab.py
set CODE=%ERRORLEVEL%
echo.
echo 脚本结束（退出码 %CODE%：0=全部拿下，1=有课没抢到）
echo 按任意键返回菜单...
pause >nul
goto menu

:end
echo 再见！
pause >nul
