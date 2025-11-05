#!/usr/bin/env python3
"""
调试版本 - 详细显示每个设备的读取过程
"""
import device_model
import time
import os

# 计数器
update_count = 0

def debug_updateData(DeviceModel):
    global update_count
    update_count += 1
    
    data = DeviceModel.deviceData
    current_time = time.strftime("%H:%M:%S.%f")[:-3]  # 精确到毫秒
    
    print(f"\n[{current_time}] 第{update_count}次数据更新:")
    print(f"   当前deviceData内容: {list(data.keys())}")
    
    # 显示每个设备的详细信息
    for device_id, device_data in data.items():
        print(f"   设备{device_id} (0x{device_id:02X}): AccX={device_data.get('AccX', 'N/A')}")
    
    print(f"   总设备数: {len(data)}")

if __name__ == "__main__":
    # 读取三个设备
    addrLis = [0x50, 0x51, 0x52]
    
    print("🔍 调试模式 - 详细监控设备读取过程")
    print(f"目标设备地址: {[f'0x{addr:02X}' for addr in addrLis]}")
    print("=" * 60)
    
    try:
        device = device_model.DeviceModel("调试设备", "/dev/ttyUSB0", 9600, addrLis, debug_updateData)
        device.openDevice()
        
        if device.isOpen:
            device.startLoopRead()
            
            # 运行15秒后停止
            print("程序运行中，15秒后自动停止...")
            time.sleep(15)
            print("\n正在停止...")
        else:
            print("设备打开失败")
            
    except Exception as e:
        print(f"程序异常: {e}")
    finally:
        try:
            if 'device' in locals() and device.isOpen:
                device.stopLoopRead()
                time.sleep(0.5)
                device.closeDevice()
        except:
            pass
        print("程序已退出")