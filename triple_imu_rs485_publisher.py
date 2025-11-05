#!/usr/bin/env python
# coding:UTF-8
"""
三IMU欧拉角读取 + ZeroMQ发布程序 (RS485版本)
基于RS485串口连接三个WIT IMU传感器，实时读取欧拉角并发布到MuJoCo仿真环境

功能说明：
1. 通过RS485连接三个IMU传感器，实时读取欧拉角
   - 设备1 (0x50): 杆1 (IMU1)
   - 设备2 (0x51): 杆2 (IMU2)
   - 设备3 (0x52): 机械爪 (IMU3)
2. 计算两杆串联机械臂的末端位置（IMU1 + IMU2）
3. 读取机械爪的姿态（IMU3）
4. 通过ZeroMQ PUB socket发布数据到MuJoCo仿真接收端
5. 发布频率默认5Hz，采用latest-only策略

数据流架构：
    IMU1 (0x50/RS485) ──┐
                         ├──> 运动学计算 ──> 末端位置
    IMU2 (0x51/RS485) ──┘                        ↓
    IMU3 (0x52/RS485) ──────> 机械爪姿态  ────────┴──> ZeroMQ发布 ──> MuJoCo仿真

运行方法：
    # 使用默认参数（5Hz发布到localhost:5555）
    python triple_imu_rs485_publisher.py
    
    # 仅在三个IMU都在线时发布（推荐）
    python triple_imu_rs485_publisher.py --online-only
    
    # 自定义发布频率和串口
    python triple_imu_rs485_publisher.py --port /dev/ttyUSB0 --interval 0.1 --online-only
"""
import time
import json
import argparse
import numpy as np
import zmq
import threading
from collections import deque
from scipy.spatial.transform import Rotation

import device_model

# === 机械臂参数配置 ===
L1 = 0.25  # 杆1长度（米）
L2 = 0.27  # 杆2长度（米）

# === IMU设备地址配置 ===
IMU1_ADDR = 0x50  # 80 - 杆1
IMU2_ADDR = 0x51  # 81 - 杆2
IMU3_ADDR = 0x52  # 82 - 机械爪

# === ZeroMQ默认配置 ===
DEFAULT_BIND_ADDRESS = "tcp://127.0.0.1:5555"
DEFAULT_PUBLISH_INTERVAL = 0.2  # 5Hz

# === Yaw归零模式 ===
YAW_NORMALIZATION_MODE = "NORMAL"  # "NORMAL": 首次数据归零, "AUTO": 智能偏置, "SIMPLE": ±180翻转, "OFF": 不归零
YAW_NORMALIZATION_THRESHOLD = 100.0  # Yaw角超过±100度时判定为边界初始化

# === 坐标映射参数配置 ===
# 机械臂原始工作空间范围（米）
X_RAW_MIN = 0.39
X_RAW_MAX = 0.52
Y_RAW_MIN = -0.4
Y_RAW_MAX = 0.4
Z_RAW_MIN = 0.0
Z_RAW_MAX = 0.3

# MuJoCo目标空间范围（米）
X_TARGET_MIN = 0.22
X_TARGET_MAX = 0.42
Y_TARGET_MIN = -0.2
Y_TARGET_MAX = 0.2
Z_TARGET_MIN = 0.1
Z_TARGET_MAX = 0.4

# === 全局变量存储最新IMU数据 ===
imu_data_lock = threading.Lock()

# IMU欧拉角数据（度）
imu1_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
imu2_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
imu3_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}

# IMU最后更新时间戳
imu1_last_update = 0.0
imu2_last_update = 0.0
imu3_last_update = 0.0

# Yaw归零偏移量
imu1_yaw_offset = None
imu2_yaw_offset = None
imu3_yaw_offset = None

# 首次数据标志（用于打印调试信息）
imu1_first_valid_data = False
imu2_first_valid_data = False
imu3_first_valid_data = False

# 首次有效数据记录（用于程序结束时回顾）
imu1_first_data = None
imu2_first_data = None
imu3_first_data = None

# 轨迹记录
trajectory_positions = deque(maxlen=1000)
trajectory_timestamps = deque(maxlen=1000)


def normalize_angle(angle):
    """将角度归一化到 [-180, 180] 范围"""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def normalize_yaw_angle(yaw_raw, yaw_offset, imu_name="IMU"):
    """
    归一化Yaw角到0附近的正常范围（借鉴dual_imu_euler.py）
    
    模式说明：
    - NORMAL: 首次有效数据归零模式，第一帧记录偏置并归零，后续帧减去偏置，保持在[-180°, +180°]
    - AUTO: 智能偏置模式，自动检测初始化位置（0附近或180附近），智能设置偏置
    - SIMPLE: 简单模式，直接将超过±100°的值翻转180°
    - OFF: 不进行归零，直接返回原始值
    
    参数:
        yaw_raw: 原始Yaw角（-180° ~ +180°）
        yaw_offset: 初始偏置（None表示第一帧，需要记录）
        imu_name: IMU名称（用于调试输出）
    
    返回:
        yaw_normalized: 归一化后的Yaw角
        new_offset: 更新后的偏置（仅AUTO和NORMAL模式下有效）
    """
    # OFF模式：不归零
    if YAW_NORMALIZATION_MODE == "OFF":
        if yaw_raw < 0:
            yaw_raw += 180
        elif yaw_raw > 0:
            yaw_raw -= 180
        return yaw_raw, 0.0
    
    # SIMPLE模式：简单翻转
    if YAW_NORMALIZATION_MODE == "SIMPLE":
        yaw_normalized = yaw_raw
        # 如果超过±100°，直接加减180°翻转到另一侧
        if yaw_raw > YAW_NORMALIZATION_THRESHOLD:
            yaw_normalized = yaw_raw - 180.0
        elif yaw_raw < -YAW_NORMALIZATION_THRESHOLD:
            yaw_normalized = yaw_raw + 180.0
        return yaw_normalized, 0.0
    
    # NORMAL模式：首次数据归零（推荐）
    if YAW_NORMALIZATION_MODE == "NORMAL":
        # 第一帧：记录偏置
        if yaw_offset is None:
            yaw_offset = yaw_raw
            print(f"🔧 [{imu_name}] [NORMAL] 首次Yaw数据归零: 原始值={yaw_raw:.2f}°, 偏置={yaw_offset:.2f}°")
            return 0.0, yaw_offset  # 第一帧归零
        
        # 后续帧：减去偏置
        yaw_normalized = yaw_raw - yaw_offset
        
        # 处理跨越±180°边界的情况，保持在[-180°, +180°]
        if yaw_normalized > 180.0:
            yaw_normalized -= 360.0
        elif yaw_normalized < -180.0:
            yaw_normalized += 360.0
        
        return yaw_normalized, yaw_offset
    
    # AUTO模式：智能偏置
    # 第一帧：记录初始偏置
    if yaw_offset is None:
        # 如果初始值接近±180°，说明初始化在180附近
        if abs(yaw_raw) > YAW_NORMALIZATION_THRESHOLD:
            # 偏置设为±180°，归一化后从0开始
            yaw_offset = 180.0 if yaw_raw > 0 else -180.0
            print(f"🔧 [{imu_name}] [AUTO] 检测到Yaw初始化在边界附近: 原始值={yaw_raw:.2f}°, 偏置={yaw_offset:.2f}°")
        else:
            # 偏置设为当前值，归一化后从0开始
            yaw_offset = yaw_raw
            print(f"🔧 [{imu_name}] [AUTO] 检测到Yaw初始化在0附近: 原始值={yaw_raw:.2f}°, 偏置={yaw_offset:.2f}°")
        
        return 0.0, yaw_offset  # 第一帧归零
    
    # 后续帧：减去偏置
    yaw_normalized = yaw_raw - yaw_offset
    
    # 处理跨越±180°边界的情况
    if yaw_normalized > 180.0:
        yaw_normalized -= 360.0
    elif yaw_normalized < -180.0:
        yaw_normalized += 360.0
    
    return yaw_normalized, yaw_offset


def calculate_end_effector_position(euler1, euler2):
    """
    计算两杆串联机械臂的末端位置（完整3D运动学，借鉴dual_imu_euler.py）
    
    参数：
        euler1: IMU1的欧拉角字典 {"roll": ..., "pitch": ..., "yaw": ...} (度)
        euler2: IMU2的欧拉角字典 {"roll": ..., "pitch": ..., "yaw": ...} (度)
    
    返回：
        end_pos: 末端位置 [x, y, z]（米）
        link1_pos: 杆1末端位置 [x, y, z]（米）
        link2_pos: 杆2末端位置 [x, y, z]（米）
    
    公式:
        末端位置 = R1 @ [L1, 0, 0]^T + R2 @ [L2, 0, 0]^T
        其中 R1, R2 是由欧拉角 (XYZ顺序) 构建的旋转矩阵
    """
    # 将欧拉角从度转换为弧度
    roll1_rad = np.deg2rad(euler1["roll"])
    pitch1_rad = np.deg2rad(euler1["pitch"])
    yaw1_rad = np.deg2rad(euler1["yaw"])
    
    roll2_rad = np.deg2rad(euler2["roll"])
    pitch2_rad = np.deg2rad(euler2["pitch"])
    yaw2_rad = np.deg2rad(euler2["yaw"])
    
    # 构建旋转矩阵 (使用XYZ欧拉角顺序，与IMU输出一致)
    R1 = Rotation.from_euler('xyz', [roll1_rad, pitch1_rad, yaw1_rad]).as_matrix()
    R2 = Rotation.from_euler('xyz', [roll2_rad, pitch2_rad, yaw2_rad]).as_matrix()
    
    # 杆1和杆2在各自局部坐标系下的向量 (沿x轴)
    link1_local = np.array([L1, 0.0, 0.0])
    link2_local = np.array([L2, 0.0, 0.0])
    
    # 转换到世界坐标系
    link1_world = R1 @ link1_local
    link2_world = R2 @ link2_local
    
    # 末端位置 = 杆1末端 + 杆2末端
    end_pos = link1_world + link2_world
    
    return end_pos, link1_world, link2_world


def data_callback(DeviceModel):
    """
    RS485数据回调函数
    当接收到IMU数据时被调用
    """
    global imu1_euler, imu2_euler, imu3_euler
    global imu1_last_update, imu2_last_update, imu3_last_update
    global imu1_yaw_offset, imu2_yaw_offset, imu3_yaw_offset
    global imu1_first_valid_data, imu2_first_valid_data, imu3_first_valid_data
    global imu1_first_data, imu2_first_data, imu3_first_data
    
    data = DeviceModel.deviceData
    current_time = time.time()
    
    with imu_data_lock:
        # 处理IMU1 (0x50 = 80)
        if 80 in data:
            device_data = data[80]
            
            # 提取欧拉角（度）
            roll = device_data.get('AngX', 0.0)
            pitch = device_data.get('AngY', 0.0)
            yaw = device_data.get('AngZ', 0.0)
            
            # 只处理有效数据（跳过全0数据）
            if abs(roll) > 0.01 or abs(pitch) > 0.01 or abs(yaw) > 0.01:
                # 打印第一次有效数据
                if not imu1_first_valid_data:
                    imu1_first_data = {"roll": roll, "pitch": pitch, "yaw": yaw}
                    print(f"📍 [IMU1] 首次有效数据: Roll={roll:.2f}°, Pitch={pitch:.2f}°, Yaw={yaw:.2f}°")
                    imu1_first_valid_data = True
                
                # Yaw归零处理（借鉴dual_imu_euler.py的智能归零）
                yaw_normalized, imu1_yaw_offset = normalize_yaw_angle(yaw, imu1_yaw_offset, "IMU1")
                
                imu1_euler = {"roll": roll, "pitch": pitch, "yaw": yaw_normalized}
                imu1_last_update = current_time
        
        # 处理IMU2 (0x51 = 81)
        if 81 in data:
            device_data = data[81]
            
            roll = device_data.get('AngX', 0.0)
            pitch = device_data.get('AngY', 0.0)
            yaw = device_data.get('AngZ', 0.0)
            
            # 只处理有效数据（跳过全0数据）
            if abs(roll) > 0.01 or abs(pitch) > 0.01 or abs(yaw) > 0.01:
                # 打印第一次有效数据
                if not imu2_first_valid_data:
                    imu2_first_data = {"roll": roll, "pitch": pitch, "yaw": yaw}
                    print(f"📍 [IMU2] 首次有效数据: Roll={roll:.2f}°, Pitch={pitch:.2f}°, Yaw={yaw:.2f}°")
                    imu2_first_valid_data = True
                
                # Yaw归零处理（借鉴dual_imu_euler.py的智能归零）
                yaw_normalized, imu2_yaw_offset = normalize_yaw_angle(yaw, imu2_yaw_offset, "IMU2")
                
                imu2_euler = {"roll": roll, "pitch": pitch, "yaw": yaw_normalized}
                imu2_last_update = current_time
        
        # 处理IMU3 (0x52 = 82)
        if 82 in data:
            device_data = data[82]
            
            roll = device_data.get('AngX', 0.0)
            pitch = device_data.get('AngY', 0.0)
            yaw = device_data.get('AngZ', 0.0)
            
            # 只处理有效数据（跳过全0数据）
            if abs(roll) > 0.01 or abs(pitch) > 0.01 or abs(yaw) > 0.01:
                # 打印第一次有效数据
                if not imu3_first_valid_data:
                    imu3_first_data = {"roll": roll, "pitch": pitch, "yaw": yaw}
                    print(f"📍 [IMU3] 首次有效数据: Roll={roll:.2f}°, Pitch={pitch:.2f}°, Yaw={yaw:.2f}°")
                    imu3_first_valid_data = True
                
                # Yaw归零处理（借鉴dual_imu_euler.py的智能归零）
                yaw_normalized, imu3_yaw_offset = normalize_yaw_angle(yaw, imu3_yaw_offset, "IMU3")
                
                imu3_euler = {"roll": roll, "pitch": pitch, "yaw": yaw_normalized}
                imu3_last_update = current_time


def publisher_loop(pub_socket, publish_interval, online_only=False):
    """
    ZeroMQ发布循环
    
    参数：
        pub_socket: ZeroMQ PUB socket
        publish_interval: 发布间隔（秒）
        online_only: 是否仅在三个IMU都在线时发布
    """
    print("\n" + "="*70)
    print("ZeroMQ发布器已启动（三IMU RS485模式）")
    print("="*70)
    print(f"发布地址: {pub_socket.getsockopt_string(zmq.LAST_ENDPOINT)}")
    print(f"发布频率: {1.0/publish_interval:.1f} Hz (间隔 {publish_interval*1000:.0f} ms)")
    print(f"在线检查: {'启用（仅在三个IMU都在线时发布）' if online_only else '禁用（始终发布）'}")
    print(f"缓冲策略: Latest-only（无缓冲队列）")
    print("="*70 + "\n")
    
    publish_count = 0
    skip_count = 0
    last_stat_time = time.time()
    
    try:
        while True:
            loop_start = time.time()
            
            # === 步骤1: 检查三个IMU在线状态 ===
            current_time = time.time()
            imu1_online = (current_time - imu1_last_update) < 1.0 if imu1_last_update > 0 else False
            imu2_online = (current_time - imu2_last_update) < 1.0 if imu2_last_update > 0 else False
            imu3_online = (current_time - imu3_last_update) < 1.0 if imu3_last_update > 0 else False
            
            # 如果启用了online_only模式，检查三个IMU是否都在线
            if online_only and not (imu1_online and imu2_online and imu3_online):
                skip_count += 1
                if skip_count % 25 == 0:  # 每5秒打印一次状态
                    print(f"⚠️  等待IMU在线... IMU1: {'✓' if imu1_online else '✗'}, "
                          f"IMU2: {'✓' if imu2_online else '✗'}, "
                          f"IMU3: {'✓' if imu3_online else '✗'} (已跳过 {skip_count} 次)")
                time.sleep(publish_interval)
                continue
            
            # === 步骤2: 读取最新IMU数据（带线程锁） ===
            with imu_data_lock:
                euler1 = imu1_euler.copy()
                euler2 = imu2_euler.copy()
                euler3 = imu3_euler.copy()
            
            # 计算机械臂末端位置
            try:
                end_pos, link1_pos, link2_pos = calculate_end_effector_position(euler1, euler2)
            except Exception as e:
                print(f"⚠️  运动学计算失败: {e}")
                end_pos = [0.0, 0.0, 0.0]
            
            # 记录轨迹
            trajectory_positions.append(end_pos.copy())
            trajectory_timestamps.append(current_time)
            
            # === 步骤3: 坐标映射和约束 ===
            # 约束到原始范围
            x_raw = np.clip(end_pos[0], X_RAW_MIN, X_RAW_MAX)
            y_raw = np.clip(end_pos[1], Y_RAW_MIN, Y_RAW_MAX)
            z_raw = np.clip(end_pos[2], Z_RAW_MIN, Z_RAW_MAX)
            
            # 线性映射到目标范围
            x_mapped = X_TARGET_MIN + (x_raw - X_RAW_MIN) / (X_RAW_MAX - X_RAW_MIN) * (X_TARGET_MAX - X_TARGET_MIN)
            y_mapped = Y_TARGET_MIN + (y_raw - Y_RAW_MIN) / (Y_RAW_MAX - Y_RAW_MIN) * (Y_TARGET_MAX - Y_TARGET_MIN)
            z_mapped = Z_TARGET_MIN + (z_raw - Z_RAW_MIN) / (Z_RAW_MAX - Z_RAW_MIN) * (Z_TARGET_MAX - Z_TARGET_MIN)
            
            # === 步骤4: 构造发布消息 ===
            message = {
                "position": [
                    float(x_mapped),  # x (米) - 映射后的值
                    float(y_mapped),  # y (米) - 映射后的值
                    float(z_mapped)   # z (米) - 映射后的值
                    # 0.0,  # x (米) - 暂时设为0
                    # 0.0,  # y (米) - 暂时设为0
                    # 0.0   # z (米) - 暂时设为0
                ],
                "orientation": [
                    float(np.deg2rad(euler3["roll"])),   # Roll（度→弧度）- IMU3机械爪欧拉角
                    float(np.deg2rad(euler3["pitch"])),  # Pitch（度→弧度）
                    float(np.deg2rad(euler3["yaw"]))     # Yaw（度→弧度）
                ],
                "gripper": 0.0,  # 夹爪状态（未实现，暂时设为0）
                "t": current_time  # 时间戳
            }
            
            # === 步骤5: 发送JSON消息 ===
            try:
                pub_socket.send_string(json.dumps(message))
                publish_count += 1
            except Exception as e:
                print(f"❌ ZeroMQ发送失败: {e}")

            # === 步骤6: 定期打印统计信息（每0.3秒） ===
            if current_time - last_stat_time >= 0.3:
                actual_rate = publish_count / (current_time - last_stat_time) if publish_count > 0 else 0.0
                
                # 清屏效果（可选）
                print("\033[H\033[J", end="")  # ANSI转义码清屏
                
                # === IMU原始数据显示（借鉴dual_imu_euler.py格式） ===
                print("┌" + "─"*68 + "┐")
                print(f"│ IMU 1 (杆1) - 地址: 0x{IMU1_ADDR:02X} ({IMU1_ADDR})".ljust(69) + "│")
                status1_text = "✅ 在线" if imu1_online else "⚠️  离线"
                print(f"│ 状态: {status1_text}  │  长度: {L1*1000:.0f} mm  │  归零模式: {YAW_NORMALIZATION_MODE}".ljust(85) + "│")
                yaw1_offset_str = f"(偏移:{imu1_yaw_offset:.2f}°)" if imu1_yaw_offset is not None else "(未归零)"
                print(f"│ Roll  = {euler1['roll']:8.2f}°  │  Pitch = {euler1['pitch']:8.2f}°  │  Yaw = {euler1['yaw']:8.2f}° {yaw1_offset_str}".ljust(97) + "│")
                print("├" + "─"*68 + "┤")
                
                print(f"│ IMU 2 (杆2) - 地址: 0x{IMU2_ADDR:02X} ({IMU2_ADDR})".ljust(69) + "│")
                status2_text = "✅ 在线" if imu2_online else "⚠️  离线"
                print(f"│ 状态: {status2_text}  │  长度: {L2*1000:.0f} mm".ljust(69) + "│")
                yaw2_offset_str = f"(偏移:{imu2_yaw_offset:.2f}°)" if imu2_yaw_offset is not None else "(未归零)"
                print(f"│ Roll  = {euler2['roll']:8.2f}°  │  Pitch = {euler2['pitch']:8.2f}°  │  Yaw = {euler2['yaw']:8.2f}° {yaw2_offset_str}".ljust(97) + "│")
                print("├" + "─"*68 + "┤")
                
                print(f"│ IMU 3 (机械爪) - 地址: 0x{IMU3_ADDR:02X} ({IMU3_ADDR})".ljust(69) + "│")
                status3_text = "✅ 在线" if imu3_online else "⚠️  离线"
                print(f"│ 状态: {status3_text}".ljust(69) + "│")
                yaw3_offset_str = f"(偏移:{imu3_yaw_offset:.2f}°)" if imu3_yaw_offset is not None else "(未归零)"
                print(f"│ Roll  = {euler3['roll']:8.2f}°  │  Pitch = {euler3['pitch']:8.2f}°  │  Yaw = {euler3['yaw']:8.2f}° {yaw3_offset_str}".ljust(97) + "│")
                print("└" + "─"*68 + "┘")
                
                # === 末端位置和ZeroMQ发布信息 ===
                print("\n┌" + "─"*68 + "┐")
                print(f"│ 机械臂末端位置 & ZeroMQ发布状态".ljust(69) + "│")
                print("├" + "─"*68 + "┤")
                print(f"│ 原始位置: [{end_pos[0]:7.3f}, {end_pos[1]:7.3f}, {end_pos[2]:7.3f}] m".ljust(69) + "│")
                print(f"│ 映射位置: [{x_mapped:7.3f}, {y_mapped:7.3f}, {z_mapped:7.3f}] m".ljust(69) + "│")
                
                # 计算发送的orientation值（弧度）
                sent_roll = float(np.deg2rad(euler3["roll"]))
                sent_pitch = float(np.deg2rad(euler3["pitch"]))
                sent_yaw = float(np.deg2rad(euler3["yaw"]))
                print(f"│ 发送姿态: Roll={sent_roll:7.4f} rad, Pitch={sent_pitch:7.4f} rad, Yaw={sent_yaw:7.4f} rad".ljust(84) + "│")
                print(f"│ 发布频率: {actual_rate:.1f} Hz  │  消息数: {publish_count}".ljust(69) + "│")
                print("└" + "─"*68 + "┘\n")
                
                publish_count = 0
                last_stat_time = current_time
            
            # === 步骤7: 精确定时控制 ===
            elapsed = time.time() - loop_start
            to_sleep = max(0.0, publish_interval - elapsed)
            time.sleep(to_sleep)
            
    except KeyboardInterrupt:
        print(f"\n📊 发布器已停止 | 总发布: {publish_count} 条消息")
        raise


def plot_trajectory():
    """
    绘制机械臂末端的3D运动轨迹
    借鉴dual_imu_euler.py的完整绘图功能
    """
    if len(trajectory_positions) == 0:
        print("没有记录到轨迹数据")
        return
    
    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        import matplotlib
        
        # 设置中文字体（避免中文显示为方框）
        matplotlib.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial Unicode MS', 'SimHei']
        matplotlib.rcParams['axes.unicode_minus'] = False
        
    except ImportError:
        print("⚠️  matplotlib未安装，无法绘制轨迹图")
        return
    
    print("\n" + "="*70)
    print("正在生成3D轨迹图...")
    print("="*70)
    
    try:
        # 转换为numpy数组便于处理
        trajectory_array = np.array(list(trajectory_positions))
        timestamps_array = np.array(list(trajectory_timestamps))
        
        # 创建3D图形（2x3布局，与dual_imu_euler.py一致）
        fig = plt.figure(figsize=(18, 10))
        
        # === 子图1: 3D轨迹 ===
        ax1 = fig.add_subplot(2, 3, 1, projection='3d')
        ax1.plot(trajectory_array[:, 0], trajectory_array[:, 1], trajectory_array[:, 2], 
                 'b-', linewidth=1.5, alpha=0.6, label='Trajectory')
        ax1.scatter(trajectory_array[0, 0], trajectory_array[0, 1], trajectory_array[0, 2], 
                    c='green', s=100, marker='o', label='Start')
        ax1.scatter(trajectory_array[-1, 0], trajectory_array[-1, 1], trajectory_array[-1, 2], 
                    c='red', s=100, marker='x', label='End')
        
        # 绘制原点
        ax1.scatter([0], [0], [0], c='black', s=100, marker='o', label='Origin')
        
        ax1.set_xlabel('X (m)', fontsize=10)
        ax1.set_ylabel('Y (m)', fontsize=10)
        ax1.set_zlabel('Z (m)', fontsize=10)
        ax1.set_title('End-Effector 3D Trajectory (RS485)', fontsize=12, fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # === 子图2: XY平面投影 ===
        ax2 = fig.add_subplot(2, 3, 2)
        ax2.plot(trajectory_array[:, 0], trajectory_array[:, 1], 'b-', linewidth=1.5, alpha=0.6)
        ax2.scatter(trajectory_array[0, 0], trajectory_array[0, 1], c='green', s=100, marker='o', label='Start')
        ax2.scatter(trajectory_array[-1, 0], trajectory_array[-1, 1], c='red', s=100, marker='x', label='End')
        ax2.scatter([0], [0], c='black', s=50, marker='o', label='Origin')
        ax2.set_xlabel('X (m)', fontsize=10)
        ax2.set_ylabel('Y (m)', fontsize=10)
        ax2.set_title('XY Plane Projection (Top View)', fontsize=12, fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.axis('equal')
        
        # === 子图3: XZ平面投影 ===
        ax3 = fig.add_subplot(2, 3, 3)
        ax3.plot(trajectory_array[:, 0], trajectory_array[:, 2], 'b-', linewidth=1.5, alpha=0.6)
        ax3.scatter(trajectory_array[0, 0], trajectory_array[0, 2], c='green', s=100, marker='o', label='Start')
        ax3.scatter(trajectory_array[-1, 0], trajectory_array[-1, 2], c='red', s=100, marker='x', label='End')
        ax3.scatter([0], [0], c='black', s=50, marker='o', label='Origin')
        ax3.set_xlabel('X (m)', fontsize=10)
        ax3.set_ylabel('Z (m)', fontsize=10)
        ax3.set_title('XZ Plane Projection (Side View)', fontsize=12, fontweight='bold')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        ax3.axis('equal')
        
        # === 子图4: YZ平面投影 ===
        ax4 = fig.add_subplot(2, 3, 4)
        ax4.plot(trajectory_array[:, 1], trajectory_array[:, 2], 'b-', linewidth=1.5, alpha=0.6)
        ax4.scatter(trajectory_array[0, 1], trajectory_array[0, 2], c='green', s=100, marker='o', label='Start')
        ax4.scatter(trajectory_array[-1, 1], trajectory_array[-1, 2], c='red', s=100, marker='x', label='End')
        ax4.scatter([0], [0], c='black', s=50, marker='o', label='Origin')
        ax4.set_xlabel('Y (m)', fontsize=10)
        ax4.set_ylabel('Z (m)', fontsize=10)
        ax4.set_title('YZ Plane Projection (Front View)', fontsize=12, fontweight='bold')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        ax4.axis('equal')
        
        # === 子图5: 位置随时间变化 ===
        ax5 = fig.add_subplot(2, 3, (5, 6))
        ax5.plot(timestamps_array, trajectory_array[:, 0], 'r-', linewidth=1.5, label='X', alpha=0.7)
        ax5.plot(timestamps_array, trajectory_array[:, 1], 'g-', linewidth=1.5, label='Y', alpha=0.7)
        ax5.plot(timestamps_array, trajectory_array[:, 2], 'b-', linewidth=1.5, label='Z', alpha=0.7)
        ax5.set_xlabel('Time (s)', fontsize=10)
        ax5.set_ylabel('Position (m)', fontsize=10)
        ax5.set_title('Position vs Time', fontsize=12, fontweight='bold')
        ax5.legend()
        ax5.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # === 统计信息（借鉴dual_imu_euler.py） ===
        print(f"\n轨迹统计:")
        print(f"  总点数: {len(trajectory_positions)}")
        
        if len(timestamps_array) > 1:
            duration = timestamps_array[-1] - timestamps_array[0]
            print(f"  持续时间: {duration:.2f} 秒")
            if duration > 0:
                print(f"  采样频率: {len(trajectory_positions) / duration:.1f} Hz")
        
        # 计算轨迹总长度
        total_distance = 0
        for i in range(1, len(trajectory_array)):
            total_distance += np.linalg.norm(trajectory_array[i] - trajectory_array[i-1])
        print(f"  轨迹总长度: {total_distance:.4f} m ({total_distance*1000:.1f} mm)")
        
        # 位置范围
        print(f"\n位置范围:")
        print(f"  X: [{trajectory_array[:, 0].min():.4f}, {trajectory_array[:, 0].max():.4f}] m")
        print(f"  Y: [{trajectory_array[:, 1].min():.4f}, {trajectory_array[:, 1].max():.4f}] m")
        print(f"  Z: [{trajectory_array[:, 2].min():.4f}, {trajectory_array[:, 2].max():.4f}] m")
        
        # 保存图像
        plt.savefig('trajectory_rs485.png', dpi=150, bbox_inches='tight')
        print("\n✓ 轨迹图已保存到 trajectory_rs485.png")
        
        # 尝试显示（如果在图形环境中）
        try:
            plt.show()
        except:
            print("✓ 图表已生成（非交互环境，仅保存文件）")
        
        print("="*70)
        
    except Exception as e:
        print(f"⚠️  绘制轨迹图失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="三IMU机械臂ZeroMQ发布器 (RS485版本) - 将双杆机械臂位置和机械爪姿态发布到MuJoCo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  # 使用默认参数（5Hz发布到localhost:5555）
  python triple_imu_rs485_publisher.py
  
  # 仅在三个IMU都在线时发布（推荐）
  python triple_imu_rs485_publisher.py --online-only
  
  # 自定义串口和发布频率
  python triple_imu_rs485_publisher.py --port /dev/ttyUSB0 --baud 9600 --interval 0.1 --online-only
  
  # 绑定到所有网络接口
  python triple_imu_rs485_publisher.py --bind tcp://0.0.0.0:5555 --online-only

重要说明：
  - IMU1 (0x50): 杆1，用于计算末端位置
  - IMU2 (0x51): 杆2，用于计算末端位置
  - IMU3 (0x52): 机械爪，提供姿态信息
  - position: 由IMU1和IMU2计算的机械臂末端位置（经过坐标映射）
  - orientation: 直接使用IMU3的欧拉角（机械爪姿态）
  - gripper: 夹爪开合状态（暂未实现，固定为0）

MuJoCo接收端：
  接收到的数据格式：
    {
      "position": [x, y, z],           // 末端位置（米）
      "orientation": [roll, pitch, yaw], // 机械爪姿态（度）
      "gripper": 0.0,
      "t": 1234567890.123
    }
        """
    )
    parser.add_argument("--port", "-p", type=str, default="/dev/ttyUSB0",
                        help="RS485串口设备路径，默认/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200,
                        help="波特率，默认115200")
    parser.add_argument("--interval", "-i", type=float, default=DEFAULT_PUBLISH_INTERVAL,
                        help="发布间隔（秒），默认0.2（5Hz）")
    parser.add_argument("--bind", "-b", type=str, default=DEFAULT_BIND_ADDRESS,
                        help="ZeroMQ绑定地址，默认tcp://127.0.0.1:5555")
    parser.add_argument("--online-only", action="store_true",
                        help="仅在三个IMU都在线时发布数据（推荐启用）")
    
    args = parser.parse_args()
    
    print("="*70)
    print("三IMU机械臂ZeroMQ发布器（RS485版本 - 双杆 + 机械爪）")
    print("="*70)
    print(f"串口设备: {args.port}")
    print(f"波特率: {args.baud}")
    print(f"IMU 1 (杆1): 地址 0x50 (80)")
    print(f"IMU 2 (杆2): 地址 0x51 (81)")
    print(f"IMU 3 (机械爪): 地址 0x52 (82)")
    print(f"杆1长度: {L1*1000:.0f} mm")
    print(f"杆2长度: {L2*1000:.0f} mm")
    print(f"Yaw归零模式: {YAW_NORMALIZATION_MODE}")
    print("="*70 + "\n")
    
    # 创建ZeroMQ上下文
    zmq_context = zmq.Context()
    pub_socket = zmq_context.socket(zmq.PUB)
    
    # RS485设备对象
    rs485_device = None
    
    try:
        # 绑定ZeroMQ
        pub_socket.bind(args.bind)
        print(f"✓ ZeroMQ PUB socket已绑定到 {args.bind}")
        print("  等待订阅者连接...\n")
        
        time.sleep(0.5)
        
        # 初始化RS485设备
        print("正在初始化RS485设备...")
        addrLis = [IMU1_ADDR, IMU2_ADDR, IMU3_ADDR]
        rs485_device = device_model.DeviceModel(
            "三IMU机械臂",
            args.port,
            args.baud,
            addrLis,
            data_callback
        )
        
        # 打开设备
        rs485_device.openDevice()
        
        if not rs485_device.isOpen:
            print("❌ 无法打开RS485设备，程序退出")
            return
        
        print("✓ RS485设备已打开\n")
        
        # 开启循环读取
        rs485_device.startLoopRead()
        print("✓ IMU数据采集已启动\n")
        
        # 等待所有IMU完成Yaw归零
        print("等待IMU归零...")
        while imu1_yaw_offset is None or imu2_yaw_offset is None or imu3_yaw_offset is None:
            time.sleep(0.1)
        print("✓ 所有IMU已完成Yaw归零\n")
        
        # 启动ZeroMQ发布循环
        print("✓ 所有任务已启动，按Ctrl+C停止\n")
        publisher_loop(pub_socket, args.interval, args.online_only)
        
    except KeyboardInterrupt:
        print("\n\n✓ 程序已被用户中断")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n正在清理资源...")
        
        # 停止RS485设备
        if rs485_device and rs485_device.isOpen:
            print("正在停止IMU数据采集...")
            rs485_device.stopLoopRead()
            time.sleep(0.5)
            rs485_device.closeDevice()
            print("✓ RS485设备已关闭")
        
        # 关闭ZeroMQ
        print("正在关闭ZeroMQ连接...")
        pub_socket.close()
        zmq_context.term()
        print("✓ ZeroMQ连接已关闭")
        
        print("已断开所有连接")
        
        # === 打印首次有效数据回顾 ===
        print("\n" + "="*70)
        print("首次有效数据回顾")
        print("="*70)
        if imu1_first_data:
            print(f"[IMU1] Roll={imu1_first_data['roll']:8.2f}°, Pitch={imu1_first_data['pitch']:8.2f}°, Yaw={imu1_first_data['yaw']:8.2f}°")
        else:
            print("[IMU1] 未收到有效数据")
        
        if imu2_first_data:
            print(f"[IMU2] Roll={imu2_first_data['roll']:8.2f}°, Pitch={imu2_first_data['pitch']:8.2f}°, Yaw={imu2_first_data['yaw']:8.2f}°")
        else:
            print("[IMU2] 未收到有效数据")
        
        if imu3_first_data:
            print(f"[IMU3] Roll={imu3_first_data['roll']:8.2f}°, Pitch={imu3_first_data['pitch']:8.2f}°, Yaw={imu3_first_data['yaw']:8.2f}°")
        else:
            print("[IMU3] 未收到有效数据")
        print("="*70)
        
        # 绘制轨迹
        if len(trajectory_positions) > 0:
            print("\n正在生成轨迹图...")
            plot_trajectory()
        else:
            print("\n未记录到轨迹数据")


if __name__ == '__main__':
    main()
