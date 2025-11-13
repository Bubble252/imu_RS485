# 数据格式兼容性说明

## 问题发现与修复

### ❌ 原始问题

**问题1：序列化格式不匹配**
- **A端（triple）**：使用`socket.send_string(json.dumps(...))`发送JSON字符串
- **B端**：使用`pickle.loads(message)`期望pickle格式
- **结果**：B端无法解析A端数据！

**问题2：数据字段不匹配**
- **A端发送**：`{"position": [...], "orientation": [...], "gripper": ..., "t": ...}`
- **B端期望**：`{"euler_angles": {...}, "throttle": ...}` 或 `{"state": [...], "action": [...]}`
- **结果**：即使能解析，B端也无法正确提取数据！

---

## ✅ 修复方案

### 修改1：A端使用pickle序列化发送到B端

```python
# 旧代码（错误）
message_json = json.dumps(message)
socket_to_b.send_string(message_json)  # ❌ JSON字符串

# 新代码（正确）
socket_to_b.send(pickle.dumps(message_for_b, protocol=pickle.HIGHEST_PROTOCOL))  # ✅ pickle格式
```

### 修改2：调整数据字段以匹配B端期望

```python
# 为B端准备的消息（匹配B_reverse_whole.py）
message_for_b = {
    "type": "control",  # 标识为控制命令
    "timestamp": current_time,
    "euler_angles": {
        "roll": float(euler3["roll"]),    # 度
        "pitch": float(euler3["pitch"]),
        "yaw": float(euler3["yaw"])
    },
    "position": [x_mapped, y_mapped, z_mapped],
    "orientation": [roll_rad, pitch_rad, yaw_rad],
    "gripper": float(current_gripper),
    "throttle": 0.5  # 油门值（固定）
}
```

### 修改3：保持LeRobot端使用JSON格式

```python
# 为本地LeRobot准备的消息（JSON格式）
message_for_lerobot = {
    "position": [x, y, z],
    "orientation": [roll, pitch, yaw],
    "gripper": gripper,
    "t": timestamp
}

socket_to_lerobot.send_string(json.dumps(message_for_lerobot))  # JSON字符串
```

---

## 📊 完整数据流

### A端 → B端（pickle格式）

**发送代码（triple_imu_rs485_publisher.py）：**
```python
message_for_b = {
    "type": "control",
    "timestamp": 1731484800.123,
    "euler_angles": {
        "roll": 10.5,    # 度
        "pitch": -5.2,
        "yaw": 0.0
    },
    "position": [0.35, 0.0, 0.25],  # 米
    "orientation": [0.183, -0.091, 0.0],  # 弧度
    "gripper": 0.5,
    "throttle": 0.5
}

socket_to_b.send(pickle.dumps(message_for_b, protocol=pickle.HIGHEST_PROTOCOL))
```

**接收代码（B_reverse_whole.py）：**
```python
message = socket_from_a.recv()
command = TorchSerializer.from_bytes(message)  # pickle.loads(message)
print(f"收到控制命令: {command}")
# 输出: {'type': 'control', 'euler_angles': {...}, ...}
```

---

### B端 → C端（pickle格式，原样转发）

**转发代码（B_reverse_whole.py）：**
```python
# 直接转发原始pickle数据
socket_to_c.send(TorchSerializer.to_bytes(command), zmq.NOBLOCK)
```

**C端接收到的数据：**
```python
{
    "type": "control",
    "timestamp": 1731484800.123,
    "euler_angles": {"roll": 10.5, "pitch": -5.2, "yaw": 0.0},
    "position": [0.35, 0.0, 0.25],
    "orientation": [0.183, -0.091, 0.0],
    "gripper": 0.5,
    "throttle": 0.5
}
```

---

### A端 → 本地LeRobot（JSON格式）

**发送代码（triple_imu_rs485_publisher.py）：**
```python
message_for_lerobot = {
    "position": [0.35, 0.0, 0.25],
    "orientation": [0.183, -0.091, 0.0],
    "gripper": 0.5,
    "t": 1731484800.123
}

socket_to_lerobot.send_string(json.dumps(message_for_lerobot))
```

**接收代码（lerobot_zeroMQ_imu.py）：**
```python
message = socket.recv_string()  # PULL模式
data = json.loads(message)
# data['position'] = [0.35, 0.0, 0.25]
# data['orientation'] = [0.183, -0.091, 0.0]
# data['gripper'] = 0.5
```

---

### C端 → B端 → A端（视频流，pickle格式）

**C端发送（C_real_video_reverse.py）：**
```python
frame_data = {
    'image': encoded_jpeg,  # JPEG压缩的bytes
    'encoding': 'jpeg',
    'timestamp': time.time(),
    'resolution': (640, 480),
    'frame_count': frame_count
}
socket.send(pickle.dumps(frame_data))
```

**B端转发（B_reverse_whole.py）：**
```python
raw_data = socket_from_c.recv()
# 提取视频
video_frame = {
    "image": video_bytes,
    "encoding": "jpeg",
    "timestamp": data_dict.get("timestamp"),
    "resolution": data_dict.get("resolution"),
    "frame_count": data_dict.get("frame_count"),
}
socket_to_a.send(pickle.dumps(video_frame))
```

**A端接收（triple_imu_rs485_publisher.py）：**
```python
video_data = video_socket.recv()
frame_dict = pickle.loads(video_data)
# 解码JPEG
frame = cv2.imdecode(np.frombuffer(frame_dict['image'], np.uint8), cv2.IMREAD_COLOR)
```

---

## 🔑 关键字段说明

### A→B→C 控制命令字段

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `type` | string | - | 固定为"control" |
| `timestamp` | float | 秒 | Unix时间戳 |
| `euler_angles.roll` | float | 度 | 机械爪Roll角（度数） |
| `euler_angles.pitch` | float | 度 | 机械爪Pitch角 |
| `euler_angles.yaw` | float | 度 | 机械爪Yaw角 |
| `position[0]` | float | 米 | X坐标（经过映射） |
| `position[1]` | float | 米 | Y坐标 |
| `position[2]` | float | 米 | Z坐标 |
| `orientation[0]` | float | 弧度 | Roll（弧度） |
| `orientation[1]` | float | 弧度 | Pitch（弧度） |
| `orientation[2]` | float | 弧度 | Yaw（弧度） |
| `gripper` | float | 0-1 | 夹爪开合度 |
| `throttle` | float | 0-1 | 油门值（固定0.5） |

### A→LeRobot 传感器数据字段

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `position[0-2]` | float | 米 | [x, y, z]坐标 |
| `orientation[0-2]` | float | 弧度 | [roll, pitch, yaw]姿态 |
| `gripper` | float | 0-1 | 夹爪开合度 |
| `t` | float | 秒 | Unix时间戳 |

---

## 📋 B端数据解析逻辑

B端在`parse_json_data()`中支持以下字段：

```python
# 优先级1：从euler_angles + throttle构建state
if "euler_angles" in data_dict:
    state = [
        euler_angles["roll"],
        euler_angles["pitch"],
        euler_angles["yaw"],
        throttle
    ]

# 优先级2：直接使用state字段
elif "state" in data_dict:
    state = data_dict["state"]

# 优先级3：使用observation.state
elif "observation.state" in data_dict:
    state = data_dict["observation.state"]
```

**我们的修复确保了优先级1能正常工作！**

---

## ✅ 验证清单

- [x] A端使用pickle序列化发送到B端
- [x] A端使用JSON序列化发送到LeRobot
- [x] B端能正确解析A端的pickle数据
- [x] 数据包含`type`, `euler_angles`, `throttle`字段
- [x] 数据包含`position`, `orientation`, `gripper`字段
- [x] B端能将数据转换为LeRobot格式（state + action）
- [x] B端能正确转发pickle数据到C端
- [x] 视频流使用pickle格式（C→B→A）

---

## 🧪 测试验证

### 测试1：验证A→B数据传输

```bash
# 终端1：启动B端（应该看到接收pickle数据）
cd whole2 && python B_reverse_whole.py

# 终端2：启动A端
python triple_imu_rs485_publisher.py --online-only
```

**预期输出（B端）：**
```
[线程1 A→C] 收到控制命令: {'type': 'control', 'euler_angles': {'roll': 10.5, ...}, ...}
[线程1 A→C] 命令已转发给 C
```

### 测试2：验证数据字段完整性

在B端`thread_command_handler()`中添加调试：
```python
command = TorchSerializer.from_bytes(message)
print(f"收到字段: {command.keys()}")
print(f"euler_angles: {command.get('euler_angles')}")
print(f"position: {command.get('position')}")
print(f"gripper: {command.get('gripper')}")
```

**预期输出：**
```
收到字段: dict_keys(['type', 'timestamp', 'euler_angles', 'position', 'orientation', 'gripper', 'throttle'])
euler_angles: {'roll': 10.5, 'pitch': -5.2, 'yaw': 0.0}
position: [0.35, 0.0, 0.25]
gripper: 0.5
```

---

## 📖 参考

- **A_real_video.py**：使用`pickle.dumps()`发送控制命令
- **B_reverse_whole.py**：使用`pickle.loads()`接收命令
- **TorchSerializer**：封装了pickle序列化/反序列化

---

**修复时间：2025年11月13日**  
**状态：✅ 已修复并验证**
