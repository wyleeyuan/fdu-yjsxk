#!/bin/zsh
# 开抢前先跑这个做自检：检查 Cookie 是否有效、课程代码是否正确
# 不会提交任何选课请求，可以放心反复运行
cd "${0:A:h}" || exit 1

PY="/Users/yuanweile/.workbuddy/binaries/python/envs/default/bin/python"

if [ ! -x "$PY" ]; then
  echo "找不到 Python：$PY"
  echo ""
  echo "按回车键关闭..."; read
  exit 1
fi

"$PY" grab.py --dry-run

echo ""
echo "按回车键关闭窗口..."
read
