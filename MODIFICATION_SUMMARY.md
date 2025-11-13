# 修改总结 - Triple文件ZMQ架构重构

## 修改日期：2025年11月13日

---

## 📋 修改概览

**目标**：将triple_imu_rs485_publisher.py的ZMQ通信模式从PUB/SUB改为PUSH/PULL，完全匹配B_reverse_whole.py和A_real_video.py的架构。

**修改文件**：
1. ✅ `triple_imu_rs485_publisher.py` - A端（传感器采集）
2. ✅ `lerobot_zeroMQ_imu.py` - 本地LeRobot（MuJoCo仿真）
3. ✅ 新增 `ZMQ_ARCHITECTURE.md` - 架构说明文档

---

## 🔧 核心修改点

### 1. triple_imu_rs485_publisher.py（A端）

#### 修改前（旧架构）：
```python
# ❌ 错误：使用PUB模式，不匹配B端的PULL
DEFAULT_BIND_ADDRESS = "tcp://127.0.0.1:5555"
pub_socket = zmq.Context().socket(zmq.PUB)
pub_socket.bind(DEFAULT_BIND_ADDRESS)
pub_socket.send_string(json.dumps(message))
```

#### 修改后（新架构）：
```python
# ✅ 正确：使用双PUSH模式，参考A_real_video.py
DEFAULT_B_HOST = "localhost"
DEFAULT_B_PORT_COMMAND = 5555  # 发送到B端
DEFAULT_LEROBOT_HOST = "localhost"
DEFAULT_LEROBOT_PORT = 5559  # 发送到本地LeRobot

# Socket 1: PUSH到B端（匹配B的PULL）
socket_to_b = zmq.Context().socket(zmq.PUSH)
socket_to_b.connect(f"tcp://{DEFAULT_B_HOST}:{DEFAULT_B_PORT_COMMAND}")

# Socket 2: PUSH到本地LeRobot
socket_to_lerobot = zmq.Context().socket(zmq.PUSH)
socket_to_lerobot.connect(f"tcp://{DEFAULT_LEROBOT_HOST}:{DEFAULT_LEROBOT_PORT}")

# 双PUSH发送（同时发送到B端和LeRobot）
message_json = json.dumps(message)
socket_to_b.send_string(message_json)
socket_to_lerobot.send_string(message_json)
```

#### 新增命令行参数：
```python
--b-host localhost          # B端服务器地址
--b-port 5555               # B端命令端口
--lerobot-host localhost    # 本地LeRobot地址
--lerobot-port 5559         # 本地LeRobot端口（新增独立端口）
```

---

### 2. lerobot_zeroMQ_imu.py（本地LeRobot）

#### 修改前（旧架构）：
```python
# ❌ 错误：使用SUB模式监听5555，与B端PULL冲突
socket = zmq.Context().socket(zmq.SUB)
socket.connect("tcp://localhost:5555")  # 端口冲突！
socket.setsockopt(zmq.SUBSCRIBE, b"")

# 非阻塞接收
message = socket.recv_string(zmq.NOBLOCK)
```

#### 修改后（新架构）：
```python
# ✅ 正确：使用PULL模式监听5559，独立端口避免冲突
socket = zmq.Context().socket(zmq.PULL)
socket.bind("tcp://127.0.0.1:5559")  # 独立端口5559

# 阻塞接收（PULL模式自动等待）
message = socket.recv_string()  # 不需要NOBLOCK
```

---

## 🔄 架构对比

### 旧架构（错误）：
```
A端(triple) ──PUB──> localhost:5555 ──SUB──> B端 (❌ 不匹配B的PULL)
                                 └──SUB──> LeRobot (❌ 端口冲突)
```

### 新架构（正确）：
```
A端(triple) ──PUSH──> localhost:5555 ──PULL──> B端 (✅ 匹配)
            └─PUSH──> localhost:5559 ──PULL──> LeRobot (✅ 独立端口)
            
A端(triple) ←─SUB───  localhost:5557 ←─PUB─── B端 (✅ 视频流)
```

---

## 📡 端口分配（最终版）

| 端口 | 绑定方 | 连接方 | 模式 | 用途 | 数据格式 |
|------|--------|--------|------|------|---------|
| **5555** | B端 | A端(triple) | PULL/PUSH | A→B传感器数据 | JSON |
| **5556** | C端 | B端 | PULL/PUSH | B→C控制命令 | Pickle |
| **5557** | B端 | A端(triple) | PUB/SUB | B→A视频流 | Pickle |
| **5558** | B端 | C端 | PULL/PUSH | C→B数据+视频 | Pickle |
| **5559** | LeRobot | A端(triple) | PULL/PUSH | A→LeRobot传感器数据 | JSON |

---

## 🚀 启动顺序（重要！）

**正确启动顺序（避免ZMQ连接失败）：**

```bash
# 第1步：启动bind端口的服务（必须先启动）
终端1: cd whole2 && python B_reverse_whole.py        # B端bind 5555, 5557, 5558
终端2: python lerobot_zeroMQ_imu.py                  # LeRobot bind 5559

# 第2步：启动C端（连接到B端）
终端3: cd whole2 && python C_real_video_reverse.py   # C端connect到B的5556, 5558

# 第3步：启动A端（连接到B端和LeRobot）
终端4: python triple_imu_rs485_publisher.py --online-only --enable-video
       # A端connect到B的5555, 5557和LeRobot的5559
```

**停止顺序（优雅关闭）：**
```bash
1. 停止A端（triple）
2. 停止C端
3. 停止LeRobot
4. 停止B端
```

---

## 📝 测试验证

### 测试1：验证A端发送到B端
```bash
# 终端1：启动B端（应该看到接收日志）
cd whole2 && python B_reverse_whole.py

# 终端2：启动A端（应该看到发送日志）
python triple_imu_rs485_publisher.py --online-only
```

**预期结果**：
- A端显示：`✓ ZeroMQ PUSH socket已连接到B端: tcp://localhost:5555`
- B端显示：接收到A端的传感器数据（position, orientation, gripper）

---

### 测试2：验证A端发送到LeRobot
```bash
# 终端1：启动LeRobot（应该看到PULL绑定5559）
python lerobot_zeroMQ_imu.py

# 终端2：启动A端
python triple_imu_rs485_publisher.py --online-only
```

**预期结果**：
- LeRobot显示：`✓ ZeroMQ PULL socket已绑定到 tcp://127.0.0.1:5559`
- LeRobot显示：接收到传感器数据，MuJoCo仿真开始运动

---

### 测试3：验证视频接收（可选）
```bash
# 终端1：启动B端
cd whole2 && python B_reverse_whole.py

# 终端2：启动C端（发送视频到B）
cd whole2 && python C_real_video_reverse.py

# 终端3：启动A端（启用视频接收）
python triple_imu_rs485_publisher.py --online-only --enable-video
```

**预期结果**：
- A端显示：`✓ 视频接收已连接到 localhost:5557`
- A端显示：`📹 [视频] 接收帧 #30, 延迟: XX.Xms`

---

## 🔍 问题排查

### 问题1：B端收不到A端数据
**症状**：B端无日志，A端正常发送

**解决方法**：
```bash
# 检查B端是否先启动
ps aux | grep B_reverse_whole

# 检查B端是否绑定5555端口
netstat -tuln | grep 5555

# 检查A端是否使用PUSH模式
grep "socket_to_b.*PUSH" triple_imu_rs485_publisher.py
```

---

### 问题2：LeRobot收不到数据
**症状**：MuJoCo仿真不动，无数据接收日志

**解决方法**：
```bash
# 检查端口是否正确（5559而不是5555）
grep "5559" lerobot_zeroMQ_imu.py

# 检查是否使用PULL模式
grep "zmq.PULL" lerobot_zeroMQ_imu.py

# 检查LeRobot是否先启动
ps aux | grep lerobot_zeroMQ_imu
```

---

### 问题3：启动报错"Address already in use"
**症状**：bind失败，端口被占用

**解决方法**：
```bash
# 查找占用端口的进程
lsof -i :5555
lsof -i :5559

# 杀死占用进程
kill -9 <PID>

# 或等待ZMQ超时释放（约60秒）
```

---

## 📚 参考文档

1. **ZMQ_ARCHITECTURE.md** - 完整架构说明和通信流程
2. **A_real_video.py** - 双线程PUSH/SUB参考实现
3. **B_reverse_whole.py** - B端中继和数据集保存

---

## ✅ 修改验证清单

- [x] triple使用PUSH模式connect到B端5555
- [x] triple新增PUSH模式connect到LeRobot 5559
- [x] triple的SUB模式connect到B端5557（视频）
- [x] lerobot改为PULL模式bind 5559
- [x] 命令行参数更新（--b-host, --b-port, --lerobot-port）
- [x] 文档注释更新（文件头部说明）
- [x] 帮助信息更新（argparse epilog）
- [x] 架构说明文档创建（ZMQ_ARCHITECTURE.md）

---

## 🎯 核心改进

| 改进项 | 旧版本 | 新版本 | 优势 |
|--------|--------|--------|------|
| **通信模式** | PUB/SUB广播 | PUSH/PULL队列 | 消息不丢失，保证送达 |
| **端口冲突** | 5555同时被B和LeRobot监听 | B用5555，LeRobot用5559 | 避免冲突 |
| **架构一致性** | 与B端不兼容 | 完全匹配A_real_video.py | 标准化架构 |
| **数据可靠性** | 订阅者离线时消息丢失 | 发送端排队等待 | 数据完整性 |

---

**修改完成时间：2025年11月13日**  
**测试状态：待验证**  
**文档版本：v2.1**
