#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WIT RS485传感器模拟器
用于测试程序功能，模拟真实的传感器响应
"""

import threading
import time
import math
import random

class WITSensorSimulator:
    """WIT传感器模拟器"""
    
    def __init__(self):
        self.running = False
        self.thread = None
        
        # 模拟传感器数据
        self.accel_x = 0.0
        self.accel_y = 0.0  
        self.accel_z = 1.0  # 重力加速度
        
        self.gyro_x = 0.0
        self.gyro_y = 0.0
        self.gyro_z = 0.0
        
        self.mag_x = 0.0
        self.mag_y = 0.0
        self.mag_z = 0.0
        
        self.angle_x = 0.0
        self.angle_y = 0.0
        self.angle_z = 0.0
        
    def start_simulation(self):
        """开始模拟"""
        self.running = True
        self.thread = threading.Thread(target=self._simulate_data)
        self.thread.start()
        print("🎭 传感器模拟器已启动")
        
    def stop_simulation(self):
        """停止模拟"""
        self.running = False
        if self.thread:
            self.thread.join()
        print("🛑 传感器模拟器已停止")
        
    def _simulate_data(self):
        """模拟传感器数据变化"""
        start_time = time.time()
        
        while self.running:
            current_time = time.time() - start_time
            
            # 模拟自然的传感器数据变化
            # 加速度 - 模拟轻微的振动
            self.accel_x = 0.1 * math.sin(current_time * 2) + random.uniform(-0.05, 0.05)
            self.accel_y = 0.1 * math.cos(current_time * 1.5) + random.uniform(-0.05, 0.05)
            self.accel_z = 1.0 + 0.05 * math.sin(current_time * 3) + random.uniform(-0.02, 0.02)
            
            # 角速度 - 模拟缓慢旋转
            self.gyro_x = 5 * math.sin(current_time * 0.5) + random.uniform(-2, 2)
            self.gyro_y = 3 * math.cos(current_time * 0.7) + random.uniform(-2, 2)
            self.gyro_z = 2 * math.sin(current_time * 0.3) + random.uniform(-1, 1)
            
            # 磁场 - 模拟地磁场
            self.mag_x = 0.2 + 0.05 * math.sin(current_time * 0.1)
            self.mag_y = 0.1 + 0.03 * math.cos(current_time * 0.15)
            self.mag_z = 0.4 + 0.02 * math.sin(current_time * 0.08)
            
            # 角度 - 模拟姿态变化
            self.angle_x = 10 * math.sin(current_time * 0.2) + random.uniform(-2, 2)
            self.angle_y = 5 * math.cos(current_time * 0.25) + random.uniform(-2, 2)
            self.angle_z = 15 * math.sin(current_time * 0.1) + random.uniform(-3, 3)
            
            time.sleep(0.1)  # 100ms更新一次
    
    def get_sensor_data(self):
        """获取当前传感器数据"""
        return {
            'AccX': round(self.accel_x, 3),
            'AccY': round(self.accel_y, 3), 
            'AccZ': round(self.accel_z, 3),
            'AsX': round(self.gyro_x, 3),
            'AsY': round(self.gyro_y, 3),
            'AsZ': round(self.gyro_z, 3),
            'HX': round(self.mag_x, 3),
            'HY': round(self.mag_y, 3),
            'HZ': round(self.mag_z, 3),
            'AngX': round(self.angle_x, 3),
            'AngY': round(self.angle_y, 3),
            'AngZ': round(self.angle_z, 3)
        }

def simulate_data_callback(device_model):
    """模拟数据回调"""
    # 创建模拟数据
    simulator = WITSensorSimulator()
    sensor_data = simulator.get_sensor_data()
    
    # 将数据注入到设备模型中
    addr = 0x50
    for key, value in sensor_data.items():
        device_model.set(addr, key, value)
    
    # 显示数据
    print(f"🎭 模拟传感器数据 [{time.strftime('%H:%M:%S')}]:")
    print(f"   加速度: X={sensor_data['AccX']:6.3f}g, Y={sensor_data['AccY']:6.3f}g, Z={sensor_data['AccZ']:6.3f}g")
    print(f"   角速度: X={sensor_data['AsX']:6.1f}°/s, Y={sensor_data['AsY']:6.1f}°/s, Z={sensor_data['AsZ']:6.1f}°/s")
    print(f"   磁  场: X={sensor_data['HX']:6.3f}G, Y={sensor_data['HY']:6.3f}G, Z={sensor_data['HZ']:6.3f}G")
    print(f"   角  度: X={sensor_data['AngX']:6.1f}°, Y={sensor_data['AngY']:6.1f}°, Z={sensor_data['AngZ']:6.1f}°")
    print("-" * 80)

def test_with_simulated_data():
    """使用模拟数据测试程序"""
    print("🎭 WIT传感器程序 - 模拟数据测试")
    print("=" * 60)
    print("注意: 这是模拟数据，用于验证程序功能")
    print("真实传感器需要硬件连接")
    print()
    
    # 创建模拟器
    simulator = WITSensorSimulator()
    simulator.start_simulation()
    
    try:
        print("🔄 开始模拟数据显示 (按Ctrl+C停止)...")
        print("-" * 80)
        
        while True:
            # 模拟数据回调
            class MockDeviceModel:
                def __init__(self):
                    self.deviceData = {0x50: {}}
                def set(self, addr, key, value):
                    self.deviceData[addr][key] = value
            
            mock_device = MockDeviceModel()
            simulate_data_callback(mock_device)
            
            time.sleep(2)  # 每2秒更新一次显示
            
    except KeyboardInterrupt:
        print("\n🛑 停止模拟...")
    finally:
        simulator.stop_simulation()
        print("✅ 模拟测试完成")

if __name__ == "__main__":
    test_with_simulated_data()