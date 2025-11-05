#!/usr/bin/env python
# coding:UTF-8
"""
双IMU欧拉角读取程序 + 机械臂末端位置计算
同时连接两个WT901BLE陀螺仪，实时显示它们的欧拉角（Roll, Pitch, Yaw）
并计算两杆串联机械臂的末端位置

机械臂模型:
    基座 ──[杆1(IMU1)]── 关节 ──[杆2(IMU2)]── 末端
    
    末端位置 = R1 @ [L1, 0, 0]^T + R2 @ [L2, 0, 0]^T
    其中 R1, R2 是由各自IMU欧拉角构建的旋转矩阵
"""
import asyncio
import bleak
import numpy as np
import time
from scipy.spatial.transform import Rotation
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

# === 配置参数 ===
# 两个IMU的MAC地址
IMU1_MAC = "D1:77:C2:AD:5D:07"  # 第一个IMU的MAC地址（杆1）
IMU2_MAC = "F5:6D:DE:5C:77:B0"  # 第二个IMU的MAC地址（杆2，需要修改）

# 机械臂几何参数
L1 = 0.25  # 杆1的长度 (米)
L2 = 0.27  # 杆2的长度 (米)

# BLE服务和特征UUID
TARGET_SERVICE_UUID = "0000ffe5-0000-1000-8000-00805f9a34fb"
TARGET_CHARACTERISTIC_UUID_READ = "0000ffe4-0000-1000-8000-00805f9a34fb"
TARGET_CHARACTERISTIC_UUID_WRITE = "0000ffe9-0000-1000-8000-00805f9a34fb"

# 刷新率控制
DISPLAY_INTERVAL = 0.2  # 每0.2秒显示一次（5Hz）

# Yaw角自动归零参数
YAW_NORMALIZATION_THRESHOLD = 100.0  # Yaw角超过±100度时自动归零到0附近
YAW_NORMALIZATION_MODE = "OFF"  # "AUTO": 智能偏置模式, "SIMPLE": 简单±180翻转模式, "OFF": 不归零

# === 全局变量 ===
# 存储两个IMU的最新欧拉角
imu1_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
imu2_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}

# Yaw角初始偏置（第一帧自动记录）
imu1_yaw_offset = None
imu2_yaw_offset = None
imu1_raw_yaw_first = None  # 调试：记录第一帧原始Yaw值
imu2_raw_yaw_first = None  # 调试：记录第一帧原始Yaw值
imu1_frame_count = 0  # 帧计数器，跳过初始的无效帧
imu2_frame_count = 0  # 帧计数器，跳过初始的无效帧
SKIP_INITIAL_FRAMES = 5  # 跳过前5帧数据，等IMU稳定

# 数据缓冲区（每个IMU独立）
imu1_buffer = []
imu2_buffer = []

# 时间戳
imu1_last_update = 0
imu2_last_update = 0

# === 轨迹记录 ===
trajectory_positions = []  # 存储末端位置 [[x, y, z], ...]
trajectory_timestamps = []  # 存储时间戳
trajectory_link1 = []  # 存储杆1末端位置
trajectory_link2 = []  # 存储杆2末端位置
trajectory_start_time = None


def parse_imu_packet(bytes_data):
    """
    解析20字节的IMU数据包，提取欧拉角
    
    返回: (roll, pitch, yaw) 单位：度
    """
    # 只处理0x61类型的数据（加速度+角速度+角度）
    if len(bytes_data) < 20 or bytes_data[1] != 0x61:
        return None
    
    def getSignInt16(num):
        if num >= pow(2, 15):
            num -= pow(2, 16)
        return num
    
    # 提取欧拉角（字节14-19）
    roll = getSignInt16(bytes_data[15] << 8 | bytes_data[14]) / 32768 * 180
    pitch = getSignInt16(bytes_data[17] << 8 | bytes_data[16]) / 32768 * 180
    yaw = getSignInt16(bytes_data[19] << 8 | bytes_data[18]) / 32768 * 180
    
    return roll, pitch, yaw


def normalize_yaw_angle(yaw_raw, yaw_offset):
    """
    归一化Yaw角到0附近的正常范围
    
    模式说明：
    - AUTO: 智能偏置模式，第一帧记录偏置，后续帧减去偏置
    - SIMPLE: 简单模式，直接将超过±100°的值翻转180°
    - OFF: 不进行归零，直接返回原始值
    
    参数:
        yaw_raw: 原始Yaw角（-180° ~ +180°）
        yaw_offset: 初始偏置（None表示第一帧，需要记录）
    
    返回:
        yaw_normalized: 归一化后的Yaw角
        new_offset: 更新后的偏置（仅AUTO模式下有效）
    """
    # OFF模式：不归零
    if YAW_NORMALIZATION_MODE == "OFF":
        if yaw_raw <0:
            yaw_raw+=180

        elif yaw_raw>0:
            yaw_raw-=180    

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
    
    # AUTO模式：智能偏置（默认）
    # 第一帧：记录初始偏置
    if yaw_offset is None:
        # 如果初始值接近±180°，说明初始化在180附近
        if abs(yaw_raw) > YAW_NORMALIZATION_THRESHOLD:
            # 偏置设为±180°，归一化后从0开始
            yaw_offset = 180.0 if yaw_raw > 0 else -180.0
            print(f"🔧 [AUTO] 检测到Yaw初始化在边界附近: 原始值={yaw_raw:.2f}°, 偏置={yaw_offset:.2f}°")
        else:
            # 偏置设为当前值，归一化后从0开始
            yaw_offset = yaw_raw
            print(f"🔧 [AUTO] 检测到Yaw初始化在0附近: 原始值={yaw_raw:.2f}°, 偏置={yaw_offset:.2f}°")
        
        return 0.0, yaw_offset  # 第一帧归零
    
    # 后续帧：减去偏置
    yaw_normalized = yaw_raw - yaw_offset
    
    # 处理跨越±180°边界的情况
    if yaw_normalized > 180.0:
        yaw_normalized -= 360.0
    elif yaw_normalized < -180.0:
        yaw_normalized += 360.0
    
    return yaw_normalized, yaw_offset


# === IMU1 数据接收回调 ===
def on_imu1_data_received(sender, data):
    """处理IMU1的数据"""
    global imu1_buffer, imu1_euler, imu1_last_update, imu1_yaw_offset, imu1_raw_yaw_first, imu1_frame_count
    
    tempdata = bytes.fromhex(data.hex())
    for byte_val in tempdata:
        imu1_buffer.append(byte_val)
        
        # 帧头校验
        if len(imu1_buffer) == 1 and imu1_buffer[0] != 0x55:
            del imu1_buffer[0]
            continue
        
        # 帧类型校验
        if len(imu1_buffer) == 2 and (imu1_buffer[1] != 0x61 and imu1_buffer[1] != 0x71):
            del imu1_buffer[0]
            continue
        
        # 收满20字节后处理
        if len(imu1_buffer) == 20:
            # 调试：打印数据包类型
            if imu1_buffer[0] == 0x55:
                packet_type = imu1_buffer[1]
                if packet_type != 0x61:
                    print(f"🔍 IMU1收到数据包类型: 0x{packet_type:02X} (期望0x61)")
            
            result = parse_imu_packet(imu1_buffer)
            if result:
                roll, pitch, yaw = result
                
                # 跳过前几帧无效数据（IMU初始化时返回0）
                imu1_frame_count += 1
                if imu1_frame_count <= SKIP_INITIAL_FRAMES:
                    imu1_buffer.clear()
                    return
                
                # 记录第一帧有效的原始Yaw值
                if imu1_raw_yaw_first is None:
                    imu1_raw_yaw_first = yaw
                
                # Yaw角归一化（自动处理0或180初始化的情况）
                yaw_normalized, imu1_yaw_offset = normalize_yaw_angle(yaw, imu1_yaw_offset)
                
                imu1_euler["roll"] = roll
                imu1_euler["pitch"] = pitch
                imu1_euler["yaw"] = yaw_normalized  # 使用归一化后的值
                imu1_last_update = time.time()
            imu1_buffer.clear()


# === IMU2 数据接收回调 ===
def on_imu2_data_received(sender, data):
    """处理IMU2的数据"""
    global imu2_buffer, imu2_euler, imu2_last_update, imu2_yaw_offset, imu2_raw_yaw_first, imu2_frame_count
    
    tempdata = bytes.fromhex(data.hex())
    for byte_val in tempdata:
        imu2_buffer.append(byte_val)
        
        # 帧头校验
        if len(imu2_buffer) == 1 and imu2_buffer[0] != 0x55:
            del imu2_buffer[0]
            continue
        
        # 帧类型校验
        if len(imu2_buffer) == 2 and (imu2_buffer[1] != 0x61 and imu2_buffer[1] != 0x71):
            del imu2_buffer[0]
            continue
        
        # 收满20字节后处理
        if len(imu2_buffer) == 20:
            result = parse_imu_packet(imu2_buffer)
            if result:
                roll, pitch, yaw = result
                
                # 跳过前几帧无效数据（IMU初始化时返回0）
                imu2_frame_count += 1
                if imu2_frame_count <= SKIP_INITIAL_FRAMES:
                    imu2_buffer.clear()
                    return
                
                # 记录第一帧有效的原始Yaw值
                if imu2_raw_yaw_first is None:
                    imu2_raw_yaw_first = yaw
                
                # Yaw角归一化（自动处理0或180初始化的情况）
                yaw_normalized, imu2_yaw_offset = normalize_yaw_angle(yaw, imu2_yaw_offset)
                
                imu2_euler["roll"] = roll
                imu2_euler["pitch"] = pitch
                imu2_euler["yaw"] = yaw_normalized  # 使用归一化后的值
                imu2_last_update = time.time()
            imu2_buffer.clear()


def calculate_end_effector_position(euler1, euler2):
    """
    计算两杆串联机械臂的末端位置
    
    参数:
        euler1: IMU1的欧拉角字典 {"roll": ..., "pitch": ..., "yaw": ...} (度)
        euler2: IMU2的欧拉角字典 {"roll": ..., "pitch": ..., "yaw": ...} (度)
    
    返回:
        end_position: 末端位置 [x, y, z] (米)
    
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
    end_position = link1_world + link2_world
    
    return end_position, link1_world, link2_world


async def display_euler_angles():
    """定时显示两个IMU的欧拉角和计算的末端位置"""
    global trajectory_positions, trajectory_timestamps, trajectory_link1, trajectory_link2, trajectory_start_time
    
    print("\n" + "="*70)
    print("开始实时显示欧拉角和末端位置 (按 Ctrl+C 停止)")
    print("="*70 + "\n")
    
    trajectory_start_time = time.time()
    
    try:
        while True:
            await asyncio.sleep(DISPLAY_INTERVAL)
            
            # 清屏效果（可选）
            print("\033[H\033[J", end="")  # ANSI转义码清屏
            
            current_time = time.time()
            
            # 显示IMU1
            time_diff1 = current_time - imu1_last_update if imu1_last_update > 0 else 999
            status1 = "✅ 在线" if time_diff1 < 1.0 else "⚠️  离线"
            
            print("┌" + "─"*68 + "┐")
            print(f"│ IMU 1 (杆1) - {IMU1_MAC}".ljust(69) + "│")
            print(f"│ 状态: {status1}  │  长度: {L1*1000:.0f} mm  │  归零模式: {YAW_NORMALIZATION_MODE}".ljust(85) + "│")
            if YAW_NORMALIZATION_MODE == "AUTO" and imu1_yaw_offset is not None and imu1_raw_yaw_first is not None:
                yaw1_offset_str = f"(原始:{imu1_raw_yaw_first:7.2f}° → 偏置:{imu1_yaw_offset:7.2f}°)"
            elif YAW_NORMALIZATION_MODE == "SIMPLE":
                yaw1_offset_str = "(SIMPLE模式)"
            elif YAW_NORMALIZATION_MODE == "OFF":
                yaw1_offset_str = "(未归零)"
            else:
                yaw1_offset_str = "(未初始化)"
            print(f"│ Roll  = {imu1_euler['roll']:8.2f}°  │  Pitch = {imu1_euler['pitch']:8.2f}°  │  Yaw = {imu1_euler['yaw']:8.2f}° {yaw1_offset_str}".ljust(105) + "│")
            print("├" + "─"*68 + "┤")
            
            # 显示IMU2
            time_diff2 = current_time - imu2_last_update if imu2_last_update > 0 else 999
            status2 = "✅ 在线" if time_diff2 < 1.0 else "⚠️  离线"
            
            print(f"│ IMU 2 (杆2) - {IMU2_MAC}".ljust(69) + "│")
            print(f"│ 状态: {status2}  │  长度: {L2*1000:.0f} mm".ljust(69) + "│")
            if YAW_NORMALIZATION_MODE == "AUTO" and imu2_yaw_offset is not None and imu2_raw_yaw_first is not None:
                yaw2_offset_str = f"(原始:{imu2_raw_yaw_first:7.2f}° → 偏置:{imu2_yaw_offset:7.2f}°)"
            elif YAW_NORMALIZATION_MODE == "SIMPLE":
                yaw2_offset_str = "(SIMPLE模式)"
            elif YAW_NORMALIZATION_MODE == "OFF":
                yaw2_offset_str = "(未归零)"
            else:
                yaw2_offset_str = "(未初始化)"
            print(f"│ Roll  = {imu2_euler['roll']:8.2f}°  │  Pitch = {imu2_euler['pitch']:8.2f}°  │  Yaw = {imu2_euler['yaw']:8.2f}° {yaw2_offset_str}".ljust(105) + "│")
            print("└" + "─"*68 + "┘")
            
            # 显示相对角度差
            roll_diff = abs(imu1_euler['roll'] - imu2_euler['roll'])
            pitch_diff = abs(imu1_euler['pitch'] - imu2_euler['pitch'])
            yaw_diff = abs(imu1_euler['yaw'] - imu2_euler['yaw'])
            
            print(f"\n📐 相对角度差: Roll={roll_diff:.2f}°  Pitch={pitch_diff:.2f}°  Yaw={yaw_diff:.2f}°")
            
            # 计算并显示末端位置
            end_pos, link1_pos, link2_pos = calculate_end_effector_position(imu1_euler, imu2_euler)
            
            # 记录轨迹数据
            if time_diff1 < 1.0 and time_diff2 < 1.0:  # 只有两个IMU都在线时才记录
                trajectory_positions.append(end_pos.copy())
                trajectory_link1.append(link1_pos.copy())
                trajectory_link2.append(link2_pos.copy())
                trajectory_timestamps.append(current_time - trajectory_start_time)
            
            print("\n" + "="*70)
            print("🎯 机械臂位置计算结果:")
            print("="*70)
            print(f"杆1末端位置 (R1@[L1,0,0]^T):  [{link1_pos[0]:7.4f}, {link1_pos[1]:7.4f}, {link1_pos[2]:7.4f}] m")
            print(f"杆2末端位置 (R2@[L2,0,0]^T):  [{link2_pos[0]:7.4f}, {link2_pos[1]:7.4f}, {link2_pos[2]:7.4f}] m")
            print(f"{'─'*70}")
            print(f"📍 末端总位置:                [{end_pos[0]:7.4f}, {end_pos[1]:7.4f}, {end_pos[2]:7.4f}] m")
            print(f"                              [{end_pos[0]*1000:7.1f}, {end_pos[1]*1000:7.1f}, {end_pos[2]*1000:7.1f}] mm")
            
            # 计算末端到原点的距离
            distance = np.linalg.norm(end_pos)
            print(f"📏 末端距离原点: {distance:.4f} m ({distance*1000:.1f} mm)")
            
            # 显示已记录的轨迹点数
            print(f"📊 已记录轨迹点: {len(trajectory_positions)} 个")
            
            print(f"\n⏱️  更新时间: {time.strftime('%H:%M:%S')}\n")

            
    except asyncio.CancelledError:
        pass


async def connect_imu(device, data_callback, imu_name="IMU"):
    """连接单个IMU设备并启动数据流（设备已预先搜索）"""
    if not device:
        print(f"❌ 未找到 {imu_name}，跳过连接")
        return
    
    try:
        print(f"正在连接 {imu_name} ({device.address})...")
        
        async with bleak.BleakClient(device, timeout=15) as client:
            print(f"✓ 已连接 {imu_name}")
            
            # 查找读取特征
            notify_characteristic = None
            for service in client.services:
                if service.uuid == TARGET_SERVICE_UUID:
                    for characteristic in service.characteristics:
                        if characteristic.uuid == TARGET_CHARACTERISTIC_UUID_READ:
                            notify_characteristic = characteristic
                            break
            
            if notify_characteristic:
                # 启动通知
                await client.start_notify(notify_characteristic.uuid, data_callback)
                print(f"✓ {imu_name} 数据流已启动\n")
                
                # 保持连接
                try:
                    while client.is_connected:
                        await asyncio.sleep(1)
                except asyncio.CancelledError:
                    pass
                finally:
                    await client.stop_notify(notify_characteristic.uuid)
            else:
                print(f"❌ {imu_name} 未找到数据特征")
                
    except Exception as e:
        print(f"❌ {imu_name} 连接错误: {e}")


async def main():
    """主函数：并发连接两个IMU"""
    print("="*70)
    print("双IMU欧拉角监控程序")
    print("="*70)
    print(f"IMU 1: {IMU1_MAC}")
    print(f"IMU 2: {IMU2_MAC}")
    print("="*70 + "\n")
    
    # === 步骤1: 依次搜索设备（避免蓝牙适配器冲突） ===
    print("🔍 开始搜索设备...")
    print(f"正在搜索 IMU1 ({IMU1_MAC})...")
    device1 = await bleak.BleakScanner.find_device_by_address(IMU1_MAC, timeout=20)
    if device1:
        print(f"✓ 找到 IMU1: {device1.name}")
    else:
        print(f"❌ 未找到 IMU1")
    
    print(f"\n正在搜索 IMU2 ({IMU2_MAC})...")
    device2 = await bleak.BleakScanner.find_device_by_address(IMU2_MAC, timeout=20)
    if device2:
        print(f"✓ 找到 IMU2: {device2.name}")
    else:
        print(f"❌ 未找到 IMU2")
    
    print("\n" + "="*70)
    
    # === 步骤2: 并发连接和数据采集 ===
    tasks = [
        asyncio.create_task(connect_imu(device1, on_imu1_data_received, "IMU1")),
        asyncio.create_task(connect_imu(device2, on_imu2_data_received, "IMU2")),
        asyncio.create_task(display_euler_angles())
    ]
    
    try:
        # 等待所有任务完成（实际上会一直运行直到Ctrl+C）
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        print("\n正在停止...")
        for task in tasks:
            task.cancel()


def plot_trajectory():
    """绘制机械臂末端的3D运动轨迹"""
    if len(trajectory_positions) == 0:
        print("没有记录到轨迹数据")
        return
    
    print("\n" + "="*70)
    print("正在生成3D轨迹图...")
    print("="*70)
    
    # 转换为numpy数组便于处理
    trajectory_array = np.array(trajectory_positions)
    link1_array = np.array(trajectory_link1)
    link2_array = np.array(trajectory_link2)
    
    # 创建3D图形（调整为2x3布局以容纳所有投影）
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
    ax1.set_title('End-Effector 3D Trajectory', fontsize=12, fontweight='bold')
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
    ax5.plot(trajectory_timestamps, trajectory_array[:, 0], 'r-', linewidth=1.5, label='X', alpha=0.7)
    ax5.plot(trajectory_timestamps, trajectory_array[:, 1], 'g-', linewidth=1.5, label='Y', alpha=0.7)
    ax5.plot(trajectory_timestamps, trajectory_array[:, 2], 'b-', linewidth=1.5, label='Z', alpha=0.7)
    ax5.set_xlabel('Time (s)', fontsize=10)
    ax5.set_ylabel('Position (m)', fontsize=10)
    ax5.set_title('Position vs Time', fontsize=12, fontweight='bold')
    ax5.legend()
    ax5.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 统计信息
    print(f"\n轨迹统计:")
    print(f"  总点数: {len(trajectory_positions)}")
    print(f"  持续时间: {trajectory_timestamps[-1]:.2f} 秒")
    print(f"  采样频率: {len(trajectory_positions) / trajectory_timestamps[-1]:.1f} Hz")
    
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
    
    print("\n✓ 图表已生成")
    print("关闭图表窗口以退出程序\n")
    plt.show()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n程序已停止")
    finally:
        print("已断开所有连接")
        
        # 绘制轨迹
        if len(trajectory_positions) > 0:
            print("\n正在生成轨迹图...")
            plot_trajectory()
        else:
            print("\n未记录到轨迹数据")
