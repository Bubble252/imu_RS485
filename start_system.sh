#!/bin/bash
# 快速启动脚本 - Triple IMU + LeRobot完整系统

echo "====================================================================="
echo "        Triple IMU + LeRobot 完整系统启动向导"
echo "====================================================================="
echo ""
echo "📋 系统组件："
echo "  1. B端（B_reverse_whole.py）       - 端口5555,5557,5558"
echo "  2. 本地LeRobot（lerobot_zeroMQ_imu.py） - 端口5559"
echo "  3. C端（C_real_video_reverse.py）   - 连接到B端"
echo "  4. A端（triple_imu_rs485_publisher.py） - 连接到B和LeRobot"
echo ""
echo "⚠️  重要：必须按照以下顺序启动（bind端口先启动）"
echo "====================================================================="
echo ""

# 检查是否在正确的目录
if [ ! -f "triple_imu_rs485_publisher.py" ]; then
    echo "❌ 错误：请在WIT_RS485目录下运行此脚本"
    exit 1
fi

# 询问用户启动模式
echo "请选择启动模式："
echo "  1. 完整系统（B + LeRobot + C + Triple）"
echo "  2. 本地测试（仅LeRobot + Triple）"
echo "  3. 远程测试（仅B + Triple，需手动启动B端）"
echo ""
read -p "请输入选项 [1-3]: " mode

case $mode in
    1)
        echo ""
        echo "🚀 启动模式：完整系统"
        echo "====================================================================="
        echo ""
        
        # 第1步：启动B端
        echo "步骤 1/4：启动B端（B_reverse_whole.py）..."
        echo "  ⏳ 请在新终端运行："
        echo "     cd whole2 && python B_reverse_whole.py"
        echo ""
        read -p "B端已启动？按Enter继续..."
        
        # 第2步：启动LeRobot
        echo ""
        echo "步骤 2/4：启动本地LeRobot（lerobot_zeroMQ_imu.py）..."
        echo "  ⏳ 请在新终端运行："
        echo "     python lerobot_zeroMQ_imu.py"
        echo ""
        read -p "LeRobot已启动？按Enter继续..."
        
        # 第3步：启动C端
        echo ""
        echo "步骤 3/4：启动C端（C_real_video_reverse.py）..."
        echo "  ⏳ 请在新终端运行："
        echo "     cd whole2 && python C_real_video_reverse.py"
        echo ""
        read -p "C端已启动？按Enter继续..."
        
        # 第4步：启动Triple
        echo ""
        echo "步骤 4/4：启动Triple（triple_imu_rs485_publisher.py）..."
        echo "  ⏳ 即将启动..."
        sleep 2
        
        # 检查是否需要视频
        read -p "是否启用视频接收？[y/N]: " enable_video
        
        if [[ "$enable_video" == "y" || "$enable_video" == "Y" ]]; then
            echo ""
            echo "✓ 启动Triple（带视频接收）..."
            python triple_imu_rs485_publisher.py --online-only --enable-video
        else
            echo ""
            echo "✓ 启动Triple（无视频）..."
            python triple_imu_rs485_publisher.py --online-only
        fi
        ;;
        
    2)
        echo ""
        echo "🚀 启动模式：本地测试（LeRobot + Triple）"
        echo "====================================================================="
        echo ""
        
        # 第1步：启动LeRobot
        echo "步骤 1/2：启动本地LeRobot（lerobot_zeroMQ_imu.py）..."
        echo "  ⏳ 请在新终端运行："
        echo "     python lerobot_zeroMQ_imu.py"
        echo ""
        read -p "LeRobot已启动？按Enter继续..."
        
        # 第2步：启动Triple
        echo ""
        echo "步骤 2/2：启动Triple（triple_imu_rs485_publisher.py）..."
        echo "  ⏳ 即将启动..."
        sleep 2
        
        echo ""
        echo "✓ 启动Triple（仅连接本地LeRobot）..."
        # 注意：B端未启动，会连接失败，但LeRobot端口5559仍可用
        python triple_imu_rs485_publisher.py --online-only \
               --lerobot-host localhost --lerobot-port 5559
        ;;
        
    3)
        echo ""
        echo "🚀 启动模式：远程测试（B + Triple）"
        echo "====================================================================="
        echo ""
        
        read -p "请输入B端服务器地址 [默认localhost]: " b_host
        b_host=${b_host:-localhost}
        
        echo ""
        echo "步骤 1/1：启动Triple（连接到B端）..."
        echo "  ⚠️  请确保B端已在 $b_host 启动！"
        echo ""
        read -p "B端已启动？按Enter继续..."
        
        # 检查是否需要视频
        read -p "是否启用视频接收？[y/N]: " enable_video
        
        if [[ "$enable_video" == "y" || "$enable_video" == "Y" ]]; then
            echo ""
            echo "✓ 启动Triple（连接B端 + 视频接收）..."
            python triple_imu_rs485_publisher.py --online-only \
                   --b-host "$b_host" --b-port 5555 \
                   --enable-video --video-host "$b_host" --video-port 5557
        else
            echo ""
            echo "✓ 启动Triple（仅连接B端）..."
            python triple_imu_rs485_publisher.py --online-only \
                   --b-host "$b_host" --b-port 5555
        fi
        ;;
        
    *)
        echo "❌ 无效选项，退出"
        exit 1
        ;;
esac

echo ""
echo "====================================================================="
echo "Triple已退出"
echo "====================================================================="
echo ""
echo "⚠️  记得按顺序停止其他服务："
echo "  1. 停止C端（如果启动了）"
echo "  2. 停止LeRobot（如果启动了）"
echo "  3. 停止B端（如果启动了）"
echo ""
