#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WIT RS485传感器数据读取诊断程序
"""

import device_model
import time
import os

def enhanced_data_callback(device_model_instance):
    """增强的数据回调函数，提供详细信息"""
    print(f"🔄 数据回调被调用! 时间: {time.strftime('%H:%M:%S')}")
    
    data = device_model_instance.deviceData
    if data:
        print(f"📊 设备数据: {data}")
        
        # 检查每个设备地址的数据
        for addr, sensor_data in data.items():
            print(f"   设备地址 {hex(addr)}: {len(sensor_data) if sensor_data else 0} 个数据项")
            if sensor_data:
                for key, value in sensor_data.items():
                    print(f"     {key}: {value}")
    else:
        print("❌ 设备数据为空")
    print("-" * 50)

def test_communication():
    """测试通信的诊断程序"""
    print("🔍 WIT RS485传感器通信诊断程序")
    print("=" * 60)
    
    # 检查设备
    device_path = "/dev/ttyUSB0"
    if not os.path.exists(device_path):
        print(f"❌ 设备文件不存在: {device_path}")
        return False
    
    print(f"✅ 设备文件存在: {device_path}")
    
    # 设备地址列表 - 尝试多个常见地址
    test_addresses = [0x50, 0x51, 0x52, 0x01]  # 常见的WIT传感器地址
    
    for addr in test_addresses:
        print(f"\n🧪 测试设备地址: {hex(addr)}")
        
        try:
            # 创建设备实例
            device = device_model.DeviceModel(
                deviceName=f"WIT传感器_地址{hex(addr)}",
                portName=device_path,
                baud=115200,
                addrLis=[addr],
                callback_method=enhanced_data_callback
            )
            
            # 打开设备
            device.openDevice()
            
            if not device.isOpen:
                print(f"❌ 设备打开失败")
                continue
            
            print(f"✅ 设备打开成功")
            
            # 手动发送读取命令
            print("📤 发送读取命令...")
            
            # 尝试不同的寄存器地址
            register_addresses = [0x34, 0x30, 0x20, 0x50, 0x51, 0x52]
            
            for reg_addr in register_addresses:
                print(f"   📍 读取寄存器 {hex(reg_addr)}")
                try:
                    device.readReg(addr, reg_addr, 12)
                    time.sleep(0.5)  # 等待响应
                except Exception as e:
                    print(f"   ❌ 读取失败: {e}")
            
            # 开始循环读取测试
            print("🔄 开始循环读取测试 (10秒)...")
            device.startLoopRead()
            
            # 等待数据
            start_time = time.time()
            data_received = False
            
            while time.time() - start_time < 10:
                if device.deviceData.get(addr):
                    print(f"🎉 收到数据! 地址: {hex(addr)}")
                    data_received = True
                    break
                time.sleep(0.1)
            
            # 停止并关闭
            device.stopLoopRead()
            device.closeDevice()
            
            if data_received:
                print(f"✅ 地址 {hex(addr)} 测试成功!")
                return True
            else:
                print(f"❌ 地址 {hex(addr)} 无响应")
                
        except Exception as e:
            print(f"❌ 测试地址 {hex(addr)} 时出错: {e}")
            try:
                device.closeDevice()
            except:
                pass
    
    print("\n❌ 所有地址测试完毕，未收到数据")
    return False

def test_raw_communication():
    """测试原始串口通信"""
    print("\n🔌 测试原始串口通信...")
    
    try:
        import serial
        
        # 打开串口
        ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=2)
        print("✅ 串口打开成功")
        
        # 清空缓冲区
        ser.flushInput()
        ser.flushOutput()
        
        # 发送一个简单的Modbus读取命令 (地址0x50, 功能码0x03, 寄存器0x34, 长度12)
        # 格式: [设备地址][功能码][起始寄存器高][起始寄存器低][寄存器数量高][寄存器数量低][CRC低][CRC高]
        test_command = bytes([0x50, 0x03, 0x00, 0x34, 0x00, 0x0C, 0x44, 0x56])
        
        print(f"📤 发送命令: {test_command.hex()}")
        ser.write(test_command)
        
        # 等待响应
        time.sleep(0.5)
        
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting)
            print(f"📥 收到响应: {response.hex()}")
            print(f"📏 响应长度: {len(response)} 字节")
            
            if len(response) > 0:
                print("✅ 串口通信正常!")
            else:
                print("❌ 无响应数据")
        else:
            print("❌ 无响应")
        
        ser.close()
        
    except Exception as e:
        print(f"❌ 串口测试失败: {e}")

def suggest_solutions():
    """建议解决方案"""
    print("\n" + "=" * 60)
    print("🛠️  可能的解决方案:")
    print()
    
    print("1. 📡 检查硬件连接:")
    print("   - 确保WIT传感器正确连接到RS485转换器")
    print("   - 检查RS485的A、B线连接")
    print("   - 确认传感器供电正常")
    print()
    
    print("2. ⚙️  检查设备配置:")
    print("   - 传感器Modbus地址可能不是0x50")
    print("   - 尝试其他常见地址: 0x51, 0x52, 0x01")
    print("   - 波特率可能需要调整: 9600, 38400, 115200")
    print()
    
    print("3. 🔧 尝试不同的寄存器地址:")
    print("   - 当前使用: 0x34")
    print("   - 尝试: 0x30, 0x20, 0x50, 0x51, 0x52")
    print()
    
    print("4. 🔄 测试步骤:")
    print("   - 先确认设备没有连接其他软件")
    print("   - 尝试重新插拔USB设备")
    print("   - 使用万用表检查RS485信号")

def main():
    print("🚀 开始WIT RS485传感器诊断...")
    
    # 测试设备地址
    if not test_communication():
        # 如果高级测试失败，尝试原始通信测试
        test_raw_communication()
    
    # 提供解决建议
    suggest_solutions()

if __name__ == "__main__":
    main()