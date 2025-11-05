#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的串口设备检测工具
帮助找到RS485设备对应的串口
"""

import os
import glob
import subprocess
import time

def check_device_info(port):
    """检查设备详细信息"""
    try:
        # 尝试获取设备信息
        result = subprocess.run(['udevadm', 'info', '--name=' + port], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout
    except:
        pass
    return None

def list_usb_serial_devices():
    """列出USB串口设备"""
    print("=== USB串口设备检测 ===")
    
    # 检查 /dev/ttyUSB* 设备
    usb_devices = glob.glob('/dev/ttyUSB*')
    acm_devices = glob.glob('/dev/ttyACM*')
    
    all_usb_devices = sorted(usb_devices + acm_devices)
    
    if not all_usb_devices:
        print("❌ 未找到USB串口设备")
        print("请检查:")
        print("  1. 设备是否已插入USB端口")
        print("  2. 设备驱动是否正确安装")
        print("  3. 设备是否需要特殊驱动(如CH340, FTDI等)")
        return []
    
    print(f"✅ 找到 {len(all_usb_devices)} 个USB串口设备:")
    for i, device in enumerate(all_usb_devices):
        print(f"\n{i+1}. {device}")
        
        # 检查设备是否可访问
        if os.access(device, os.R_OK | os.W_OK):
            print(f"   ✅ 权限: 可读写")
        else:
            print(f"   ❌ 权限: 无法访问 (需要添加到dialout组)")
        
        # 获取设备详细信息
        info = check_device_info(device)
        if info:
            # 提取有用信息
            for line in info.split('\n'):
                if 'ID_VENDOR=' in line:
                    vendor = line.split('=')[1].strip()
                    print(f"   厂商: {vendor}")
                elif 'ID_MODEL=' in line:
                    model = line.split('=')[1].strip()
                    print(f"   型号: {model}")
                elif 'ID_SERIAL_SHORT=' in line:
                    serial = line.split('=')[1].strip()
                    print(f"   序列号: {serial}")
    
    return all_usb_devices

def monitor_device_insertion():
    """监控设备插拔"""
    print("\n=== 设备插拔监控 ===")
    print("请按以下步骤操作:")
    print("1. 拔掉您的RS485设备")
    print("2. 按Enter键记录当前设备列表")
    input("   按Enter继续...")
    
    # 记录拔掉设备后的设备列表
    devices_before = set(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*'))
    print(f"拔掉设备后，检测到 {len(devices_before)} 个USB串口设备")
    
    print("\n3. 现在插入您的RS485设备")
    print("4. 等待2-3秒后按Enter键")
    input("   按Enter继续...")
    
    # 记录插入设备后的设备列表
    devices_after = set(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*'))
    print(f"插入设备后，检测到 {len(devices_after)} 个USB串口设备")
    
    # 找出新增的设备
    new_devices = devices_after - devices_before
    
    if new_devices:
        print(f"\n🎉 找到您的RS485设备:")
        for device in sorted(new_devices):
            print(f"   ➤ {device}")
            
            # 检查权限
            if os.access(device, os.R_OK | os.W_OK):
                print(f"      ✅ 权限正常，可以直接使用")
            else:
                print(f"      ❌ 权限不足，请运行: sudo chmod 666 {device}")
                print(f"      或者将用户添加到dialout组: sudo usermod -a -G dialout $USER")
    else:
        print("\n❌ 未检测到新设备，可能原因:")
        print("  1. 设备未正确插入")
        print("  2. 设备需要特殊驱动")
        print("  3. 设备可能对应/dev/ttyS*设备")

def check_dmesg_log():
    """检查系统日志中的USB设备信息"""
    print("\n=== 系统日志检查 ===")
    try:
        # 获取最近的USB设备日志
        result = subprocess.run(['dmesg', '|', 'grep', '-i', 'usb.*serial', '|', 'tail', '-10'], 
                              shell=True, capture_output=True, text=True, timeout=10)
        
        if result.stdout.strip():
            print("最近的USB串口设备日志:")
            for line in result.stdout.strip().split('\n'):
                print(f"  {line}")
        else:
            print("未找到相关USB串口日志")
            
    except Exception as e:
        print(f"无法获取系统日志: {e}")

def main():
    print("🔍 RS485设备串口检测工具")
    print("=" * 50)
    
    # 检查当前用户权限
    import getpass
    username = getpass.getuser()
    
    try:
        import grp
        dialout_group = grp.getgrnam('dialout')
        if username in dialout_group.gr_mem:
            print(f"✅ 用户 {username} 已在dialout组中")
        else:
            print(f"⚠️  用户 {username} 不在dialout组中")
            print(f"   建议运行: sudo usermod -a -G dialout {username}")
            print(f"   然后重新登录或重启")
    except:
        print("无法检查用户组信息")
    
    print()
    
    # 方法1: 列出当前USB设备
    usb_devices = list_usb_serial_devices()
    
    if usb_devices:
        print(f"\n💡 如果上面的设备中有您的RS485设备，可以直接使用")
        print(f"   推荐设备: {usb_devices[0]}")
    
    # 方法2: 监控设备插拔
    print(f"\n" + "="*50)
    choice = input("是否要通过插拔设备来确定串口? (y/n): ").lower()
    if choice == 'y':
        monitor_device_insertion()
    
    # 方法3: 检查系统日志
    check_dmesg_log()
    
    print(f"\n" + "="*50)
    print("🔧 其他有用的命令:")
    print("  查看所有串口: ls -la /dev/tty*")
    print("  查看USB设备: lsusb")
    print("  实时监控日志: sudo dmesg -w")
    print("  查看设备详情: udevadm info --name=/dev/ttyUSB0")

if __name__ == "__main__":
    main()