#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CH340设备实时监控和自动修复工具
"""

import time
import os
import subprocess
import signal
import sys

def run_command(cmd, silent=False):
    """运行系统命令"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if not silent:
            if result.returncode != 0 and result.stderr:
                print(f"   警告: {result.stderr.strip()}")
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        if not silent:
            print(f"   错误: {e}")
        return False, ""

def check_ch340_usb():
    """检查CH340 USB设备"""
    success, output = run_command("lsusb | grep -i ch340", silent=True)
    return success

def check_brltty_process():
    """检查BRLTTY进程"""
    success, output = run_command("ps aux | grep brltty | grep -v grep", silent=True)
    return success, output

def kill_brltty():
    """杀死BRLTTY进程"""
    print("   停止BRLTTY进程...")
    run_command("sudo pkill brltty", silent=True)
    run_command("sudo systemctl stop brltty", silent=True)

def check_ttyusb0():
    """检查ttyUSB0设备"""
    return os.path.exists("/dev/ttyUSB0")

def fix_permissions():
    """修复权限"""
    if os.path.exists("/dev/ttyUSB0"):
        print("   修复设备权限...")
        success, _ = run_command("sudo chmod 666 /dev/ttyUSB0")
        return success
    return False

def trigger_device_reset():
    """触发设备重新识别"""
    print("   触发设备重新识别...")
    # 尝试重新绑定设备
    success, output = run_command("lsusb | grep -i ch340 | awk '{print $2 \":\" $4}' | sed 's/://' | sed 's/://'")
    if success and output:
        bus_device = output.strip()
        if bus_device:
            # 尝试重新绑定USB设备
            run_command(f"sudo sh -c 'echo \"{bus_device}\" > /sys/bus/usb/drivers/usb/unbind'", silent=True)
            time.sleep(1)
            run_command(f"sudo sh -c 'echo \"{bus_device}\" > /sys/bus/usb/drivers/usb/bind'", silent=True)
            time.sleep(2)

def monitor_and_fix():
    """监控并自动修复CH340设备"""
    print("🔍 CH340设备实时监控和自动修复")
    print("="*50)
    print("按 Ctrl+C 停止监控")
    print()
    
    attempt = 0
    max_attempts = 10
    
    def signal_handler(sig, frame):
        print("\n\n监控结束")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    while attempt < max_attempts:
        attempt += 1
        print(f"🔄 第 {attempt} 次检查...")
        
        # 1. 检查USB设备
        if not check_ch340_usb():
            print("❌ CH340 USB设备未找到")
            print("   请重新插入CH340设备")
            time.sleep(3)
            continue
        else:
            print("✅ CH340 USB设备已识别")
        
        # 2. 检查BRLTTY干扰
        has_brltty, brltty_info = check_brltty_process()
        if has_brltty:
            print("⚠️  发现BRLTTY进程干扰")
            print(f"   {brltty_info}")
            kill_brltty()
            time.sleep(1)
        
        # 3. 检查ttyUSB0设备
        if not check_ttyusb0():
            print("❌ /dev/ttyUSB0 设备文件不存在")
            print("   尝试触发设备重新识别...")
            trigger_device_reset()
            time.sleep(3)
            
            # 再次检查
            if not check_ttyusb0():
                print("   仍然无法创建设备文件，继续尝试...")
                time.sleep(2)
                continue
        
        print("✅ /dev/ttyUSB0 设备文件存在")
        
        # 4. 修复权限
        if fix_permissions():
            print("✅ 设备权限修复成功")
        else:
            print("❌ 设备权限修复失败")
        
        # 5. 最终验证
        if os.access("/dev/ttyUSB0", os.R_OK | os.W_OK):
            print("\n🎉 CH340设备已就绪!")
            print(f"   设备路径: /dev/ttyUSB0")
            print(f"   权限状态: 可读写")
            print("\n现在可以运行您的程序:")
            print("   python simple_test.py")
            return True
        else:
            print("❌ 设备权限验证失败")
        
        print(f"   等待 3 秒后重试...")
        print()
        time.sleep(3)
    
    print(f"\n❌ 经过 {max_attempts} 次尝试仍然无法修复设备")
    print("请尝试以下手动步骤:")
    print("1. 重新插拔USB设备")
    print("2. 重启系统")
    print("3. 检查硬件连接")
    return False

if __name__ == "__main__":
    if monitor_and_fix():
        # 成功修复后，询问是否直接运行测试程序
        try:
            choice = input("\n是否立即运行测试程序? (y/n): ").lower()
            if choice == 'y':
                print("\n启动测试程序...")
                os.system("python simple_test.py")
        except KeyboardInterrupt:
            print("\n程序结束")
    else:
        print("\n设备修复失败，请手动检查")