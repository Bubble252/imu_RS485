#!/bin/bash
# 检查 B 端状态

echo "=========================================="
echo "检查 B 端状态（目标服务器）"
echo "=========================================="
echo ""

ssh -i ./capri_yhx_2237 -p 2237 \
    -o "ProxyCommand ssh -i ./leo_tmp_2258.txt -p 2258 -W %h:%p root@202.112.113.78" \
    root@202.112.113.74 << 'ENDSSH'

echo "1️⃣ B 端进程状态："
echo "----------------------------------------"
if ps aux | grep -v grep | grep "B_reverse_whole.py" > /dev/null; then
    echo "✅ B 端正在运行"
    ps aux | grep -v grep | grep "B_reverse_whole.py"
else
    echo "❌ B 端未运行！"
    echo ""
    echo "请执行："
    echo "  conda activate lerobot_server"
    echo "  cd /data7/yhx/lerobot_data_collection"
    echo "  ./start_b_whole.sh"
fi

echo ""
echo "2️⃣ 端口监听状态："
echo "----------------------------------------"
echo "期望：应该看到 5555, 5556, 5557, 5558 四个端口"
if ss -tuln | grep -E "5555|5556|5557|5558" > /dev/null; then
    echo "✅ 端口正在监听："
    ss -tuln | grep -E "5555|5556|5557|5558"
else
    echo "❌ 没有发现端口监听！B 端可能未启动或崩溃"
fi

echo ""
echo "3️⃣ B 端最新日志（最后 30 行）："
echo "----------------------------------------"
if [ -f /data7/yhx/lerobot_data_collection/nohup.out ]; then
    tail -30 /data7/yhx/lerobot_data_collection/nohup.out
else
    echo "❌ 日志文件不存在"
fi

echo ""
echo "4️⃣ 错误日志（如果有）："
echo "----------------------------------------"
if [ -f /data7/yhx/lerobot_data_collection/nohup.out ]; then
    grep -i "error\|traceback\|exception" /data7/yhx/lerobot_data_collection/nohup.out | tail -20
    if [ $? -ne 0 ]; then
        echo "✅ 没有发现错误"
    fi
else
    echo "❌ 日志文件不存在"
fi

ENDSSH

echo ""
echo "=========================================="
echo "检查完成"
echo "=========================================="
