#!/bin/bash
# IMU双摄像头可视化查看器 - 启动脚本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  IMU双摄像头可视化查看器${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查并激活conda环境
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
    
    # 检查pyqt5_ui环境是否存在
    if conda env list | grep -q "^pyqt5_ui "; then
        echo -e "${GREEN}✓ 检测到pyqt5_ui环境，正在激活...${NC}"
        conda activate pyqt5_ui
        echo -e "${GREEN}✓ 已激活pyqt5_ui环境${NC}"
    else
        echo -e "${YELLOW}⚠️  未找到pyqt5_ui环境，使用当前环境${NC}"
    fi
fi

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3未安装${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python3: $(python3 --version)${NC}"

# 检查依赖
echo -e "\n${YELLOW}检查依赖...${NC}"

MISSING_DEPS=()

python3 -c "import PyQt5" 2>/dev/null || MISSING_DEPS+=("PyQt5")
python3 -c "import pyqtgraph" 2>/dev/null || MISSING_DEPS+=("pyqtgraph")
python3 -c "import OpenGL" 2>/dev/null || MISSING_DEPS+=("PyOpenGL")
python3 -c "import zmq" 2>/dev/null || MISSING_DEPS+=("pyzmq")
python3 -c "import cv2" 2>/dev/null || MISSING_DEPS+=("opencv-python")
python3 -c "import numpy" 2>/dev/null || MISSING_DEPS+=("numpy")

if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    echo -e "${YELLOW}⚠️  缺少以下依赖:${NC}"
    for dep in "${MISSING_DEPS[@]}"; do
        echo "  - $dep"
    done
    echo ""
    echo -e "${YELLOW}是否自动安装? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo -e "${GREEN}正在安装依赖...${NC}"
        pip3 install PyQt5 pyqtgraph PyOpenGL pyzmq opencv-python numpy
    else
        echo -e "${RED}请手动安装依赖后再运行${NC}"
        echo "pip3 install PyQt5 pyqtgraph PyOpenGL pyzmq opencv-python numpy"
        exit 1
    fi
else
    echo -e "${GREEN}✓ 所有依赖已安装${NC}"
fi

# 解析参数
ZMQ_HOST="localhost"
ZMQ_PORT="5560"

while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            ZMQ_HOST="$2"
            shift 2
            ;;
        --port)
            ZMQ_PORT="$2"
            shift 2
            ;;
        -h|--help)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --host <地址>    ZMQ服务器地址 (默认: localhost)"
            echo "  --port <端口>    ZMQ订阅端口 (默认: 5560)"
            echo "  -h, --help      显示此帮助信息"
            echo ""
            echo "示例:"
            echo "  $0                      # 连接到本地5560端口"
            echo "  $0 --host 192.168.1.100 --port 5560"
            exit 0
            ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            echo "使用 -h 或 --help 查看帮助"
            exit 1
            ;;
    esac
done

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 启动PyQt5 UI
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}启动参数:${NC}"
echo -e "  ZMQ地址: ${YELLOW}tcp://${ZMQ_HOST}:${ZMQ_PORT}${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

cd "$SCRIPT_DIR"

python3 imu_dual_cam_viewer.py --host "$ZMQ_HOST" --port "$ZMQ_PORT"

echo ""
echo -e "${GREEN}✓ UI已退出${NC}"
