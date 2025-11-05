#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多波特率WIT传感器测试程序
"""

import device_model
import time
import os

def enhanced_data_callback(device_model_instance):
    """数据回调函数"""
    print(f"📊 收到数据! 时间: {time.strftime('%H:%M:%S')}")
    
    data = device_model_instance.deviceData
    if data:
        for addr, sensor_data in data.items():
            if sensor_data:
                print(f"🎯 设备地址 {hex(addr)} 数据:")
                for key, value in sensor_data.items():
                    print(f"   {key}: {value}")
                print("-" * 50)
                return True  # 找到数据就返回
    return False

def test_multiple_baudrates():
    """测试多个波特率"""
    print("🔧 WIT RS485传感器 - 多波特率测试")
    print("=" * 60)
    
    # 检查设备
    device_path = "/dev/ttyUSB0"
    if not os.path.exists(device_path):
        print(f"❌ 设备文件不存在: {device_path}")
        return False
    
    # 常见的波特率列表（按常用程度排序）
    baudrates = [9600, 115200, 38400, 19200, 4800, 57600]
    
    # 常见的设备地址
    addresses = [0x50, 0x51, 0x52, 0x01]
    
    print(f"🔍 将测试波特率: {baudrates}")
    print(f"🎯 将测试设备地址: {[hex(addr) for addr in addresses]}")
    print()
    
    for baudrate in baudrates:
        print(f"🚀 测试波特率: {baudrate}")
        print("-" * 40)
        
        success = False
        
        for addr in addresses:
            print(f"   📡 测试地址: {hex(addr)}")
            
            try:
                # 创建设备实例
                device = device_model.DeviceModel(
                    deviceName=f"WIT_{baudrate}_{hex(addr)}",
                    portName=device_path,
                    baud=baudrate,  # 使用当前测试的波特率
                    addrLis=[addr],
                    callback_method=enhanced_data_callback
                )
                
                # 打开设备
                device.openDevice()
                
                if not device.isOpen:
                    print(f"     ❌ 设备打开失败")
                    continue
                
                print(f"     ✅ 设备打开成功")
                
                # 手动发送几个读取命令
                register_addresses = [0x34, 0x30, 0x20]
                
                for reg_addr in register_addresses:
                    print(f"     📤 读取寄存器 {hex(reg_addr)}")
                    try:
                        device.readReg(addr, reg_addr, 12)
                        time.sleep(0.3)  # 等待响应
                    except Exception as e:
                        print(f"     ⚠️  发送失败: {e}")
                
                # 开始短时间的循环读取测试
                print(f"     🔄 循环读取测试 (5秒)...")
                device.startLoopRead()
                
                # 等待数据
                start_time = time.time()
                data_received = False
                
                while time.time() - start_time < 5:
                    if device.deviceData.get(addr):
                        print(f"     🎉 成功! 波特率={baudrate}, 地址={hex(addr)}")
                        data_received = True
                        success = True
                        break
                    time.sleep(0.1)
                
                # 停止并关闭
                device.stopLoopRead()
                device.closeDevice()
                
                if data_received:
                    print(f"\n✅ 找到正确配置!")
                    print(f"   波特率: {baudrate}")
                    print(f"   设备地址: {hex(addr)}")
                    return baudrate, addr
                else:
                    print(f"     ❌ 地址 {hex(addr)} 无响应")
                    
            except Exception as e:
                print(f"     ❌ 测试地址 {hex(addr)} 时出错: {e}")
                try:
                    device.closeDevice()
                except:
                    pass
        
        if success:
            break
        
        print(f"❌ 波特率 {baudrate} 测试完毕，无响应")
        print()
    
    print("❌ 所有波特率和地址组合都测试完毕，未收到数据")
    print("\n可能的原因:")
    print("1. 🔌 没有连接实际的WIT传感器")
    print("2. ⚡ 传感器没有供电")
    print("3. 🔧 RS485接线问题")
    print("4. 📋 传感器使用了非标准配置")
    
    return None, None

def run_with_found_config(baudrate, address):
    """使用找到的配置运行程序"""
    print(f"\n🚀 使用找到的配置运行程序")
    print(f"   波特率: {baudrate}")
    print(f"   设备地址: {hex(address)}")
    print("=" * 60)
    
    try:
        device = device_model.DeviceModel(
            deviceName="WIT传感器",
            portName="/dev/ttyUSB0",
            baud=baudrate,
            addrLis=[address],
            callback_method=enhanced_data_callback
        )
        
        device.openDevice()
        
        if device.isOpen:
            device.startLoopRead()
            
            print("🔄 程序运行中，按 Ctrl+C 停止...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 停止程序...")
        
        device.stopLoopRead()
        device.closeDevice()
        print("✅ 程序退出")
        
    except Exception as e:
        print(f"❌ 运行错误: {e}")

def main():
    print("🔍 开始多波特率检测...")
    
    # 测试多个波特率
    baudrate, address = test_multiple_baudrates()
    
    if baudrate and address:
        # 如果找到了正确的配置，询问是否继续运行
        choice = input(f"\n是否使用找到的配置继续运行程序? (y/n): ").lower()
        if choice == 'y':
            run_with_found_config(baudrate, address)
    else:
        print("\n💡 建议:")
        print("1. 检查硬件连接")
        print("2. 确认传感器供电")
        print("3. 查看传感器说明书确认配置")
        print("4. 尝试使用专业的Modbus调试工具")

if __name__ == "__main__":
    main()