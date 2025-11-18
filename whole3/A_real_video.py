# A_real_video.py - 真实视频显示客户端
import time
import threading
from datetime import datetime
from zmq_base import TorchSerializer
import zmq
import cv2
import numpy as np
import pickle

# --- 配置 ---
# ⚠️ 重要：使用 SSH 隧道连接跳板机 Docker 容器
# 先在另一个终端运行 SSH 隧道命令（见 start_with_ssh_tunnel.sh）
# 然后通过 localhost 连接（SSH 隧道会转发到跳板机）
SERVER_B_HOST = "localhost"  # 通过 SSH 隧道连接
SERVER_B_PORT_COMMAND = 5555  # 发送控制命令
SERVER_B_PORT_VIDEO = 5557    # 接收视频流

# 控制命令配置
COMMAND_RATE_HZ = 50  # 控制命令发送频率
ENABLE_VIDEO_DISPLAY = True  # 是否显示视频窗口
# ------------

def thread_send_commands():
    """
    线程1：持续发送控制命令（欧拉角等）到 B
    """
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.connect(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_COMMAND}")
    
    print(f"[线程1-命令] 连接到 B 的命令端口: {SERVER_B_HOST}:{SERVER_B_PORT_COMMAND}")
    
    # 模拟欧拉角控制命令
    roll, pitch, yaw = 0.0, 0.0, 0.0
    
    try:
        while True:
            # 生成控制命令（模拟欧拉角变化）
            roll = (roll + 0.1) % 360
            pitch = (pitch + 0.2) % 360
            yaw = (yaw + 0.15) % 360
            
            command = {
                "type": "control",
                "timestamp": datetime.now().isoformat(),
                "euler_angles": {
                    "roll": round(roll, 2),
                    "pitch": round(pitch, 2),
                    "yaw": round(yaw, 2)
                },
                "throttle": 0.5
            }
            
            # 发送命令 - 强制使用 pickle 以匹配 B 端
            socket.send(pickle.dumps(command, protocol=pickle.HIGHEST_PROTOCOL))
            
            # 减少打印频率以避免刷屏
            if int(roll * 10) % 10 == 0:  # 每度打印一次
                print(f"[线程1 A→B] 发送命令: 欧拉角({command['euler_angles']['roll']:.2f}, "
                      f"{command['euler_angles']['pitch']:.2f}, {command['euler_angles']['yaw']:.2f})")
            
            # 控制频率
            time.sleep(1.0 / COMMAND_RATE_HZ)
            
    except KeyboardInterrupt:
        pass
    finally:
        socket.close()
        context.term()


def thread_receive_video():
    """
    线程2：持续接收来自 B 的视频流并显示
    """
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.RCVHWM, 1)  # 接收缓冲区只保留1帧
    socket.setsockopt(zmq.CONFLATE, 1)  # 只保留最新消息，丢弃旧帧
    socket.connect(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_VIDEO}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # 订阅所有消息
    
    print(f"[线程2-视频] 订阅 B 的视频流: {SERVER_B_HOST}:{SERVER_B_PORT_VIDEO}")
    
    frame_count = 0
    last_fps_time = time.time()
    fps_counter = 0
    current_fps = 0
    
    # 延迟统计
    latencies = []
    max_latency = 0
    min_latency = float('inf')
    
    # 创建窗口（如果启用显示）
    if ENABLE_VIDEO_DISPLAY:
        cv2.namedWindow('Remote Video Stream', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Remote Video Stream', 800, 600)
    
    try:
        while True:
            # 接收视频帧
            recv_time = time.time()
            video_data = socket.recv()
            frame_dict = TorchSerializer.from_bytes(video_data)
            
            # 计算端到端延迟
            if 'timestamp' in frame_dict:
                latency = (recv_time - frame_dict['timestamp']) * 1000  # 转换为毫秒
                latencies.append(latency)
                max_latency = max(max_latency, latency)
                min_latency = min(min_latency, latency)
                # 只保留最近100个延迟数据
                if len(latencies) > 100:
                    latencies.pop(0)
            
            frame_count += 1
            fps_counter += 1
            
            # 计算 FPS
            current_time = time.time()
            if current_time - last_fps_time >= 1.0:
                current_fps = fps_counter
                fps_counter = 0
                last_fps_time = current_time
            
            # 解码视频帧
            if 'image' in frame_dict and frame_dict.get('encoding') == 'jpeg':
                # JPEG 压缩的图像
                encoded_data = frame_dict['image']
                if isinstance(encoded_data, bytes):
                    nparr = np.frombuffer(encoded_data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        # 计算延迟统计
                        avg_latency = sum(latencies) / len(latencies) if latencies else 0
                        
                        # 在图像上叠加信息
                        cv2.putText(frame, f"FPS: {current_fps}", (10, frame.shape[0] - 20),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                        cv2.putText(frame, f"Frames: {frame_count}", (10, frame.shape[0] - 50),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                        
                        # 延迟信息（右上角）
                        if latencies:
                            cv2.putText(frame, f"Latency: {latencies[-1]:.1f}ms", (frame.shape[1] - 250, 25),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                            cv2.putText(frame, f"Avg: {avg_latency:.1f}ms", (frame.shape[1] - 250, 50),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                            cv2.putText(frame, f"Min/Max: {min_latency:.0f}/{max_latency:.0f}ms", 
                                       (frame.shape[1] - 250, 75),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                        
                        # 显示视频
                        if ENABLE_VIDEO_DISPLAY:
                            cv2.imshow('Remote Video Stream', frame)
                            # 按 'q' 退出
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                print("\n[线程2-视频] 用户按下 'q'，退出...")
                                break
                        
                        # 打印日志（降低频率）
                        if frame_count % 30 == 0:
                            print(f"[线程2 B→A] 收到视频帧 #{frame_count}, "
                                  f"大小: {len(encoded_data)/1024:.1f} KB, "
                                  f"分辨率: {frame_dict.get('resolution', 'N/A')}, "
                                  f"FPS: {current_fps}, "
                                  f"延迟: {latencies[-1]:.1f}ms (平均: {avg_latency:.1f}ms)")
                    else:
                        print(f"[线程2-视频] ⚠️ 解码帧 #{frame_count} 失败")
            else:
                # 纯数据（测试模式）
                if frame_count % 30 == 0:
                    print(f"[线程2 B→A] 收到数据帧 #{frame_count}, "
                          f"大小: {len(video_data)} bytes, "
                          f"分辨率: {frame_dict.get('resolution', 'N/A')}")
            
    except KeyboardInterrupt:
        pass
    finally:
        if ENABLE_VIDEO_DISPLAY:
            cv2.destroyAllWindows()
        socket.close()
        context.term()
        print("[线程2-视频] 视频窗口已关闭")


def run_client_a():
    """
    主函数：启动双线程客户端
    """
    print("=" * 60)
    print("客户端 A 启动 - 真实视频显示模式")
    print("=" * 60)
    print(f"线程1: 发送控制命令 ({COMMAND_RATE_HZ}Hz)")
    print(f"线程2: 接收并显示视频流")
    print(f"视频显示: {'启用' if ENABLE_VIDEO_DISPLAY else '禁用'}")
    print("=" * 60)
    print("\n💡 提示: 在视频窗口按 'q' 键退出\n")
    
    # 启动命令发送线程
    command_thread = threading.Thread(target=thread_send_commands, daemon=True)
    command_thread.start()
    
    # 启动视频接收线程
    video_thread = threading.Thread(target=thread_receive_video, daemon=True)
    video_thread.start()
    
    print("客户端运行中，按 Ctrl+C 退出\n")
    
    try:
        command_thread.join()
        video_thread.join()
    except KeyboardInterrupt:
        print("\n\n客户端 A 正在关闭...")
        print("客户端 A 已关闭。")


if __name__ == "__main__":
    run_client_a()
