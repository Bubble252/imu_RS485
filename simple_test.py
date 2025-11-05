#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版RS485设备测试程序
专门针对CH340设备优化
"""

import device_model
import time
import os
import subprocess

def setup_ch340_device():
    """设置CH340设备"""
    print("🔍 CH340 RS485设备设置向导")
    print("="*50)
    
    # 检查设备是否存在
    device_path = "/dev/ttyUSB0"
    
    print("1. 检查设备连接...")
    if not os.path.exists(device_path):
        print(f"❌ 未找到设备 {device_path}")
        print("请确保:")
        print("  - CH340设备已插入USB端口")
        print("  - BRLTTY服务已停止: sudo systemctl stop brltty")
        print("  - 驱动已正确加载: lsmod | grep ch341")
        return None
    
    print(f"✅ 找到设备: {device_path}")
    
    # 检查权限
    print("2. 检查设备权限...")
    if os.access(device_path, os.R_OK | os.W_OK):
        print("✅ 权限正常")
        return device_path
    
    print("❌ 权限不足")
    print("尝试修复权限...")
    
    try:
        # 尝试修复权限
        result = subprocess.run(f"sudo chmod 666 {device_path}", 
                              shell=True, check=True, capture_output=True)
        print("✅ 权限修复成功")
        return device_path
    except:
        print("❌ 权限修复失败")
        print(f"请手动运行: sudo chmod 666 {device_path}")
        return device_path  # 仍然返回设备路径，让用户决定

def data_callback(device_model):
    """数据回调函数 - 打印接收到的传感器数据"""
    data = device_model.deviceData
    if data:
        for addr, sensor_data in data.items():
            if sensor_data:  # 只打印有数据的设备
                print(f"设备 {hex(addr)} 数据:", sensor_data)

def main():
    print("🚀 WIT RS485传感器测试程序 (Linux版)")
    print("="*50)
    
    # 设置CH340设备
    device_path = setup_ch340_device()
    if device_path is None:
        print("设备设置失败，程序退出")
        return
    
    print(f"\n3. 初始化传感器...")
    print(f"使用串口: {device_path}")
    
    # Modbus设备地址列表
    addr_list = [0x50]  # WIT传感器默认地址
    
    try:
        # 创建设备模型
        device = device_model.DeviceModel(
            deviceName="WIT RS485传感器",
            portName=device_path,
            baud=9600,  # 正确的波特率是9600
            addrLis=addr_list,
            callback_method=data_callback
        )
        
        # 打开设备
        print("4. 打开串口连接...")
        device.openDevice()
        
        if not device.isOpen:
            print("❌ 串口打开失败")
            return
        
        print("✅ 串口连接成功")
        
        # 开始循环读取
        print("5. 开始读取传感器数据...")
        print("按 Ctrl+C 停止")
        print("-" * 50)
        
        device.startLoopRead()
        
        # 保持程序运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n6. 停止数据读取...")
            device.stopLoopRead()
            device.closeDevice()
            print("✅ 程序正常退出")
            
    except Exception as e:
        print(f"❌ 程序异常: {e}")
        print("请检查:")
        print("  - 串口权限是否正确")
        print("  - 传感器是否正确连接")
        print("  - 传感器地址是否为0x50")
        print("  - 波特率是否为115200")

if __name__ == "__main__":
    main()