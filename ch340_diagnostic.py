#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CH340 USB转串口设备检测和修复工具
"""

import subprocess
import os
import sys

def run_command(cmd, use_sudo=False):
    """运行系统命令"""
    try:
        if use_sudo:
            cmd = f"sudo {cmd}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)

def check_ch340_device():
    """检查CH340设备"""
    print("=== 检查CH340设备 ===")
    
    # 检查USB设备列表
    returncode, stdout, stderr = run_command("lsusb | grep -i ch340")
    
    if returncode == 0 and stdout.strip():
        print("✅ 找到CH340设备:")
        print(f"   {stdout.strip()}")
        return True
    else:
        print("❌ 未找到CH340设备")
        return False

def check_ch340_driver():
    """检查CH340驱动"""
    print("\n=== 检查CH340驱动 ===")
    
    # 检查驱动模块
    returncode, stdout, stderr = run_command("lsmod | grep ch341")
    
    if returncode == 0 and stdout.strip():
        print("✅ CH340驱动(ch341-uart)已加载:")
        print(f"   {stdout.strip()}")
        return True
    else:
        print("❌ CH340驱动未加载")
        return False

def check_serial_devices():
    """检查串口设备"""
    print("\n=== 检查串口设备 ===")
    
    # 检查各种串口设备
    devices_found = []
    
    for pattern in ['/dev/ttyUSB*', '/dev/ttyACM*', '/dev/ttyS*']:
        returncode, stdout, stderr = run_command(f"ls {pattern} 2>/dev/null")
        if returncode == 0 and stdout.strip():
            devices = stdout.strip().split('\n')
            devices_found.extend(devices)
    
    if devices_found:
        print(f"✅ 找到 {len(devices_found)} 个串口设备:")
        for i, device in enumerate(sorted(set(devices_found))):
            print(f"   {i+1}. {device}")
            
            # 检查设备权限
            try:
                if os.access(device, os.R_OK | os.W_OK):
                    print(f"      ✅ 可读写")
                else:
                    print(f"      ❌ 权限不足")
            except:
                print(f"      ❓ 无法检查权限")
        
        return sorted(set(devices_found))
    else:
        print("❌ 未找到任何串口设备")
        return []

def fix_ch340_driver():
    """修复CH340驱动"""
    print("\n=== 修复CH340驱动 ===")
    
    print("尝试手动加载CH340驱动...")
    
    # 尝试加载驱动
    returncode, stdout, stderr = run_command("modprobe ch341-uart", use_sudo=True)
    
    if returncode == 0:
        print("✅ 驱动加载成功")
        return True
    else:
        print(f"❌ 驱动加载失败: {stderr}")
        
        print("\n尝试安装CH340驱动...")
        print("请手动运行以下命令:")
        print("sudo apt update")
        print("sudo apt install linux-headers-$(uname -r)")
        print("sudo modprobe ch341-uart")
        
        return False

def check_user_permissions():
    """检查用户权限"""
    print("\n=== 检查用户权限 ===")
    
    import getpass
    username = getpass.getuser()
    
    # 检查dialout组
    returncode, stdout, stderr = run_command(f"groups {username}")
    
    if returncode == 0:
        groups = stdout.strip().split()
        if 'dialout' in groups:
            print(f"✅ 用户 {username} 在dialout组中")
            return True
        else:
            print(f"❌ 用户 {username} 不在dialout组中")
            print(f"请运行: sudo usermod -a -G dialout {username}")
            print("然后重新登录或重启系统")
            return False
    else:
        print("❓ 无法检查用户组")
        return False

def suggest_solutions(has_device, has_driver, has_serials, has_permission):
    """建议解决方案"""
    print("\n" + "="*50)
    print("🔧 解决方案建议:")
    
    if not has_device:
        print("1. 请检查CH340设备是否正确连接")
        print("2. 尝试重新插拔USB设备")
        print("3. 尝试更换USB端口")
    
    elif not has_driver:
        print("1. 手动加载驱动: sudo modprobe ch341-uart")
        print("2. 安装内核头文件: sudo apt install linux-headers-$(uname -r)")
        print("3. 重启系统后再试")
    
    elif not has_serials:
        print("1. 驱动可能加载了但设备未创建")
        print("2. 尝试重新插拔设备")
        print("3. 检查dmesg日志: sudo dmesg | tail -20")
    
    elif not has_permission:
        print("1. 添加用户到dialout组: sudo usermod -a -G dialout $USER")
        print("2. 重新登录或重启系统")
        print("3. 或临时修改权限: sudo chmod 666 /dev/ttyUSB0")
    
    else:
        print("✅ 一切看起来正常!")
        if has_serials:
            print(f"建议使用设备: {has_serials[0]}")

def main():
    print("🔍 CH340 USB转串口设备诊断工具")
    print("="*50)
    
    # 检查各个组件
    has_device = check_ch340_device()
    has_driver = check_ch340_driver()
    has_serials = check_serial_devices()
    has_permission = check_user_permissions()
    
    # 如果没有驱动，尝试修复
    if has_device and not has_driver:
        choice = input("\n是否尝试自动修复驱动? (y/n): ").lower()
        if choice == 'y':
            has_driver = fix_ch340_driver()
            # 重新检查串口设备
            print("\n重新检查串口设备...")
            has_serials = check_serial_devices()
    
    # 提供解决方案
    suggest_solutions(has_device, has_driver, has_serials, has_permission)
    
    print("\n" + "="*50)
    print("📋 快速命令参考:")
    print("  查看USB设备: lsusb")
    print("  查看驱动模块: lsmod | grep ch341")
    print("  加载驱动: sudo modprobe ch341-uart")
    print("  查看串口: ls -la /dev/ttyUSB*")
    print("  查看日志: sudo dmesg | grep -i usb")

if __name__ == "__main__":
    main()