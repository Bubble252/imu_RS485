#!/usr/bin/env python3
"""
音频环回测试脚本
功能：采集麦克风音频 → Opus 编码 → Opus 解码 → 扬声器播放
用于验证音频采集、编码、解码、播放的完整流程
"""

import time
import threading
import queue
import numpy as np

try:
    import sounddevice as sd
    print("✅ sounddevice 已导入")
except ImportError as e:
    print(f"❌ sounddevice 导入失败: {e}")
    print("安装方法: pip install sounddevice")
    exit(1)

try:
    import opuslib
    print("✅ opuslib 已导入")
except ImportError as e:
    print(f"❌ opuslib 导入失败: {e}")
    print("安装方法: pip install opuslib")
    exit(1)

# --- 音频配置 ---
SAMPLE_RATE = 48000  # 使用设备支持的采样率
CHANNELS = 1
FRAME_SIZE = 2880  # 60ms @ 48kHz
BITRATE = 64000  # 提高比特率以匹配更高采样率
COMPLEXITY = 5

# --- 队列 ---
audio_queue = queue.Queue(maxsize=10)
encoded_queue = queue.Queue(maxsize=10)

# --- 统计 ---
stats = {
    "captured": 0,
    "encoded": 0,
    "decoded": 0,
    "played": 0,
    "dropped": 0,
    "encoding_errors": 0,
    "decoding_errors": 0
}
stats_lock = threading.Lock()


def audio_input_callback(indata, frames, time_info, status):
    """音频输入回调（采集）"""
    if status:
        print(f"[采集] 状态: {status}")
    
    try:
        # 转换为 int16
        audio_data = (indata[:, 0] * 32767).astype(np.int16)
        audio_queue.put_nowait(audio_data.copy())
        
        with stats_lock:
            stats["captured"] += 1
    except queue.Full:
        with stats_lock:
            stats["dropped"] += 1


def thread_encode():
    """编码线程：PCM → Opus"""
    print("[编码线程] 启动...")
    
    try:
        encoder = opuslib.Encoder(
            fs=SAMPLE_RATE,
            channels=CHANNELS,
            application=opuslib.APPLICATION_VOIP
        )
        encoder.bitrate = BITRATE
        encoder.complexity = COMPLEXITY
        print(f"[编码线程] Opus 编码器已创建 (比特率: {BITRATE} bps)")
    except Exception as e:
        print(f"[编码线程] ❌ 创建编码器失败: {e}")
        return
    
    while True:
        try:
            # 获取 PCM 数据
            pcm_data = audio_queue.get(timeout=1.0)
            
            # 确保数据连续
            pcm_bytes = np.ascontiguousarray(pcm_data).tobytes()
            
            # Opus 编码
            opus_data = encoder.encode(pcm_bytes, FRAME_SIZE)
            
            # 放入编码队列
            encoded_queue.put_nowait(opus_data)
            
            with stats_lock:
                stats["encoded"] += 1
                
        except queue.Empty:
            continue
        except queue.Full:
            with stats_lock:
                stats["dropped"] += 1
        except Exception as e:
            with stats_lock:
                stats["encoding_errors"] += 1
            if stats["encoding_errors"] <= 3:
                print(f"[编码线程] 编码错误: {e}")


def audio_output_callback(outdata, frames, time_info, status):
    """音频输出回调（播放）"""
    if status:
        print(f"[播放] 状态: {status}")
    
    try:
        # 从解码队列获取数据
        if not hasattr(audio_output_callback, 'decoder'):
            audio_output_callback.decoder = opuslib.Decoder(fs=SAMPLE_RATE, channels=CHANNELS)
            print("[播放] Opus 解码器已创建")
        
        decoder = audio_output_callback.decoder
        
        # 获取 Opus 数据
        opus_data = encoded_queue.get_nowait()
        
        # Opus 解码
        pcm_bytes = decoder.decode(opus_data, FRAME_SIZE)
        pcm_data = np.frombuffer(pcm_bytes, dtype=np.int16)
        
        # 转换为 float32 (-1.0 到 1.0)
        audio_float = pcm_data.astype(np.float32) / 32767.0
        
        # 填充输出缓冲
        outdata[:len(audio_float), 0] = audio_float
        if len(audio_float) < len(outdata):
            outdata[len(audio_float):, 0] = 0
        
        with stats_lock:
            stats["decoded"] += 1
            stats["played"] += 1
            
    except queue.Empty:
        # 没有数据，输出静音
        outdata.fill(0)
    except Exception as e:
        with stats_lock:
            stats["decoding_errors"] += 1
        if stats["decoding_errors"] <= 3:
            print(f"[播放] 解码错误: {e}")
        outdata.fill(0)


def print_stats():
    """打印统计信息"""
    while True:
        time.sleep(2.0)
        with stats_lock:
            print(f"\n[统计] "
                  f"采集: {stats['captured']}, "
                  f"编码: {stats['encoded']}, "
                  f"解码: {stats['decoded']}, "
                  f"播放: {stats['played']}, "
                  f"丢弃: {stats['dropped']}, "
                  f"编码错误: {stats['encoding_errors']}, "
                  f"解码错误: {stats['decoding_errors']}")
            print(f"        队列状态 - 采集队列: {audio_queue.qsize()}/{audio_queue.maxsize}, "
                  f"编码队列: {encoded_queue.qsize()}/{encoded_queue.maxsize}")


def main():
    print("=" * 70)
    print("音频环回测试 - 麦克风 → Opus 编码 → Opus 解码 → 扬声器")
    print("=" * 70)
    print()
    
    # 列出音频设备
    print("可用音频设备:")
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        device_type = []
        if dev['max_input_channels'] > 0:
            device_type.append(f"输入:{dev['max_input_channels']}ch")
        if dev['max_output_channels'] > 0:
            device_type.append(f"输出:{dev['max_output_channels']}ch")
        print(f"  [{i}] {dev['name']} ({', '.join(device_type)})")
    
    print()
    default_input = sd.query_devices(kind='input')
    default_output = sd.query_devices(kind='output')
    print(f"默认输入设备: {default_input['name']}")
    print(f"默认输出设备: {default_output['name']}")
    print()
    
    print(f"配置:")
    print(f"  采样率: {SAMPLE_RATE} Hz")
    print(f"  声道: {CHANNELS}")
    print(f"  帧大小: {FRAME_SIZE} 样本 ({FRAME_SIZE/SAMPLE_RATE*1000:.0f}ms)")
    print(f"  Opus 比特率: {BITRATE} bps")
    print(f"  Opus 复杂度: {COMPLEXITY}")
    print()
    print("=" * 70)
    print()
    
    # 启动编码线程
    encode_thread = threading.Thread(target=thread_encode, daemon=True)
    encode_thread.start()
    
    # 启动统计线程
    stats_thread = threading.Thread(target=print_stats, daemon=True)
    stats_thread.start()
    
    # 等待编码器初始化
    time.sleep(0.5)
    
    try:
        # 打开输入流（采集）
        print("🎤 启动音频采集...")
        input_stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype='float32',
            blocksize=FRAME_SIZE,
            callback=audio_input_callback
        )
        
        # 打开输出流（播放）
        print("🔊 启动音频播放...")
        output_stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype='float32',
            blocksize=FRAME_SIZE,
            callback=audio_output_callback
        )
        
        input_stream.start()
        output_stream.start()
        
        print()
        print("✅ 音频环回已启动！")
        print("   说话测试：对着麦克风说话，应该能听到延迟的回声")
        print("   按 Ctrl+C 停止测试")
        print()
        
        # 保持运行
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n正在停止...")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'input_stream' in locals():
            input_stream.stop()
            input_stream.close()
        if 'output_stream' in locals():
            output_stream.stop()
            output_stream.close()
        
        print()
        print("最终统计:")
        with stats_lock:
            print(f"  采集帧数: {stats['captured']}")
            print(f"  编码帧数: {stats['encoded']}")
            print(f"  解码帧数: {stats['decoded']}")
            print(f"  播放帧数: {stats['played']}")
            print(f"  丢弃帧数: {stats['dropped']}")
            print(f"  编码错误: {stats['encoding_errors']}")
            print(f"  解码错误: {stats['decoding_errors']}")
        print()
        print("测试结束。")


if __name__ == "__main__":
    main()
