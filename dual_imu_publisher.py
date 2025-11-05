#!/usr/bin/env python
# coding:UTF-8
"""
双IMU欧拉角读取 + ZeroMQ发布程序
整合 dual_imu_euler.py 的功能，并通过ZeroMQ发布机械臂末端位置姿态到MuJoCo仿真环境

功能说明：
1. 连接两个IMU传感器，实时读取欧拉角
2. 计算两杆串联机械臂的末端位置和姿态
3. 通过ZeroMQ PUB socket发布数据到MuJoCo仿真接收端
4. 发布频率默认5Hz（与IMU显示频率一致，避免仿真卡顿）
5. 采用latest-only策略（无缓冲队列），保证实时性

数据流架构：
    IMU1 (蓝牙) ──┐
                   ├──> 欧拉角解析 ──> 运动学计算 ──> ZeroMQ发布 ──> MuJoCo仿真
    IMU2 (蓝牙) ──┘
    
    - IMU采集和ZeroMQ发布在同一个asyncio事件循环中运行
    - 通过全局变量（imu1_euler, imu2_euler）进行数据共享
    - Latest-only策略：每次发布时读取最新值，不累积旧数据

运行方法：
    # 使用默认参数（5Hz发布到localhost:5555）
    python dual_imu_publisher.py
    
    # 自定义发布频率为10Hz
    python dual_imu_publisher.py --interval 0.1
    
    # 绑定到所有网络接口（允许远程连接）
    python dual_imu_publisher.py --bind tcp://0.0.0.0:5555
    
    # 仅在两个IMU都在线时发布
    python dual_imu_publisher.py --online-only
    
命令行参数：
    --interval: 发布间隔（秒），默认0.2（5Hz）
    --bind: ZeroMQ绑定地址，默认tcp://127.0.0.1:5555
    --online-only: 仅在两个IMU都在线时发布数据（推荐启用）
"""
import asyncio
import time
import json
import argparse
import numpy as np
import zmq
import zmq.asyncio

# 导入dual_imu_euler模块（必须在同一目录下）
# 该模块提供：
#   - async main()：IMU连接和数据采集主函数
#   - imu1_euler, imu2_euler：全局变量，存储最新欧拉角
#   - calculate_end_effector_position()：机械臂运动学计算函数
#   - imu1_last_update, imu2_last_update：时间戳，用于判断IMU在线状态
import dual_imu_euler as imu_mod

# === 默认配置参数 ===
DEFAULT_BIND_ADDRESS = "tcp://127.0.0.1:5555"  # ZeroMQ绑定地址（与MuJoCo接收端匹配）
DEFAULT_PUBLISH_INTERVAL = 0.2  # 发布间隔（秒），默认5Hz


async def publisher_loop(pub_socket, publish_interval, online_only=False):
    """
    ZeroMQ发布循环（异步版本）
    
    参数：
        pub_socket: ZeroMQ PUB socket（异步版本）
        publish_interval: 发布间隔（秒）
        online_only: 是否仅在两个IMU都在线时发布
    
    发布策略详解：
        【Latest-only策略】
        - 不使用缓冲队列，每次发布时直接读取最新的全局变量值
        - 优点：保证仿真端接收到的总是最新状态，避免延迟累积
        - 适用场景：实时控制系统，旧数据无价值
        
        【为什么不用缓冲队列？】
        - 如果IMU采集频率（50-200Hz）> 发布频率（5Hz），缓冲队列会不断积压
        - 仿真端处理速度有限，积压的数据会导致控制延迟
        - Latest-only直接丢弃中间帧，确保低延迟
    
    消息格式（JSON字符串）：
        {
          "position": [x, y, z],           // 末端位置（米）
          "orientation": [roll, pitch, yaw], // 末端姿态（度，使用IMU2的欧拉角）
          "gripper": gripper_value,         // 夹爪状态（0.0表示未实现）
          "t": timestamp                    // 时间戳（Unix时间）
        }
    """
    print("\n" + "="*70)
    print("ZeroMQ发布器已启动")
    print("="*70)
    print(f"发布地址: {pub_socket.getsockopt_string(zmq.LAST_ENDPOINT)}")
    print(f"发布频率: {1.0/publish_interval:.1f} Hz (间隔 {publish_interval*1000:.0f} ms)")
    print(f"在线检查: {'启用（仅在两个IMU都在线时发布）' if online_only else '禁用（始终发布）'}")
    print(f"缓冲策略: Latest-only（无缓冲队列，实时发布最新数据）")
    print("="*70 + "\n")
    
    publish_count = 0  # 发布计数器
    skip_count = 0     # 跳过计数器（IMU离线时）
    last_stat_time = time.time()  # 上次统计时间
    
    try:
        while True:
            loop_start = time.time()
            
            # === 步骤1: 检查IMU在线状态 ===
            current_time = time.time()
            imu1_online = (current_time - imu_mod.imu1_last_update) < 1.0 if imu_mod.imu1_last_update > 0 else False
            imu2_online = (current_time - imu_mod.imu2_last_update) < 1.0 if imu_mod.imu2_last_update > 0 else False
            
            # 如果启用了online_only模式，检查两个IMU是否都在线
            if online_only and not (imu1_online and imu2_online):
                skip_count += 1
                if skip_count % 25 == 0:  # 每5秒打印一次状态
                    print(f"⚠️  等待IMU在线... IMU1: {'✓在线' if imu1_online else '✗离线'}, "
                          f"IMU2: {'✓在线' if imu2_online else '✗离线'} (已跳过 {skip_count} 次发布)")
                await asyncio.sleep(publish_interval)
                continue
            
            # === 步骤2: 读取最新IMU数据（Latest-only策略） ===
            try:
                # 直接读取全局变量（无需加锁，因为Python的字典读取是原子操作）
                euler1 = imu_mod.imu1_euler.copy()  # copy()避免发布过程中数据被修改
                euler2 = imu_mod.imu2_euler.copy()
                
                # 计算机械臂末端位置和姿态
                end_pos, link1_pos, link2_pos = imu_mod.calculate_end_effector_position(euler1, euler2)
                
            except Exception as e:
                # 如果读取或计算失败，发布默认值（避免发布中断）
                print(f"⚠️  读取IMU数据失败: {e}")
                end_pos = [0.0, 0.0, 0.0]
                euler2 = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}

            
            # === 坐标映射和约束 ===
            # 步骤1: 约束到原始范围（使用numpy.clip）
            # 原始范围: x=[0, 0.55], y=[-0.4, 0.4], z=[0, 0.3]
            x_raw = np.clip(end_pos[0], 0.0, 0.55)
            y_raw = np.clip(end_pos[1], -0.4, 0.4)
            z_raw = np.clip(end_pos[2], 0.0, 0.3)
            
            # 步骤2: 线性映射到目标范围
            # 目标范围: x=[0.22, 0.35], y=[-0.2, 0.2], z=[0.16, 0.36]
            # 映射公式: target = target_min + (raw - raw_min) / (raw_max - raw_min) * (target_max - target_min)
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
                    float(0),   # Roll（度）- 使用IMU2的欧拉角作为末端姿态
                    float(0),  # Pitch（度）
                    float(0)     # Yaw（度）- 注意：dual_imu_euler.py的OFF模式已添加±180翻转
                ],
                "gripper": 0.0,  # 夹爪状态（dual_imu_euler未实现gripper控制，暂时设为0）
                "t": current_time  # 时间戳
            }
            
            # === 步骤4: 异步发送JSON消息 ===
            try:
                await pub_socket.send_string(json.dumps(message))
                publish_count += 1
            except Exception as e:
                print(f"❌ ZeroMQ发送失败: {e}")

            # === 步骤5: 定期打印统计信息（每2秒） ===
            if current_time - last_stat_time >= 2:
                actual_rate = publish_count / (current_time - last_stat_time) if publish_count > 0 else 0.0
                print(f"📡 发布统计 | 消息数: {publish_count} | 实际频率: {actual_rate:.1f} Hz")
                print(f"   原始位置: [{end_pos[0]:7.3f}, {end_pos[1]:7.3f}, {end_pos[2]:7.3f}] m")
                print(f"   映射位置: [{x_mapped:7.3f}, {y_mapped:7.3f}, {z_mapped:7.3f}] m")
                print(f"   IMU2姿态: [R:{euler2['roll']:6.1f}° P:{euler2['pitch']:6.1f}° Y:{euler2['yaw']:6.1f}°]")
                print(f"   IMU状态: IMU1={'✓' if imu1_online else '✗'} IMU2={'✓' if imu2_online else '✗'}")
                publish_count = 0
                last_stat_time = current_time
            
            # === 步骤6: 精确定时控制 ===
            # 计算本次循环耗时，补偿剩余时间
            elapsed = time.time() - loop_start
            to_sleep = max(0.0, publish_interval - elapsed)
            await asyncio.sleep(to_sleep)
            
    except asyncio.CancelledError:
        print(f"\n📊 发布器已停止 | 总发布: {publish_count} 条消息")
        raise


async def main_async(bind_address, publish_interval, online_only):
    """
    主异步函数：同时运行IMU采集和ZeroMQ发布
    
    参数：
        bind_address: ZeroMQ绑定地址（例如 tcp://127.0.0.1:5555）
        publish_interval: 发布间隔（秒）
        online_only: 是否仅在两个IMU都在线时发布
    
    架构说明：
        使用单个asyncio事件循环同时运行两个任务：
        
        任务1: dual_imu_euler.main()
            - 蓝牙扫描和连接两个IMU
            - 持续接收数据并更新全局变量（imu1_euler, imu2_euler）
            - 实时显示欧拉角和末端位置
            - 记录运动轨迹
        
        任务2: publisher_loop()
            - 定期读取全局变量（Latest-only策略）
            - 计算末端位置和姿态
            - 通过ZeroMQ发布JSON消息
        
        数据共享方式：
            - 生产者-消费者模式
            - 生产者：IMU数据接收回调函数（on_imu1_data_received, on_imu2_data_received）
            - 消费者：publisher_loop() 和 display_euler_angles()
            - 共享介质：全局变量（imu1_euler, imu2_euler等）
            - 线程安全：asyncio是单线程的，无需加锁
    """
    print("="*70)
    print("双IMU机械臂ZeroMQ发布器")
    print("="*70)
    print(f"IMU 1 (杆1): {imu_mod.IMU1_MAC}")
    print(f"IMU 2 (杆2): {imu_mod.IMU2_MAC}")
    print(f"杆1长度: {imu_mod.L1*1000:.0f} mm")
    print(f"杆2长度: {imu_mod.L2*1000:.0f} mm")
    print(f"Yaw归零模式: {imu_mod.YAW_NORMALIZATION_MODE}")
    if imu_mod.YAW_NORMALIZATION_MODE == "OFF":
        print("  ⚠️  注意：OFF模式下Yaw角会进行±180°翻转")
    print("="*70 + "\n")
    
    # === 步骤1: 创建ZeroMQ异步上下文和PUB socket ===
    zmq_context = zmq.asyncio.Context()
    pub_socket = zmq_context.socket(zmq.PUB)
    
    try:
        # 绑定到指定地址
        pub_socket.bind(bind_address)
        print(f"✓ ZeroMQ PUB socket已绑定到 {bind_address}")
        print("  等待订阅者连接...\n")
        
        # 等待一小段时间，让订阅者有机会连接（ZeroMQ的"慢加入"问题）
        await asyncio.sleep(0.5)
        
        # === 步骤2: 并发运行两个任务 ===
        tasks = [
            asyncio.create_task(imu_mod.main(), name="IMU采集"),
            asyncio.create_task(publisher_loop(pub_socket, publish_interval, online_only), name="ZeroMQ发布")
        ]
        
        print("✓ 所有任务已启动，按Ctrl+C停止\n")
        
        # 等待任务完成（实际上会一直运行直到Ctrl+C）
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
        description="双IMU机械臂ZeroMQ发布器 - 将IMU数据发布到MuJoCo仿真环境",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  # 使用默认参数（5Hz发布到localhost:5555）
  python dual_imu_publisher.py
  
  # 自定义发布频率为10Hz（注意：过高频率可能导致仿真卡顿）
  python dual_imu_publisher.py --interval 0.1
  
  # 绑定到所有网络接口（允许其他机器连接）
  python dual_imu_publisher.py --bind tcp://0.0.0.0:5555
  
  # 仅在两个IMU都在线时发布（推荐，避免发布无效数据）
  python dual_imu_publisher.py --online-only
  
  # 组合使用
  python dual_imu_publisher.py --interval 0.1 --online-only

MuJoCo接收端连接方式：
  在MuJoCo程序中使用：
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://localhost:5555")
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    
  接收数据：
    message = socket.recv_string()
    data = json.loads(message)
    position = data["position"]      # [x, y, z] 米
    orientation = data["orientation"] # [roll, pitch, yaw] 度
    gripper = data["gripper"]        # 夹爪状态

频率选择建议：
  - 5Hz  (0.2s): 推荐，与IMU显示频率一致，平衡实时性和稳定性
  - 10Hz (0.1s): 较高实时性，适合快速运动
  - 20Hz (0.05s): 高实时性，可能导致仿真卡顿（取决于仿真复杂度）
  - 注意：IMU原始采集频率为50-200Hz，但无需全部发布

缓冲策略说明：
  本程序采用Latest-only策略（无缓冲队列）：
  - 每次发布时读取最新的IMU数据，丢弃中间帧
  - 适用于实时控制，避免延迟累积
  - 如果需要完整记录所有数据，请修改为队列模式
        """
    )
    parser.add_argument("--interval", "-i", type=float, default=DEFAULT_PUBLISH_INTERVAL,
                        help="发布间隔（秒），默认0.2（5Hz）")
    parser.add_argument("--bind", "-b", type=str, default=DEFAULT_BIND_ADDRESS,
                        help="ZeroMQ绑定地址，默认tcp://127.0.0.1:5555")
    parser.add_argument("--online-only", action="store_true",
                        help="仅在两个IMU都在线时发布数据（推荐启用）")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(main_async(args.bind, args.interval, args.online_only))
    except KeyboardInterrupt:
        print("\n\n✓ 程序已被用户中断")
    finally:
        print("已断开所有连接")
        
        # 绘制轨迹（继承dual_imu_euler的功能）
        if len(imu_mod.trajectory_positions) > 0:
            print("\n正在生成轨迹图...")
            imu_mod.plot_trajectory()
        else:
            print("\n未记录到轨迹数据")


if __name__ == '__main__':
    main()
