#!/bin/bash

# 白龙马自动化测试 - Linux客户端代理安装脚本
# 使用说明: bash client_agent.sh <服务器地址>

SERVER_URL="${1:-http://192.168.31.182:5000}"

echo "=========================================="
echo "  白龙马自动化测试 - Linux客户端代理"
echo "=========================================="
echo ""

# 检查是否以root身份运行
if [ "$(id -u)" != "0" ]; then
    echo "⚠️  警告：建议以root身份运行以安装依赖"
    echo ""
fi

# 检查Python3是否安装
if ! command -v python3 &> /dev/null; then
    echo "📦 正在安装Python3..."
    if command -v apt-get &> /dev/null; then
        apt-get update && apt-get install -y python3 python3-pip
    elif command -v yum &> /dev/null; then
        yum install -y python3 python3-pip
    elif command -v dnf &> /dev/null; then
        dnf install -y python3 python3-pip
    else
        echo "❌ 无法自动安装Python3，请手动安装"
        exit 1
    fi
else
    echo "✅ Python3 已安装"
fi

# 检查pip3是否安装
if ! command -v pip3 &> /dev/null; then
    echo "📦 正在安装pip3..."
    if command -v apt-get &> /dev/null; then
        apt-get install -y python3-pip
    elif command -v yum &> /dev/null; then
        yum install -y python3-pip
    elif command -v dnf &> /dev/null; then
        dnf install -y python3-pip
    else
        echo "❌ 无法自动安装pip3，请手动安装"
        exit 1
    fi
else
    echo "✅ pip3 已安装"
fi

# 安装必要的Python依赖
echo ""
echo "📦 正在安装Python依赖..."
pip3 install requests pyautogui python-xlib Pillow

# 创建客户端目录
CLIENT_DIR="/opt/balongma_agent"
mkdir -p "$CLIENT_DIR"

# 下载客户端代理脚本
echo ""
echo "📥 正在下载客户端代理脚本..."
curl -s -o "$CLIENT_DIR/client_agent.py" "$SERVER_URL/balongma/download_client?platform=python"

# 修改SERVER_URL
echo "🔧 正在配置服务器地址..."
sed -i "s|http://192.168.31.182:5000|$SERVER_URL|g" "$CLIENT_DIR/client_agent.py"

# 创建启动脚本
echo "🔧 正在创建启动脚本..."
cat > "$CLIENT_DIR/start.sh" << EOF
#!/bin/bash
cd "$CLIENT_DIR"
python3 client_agent.py
EOF
chmod +x "$CLIENT_DIR/start.sh"

# 创建systemd服务（可选）
if command -v systemctl &> /dev/null; then
    echo ""
    echo "🔧 是否创建systemd服务？(y/n)"
    read -r create_service
    if [ "$create_service" = "y" ] || [ "$create_service" = "Y" ]; then
        cat > /etc/systemd/system/balongma_agent.service << EOF
[Unit]
Description=白龙马自动化测试客户端代理
After=network.target

[Service]
ExecStart=$CLIENT_DIR/start.sh
Restart=always
User=root
WorkingDirectory=$CLIENT_DIR

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable balongma_agent
        echo "✅ systemd服务已创建"
    fi
fi

echo ""
echo "=========================================="
echo "✅ 安装完成！"
echo "=========================================="
echo ""
echo "启动方式："
echo "1. 直接运行：bash $CLIENT_DIR/start.sh"
echo "2. 或使用systemd：systemctl start balongma_agent"
echo ""
echo "服务器地址：$SERVER_URL"
echo "客户端目录：$CLIENT_DIR"
echo ""