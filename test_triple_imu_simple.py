#!/usr/bin/env python
# coding:UTF-8
"""
简单测试脚本 - 验证三IMU RS485数据采集
不包含ZeroMQ发布，仅显示IMU数据和末端位置
"""
import time
import numpy as np
import device_model

# === 机械臂参数 ===
L1 = 0.275  # 杆1长度（米）
L2 = 0.275  # 杆2长度（米）

# === IMU设备地址 ===
IMU1_ADDR = 0x50  # 80
IMU2_ADDR = 0x51  # 81
IMU3_ADDR = 0x52  # 82

# === 全局数据 ===
imu1_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
imu2_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
imu3_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}

imu1_yaw_offset = None
imu2_yaw_offset = None
imu3_yaw_offset = None

update_count = 0


def normalize_angle(angle):
    """归一化角度到 [-180, 180]"""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def calculate_position(euler1, euler2):
    """计算末端位置"""
    yaw1_rad = np.deg2rad(euler1["yaw"])
    yaw2_rad = np.deg2rad(euler2["yaw"])
    
    x1 = L1 * np.cos(yaw1_rad)
    y1 = L1 * np.sin(yaw1_rad)
    
    x2 = x1 + L2 * np.cos(yaw2_rad)
    y2 = y1 + L2 * np.sin(yaw2_rad)
    
    return [x2, y2, 0.0]


def data_callback(DeviceModel):
    """数据回调"""
    global imu1_euler, imu2_euler, imu3_euler
    global imu1_yaw_offset, imu2_yaw_offset, imu3_yaw_offset
    global update_count
    
    data = DeviceModel.deviceData
    update_count += 1
    
    # 处理IMU1
    if 80 in data:
        d = data[80]
        yaw = d.get('AngZ', 0.0)
        
        if imu1_yaw_offset is None:
            imu1_yaw_offset = yaw
            print(f"✓ IMU1 归零: {imu1_yaw_offset:.2f}°")
        
        imu1_euler = {
            "roll": d.get('AngX', 0.0),
            "pitch": d.get('AngY', 0.0),
            "yaw": normalize_angle(yaw - imu1_yaw_offset)
        }
    
    # 处理IMU2
    if 81 in data:
        d = data[81]
        yaw = d.get('AngZ', 0.0)
        
        if imu2_yaw_offset is None:
            imu2_yaw_offset = yaw
            print(f"✓ IMU2 归零: {imu2_yaw_offset:.2f}°")
        
        imu2_euler = {
            "roll": d.get('AngX', 0.0),
            "pitch": d.get('AngY', 0.0),
            "yaw": normalize_angle(yaw - imu2_yaw_offset)
        }
    
    # 处理IMU3
    if 82 in data:
        d = data[82]
        yaw = d.get('AngZ', 0.0)
        
        if imu3_yaw_offset is None:
            imu3_yaw_offset = yaw
            print(f"✓ IMU3 归零: {imu3_yaw_offset:.2f}°")
        
        imu3_euler = {
            "roll": d.get('AngX', 0.0),
            "pitch": d.get('AngY', 0.0),
            "yaw": normalize_angle(yaw - imu3_yaw_offset)
        }
    
    # 每10次更新显示一次
    if update_count % 10 == 0:
        pos = calculate_position(imu1_euler, imu2_euler)
        
        print(f"\n[更新 #{update_count}]")
        print(f"  末端位置: [{pos[0]:7.3f}, {pos[1]:7.3f}, {pos[2]:7.3f}] m")
        print(f"  IMU1: Y={imu1_euler['yaw']:6.1f}° R={imu1_euler['roll']:6.1f}° P={imu1_euler['pitch']:6.1f}°")
        print(f"  IMU2: Y={imu2_euler['yaw']:6.1f}° R={imu2_euler['roll']:6.1f}° P={imu2_euler['pitch']:6.1f}°")
        print(f"  IMU3: Y={imu3_euler['yaw']:6.1f}° R={imu3_euler['roll']:6.1f}° P={imu3_euler['pitch']:6.1f}°")


def main():
    print("="*60)
    print("三IMU数据采集测试（简化版）")
    print("="*60)
    print(f"串口: /dev/ttyUSB0")
    print(f"波特率: 9600")
    print(f"设备地址: 0x50, 0x51, 0x52")
    print("="*60 + "\n")
    
    try:
        # 创建设备
        device = device_model.DeviceModel(
            "三IMU测试",
            "/dev/ttyUSB0",
            9600,
            [IMU1_ADDR, IMU2_ADDR, IMU3_ADDR],
            data_callback
        )
        
        # 打开设备
        device.openDevice()
        
        if not device.isOpen:
            print("❌ 无法打开串口")
            return
        
        print("✓ 串口已打开\n")
        
        # 启动循环读取
        device.startLoopRead()
        print("✓ 数据采集已启动\n")
        print("等待IMU归零...\n")
        
        # 等待归零
        while imu1_yaw_offset is None or imu2_yaw_offset is None or imu3_yaw_offset is None:
            time.sleep(0.1)
        
        print("\n✓ 所有IMU已归零")
        print("按Ctrl+C停止...\n")
        
        # 持续运行
        while True:
            time.sleep(1)
        
    except KeyboardInterrupt:
        print("\n\n✓ 程序已停止")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if device and device.isOpen:
            device.stopLoopRead()
            time.sleep(0.5)
            device.closeDevice()
        print(f"\n总更新次数: {update_count}")
        print("程序已退出")


if __name__ == '__main__':
    main()
