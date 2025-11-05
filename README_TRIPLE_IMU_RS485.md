# 三IMU RS485发布器使用说明

## 概述

这个程序通过RS485串口连接三个WIT IMU传感器，计算双杆机械臂的末端位置和机械爪姿态，并通过ZeroMQ发布到MuJoCo仿真环境。

## 硬件连接

- **IMU1 (地址 0x50)**: 连接到杆1，用于计算末端位置
- **IMU2 (地址 0x51)**: 连接到杆2，用于计算末端位置  
- **IMU3 (地址 0x52)**: 连接到机械爪，提供姿态信息

所有三个IMU通过RS485总线连接到同一个USB转RS485适配器（默认 `/dev/ttyUSB0`）。

## 机械参数

- 杆1长度: 275mm
- 杆2长度: 275mm
- 工作空间: x=[0, 0.55]m, y=[-0.4, 0.4]m, z=[0, 0.3]m
- 映射到MuJoCo: x=[0.22, 0.35]m, y=[-0.2, 0.2]m, z=[0.16, 0.36]m

## 快速开始

### 方法1: 使用启动脚本（推荐）

```bash
./run_triple_imu.sh
```

这个脚本会自动：
- 检查串口设备是否存在
- 修复权限问题（需要sudo）
- 激活Python虚拟环境
- 启动程序（--online-only模式）

### 方法2: 手动运行

```bash
# 1. 激活虚拟环境
source .venv/bin/activate

# 2. 确保串口权限正确
sudo chmod 666 /dev/ttyUSB0

# 3. 运行程序
python triple_imu_rs485_publisher.py --online-only
```

## 命令行参数

```bash
python triple_imu_rs485_publisher.py [选项]

选项：
  --port, -p PORT        RS485串口设备路径（默认: /dev/ttyUSB0）
  --baud BAUD            波特率（默认: 9600）
  --interval, -i SECS    发布间隔秒数（默认: 0.2，即5Hz）
  --bind, -b ADDR        ZeroMQ绑定地址（默认: tcp://127.0.0.1:5555）
  --online-only          仅在三个IMU都在线时发布（推荐）
```

## 使用示例

### 基本用法
```bash
# 使用默认参数（5Hz发布）
python triple_imu_rs485_publisher.py --online-only
```

### 高频发布
```bash
# 10Hz发布频率
python triple_imu_rs485_publisher.py --interval 0.1 --online-only
```

### 自定义串口
```bash
# 使用不同的串口设备
python triple_imu_rs485_publisher.py --port /dev/ttyACM0 --online-only
```

### 网络发布
```bash
# 绑定到所有网络接口，允许其他机器订阅
python triple_imu_rs485_publisher.py --bind tcp://0.0.0.0:5555 --online-only
```

## 数据格式

程序通过ZeroMQ发布JSON消息，格式如下：

```json
{
  "position": [x, y, z],              // 末端位置（米）
  "orientation": [roll, pitch, yaw],  // 机械爪姿态（度）
  "gripper": 0.0,                     // 夹爪状态（暂未实现）
  "t": 1234567890.123                 // 时间戳
}
```

### 字段说明

- **position**: 由IMU1和IMU2通过正向运动学计算得到的机械臂末端位置
  - 坐标系: 杆1基座为原点
  - 单位: 米
  - 已映射到MuJoCo工作空间范围

- **orientation**: 直接使用IMU3（机械爪）的欧拉角
  - roll: 翻滚角（度）
  - pitch: 俯仰角（度）
  - yaw: 偏航角（度，已归零）
  
- **gripper**: 夹爪开合状态（0.0 = 关闭，1.0 = 打开，暂未实现）

- **t**: Unix时间戳（秒）

## 运行输出

程序运行时会显示：

```
======================================================================
ZeroMQ发布器已启动（三IMU RS485模式）
======================================================================
发布地址: tcp://127.0.0.1:5555
发布频率: 5.0 Hz (间隔 200 ms)
在线检查: 启用（仅在三个IMU都在线时发布）
缓冲策略: Latest-only（无缓冲队列）
======================================================================

✓ IMU1 Yaw归零: 偏移量 = 74.52°
✓ IMU2 Yaw归零: 偏移量 = -90.28°
✓ IMU3 Yaw归零: 偏移量 = -90.40°

📡 发布统计 | 消息数: 10 | 实际频率: 5.0 Hz
   原始位置: [  0.234,  -0.156,   0.000] m
   映射位置: [  0.275,  -0.078,   0.160] m
   IMU1欧拉角: [R:  -2.8° P: -13.4° Y:   0.0°]
   IMU2欧拉角: [R:  -2.9° P: -13.5° Y:   0.1°]
   机械爪姿态: [R:  -2.9° P: -13.4° Y:   0.2°]
   IMU状态: IMU1=✓ IMU2=✓ IMU3=✓
```

## Yaw归零机制

程序启动时会自动记录每个IMU的初始Yaw角作为零点：
- 启动后首次接收到数据时记录偏移量
- 后续所有Yaw角度都减去该偏移量
- 确保机械臂从一个一致的"零位"开始

## 轨迹记录

程序会自动记录末端轨迹（最多1000个点）。按Ctrl+C停止后会：
- 自动生成轨迹图（3D视图 + XY平面投影）
- 保存为 `trajectory_rs485.png`

## 故障排除

### 串口打开失败
```bash
# 检查设备是否存在
ls -la /dev/ttyUSB0

# 检查权限
# 应该显示: crw-rw-rw- 或 crw-rw----（dialout组）

# 修复权限
sudo chmod 666 /dev/ttyUSB0

# 或者永久解决（需要重新登录）
sudo usermod -a -G dialout $USER
```

### IMU不在线
```
⚠️  等待IMU在线... IMU1: ✓, IMU2: ✗, IMU3: ✓ (已跳过 25 次)
```

**可能原因**：
1. IMU2未通电或连接不良
2. IMU2地址配置错误（应该是0x51）
3. RS485总线连接问题

**解决方法**：
```bash
# 运行设备检测程序
python check_devices.py

# 应该看到三个设备都在线：
# ✅ 在线 (响应29字节)
```

### ZeroMQ连接问题

如果MuJoCo接收端无法连接：

```bash
# 检查端口是否被占用
netstat -an | grep 5555

# 尝试绑定到所有接口
python triple_imu_rs485_publisher.py --bind tcp://0.0.0.0:5555
```

### 数据更新缓慢

如果IMU数据更新频率低：

```bash
# 检查RS485波特率是否正确
python triple_imu_rs485_publisher.py --baud 115200

# 减少发布频率以确保稳定性
python triple_imu_rs485_publisher.py --interval 0.5  # 2Hz
```

## 与蓝牙版本的区别

| 特性 | RS485版本 | 蓝牙版本 |
|------|----------|---------|
| 连接方式 | 有线RS485总线 | 无线蓝牙 |
| 设备识别 | Modbus地址(0x50-0x52) | MAC地址 |
| 同时采样 | 是（同一总线） | 否（分时扫描） |
| 延迟 | 低（<10ms） | 中（50-100ms） |
| 可靠性 | 高 | 中（易受干扰） |
| 移动范围 | 受线缆限制 | 10米范围 |
| 功耗 | 需要外部供电 | 电池供电 |
| 成本 | 需要RS485转换器 | 仅需蓝牙模块 |

## 依赖包

```bash
pip install pyserial numpy pyzmq matplotlib
```

或使用requirements.txt：
```bash
pip install -r requirements.txt
```

## 性能优化建议

1. **降低发布频率**: 如果不需要高频更新，使用`--interval 0.5`（2Hz）可以减少CPU占用

2. **禁用在线检查**: 如果三个IMU总是在线，去掉`--online-only`可以避免每次检查

3. **禁用轨迹记录**: 如果不需要轨迹图，可以注释掉轨迹记录代码以节省内存

4. **网络优化**: 如果发布到远程机器，考虑使用TCP而不是ZeroMQ的PUB/SUB模式

## 相关文件

- `triple_imu_rs485_publisher.py` - 主程序
- `device_model.py` - RS485 Modbus通信模块
- `test.py` - RS485设备测试程序
- `check_devices.py` - 设备地址扫描工具
- `run_triple_imu.sh` - 启动脚本
- `README_TRIPLE_IMU_RS485.md` - 本文件

## 技术支持

如有问题，请检查：
1. 所有IMU是否正确通电
2. RS485连线是否正确（A-A, B-B）
3. 设备地址是否配置为0x50, 0x51, 0x52
4. 波特率是否匹配（默认9600）
5. Python虚拟环境是否激活
6. 所有依赖包是否安装完整

## 许可证

MIT License
