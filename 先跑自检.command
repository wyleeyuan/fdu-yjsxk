#!/bin/zsh
# 开抢前先跑这个做自检：检查 Cookie 是否有效、课程代码是否正确
# 不会提交任何选课请求，可以放心反复运行
# Python 定位策略同 一键抢课.command（$HOME 展开 + 候选探测，作者机器与 clone 用户均可直接用）
cd "${0:A:h}" || exit 1

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

"$PY" grab.py --dry-run

echo ""
echo "按回车键关闭窗口..."
read
