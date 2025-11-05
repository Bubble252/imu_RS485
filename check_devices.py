#!/usr/bin/env python3
"""
多设备检测程序 - 检查哪些设备地址有响应
"""
import serial
import time
import struct

def calculate_crc16_modbus(data):
    """计算Modbus CRC16校验"""
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

def create_modbus_request(device_addr, start_reg=0x34, num_regs=12):
    """创建Modbus读取请求"""
    # 功能码：03 (读保持寄存器)
    func_code = 0x03
    
    # 构建请求数据包
    request = struct.pack('>BBHH', device_addr, func_code, start_reg, num_regs)
    
    # 计算CRC
    crc = calculate_crc16_modbus(request)
    request += struct.pack('<H', crc)
    
    return request

def test_device_response(ser, device_addr, timeout=1.0):
    """测试单个设备是否响应"""
    try:
        # 清空缓冲区
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # 发送请求
        request = create_modbus_request(device_addr)
        ser.write(request)
        
        # 等待响应
        start_time = time.time()
        response = b''
        
        while (time.time() - start_time) < timeout:
            if ser.in_waiting > 0:
                response += ser.read(ser.in_waiting)
                # 检查是否收到完整响应（至少5字节）
                if len(response) >= 5:
                    # 检查设备地址是否匹配
                    if response[0] == device_addr:
                        return True, len(response)
            time.sleep(0.01)
        
        return False, len(response)
    
    except Exception as e:
        return False, f"错误: {e}"

def main():
    # 要测试的设备地址列表
    test_addresses = [0x50, 0x51, 0x52, 0x53, 0x54, 0x55]
    
    print("🔍 多设备连接检测程序")
    print("=" * 50)
    
    try:
        # 打开串口
        ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
        print(f"✅ 串口已打开: {ser.name}")
        print(f"📊 波特率: {ser.baudrate}")
        print()
        
        # 测试每个设备地址
        online_devices = []
        
        for addr in test_addresses:
            print(f"测试设备地址 0x{addr:02X} ({addr})... ", end="", flush=True)
            
            is_online, response_info = test_device_response(ser, addr)
            
            if is_online:
                print(f"✅ 在线 (响应{response_info}字节)")
                online_devices.append(addr)
            else:
                print(f"❌ 离线 ({response_info})")
            
            time.sleep(0.1)  # 设备间延时
        
        print()
        print("=" * 50)
        print(f"📈 检测结果总结:")
        print(f"   在线设备数量: {len(online_devices)}")
        
        if online_devices:
            print(f"   在线设备地址: {[f'0x{addr:02X}' for addr in online_devices]}")
            print()
            print("💡 建议:")
            print(f"   在test.py中使用: addrLis = {online_devices}")
        else:
            print("   ⚠️  未检测到任何设备响应")
            print()
            print("🔧 故障排除建议:")
            print("   1. 检查设备电源是否正常")
            print("   2. 检查RS485连线是否正确")
            print("   3. 确认设备地址配置")
            print("   4. 尝试不同的波特率")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    finally:
        try:
            ser.close()
            print("\n🔚 串口已关闭")
        except:
            pass

if __name__ == "__main__":
    main()