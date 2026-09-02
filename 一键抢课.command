#!/bin/zsh
# 一键抢课 —— 双击即可运行
cd "${0:A:h}" || exit 1

PY="/Users/yuanweile/.workbuddy/binaries/python/envs/default/bin/python"

if [ ! -x "$PY" ]; then
  echo "找不到 Python：$PY"
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
