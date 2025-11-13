# 🚀 快速开始指南

## 第一次使用？跟着这个走！

### 1️⃣ 安装依赖（只需一次）

```bash
cd /home/bubble/桌面/WIT_RS485

# 安装Python后端依赖
pip install -r requirements_debug_server.txt

# 安装Node.js前端依赖（可能需要5-10分钟）
cd imu-dashboard
npm install
cd ..
```

### 2️⃣ 启动系统

```bash
# 一键启动
./start_debug_ui.sh
```

按提示选择：
- **首次运行**：选择 `y` 安装依赖
- **启动模式**：选择 `1` 完整模式

### 3️⃣ 访问UI

打开浏览器访问：**http://localhost:3000**

你会看到：
- 🌐 3D轨迹可视化（左上）
- 📊 IMU状态仪表盘（右上）
- 📈 噪声分析（左下）
- ⚙️ 控制面板（右下）

### 4️⃣ 停止系统

```bash
./stop_debug_ui.sh
```

---

## 🎯 测试数据流（不连接真实硬件）

如果只想测试UI，不想连接IMU硬件：

```bash
# 1. 仅启动后端+前端
./start_debug_ui.sh
# 选择模式 2

# 2. 手动发送测试数据（另开终端）
python -c "
import zmq
import json
import time

context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind('tcp://*:5560')
time.sleep(1)

for i in range(100):
    data = {
        'timestamp': time.time(),
        'imu1': {'roll': i, 'pitch': -i, 'yaw': i/2},
        'imu2': {'roll': i*1.5, 'pitch': -i*1.5, 'yaw': i/3},
        'imu3': {'roll': i*0.5, 'pitch': -i*0.5, 'yaw': i/4},
        'position': {
            'raw': [0.4, 0.1, 0.2],
            'mapped': [0.3, 0.05, 0.25]
        },
        'gripper': (i % 100) / 100,
        'online_status': {'imu1': True, 'imu2': True, 'imu3': True}
    }
    socket.send_json(data)
    time.sleep(0.05)
"
```

---

## 🔧 常见问题

### Q: 浏览器显示"未连接"？
A: 等待几秒钟让服务启动完成，或检查后端日志：
```bash
tail -f logs/backend.log
```

### Q: 3D轨迹是黑色的？
A: 主程序可能没启动，或者没有添加 `--enable-debug` 参数

### Q: npm install 太慢？
A: 使用淘宝镜像：
```bash
npm config set registry https://registry.npmmirror.com
npm install
```

---

## 📚 完整文档

详细说明请查看：**DEBUG_UI_README.md**
