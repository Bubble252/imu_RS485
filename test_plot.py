#!/usr/bin/env python
# coding:UTF-8
"""
快速测试绘图功能
"""
import numpy as np
from collections import deque
import time

# 模拟轨迹数据
trajectory_positions = deque(maxlen=1000)
trajectory_timestamps = deque(maxlen=1000)

# 生成一些测试数据（圆形轨迹）
print("生成测试轨迹数据...")
for i in range(100):
    t = i * 0.1
    x = 0.3 + 0.1 * np.cos(t)
    y = 0.1 * np.sin(t)
    z = 0.0
    
    trajectory_positions.append([x, y, z])
    trajectory_timestamps.append(t)

print(f"已生成 {len(trajectory_positions)} 个轨迹点")

# 导入绘图函数
def plot_trajectory():
    """
    绘制机械臂末端的3D运动轨迹
    借鉴dual_imu_euler.py的完整绘图功能
    """
    if len(trajectory_positions) == 0:
        print("没有记录到轨迹数据")
        return
    
    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        import matplotlib
        
        # 设置中文字体（避免中文显示为方框）
        matplotlib.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial Unicode MS', 'SimHei']
        matplotlib.rcParams['axes.unicode_minus'] = False
        
    except ImportError:
        print("⚠️  matplotlib未安装，无法绘制轨迹图")
        return
    
    print("\n" + "="*70)
    print("正在生成3D轨迹图...")
    print("="*70)
    
    try:
        # 转换为numpy数组便于处理
        trajectory_array = np.array(list(trajectory_positions))
        timestamps_array = np.array(list(trajectory_timestamps))
        
        # 创建3D图形（2x3布局，与dual_imu_euler.py一致）
        fig = plt.figure(figsize=(18, 10))
        
        # === 子图1: 3D轨迹 ===
        ax1 = fig.add_subplot(2, 3, 1, projection='3d')
        ax1.plot(trajectory_array[:, 0], trajectory_array[:, 1], trajectory_array[:, 2], 
                 'b-', linewidth=1.5, alpha=0.6, label='Trajectory')
        ax1.scatter(trajectory_array[0, 0], trajectory_array[0, 1], trajectory_array[0, 2], 
                    c='green', s=100, marker='o', label='Start')
        ax1.scatter(trajectory_array[-1, 0], trajectory_array[-1, 1], trajectory_array[-1, 2], 
                    c='red', s=100, marker='x', label='End')
        
        # 绘制原点
        ax1.scatter([0], [0], [0], c='black', s=100, marker='o', label='Origin')
        
        ax1.set_xlabel('X (m)', fontsize=10)
        ax1.set_ylabel('Y (m)', fontsize=10)
        ax1.set_zlabel('Z (m)', fontsize=10)
        ax1.set_title('End-Effector 3D Trajectory (RS485)', fontsize=12, fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # === 子图2: XY平面投影 ===
        ax2 = fig.add_subplot(2, 3, 2)
        ax2.plot(trajectory_array[:, 0], trajectory_array[:, 1], 'b-', linewidth=1.5, alpha=0.6)
        ax2.scatter(trajectory_array[0, 0], trajectory_array[0, 1], c='green', s=100, marker='o', label='Start')
        ax2.scatter(trajectory_array[-1, 0], trajectory_array[-1, 1], c='red', s=100, marker='x', label='End')
        ax2.scatter([0], [0], c='black', s=50, marker='o', label='Origin')
        ax2.set_xlabel('X (m)', fontsize=10)
        ax2.set_ylabel('Y (m)', fontsize=10)
        ax2.set_title('XY Plane Projection (Top View)', fontsize=12, fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.axis('equal')
        
        # === 子图3: XZ平面投影 ===
        ax3 = fig.add_subplot(2, 3, 3)
        ax3.plot(trajectory_array[:, 0], trajectory_array[:, 2], 'b-', linewidth=1.5, alpha=0.6)
        ax3.scatter(trajectory_array[0, 0], trajectory_array[0, 2], c='green', s=100, marker='o', label='Start')
        ax3.scatter(trajectory_array[-1, 0], trajectory_array[-1, 2], c='red', s=100, marker='x', label='End')
        ax3.scatter([0], [0], c='black', s=50, marker='o', label='Origin')
        ax3.set_xlabel('X (m)', fontsize=10)
        ax3.set_ylabel('Z (m)', fontsize=10)
        ax3.set_title('XZ Plane Projection (Side View)', fontsize=12, fontweight='bold')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        ax3.axis('equal')
        
        # === 子图4: YZ平面投影 ===
        ax4 = fig.add_subplot(2, 3, 4)
        ax4.plot(trajectory_array[:, 1], trajectory_array[:, 2], 'b-', linewidth=1.5, alpha=0.6)
        ax4.scatter(trajectory_array[0, 1], trajectory_array[0, 2], c='green', s=100, marker='o', label='Start')
        ax4.scatter(trajectory_array[-1, 1], trajectory_array[-1, 2], c='red', s=100, marker='x', label='End')
        ax4.scatter([0], [0], c='black', s=50, marker='o', label='Origin')
        ax4.set_xlabel('Y (m)', fontsize=10)
        ax4.set_ylabel('Z (m)', fontsize=10)
        ax4.set_title('YZ Plane Projection (Front View)', fontsize=12, fontweight='bold')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        ax4.axis('equal')
        
        # === 子图5: 位置随时间变化 ===
        ax5 = fig.add_subplot(2, 3, (5, 6))
        ax5.plot(timestamps_array, trajectory_array[:, 0], 'r-', linewidth=1.5, label='X', alpha=0.7)
        ax5.plot(timestamps_array, trajectory_array[:, 1], 'g-', linewidth=1.5, label='Y', alpha=0.7)
        ax5.plot(timestamps_array, trajectory_array[:, 2], 'b-', linewidth=1.5, label='Z', alpha=0.7)
        ax5.set_xlabel('Time (s)', fontsize=10)
        ax5.set_ylabel('Position (m)', fontsize=10)
        ax5.set_title('Position vs Time', fontsize=12, fontweight='bold')
        ax5.legend()
        ax5.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # === 统计信息（借鉴dual_imu_euler.py） ===
        print(f"\n轨迹统计:")
        print(f"  总点数: {len(trajectory_positions)}")
        
        if len(timestamps_array) > 1:
            duration = timestamps_array[-1] - timestamps_array[0]
            print(f"  持续时间: {duration:.2f} 秒")
            if duration > 0:
                print(f"  采样频率: {len(trajectory_positions) / duration:.1f} Hz")
        
        # 计算轨迹总长度
        total_distance = 0
        for i in range(1, len(trajectory_array)):
            total_distance += np.linalg.norm(trajectory_array[i] - trajectory_array[i-1])
        print(f"  轨迹总长度: {total_distance:.4f} m ({total_distance*1000:.1f} mm)")
        
        # 位置范围
        print(f"\n位置范围:")
        print(f"  X: [{trajectory_array[:, 0].min():.4f}, {trajectory_array[:, 0].max():.4f}] m")
        print(f"  Y: [{trajectory_array[:, 1].min():.4f}, {trajectory_array[:, 1].max():.4f}] m")
        print(f"  Z: [{trajectory_array[:, 2].min():.4f}, {trajectory_array[:, 2].max():.4f}] m")
        
        # 保存图像
        plt.savefig('trajectory_rs485_test.png', dpi=150, bbox_inches='tight')
        print("\n✓ 轨迹图已保存到 trajectory_rs485_test.png")
        
        print("="*70)
        
    except Exception as e:
        print(f"⚠️  绘制轨迹图失败: {e}")
        import traceback
        traceback.print_exc()

# 测试绘图
plot_trajectory()
print("\n测试完成！")
