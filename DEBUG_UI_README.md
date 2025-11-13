# IMU机械臂调试UI系统 - 使用文档

## 🎯 系统概述

这是一个**前后端分离**的现代化Web监控系统，用于IMU机械臂的实时调试和数据可视化。

### 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                 前端UI（React + Three.js）                        │
│  - 3D轨迹实时显示                                                  │
│  - IMU状态仪表盘                                                  │
│  - 噪声分析图表                                                    │
│  - 交互控制面板                                                    │
│                                                                   │
│  访问地址: http://localhost:3000                                  │
└────────────────────┬──────────────────────────────────────────────┘
                     │ WebSocket (实时双向通信)
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│             后端服务（FastAPI + WebSocket）                       │
│  - ZeroMQ订阅主程序数据流                                          │
│  - 数据处理：轨迹缓冲、噪声分析、统计计算                              │
│  - WebSocket广播给所有前端客户端                                    │
│                                                                   │
│  API地址: http://localhost:8000                                   │
│  WebSocket: ws://localhost:8000/ws                                │
└────────────────────┬──────────────────────────────────────────────┘
                     │ ZeroMQ SUB (订阅调试数据)
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│         主程序（triple_imu_rs485_publisher.py）                   │
│  - IMU数据采集（RS485）                                            │
│  - 运动学计算                                                      │
│  - ZeroMQ发布到B端和LeRobot（主要功能）                             │
│  + 新增：ZeroMQ PUB socket（端口5560）发布调试数据                  │
│                                                                   │
│  运行命令: python triple_imu_rs485_publisher.py --online-only --enable-debug
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 安装依赖

### 1. 后端依赖（Python）

```bash
cd /home/bubble/桌面/WIT_RS485
pip install -r requirements_debug_server.txt
```

**依赖包列表：**
- `fastapi` - Web框架
- `uvicorn` - ASGI服务器
- `websockets` - WebSocket支持
- `pyzmq` - ZeroMQ异步支持
- `numpy` - 数据处理

### 2. 前端依赖（Node.js）

**首次安装：**

```bash
cd imu-dashboard
npm install
```

这将安装以下包：
- `react` + `react-dom` - UI框架
- `@react-three/fiber` + `@react-three/drei` - 3D渲染
- `three` - Three.js核心
- `antd` - UI组件库
- `chart.js` + `react-chartjs-2` - 图表库
- `typescript` - 类型支持

---

## 🚀 快速启动

### 方式1：一键启动（推荐）

```bash
./start_debug_ui.sh
```

启动脚本会引导您：
1. 选择是否安装/更新依赖
2. 选择启动模式：
   - **完整模式**：主程序 + 后端 + 前端
   - **调试UI模式**：仅后端 + 前端（测试UI）
   - **无前端模式**：主程序 + 后端（无界面）

### 方式2：手动启动

#### 步骤1：启动主程序（可选，如果只测试UI可跳过）

```bash
python triple_imu_rs485_publisher.py --online-only --enable-debug
```

**重要参数：**
- `--online-only` - 仅在三个IMU都在线时发布
- `--enable-debug` - 启用调试数据发布（给UI后端）
- `--debug-port 5560` - 调试数据端口（默认5560）

#### 步骤2：启动后端服务

```bash
python debug_server.py
```

**输出示例：**
```
======================================================================
🚀 IMU调试数据后端服务启动
======================================================================
WebSocket端点: ws://localhost:8000/ws
API文档: http://localhost:8000/docs
======================================================================
```

#### 步骤3：启动前端UI

```bash
cd imu-dashboard
npm start
```

浏览器会自动打开 `http://localhost:3000`

---

## 🛑 停止服务

```bash
./stop_debug_ui.sh
```

或者手动按 `Ctrl+C` 停止各个进程。

---

## 🖥️ UI功能说明

### 1. 3D轨迹可视化（左上）

- **实时轨迹渲染**：最近1000个位置点
- **起点标记**：绿色球体
- **当前位置**：红色球体（实时跟踪）
- **坐标轴**：
  - 红色 = X轴
  - 绿色 = Y轴
  - 蓝色 = Z轴
- **交互操作**：
  - 鼠标拖拽 = 旋转视角
  - 滚轮 = 缩放
  - 右键拖拽 = 平移

### 2. IMU状态仪表盘（右上）

- **三个IMU卡片**：
  - IMU 1（杆1）
  - IMU 2（杆2）
  - IMU 3（机械爪）
- **实时数据**：
  - Roll、Pitch、Yaw欧拉角（度）
  - 在线/离线状态指示
- **夹爪开合度**：
  - 进度条显示（0-100%）
  - 颜色渐变（红→绿）
- **运动速度**：
  - 速度大小（m/s）
  - Vx、Vy、Vz分量

### 3. 噪声分析（左下）

- **三个IMU的噪声统计**：
  - Roll、Pitch、Yaw的标准差（σ）
- **噪声等级评估**：
  - 优秀（绿色）：σ < 0.5°
  - 良好（蓝色）：0.5° ≤ σ < 1.5°
  - 一般（橙色）：1.5° ≤ σ < 3.0°
  - 较差（红色）：σ ≥ 3.0°

### 4. 控制面板（右下）

- **系统配置显示**：
  - L1、L2杆长（mm）
  - Yaw归零模式
- **控制按钮**：
  - **重置轨迹**：清空历史轨迹数据
  - **导出数据**：（未来功能）导出为CSV/JSON

---

## 📊 数据流详解

### 主程序 → 后端（ZeroMQ PUB/SUB）

**端口：** 5560  
**频率：** 20Hz  
**格式：** JSON

```json
{
  "timestamp": 1234567890.123,
  "imu1": {"roll": 10.5, "pitch": -5.2, "yaw": 0.3},
  "imu2": {"roll": 15.2, "pitch": -10.1, "yaw": 1.5},
  "imu3": {"roll": 5.1, "pitch": 2.3, "yaw": -0.8},
  "position": {
    "raw": [0.45, 0.12, 0.25],
    "mapped": [0.32, 0.05, 0.28]
  },
  "gripper": 0.75,
  "online_status": {
    "imu1": true,
    "imu2": true,
    "imu3": true
  },
  "stats": {
    "publish_count": 1500,
    "publish_rate": 19.8
  },
  "config": {
    "L1": 0.25,
    "L2": 0.27,
    "yaw_mode": "NORMAL"
  }
}
```

### 后端 → 前端（WebSocket）

**端口：** 8000  
**协议：** ws://localhost:8000/ws  
**格式：** JSON（增强数据）

**增强内容：**
- `trajectory`: 最近50个轨迹点
- `noise_analysis`: 噪声统计（标准差、均值、最大/最小值）
- `velocity`: 速度计算（Vx、Vy、Vz、magnitude）
- `stats`: 统计信息（total_messages、current_rate、uptime）

---

## 🔧 配置和定制

### 修改发布频率

编辑 `triple_imu_rs485_publisher.py`：

```python
# 第390行左右（debug_publisher_thread函数内）
time.sleep(0.05)  # 20Hz，修改此值调整频率
```

### 修改轨迹缓冲区大小

编辑 `debug_server.py`：

```python
# 第52行
data_manager = DataManager(
    max_trajectory_points=1000,  # 轨迹点数
    max_noise_samples=100        # 噪声样本数
)
```

### 修改UI主题颜色

编辑 `imu-dashboard/src/App.css` 和各组件文件中的颜色值。

---

## 📝 API端点

后端服务提供以下RESTful API（访问 http://localhost:8000/docs 查看完整文档）：

### GET /
服务信息和状态

### GET /api/health
健康检查

**响应：**
```json
{
  "status": "healthy",
  "connections": 2,
  "total_messages": 5000,
  "uptime": 123.5
}
```

### GET /api/stats
统计信息

### GET /api/latest
获取最新数据（HTTP轮询备用方案）

### WebSocket /ws
实时数据推送

**客户端可发送控制命令：**
```json
{
  "command": "reset_trajectory"  // 重置轨迹
}
```

---

## 🐛 故障排查

### 问题1：前端无法连接后端

**症状：** 浏览器显示"未连接"

**解决：**
1. 检查后端是否运行：`curl http://localhost:8000/api/health`
2. 查看后端日志：`tail -f logs/backend.log`
3. 确认防火墙未阻止8000端口

### 问题2：3D轨迹不显示

**症状：** 黑屏或空白

**解决：**
1. 检查主程序是否启用 `--enable-debug`
2. 打开浏览器控制台（F12）查看错误
3. 确认WebSocket已连接

### 问题3：npm安装失败

**症状：** `npm install` 报错

**解决：**
```bash
# 清理缓存
rm -rf node_modules package-lock.json
npm cache clean --force
npm install
```

### 问题4：端口被占用

**症状：** "Address already in use"

**解决：**
```bash
# 查找占用进程
lsof -i :8000  # 后端端口
lsof -i :3000  # 前端端口
lsof -i :5560  # 调试数据端口

# 杀死进程
kill -9 <PID>
```

---

## 📈 性能优化建议

### 1. 减少数据传输量

如果网络带宽有限，可以：
- 降低主程序的调试数据发布频率（修改`time.sleep(0.05)`为更大值）
- 减少轨迹缓冲区大小
- 压缩WebSocket消息（需修改后端代码）

### 2. 提高UI响应速度

- 使用生产构建：`npm run build`
- 部署到Nginx等静态服务器
- 启用浏览器缓存

### 3. 数据库持久化（高级）

当前系统数据仅保存在内存中，如需持久化：
- 修改 `debug_server.py`，添加SQLite/PostgreSQL支持
- 实现数据导出API
- 添加历史数据回放功能

---

## 🔮 未来功能规划

- [ ] 数据录制和回放
- [ ] 导出为CSV/JSON/HDF5格式
- [ ] 实时参数调节（L1、L2、坐标映射范围）
- [ ] 多设备支持（同时监控多个机械臂）
- [ ] 移动端适配（响应式布局）
- [ ] AI异常检测（自动识别抖动、漂移）

---

## 📞 技术支持

**问题反馈：** 查看logs/目录下的日志文件  
**修改建议：** 所有代码均有详细注释，欢迎定制

**日志文件位置：**
- 主程序：`logs/main_program.log`
- 后端：`logs/backend.log`
- 前端：`logs/frontend.log`

---

## 📄 许可证

本系统为内部调试工具，仅供学习和研发使用。
