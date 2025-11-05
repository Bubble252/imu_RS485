#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时监控串口设备的插拔
"""

import time
import glob
import os

def get_serial_devices():
    """获取当前所有串口设备"""
    devices = []
    for pattern in ['/dev/ttyUSB*', '/dev/ttyACM*']:
        devices.extend(glob.glob(pattern))
    return sorted(devices)

def main():
    print("🔍 实时监控串口设备插拔")
    print("="*50)
    print("请重新插拔您的CH340 USB设备...")
    print("按 Ctrl+C 停止监控")
    print()
    
    previous_devices = set(get_serial_devices())
    print(f"初始设备: {list(previous_devices) if previous_devices else '无'}")
    
    try:
        while True:
            time.sleep(1)
            current_devices = set(get_serial_devices())
            
            # 检查新插入的设备
            new_devices = current_devices - previous_devices
            if new_devices:
                for device in new_devices:
                    print(f"🔌 设备插入: {device}")
                    
                    # 检查权限
                    if os.access(device, os.R_OK | os.W_OK):
                        print(f"   ✅ 权限正常，可以使用")
                        print(f"   💡 您的RS485设备可能是: {device}")
                    else:
                        print(f"   ❌ 权限不足")
                        print(f"   🔧 临时解决: sudo chmod 666 {device}")
            
            # 检查拔出的设备  
            removed_devices = previous_devices - current_devices
            if removed_devices:
                for device in removed_devices:
                    print(f"🔌 设备拔出: {device}")
            
            previous_devices = current_devices
            
    except KeyboardInterrupt:
        print("\n监控结束")
        
        final_devices = get_serial_devices()
        if final_devices:
            print(f"\n当前可用设备: {final_devices}")
            print(f"建议使用: {final_devices[0]}")

if __name__ == "__main__":
    main()