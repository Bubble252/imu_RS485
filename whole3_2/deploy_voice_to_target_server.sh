#!/bin/bash
# 将 B_reverse_whole_voice.py 部署到目标服务器 (202.112.113.74:2237)
# 通过跳板机 (202.112.113.78:2258) 访问
# 带音频转发功能的版本

set -e  # 遇到错误立即退出

# --- 配置 ---
TARGET_HOST="202.112.113.74"
TARGET_PORT="2237"
TARGET_USER="root"
TARGET_SSH_KEY="./capri_yhx_2237"

JUMPHOST="202.112.113.78"
JUMPHOST_PORT="2258"
JUMPHOST_USER="root"
JUMPHOST_SSH_KEY="./leo_tmp_2258.txt"

REMOTE_DIR="/data7/yhx/lerobot_data_collection"  # 目标服务器上的目录
# ------------

echo "========================================"
echo "部署音频版本到目标服务器（通过跳板机）"
echo "========================================"
echo "跳板机: $JUMPHOST_USER@$JUMPHOST:$JUMPHOST_PORT"
echo "目标服务器: $TARGET_USER@$TARGET_HOST:$TARGET_PORT"
echo "远程目录: $REMOTE_DIR"
echo "版本: B_reverse_whole_voice.py (支持音频转发)"
echo "========================================"
echo ""

# 1. 检查 SSH 密钥
if [ ! -f "$JUMPHOST_SSH_KEY" ]; then
    echo "❌ 错误: 跳板机 SSH 密钥文件不存在: $JUMPHOST_SSH_KEY"
    exit 1
fi

if [ ! -f "$TARGET_SSH_KEY" ]; then
    echo "❌ 错误: 目标服务器 SSH 密钥文件不存在: $TARGET_SSH_KEY"
    exit 1
fi

chmod 400 "$JUMPHOST_SSH_KEY"
chmod 400 "$TARGET_SSH_KEY"
echo "✅ SSH 密钥检查完成"

# 2. 检查本地文件是否存在
echo ""
echo "📋 检查本地文件..."
if [ ! -f "B_reverse_whole_voice.py" ]; then
    echo "❌ 错误: 文件不存在: B_reverse_whole_voice.py"
    echo "   请确保在 whole3_2 目录下运行此脚本"
    exit 1
fi
echo "✅ B_reverse_whole_voice.py 文件存在"

# 3. 创建远程目录
echo ""
echo "📁 创建目标服务器远程目录..."
ssh -i "$JUMPHOST_SSH_KEY" -p "$JUMPHOST_PORT" -o StrictHostKeyChecking=no \
    "$JUMPHOST_USER@$JUMPHOST" \
    "ssh -i /root/.ssh/capri_yhx_2237 -p $TARGET_PORT -o StrictHostKeyChecking=no \
    $TARGET_USER@$TARGET_HOST 'mkdir -p $REMOTE_DIR'"

if [ $? -eq 0 ]; then
    echo "✅ 远程目录创建成功: $REMOTE_DIR"
else
    echo "❌ 远程目录创建失败"
    echo "ℹ️  提示: 需要先将目标服务器的 SSH 密钥复制到跳板机"
    echo "   scp -i $JUMPHOST_SSH_KEY -P $JUMPHOST_PORT $TARGET_SSH_KEY $JUMPHOST_USER@$JUMPHOST:/root/.ssh/"
    exit 1
fi

# 4. 上传文件到跳板机临时目录
echo ""
echo "📤 步骤1: 上传文件到跳板机临时目录..."

TEMP_DIR="/tmp/lerobot_deploy_voice_$(date +%s)"
ssh -i "$JUMPHOST_SSH_KEY" -p "$JUMPHOST_PORT" -o StrictHostKeyChecking=no \
    "$JUMPHOST_USER@$JUMPHOST" "mkdir -p $TEMP_DIR"

FILES=(
    "B_reverse_whole_voice.py"
)

for file in "${FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ 错误: 文件不存在: $file"
        exit 1
    fi
    
    echo "   上传: $file"
    scp -i "$JUMPHOST_SSH_KEY" -P "$JUMPHOST_PORT" -o StrictHostKeyChecking=no \
        "$file" "$JUMPHOST_USER@$JUMPHOST:$TEMP_DIR/"
    
    if [ $? -eq 0 ]; then
        echo "   ✅ $file 上传到跳板机成功"
    else
        echo "   ❌ $file 上传到跳板机失败"
        exit 1
    fi
done

# 5. 从跳板机传输文件到目标服务器
echo ""
echo "📤 步骤2: 从跳板机传输文件到目标服务器..."

ssh -i "$JUMPHOST_SSH_KEY" -p "$JUMPHOST_PORT" -o StrictHostKeyChecking=no \
    "$JUMPHOST_USER@$JUMPHOST" << ENDSSH
set -e

cd $TEMP_DIR

echo "开始传输文件到目标服务器..."
for file in *.py; do
    if [ -f "\$file" ]; then
        echo "   传输: \$file"
        scp -i /root/.ssh/capri_yhx_2237 -P $TARGET_PORT -o StrictHostKeyChecking=no \
            "\$file" "$TARGET_USER@$TARGET_HOST:$REMOTE_DIR/"
        
        if [ \$? -eq 0 ]; then
            echo "   ✅ \$file 传输成功"
        else
            echo "   ❌ \$file 传输失败"
            exit 1
        fi
    fi
done

# 清理临时文件
rm -rf $TEMP_DIR
echo "✅ 临时文件已清理"
ENDSSH

if [ $? -ne 0 ]; then
    echo "❌ 文件传输到目标服务器失败"
    exit 1
fi

# 6. 在目标服务器上创建启动脚本
echo ""
echo "📝 在目标服务器上创建启动脚本..."

ssh -i "$JUMPHOST_SSH_KEY" -p "$JUMPHOST_PORT" -o StrictHostKeyChecking=no \
    "$JUMPHOST_USER@$JUMPHOST" \
    "ssh -i /root/.ssh/capri_yhx_2237 -p $TARGET_PORT -o StrictHostKeyChecking=no \
    $TARGET_USER@$TARGET_HOST" << 'ENDSSH'

cd /data7/yhx/lerobot_data_collection

# 创建音频版本启动脚本
cat > start_b_voice.sh << "EOFSTART"
#!/bin/bash
# 启动 B_reverse_whole_voice.py - LeRobot数据收集服务器（支持音频转发）

cd "$(dirname "$0")"

echo "========================================"
echo "启动 LeRobot 数据收集服务器 B (音频版)"
echo "========================================"
echo "工作目录: $(pwd)"
echo "时间: $(date)"
echo "功能: 视频 + 音频转发"
echo "========================================"
echo ""

# 检查并激活 Conda 环境
if command -v conda &> /dev/null; then
    echo "检测到 Conda 环境"
    # 尝试激活 lerobot_server 环境
    source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/anaconda3/etc/profile.d/conda.sh 2>/dev/null || true
    conda activate lerobot_server 2>/dev/null || echo "⚠️  未找到 lerobot_server 环境，使用系统 Python"
fi

# 检查 Python 版本和路径
echo "Python 版本: $(python3 --version)"
echo "Python 路径: $(which python3)"
echo ""

# 检查依赖库
echo "检查依赖库..."

if python3 -c "import lerobot" 2>/dev/null; then
    echo "✅ lerobot 库已安装"
else
    echo "❌ 错误: 未找到 lerobot 库"
    echo "请先安装: pip install lerobot"
    exit 1
fi

if python3 -c "import zmq" 2>/dev/null; then
    echo "✅ zmq 库已安装"
else
    echo "❌ 错误: 未找到 zmq 库"
    echo "请先安装: pip install pyzmq"
    exit 1
fi

if python3 -c "import cv2" 2>/dev/null; then
    echo "✅ cv2 库已安装"
else
    echo "❌ 错误: 未找到 cv2 库"
    echo "请先安装: pip install opencv-python-headless"
    exit 1
fi

echo ""
echo "ℹ️  音频功能说明:"
echo "   - B 端只转发音频，不需要 sounddevice/opuslib"
echo "   - 音频解码在 A 端进行"
echo ""
echo "🚀 启动服务器（音频版）..."
echo ""

# 启动 B_reverse_whole_voice.py（带参数）
python3 B_reverse_whole_voice.py \
    --repo-id "real_robot_online_data_with_audio" \
    --instruction "Real robot teleoperation with audio feedback" \
    --fps 30 \
    --data-root "./real_robot_data" \
    --action-dim 13 \
    --state-dim 13 \
    --image-height 480 \
    --image-width 640
EOFSTART

chmod +x start_b_voice.sh

echo "✅ 音频版启动脚本已创建: start_b_voice.sh"

# 创建停止脚本
cat > stop_b_voice.sh << 'EOF'
#!/bin/bash
# 停止 B_reverse_whole_voice.py

echo "正在停止 B_reverse_whole_voice.py..."
pkill -f "B_reverse_whole_voice.py"
echo "✅ 已发送停止信号"
EOF

chmod +x stop_b_voice.sh

echo "✅ 停止脚本已创建: stop_b_voice.sh"

# 创建查看日志脚本（通用）
if [ ! -f view_logs.sh ]; then
    cat > view_logs.sh << 'EOF'
#!/bin/bash
# 查看服务器日志

echo "最近的日志 (按 Ctrl+C 退出):"
echo "========================================"
tail -f nohup.out 2>/dev/null || echo "⚠️  没有找到日志文件 nohup.out"
EOF
    chmod +x view_logs.sh
    echo "✅ 查看日志脚本已创建: view_logs.sh"
fi

# 创建后台运行脚本
cat > start_b_voice_background.sh << 'EOF'
#!/bin/bash
# 在后台启动 B_reverse_whole_voice.py

cd "$(dirname "$0")"

echo "在后台启动 B_reverse_whole_voice.py (音频版)..."
nohup ./start_b_voice.sh > nohup.out 2>&1 &

PID=$!
echo "✅ 服务器已在后台启动，PID: $PID"
echo "   查看日志: ./view_logs.sh"
echo "   停止服务: ./stop_b_voice.sh"
EOF

chmod +x start_b_voice_background.sh

echo "✅ 后台运行脚本已创建: start_b_voice_background.sh"

# 创建版本对比说明文件
cat > VERSION_INFO.txt << 'EOF'
B 端版本说明
============

1. B_reverse_whole.py (原版)
   - 功能: 视频转发 + LeRobot数据保存
   - 启动: ./start_b_whole.sh
   - 停止: ./stop_b_whole.sh

2. B_reverse_whole_voice.py (音频版)
   - 功能: 视频 + 音频转发 + LeRobot数据保存
   - 启动: ./start_b_voice.sh
   - 停止: ./stop_b_voice.sh
   - 说明: B 端只转发音频，不需要额外依赖

配套使用:
---------
原版系统:
  A端: triple_imu_rs485_publisher_dual_cam_UI.py
  B端: B_reverse_whole.py
  C端: C_real_video_reverse_ultra.py

音频系统:
  A端: triple_imu_rs485_publisher_dual_cam_UI_voice.py --enable-audio
  B端: B_reverse_whole_voice.py
  C端: C_real_video_audio.py

注意事项:
---------
1. B 端可以同时存在两个版本，按需启动
2. 确保同一时间只运行一个版本
3. 音频系统需要 A 端和 C 端也升级
EOF

echo "✅ 版本说明文件已创建: VERSION_INFO.txt"

ENDSSH

if [ $? -eq 0 ]; then
    echo "✅ 目标服务器上的启动脚本创建成功"
else
    echo "❌ 启动脚本创建失败"
    exit 1
fi

# 7. 完成
echo ""
echo "========================================"
echo "✅ 音频版本部署完成！"
echo "========================================"
echo ""
echo "📦 已部署文件:"
echo "   - B_reverse_whole_voice.py (主程序)"
echo "   - start_b_voice.sh (启动脚本)"
echo "   - stop_b_voice.sh (停止脚本)"
echo "   - start_b_voice_background.sh (后台运行)"
echo "   - VERSION_INFO.txt (版本说明)"
echo ""
echo "接下来的步骤："
echo ""
echo "1. 登录到目标服务器（通过跳板机）："
echo "   ./connect.sh"
echo ""
echo "2. 进入工作目录："
echo "   cd $REMOTE_DIR"
echo ""
echo "3. 查看版本说明："
echo "   cat VERSION_INFO.txt"
echo ""
echo "4. 启动音频版服务器（前台运行）："
echo "   ./start_b_voice.sh"
echo ""
echo "   或者在后台运行："
echo "   ./start_b_voice_background.sh"
echo ""
echo "5. 停止服务器："
echo "   ./stop_b_voice.sh"
echo ""
echo "========================================"
echo ""
echo "🎯 完整音频系统启动顺序："
echo ""
echo "第1步: 启动 B 端（服务器）"
echo "   ./connect.sh"
echo "   cd $REMOTE_DIR"
echo "   ./start_b_voice.sh"
echo ""
echo "第2步: 启动 C 端（本地，采集音频）"
echo "   cd ~/桌面/WIT_RS485/whole3_2"
echo "   python C_real_video_audio.py"
echo ""
echo "第3步: 启动 A 端（本地，播放音频）"
echo "   cd ~/桌面/WIT_RS485"
echo "   python triple_imu_rs485_publisher_dual_cam_UI_voice.py \\"
echo "       --online-only -p /dev/ttyUSB1 \\"
echo "       --enable-video --enable-audio \\"
echo "       --enable-debug --debug-port 5560"
echo ""
echo "========================================"
echo ""
echo "⚠️  重要提示："
echo "1. B 端不需要音频库，只负责转发"
echo "2. C 端需要安装: pip install sounddevice opuslib"
echo "3. A 端需要安装: pip install sounddevice opuslib"
echo "4. 使用 SSH 隧道连接时，音频走 5557 端口（与视频共用）"
echo ""
echo "🔧 SSH 隧道命令（记得端口转发）:"
echo "   ssh -i $JUMPHOST_SSH_KEY -p $JUMPHOST_PORT \\"
echo "       -o \"ProxyCommand ssh -i $TARGET_SSH_KEY -p $TARGET_PORT -W %h:%p $JUMPHOST_USER@$JUMPHOST\" \\"
echo "       -L 5555:localhost:5555 -L 5556:localhost:5556 \\"
echo "       -L 5557:localhost:5557 -L 5558:localhost:5558 \\"
echo "       $TARGET_USER@$TARGET_HOST"
echo ""
