# C_real_video_audio.py - 视频 + 音频采集版本（基于 Opus 编码）
# 功能：
# 1. 单摄像头采集，复用为 left_wrist 和 top（保持与现有架构兼容）
# 2. 麦克风音频采集，使用 Opus 编码（低延迟、高压缩比）
# 3. 通过 ZMQ 发送视频+音频到 B 端

import time
import threading
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

# --- 服务器配置 ---
SERVER_B_HOST = "localhost"
SERVER_B_PORT_COMMAND = 5556  # 接收命令
SERVER_B_PORT_DATA = 5558     # 发送视频+音频数据

# --- 摄像头配置 ---
CAMERA_ID = 0
VIDEO_FPS = 8
VIDEO_WIDTH = 240
VIDEO_HEIGHT = 180
JPEG_QUALITY = 30
FRAME_SKIP = 1
ENABLE_OSD = False

# --- 音频配置 ---
AUDIO_SAMPLE_RATE = 16000      # 16kHz 采样率（语音质量足够）
AUDIO_CHANNELS = 1              # 单声道
AUDIO_CHUNK_SIZE = 960          # 每次读取 960 样本（60ms @ 16kHz）
OPUS_BITRATE = 24000           # 24kbps 比特率（语音质量好）
OPUS_FRAME_SIZE = 960          # Opus 帧大小（60ms @ 16kHz）
OPUS_COMPLEXITY = 5            # 编码复杂度（0-10，5 为平衡）
OPUS_APPLICATION = opuslib.APPLICATION_VOIP if OPUS_AVAILABLE else None  # VOIP 模式

# --- 全局状态 ---
latest_command = {
    "euler_angles": {"roll": 0, "pitch": 0, "yaw": 0},
    "throttle": 0,
    "timestamp": time.time()
}
command_lock = threading.Lock()

# 音频缓冲
audio_buffer = []
audio_lock = threading.Lock()
audio_enabled = AUDIO_AVAILABLE and OPUS_AVAILABLE


def thread_receive_commands():
    """线程1：接收控制命令"""
    global latest_command
    
    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    socket.connect(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_COMMAND}")
    
    print(f"[命令线程] 已连接到 B: {SERVER_B_HOST}:{SERVER_B_PORT_COMMAND}")
    print(f"[命令线程] 等待接收控制命令...")
    
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
    音频采集回调函数（由 sounddevice 调用）
    
    Args:
        indata: 输入音频数据（numpy array）
        frames: 帧数
        time_info: 时间信息
        status: 状态标志
    """
    if status:
        print(f"[音频] 采集警告: {status}")
    
    # 将音频数据添加到缓冲区
    with audio_lock:
        audio_buffer.append(indata.copy())


def thread_audio_capture():
    """线程2：音频采集与编码"""
    if not audio_enabled:
        print("[音频线程] 音频功能未启用，线程退出")
        return
    
    print(f"[音频线程] 初始化音频采集...")
    print(f"[音频线程] 采样率: {AUDIO_SAMPLE_RATE} Hz, 声道: {AUDIO_CHANNELS}")
    print(f"[音频线程] Opus 编码: {OPUS_BITRATE} bps, 复杂度: {OPUS_COMPLEXITY}")
    
    # 创建 Opus 编码器
    try:
        encoder = opuslib.Encoder(
            fs=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            application=OPUS_APPLICATION
        )
        encoder.bitrate = OPUS_BITRATE
        encoder.complexity = OPUS_COMPLEXITY
        print("[音频线程] ✅ Opus 编码器已创建")
    except Exception as e:
        print(f"[音频线程] ❌ 创建 Opus 编码器失败: {e}")
        return
    
    # 列出可用音频设备
    print("\n[音频线程] 可用音频设备:")
    try:
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                print(f"  [{i}] {dev['name']} (输入声道: {dev['max_input_channels']})")
    except Exception as e:
        print(f"[音频线程] 查询设备失败: {e}")
    
    # 打开音频流（使用默认输入设备）
    try:
        stream = sd.InputStream(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            dtype='int16',  # 16-bit PCM
            blocksize=AUDIO_CHUNK_SIZE,
            callback=audio_callback
        )
        stream.start()
        print(f"[音频线程] ✅ 音频流已启动（块大小: {AUDIO_CHUNK_SIZE} 样本 = {AUDIO_CHUNK_SIZE/AUDIO_SAMPLE_RATE*1000:.1f}ms）\n")
    except Exception as e:
        print(f"[音频线程] ❌ 打开音频流失败: {e}")
        return
    
    encoded_count = 0
    try:
        while True:
            # 从缓冲区获取音频数据
            audio_chunk = None
            with audio_lock:
                if len(audio_buffer) > 0:
                    audio_chunk = audio_buffer.pop(0)
            
            if audio_chunk is None:
                time.sleep(0.01)  # 10ms
                continue
            
            # 编码音频数据
            try:
                # 确保数据是连续的（Opus 要求）
                pcm_data = np.ascontiguousarray(audio_chunk[:, 0] if audio_chunk.ndim > 1 else audio_chunk)
                
                # Opus 编码（输入为 int16 PCM）
                opus_data = encoder.encode(pcm_data.tobytes(), OPUS_FRAME_SIZE)
                
                encoded_count += 1
                
                # 统计信息
                if encoded_count % 50 == 0:
                    compression_ratio = len(pcm_data.tobytes()) / len(opus_data)
                    print(f"[音频线程] 已编码 {encoded_count} 帧, "
                          f"PCM: {len(pcm_data.tobytes())} bytes → "
                          f"Opus: {len(opus_data)} bytes (压缩比: {compression_ratio:.1f}x)")
                
            except Exception as e:
                print(f"[音频线程] 编码失败: {e}")
                continue
            
    except KeyboardInterrupt:
        print("\n[音频线程] 停止中...")
    finally:
        stream.stop()
        stream.close()
        print("[音频线程] 音频流已关闭")


def thread_send_data():
    """线程3：发送视频+音频数据"""
    context = zmq.Context()
    
    # 配置 socket
    socket = context.socket(zmq.PUSH)
    socket.setsockopt(zmq.SNDHWM, 1)
    socket.setsockopt(zmq.LINGER, 0)
    try:
        socket.setsockopt(1, 1)  # TCP_NODELAY
    except:
        pass
    try:
        socket.setsockopt(zmq.SNDBUF, 32768)
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
    
    print(f"[数据线程] 摄像头已打开，分辨率: {VIDEO_WIDTH}x{VIDEO_HEIGHT}, FPS: {VIDEO_FPS}")
    
    # 初始化 Opus 编码器（用于音频编码）
    opus_encoder = None
    if audio_enabled:
        try:
            opus_encoder = opuslib.Encoder(
                fs=AUDIO_SAMPLE_RATE,
                channels=AUDIO_CHANNELS,
                application=OPUS_APPLICATION
            )
            opus_encoder.bitrate = OPUS_BITRATE
            opus_encoder.complexity = OPUS_COMPLEXITY
            print(f"[数据线程] ✅ Opus 编码器已初始化")
        except Exception as e:
            print(f"[数据线程] ⚠️ Opus 编码器初始化失败: {e}")
    
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
                print("[数据线程] 无法读取帧，尝试重新打开摄像头...")
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(CAMERA_ID)
                continue
            
            frame_count += 1
            
            # 跳帧策略
            if frame_count % FRAME_SKIP != 0:
                continue
            
            # 记录时间戳
            timestamp = time.time()
            
            # JPEG 编码
            _, encoded_frame = cv2.imencode('.jpg', frame, encode_param)
            video_bytes = encoded_frame.tobytes()
            
            # 获取音频数据（从缓冲区）
            audio_data = None
            if audio_enabled and opus_encoder:
                with audio_lock:
                    if len(audio_buffer) > 0:
                        audio_chunk = audio_buffer.pop(0)
                        try:
                            # Opus 编码
                            pcm_data = np.ascontiguousarray(
                                audio_chunk[:, 0] if audio_chunk.ndim > 1 else audio_chunk
                            )
                            audio_data = opus_encoder.encode(pcm_data.tobytes(), OPUS_FRAME_SIZE)
                        except Exception as e:
                            if sent_count % 20 == 0:
                                print(f"[数据线程] 音频编码失败: {e}")
            
            # 准备发送的数据包（兼容现有格式）
            frame_data = {
                "image.left_wrist": video_bytes,  # 单摄像头复用为 left_wrist
                "image.top": video_bytes,         # 同样的图像也作为 top
                "timestamp": timestamp,
            }
            
            # 添加音频数据（如果有）
            if audio_data:
                frame_data["audio"] = {
                    "codec": "opus",
                    "sample_rate": AUDIO_SAMPLE_RATE,
                    "channels": AUDIO_CHANNELS,
                    "data": audio_data,
                    "timestamp": timestamp
                }
            
            # 发送数据
            socket.send(pickle.dumps(frame_data, protocol=pickle.HIGHEST_PROTOCOL))
            sent_count += 1
            
            # 统计信息
            if sent_count % 20 == 0:
                elapsed = time.time() - start_time
                fps = 20 / elapsed
                audio_status = "有音频" if audio_data else "无音频"
                print(f"[数据线程] 已发送 {sent_count} 帧, FPS: {fps:.1f}, "
                      f"视频: {len(video_bytes)} bytes, {audio_status}")
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
    print("服务器 C 启动 - 视频 + 音频采集版本（Opus 编码）")
    print("=" * 70)
    print(f"视频配置:")
    print(f"  - 分辨率: {VIDEO_WIDTH}x{VIDEO_HEIGHT}")
    print(f"  - 帧率: {VIDEO_FPS} FPS")
    print(f"  - JPEG 质量: {JPEG_QUALITY}")
    print(f"  - 摄像头策略: 单摄像头复用为 left_wrist 和 top")
    print()
    
    if audio_enabled:
        print(f"音频配置:")
        print(f"  - 采样率: {AUDIO_SAMPLE_RATE} Hz")
        print(f"  - 声道: {AUDIO_CHANNELS}")
        print(f"  - Opus 比特率: {OPUS_BITRATE} bps")
        print(f"  - Opus 帧大小: {OPUS_FRAME_SIZE} 样本 ({OPUS_FRAME_SIZE/AUDIO_SAMPLE_RATE*1000:.0f}ms)")
        print(f"  - 状态: ✅ 启用")
    else:
        print(f"音频配置:")
        print(f"  - 状态: ❌ 禁用（缺少依赖库）")
    
    print("=" * 70)
    print()
    
    # 启动线程
    command_thread = threading.Thread(target=thread_receive_commands, daemon=True)
    data_thread = threading.Thread(target=thread_send_data, daemon=True)
    
    command_thread.start()
    data_thread.start()
    
    # 如果音频启用，启动音频采集线程
    if audio_enabled:
        audio_thread = threading.Thread(target=thread_audio_capture, daemon=True)
        audio_thread.start()
    
    print("所有线程已启动，按 Ctrl+C 停止...")
    print()
    
    try:
        command_thread.join()
        data_thread.join()
    except KeyboardInterrupt:
        print("\n\n客户端 C 正在关闭...")
        print("客户端 C 已关闭。")


if __name__ == "__main__":
    main()
