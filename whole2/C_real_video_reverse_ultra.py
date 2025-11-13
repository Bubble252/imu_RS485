# C_real_video_reverse.py - 极致优化版本
# 目标延迟: < 500ms

import time
import threading
from datetime import datetime
from zmq_base import TorchSerializer
import zmq
import cv2
import numpy as np
import pickle

# --- 极致优化配置 ---
SERVER_B_HOST = "localhost"
SERVER_B_PORT_COMMAND = 5556
SERVER_B_PORT_VIDEO = 5558

# 摄像头配置 - 极致优化
CAMERA_ID = 0
VIDEO_FPS = 8  # 8 帧/秒
VIDEO_WIDTH = 240  # 极小分辨率
VIDEO_HEIGHT = 180
JPEG_QUALITY = 30  # 极低画质
FRAME_SKIP = 1  # 跳帧：1=不跳帧，2=跳过50%，3=跳过66%
ENABLE_OSD = False  # 禁用 OSD 绘制以节省时间
# ------------

# 全局状态
latest_command = {
    "euler_angles": {"roll": 0, "pitch": 0, "yaw": 0},
    "throttle": 0,
    "timestamp": time.time()
}
command_lock = threading.Lock()


def thread_receive_commands():
    """接收控制命令"""
    global latest_command
    
    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    socket.connect(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_COMMAND}")
    
    print(f"[命令线程] 已连接到 B: {SERVER_B_HOST}:{SERVER_B_PORT_COMMAND}")
    print(f"[命令线程] 等待接收控制命令...")
    
    try:
        while True:
            raw_data = socket.recv()
            command = TorchSerializer.from_bytes(raw_data)
            
            with command_lock:
                latest_command = command
                
    except KeyboardInterrupt:
        pass
    finally:
        socket.close()
        context.term()


def thread_send_video():
    """发送视频流 - 极致优化版"""
    context = zmq.Context()
    
    # 优化的 socket 配置
    socket = context.socket(zmq.PUSH)
    socket.setsockopt(zmq.SNDHWM, 1)  # 只保留1帧
    socket.setsockopt(zmq.LINGER, 0)  # 立即丢弃
    # TCP_NODELAY = 1 (use integer directly, zmq.TCP_NODELAY may not be available)
    try:
        socket.setsockopt(1, 1)  # TCP_NODELAY = 1
    except:
        pass  # 如果不支持就跳过
    # SNDBUF 使用 zmq.SNDBUF
    try:
        socket.setsockopt(zmq.SNDBUF, 32768)  # 减小发送缓冲 (32KB)
    except:
        pass
    socket.connect(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_VIDEO}")
    
    print(f"[视频线程] 已连接到 B: {SERVER_B_HOST}:{SERVER_B_PORT_VIDEO}")
    
    # 打开摄像头
    cap = cv2.VideoCapture(CAMERA_ID)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, VIDEO_FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 最小缓冲
    
    print(f"[视频线程] 摄像头已打开，分辨率: {VIDEO_WIDTH}x{VIDEO_HEIGHT}, FPS: {VIDEO_FPS}")
    print(f"[视频线程] 跳帧策略: 每 {FRAME_SKIP} 帧发送 1 帧")
    
    # JPEG 编码参数
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    
    frame_count = 0
    sent_count = 0
    start_time = time.time()
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[视频] 无法读取帧，尝试重新打开摄像头...")
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(CAMERA_ID)
                continue
            
            frame_count += 1
            
            # 跳帧策略
            if frame_count % FRAME_SKIP != 0:
                continue
            
            # 记录采集时间
            capture_time = time.time()
            
            # JPEG 编码（无 OSD 绘制）
            _, encoded_frame = cv2.imencode('.jpg', frame, encode_param)
            
            # 最小化数据包
            frame_data = {
                "image": encoded_frame.tobytes(),
                "timestamp": capture_time
            }
            
            # 发送 - 强制使用 pickle 以匹配 B 端
            socket.send(pickle.dumps(frame_data, protocol=pickle.HIGHEST_PROTOCOL))
            sent_count += 1
            
            # 统计
            if sent_count % 20 == 0:
                elapsed = time.time() - start_time
                fps = 20 / elapsed
                print(f"[视频] 已发送 {sent_count} 帧, FPS: {fps:.1f}, "
                      f"大小: {len(encoded_frame)} bytes")
                start_time = time.time()
            
            # 控制帧率（实际发送频率）
            time.sleep(1.0 / (VIDEO_FPS / FRAME_SKIP))
            
    except KeyboardInterrupt:
        print("\n[视频线程] 停止中...")
    finally:
        cap.release()
        socket.close()
        context.term()


def main():
    print("============================================================")
    print("服务器 C 启动 - 极致优化版（目标延迟 < 500ms）")
    print("============================================================")
    print(f"分辨率: {VIDEO_WIDTH}x{VIDEO_HEIGHT}")
    print(f"帧率: {VIDEO_FPS} FPS")
    print(f"跳帧: 每 {FRAME_SKIP} 帧")
    print(f"画质: {JPEG_QUALITY}")
    print(f"OSD: {'启用' if ENABLE_OSD else '禁用'}")
    print("============================================================")
    print("")
    
    # 启动线程
    command_thread = threading.Thread(target=thread_receive_commands, daemon=True)
    video_thread = threading.Thread(target=thread_send_video, daemon=True)
    
    command_thread.start()
    video_thread.start()
    
    print("两个线程已启动，按 Ctrl+C 停止...")
    print("")
    
    try:
        command_thread.join()
        video_thread.join()
    except KeyboardInterrupt:
        print("\n\n客户端 C 正在关闭...")
        print("客户端 C 已关闭。")


if __name__ == "__main__":
    main()
