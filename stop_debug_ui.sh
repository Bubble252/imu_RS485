#!/bin/bash
# 停止所有调试UI服务

echo "🛑 停止IMU调试UI系统..."

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0;29m'

# 停止服务的函数
stop_service() {
    local service_name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if ps -p $PID > /dev/null 2>&1; then
            echo "   停止 $service_name (PID: $PID)..."
            kill $PID 2>/dev/null
            sleep 1
            
            # 强制杀死
            if ps -p $PID > /dev/null 2>&1; then
                kill -9 $PID 2>/dev/null
            fi
            
            echo -e "${GREEN}✓ $service_name 已停止${NC}"
        else
            echo -e "${YELLOW}⚠️  $service_name 未运行${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}⚠️  $service_name PID文件不存在${NC}"
    fi
}

# 停止所有服务
stop_service "前端UI" ".pids/frontend.pid"
stop_service "后端服务" ".pids/backend.pid"
stop_service "主程序" ".pids/main.pid"

# 清理残留进程（备用）
echo ""
echo "清理可能的残留进程..."
pkill -f "debug_server.py" 2>/dev/null && echo "   清理 debug_server.py"
pkill -f "react-scripts start" 2>/dev/null && echo "   清理 react-scripts"
pkill -f "triple_imu_rs485_publisher.py.*--enable-debug" 2>/dev/null && echo "   清理 triple程序"

echo ""
echo -e "${GREEN}✅ 所有服务已停止${NC}"
