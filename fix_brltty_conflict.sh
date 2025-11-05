#!/bin/bash
# CH340 与 BRLTTY 冲突的终极解决方案

echo "🔧 CH340 与 BRLTTY 冲突终极解决方案"
echo "=================================================="

echo "检测到BRLTTY持续干扰CH340设备。"
echo "BRLTTY是盲文显示器支持服务，如果您不需要盲文支持，建议移除。"
echo ""

echo "请选择解决方案："
echo "1. 完全移除BRLTTY包 (推荐，如果不需要盲文支持)"
echo "2. 配置BRLTTY排除CH340设备"
echo "3. 使用其他串口号（如果有多个串口设备）"
echo "4. 退出"

read -p "请输入选择 (1-4): " choice

case $choice in
    1)
        echo "选择方案1: 移除BRLTTY包"
        echo "这将完全移除盲文显示器支持，但解决CH340冲突问题。"
        read -p "确认移除BRLTTY? (y/n): " confirm
        if [ "$confirm" = "y" ]; then
            echo "移除BRLTTY包..."
            sudo apt remove --purge brltty -y
            sudo apt autoremove -y
            echo "✅ BRLTTY已移除"
            
            echo "重新插入CH340设备..."
            read -p "请重新插入CH340设备，然后按Enter: "
            
            sleep 3
            if [ -e /dev/ttyUSB0 ]; then
                sudo chmod 666 /dev/ttyUSB0
                echo "✅ 设备就绪: /dev/ttyUSB0"
                ls -la /dev/ttyUSB0
            else
                echo "❌ 设备仍未创建，可能需要重启系统"
            fi
        fi
        ;;
    2)
        echo "选择方案2: 配置BRLTTY排除CH340"
        echo "配置BRLTTY以排除CH340设备..."
        
        # 备份原配置
        sudo cp /etc/brltty.conf /etc/brltty.conf.backup 2>/dev/null || true
        
        # 添加排除规则
        echo "device-parameters:usb:,exclude={idVendor=1a86}" | sudo tee -a /etc/brltty.conf
        
        # 重启BRLTTY服务
        sudo systemctl restart brltty
        
        echo "✅ BRLTTY配置已更新"
        echo "重新插入CH340设备测试..."
        read -p "请重新插入CH340设备，然后按Enter: "
        
        sleep 3
        if [ -e /dev/ttyUSB0 ]; then
            sudo chmod 666 /dev/ttyUSB0
            echo "✅ 设备就绪: /dev/ttyUSB0"
            ls -la /dev/ttyUSB0
        else
            echo "❌ 配置未生效，建议选择方案1"
        fi
        ;;
    3)
        echo "选择方案3: 查找其他可用串口"
        echo "当前可用的串口设备:"
        ls -la /dev/ttyS* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -10
        echo ""
        echo "如果您的设备支持，可以尝试使用/dev/ttyS0或其他串口"
        echo "需要修改程序中的串口配置"
        ;;
    4)
        echo "退出"
        exit 0
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac

echo ""
echo "=================================================="
echo "解决方案执行完毕。"
echo "如果问题仍然存在，建议重启系统后再试。"