#!/usr/bin/env python
# coding:UTF-8
"""
三IMU欧拉角读取 + ZeroMQ发布程序 (RS485版本 - 双PUSH架构 + 音频接收播放)
基于RS485串口连接三个WIT IMU传感器，实时读取欧拉角并发布到B端和本地LeRobot

功能说明：
1. 通过RS485连接三个IMU传感器，实时读取欧拉角
   - 设备1 (0x50): 杆1 (IMU1)
   - 设备2 (0x51): 杆2 (IMU2)
   - 设备3 (0x52): 机械爪 (IMU3)
2. 计算两杆串联机械臂的末端位置（IMU1 + IMU2）
3. 读取机械爪的姿态（IMU3）
4. 键盘控制夹爪开合（按键1打开，按键2闭合）
5. 通过ZeroMQ双PUSH socket发布数据（参考A_real_video.py）
   - PUSH → B端:5555 (转发到C端和保存LeRobot数据集)
   - PUSH → 本地LeRobot:5559 (MuJoCo实时仿真)
6. 通过ZeroMQ SUB socket接收B端视频流+音频流（可选）
7. 音频接收和播放（Opus解码，实时扬声器输出）
8. 发布频率默认5Hz

数据流架构（参考A_real_video.py + B_reverse_whole.py）：
    IMU1 (0x50/RS485) ──┐
                         ├──> 运动学计算 ──> 末端位置
    IMU2 (0x51/RS485) ──┘                        ↓
    IMU3 (0x52/RS485) ──────> 机械爪姿态  ────────┴──> 数据打包
    键盘按键1/2 ──────────> 夹爪控制 ────────────┘          ↓
                                                    ┌──────┴──────┐
                                                    │             │
                                         PUSH → B端:5555    PUSH → 本地:5559
                                                ↓                  ↓
                                           转发到C端         MuJoCo仿真
                                         LeRobot保存      (lerobot_zeroMQ_imu.py)
    
    视频流: B端:5557 (PUB) ──SUB──> 本地显示（可选）

ZeroMQ通信模式（与B_reverse_whole.py兼容）：
    发送端（A端，本文件）:
      - socket_to_b (PUSH): connect到B的5555端口
      - socket_to_lerobot (PUSH): connect到本地5559端口
      - video_receiver (SUB): connect到B的5557端口（可选）
    
    接收端（B端，B_reverse_whole.py）:
      - 5555端口 (PULL): bind，接收A的传感器数据
      - 5557端口 (PUB): bind，发送视频给A
      - 5556端口 (PUSH): connect到C
      - 5558端口 (PULL): bind，接收C的数据
    
    接收端（本地LeRobot，lerobot_zeroMQ_imu.py）:
      - 5559端口 (PULL): bind，接收A的传感器数据

运行方法：
    # 使用默认参数（发送到B端5555和本地5559）
    python triple_imu_rs485_publisher.py --online-only
    
    # 完整示例（远程B端 + 本地LeRobot + 视频）
    python triple_imu_rs485_publisher.py --online-only \\
           --b-host 192.168.1.100 --b-port 5555 \\
           --lerobot-host localhost --lerobot-port 5559 \\
           --enable-video --video-host 192.168.1.100 --video-port 5557

键盘控制：
    按键 '1' - 夹爪慢慢打开 (gripper值增加0.01，范围0.0-1.0)
    按键 '2' - 夹爪慢慢闭合 (gripper值减少0.01，范围0.0-1.0)
    按键 'q' - 退出程序
"""
import time
import json
import argparse
import numpy as np
import zmq
import threading
from collections import deque
from scipy.spatial.transform import Rotation
import sys
import select
import termios
import tty
import pickle
import cv2

import device_model

# === 音频相关导入 ===
try:
    import sounddevice as sd
    import queue
    AUDIO_AVAILABLE = True
except ImportError:
    print("⚠️ sounddevice 未安装，音频播放功能将被禁用")
    print("安装方法: pip install sounddevice")
    AUDIO_AVAILABLE = False
    sd = None
    queue = None

try:
    import opuslib
    OPUS_AVAILABLE = True
except ImportError:
    print("⚠️ opuslib 未安装，音频解码功能将被禁用")
    print("安装方法: pip install opuslib")
    OPUS_AVAILABLE = False
    opuslib = None

# === 机械臂参数配置 ===
L1 = 0.25  # 杆1长度（米）
L2 = 0.27  # 杆2长度（米）

# === IMU设备地址配置 ===
IMU1_ADDR = 0x50  # 80 - 杆1
IMU2_ADDR = 0x51  # 81 - 杆2
IMU3_ADDR = 0x52  # 82 - 机械爪

# === ZeroMQ默认配置（参考A_real_video.py双线程架构）===
# 发送传感器数据到B端（PUSH模式，匹配B_reverse_whole.py的PULL socket）
DEFAULT_B_HOST = "localhost"
DEFAULT_B_PORT_COMMAND = 5555  # 发送传感器数据到B端（对应B的SERVER_B_PORT_FOR_A_COMMAND）

# 发送传感器数据到本地LeRobot（PUSH模式）
DEFAULT_LEROBOT_HOST = "localhost"
DEFAULT_LEROBOT_PORT = 5559  # 本地LeRobot接收端口（独立端口避免冲突）

# 发送调试数据到Web UI后端（PUB模式）
DEFAULT_DEBUG_PORT = 5560  # 调试数据发布端口（给debug_server.py订阅）

# 接收B端视频流（SUB模式，对应B的SERVER_B_PORT_FOR_A_VIDEO）
DEFAULT_VIDEO_HOST = "localhost"
DEFAULT_VIDEO_PORT = 5557  # 从B端接收视频流

# 接收B端音频流（SUB模式，独立端口）
DEFAULT_AUDIO_HOST = "localhost"
DEFAULT_AUDIO_PORT = 5561  # 从B端接收音频流（独立）

DEFAULT_PUBLISH_INTERVAL = 0.05  # 20Hz
ENABLE_VIDEO_DISPLAY = True  # 是否显示视频窗口（默认关闭，避免阻塞）

# === 音频配置 ===
AUDIO_SAMPLE_RATE = 48000      # 48kHz 采样率（设备支持）
AUDIO_CHANNELS = 1              # 单声道
AUDIO_BUFFER_SIZE = 5           # 音频缓冲队列大小（帧数），用于平滑网络抖动
OPUS_FRAME_SIZE = 2880         # Opus 帧大小（60ms @ 48kHz）
AUDIO_ENABLED = AUDIO_AVAILABLE and OPUS_AVAILABLE  # 音频功能是否可用

# === Yaw归零模式 ===
YAW_NORMALIZATION_MODE = "NORMAL"  # "NORMAL": 首次数据归零, "AUTO": 智能偏置, "SIMPLE": ±180翻转, "OFF": 不归零
YAW_NORMALIZATION_THRESHOLD = 100.0  # Yaw角超过±100度时判定为边界初始化

# === 坐标映射参数配置 ===
# 机械臂原始工作空间范围（米）
X_RAW_MIN = 0.39
X_RAW_MAX = 0.52
Y_RAW_MIN = -0.4
Y_RAW_MAX = 0.4
Z_RAW_MIN = 0.0
Z_RAW_MAX = 0.3

# MuJoCo目标空间范围（米）
X_TARGET_MIN = 0.22
X_TARGET_MAX = 0.42
Y_TARGET_MIN = -0.2
Y_TARGET_MAX = 0.2
Z_TARGET_MIN = 0.1
Z_TARGET_MAX = 0.4

# === 全局变量存储最新IMU数据 ===
imu_data_lock = threading.Lock()

# IMU欧拉角数据（度）
imu1_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
imu2_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
imu3_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}

# IMU最后更新时间戳
imu1_last_update = 0.0
imu2_last_update = 0.0
imu3_last_update = 0.0

# Yaw归零偏移量
imu1_yaw_offset = None
imu2_yaw_offset = None
imu3_yaw_offset = None

# 首次数据标志（用于打印调试信息）
imu1_first_valid_data = False
imu2_first_valid_data = False
imu3_first_valid_data = False

# 首次有效数据记录（用于程序结束时回顾）
imu1_first_data = None
imu2_first_data = None
imu3_first_data = None

# 轨迹记录
trajectory_positions = deque(maxlen=1000)
trajectory_timestamps = deque(maxlen=1000)

# === 夹爪控制参数 ===
gripper_value = 0.0  # 夹爪开合值 (0.0 = 完全闭合, 1.0 = 完全打开)
gripper_lock = threading.Lock()
GRIPPER_STEP = 0.005  # 每次调整的步长（减小以提高平滑度）
GRIPPER_UPDATE_RATE = 0.02  # 更新频率（秒），50Hz更新

# === 键盘监听状态 ===
keyboard_thread_running = False
original_terminal_settings = None
current_key = None  # 当前按下的键
last_key_time = 0.0  # 最后一次按键时间
KEY_TIMEOUT = 0.1  # 按键超时时间（秒）- 超过此时间视为松开

# === 视频接收状态 ===
video_thread_running = False
video_frame_count = 0
video_last_latency = 0.0
latest_video_left = None    # 最新的左腕摄像头JPEG数据
latest_video_top = None     # 最新的顶部摄像头JPEG数据
video_lock = threading.Lock()  # 视频帧访问锁

# === 音频接收和播放状态 ===
audio_thread_running = False
audio_frame_count = 0
audio_buffer_queue = None  # 音频缓冲队列（queue.Queue）
audio_opus_decoder = None  # Opus 解码器
audio_stream = None        # sounddevice 音频流


def keyboard_listener():
    """
    键盘输入检测线程 - 持续读取按键
    """
    global current_key, last_key_time, keyboard_thread_running, original_terminal_settings
    
    # 保存原始终端设置
    try:
        original_terminal_settings = termios.tcgetattr(sys.stdin)
        # 设置终端为非缓冲模式
        tty.setcbreak(sys.stdin.fileno())
    except:
        print("⚠️  无法设置终端模式，键盘控制可能不可用")
        return
    
    print("\n" + "="*70)
    print("键盘控制已启用（实时响应模式）:")
    print("  按住 '1' - 夹爪持续打开")
    print("  按住 '2' - 夹爪持续闭合")
    print("  松开按键 - 立刻停止（100ms内无重复按键）")
    print("  按 'q' - 退出程序")
    print("="*70 + "\n")
    
    try:
        while keyboard_thread_running:
            # 非阻塞检查是否有按键输入
            if select.select([sys.stdin], [], [], 0.001)[0]:  # 1ms超时
                key = sys.stdin.read(1)
                
                if key in ['1', '2']:
                    current_key = key
                    last_key_time = time.time()
                elif key == 'q' or key == 'Q':
                    print("\n⚠️  检测到退出键 'q'，程序即将退出...")
                    keyboard_thread_running = False
                    break
            
            time.sleep(0.001)  # 1ms循环
    
    finally:
        # 恢复终端设置
        if original_terminal_settings:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_terminal_settings)
            except:
                pass


def gripper_update_thread():
    """
    夹爪更新线程 - 根据按键状态持续更新夹爪值
    """
    global gripper_value, current_key, last_key_time, keyboard_thread_running
    
    last_print_value = 0.0
    
    while keyboard_thread_running:
        current_time = time.time()
        
        # 检查按键是否超时（视为松开）
        if current_time - last_key_time > KEY_TIMEOUT:
            current_key = None
        
        # 根据当前按键更新夹爪值
        with gripper_lock:
            old_value = gripper_value
            
            if current_key == '1':
                # 夹爪打开
                gripper_value = min(1.0, gripper_value + GRIPPER_STEP)
            elif current_key == '2':
                # 夹爪闭合
                gripper_value = max(0.0, gripper_value - GRIPPER_STEP)
            
            # 只在值有明显变化时打印（减少输出噪音）
            if abs(gripper_value - last_print_value) > 0.01:
                if current_key == '1':
                    print(f"\r🔧 夹爪 ↑ 打开: {gripper_value:.3f} ({gripper_value*100:.1f}%)   ", end='', flush=True)
                    last_print_value = gripper_value
                elif current_key == '2':
                    print(f"\r🔧 夹爪 ↓ 闭合: {gripper_value:.3f} ({gripper_value*100:.1f}%)   ", end='', flush=True)
                    last_print_value = gripper_value
            
            # 检测到松开（从有按键变为无按键）
            if current_key is None and old_value != gripper_value:
                # 已经停止变化了，不需要额外打印
                pass
        
        time.sleep(GRIPPER_UPDATE_RATE)
    
    print()  # 换行


def video_receiver_thread(video_host="localhost", video_port=5557):
    """
    视频接收线程 - 从B端接收视频流（支持双摄像头：left_wrist + top）
    """
    global video_thread_running, video_frame_count, video_last_latency
    global latest_video_left, latest_video_top, video_lock
    
    print(f"\n📹 启动视频接收线程（双摄像头模式）: {video_host}:{video_port}")
    
    try:
        # 创建独立的ZMQ上下文（避免与发布端冲突）
        video_context = zmq.Context()
        video_socket = video_context.socket(zmq.SUB)
        video_socket.setsockopt(zmq.RCVHWM, 1)  # 接收缓冲区只保留1帧
        video_socket.setsockopt(zmq.CONFLATE, 1)  # 只保留最新消息，丢弃旧帧
        video_socket.connect(f"tcp://{video_host}:{video_port}")
        video_socket.setsockopt_string(zmq.SUBSCRIBE, "")  # 订阅所有消息
        
        print(f"✓ 视频接收已连接到 {video_host}:{video_port}")
        
        # 创建双摄像头窗口（如果启用显示）
        if ENABLE_VIDEO_DISPLAY:
            try:
                cv2.namedWindow('Left Wrist Camera', cv2.WINDOW_NORMAL)
                cv2.resizeWindow('Left Wrist Camera', 640, 480)
                cv2.namedWindow('Top Camera', cv2.WINDOW_NORMAL)
                cv2.resizeWindow('Top Camera', 640, 480)
                print("✓ OpenCV双摄像头窗口已创建（Left Wrist + Top）")
            except Exception as e:
                print(f"⚠️  OpenCV窗口创建失败（可能无显示环境）: {e}")
        
        while video_thread_running:
            try:
                # 非阻塞接收（1秒超时）
                if video_socket.poll(1000):
                    recv_time = time.time()
                    video_data = video_socket.recv()
                    
                    # 尝试反序列化（支持pickle和JSON）
                    try:
                        # 优先尝试pickle（A_real_video.py使用pickle）
                        frame_dict = pickle.loads(video_data)
                    except:
                        try:
                            # 回退到JSON
                            frame_dict = json.loads(video_data.decode('utf-8'))
                        except:
                            print("⚠️  视频数据反序列化失败")
                            continue
                    
                    video_frame_count += 1
                    
                    # 计算延迟
                    if 'timestamp' in frame_dict:
                        video_last_latency = (recv_time - frame_dict['timestamp']) * 1000  # ms
                    
                    # 保存和解码双摄像头视频帧
                    if frame_dict.get('encoding') == 'jpeg':
                        try:
                            # 处理左腕摄像头
                            if 'image.left_wrist' in frame_dict:
                                encoded_data_left = frame_dict['image.left_wrist']
                                if isinstance(encoded_data_left, bytes):
                                    # 保存到全局变量供PyQt5 UI使用
                                    with video_lock:
                                        latest_video_left = encoded_data_left
                                    
                                    # OpenCV显示（如果启用）
                                    if ENABLE_VIDEO_DISPLAY:
                                        nparr_left = np.frombuffer(encoded_data_left, np.uint8)
                                        frame_left = cv2.imdecode(nparr_left, cv2.IMREAD_COLOR)
                                        
                                        if frame_left is not None:
                                            # 叠加信息
                                            cv2.putText(frame_left, f"Left Wrist - Frame: {video_frame_count}", 
                                                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                                                       0.6, (0, 255, 255), 2)
                                            if video_last_latency > 0:
                                                cv2.putText(frame_left, f"Latency: {video_last_latency:.1f}ms", 
                                                           (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 
                                                           0.6, (0, 255, 0), 2)
                                            
                                            cv2.imshow('Left Wrist Camera', frame_left)
                            
                            # 处理顶部摄像头
                            if 'image.top' in frame_dict:
                                encoded_data_top = frame_dict['image.top']
                                if isinstance(encoded_data_top, bytes):
                                    # 保存到全局变量供PyQt5 UI使用
                                    with video_lock:
                                        latest_video_top = encoded_data_top
                                    
                                    # OpenCV显示（如果启用）
                                    if ENABLE_VIDEO_DISPLAY:
                                        nparr_top = np.frombuffer(encoded_data_top, np.uint8)
                                        frame_top = cv2.imdecode(nparr_top, cv2.IMREAD_COLOR)
                                        
                                        if frame_top is not None:
                                            # 叠加信息
                                            cv2.putText(frame_top, f"Top - Frame: {video_frame_count}", 
                                                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                                                       0.6, (0, 255, 255), 2)
                                            if video_last_latency > 0:
                                                cv2.putText(frame_top, f"Latency: {video_last_latency:.1f}ms", 
                                                           (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 
                                                           0.6, (0, 255, 0), 2)
                                            
                                            cv2.imshow('Top Camera', frame_top)
                            
                            # 按 'q' 退出（仅在OpenCV显示模式）
                            if ENABLE_VIDEO_DISPLAY:
                                if cv2.waitKey(1) & 0xFF == ord('q'):
                                    print("\n⚠️  视频窗口按下'q'，退出...")
                                    video_thread_running = False
                                    break
                                
                        except Exception as e:
                            if video_frame_count % 30 == 0:
                                print(f"⚠️  视频解码失败: {e}")
                    
                    # 音频已由独立线程处理，这里只处理视频
                    
                    # 每30帧打印一次日志
                    if video_frame_count % 30 == 0:
                        latency_str = f"{video_last_latency:.1f}ms" if video_last_latency > 0 else "N/A"
                        cameras_info = []
                        if 'image.left_wrist' in frame_dict:
                            cameras_info.append("left_wrist")
                        if 'image.top' in frame_dict:
                            cameras_info.append("top")
                        cameras_str = "+".join(cameras_info) if cameras_info else "N/A"
                        print(f"📹 [视频] 接收帧 #{video_frame_count}, 摄像头: [{cameras_str}], 延迟: {latency_str}")
            
            except zmq.Again:
                # 超时，继续循环
                time.sleep(0.01)
            except Exception as e:
                print(f"⚠️  视频接收错误: {e}")
                time.sleep(0.1)
        
    except Exception as e:
        print(f"❌ 视频接收线程异常: {e}")
    finally:
        if ENABLE_VIDEO_DISPLAY:
            try:
                cv2.destroyAllWindows()
            except:
                pass
        try:
            video_socket.close()
            video_context.term()
        except:
            pass
        print("✓ 视频接收线程已退出")


def audio_receiver_thread(audio_host="localhost", audio_port=5561):
    """
    音频接收线程 - 从独立端口接收 Opus 音频流
    
    工作流程：
    1. 从 B 端独立音频端口接收 Opus 编码数据
    2. 放入 audio_buffer_queue 供播放线程使用
    
    独立音频流的优势：
    - 不受视频帧率限制
    - 更低延迟
    - 更稳定的音频质量
    """
    global audio_frame_count, audio_buffer_queue
    
    if not AUDIO_ENABLED or audio_buffer_queue is None:
        print("⚠️  音频功能未启用，音频接收线程退出")
        return
    
    print(f"\n🔊 启动音频接收线程: {audio_host}:{audio_port}")
    
    context = zmq.Context()
    audio_socket = None
    
    try:
        audio_socket = context.socket(zmq.SUB)
        audio_socket.setsockopt(zmq.SUBSCRIBE, b'')
        audio_socket.setsockopt(zmq.RCVHWM, 100)
        audio_socket.setsockopt(zmq.CONFLATE, 0)  # 不要合并消息
        
        audio_socket.connect(f"tcp://{audio_host}:{audio_port}")
        
        print(f"✓ 音频接收已连接到 {audio_host}:{audio_port}")
        print(f"   接收模式: 独立音频流 (Opus 编码)")
        
        while audio_thread_running:
            try:
                # 接收音频数据
                audio_packet = audio_socket.recv()
                
                # 反序列化
                audio_data = pickle.loads(audio_packet)
                
                if isinstance(audio_data, dict) and 'data' in audio_data:
                    # 提取 Opus 编码数据
                    opus_bytes = audio_data['data']
                    
                    if isinstance(opus_bytes, bytes) and len(opus_bytes) > 0:
                        try:
                            audio_buffer_queue.put_nowait(opus_bytes)
                            audio_frame_count += 1
                            
                            if audio_frame_count % 100 == 0:
                                queue_size = audio_buffer_queue.qsize()
                                print(f"🔊 音频接收: {audio_frame_count} 帧, "
                                      f"队列: {queue_size}/{AUDIO_BUFFER_SIZE}, "
                                      f"编码: {audio_data.get('codec', 'unknown')}")
                        except:
                            # 队列满，丢弃
                            if audio_frame_count % 200 == 0:
                                print("⚠️  音频缓冲队列已满，丢弃旧帧")
                            
            except zmq.Again:
                time.sleep(0.001)
            except Exception as e:
                if audio_frame_count % 100 == 0:
                    print(f"⚠️  音频接收错误: {e}")
                time.sleep(0.01)
                
    except Exception as e:
        print(f"❌ 音频接收线程错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if audio_socket:
            try:
                audio_socket.close()
            except:
                pass
        try:
            context.term()
        except:
            pass
        print("✓ 音频接收线程已退出")


def audio_player_thread():
    """
    音频播放线程 - Opus 解码并通过扬声器播放
    
    工作流程：
    1. 从 audio_buffer_queue 获取 Opus 编码的音频数据
    2. 使用 opuslib.Decoder 解码为 PCM
    3. 通过 sounddevice 实时播放
    """
    global audio_thread_running, audio_opus_decoder, audio_stream
    
    if not AUDIO_ENABLED:
        print("⚠️  音频功能未启用（缺少 sounddevice 或 opuslib）")
        return
    
    print(f"\n🔊 启动音频播放线程")
    print(f"   采样率: {AUDIO_SAMPLE_RATE} Hz")
    print(f"   声道: {AUDIO_CHANNELS}")
    print(f"   帧大小: {OPUS_FRAME_SIZE} 样本 ({OPUS_FRAME_SIZE/AUDIO_SAMPLE_RATE*1000:.0f}ms)")
    print(f"   缓冲大小: {AUDIO_BUFFER_SIZE} 帧")
    
    try:
        # 创建 Opus 解码器
        audio_opus_decoder = opuslib.Decoder(AUDIO_SAMPLE_RATE, AUDIO_CHANNELS)
        print("✓ Opus 解码器已创建")
        
        # 列出可用音频设备
        print("\n可用音频输出设备:")
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev['max_output_channels'] > 0:
                default = " (默认)" if i == sd.default.device[1] else ""
                print(f"  [{i}] {dev['name']} (输出声道: {dev['max_output_channels']}){default}")
        
        # 打开音频输出流
        audio_stream = sd.OutputStream(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            dtype='int16',
            blocksize=OPUS_FRAME_SIZE,
        )
        audio_stream.start()
        print(f"✓ 音频输出流已启动\n")
        
        decoded_count = 0
        underrun_count = 0
        
        while audio_thread_running:
            try:
                # 从队列获取 Opus 编码数据（阻塞，1秒超时）
                opus_bytes = audio_buffer_queue.get(timeout=1.0)
                
                # Opus 解码
                pcm_data = audio_opus_decoder.decode(opus_bytes, OPUS_FRAME_SIZE)
                
                # 转换为 numpy array
                audio_array = np.frombuffer(pcm_data, dtype=np.int16)
                
                # 播放音频
                audio_stream.write(audio_array)
                
                decoded_count += 1
                
                # 统计信息
                if decoded_count % 50 == 0:
                    queue_size = audio_buffer_queue.qsize()
                    print(f"🔊 音频播放: {decoded_count} 帧, "
                          f"队列: {queue_size}/{AUDIO_BUFFER_SIZE}, "
                          f"下溢: {underrun_count}")
                
            except Exception as e:
                if "Empty" in str(e):
                    # 队列为空（正常情况，等待新数据）
                    underrun_count += 1
                    if underrun_count % 10 == 0:
                        print(f"⚠️  音频缓冲下溢（{underrun_count} 次），等待数据...")
                else:
                    if decoded_count % 20 == 0:
                        print(f"⚠️  音频解码/播放失败: {e}")
                time.sleep(0.01)
    
    except Exception as e:
        print(f"❌ 音频播放线程异常: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理资源
        if audio_stream:
            try:
                audio_stream.stop()
                audio_stream.close()
            except:
                pass
        print("✓ 音频播放线程已退出")


def debug_publisher_thread(debug_port=5560):
    """
    调试数据发布线程 - 发送实时数据给PyQt5 UI（独立运行，不影响主逻辑）
    
    发布格式：Pickle over ZeroMQ PUB（包含视频帧）
    端口：5560（默认）
    频率：20Hz（避免UI过载）
    
    数据结构：
    {
        "timestamp": 当前时间戳,
        "imu1/2/3": {"roll": ..., "pitch": ..., "yaw": ...},
        "position": {"raw": [x,y,z], "mapped": [x,y,z]},
        "gripper": 0.0-1.0,
        "online_status": {"imu1": true/false, ...},
        "stats": {"publish_rate": ..., "message_count": ...},
        "video_left": <JPEG bytes or None>,
        "video_top": <JPEG bytes or None>
    }
    """
    global imu1_euler, imu2_euler, imu3_euler, gripper_value
    global imu1_last_update, imu2_last_update, imu3_last_update
    global latest_video_left, latest_video_top, video_lock
    
    print(f"\n🔧 启动调试数据发布线程: tcp://*:{debug_port}")
    
    try:
        # 创建独立的ZMQ上下文（避免与主线程冲突）
        debug_context = zmq.Context()
        debug_socket = debug_context.socket(zmq.PUB)
        debug_socket.bind(f"tcp://*:{debug_port}")
        
        print(f"✓ 调试数据PUB socket已绑定到端口 {debug_port}")
        
        # 等待订阅者连接（ZeroMQ PUB需要短暂延迟）
        time.sleep(0.5)
        
        publish_count = 0
        last_position_raw = [0.0, 0.0, 0.0]
        last_position_mapped = [0.0, 0.0, 0.0]
        last_publish_rate = 0.0
        
        while True:
            try:
                current_time = time.time()
                
                # === 读取最新IMU数据 ===
                with imu_data_lock:
                    euler1 = imu1_euler.copy()
                    euler2 = imu2_euler.copy()
                    euler3 = imu3_euler.copy()
                    
                    # 在线状态检查
                    imu1_online = (current_time - imu1_last_update) < 1.0 if imu1_last_update > 0 else False
                    imu2_online = (current_time - imu2_last_update) < 1.0 if imu2_last_update > 0 else False
                    imu3_online = (current_time - imu3_last_update) < 1.0 if imu3_last_update > 0 else False
                
                # === 计算末端位置 ===
                try:
                    end_pos, link1_pos, link2_pos = calculate_end_effector_position(euler1, euler2)
                    
                    # 坐标映射
                    x_raw = float(np.clip(end_pos[0], X_RAW_MIN, X_RAW_MAX))
                    y_raw = float(np.clip(end_pos[1], Y_RAW_MIN, Y_RAW_MAX))
                    z_raw = float(np.clip(end_pos[2], Z_RAW_MIN, Z_RAW_MAX))
                    
                    x_mapped = float(X_TARGET_MIN + (x_raw - X_RAW_MIN) / (X_RAW_MAX - X_RAW_MIN) * (X_TARGET_MAX - X_TARGET_MIN))
                    y_mapped = float(Y_TARGET_MIN + (y_raw - Y_RAW_MIN) / (Y_RAW_MAX - Y_RAW_MIN) * (Y_TARGET_MAX - Y_TARGET_MIN))
                    z_mapped = float(Z_TARGET_MIN + (z_raw - Z_RAW_MIN) / (Z_RAW_MAX - Z_RAW_MIN) * (Z_TARGET_MAX - Z_TARGET_MIN))
                    
                    last_position_raw = [x_raw, y_raw, z_raw]
                    last_position_mapped = [x_mapped, y_mapped, z_mapped]
                except Exception as e:
                    # 计算失败时使用上次的值
                    pass
                
                # === 读取夹爪值 ===
                with gripper_lock:
                    current_gripper = float(gripper_value)
                
                # === 读取最新视频帧 ===
                with video_lock:
                    current_video_left = latest_video_left
                    current_video_top = latest_video_top
                
                # === 构造调试数据包 ===
                debug_data = {
                    "timestamp": current_time,
                    "imu1": {
                        "roll": float(euler1["roll"]),
                        "pitch": float(euler1["pitch"]),
                        "yaw": float(euler1["yaw"])
                    },
                    "imu2": {
                        "roll": float(euler2["roll"]),
                        "pitch": float(euler2["pitch"]),
                        "yaw": float(euler2["yaw"])
                    },
                    "imu3": {
                        "roll": float(euler3["roll"]),
                        "pitch": float(euler3["pitch"]),
                        "yaw": float(euler3["yaw"])
                    },
                    "position": {
                        "raw": last_position_raw,
                        "mapped": last_position_mapped
                    },
                    "gripper": current_gripper,
                    "online_status": {
                        "imu1": imu1_online,
                        "imu2": imu2_online,
                        "imu3": imu3_online
                    },
                    "stats": {
                        "publish_count": publish_count,
                        "publish_rate": last_publish_rate,
                        "video_frame_count": video_frame_count,
                        "video_latency": video_last_latency
                    },
                    "config": {
                        "L1": L1,
                        "L2": L2,
                        "yaw_mode": YAW_NORMALIZATION_MODE
                    },
                    "video_left": current_video_left,  # JPEG bytes or None
                    "video_top": current_video_top     # JPEG bytes or None
                }
                
                # === 发送Pickle数据（支持bytes类型）===
                debug_socket.send_pyobj(debug_data)
                publish_count += 1
                
                # 每50次打印一次日志（避免刷屏）
                if publish_count % 50 == 0:
                    last_publish_rate = 50 / 2.5  # 20Hz
                    # print(f"🔧 [调试] 已发送 {publish_count} 条数据, IMU在线: {imu1_online}/{imu2_online}/{imu3_online}")
                
                # 20Hz发布频率
                time.sleep(0.05)
                
            except Exception as e:
                print(f"⚠️  调试数据发送失败: {e}")
                time.sleep(0.1)
    
    except Exception as e:
        print(f"❌ 调试数据发布线程异常: {e}")
    finally:
        try:
            debug_socket.close()
            debug_context.term()
        except:
            pass
        print("✓ 调试数据发布线程已退出")


def normalize_angle(angle):
    """将角度归一化到 [-180, 180] 范围"""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def normalize_yaw_angle(yaw_raw, yaw_offset, imu_name="IMU"):
    """
    归一化Yaw角到0附近的正常范围（借鉴dual_imu_euler.py）
    
    模式说明：
    - NORMAL: 首次有效数据归零模式，第一帧记录偏置并归零，后续帧减去偏置，保持在[-180°, +180°]
    - AUTO: 智能偏置模式，自动检测初始化位置（0附近或180附近），智能设置偏置
    - SIMPLE: 简单模式，直接将超过±100°的值翻转180°
    - OFF: 不进行归零，直接返回原始值
    
    参数:
        yaw_raw: 原始Yaw角（-180° ~ +180°）
        yaw_offset: 初始偏置（None表示第一帧，需要记录）
        imu_name: IMU名称（用于调试输出）
    
    返回:
        yaw_normalized: 归一化后的Yaw角
        new_offset: 更新后的偏置（仅AUTO和NORMAL模式下有效）
    """
    # OFF模式：不归零
    if YAW_NORMALIZATION_MODE == "OFF":
        if yaw_raw < 0:
            yaw_raw += 180
        elif yaw_raw > 0:
            yaw_raw -= 180
        return yaw_raw, 0.0
    
    # SIMPLE模式：简单翻转
    if YAW_NORMALIZATION_MODE == "SIMPLE":
        yaw_normalized = yaw_raw
        # 如果超过±100°，直接加减180°翻转到另一侧
        if yaw_raw > YAW_NORMALIZATION_THRESHOLD:
            yaw_normalized = yaw_raw - 180.0
        elif yaw_raw < -YAW_NORMALIZATION_THRESHOLD:
            yaw_normalized = yaw_raw + 180.0
        return yaw_normalized, 0.0
    
    # NORMAL模式：首次数据归零（推荐）
    if YAW_NORMALIZATION_MODE == "NORMAL":
        # 第一帧：记录偏置
        if yaw_offset is None:
            yaw_offset = yaw_raw
            print(f"🔧 [{imu_name}] [NORMAL] 首次Yaw数据归零: 原始值={yaw_raw:.2f}°, 偏置={yaw_offset:.2f}°")
            return 0.0, yaw_offset  # 第一帧归零
        
        # 后续帧：减去偏置
        yaw_normalized = yaw_raw - yaw_offset
        
        # 处理跨越±180°边界的情况，保持在[-180°, +180°]
        if yaw_normalized > 180.0:
            yaw_normalized -= 360.0
        elif yaw_normalized < -180.0:
            yaw_normalized += 360.0
        
        return yaw_normalized, yaw_offset
    
    # AUTO模式：智能偏置
    # 第一帧：记录初始偏置
    if yaw_offset is None:
        # 如果初始值接近±180°，说明初始化在180附近
        if abs(yaw_raw) > YAW_NORMALIZATION_THRESHOLD:
            # 偏置设为±180°，归一化后从0开始
            yaw_offset = 180.0 if yaw_raw > 0 else -180.0
            print(f"🔧 [{imu_name}] [AUTO] 检测到Yaw初始化在边界附近: 原始值={yaw_raw:.2f}°, 偏置={yaw_offset:.2f}°")
        else:
            # 偏置设为当前值，归一化后从0开始
            yaw_offset = yaw_raw
            print(f"🔧 [{imu_name}] [AUTO] 检测到Yaw初始化在0附近: 原始值={yaw_raw:.2f}°, 偏置={yaw_offset:.2f}°")
        
        return 0.0, yaw_offset  # 第一帧归零
    
    # 后续帧：减去偏置
    yaw_normalized = yaw_raw - yaw_offset
    
    # 处理跨越±180°边界的情况
    if yaw_normalized > 180.0:
        yaw_normalized -= 360.0
    elif yaw_normalized < -180.0:
        yaw_normalized += 360.0
    
    return yaw_normalized, yaw_offset


def calculate_end_effector_position(euler1, euler2):
    """
    计算两杆串联机械臂的末端位置（完整3D运动学，借鉴dual_imu_euler.py）
    
    参数：
        euler1: IMU1的欧拉角字典 {"roll": ..., "pitch": ..., "yaw": ...} (度)
        euler2: IMU2的欧拉角字典 {"roll": ..., "pitch": ..., "yaw": ...} (度)
    
    返回：
        end_pos: 末端位置 [x, y, z]（米）
        link1_pos: 杆1末端位置 [x, y, z]（米）
        link2_pos: 杆2末端位置 [x, y, z]（米）
    
    公式:
        末端位置 = R1 @ [L1, 0, 0]^T + R2 @ [L2, 0, 0]^T
        其中 R1, R2 是由欧拉角 (XYZ顺序) 构建的旋转矩阵
    """
    # 将欧拉角从度转换为弧度
    roll1_rad = np.deg2rad(euler1["roll"])
    pitch1_rad = np.deg2rad(euler1["pitch"])
    yaw1_rad = np.deg2rad(euler1["yaw"])
    
    roll2_rad = np.deg2rad(euler2["roll"])
    pitch2_rad = np.deg2rad(euler2["pitch"])
    yaw2_rad = np.deg2rad(euler2["yaw"])
    
    # 构建旋转矩阵 (使用XYZ欧拉角顺序，与IMU输出一致)
    R1 = Rotation.from_euler('xyz', [roll1_rad, pitch1_rad, yaw1_rad]).as_matrix()
    R2 = Rotation.from_euler('xyz', [roll2_rad, pitch2_rad, yaw2_rad]).as_matrix()
    
    # 杆1和杆2在各自局部坐标系下的向量 (沿x轴)
    link1_local = np.array([L1, 0.0, 0.0])
    link2_local = np.array([L2, 0.0, 0.0])
    
    # 转换到世界坐标系
    link1_world = R1 @ link1_local
    link2_world = R2 @ link2_local
    
    # 末端位置 = 杆1末端 + 杆2末端
    end_pos = link1_world + link2_world
    
    return end_pos, link1_world, link2_world


def data_callback(DeviceModel):
    """
    RS485数据回调函数
    当接收到IMU数据时被调用
    """
    global imu1_euler, imu2_euler, imu3_euler
    global imu1_last_update, imu2_last_update, imu3_last_update
    global imu1_yaw_offset, imu2_yaw_offset, imu3_yaw_offset
    global imu1_first_valid_data, imu2_first_valid_data, imu3_first_valid_data
    global imu1_first_data, imu2_first_data, imu3_first_data
    
    data = DeviceModel.deviceData
    current_time = time.time()
    
    with imu_data_lock:
        # 处理IMU1 (0x50 = 80)
        if 80 in data:
            device_data = data[80]
            
            # 提取欧拉角（度）
            roll = device_data.get('AngX', 0.0)
            pitch = device_data.get('AngY', 0.0)
            yaw = device_data.get('AngZ', 0.0)
            
            # 只处理有效数据（跳过全0数据）
            if abs(roll) > 0.01 or abs(pitch) > 0.01 or abs(yaw) > 0.01:
                # 打印第一次有效数据
                if not imu1_first_valid_data:
                    imu1_first_data = {"roll": roll, "pitch": pitch, "yaw": yaw}
                    print(f"📍 [IMU1] 首次有效数据: Roll={roll:.2f}°, Pitch={pitch:.2f}°, Yaw={yaw:.2f}°")
                    imu1_first_valid_data = True
                
                # Yaw归零处理（借鉴dual_imu_euler.py的智能归零）
                yaw_normalized, imu1_yaw_offset = normalize_yaw_angle(yaw, imu1_yaw_offset, "IMU1")
                
                imu1_euler = {"roll": roll, "pitch": pitch, "yaw": yaw_normalized}
                imu1_last_update = current_time
        
        # 处理IMU2 (0x51 = 81)
        if 81 in data:
            device_data = data[81]
            
            roll = device_data.get('AngX', 0.0)
            pitch = device_data.get('AngY', 0.0)
            yaw = device_data.get('AngZ', 0.0)
            
            # 只处理有效数据（跳过全0数据）
            if abs(roll) > 0.01 or abs(pitch) > 0.01 or abs(yaw) > 0.01:
                # 打印第一次有效数据
                if not imu2_first_valid_data:
                    imu2_first_data = {"roll": roll, "pitch": pitch, "yaw": yaw}
                    print(f"📍 [IMU2] 首次有效数据: Roll={roll:.2f}°, Pitch={pitch:.2f}°, Yaw={yaw:.2f}°")
                    imu2_first_valid_data = True
                
                # Yaw归零处理（借鉴dual_imu_euler.py的智能归零）
                yaw_normalized, imu2_yaw_offset = normalize_yaw_angle(yaw, imu2_yaw_offset, "IMU2")
                
                imu2_euler = {"roll": roll, "pitch": pitch, "yaw": yaw_normalized}
                imu2_last_update = current_time
        
        # 处理IMU3 (0x52 = 82)
        if 82 in data:
            device_data = data[82]
            
            roll = device_data.get('AngX', 0.0)
            pitch = device_data.get('AngY', 0.0)
            yaw = device_data.get('AngZ', 0.0)
            
            # 只处理有效数据（跳过全0数据）
            if abs(roll) > 0.01 or abs(pitch) > 0.01 or abs(yaw) > 0.01:
                # 打印第一次有效数据
                if not imu3_first_valid_data:
                    imu3_first_data = {"roll": roll, "pitch": pitch, "yaw": yaw}
                    print(f"📍 [IMU3] 首次有效数据: Roll={roll:.2f}°, Pitch={pitch:.2f}°, Yaw={yaw:.2f}°")
                    imu3_first_valid_data = True
                
                # Yaw归零处理（借鉴dual_imu_euler.py的智能归零）
                yaw_normalized, imu3_yaw_offset = normalize_yaw_angle(yaw, imu3_yaw_offset, "IMU3")
                
                imu3_euler = {"roll": roll, "pitch": pitch, "yaw": yaw_normalized}
                imu3_last_update = current_time


def publisher_loop(socket_to_b, socket_to_lerobot, publish_interval, online_only=False):
    """
    ZeroMQ发布循环（双PUSH模式：发送给B端和本地LeRobot）
    
    参数：
        socket_to_b: 发送到B端的PUSH socket
        socket_to_lerobot: 发送到本地LeRobot的PUSH socket（可为None）
        publish_interval: 发布间隔（秒）
        online_only: 是否仅在三个IMU都在线时发布
    """
    print("\n" + "="*70)
    print("ZeroMQ发布器已启动（三IMU RS485模式 - 双PUSH架构）")
    print("="*70)
    print(f"发送到B端: {socket_to_b.getsockopt_string(zmq.LAST_ENDPOINT)}")
    if socket_to_lerobot is not None:
        print(f"发送到LeRobot: {socket_to_lerobot.getsockopt_string(zmq.LAST_ENDPOINT)}")
    else:
        print(f"发送到LeRobot: 未启用")
    print(f"发布频率: {1.0/publish_interval:.1f} Hz (间隔 {publish_interval*1000:.0f} ms)")
    print(f"在线检查: {'启用（仅在三个IMU都在线时发布）' if online_only else '禁用（始终发布）'}")
    print(f"发送模式: PUSH (点对点队列)")
    print("="*70 + "\n")
    
    publish_count = 0
    skip_count = 0
    last_stat_time = time.time()
    
    try:
        while True:
            loop_start = time.time()
            
            # === 步骤1: 检查三个IMU在线状态 ===
            current_time = time.time()
            imu1_online = (current_time - imu1_last_update) < 1.0 if imu1_last_update > 0 else False
            imu2_online = (current_time - imu2_last_update) < 1.0 if imu2_last_update > 0 else False
            imu3_online = (current_time - imu3_last_update) < 1.0 if imu3_last_update > 0 else False
            
            # 如果启用了online_only模式，检查三个IMU是否都在线
            if online_only and not (imu1_online and imu2_online and imu3_online):
                skip_count += 1
                if skip_count % 25 == 0:  # 每5秒打印一次状态
                    print(f"⚠️  等待IMU在线... IMU1: {'✓' if imu1_online else '✗'}, "
                          f"IMU2: {'✓' if imu2_online else '✗'}, "
                          f"IMU3: {'✓' if imu3_online else '✗'} (已跳过 {skip_count} 次)")
                time.sleep(publish_interval)
                continue
            
            # === 步骤2: 读取最新IMU数据（带线程锁） ===
            with imu_data_lock:
                euler1 = imu1_euler.copy()
                euler2 = imu2_euler.copy()
                euler3 = imu3_euler.copy()
            
            # 计算机械臂末端位置
            try:
                end_pos, link1_pos, link2_pos = calculate_end_effector_position(euler1, euler2)
            except Exception as e:
                print(f"⚠️  运动学计算失败: {e}")
                end_pos = [0.0, 0.0, 0.0]
            
            # 记录轨迹
            trajectory_positions.append(end_pos.copy())
            trajectory_timestamps.append(current_time)
            
            # === 步骤3: 坐标映射和约束 ===
            # 约束到原始范围
            x_raw = np.clip(end_pos[0], X_RAW_MIN, X_RAW_MAX)
            y_raw = np.clip(end_pos[1], Y_RAW_MIN, Y_RAW_MAX)
            z_raw = np.clip(end_pos[2], Z_RAW_MIN, Z_RAW_MAX)
            
            # 保存原始位置数据（用于robot_info）
            last_position_raw = [x_raw, y_raw, z_raw]
            
            # 线性映射到目标范围
            x_mapped = X_TARGET_MIN + (x_raw - X_RAW_MIN) / (X_RAW_MAX - X_RAW_MIN) * (X_TARGET_MAX - X_TARGET_MIN)
            y_mapped = Y_TARGET_MIN + (y_raw - Y_RAW_MIN) / (Y_RAW_MAX - Y_RAW_MIN) * (Y_TARGET_MAX - Y_TARGET_MIN)
            z_mapped = Z_TARGET_MIN + (z_raw - Z_RAW_MIN) / (Z_RAW_MAX - Z_RAW_MIN) * (Z_TARGET_MAX - Z_TARGET_MIN)
            
            # 计算shoulder_pan角度（使用raw数据，末端在xy平面投影相对于x轴的角度）
            # 假设基座在原点(0, 0)，末端位置为(x_raw, y_raw)
            shoulder_pan = np.arctan2(y_raw, x_raw)  # 弧度
            shoulder_pan_deg = np.rad2deg(shoulder_pan)     # 度
            
            # 读取夹爪值（带线程锁）
            with gripper_lock:
                current_gripper = gripper_value
            
            # === 步骤4: 构造发布消息 ===
            # 为B端准备的消息（使用pickle序列化，匹配B_reverse_whole.py）
            message_for_b = {
                "type": "control",  # 标识为控制命令
                "timestamp": current_time,
                # "euler_angles": {
                #     "roll": float(np.rad2deg(np.deg2rad(euler3["roll"]))),   # 机械爪姿态（度）
                #     "pitch": float(np.rad2deg(np.deg2rad(euler3["pitch"]))),
                #     "yaw": float(np.rad2deg(np.deg2rad(euler3["yaw"])))
                # },
                # "position": [
                #     float(x_mapped),  # x (米)
                #     float(y_mapped),  # y (米)
                #     float(z_mapped)   # z (米)
                # ],
                # "orientation": [
                #     float(np.deg2rad(euler3["roll"])),   # Roll（弧度）
                #     float(np.deg2rad(euler3["pitch"])),  # Pitch（弧度）
                #     float(np.deg2rad(euler3["yaw"]))     # Yaw（弧度）
                # ],
                "robot_info": {
                    "shoulder_pan": float(shoulder_pan),  # 肩部转角（弧度，从raw数据计算）
                    "wrist_roll": float(np.deg2rad(euler3["roll"])),  # 手腕roll（弧度）
                    "pitch": float(np.deg2rad(euler3["pitch"])),     # pitch（弧度）
                    "x": float(end_pos[0]),    # 原始x坐标（米）
                    "y": float(end_pos[2]),     # 原始z坐标映射到y（坐标系转换）
                    "gripper": float(current_gripper)  # 夹爪状态 (0.0-1.0)
                }

            }
            
            # 为本地LeRobot准备的消息（JSON格式，保持原有格式）
            message_for_lerobot = {
                "position": [
                    float(x_mapped),
                    float(y_mapped),
                    float(z_mapped)
                ],
                "orientation": [
                    float(np.deg2rad(euler3["roll"])),
                    float(np.deg2rad(euler3["pitch"])),
                    float(np.deg2rad(euler3["yaw"]))
                ],
                "gripper": float(current_gripper),
                "t": current_time
            }
            
            # === 步骤5: 发送消息到B端和LeRobot（不同格式） ===
            try:
                # 发送到B端（使用pickle序列化，阻塞模式，匹配A_real_video.py）
                socket_to_b.send(pickle.dumps(message_for_b, protocol=pickle.HIGHEST_PROTOCOL))
                
                # 发送到本地LeRobot（仅在启用时，使用JSON字符串）
                if socket_to_lerobot is not None:
                    socket_to_lerobot.send_string(json.dumps(message_for_lerobot))
                
                publish_count += 1
            except Exception as e:
                print(f"❌ ZeroMQ发送失败: {e}")

            # === 步骤6: 定期打印统计信息（每0.3秒） ===
            if current_time - last_stat_time >= 0.3:
                actual_rate = publish_count / (current_time - last_stat_time) if publish_count > 0 else 0.0
                
                # 清屏效果（可选）
                print("\033[H\033[J", end="")  # ANSI转义码清屏
                
                # === IMU原始数据显示（借鉴dual_imu_euler.py格式） ===
                print("┌" + "─"*68 + "┐")
                print(f"│ IMU 1 (杆1) - 地址: 0x{IMU1_ADDR:02X} ({IMU1_ADDR})".ljust(69) + "│")
                status1_text = "✅ 在线" if imu1_online else "⚠️  离线"
                print(f"│ 状态: {status1_text}  │  长度: {L1*1000:.0f} mm  │  归零模式: {YAW_NORMALIZATION_MODE}".ljust(85) + "│")
                yaw1_offset_str = f"(偏移:{imu1_yaw_offset:.2f}°)" if imu1_yaw_offset is not None else "(未归零)"
                print(f"│ Roll  = {euler1['roll']:8.2f}°  │  Pitch = {euler1['pitch']:8.2f}°  │  Yaw = {euler1['yaw']:8.2f}° {yaw1_offset_str}".ljust(97) + "│")
                print("├" + "─"*68 + "┤")
                
                print(f"│ IMU 2 (杆2) - 地址: 0x{IMU2_ADDR:02X} ({IMU2_ADDR})".ljust(69) + "│")
                status2_text = "✅ 在线" if imu2_online else "⚠️  离线"
                print(f"│ 状态: {status2_text}  │  长度: {L2*1000:.0f} mm".ljust(69) + "│")
                yaw2_offset_str = f"(偏移:{imu2_yaw_offset:.2f}°)" if imu2_yaw_offset is not None else "(未归零)"
                print(f"│ Roll  = {euler2['roll']:8.2f}°  │  Pitch = {euler2['pitch']:8.2f}°  │  Yaw = {euler2['yaw']:8.2f}° {yaw2_offset_str}".ljust(97) + "│")
                print("├" + "─"*68 + "┤")
                
                print(f"│ IMU 3 (机械爪) - 地址: 0x{IMU3_ADDR:02X} ({IMU3_ADDR})".ljust(69) + "│")
                status3_text = "✅ 在线" if imu3_online else "⚠️  离线"
                print(f"│ 状态: {status3_text}".ljust(69) + "│")
                yaw3_offset_str = f"(偏移:{imu3_yaw_offset:.2f}°)" if imu3_yaw_offset is not None else "(未归零)"
                print(f"│ Roll  = {euler3['roll']:8.2f}°  │  Pitch = {euler3['pitch']:8.2f}°  │  Yaw = {euler3['yaw']:8.2f}° {yaw3_offset_str}".ljust(97) + "│")
                print("└" + "─"*68 + "┘")
                
                # === 末端位置和ZeroMQ发布信息 ===
                print("\n┌" + "─"*68 + "┐")
                print(f"│ 机械臂末端位置 & ZeroMQ发布状态".ljust(69) + "│")
                print("├" + "─"*68 + "┤")
                print(f"│ 原始位置: [{end_pos[0]:7.3f}, {end_pos[1]:7.3f}, {end_pos[2]:7.3f}] m".ljust(69) + "│")
                print(f"│ 映射位置: [{x_mapped:7.3f}, {y_mapped:7.3f}, {z_mapped:7.3f}] m".ljust(69) + "│")
                print(f"│ Shoulder Pan: {shoulder_pan_deg:7.2f}° ({shoulder_pan:7.4f} rad)".ljust(69) + "│")
                
                # 计算发送的orientation值（弧度）
                sent_roll = float(np.deg2rad(euler3["roll"]))
                sent_pitch = float(np.deg2rad(euler3["pitch"]))
                sent_yaw = float(np.deg2rad(euler3["yaw"]))
                print(f"│ 发送姿态: Roll={sent_roll:7.4f} rad, Pitch={sent_pitch:7.4f} rad, Yaw={sent_yaw:7.4f} rad".ljust(84) + "│")
                
                # 显示夹爪状态
                gripper_percent = current_gripper * 100
                gripper_bar = "█" * int(current_gripper * 20) + "░" * (20 - int(current_gripper * 20))
                print(f"│ 夹爪开合: [{gripper_bar}] {gripper_percent:5.1f}% ({current_gripper:.2f})".ljust(85) + "│")
                
                print(f"│ 发布频率: {actual_rate:.1f} Hz  │  消息数: {publish_count}".ljust(69) + "│")
                
                # 显示视频接收状态（如果启用）
                if video_thread_running:
                    latency_str = f"{video_last_latency:.1f}ms" if video_last_latency > 0 else "N/A"
                    print(f"│ 📹 视频接收: 帧数={video_frame_count}, 延迟={latency_str}".ljust(69) + "│")
                
                print("└" + "─"*68 + "┘\n")
                
                publish_count = 0
                last_stat_time = current_time
            
            # === 步骤7: 精确定时控制 ===
            elapsed = time.time() - loop_start
            to_sleep = max(0.0, publish_interval - elapsed)
            time.sleep(to_sleep)
            
    except KeyboardInterrupt:
        print(f"\n📊 发布器已停止 | 总发布: {publish_count} 条消息")
        # 不要重新抛出异常，让程序正常返回到main()的finally块
        return


def plot_trajectory(use_agg_backend=False):
    """
    绘制机械臂末端的3D运动轨迹
    借鉴dual_imu_euler.py的完整绘图功能
    
    Args:
        use_agg_backend: 是否使用Agg后端（非GUI，避免Qt冲突）
    """
    if len(trajectory_positions) == 0:
        print("没有记录到轨迹数据")
        return
    
    try:
        import matplotlib
        
        # 如果需要，强制使用Agg后端（非GUI，避免Qt冲突）
        if use_agg_backend:
            matplotlib.use('Agg')
            print("ℹ️  使用matplotlib Agg后端（非GUI模式）")
        
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        
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
        plt.savefig('trajectory_rs485.png', dpi=150, bbox_inches='tight')
        print("\n✓ 轨迹图已保存到 trajectory_rs485.png")
        
        # 尝试显示（如果在图形环境中）
        try:
            plt.show()
        except:
            print("✓ 图表已生成（非交互环境，仅保存文件）")
        
        print("="*70)
        
    except Exception as e:
        print(f"⚠️  绘制轨迹图失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="三IMU机械臂ZeroMQ发布器 (RS485版本) - 双PUSH架构，参考A_real_video.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  # 使用默认参数（发送到B端5555和本地LeRobot 5559）
  python triple_imu_rs485_publisher.py --online-only
  
  # 自定义B端地址和LeRobot端口
  python triple_imu_rs485_publisher.py --b-host 192.168.1.100 --b-port 5555 \\
                                        --lerobot-port 5559 --online-only
  
  # 启用视频接收（从B端接收视频流）
  python triple_imu_rs485_publisher.py --online-only --enable-video \\
                                        --video-host 192.168.1.100 --video-port 5557
  
  # 完整示例（远程B端 + 本地LeRobot + 视频）
  python triple_imu_rs485_publisher.py --online-only \\
         --b-host 192.168.1.100 --b-port 5555 \\
         --lerobot-host localhost --lerobot-port 5559 \\
         --enable-video --video-host 192.168.1.100 --video-port 5557

重要说明：
  - IMU1 (0x50): 杆1，用于计算末端位置
  - IMU2 (0x51): 杆2，用于计算末端位置
  - IMU3 (0x52): 机械爪，提供姿态信息
  - position: 由IMU1和IMU2计算的机械臂末端位置（经过坐标映射）
  - orientation: 直接使用IMU3的欧拉角（机械爪姿态）
  - gripper: 夹爪开合状态（键盘控制1/2）

ZeroMQ架构（参考A_real_video.py双线程PUSH/SUB模式）：
  线程1（数据发送）：
    - PUSH → B端:5555 (对应B_reverse_whole.py的PULL socket)
    - PUSH → 本地LeRobot:5559 (对应lerobot_zeroMQ_imu.py的PULL socket)
  
  线程2（视频接收，可选）：
    - SUB ← B端:5557 (对应B_reverse_whole.py的PUB socket)

架构对比：
  原始版本：A (PUB) → B (SUB) → C
  新版本：  A (PUSH) → B (PULL) → C  (匹配B_reverse_whole.py)
           A (PUSH) → LeRobot (PULL)  (本地MuJoCo仿真)
           A (SUB)  ← B (PUB)         (视频流)

数据流向：
  传感器数据 → B端（转发到C和保存LeRobot数据集）
  传感器数据 → 本地LeRobot（MuJoCo实时仿真）
  视频流      ← B端（来自C端摄像头）
  
MuJoCo接收端（lerobot_zeroMQ_imu.py）：
  监听端口: localhost:5559 (PULL模式)
  数据格式：
    {
      "position": [x, y, z],           // 末端位置（米）
      "orientation": [roll, pitch, yaw], // 机械爪姿态（弧度）
      "gripper": 0.0-1.0,              // 夹爪开合（键盘控制）
      "t": 1234567890.123
    }
        """
    )
    parser.add_argument("--port", "-p", type=str, default="/dev/ttyUSB0",
                        help="RS485串口设备路径，默认/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200,
                        help="波特率，默认115200")
    parser.add_argument("--interval", "-i", type=float, default=DEFAULT_PUBLISH_INTERVAL,
                        help="发布间隔（秒），默认0.2（5Hz）")
    parser.add_argument("--b-host", type=str, default=DEFAULT_B_HOST,
                        help="B端服务器地址，默认localhost")
    parser.add_argument("--b-port", type=int, default=DEFAULT_B_PORT_COMMAND,
                        help="B端命令端口，默认5555")
    parser.add_argument("--enable-lerobot", action="store_true",
                        help="启用本地LeRobot仿真通信（5559端口）")
    parser.add_argument("--lerobot-host", type=str, default=DEFAULT_LEROBOT_HOST,
                        help="本地LeRobot地址，默认localhost")
    parser.add_argument("--lerobot-port", type=int, default=DEFAULT_LEROBOT_PORT,
                        help="本地LeRobot端口，默认5559")
    parser.add_argument("--online-only", action="store_true",
                        help="仅在三个IMU都在线时发布数据（推荐启用）")
    parser.add_argument("--enable-video", action="store_true",
                        help="启用视频接收功能（从B端接收视频流）")
    parser.add_argument("--video-host", type=str, default="localhost",
                        help="视频流服务器地址，默认localhost")
    parser.add_argument("--video-port", type=int, default=DEFAULT_VIDEO_PORT,
                        help="视频流端口，默认5557")
    parser.add_argument("--enable-audio", action="store_true",
                        help="启用音频接收和播放功能（从B端接收音频流，Opus解码）")
    parser.add_argument("--audio-host", type=str, default=DEFAULT_AUDIO_HOST,
                        help="音频流服务器地址，默认localhost")
    parser.add_argument("--audio-port", type=int, default=DEFAULT_AUDIO_PORT,
                        help="音频流端口，默认5561（独立端口）")
    parser.add_argument("--enable-debug", action="store_true",
                        help="启用调试数据发布功能（给Web UI后端）")
    parser.add_argument("--debug-port", type=int, default=DEFAULT_DEBUG_PORT,
                        help="调试数据发布端口，默认5560")
    parser.add_argument("--disable-trajectory-plot", action="store_true",
                        help="禁用程序退出时的matplotlib 3D轨迹图生成（避免Qt冲突）")
    
    args = parser.parse_args()
    
    print("="*70)
    print("三IMU机械臂ZeroMQ发布器（RS485版本 - 双杆 + 机械爪）")
    print("="*70)
    print(f"串口设备: {args.port}")
    print(f"波特率: {args.baud}")
    print(f"IMU 1 (杆1): 地址 0x50 (80)")
    print(f"IMU 2 (杆2): 地址 0x51 (81)")
    print(f"IMU 3 (机械爪): 地址 0x52 (82)")
    print(f"杆1长度: {L1*1000:.0f} mm")
    print(f"杆2长度: {L2*1000:.0f} mm")
    print(f"Yaw归零模式: {YAW_NORMALIZATION_MODE}")
    print("─"*70)
    print(f"ZMQ发送到B端: tcp://{args.b_host}:{args.b_port} (PUSH模式)")
    if args.enable_lerobot:
        print(f"ZMQ发送到LeRobot: tcp://{args.lerobot_host}:{args.lerobot_port} (PUSH模式)")
    else:
        print("ZMQ发送到LeRobot: 未启用（使用--enable-lerobot启用）")
    if args.enable_video:
        print(f"ZMQ接收视频: tcp://{args.video_host}:{args.video_port} (SUB模式)")
        print(f"视频显示: {'启用' if ENABLE_VIDEO_DISPLAY else '禁用'}")
    else:
        print("ZMQ接收视频: 未启用（仅发送模式）")
    print("="*70 + "\n")
    
    # 创建ZeroMQ上下文和socket（参考A_real_video.py双PUSH架构）
    zmq_context = zmq.Context()
    
    # Socket 1: 发送传感器数据到B端（PUSH模式，匹配B的PULL）
    socket_to_b = zmq_context.socket(zmq.PUSH)
    # 简单配置，不设置复杂参数（参考A_real_video.py的成功经验）
    
    # Socket 2: 发送传感器数据到本地LeRobot（PUSH模式，可选）
    socket_to_lerobot = None
    if args.enable_lerobot:
        socket_to_lerobot = zmq_context.socket(zmq.PUSH)
    
    # RS485设备对象
    rs485_device = None
    
    try:
        # 连接到B端（PUSH - connect模式）
        b_address = f"tcp://{args.b_host}:{args.b_port}"
        socket_to_b.connect(b_address)
        print(f"✓ ZeroMQ PUSH socket已连接到B端: {b_address}")
        
        # 连接到本地LeRobot（PUSH - connect模式，可选）
        if args.enable_lerobot:
            lerobot_address = f"tcp://{args.lerobot_host}:{args.lerobot_port}"
            socket_to_lerobot.connect(lerobot_address)
            print(f"✓ ZeroMQ PUSH socket已连接到LeRobot: {lerobot_address}")
        print("  等待接收端准备就绪...\n")
        
        # 等待连接稳定（PUSH socket需要时间建立连接）
        time.sleep(0.5)
        
        # 初始化RS485设备
        print("正在初始化RS485设备...")
        addrLis = [IMU1_ADDR, IMU2_ADDR, IMU3_ADDR]
        rs485_device = device_model.DeviceModel(
            "三IMU机械臂",
            args.port,
            args.baud,
            addrLis,
            data_callback
        )
        
        # 打开设备
        rs485_device.openDevice()
        
        if not rs485_device.isOpen:
            print("❌ 无法打开RS485设备，程序退出")
            return
        
        print("✓ RS485设备已打开\n")
        
        # 开启循环读取
        rs485_device.startLoopRead()
        print("✓ IMU数据采集已启动\n")
        
        # 等待所有IMU完成Yaw归零
        print("等待IMU归零...")
        while imu1_yaw_offset is None or imu2_yaw_offset is None or imu3_yaw_offset is None:
            time.sleep(0.1)
        print("✓ 所有IMU已完成Yaw归零\n")
        
        # 启动键盘监听线程和夹爪更新线程
        global keyboard_thread_running
        keyboard_thread_running = True
        
        # 键盘输入检测线程
        keyboard_thread = threading.Thread(target=keyboard_listener, daemon=True, name="KeyboardListener")
        keyboard_thread.start()
        
        # 夹爪更新线程
        gripper_thread = threading.Thread(target=gripper_update_thread, daemon=True, name="GripperUpdater")
        gripper_thread.start()
        
        print("✓ 键盘控制已启动（双线程模式：按键检测 + 夹爪更新）\n")
        
        # 启动视频接收线程（如果启用）
        global video_thread_running
        if args.enable_video:
            video_thread_running = True
            video_thread = threading.Thread(
                target=video_receiver_thread, 
                args=(args.video_host, args.video_port),
                daemon=True, 
                name="VideoReceiver"
            )
            video_thread.start()
            print(f"✓ 视频接收已启动: {args.video_host}:{args.video_port}\n")
        else:
            print("⚠️  视频接收未启用（使用 --enable-video 启用）\n")
        
        # 启动音频接收和播放线程（如果启用）
        global audio_thread_running, audio_buffer_queue
        if args.enable_audio:
            if AUDIO_ENABLED:
                # 初始化音频缓冲队列
                import queue as queue_module
                audio_buffer_queue = queue_module.Queue(maxsize=AUDIO_BUFFER_SIZE)
                
                audio_thread_running = True
                
                # 启动音频接收线程（从独立端口接收）
                audio_receiver_thread_obj = threading.Thread(
                    target=audio_receiver_thread,
                    args=(args.audio_host, args.audio_port),
                    daemon=True,
                    name="AudioReceiver"
                )
                audio_receiver_thread_obj.start()
                
                # 启动音频播放线程
                audio_player_thread_obj = threading.Thread(
                    target=audio_player_thread,
                    daemon=True,
                    name="AudioPlayer"
                )
                audio_player_thread_obj.start()
                
                print(f"✓ 音频接收已启动: {args.audio_host}:{args.audio_port} (独立音频流)")
                print(f"✓ 音频播放已启动: Opus解码 → 扬声器\n")
            else:
                print("⚠️  音频功能不可用（缺少 sounddevice 或 opuslib）")
                print("   安装方法: pip install sounddevice opuslib\n")
        else:
            print("⚠️  音频接收未启用（使用 --enable-audio 启用）\n")
        
        # 启动调试数据发布线程（给Web UI后端）
        if args.enable_debug:
            debug_thread = threading.Thread(
                target=debug_publisher_thread,
                args=(args.debug_port,),
                daemon=True,
                name="DebugPublisher"
            )
            debug_thread.start()
            print(f"✓ 调试数据发布已启动: tcp://*:{args.debug_port} (给Web UI后端)\n")
        else:
            print("⚠️  调试数据发布未启用（使用 --enable-debug 启用）\n")
        
        # 启动ZeroMQ发布循环（双PUSH模式）
        print("✓ 所有任务已启动，按Ctrl+C或'q'键停止\n")
        publisher_loop(socket_to_b, socket_to_lerobot, args.interval, args.online_only)
        
    except KeyboardInterrupt:
        print("\n\n✓ 程序已被用户中断")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n正在清理资源...")
        
        # 停止所有线程
        keyboard_thread_running = False
        video_thread_running = False
        audio_thread_running = False
        
        # 恢复终端设置
        if original_terminal_settings:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_terminal_settings)
                print("✓ 终端设置已恢复")
            except:
                pass
        
        # 停止RS485设备
        if rs485_device and rs485_device.isOpen:
            try:
                print("正在停止IMU数据采集...")
                rs485_device.stopLoopRead()
                time.sleep(0.5)
                rs485_device.closeDevice()
                print("✓ RS485设备已关闭")
            except KeyboardInterrupt:
                print("⚠️  RS485设备关闭被中断，强制关闭")
                try:
                    rs485_device.closeDevice()
                except:
                    pass
            except Exception as e:
                print(f"⚠️  RS485设备关闭出错: {e}")
        
        # 关闭ZeroMQ
        print("正在关闭ZeroMQ连接...")
        try:
            socket_to_b.close()
            if socket_to_lerobot is not None:
                socket_to_lerobot.close()
            zmq_context.term()
            print("✓ ZeroMQ连接已关闭")
        except KeyboardInterrupt:
            print("⚠️  ZeroMQ清理被中断，强制关闭")
        except Exception as e:
            print(f"⚠️  ZeroMQ关闭出错: {e}")
        
        print("已断开所有连接")
        
        # === 打印首次有效数据回顾 ===
        print("\n" + "="*70)
        print("首次有效数据回顾")
        print("="*70)
        if imu1_first_data:
            print(f"[IMU1] Roll={imu1_first_data['roll']:8.2f}°, Pitch={imu1_first_data['pitch']:8.2f}°, Yaw={imu1_first_data['yaw']:8.2f}°")
        else:
            print("[IMU1] 未收到有效数据")
        
        if imu2_first_data:
            print(f"[IMU2] Roll={imu2_first_data['roll']:8.2f}°, Pitch={imu2_first_data['pitch']:8.2f}°, Yaw={imu2_first_data['yaw']:8.2f}°")
        else:
            print("[IMU2] 未收到有效数据")
        
        if imu3_first_data:
            print(f"[IMU3] Roll={imu3_first_data['roll']:8.2f}°, Pitch={imu3_first_data['pitch']:8.2f}°, Yaw={imu3_first_data['yaw']:8.2f}°")
        else:
            print("[IMU3] 未收到有效数据")
        print("="*70)
        
        # 绘制轨迹（添加异常保护，确保即使用户按Ctrl+C也能执行）
        if not args.disable_trajectory_plot:
            try:
                if len(trajectory_positions) > 0:
                    print("\n正在生成轨迹图...")
                    # 使用Agg后端避免Qt冲突（在lerobot环境中opencv-python和PyQt5冲突）
                    plot_trajectory(use_agg_backend=True)
                else:
                    print("\n未记录到轨迹数据")
            except KeyboardInterrupt:
                print("\n⚠️  轨迹绘制被用户中断")
            except Exception as e:
                print(f"\n⚠️  轨迹绘制失败: {e}")
        else:
            print("\n✅ 轨迹图生成已禁用（--disable-trajectory-plot）")


if __name__ == '__main__':
    main()
