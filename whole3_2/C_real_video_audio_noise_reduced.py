#!/usr/bin/env python3
# C_real_video_audio_noise_reduced.py - 音频降噪优化版
# 功能：
# 1. 单摄像头采集，复用为 left_wrist 和 top
# 2. 麦克风音频采集，使用 Opus 编码
# 3. 【新增】深度降噪（noisereduce）+ 噪声门（Noise Gate）
# 4. 通过 ZMQ 发送视频+音频到 B 端
# 
# 降噪策略：
# - 方案5: noisereduce 深度学习降噪（去除环境噪声）
# - 方案1: 噪声门阈值 500（去除底噪）
# 
# 延迟分析：
# - noisereduce 处理时间：~5-10ms/帧（非平稳模式）
# - 对于 60ms 帧大小，延迟增加 < 10ms
# - 总延迟：~70ms（原 60ms + 降噪 10ms）

import time
import threading
import queue
from datetime import datetime
from zmq_base import TorchSerializer
import zmq
import cv2
import numpy as np
import pickle

try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    print("⚠️ sounddevice 未安装，音频功能将被禁用")
    print("安装方法: pip install sounddevice")
    AUDIO_AVAILABLE = False

try:
    import opuslib
    OPUS_AVAILABLE = True
except ImportError:
    print("⚠️ opuslib 未安装，音频功能将被禁用")
    print("安装方法: pip install opuslib")
    OPUS_AVAILABLE = False

try:
    import noisereduce as nr
    NOISEREDUCE_AVAILABLE = True
except ImportError:
    print("⚠️ noisereduce 未安装，降噪功能将被禁用")
    print("安装方法: pip install noisereduce")
    NOISEREDUCE_AVAILABLE = False

# --- 服务器配置 ---
SERVER_B_HOST = "localhost"
SERVER_B_PORT_COMMAND = 5556  # 接收命令
SERVER_B_PORT_DATA = 5558     # 发送视频数据
SERVER_B_PORT_AUDIO = 5559    # 发送音频数据（独立端口）

# --- 摄像头配置 ---
CAMERA_ID = 0
VIDEO_FPS = 8
VIDEO_WIDTH = 240
VIDEO_HEIGHT = 180
JPEG_QUALITY = 30
FRAME_SKIP = 1

# --- 音频配置 ---
AUDIO_SAMPLE_RATE = 48000      # 48kHz 采样率（设备支持）
AUDIO_CHANNELS = 1              # 单声道
AUDIO_CHUNK_SIZE = 2880         # 2880 样本 = 60ms @ 48kHz
OPUS_BITRATE = 64000           # 64kbps（匹配更高采样率）
OPUS_FRAME_SIZE = 2880         # Opus 帧大小
OPUS_COMPLEXITY = 5            # 编码复杂度

# --- 降噪配置 ---
ENABLE_NOISEREDUCE = NOISEREDUCE_AVAILABLE  # 是否启用深度降噪
ENABLE_NOISE_GATE = True                     # 是否启用噪声门
NOISE_GATE_THRESHOLD = 500                   # 噪声门阈值（建议范围：300-800）
NOISE_PROFILE_FRAMES = 10                    # 学习噪声特征的帧数（~0.6秒）

# --- 全局状态 ---
latest_command = {
    "euler_angles": {"roll": 0, "pitch": 0, "yaw": 0},
    "throttle": 0,
    "timestamp": time.time()
}
command_lock = threading.Lock()

# 音频队列：存储已编码的 Opus 数据
audio_encoded_queue = queue.Queue(maxsize=5)
audio_enabled = AUDIO_AVAILABLE and OPUS_AVAILABLE


def thread_receive_commands():
    """线程1：接收控制命令"""
    global latest_command
    
    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    socket.connect(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_COMMAND}")
    
    print(f"[命令线程] 已连接到 B: {SERVER_B_HOST}:{SERVER_B_PORT_COMMAND}")
    
    received_count = 0
    try:
        while True:
            raw_data = socket.recv()
            command = TorchSerializer.from_bytes(raw_data)
            received_count += 1
            
            with command_lock:
                latest_command = command
            
            if received_count % 10 == 0:
                print(f"[命令线程] 已接收 {received_count} 条命令")
                
    except KeyboardInterrupt:
        pass
    finally:
        socket.close()
        context.term()


def audio_callback(indata, frames, time_info, status):
    """
    音频采集回调函数
    【优化】添加 noisereduce 深度降噪 + 噪声门
    """
    if status:
        print(f"[音频] 警告: {status}")
    
    if not hasattr(audio_callback, 'encoder'):
        # 在第一次调用时创建编码器
        try:
            audio_callback.encoder = opuslib.Encoder(
                fs=AUDIO_SAMPLE_RATE,
                channels=AUDIO_CHANNELS,
                application=opuslib.APPLICATION_VOIP
            )
            audio_callback.encoder.bitrate = OPUS_BITRATE
            audio_callback.encoder.complexity = OPUS_COMPLEXITY
            audio_callback.encode_count = 0
            
            # 降噪相关状态
            audio_callback.noise_learning = ENABLE_NOISEREDUCE
            audio_callback.noise_buffer = []
            audio_callback.noise_profile = None
            audio_callback.nr_processing_times = []
            audio_callback.noisereduce_enabled = ENABLE_NOISEREDUCE  # 存储到局部状态
            
            print("[音频回调] Opus 编码器已创建")
            if ENABLE_NOISEREDUCE:
                print(f"[音频回调] 深度降噪已启用，学习前 {NOISE_PROFILE_FRAMES} 帧作为噪声特征")
            if ENABLE_NOISE_GATE:
                print(f"[音频回调] 噪声门已启用，阈值: {NOISE_GATE_THRESHOLD}")
        except Exception as e:
            print(f"[音频回调] 创建编码器失败: {e}")
            return
    
    try:
        # ========================================
        # 步骤1：获取 float32 音频数据
        # ========================================
        audio_float = indata[:, 0].copy()  # 单声道
        
        # ========================================
        # 步骤2：深度降噪（noisereduce）
        # ========================================
        if audio_callback.noisereduce_enabled:
            if audio_callback.noise_learning:
                # 学习阶段：收集噪声样本
                audio_callback.noise_buffer.append(audio_float)
                
                if len(audio_callback.noise_buffer) >= NOISE_PROFILE_FRAMES:
                    # 学习完成：生成噪声特征
                    noise_sample = np.concatenate(audio_callback.noise_buffer)
                    
                    nr_start = time.time()
                    try:
                        # 使用收集的噪声样本作为参考
                        audio_callback.noise_profile = noise_sample
                        audio_callback.noise_learning = False
                        
                        nr_time = (time.time() - nr_start) * 1000
                        print(f"[音频回调] ✅ 噪声特征学习完成，用时: {nr_time:.1f}ms")
                        print(f"[音频回调] 噪声样本 RMS: {np.sqrt(np.mean(noise_sample**2)):.6f}")
                    except Exception as e:
                        print(f"[音频回调] 噪声学习失败: {e}")
                        audio_callback.noise_learning = False
                        audio_callback.noisereduce_enabled = False
                
                # 学习期间不处理音频，直接返回
                return
            else:
                # 降噪处理
                nr_start = time.time()
                try:
                    audio_float = nr.reduce_noise(
                        y=audio_float,
                        sr=AUDIO_SAMPLE_RATE,
                        y_noise=audio_callback.noise_profile,
                        stationary=False,      # 非平稳降噪（更智能，稍慢）
                        prop_decrease=1.0,     # 降噪强度（0.0-1.0，1.0=最强）
                    )
                    
                    nr_time = (time.time() - nr_start) * 1000
                    audio_callback.nr_processing_times.append(nr_time)
                    
                    # 定期报告降噪性能
                    if audio_callback.encode_count % 100 == 0 and audio_callback.nr_processing_times:
                        avg_nr_time = np.mean(audio_callback.nr_processing_times[-50:])
                        max_nr_time = np.max(audio_callback.nr_processing_times[-50:])
                        print(f"[音频回调] 降噪处理时间: 平均 {avg_nr_time:.1f}ms, 最大 {max_nr_time:.1f}ms")
                        
                except Exception as e:
                    if not hasattr(audio_callback, 'nr_error_count'):
                        audio_callback.nr_error_count = 0
                    audio_callback.nr_error_count += 1
                    if audio_callback.nr_error_count <= 3:
                        print(f"[音频回调] 降噪处理失败: {e}")
        
        # ========================================
        # 步骤3：转换为 int16 PCM
        # ========================================
        pcm_data = (audio_float * 32767).astype(np.int16)
        
        # ========================================
        # 步骤4：噪声门（Noise Gate）
        # ========================================
        if ENABLE_NOISE_GATE:
            # 计算当前帧的 RMS 能量
            rms = np.sqrt(np.mean(pcm_data.astype(np.float32)**2))
            
            # 低于阈值时强制静音
            if rms < NOISE_GATE_THRESHOLD:
                pcm_data = np.zeros_like(pcm_data)
                
                # 定期报告噪声门触发
                if not hasattr(audio_callback, 'gate_trigger_count'):
                    audio_callback.gate_trigger_count = 0
                audio_callback.gate_trigger_count += 1
                
                if audio_callback.gate_trigger_count % 100 == 0:
                    print(f"[音频回调] 噪声门已触发 {audio_callback.gate_trigger_count} 次")
        
        # ========================================
        # 步骤5：Opus 编码
        # ========================================
        pcm_bytes = np.ascontiguousarray(pcm_data).tobytes()
        opus_data = audio_callback.encoder.encode(pcm_bytes, OPUS_FRAME_SIZE)
        
        # ========================================
        # 步骤6：放入发送队列
        # ========================================
        try:
            audio_encoded_queue.put_nowait({
                "codec": "opus",
                "sample_rate": AUDIO_SAMPLE_RATE,
                "channels": AUDIO_CHANNELS,
                "data": opus_data,
                "timestamp": time.time()
            })
            
            audio_callback.encode_count += 1
            
            # 定期打印统计信息
            if audio_callback.encode_count % 50 == 0:
                pcm_size = len(pcm_bytes)
                opus_size = len(opus_data)
                compression = pcm_size / opus_size if opus_size > 0 else 0
                
                # 计算当前音频质量指标
                current_rms = np.sqrt(np.mean(pcm_data.astype(np.float32)**2))
                
                status_msg = f"[音频回调] 已编码 {audio_callback.encode_count} 帧, "
                status_msg += f"PCM: {pcm_size}B → Opus: {opus_size}B (压缩比: {compression:.1f}x), "
                status_msg += f"队列: {audio_encoded_queue.qsize()}/{audio_encoded_queue.maxsize}, "
                status_msg += f"RMS: {current_rms:.0f}"
                
                print(status_msg)
        
        except queue.Full:
            # 队列满，丢弃旧数据
            if not hasattr(audio_callback, 'drop_count'):
                audio_callback.drop_count = 0
            audio_callback.drop_count += 1
            
            if audio_callback.drop_count % 20 == 0:
                print(f"[音频回调] 队列满，已丢弃 {audio_callback.drop_count} 帧")
    
    except Exception as e:
        if not hasattr(audio_callback, 'error_count'):
            audio_callback.error_count = 0
        audio_callback.error_count += 1
        if audio_callback.error_count <= 3:
            print(f"[音频回调] 处理错误: {e}")


def thread_send_audio():
    """线程2：独立发送音频数据"""
    if not audio_enabled:
        print("[音频发送线程] 音频功能未启用，线程退出")
        return
    
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.setsockopt(zmq.SNDHWM, 10)  # 音频允许更多缓冲
    socket.setsockopt(zmq.LINGER, 0)
    try:
        socket.setsockopt(1, 1)  # TCP_NODELAY
    except:
        pass
    socket.connect(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_AUDIO}")
    
    print(f"[音频发送线程] 已连接到 B: {SERVER_B_HOST}:{SERVER_B_PORT_AUDIO}")
    print(f"[音频发送线程] 独立音频流已启动")
    
    sent_count = 0
    start_time = time.time()
    
    try:
        while True:
            # 从队列获取音频数据（阻塞）
            try:
                audio_data = audio_encoded_queue.get(timeout=1.0)
                
                # 发送音频数据
                socket.send(pickle.dumps(audio_data, protocol=pickle.HIGHEST_PROTOCOL))
                sent_count += 1
                
                # 统计信息
                if sent_count % 50 == 0:
                    elapsed = time.time() - start_time
                    fps = 50 / elapsed if elapsed > 0 else 0
                    queue_size = audio_encoded_queue.qsize()
                    print(f"[音频发送线程] 已发送 {sent_count} 帧, FPS: {fps:.1f}, "
                          f"队列: {queue_size}/{audio_encoded_queue.maxsize}")
                    start_time = time.time()
                    
            except queue.Empty:
                continue
                
    except KeyboardInterrupt:
        print("\n[音频发送线程] 停止中...")
    finally:
        socket.close()
        context.term()
        print("[音频发送线程] 已关闭")


def thread_send_data():
    """线程3：发送视频数据（不再包含音频）"""
    context = zmq.Context()
    
    # 配置 socket
    socket = context.socket(zmq.PUSH)
    socket.setsockopt(zmq.SNDHWM, 1)
    socket.setsockopt(zmq.LINGER, 0)
    try:
        socket.setsockopt(1, 1)  # TCP_NODELAY
    except:
        pass
    socket.connect(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_DATA}")
    
    print(f"[数据线程] 已连接到 B: {SERVER_B_HOST}:{SERVER_B_PORT_DATA}")
    
    # 打开摄像头
    cap = cv2.VideoCapture(CAMERA_ID)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, VIDEO_FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    print(f"[数据线程] 摄像头已打开: {VIDEO_WIDTH}x{VIDEO_HEIGHT} @ {VIDEO_FPS} FPS")
    
    # JPEG 编码参数
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    
    frame_count = 0
    sent_count = 0
    start_time = time.time()
    
    try:
        while True:
            # 读取视频帧
            ret, frame = cap.read()
            if not ret:
                print("[数据线程] 无法读取帧，尝试重新打开...")
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(CAMERA_ID)
                continue
            
            frame_count += 1
            
            # 跳帧
            if frame_count % FRAME_SKIP != 0:
                continue
            
            timestamp = time.time()
            
            # JPEG 编码
            _, encoded_frame = cv2.imencode('.jpg', frame, encode_param)
            video_bytes = encoded_frame.tobytes()
            
            # 准备数据包（不再包含音频，音频由独立线程发送）
            frame_data = {
                "image.left_wrist": video_bytes,
                "image.top": video_bytes,  # 单摄像头复用
                "timestamp": timestamp,
            }
            
            # 发送视频数据
            socket.send(pickle.dumps(frame_data, protocol=pickle.HIGHEST_PROTOCOL))
            sent_count += 1
            
            # 统计信息
            if sent_count % 20 == 0:
                elapsed = time.time() - start_time
                fps = 20 / elapsed if elapsed > 0 else 0
                queue_status = f"音频队列: {audio_encoded_queue.qsize()}" if audio_enabled else ""
                print(f"[视频发送线程] 已发送 {sent_count} 帧, FPS: {fps:.1f}, "
                      f"视频: {len(video_bytes)}B, {queue_status}")
                start_time = time.time()
            
            # 控制帧率
            time.sleep(1.0 / (VIDEO_FPS / FRAME_SKIP))
            
    except KeyboardInterrupt:
        print("\n[数据线程] 停止中...")
    finally:
        cap.release()
        socket.close()
        context.term()


def main():
    print("=" * 70)
    print("服务器 C 启动 - 音频降噪优化版")
    print("=" * 70)
    print(f"视频配置:")
    print(f"  - 分辨率: {VIDEO_WIDTH}x{VIDEO_HEIGHT}")
    print(f"  - 帧率: {VIDEO_FPS} FPS")
    print(f"  - JPEG 质量: {JPEG_QUALITY}")
    print()
    
    if audio_enabled:
        print(f"音频配置:")
        print(f"  - 采样率: {AUDIO_SAMPLE_RATE} Hz")
        print(f"  - 声道: {AUDIO_CHANNELS}")
        print(f"  - Opus 比特率: {OPUS_BITRATE} bps")
        print(f"  - 帧大小: {OPUS_FRAME_SIZE} 样本 ({OPUS_FRAME_SIZE/AUDIO_SAMPLE_RATE*1000:.0f}ms)")
        print(f"  - 状态: ✅ 启用")
        print()
        print(f"降噪配置:")
        print(f"  - 深度降噪 (noisereduce): {'✅ 启用' if ENABLE_NOISEREDUCE else '❌ 禁用'}")
        if ENABLE_NOISEREDUCE:
            print(f"    · 噪声学习帧数: {NOISE_PROFILE_FRAMES} ({NOISE_PROFILE_FRAMES * OPUS_FRAME_SIZE / AUDIO_SAMPLE_RATE:.1f}秒)")
            print(f"    · 模式: 非平稳降噪（智能）")
            print(f"    · 预计延迟: +5-10ms/帧")
        print(f"  - 噪声门 (Noise Gate): {'✅ 启用' if ENABLE_NOISE_GATE else '❌ 禁用'}")
        if ENABLE_NOISE_GATE:
            print(f"    · 阈值: {NOISE_GATE_THRESHOLD}")
            print(f"    · 说明: 音频 RMS < {NOISE_GATE_THRESHOLD} 时强制静音")
    else:
        print(f"音频配置:")
        print(f"  - 状态: ❌ 禁用（缺少依赖库）")
        missing = []
        if not AUDIO_AVAILABLE:
            missing.append("sounddevice")
        if not OPUS_AVAILABLE:
            missing.append("opuslib")
        if missing:
            print(f"  - 缺少: {', '.join(missing)}")
    
    print("=" * 70)
    print()
    
    # 列出音频设备
    if audio_enabled:
        print("可用音频设备:")
        try:
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    marker = "✓" if i == sd.default.device[0] else " "
                    print(f"  [{marker}] [{i}] {dev['name']} (输入: {dev['max_input_channels']}ch)")
            print()
        except Exception as e:
            print(f"  查询设备失败: {e}\n")
    
    # 启动线程1: 命令接收
    command_thread = threading.Thread(target=thread_receive_commands, daemon=True)
    command_thread.start()
    
    # 启动线程2: 音频发送（独立）
    audio_send_thread = None
    if audio_enabled:
        audio_send_thread = threading.Thread(target=thread_send_audio, daemon=True)
        audio_send_thread.start()
    
    # 启动线程3: 视频发送
    data_thread = threading.Thread(target=thread_send_data, daemon=True)
    data_thread.start()
    
    # 如果音频启用，启动音频流
    audio_stream = None
    if audio_enabled:
        try:
            print("🎤 启动音频采集流...")
            audio_stream = sd.InputStream(
                samplerate=AUDIO_SAMPLE_RATE,
                channels=AUDIO_CHANNELS,
                dtype='float32',
                blocksize=AUDIO_CHUNK_SIZE,
                callback=audio_callback
            )
            audio_stream.start()
            
            if ENABLE_NOISEREDUCE:
                print(f"⏳ 学习环境噪声中（{NOISE_PROFILE_FRAMES * OPUS_FRAME_SIZE / AUDIO_SAMPLE_RATE:.1f}秒）...")
                print(f"   请在此期间保持安静！")
                print()
            else:
                print("✅ 音频采集已启动")
                print()
        except Exception as e:
            print(f"❌ 启动音频流失败: {e}")
            print()
    
    print("=" * 70)
    print("所有线程已启动:")
    print("  线程1: 命令接收 (A→C)")
    if audio_enabled:
        print("  线程2: 音频发送 (C→B:5559) ← 独立音频流")
        if ENABLE_NOISEREDUCE:
            print("         └─ 深度降噪 (noisereduce)")
        if ENABLE_NOISE_GATE:
            print("         └─ 噪声门 (阈值 500)")
    else:
        print("  线程2: 音频发送 (禁用)")
    print("  线程3: 视频发送 (C→B:5558)")
    print("按 Ctrl+C 停止...")
    print("=" * 70)
    print()
    
    try:
        command_thread.join()
        data_thread.join()
    except KeyboardInterrupt:
        print("\n\n客户端 C 正在关闭...")
        if audio_stream:
            audio_stream.stop()
            audio_stream.close()
        print("客户端 C 已关闭。")


if __name__ == "__main__":
    main()
