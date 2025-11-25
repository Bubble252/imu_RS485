#!/bin/bash

# PyQt5 UI 集成启动脚本
# 用法：
#   ./start_ui_system.sh        - 启动主程序和UI（默认参数）
#   ./start_ui_system.sh main   - 只启动主程序
#   ./start_ui_system.sh ui     - 只启动UI

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 工作目录
WORK_DIR="/home/bubble/桌面/WIT_RS485"
cd "$WORK_DIR"

# 默认参数
SERIAL_PORT="${SERIAL_PORT:-/dev/ttyUSB0}"
B_HOST="${B_HOST:-192.168.1.100}"
B_PORT="${B_PORT:-5555}"
DEBUG_PORT="${DEBUG_PORT:-5560}"
CMD_PORT="${CMD_PORT:-5562}"

# 帮助信息
show_help() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  PyQt5 UI 集成系统启动脚本${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "用法："
    echo "  $0 [选项]"
    echo ""
    echo "选项："
    echo "  all      - 启动主程序和UI（默认）"
    echo "  main     - 只启动主程序"
    echo "  ui       - 只启动UI"
    echo "  help     - 显示此帮助"
    echo ""
    echo "环境变量："
    echo "  SERIAL_PORT  - 串口设备（默认：/dev/ttyUSB0）"
    echo "  B_HOST       - B端地址（默认：192.168.1.100）"
    echo "  B_PORT       - B端端口（默认：5555）"
    echo "  DEBUG_PORT   - 调试数据端口（默认：5560）"
    echo "  CMD_PORT     - 命令接收端口（默认：5562）"
    echo ""
    echo "示例："
    echo "  ./start_ui_system.sh"
    echo "  SERIAL_PORT=/dev/ttyUSB1 ./start_ui_system.sh main"
    echo "  ./start_ui_system.sh ui"
    echo ""
}

# 检查依赖
check_dependencies() {
    echo -e "${YELLOW}检查依赖...${NC}"
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ 未找到 python3${NC}"
        exit 1
    fi
    
    # 检查PyQt5
    if ! python3 -c "import PyQt5" 2>/dev/null; then
        echo -e "${RED}❌ 未安装 PyQt5${NC}"
        echo -e "${YELLOW}请运行: pip install PyQt5${NC}"
        exit 1
    fi
    
    # 检查ZMQ
    if ! python3 -c "import zmq" 2>/dev/null; then
        echo -e "${RED}❌ 未安装 pyzmq${NC}"
        echo -e "${YELLOW}请运行: pip install pyzmq${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ 依赖检查通过${NC}"
}

# 启动主程序
start_main() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}启动主控制程序${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  串口: ${YELLOW}${SERIAL_PORT}${NC}"
    echo -e "  B端: ${YELLOW}${B_HOST}:${B_PORT}${NC}"
    echo -e "  调试端口: ${YELLOW}${DEBUG_PORT}${NC}"
    echo -e "  命令端口: ${YELLOW}${CMD_PORT}${NC}"
    echo ""
    
    python3 triple_imu_rs485_publisher_dual_cam_UI_voice.py \
        --port "$SERIAL_PORT" \
        --b-host "$B_HOST" \
        --b-port "$B_PORT" \
        --enable-debug \
        --debug-port "$DEBUG_PORT" \
        --ui-command-port "$CMD_PORT" \
        --online-only
}

# 启动UI
start_ui() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}启动PyQt5 UI${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  连接: ${YELLOW}localhost:${DEBUG_PORT}${NC}"
    echo ""
    
    cd pyqt5_viewer
    python3 imu_dual_cam_viewer.py --host localhost --port "$DEBUG_PORT"
}

# 启动全部（后台主程序 + 前台UI）
start_all() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}启动完整系统（主程序 + UI）${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    # 检查主程序是否已在运行
    if pgrep -f "triple_imu_rs485_publisher_dual_cam_UI_voice.py" > /dev/null; then
        echo -e "${YELLOW}⚠️  主程序已在运行，跳过启动${NC}"
    else
        echo -e "${YELLOW}后台启动主程序...${NC}"
        nohup python3 triple_imu_rs485_publisher_dual_cam_UI_voice.py \
            --port "$SERIAL_PORT" \
            --b-host "$B_HOST" \
            --b-port "$B_PORT" \
            --enable-debug \
            --debug-port "$DEBUG_PORT" \
            --ui-command-port "$CMD_PORT" \
            --online-only \
            > main_program.log 2>&1 &
        
        MAIN_PID=$!
        echo -e "${GREEN}✓ 主程序已启动 (PID: $MAIN_PID)${NC}"
        echo -e "${YELLOW}  日志: main_program.log${NC}"
        
        # 等待主程序启动
        echo -n "等待主程序初始化"
        for i in {1..5}; do
            sleep 1
            echo -n "."
        done
        echo ""
    fi
    
    # 启动UI（前台）
    echo ""
    echo -e "${GREEN}启动PyQt5 UI（按 Ctrl+C 退出）...${NC}"
    sleep 1
    
    cd pyqt5_viewer
    python3 imu_dual_cam_viewer.py --host localhost --port "$DEBUG_PORT"
}

# 清理函数
cleanup() {
    echo ""
    echo -e "${YELLOW}正在清理...${NC}"
    
    # 终止后台主程序
    if [ ! -z "$MAIN_PID" ]; then
        echo -e "${YELLOW}终止主程序 (PID: $MAIN_PID)${NC}"
        kill $MAIN_PID 2>/dev/null || true
    fi
    
    echo -e "${GREEN}✓ 清理完成${NC}"
}

# 主逻辑
main() {
    # 注册清理函数
    trap cleanup EXIT INT TERM
    
    MODE="${1:-all}"
    
    case "$MODE" in
        help|--help|-h)
            show_help
            exit 0
            ;;
        all)
            check_dependencies
            start_all
            ;;
        main)
            check_dependencies
            start_main
            ;;
        ui)
            check_dependencies
            start_ui
            ;;
        *)
            echo -e "${RED}❌ 未知选项: $MODE${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 运行
main "$@"
