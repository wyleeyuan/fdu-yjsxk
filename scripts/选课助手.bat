@echo off
chcp 65001 >nul
REM ============================================================
REM 复旦研究生选课助手（Windows 版）—— 自检 / 预选课 / 抢课 三合一
REM   1) 自检     检查登录态与课程配置，不发任何选课请求（可反复跑）
REM   2) 预选课   拉取课程列表，生成 / 更新 config.json（顺序即抢课优先级）
REM   3) 开始抢课 按 config.json 自动抢（会等到 start_time 再开抢）
REM   0) 退出
REM   建议顺序：先 1 自检 -> 2 预选课 -> 3 抢课，菜单可随时切换
REM 本脚本在仓库根的 scripts\ 里，先回到仓库根，再运行 src\ 下的代码
cd /d "%~dp0.."
title 复旦研究生选课助手

python -c "import requests, browser_cookie3" >nul 2>&1
if errorlevel 1 (
  echo [提示] 未检测到依赖，先安装 requests 和 browser-cookie3 ...
  python -m pip install -r requirements.txt
  echo.
)

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
python src\grab.py --dry-run
echo.
echo 按任意键返回菜单...
pause >nul
goto menu

:preselect
python src\preselect.py
echo.
echo 按任意键返回菜单...
pause >nul
goto menu

:grab
python src\grab.py
set CODE=%ERRORLEVEL%
echo.
echo 脚本结束（退出码 %CODE%：0=全部拿下，1=有课没抢到）
echo 按任意键返回菜单...
pause >nul
goto menu

:end
echo 再见！
pause >nul
