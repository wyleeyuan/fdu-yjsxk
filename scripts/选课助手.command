#!/bin/zsh
# ============================================================
# 复旦研究生选课助手（macOS 版）—— 自检 / 预选课 / 抢课 三合一
#   1) 自检     检查登录态与课程配置，不发任何选课请求（可反复跑）
#   2) 预选课   拉取课程列表，生成 / 更新 config.json（顺序即抢课优先级）
#   3) 开始抢课 按 config.json 自动抢（会等到 start_time 再开抢）
#   0) 退出
#   建议顺序：先 1 自检 → 2 预选课 → 3 抢课，菜单可随时切换
# Python 定位：按顺序探测候选路径，取第一个“存在且依赖齐全”的用
#   ① 作者机器的完整环境（用 $HOME 展开，仓库中不出现任何本机用户名 / 私有路径）
#   ②~⑤ 常见安装位置，clone 仓库后在其他机器上也能直接用
# 本脚本在仓库根的 scripts/ 里，先回到仓库根，再运行 src/ 下的代码
cd "${0:A:h}/.." || exit 1

PY=""
for CAND in \
  "$HOME/.workbuddy/binaries/python/envs/default/bin/python" \
  "/opt/homebrew/bin/python3" \
  "/usr/local/bin/python3" \
  "$HOME/.pyenv/shims/python3" \
  "/usr/bin/python3"; do
  if [ -x "$CAND" ] && "$CAND" -c "import requests, browser_cookie3" >/dev/null 2>&1; then
    PY="$CAND"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "未找到依赖齐全的 Python 3（需要 requests + browser-cookie3）"
  echo ""
  echo "如果你本机已安装 Python 3，请先安装依赖，然后重新双击本脚本："
  echo "  python3 -m pip install --user -r requirements.txt"
  echo ""
  echo "按回车键关闭..."; read
  exit 1
fi

while true; do
  echo ""
  echo "=================================================="
  echo "  复旦研究生选课助手（macOS）"
  echo "  ------------------------------------------------"
  echo "    1) 自检      —— 检查登录态与课程配置（不发选课请求）"
  echo "    2) 预选课    —— 拉课程列表，生成/更新 config.json"
  echo "    3) 开始抢课  —— 按 config.json 自动抢（到点开抢）"
  echo "    0) 退出"
  echo "=================================================="
  read "choice?请输入编号并回车："
  case "$choice" in
    1)
      "$PY" src/grab.py --dry-run
      ;;
    2)
      "$PY" src/preselect.py
      ;;
    3)
      "$PY" src/grab.py
      code=$?
      echo ""
      echo "退出码 $code = 0 表示全部拿下；1 = 有课没抢到"
      ;;
    0)
      echo "再见！"
      break
      ;;
    *)
      echo "无效输入，请输入 0 ~ 3"
      continue
      ;;
  esac
  echo ""
  echo "按回车键返回菜单..."
  read
done
