#!/bin/bash
# test_audio_c.sh - 测试 C 端音频功能

echo "=========================================="
echo "音频功能测试脚本"
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

python3 -c "import cv2" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ opencv-python 已安装"
else
    echo "❌ opencv-python 未安装"
    echo "   安装方法: pip install opencv-python"
    exit 1
fi

echo ""

# 列出音频设备
echo "2. 可用音频设备:"
python3 -c "import sounddevice as sd; devices = sd.query_devices(); \
    [print(f'   [{i}] {dev[\"name\"]}') for i, dev in enumerate(devices) if dev['max_input_channels'] > 0]"

echo ""

# 测试音频录制
echo "3. 测试音频录制（3秒）..."
python3 << EOF
import sounddevice as sd
import numpy as np
import time

print("   开始录音...")
try:
    recording = sd.rec(int(3 * 16000), samplerate=16000, channels=1, dtype='int16')
    sd.wait()
    print("   ✅ 录音成功")
    print(f"   数据形状: {recording.shape}")
    print(f"   数据类型: {recording.dtype}")
except Exception as e:
    print(f"   ❌ 录音失败: {e}")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ 所有测试通过！可以运行 C_real_video_audio.py"
    echo "=========================================="
else
    echo ""
    echo "=========================================="
    echo "❌ 测试失败，请检查音频设备"
    echo "=========================================="
    exit 1
fi
