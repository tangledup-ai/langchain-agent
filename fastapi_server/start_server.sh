#!/bin/bash

echo "启动Lang Agent Chat API服务器..."

# 检查Python环境
if ! command -v python &> /dev/null; then
    echo "错误: 未找到Python。请确保Python已安装并添加到PATH中。"
    exit 1
fi

# 检查环境变量
if [ -z "$ALI_API_KEY" ]; then
    echo "警告: 未设置ALI_API_KEY环境变量。请确保已设置此变量。"
    echo "例如: export ALI_API_KEY='your_api_key'"
fi

# 启动服务器
cd "$(dirname "$0")"
python server.py