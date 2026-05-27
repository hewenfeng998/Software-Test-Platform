#!/bin/bash
# 白龙马自动化测试 - Linux客户端代理
# 支持远程桌面控制

SERVER_URL="http://192.168.31.182:5000"
HEARTBEAT_INTERVAL=5
MACHINE_ID=""

echo "============================================="
echo "        白龙马自动化测试 - 客户端代理"
echo "============================================="
echo ""

# 获取系统信息
HOSTNAME=$(hostname)
OS_TYPE="linux"
OS_VERSION=$(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2 || echo "Unknown")
CPU_COUNT=$(nproc)
IP_ADDRESS=$(ip addr show | grep inet | grep -v '127.0.0.1' | grep -v '::1' | head -1 | awk '{print $2}' | cut -d'/' -f1)
SCREEN_WIDTH=$(xrandr 2>/dev/null | grep '*' | head -1 | awk '{print $1}' | cut -d'x' -f1 || echo "1920")
SCREEN_HEIGHT=$(xrandr 2>/dev/null | grep '*' | head -1 | awk '{print $1}' | cut -d'x' -f2 || echo "1080")

echo "主机名: $HOSTNAME"
echo "操作系统: $OS_TYPE"
echo "系统版本: $OS_VERSION"
echo "CPU核心: $CPU_COUNT"
echo "IP地址: $IP_ADDRESS"
echo "屏幕分辨率: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
echo "---------------------------------------------"

# 注册到服务器
echo "正在连接服务器..."

if command -v curl >/dev/null 2>&1; then
    RESPONSE=$(curl -s -X POST "$SERVER_URL/balongma/register" \
        -H "Content-Type: application/json" \
        -d "{\"hostname\":\"$HOSTNAME\",\"os_type\":\"$OS_TYPE\",\"os_version\":\"$OS_VERSION\",\"cpu_count\":$CPU_COUNT,\"ip_address\":\"$IP_ADDRESS\",\"screen_width\":$SCREEN_WIDTH,\"screen_height\":$SCREEN_HEIGHT}" \
        --max-time 5)
elif command -v wget >/dev/null 2>&1; then
    RESPONSE=$(wget -qO- --post-data="{\"hostname\":\"$HOSTNAME\",\"os_type\":\"$OS_TYPE\",\"os_version\":\"$OS_VERSION\",\"cpu_count\":$CPU_COUNT,\"ip_address\":\"$IP_ADDRESS\",\"screen_width\":$SCREEN_WIDTH,\"screen_height\":$SCREEN_HEIGHT}" \
        --header="Content-Type: application/json" \
        --timeout=5 \
        "$SERVER_URL/balongma/register")
else
    echo "错误: 未找到 curl 或 wget"
    exit 1
fi

MACHINE_ID=$(echo "$RESPONSE" | grep -o '"machine_id":[0-9]*' | cut -d':' -f2)

if [ -z "$MACHINE_ID" ]; then
    echo "❌ 注册失败，请检查网络连接"
    exit 1
fi

echo ""
echo "✓ 成功注册到服务器，机器ID: $MACHINE_ID"
echo "✓ 客户端已启动，保持此窗口打开"
echo "✓ 等待远程控制请求..."
echo ""
echo "============================================="

# 心跳循环
while true; do
    if command -v curl >/dev/null 2>&1; then
        curl -s -X POST "$SERVER_URL/balongma/heartbeat/$MACHINE_ID" --max-time 3 >/dev/null
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- -T 3 "$SERVER_URL/balongma/heartbeat/$MACHINE_ID" >/dev/null
    fi
    sleep $HEARTBEAT_INTERVAL
done