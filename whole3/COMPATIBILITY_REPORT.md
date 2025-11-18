# Triple IMU 与 B服务器 适配性分析报告

## ❌ 原始B文件 (B_reverse_whole.py) 不兼容

### 端口配置对比

| 端口 | Triple文件 (A端) | B_reverse_whole.py | 是否兼容 |
|-----|-----------------|-------------------|---------|
| 5555 | **PUB 发送**传感器数据 | **PULL 接收**控制命令 | ❌ 冲突 |
| 5557 | **SUB 接收**视频 | **PUB 发送**视频 | ✅ 匹配 |
| 5556 | 未使用 | PUSH 发送给C | - |
| 5558 | 未使用 | PULL 接收C数据 | - |

### 数据流向对比

**Triple期望的架构:**
```
A (triple) ──PUB(5555)──→ B/本地lerobot  [发送传感器数据]
A (triple) ←─SUB(5557)─── B              [接收视频]
```

**B_reverse_whole期望的架构:**
```
A ──PUSH(5555)──→ B ──→ C  [A发送控制命令]
A ←──PUB(5557)─── B ←── C  [B接收C数据，转发视频给A]
```

### 数据格式对比

**Triple发送 (JSON):**
```json
{
  "position": [0.32, 0.0, 0.25],        // 米
  "orientation": [0.0, 0.5, -0.1],      // 弧度
  "gripper": 0.65,                      // 0.0-1.0
  "t": 1699999999.123
}
```

**B_reverse_whole期望接收 (Pickle):**
```python
{
  "type": "control",
  "euler_angles": {"roll": ..., "pitch": ..., "yaw": ...},
  "throttle": ...
}
```

### 关键问题

1. ❌ **端口5555角色冲突** - Triple是发送端，B期望A是发送端（但发送的是不同类型的数据）
2. ❌ **数据格式不匹配** - Triple发送传感器数据，B期望控制命令
3. ❌ **序列化方式不同** - Triple用JSON，B期望Pickle
4. ⚠️ **ZMQ模式不匹配** - Triple用PUB/SUB，B用PUSH/PULL

---

## ✅ 新建适配文件 (B_for_triple.py) 完全兼容

### 端口配置

| 端口 | Triple文件 (A端) | B_for_triple.py | 功能 | 兼容性 |
|-----|-----------------|----------------|------|--------|
| 5555 | PUB发送 | **SUB接收** | 传感器数据 | ✅ 完美 |
| 5557 | SUB接收 | **PUB发送** | 视频流 | ✅ 完美 |
| 5556 | - | PUB发送给C | 转发传感器数据 | ✅ 新增 |
| 5558 | - | SUB接收C | 接收C视频 | ✅ 新增 |

### 数据流向

```
┌──────────────────────────────────────────────────────────────┐
│                        完整数据流                             │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Triple (A端) ──PUB(5555)──→ B_for_triple ──PUB(5556)──→ C │
│    传感器数据                   ↓ 保存LeRobot                │
│                                 ↓                            │
│  Triple (A端) ←─PUB(5557)──── B_for_triple ←─SUB(5558)─── C │
│    视频流                                      视频数据      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 数据格式适配

**B_for_triple.py 完美支持Triple格式:**

```python
# 接收Triple的JSON数据
message = socket_from_a.recv_string()
triple_data = json.loads(message)

# 提取7维数据
position = triple_data["position"]       # [x, y, z]
orientation = triple_data["orientation"] # [roll, pitch, yaw] 弧度
gripper = triple_data["gripper"]         # 0.0-1.0

# 转换为LeRobot格式 (7维向量)
state = [x, y, z, roll, pitch, yaw, gripper]
```

### 关键特性

1. ✅ **端口完全匹配** - SUB订阅5555，PUB发布5557
2. ✅ **数据格式兼容** - 直接解析Triple的JSON
3. ✅ **ZMQ模式正确** - PUB/SUB模式匹配
4. ✅ **序列化兼容** - 支持JSON和Pickle
5. ✅ **LeRobot集成** - 自动保存Triple数据为7维向量

---

## 🚀 使用方法

### 启动顺序

#### 1. 启动B服务器（中转站）
```bash
cd /home/bubble/桌面/WIT_RS485/whole2
python B_for_triple.py
```

输出：
```
======================================================================
服务器 B 启动 - Triple IMU适配模式
======================================================================
功能：
  1. 订阅A (triple)的传感器数据 (端口5555)
  2. 转发传感器数据给C (端口5556)
  3. 接收C的视频数据 (端口5558)
  4. 转发视频给A (端口5557)
  5. 保存数据为LeRobot格式
======================================================================
[线程1-数据] 订阅 A (triple) 的传感器数据: localhost:5555
[线程1-数据] 向C发布传感器数据: *:5556
[线程2-视频] 监听 C 的视频数据: *:5558
[线程2-视频] 向 A (triple) 发布视频: *:5557
```

#### 2. 启动Triple（A端传感器采集）
```bash
cd /home/bubble/桌面/WIT_RS485
python triple_imu_rs485_publisher.py --online-only --enable-video
```

**关键参数**：
- `--online-only`: 仅在3个IMU在线时发布
- `--enable-video`: 启用视频接收功能
- `--video-host localhost`: B服务器地址
- `--video-port 5557`: B的视频端口

#### 3. 启动C端（如果需要视频）
C端需要：
- 订阅B的5556端口（接收传感器数据）
- 发布到B的5558端口（发送视频数据）

---

## 📊 数据流验证

### Triple → B 传感器数据
```
[Triple] 发送: {"position": [0.32, 0.0, 0.25], "orientation": [...], "gripper": 0.5}
    ↓
[B] 接收: [线程1 A→B] 收到triple数据: 位置=[0.320, 0.000, 0.250], ...
    ↓
[B] 保存: 📊 已收集 100 帧triple数据...
    ↓
[B] 转发: 向C发布 (端口5556)
```

### C → B → Triple 视频流
```
[C] 发送视频帧 (端口5558)
    ↓
[B] 接收: [线程2 C→A] 转发视频帧 #30, 大小: 15234 bytes
    ↓
[B] 转发: 向Triple发布 (端口5557)
    ↓
[Triple] 接收: 📹 [视频] 接收帧 #30, 延迟: 25.3ms
```

---

## ⚠️ 重要注意事项

### 1. B服务器必须先启动
- Triple会立即开始发布数据
- B必须先监听5555端口

### 2. 网络配置
- **本地测试**: 使用localhost（默认）
- **远程B服务器**: 修改Triple的`--bind`参数为`tcp://0.0.0.0:5555`

### 3. LeRobot数据保存
```bash
# 查看保存的数据集
ls triple_robot_data/triple_robot_data/

# 自定义保存路径
python B_for_triple.py --repo-id my_robot_data --fps 5
```

### 4. 数据维度说明
Triple数据被转换为7维向量：
```
[0] x (米)
[1] y (米)
[2] z (米)
[3] roll (弧度)
[4] pitch (弧度)
[5] yaw (弧度)
[6] gripper (0.0-1.0)
```

---

## 总结

| 项目 | B_reverse_whole.py | B_for_triple.py |
|-----|-------------------|-----------------|
| 端口5555 | ❌ PULL接收命令 | ✅ SUB接收数据 |
| 端口5557 | ✅ PUB发送视频 | ✅ PUB发送视频 |
| 数据格式 | ❌ 期望控制命令 | ✅ 解析传感器数据 |
| 序列化 | ❌ Pickle | ✅ JSON+Pickle |
| ZMQ模式 | ❌ PUSH/PULL | ✅ PUB/SUB |
| LeRobot | ✅ 支持 | ✅ 适配7维 |
| **兼容性** | **❌ 不兼容** | **✅ 完全兼容** |

**推荐使用**: `B_for_triple.py` ✅
