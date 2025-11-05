import device_model
import time
import os
import glob


def get_linux_serial_ports():
    """获取Linux系统下常见的串口设备"""
    # 常见的Linux串口设备路径
    possible_ports = [
        '/dev/ttyUSB*',  # USB转串口设备
        '/dev/ttyACM*',  # USB CDC ACM设备  
        '/dev/ttyS*',    # 标准串口
        '/dev/ttyAMA*',  # ARM设备串口(如树莓派)
    ]
    
    available_ports = []
    for pattern in possible_ports:
        ports = glob.glob(pattern)
        for port in ports:
            if os.path.exists(port):
                available_ports.append(port)
    
    return sorted(available_ports)


def select_serial_port():
    """选择串口设备"""
    # 优先检查CH340设备(ttyUSB0)
    ch340_device = "/dev/ttyUSB0"
    if os.path.exists(ch340_device):
        print(f"✅ 找到CH340设备: {ch340_device}")
        
        # 检查权限
        if os.access(ch340_device, os.R_OK | os.W_OK):
            print(f"✅ 权限正常")
            return ch340_device
        else:
            print(f"❌ 权限不足，请运行以下命令之一:")
            print(f"   临时解决: sudo chmod 666 {ch340_device}")
            print(f"   永久解决: sudo usermod -a -G dialout $USER (需要重新登录)")
            
            # 尝试临时解决权限问题
            choice = input("是否尝试自动修复权限? (y/n): ").lower()
            if choice == 'y':
                import subprocess
                try:
                    subprocess.run(f"sudo chmod 666 {ch340_device}", shell=True, check=True)
                    print(f"✅ 权限修复成功")
                    return ch340_device
                except:
                    print(f"❌ 权限修复失败，请手动运行命令")
            
            return ch340_device
    
    # 如果没有ttyUSB0，检查其他设备
    ports = get_linux_serial_ports()
    
    if not ports:
        print("警告: 未找到任何串口设备")
        print("请确保:")
        print("1. CH340设备已正确连接")
        print("2. BRLTTY服务已停止: sudo systemctl stop brltty")
        print("3. 设备驱动已加载: lsmod | grep ch341")
        return "/dev/ttyUSB0"  # 返回默认值
    
    print("找到以下串口设备:")
    for i, port in enumerate(ports):
        print(f"{i+1}. {port}")
    
    # 自动选择第一个USB设备
    for port in ports:
        if 'USB' in port:
            print(f"自动选择: {port}")
            return port
    
    # 如果没有USB设备，选择第一个
    print(f"自动选择: {ports[0]}")
    return ports[0]


# 数据更新事件  Data update event  
def updateData(DeviceModel):
    data = DeviceModel.deviceData
    
    # 显示当前时间戳
    current_time = time.strftime("%H:%M:%S")
    
    # 每5次更新显示一次详细信息
    if not hasattr(updateData, 'count'):
        updateData.count = 0
    updateData.count += 1
    
    if updateData.count % 5 == 1:  # 每5次显示一次
        print(f"\n[{current_time}] 所有设备状态:")
        for device_id in sorted(data.keys()):
            device_data = data[device_id]
            acc_x = device_data.get('AccX', 0)
            acc_y = device_data.get('AccY', 0)
            acc_z = device_data.get('AccZ', 0)
            print(f"  设备{device_id} (0x{device_id:02X}): AccX={acc_x:.3f}g, AccY={acc_y:.3f}g, AccZ={acc_z:.3f}g")
        print(f"  总设备数: {len(data)}")
        print("-" * 60)


if __name__ == "__main__":
    # 读取的modbus地址列表 List of Modbus addresses read
    addrLis = [0x50, 0x51, 0x52]  # 三个设备的地址
    
    # 获取Linux系统下的串口设备
    port_name = select_serial_port()
    
    if port_name is None:
        print("\n请手动指定串口设备:")
        print("常见的RS485/USB转串口设备: /dev/ttyUSB0, /dev/ttyACM0")
        port_name = input("请输入串口设备路径 (默认: /dev/ttyUSB0): ").strip()
        if not port_name:
            port_name = "/dev/ttyUSB0"
    
    print(f"使用串口: {port_name}")
    
    try:
        # 拿到设备模型 Get the device model
        device = device_model.DeviceModel("测试设备1", port_name, 9600, addrLis, updateData)
        
        # 开启设备 Turn on the device
        device.openDevice()
        
        if device.isOpen:
            # 开启轮询 Enable loop reading
            device.startLoopRead()
            
            try:
                # 保持程序运行，直到用户按Ctrl+C
                print("程序运行中，按 Ctrl+C 停止...")
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n正在停止...")
        else:
            print("设备打开失败，程序退出")
            
    except Exception as e:
        print(f"程序异常: {e}")
    finally:
        # 确保设备被正确关闭
        try:
            if 'device' in locals() and device.isOpen:
                device.stopLoopRead()
                time.sleep(0.5)  # 给线程时间停止
                device.closeDevice()
        except Exception:
            pass  # 忽略关闭时的错误
        print("程序已退出")
