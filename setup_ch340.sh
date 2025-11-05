#!/bin/bash
# CH340 RS485设备快速设置脚本

echo "🔧 CH340 RS485设备快速设置"
echo "=================================================="

# 1. 停止可能干扰的BRLTTY服务
echo "1. 停止BRLTTY服务..."
sudo systemctl stop brltty 2>/dev/null
sudo systemctl disable brltty 2>/dev/null
echo "   ✅ BRLTTY服务已停止"

# 2. 确保驱动已加载
echo "2. 检查并加载CH341驱动..."
if lsmod | grep -q ch341; then
    echo "   ✅ CH341驱动已加载"
else
    echo "   加载CH341驱动..."
    sudo modprobe ch341-uart
    if [ $? -eq 0 ]; then
        echo "   ✅ CH341驱动加载成功"
    else
        echo "   ❌ CH341驱动加载失败"
    fi
fi

# 3. 等待设备插入
echo "3. 等待CH340设备..."
echo "   请确保您的CH340设备已插入USB端口"

# 等待ttyUSB0设备出现
for i in {1..10}; do
    if [ -e /dev/ttyUSB0 ]; then
        echo "   ✅ 找到设备: /dev/ttyUSB0"
        break
    fi
    echo "   等待设备... (${i}/10)"
    sleep 1
done

# 4. 设置设备权限
if [ -e /dev/ttyUSB0 ]; then
    echo "4. 设置设备权限..."
    sudo chmod 666 /dev/ttyUSB0
    if [ $? -eq 0 ]; then
        echo "   ✅ 权限设置成功"
        echo "   设备可用: /dev/ttyUSB0"
    else
        echo "   ❌ 权限设置失败"
    fi
else
    echo "❌ 设备未找到，请检查:"
    echo "   - 设备是否正确插入"
    echo "   - USB线是否正常"
    echo "   - 设备驱动是否正确"
fi

# 5. 显示设备信息
echo "5. 设备信息:"
if [ -e /dev/ttyUSB0 ]; then
    ls -la /dev/ttyUSB0
    echo ""
    echo "🎉 设备设置完成!"
    echo "现在可以运行: python simple_test.py"
else
    echo "❌ 设备设置失败"
    echo ""
    echo "📋 手动检查命令:"
    echo "   查看USB设备: lsusb | grep CH340"
    echo "   查看驱动: lsmod | grep ch341"
    echo "   查看日志: sudo dmesg | tail -20"
fi

echo "=================================================="