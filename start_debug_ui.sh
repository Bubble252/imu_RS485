#!/bin/bash
# IMU调试UI系统 - 一键启动脚本
# 启动主程序、后端服务、前端UI

set -e  # 遇到错误立即退出

echo "======================================================================"
echo "🚀 IMU机械臂调试UI系统 - 启动脚本"
echo "======================================================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查依赖
check_dependencies() {
    echo "📦 检查依赖..."
    
    # 检查Python
    if ! command -v python &> /dev/null; then
        echo -e "${RED}❌ Python未安装${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Python已安装: $(python --version)${NC}"
    
    # 检查Node.js
    if ! command -v node &> /dev/null; then
        echo -e "${YELLOW}⚠️  Node.js未安装，前端UI将无法启动${NC}"
        echo "   安装方法: sudo apt install nodejs npm"
        return 1
    fi
    echo -e "${GREEN}✓ Node.js已安装: $(node --version)${NC}"
    
    return 0
}

# 安装后端依赖
install_backend_deps() {
    echo ""
    echo "📦 安装后端依赖..."
    
    if [ ! -f "requirements_debug_server.txt" ]; then
        echo -e "${RED}❌ requirements_debug_server.txt不存在${NC}"
        exit 1
    fi
    
    pip install -r requirements_debug_server.txt
    echo -e "${GREEN}✓ 后端依赖安装完成${NC}"
}

# 安装前端依赖
install_frontend_deps() {
    echo ""
    echo "📦 安装前端依赖..."
    
    if [ ! -d "imu-dashboard" ]; then
        echo -e "${RED}❌ imu-dashboard目录不存在${NC}"
        exit 1
    fi
    
    cd imu-dashboard
    
    if [ ! -d "node_modules" ]; then
        echo "   首次运行，正在安装npm包（可能需要几分钟）..."
        npm install
    else
        echo "   node_modules已存在，跳过安装"
    fi
    
    cd ..
    echo -e "${GREEN}✓ 前端依赖安装完成${NC}"
}

# 启动主程序
start_main_program() {
    echo ""
    echo "1️⃣  启动主程序（triple_imu_rs485_publisher.py）..."
    
    # 使用nohup后台运行，输出到日志文件
    nohup python triple_imu_rs485_publisher.py --online-only --enable-debug > logs/main_program.log 2>&1 &
    MAIN_PID=$!
    
    echo -e "${GREEN}✓ 主程序已启动 (PID: $MAIN_PID)${NC}"
    echo "   日志文件: logs/main_program.log"
    echo $MAIN_PID > .pids/main.pid
    
    sleep 2
}

# 启动后端服务
start_backend() {
    echo ""
    echo "2️⃣  启动后端服务（debug_server.py）..."
    
    nohup python debug_server.py > logs/backend.log 2>&1 &
    BACKEND_PID=$!
    
    echo -e "${GREEN}✓ 后端服务已启动 (PID: $BACKEND_PID)${NC}"
    echo "   WebSocket: ws://localhost:8000/ws"
    echo "   API文档: http://localhost:8000/docs"
    echo "   日志文件: logs/backend.log"
    echo $BACKEND_PID > .pids/backend.pid
    
    sleep 2
}

# 启动前端UI
start_frontend() {
    echo ""
    echo "3️⃣  启动前端UI（React开发服务器）..."
    
    cd imu-dashboard
    nohup npm start > ../logs/frontend.log 2>&1 &
    FRONTEND_PID=$!
    cd ..
    
    echo -e "${GREEN}✓ 前端UI已启动 (PID: $FRONTEND_PID)${NC}"
    echo "   访问地址: http://localhost:3000"
    echo "   日志文件: logs/frontend.log"
    echo $FRONTEND_PID > .pids/frontend.pid
    
    sleep 3
}

# 显示状态
show_status() {
    echo ""
    echo "======================================================================"
    echo "✅ 所有服务已启动"
    echo "======================================================================"
    echo ""
    echo "📊 访问地址:"
    echo "   🌐 前端UI:    http://localhost:3000"
    echo "   🔧 后端API:   http://localhost:8000/docs"
    echo "   📡 WebSocket: ws://localhost:8000/ws"
    echo ""
    echo "📁 日志文件:"
    echo "   主程序: logs/main_program.log"
    echo "   后端:   logs/backend.log"
    echo "   前端:   logs/frontend.log"
    echo ""
    echo "📝 PID文件:"
    echo "   主程序: .pids/main.pid"
    echo "   后端:   .pids/backend.pid"
    echo "   前端:   .pids/frontend.pid"
    echo ""
    echo "⏹️  停止服务: ./stop_debug_ui.sh"
    echo "📊 查看日志: tail -f logs/*.log"
    echo ""
    echo "======================================================================"
}

# 主流程
main() {
    # 创建必要的目录
    mkdir -p logs
    mkdir -p .pids
    
    # 检查依赖
    if ! check_dependencies; then
        echo ""
        echo -e "${YELLOW}部分依赖缺失，但将继续尝试启动...${NC}"
    fi
    
    # 询问是否安装依赖
    echo ""
    read -p "是否安装/更新依赖包? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        install_backend_deps
        if command -v node &> /dev/null; then
            install_frontend_deps
        fi
    fi
    
    # 询问启动模式
    echo ""
    echo "请选择启动模式:"
    echo "  1) 完整模式（主程序 + 后端 + 前端）"
    echo "  2) 仅后端+前端（调试UI）"
    echo "  3) 仅主程序+后端（无前端）"
    read -p "请选择 (1-3): " -n 1 -r MODE
    echo ""
    
    case $MODE in
        1)
            start_main_program
            start_backend
            start_frontend
            ;;
        2)
            start_backend
            start_frontend
            ;;
        3)
            start_main_program
            start_backend
            ;;
        *)
            echo -e "${RED}无效选择，退出${NC}"
            exit 1
            ;;
    esac
    
    show_status
    
    # 询问是否打开浏览器
    if command -v xdg-open &> /dev/null && [ "$MODE" != "3" ]; then
        read -p "是否打开浏览器? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sleep 2
            xdg-open http://localhost:3000 &
        fi
    fi
}

# 陷阱处理（Ctrl+C）
trap 'echo -e "\n${YELLOW}⚠️  请使用 ./stop_debug_ui.sh 停止服务${NC}"; exit 0' INT

main "$@"
