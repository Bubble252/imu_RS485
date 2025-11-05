#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的串口测试程序
"""

import serial
import time

def test_raw_serial():
    """测试原始串口通信"""
    print("🔌 串口原始通信测试")
    print("=" * 40)
    
    try:
        # 打开串口
        ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=2)
        print(f"✅ 串口打开成功")
        print(f"   端口: {ser.name}")
        print(f"   波特率: {ser.baudrate}")
        print(f"   超时: {ser.timeout}秒")
        
        # 清空缓冲区
        ser.flushInput()
        ser.flushOutput()
        
        # 测试不同的Modbus命令
        test_commands = [
            # 地址0x50, 功能码0x03, 寄存器0x34, 长度12
            ([0x50, 0x03, 0x00, 0x34, 0x00, 0x0C], "地址0x50,寄存器0x34"),
            # 地址0x50, 功能码0x03, 寄存器0x30, 长度12  
            ([0x50, 0x03, 0x00, 0x30, 0x00, 0x0C], "地址0x50,寄存器0x30"),
            # 地址0x51, 功能码0x03, 寄存器0x34, 长度12
            ([0x51, 0x03, 0x00, 0x34, 0x00, 0x0C], "地址0x51,寄存器0x34"),
        ]
        
        for cmd_data, description in test_commands:
            print(f"\n📤 测试: {description}")
            
            # 计算CRC
            crc = calculate_crc(cmd_data)
            full_command = cmd_data + [crc & 0xFF, (crc >> 8) & 0xFF]
            
            command_bytes = bytes(full_command)
            print(f"   发送: {command_bytes.hex()}")
            
            # 发送命令
            ser.write(command_bytes)
            
            # 等待响应
            time.sleep(0.5)
            
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting)
                print(f"   📥 收到: {response.hex()} ({len(response)} 字节)")
                
                if len(response) >= 5:  # 最小Modbus响应长度
                    addr = response[0]
                    func = response[1]
                    data_len = response[2] if func == 0x03 else 0
                    print(f"   ✅ 响应解析: 地址={hex(addr)}, 功能码={hex(func)}, 数据长度={data_len}")
                else:
                    print(f"   ⚠️  响应太短")
            else:
                print(f"   ❌ 无响应")
            
            # 清空缓冲区
            ser.flushInput()
        
        ser.close()
        print(f"\n✅ 串口测试完成")
        
    except Exception as e:
        print(f"❌ 串口测试失败: {e}")

def calculate_crc(data):
    """计算Modbus CRC"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc

def test_loop_back():
    """测试回环 - 发送简单数据看能否收到"""
    print("\n🔄 回环测试")
    print("=" * 20)
    
    try:
        ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
        
        # 发送简单的测试数据
        test_data = b'\x01\x02\x03\x04\x05'
        print(f"📤 发送测试数据: {test_data.hex()}")
        
        ser.write(test_data)
        time.sleep(0.1)
        
        if ser.in_waiting > 0:
            received = ser.read(ser.in_waiting)
            print(f"📥 收到: {received.hex()}")
            if received == test_data:
                print("✅ 完美回环!")
            else:
                print("⚠️  数据不匹配")
        else:
            print("❌ 无回环响应 (这是正常的，因为没有连接实际设备)")
        
        ser.close()
        
    except Exception as e:
        print(f"❌ 回环测试失败: {e}")

def check_physical_connection():
    """检查物理连接建议"""
    print("\n🔧 物理连接检查清单")
    print("=" * 30)
    
    print("1. 🔌 USB连接:")
    print("   ✅ CH340设备已识别")
    print("   ✅ /dev/ttyUSB0 设备文件存在")
    print("   ✅ 串口可以打开")
    
    print("\n2. ❓ 需要检查的项目:")
    print("   🔍 WIT传感器是否已连接到RS485转换器?")
    print("   🔍 RS485转换器是否连接到CH340?") 
    print("   🔍 传感器是否正常供电?")
    print("   🔍 RS485的A、B线连接是否正确?")
    
    print("\n3. 🎯 可能的问题:")
    print("   • 没有连接实际的WIT传感器")
    print("   • 传感器Modbus地址不是0x50")
    print("   • 传感器波特率不是115200")
    print("   • RS485接线错误")
    print("   • 传感器没有供电或损坏")
    
    print("\n4. 🧪 测试建议:")
    print("   • 使用万用表测试RS485信号线")
    print("   • 尝试不同的波特率: 9600, 38400, 115200")
    print("   • 查看WIT传感器的配置手册")
    print("   • 使用专业的Modbus测试工具验证")

if __name__ == "__main__":
    test_raw_serial()
    test_loop_back()
    check_physical_connection()