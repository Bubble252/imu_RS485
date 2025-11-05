#!/usr/bin/env python
# coding:UTF-8
"""
三IMU欧拉角读取 + ZeroMQ发布程序
整合 triple_imu_euler.py 的功能，并通过ZeroMQ发布机械臂末端位置姿态到MuJoCo仿真环境

功能说明：
1. 连接三个IMU传感器，实时读取欧拉角
2. 计算两杆串联机械臂的末端位置（IMU1 + IMU2）
3. 读取机械爪的姿态（IMU3）
4. 通过ZeroMQ PUB socket发布数据到MuJoCo仿真接收端
5. 发布频率默认5Hz，采用latest-only策略

数据流架构：
    IMU1 (蓝牙) ──┐
                   ├──> 运动学计算 ──> 末端位置
    IMU2 (蓝牙) ──┘                        ↓
    IMU3 (蓝牙) ──────> 机械爪姿态  ────────┴──> ZeroMQ发布 ──> MuJoCo仿真

运行方法：
    # 使用默认参数（5Hz发布到localhost:5555）
    python triple_imu_publisher.py
    
    # 仅在三个IMU都在线时发布（推荐）
    python triple_imu_publisher.py --online-only
    
    # 自定义发布频率
    python triple_imu_publisher.py --interval 0.1 --online-only
"""
import asyncio
import time
import json
import argparse
import numpy as np
import zmq
import zmq.asyncio

# 导入triple_imu_euler模块
import triple_imu_euler as imu_mod

# === 默认配置参数 ===
DEFAULT_BIND_ADDRESS = "tcp://127.0.0.1:5555"
DEFAULT_PUBLISH_INTERVAL = 0.2  # 5Hz


async def publisher_loop(pub_socket, publish_interval, online_only=False):
    """
    ZeroMQ发布循环（异步版本）
    
    参数：
        pub_socket: ZeroMQ PUB socket
        publish_interval: 发布间隔（秒）
        online_only: 是否仅在三个IMU都在线时发布
    
    发布消息格式：
        {
          "position": [x, y, z],           // 末端位置（米，映射后）
          "orientation": [roll, pitch, yaw], // 机械爪姿态（度，直接使用IMU3）
          "gripper": 0.0,                   // 夹爪状态
          "t": timestamp                    // 时间戳
        }
    """
    print("\n" + "="*70)
    print("ZeroMQ发布器已启动（三IMU模式）")
    print("="*70)
    print(f"发布地址: {pub_socket.getsockopt_string(zmq.LAST_ENDPOINT)}")
    print(f"发布频率: {1.0/publish_interval:.1f} Hz (间隔 {publish_interval*1000:.0f} ms)")
    print(f"在线检查: {'启用（仅在三个IMU都在线时发布）' if online_only else '禁用（始终发布）'}")
    print(f"缓冲策略: Latest-only（无缓冲队列）")
    print("="*70 + "\n")
    
    publish_count = 0
    skip_count = 0
    last_stat_time = time.time()
    
    try:
        while True:
            loop_start = time.time()
            
            # === 步骤1: 检查三个IMU在线状态 ===
            current_time = time.time()
            imu1_online = (current_time - imu_mod.imu1_last_update) < 1.0 if imu_mod.imu1_last_update > 0 else False
            imu2_online = (current_time - imu_mod.imu2_last_update) < 1.0 if imu_mod.imu2_last_update > 0 else False
            imu3_online = (current_time - imu_mod.imu3_last_update) < 1.0 if imu_mod.imu3_last_update > 0 else False
            
            # 如果启用了online_only模式，检查三个IMU是否都在线
            if online_only and not (imu1_online and imu2_online and imu3_online):
                skip_count += 1
                if skip_count % 25 == 0:  # 每5秒打印一次状态
                    print(f"⚠️  等待IMU在线... IMU1: {'✓' if imu1_online else '✗'}, "
                          f"IMU2: {'✓' if imu2_online else '✗'}, "
                          f"IMU3: {'✓' if imu3_online else '✗'} (已跳过 {skip_count} 次)")
                await asyncio.sleep(publish_interval)
                continue
            
            # === 步骤2: 读取最新IMU数据 ===
            try:
                euler1 = imu_mod.imu1_euler.copy()
                euler2 = imu_mod.imu2_euler.copy()
                euler3 = imu_mod.imu3_euler.copy()  # 机械爪姿态
                
                # 计算机械臂末端位置
                end_pos, link1_pos, link2_pos = imu_mod.calculate_end_effector_position(euler1, euler2)
                
            except Exception as e:
                print(f"⚠️  读取IMU数据失败: {e}")
                end_pos = [0.0, 0.0, 0.0]
                euler3 = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
            
            # === 坐标映射和约束 ===
            # 约束到原始范围: x=[0, 0.55], y=[-0.4, 0.4], z=[0, 0.3]
            x_raw = np.clip(end_pos[0], 0.0, 0.55)
            y_raw = np.clip(end_pos[1], -0.4, 0.4)
            z_raw = np.clip(end_pos[2], 0.0, 0.3)
            
            # 线性映射到目标范围: x=[0.22, 0.35], y=[-0.2, 0.2], z=[0.16, 0.36]
            x_mapped = 0.22 + (x_raw - 0.0) / (0.55 - 0.0) * (0.35 - 0.22)
            y_mapped = -0.2 + (y_raw - (-0.4)) / (0.4 - (-0.4)) * (0.2 - (-0.2))
            z_mapped = 0.16 + (z_raw - 0.0) / (0.3 - 0.0) * (0.36 - 0.16)
            
            # === 步骤3: 构造发布消息 ===
            message = {
                "position": [
                    float(x_mapped),  # x (米) - 映射后的值
                    float(y_mapped),  # y (米) - 映射后的值
                    float(z_mapped)   # z (米) - 映射后的值
                ],
                "orientation": [
                    float(euler3["roll"]),   # Roll（度）- 直接使用IMU3（机械爪）的欧拉角
                    float(euler3["pitch"]),  # Pitch（度）
                    float(euler3["yaw"])     # Yaw（度）
                ],
                "gripper": 0.0,  # 夹爪状态（未实现，暂时设为0）
                "t": current_time  # 时间戳
            }
            
            # === 步骤4: 异步发送JSON消息 ===
            try:
                await pub_socket.send_string(json.dumps(message))
                publish_count += 1
            except Exception as e:
                print(f"❌ ZeroMQ发送失败: {e}")
            
            # === 步骤5: 定期打印统计信息（每2秒） ===
            if current_time - last_stat_time >= 2.0:
                actual_rate = publish_count / (current_time - last_stat_time) if publish_count > 0 else 0.0
                print(f"📡 发布统计 | 消息数: {publish_count} | 实际频率: {actual_rate:.1f} Hz")
                print(f"   原始位置: [{end_pos[0]:7.3f}, {end_pos[1]:7.3f}, {end_pos[2]:7.3f}] m")
                print(f"   映射位置: [{x_mapped:7.3f}, {y_mapped:7.3f}, {z_mapped:7.3f}] m")
                print(f"   机械爪姿态: [R:{euler3['roll']:6.1f}° P:{euler3['pitch']:6.1f}° Y:{euler3['yaw']:6.1f}°]")
                print(f"   IMU状态: IMU1={'✓' if imu1_online else '✗'} "
                      f"IMU2={'✓' if imu2_online else '✗'} "
                      f"IMU3={'✓' if imu3_online else '✗'}")
                publish_count = 0
                last_stat_time = current_time
            
            # === 步骤6: 精确定时控制 ===
            elapsed = time.time() - loop_start
            to_sleep = max(0.0, publish_interval - elapsed)
            await asyncio.sleep(to_sleep)
            
    except asyncio.CancelledError:
        print(f"\n📊 发布器已停止 | 总发布: {publish_count} 条消息")
        raise


async def main_async(bind_address, publish_interval, online_only):
    """
    主异步函数：同时运行三IMU采集和ZeroMQ发布
    
    架构说明：
        任务1: triple_imu_euler.main()
            - 蓝牙扫描和连接三个IMU
            - 持续接收数据并更新全局变量
            - 实时显示欧拉角和末端位置
            - 记录运动轨迹
        
        任务2: publisher_loop()
            - 定期读取全局变量（Latest-only策略）
            - 计算末端位置（IMU1 + IMU2）
            - 读取机械爪姿态（IMU3）
            - 通过ZeroMQ发布JSON消息
    """
    print("="*70)
    print("三IMU机械臂ZeroMQ发布器（双杆 + 机械爪）")
    print("="*70)
    print(f"IMU 1 (杆1): {imu_mod.IMU1_MAC}")
    print(f"IMU 2 (杆2): {imu_mod.IMU2_MAC}")
    print(f"IMU 3 (机械爪): {imu_mod.IMU3_MAC}")
    print(f"杆1长度: {imu_mod.L1*1000:.0f} mm")
    print(f"杆2长度: {imu_mod.L2*1000:.0f} mm")
    print(f"Yaw归零模式: {imu_mod.YAW_NORMALIZATION_MODE}")
    print("="*70 + "\n")
    
    # 创建ZeroMQ异步上下文
    zmq_context = zmq.asyncio.Context()
    pub_socket = zmq_context.socket(zmq.PUB)
    
    try:
        # 绑定到指定地址
        pub_socket.bind(bind_address)
        print(f"✓ ZeroMQ PUB socket已绑定到 {bind_address}")
        print("  等待订阅者连接...\n")
        
        await asyncio.sleep(0.5)
        
        # 并发运行两个任务
        tasks = [
            asyncio.create_task(imu_mod.main(), name="三IMU采集"),
            asyncio.create_task(publisher_loop(pub_socket, publish_interval, online_only), name="ZeroMQ发布")
        ]
        
        print("✓ 所有任务已启动，按Ctrl+C停止\n")
        
        await asyncio.gather(*tasks)
        
    except asyncio.CancelledError:
        print("\n正在停止所有任务...")
        for task in tasks:
            task.cancel()
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
    finally:
        print("正在关闭ZeroMQ连接...")
        pub_socket.close()
        zmq_context.term()
        print("✓ ZeroMQ连接已关闭")


def main():
    """命令行入口函数"""
    parser = argparse.ArgumentParser(
        description="三IMU机械臂ZeroMQ发布器 - 将双杆机械臂位置和机械爪姿态发布到MuJoCo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  # 使用默认参数（5Hz发布到localhost:5555）
  python triple_imu_publisher.py
  
  # 仅在三个IMU都在线时发布（推荐）
  python triple_imu_publisher.py --online-only
  
  # 自定义发布频率为10Hz
  python triple_imu_publisher.py --interval 0.1 --online-only
  
  # 绑定到所有网络接口
  python triple_imu_publisher.py --bind tcp://0.0.0.0:5555 --online-only

重要说明：
  - position: 由IMU1和IMU2计算的机械臂末端位置（经过坐标映射）
  - orientation: 直接使用IMU3的欧拉角（机械爪姿态）
  - gripper: 夹爪开合状态（暂未实现，固定为0）
  
  与dual_imu_publisher.py的区别：
  - 连接3个IMU而不是2个
  - orientation字段使用IMU3的欧拉角（机械爪）而不是IMU2
  - 需要三个IMU都在线才发布（如果使用--online-only）

MuJoCo接收端：
  接收到的数据格式：
    {
      "position": [x, y, z],           // 末端位置（米）
      "orientation": [roll, pitch, yaw], // 机械爪姿态（度）
      "gripper": 0.0,
      "t": 1234567890.123
    }
        """
    )
    parser.add_argument("--interval", "-i", type=float, default=DEFAULT_PUBLISH_INTERVAL,
                        help="发布间隔（秒），默认0.2（5Hz）")
    parser.add_argument("--bind", "-b", type=str, default=DEFAULT_BIND_ADDRESS,
                        help="ZeroMQ绑定地址，默认tcp://127.0.0.1:5555")
    parser.add_argument("--online-only", action="store_true",
                        help="仅在三个IMU都在线时发布数据（推荐启用）")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(main_async(args.bind, args.interval, args.online_only))
    except KeyboardInterrupt:
        print("\n\n✓ 程序已被用户中断")
    finally:
        print("已断开所有连接")
        
        # 绘制轨迹
        if len(imu_mod.trajectory_positions) > 0:
            print("\n正在生成轨迹图...")
            imu_mod.plot_trajectory()
        else:
            print("\n未记录到轨迹数据")


if __name__ == '__main__':
    main()
