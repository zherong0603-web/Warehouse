#!/bin/zsh
cd "$(dirname "$0")" || exit 1
/usr/bin/env python3 run_stage1.py
echo ""
echo "阶段 1 运行结束。输出已生成在项目目录中。"
echo "按任意键关闭窗口。"
read -k 1
