#!/bin/bash
# 三IMU RS485发布器启动脚本
# 自动处理权限并启动程序

echo "========================================"
echo "三IMU RS485发布器启动脚本"
echo "========================================"

# 检查串口设备
SERIAL_PORT="/dev/ttyUSB0"

if [ ! -e "$SERIAL_PORT" ]; then
    echo "❌ 串口设备 $SERIAL_PORT 不存在"
    echo "请检查设备连接"
    exit 1
fi

# 检查权限
if [ ! -r "$SERIAL_PORT" ] || [ ! -w "$SERIAL_PORT" ]; then
    echo "⚠️  串口权限不足，尝试修复..."
    sudo chmod 666 "$SERIAL_PORT"
    
    if [ $? -eq 0 ]; then
        echo "✓ 权限修复成功"
    else
        echo "❌ 权限修复失败"
        exit 1
    fi
fi

echo "✓ 串口设备: $SERIAL_PORT"
echo "✓ 权限检查通过"
echo ""

# 激活虚拟环境
cd "$(dirname "$0")"
source .venv/bin/activate

# 启动程序（使用--online-only模式）
echo "正在启动程序..."
python triple_imu_rs485_publisher.py --online-only "$@"
