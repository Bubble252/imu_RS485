#!/bin/bash
# install_audio_deps.sh - 安装音频功能所需的依赖

echo "=========================================="
echo "音频功能依赖安装脚本"
echo "=========================================="
echo ""

# 检查是否在虚拟环境中
if [ -z "$VIRTUAL_ENV" ] && [ -z "$CONDA_DEFAULT_ENV" ]; then
    echo "⚠️  警告: 您不在虚拟环境中"
    echo "   建议先激活虚拟环境: source .venv/bin/activate"
    echo "   或使用 conda: conda activate your_env"
    echo ""
    read -p "是否继续全局安装？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "1. 安装系统依赖（需要 sudo）..."
sudo apt-get update
sudo apt-get install -y libopus0 libopus-dev portaudio19-dev python3-dev

if [ $? -ne 0 ]; then
    echo "❌ 系统依赖安装失败"
    exit 1
fi

echo ""
echo "2. 安装 Python 库..."

pip install sounddevice
if [ $? -ne 0 ]; then
    echo "❌ sounddevice 安装失败"
    exit 1
fi

pip install opuslib
if [ $? -ne 0 ]; then
    echo "❌ opuslib 安装失败"
    exit 1
fi

echo ""
echo "3. 验证安装..."

python3 -c "import sounddevice; print('✅ sounddevice 版本:', sounddevice.__version__)"
if [ $? -ne 0 ]; then
    echo "❌ sounddevice 验证失败"
    exit 1
fi

python3 -c "import opuslib; print('✅ opuslib 已安装')"
if [ $? -ne 0 ]; then
    echo "❌ opuslib 验证失败"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ 所有依赖安装成功！"
echo "=========================================="
echo ""
echo "下一步:"
echo "  1. 运行测试: ./test_audio_c.sh"
echo "  2. 启动 C 端: python C_real_video_audio.py"
