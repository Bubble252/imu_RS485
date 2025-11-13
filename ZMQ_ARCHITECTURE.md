# ZeroMQ架构说明文档

## 最新架构（基于A_real_video.py + B_reverse_whole.py）

### 架构概览

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         A端（triple_imu_rs485_publisher.py）              │
│                                                                          │
│  IMU1(0x50) ─┐                                                          │
│  IMU2(0x51) ─┼─> 运动学计算 ─┐                                          │
│  IMU3(0x52) ─┘               ├─> 数据打包 ─┐                            │
│  键盘(1/2) ──────────────────┘             │                            │
│                                             │                            │
│  ┌──────────────────────────────────────────┴──────────────────┐        │
│  │            ZMQ双PUSH发送 + SUB接收（参考A_real_video.py）    │        │
│  └──────────────────────────────────────────┬──────────────────┘        │
│                                             │                            │
│  PUSH ────────> localhost:5555 (传感器数据到B端)                         │
│  PUSH ────────> localhost:5559 (传感器数据到LeRobot)                     │
│  SUB  <──────── localhost:5557 (视频流从B端，可选)                       │
└──────────────────────────────────────────────────────────────────────────┘
                │                    │                    │
                │ 传感器数据          │ 传感器数据          │ 视频流
                ↓                    ↓                    ↑
┌─────────────────────────────┐  ┌──────────────────────────────────┐
│    B端（B_reverse_whole.py） │  │  本地LeRobot（lerobot_zeroMQ_imu.py）│
│                             │  │                                  │
│  5555: PULL (bind)          │  │  5559: PULL (bind)               │
│  5557: PUB  (bind) ─────────┼──┘  接收传感器数据                   │
│  5556: PUSH (connect到C)    │     MuJoCo实时仿真                  │
│  5558: PULL (bind从C)       │                                    │
│                             │                                    │
│  转发到C端 + LeRobot数据集   │                                    │
└─────────────────────────────┘                                    │
                │                                                  │
                │ 控制命令                                          │
                ↓                                                  │
┌─────────────────────────────┐                                    │
│    C端（C_real_video_reverse.py）                                 │
│                             │                                    │
│  5556: PULL (bind)          │                                    │
│  5558: PUB  (connect)       │                                    │
│                             │                                    │
│  执行控制 + 视频采集         │                                    │
└─────────────────────────────┘                                    │
                                                                   │
                                                                   │
                                    MuJoCo Viewer ←────────────────┘
                                    实时仿真显示
```

---

## 端口分配表

| 端口 | 模式 | 绑定方/连接方 | 用途 | 数据格式 |
|------|------|--------------|------|---------|
| **5555** | PULL/PUSH | B端bind，A端connect | A→B传感器数据 | JSON |
| **5556** | PULL/PUSH | C端bind，B端connect | B→C控制命令 | Pickle |
| **5557** | PUB/SUB | B端bind，A端connect | B→A视频流 | Pickle (JPEG压缩) |
| **5558** | PULL/PUSH | B端bind，C端connect | C→B数据+视频 | Pickle |
| **5559** | PULL/PUSH | LeRobot bind，A端connect | A→LeRobot传感器数据 | JSON |

---

## 关键修改点

### 1. triple_imu_rs485_publisher.py（A端）

**旧版本（错误）：**
```python
# PUB模式 - 广播，不匹配B端的PULL
pub_socket = zmq.PUB
pub_socket.bind("tcp://127.0.0.1:5555")
```

**新版本（正确）：**
```python
# PUSH模式 - 点对点队列，匹配B端的PULL
socket_to_b = zmq.PUSH
socket_to_b.connect("tcp://localhost:5555")  # connect到B端

# 新增：独立的PUSH到本地LeRobot
socket_to_lerobot = zmq.PUSH
socket_to_lerobot.connect("tcp://localhost:5559")  # connect到LeRobot

# 视频接收（SUB模式，保持不变）
video_socket = zmq.SUB
video_socket.connect("tcp://localhost:5557")  # connect到B端
```

**发送逻辑：**
```python
# 双PUSH发送（同时发送到B端和LeRobot）
message_json = json.dumps(message)
socket_to_b.send_string(message_json)         # 发送到B端
socket_to_lerobot.send_string(message_json)   # 发送到本地LeRobot
```

---

### 2. lerobot_zeroMQ_imu.py（本地MuJoCo仿真）

**旧版本（冲突）：**
```python
# SUB模式 - 订阅localhost:5555
socket = zmq.SUB
socket.connect("tcp://localhost:5555")  # 与B端冲突！
socket.setsockopt(zmq.SUBSCRIBE, b"")
```

**新版本（正确）：**
```python
# PULL模式 - 匹配A端的PUSH
socket = zmq.PULL
socket.bind("tcp://127.0.0.1:5559")  # 独立端口，避免冲突
```

**接收逻辑：**
```python
# PULL模式会阻塞等待，不需要NOBLOCK
message = socket.recv_string()  # 阻塞接收
data = json.loads(message)
```

---

### 3. B_reverse_whole.py（B端，无需修改）

B端配置已经正确，无需修改：

```python
# 5555: PULL socket - 接收A的传感器数据
socket_from_a = zmq.PULL
socket_from_a.bind("tcp://0.0.0.0:5555")

# 5557: PUB socket - 发送视频给A
socket_to_a_video = zmq.PUB
socket_to_a_video.bind("tcp://0.0.0.0:5557")

# 5556: PUSH socket - 转发控制命令给C
socket_to_c = zmq.PUSH
socket_to_c.connect("tcp://C_HOST:5556")

# 5558: PULL socket - 接收C的数据和视频
socket_from_c = zmq.PULL
socket_from_c.bind("tcp://0.0.0.0:5558")
```

---

## 数据流详解

### 传感器数据流（A → B + LeRobot）

**triple_imu_rs485_publisher.py（A端）发送：**
```json
{
  "position": [0.35, 0.0, 0.25],        // 末端位置（米）
  "orientation": [0.0, -0.5, 0.0],      // 机械爪姿态（弧度）
  "gripper": 0.5,                       // 夹爪开合度（0.0-1.0）
  "t": 1234567890.123                   // 时间戳
}
```

**B_reverse_whole.py（B端）处理：**
1. PULL接收A的传感器数据
2. 转发到C端（PUSH）
3. 保存到LeRobot数据集
4. 从C端接收视频（PULL）
5. 转发视频给A端（PUB）

**lerobot_zeroMQ_imu.py（本地LeRobot）处理：**
1. PULL接收A的传感器数据
2. 解析position, orientation, gripper
3. 逆运动学计算
4. 更新MuJoCo仿真

---

### 视频流（C → B → A）

**C_real_video_reverse.py（C端）发送：**
```python
frame_data = {
    'image': encoded_jpeg,          # JPEG压缩的图像（bytes）
    'encoding': 'jpeg',
    'timestamp': time.time(),
    'resolution': (640, 480)
}
video_socket.send(pickle.dumps(frame_data))
```

**B_reverse_whole.py（B端）转发：**
```python
# 从C接收
c_data = socket_from_c.recv()
# 转发给A
socket_to_a_video.send(c_data)
```

**triple_imu_rs485_publisher.py（A端）接收：**
```python
# SUB socket接收
video_data = video_socket.recv()
frame_dict = pickle.loads(video_data)
# 解码JPEG
frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
cv2.imshow('Remote Video from B', frame)
```

---

## 启动顺序

**推荐启动顺序（避免ZMQ连接超时）：**

```bash
# 1. 先启动所有bind端口的服务（B端和本地LeRobot）
# 终端1：启动B端
cd whole2
python B_reverse_whole.py

# 终端2：启动本地LeRobot（MuJoCo仿真）
python lerobot_zeroMQ_imu.py

# 2. 再启动C端（连接到B端）
# 终端3：启动C端
cd whole2
python C_real_video_reverse.py

# 3. 最后启动A端（triple，连接到B端和LeRobot）
# 终端4：启动triple
python triple_imu_rs485_publisher.py --online-only --enable-video
```

**停止顺序（优雅关闭）：**
```bash
# 1. 先停止A端（Ctrl+C或按'q'键）
# 2. 停止C端（Ctrl+C）
# 3. 停止本地LeRobot（Ctrl+C）
# 4. 最后停止B端（Ctrl+C）
```

---

## 通信模式对比

### PUB/SUB（发布/订阅）
- **特点**：一对多广播，订阅者可以随时加入/退出
- **缓冲策略**：订阅者离线时，消息会丢失
- **适用场景**：视频流、状态广播
- **本项目使用**：B→A视频流（端口5557）

### PUSH/PULL（推/拉）
- **特点**：点对点队列，负载均衡，消息不会丢失
- **缓冲策略**：接收者离线时，消息会在发送端排队
- **适用场景**：任务分发、控制命令
- **本项目使用**：
  - A→B传感器数据（端口5555）
  - A→LeRobot传感器数据（端口5559）
  - B→C控制命令（端口5556）
  - C→B数据上传（端口5558）

---

## 常见问题排查

### 问题1：B端收不到A端的传感器数据

**可能原因：**
- A端使用了PUB模式而不是PUSH模式
- 端口号不匹配
- B端没有先启动（PULL必须先bind）

**解决方法：**
```bash
# 检查A端是否使用PUSH模式
grep "socket_to_b.*PUSH" triple_imu_rs485_publisher.py

# 检查B端是否已启动并绑定5555端口
netstat -tuln | grep 5555

# 检查启动顺序（先B后A）
```

### 问题2：本地LeRobot收不到数据

**可能原因：**
- lerobot_zeroMQ_imu.py仍在监听5555而不是5559
- 使用了SUB模式而不是PULL模式
- LeRobot没有先启动

**解决方法：**
```bash
# 检查lerobot是否使用PULL模式和5559端口
grep "socket.*PULL" lerobot_zeroMQ_imu.py
grep "5559" lerobot_zeroMQ_imu.py

# 检查端口占用
netstat -tuln | grep 5559
```

### 问题3：视频显示延迟高

**可能原因：**
- B端视频缓冲区积压
- 网络带宽不足
- JPEG压缩质量过高

**解决方法：**
```python
# A端设置CONFLATE（只保留最新帧）
video_socket.setsockopt(zmq.CONFLATE, 1)

# B端降低JPEG质量
cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
```

---

## 性能优化建议

### 1. 减少JSON序列化开销
```python
# 预计算JSON字符串，避免重复序列化
message_json = json.dumps(message)
socket_to_b.send_string(message_json)
socket_to_lerobot.send_string(message_json)
```

### 2. 视频帧率控制
```python
# C端限制视频采集帧率
if time.time() - last_frame_time > 1.0 / TARGET_FPS:
    # 采集和发送视频帧
    last_frame_time = time.time()
```

### 3. ZMQ高水位标记（HWM）
```python
# 限制发送缓冲区大小，避免内存积压
socket_to_b.setsockopt(zmq.SNDHWM, 10)
socket_to_lerobot.setsockopt(zmq.SNDHWM, 10)
```

---

## 参考资料

- **A_real_video.py**：双线程PUSH/SUB架构参考
- **B_reverse_whole.py**：B端中继和LeRobot数据集保存
- **ZeroMQ官方文档**：https://zeromq.org/socket-api/

---

## 版本历史

| 版本 | 日期 | 修改内容 |
|------|------|---------|
| v1.0 | 2025-11-13 | 初始版本，PUB模式（与B端不兼容） |
| v2.0 | 2025-11-13 | 修改为PUSH模式，参考A_real_video.py |
| v2.1 | 2025-11-13 | 新增独立LeRobot端口5559，避免冲突 |

---

**最后更新：2025年11月13日**
