# 快速参考卡 - Triple IMU + ZeroMQ系统

## 📡 端口速查表

| 端口 | 用途 | bind方 | connect方 | 模式 |
|------|------|--------|-----------|------|
| 5555 | A→B传感器数据 | B端 | A端(triple) | PULL/PUSH |
| 5556 | B→C控制命令 | C端 | B端 | PULL/PUSH |
| 5557 | B→A视频流 | B端 | A端(triple) | PUB/SUB |
| 5558 | C→B数据+视频 | B端 | C端 | PULL/PUSH |
| 5559 | A→LeRobot传感器 | LeRobot | A端(triple) | PULL/PUSH |

---

## 🚀 快速启动（3步）

```bash
# 第1步：启动bind端口的服务
终端1: cd whole2 && python B_reverse_whole.py
终端2: python lerobot_zeroMQ_imu.py

# 第2步（可选）：启动C端
终端3: cd whole2 && python C_real_video_reverse.py

# 第3步：启动Triple
终端4: python triple_imu_rs485_publisher.py --online-only --enable-video

# 或使用快速启动脚本
./start_system.sh
```

---

## 🔧 Triple常用命令

```bash
# 基础启动（仅发送传感器数据）
python triple_imu_rs485_publisher.py --online-only

# 完整启动（传感器数据 + 视频接收）
python triple_imu_rs485_publisher.py --online-only --enable-video

# 远程B端
python triple_imu_rs485_publisher.py --online-only \
       --b-host 192.168.1.100 --b-port 5555 \
       --enable-video --video-host 192.168.1.100

# 自定义LeRobot端口
python triple_imu_rs485_publisher.py --online-only \
       --lerobot-host localhost --lerobot-port 5559

# 自定义串口和频率
python triple_imu_rs485_publisher.py --online-only \
       --port /dev/ttyUSB0 --baud 115200 --interval 0.1
```

---

## ⌨️ 键盘控制

| 按键 | 功能 |
|------|------|
| 按住 `1` | 夹爪持续打开 |
| 按住 `2` | 夹爪持续闭合 |
| 松开按键 | 立即停止（100ms超时） |
| `q` | 退出程序 |

---

## 📊 数据格式

### Triple发送（JSON）
```json
{
  "position": [0.35, 0.0, 0.25],    // 末端位置（米）
  "orientation": [0.0, -0.5, 0.0],  // 姿态（弧度）
  "gripper": 0.5,                   // 夹爪（0-1）
  "t": 1234567890.123               // 时间戳
}
```

### B端接收视频（Pickle）
```python
{
  'image': b'...',          # JPEG压缩图像
  'encoding': 'jpeg',
  'timestamp': 1234567890.123,
  'resolution': (640, 480)
}
```

---

## 🔍 问题排查速查

| 问题 | 检查命令 | 解决方法 |
|------|----------|---------|
| B端收不到数据 | `netstat -tuln \| grep 5555` | 先启动B端，再启动Triple |
| LeRobot无响应 | `grep 5559 lerobot_zeroMQ_imu.py` | 确认使用PULL模式和5559端口 |
| 端口被占用 | `lsof -i :5555` | `kill -9 <PID>` |
| 视频延迟高 | 检查网络带宽 | 降低JPEG质量或帧率 |
| IMU离线 | 检查串口 | `ls -l /dev/ttyUSB*` |

---

## 📝 日志关键词

| 日志 | 含义 |
|------|------|
| `✓ ZeroMQ PUSH socket已连接到B端` | Triple成功连接B端5555 |
| `✓ ZeroMQ PUSH socket已连接到LeRobot` | Triple成功连接LeRobot 5559 |
| `✓ 视频接收已连接到` | 视频SUB连接成功 |
| `IMU在线 ✅` | IMU传感器数据正常 |
| `📹 [视频] 接收帧` | 正在接收B端视频流 |
| `⚠️ 等待IMU在线` | IMU未检测到或离线 |

---

## 🛠️ 配置修改

### 修改坐标映射范围
编辑 `triple_imu_rs485_publisher.py` 第86-100行：
```python
X_RAW_MIN = 0.39    # 原始X最小值
X_RAW_MAX = 0.52    # 原始X最大值
X_TARGET_MIN = 0.22 # MuJoCo X最小值
X_TARGET_MAX = 0.42 # MuJoCo X最大值
```

### 修改杆长
编辑第82-83行：
```python
L1 = 0.25  # 杆1长度（米）
L2 = 0.27  # 杆2长度（米）
```

### 修改Yaw归零模式
编辑第105行：
```python
YAW_NORMALIZATION_MODE = "NORMAL"  # NORMAL/AUTO/SIMPLE/OFF
```

---

## 📚 文档索引

| 文档 | 内容 |
|------|------|
| `ZMQ_ARCHITECTURE.md` | 完整架构说明和通信流程 |
| `MODIFICATION_SUMMARY.md` | 本次修改的详细总结 |
| `README.md` | 项目介绍和使用说明 |
| `start_system.sh` | 交互式启动脚本 |

---

## 🔗 相关文件

| 文件 | 作用 |
|------|------|
| `triple_imu_rs485_publisher.py` | A端（传感器采集和发送） |
| `lerobot_zeroMQ_imu.py` | 本地LeRobot（MuJoCo仿真） |
| `whole2/B_reverse_whole.py` | B端（中继和数据集） |
| `whole2/C_real_video_reverse.py` | C端（执行和视频） |
| `whole2/A_real_video.py` | 参考实现（双线程PUSH/SUB） |

---

## ⚡ 性能优化

```python
# 减少打印频率（降低CPU占用）
if frame_count % 30 == 0:  # 每30帧打印一次

# 限制ZMQ发送缓冲区（避免内存积压）
socket.setsockopt(zmq.SNDHWM, 10)

# 视频只保留最新帧（减少延迟）
socket.setsockopt(zmq.CONFLATE, 1)

# 降低JPEG质量（减少带宽）
cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
```

---

**最后更新：2025年11月13日**
