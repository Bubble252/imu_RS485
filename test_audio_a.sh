#!/bin/bash
# test_audio_a.sh - 测试 A 端音频功能

echo "=========================================="
echo "A 端音频功能测试脚本"
echo "=========================================="
echo ""

# 检查依赖
echo "1. 检查音频依赖库..."
python3 -c "import sounddevice" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ sounddevice 已安装"
else
    echo "❌ sounddevice 未安装"
    echo "   安装方法: pip install sounddevice"
    exit 1
fi

python3 -c "import opuslib" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ opuslib 已安装"
else
    echo "❌ opuslib 未安装"
    echo "   安装方法: pip install opuslib"
    exit 1
fi

echo ""

# 列出音频设备
echo "2. 可用音频输出设备:"
python3 -c "import sounddevice as sd; devices = sd.query_devices(); \
    [print(f'   [{i}] {dev[\"name\"]}') for i, dev in enumerate(devices) if dev['max_output_channels'] > 0]"

echo ""

# 测试音频播放
echo "3. 测试音频播放（3秒蜂鸣音）..."
python3 << EOF
import sounddevice as sd
import numpy as np
import time

print("   生成测试音频...")
try:
    # 生成 440Hz 正弦波（3秒）
    sample_rate = 16000
    duration = 3
    frequency = 440  # A4 音符
    
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = (np.sin(2 * np.pi * frequency * t) * 8000).astype('int16')
    
    print("   开始播放...")
    sd.play(audio, samplerate=sample_rate)
    sd.wait()
    print("   ✅ 播放成功")
except Exception as e:
    print(f"   ❌ 播放失败: {e}")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ 所有测试通过！可以运行 A 端程序"
    echo "=========================================="
    echo ""
    echo "启动命令:"
    echo "python triple_imu_rs485_publisher_dual_cam_UI_voice.py \\"
    echo "    --online-only -p /dev/ttyUSB1 \\"
    echo "    --enable-video --video-host localhost --video-port 5557 \\"
    echo "    --enable-audio \\"
    echo "    --enable-debug --debug-port 5560"
else
    echo ""
    echo "=========================================="
    echo "❌ 测试失败，请检查音频设备"
    echo "=========================================="
    exit 1
fi
