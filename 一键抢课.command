#!/bin/zsh
# 一键抢课 —— 双击即可运行
# Python 定位：按顺序探测候选路径，取第一个“存在且依赖齐全”的用
#   ① 作者机器的完整环境（用 $HOME 展开，仓库中不出现任何本机用户名 / 私有路径）
#   ②~⑤ 常见安装位置，clone 仓库后在其他机器上也能直接用
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

"$PY" grab.py
code=$?

echo ""
echo "=================================="
echo " 脚本结束（退出码 $code）"
echo " 退出码 0 = 全部拿下；1 = 有课没抢到"
echo "=================================="
echo "按回车键关闭窗口..."
read
