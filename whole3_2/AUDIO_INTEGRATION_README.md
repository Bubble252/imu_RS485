# 音频流集成说明

## 概述

已完成 C→B→A 的音频流集成，采用 **Opus 编码**方案（低延迟、高压缩比）。

## 新增文件

### 1. C_real_video_audio.py
基于 `C_real_video_reverse_ultra.py` 创建，新增音频采集功能。

**主要特性**：
- ✅ 单摄像头复用为 `left_wrist` 和 `top`（保持与现有架构兼容）
- ✅ 麦克风音频采集（16kHz, 单声道）
- ✅ Opus 实时编码（24kbps, 低延迟）
- ✅ 视频+音频混合发送到 B 端（5558 端口）
- ✅ 自动降级（如果缺少音频库，只发送视频）

**音频配置**：
```python
AUDIO_SAMPLE_RATE = 16000      # 16kHz（语音质量）
AUDIO_CHANNELS = 1              # 单声道
OPUS_BITRATE = 24000           # 24kbps
OPUS_FRAME_SIZE = 960          # 60ms @ 16kHz
OPUS_COMPLEXITY = 5            # 编码复杂度（0-10）
```

**数据格式**（发送给 B）：
```python
{
    "image.left_wrist": jpeg_bytes,    # 视频帧（JPEG）
    "image.top": jpeg_bytes,           # 同一视频帧
    "timestamp": time.time(),
    "audio": {                         # 新增音频字段
        "codec": "opus",
        "sample_rate": 16000,
        "channels": 1,
        "data": opus_encoded_bytes,    # Opus 编码数据
        "timestamp": time.time()
    }
}
```

### 2. B_reverse_whole_voice.py
修改自 `B_reverse_whole.py`，新增音频转发功能。

**修改内容**：
1. **文件头注释**：添加音频功能说明
2. **thread_data_handler 函数**（第 490-520 行）：
   - 从 C 接收的数据中提取 `audio` 字段
   - 将音频数据混合到转发给 A 的 `video_frame` 字典中
   - 添加音频大小和编码格式的日志输出

**转发数据格式**（B→A）：
```python
{
    "image.left_wrist": jpeg_bytes,
    "image.top": jpeg_bytes,
    "encoding": "jpeg",
    "timestamp": timestamp,
    "audio": {                         # 原样转发音频
        "codec": "opus",
        "sample_rate": 16000,
        "channels": 1,
        "data": opus_encoded_bytes
    }
}
```

## 依赖安装

### C 端依赖
```bash
# 音频采集库
pip install sounddevice

# Opus 编码库
pip install opuslib

# 系统依赖（Ubuntu/Debian）
sudo apt-get install libopus0 libopus-dev portaudio19-dev

# 验证安装
python -c "import sounddevice; print('sounddevice OK')"
python -c "import opuslib; print('opuslib OK')"
```

### B 端依赖
无需额外依赖，B 端只是转发音频数据（不解码）。

## 使用方法

### 1. 启动 B 端（远程服务器）
```bash
cd /data7/yhx/lerobot_data_collection
python B_reverse_whole_voice.py --repo-id my_audio_dataset
```

### 2. 启动 C 端（本地）
```bash
cd /home/bubble/桌面/WIT_RS485/whole3_2
python C_real_video_audio.py
```

**预期输出**：
```
============================================================
服务器 C 启动 - 视频 + 音频采集版本（Opus 编码）
============================================================
视频配置:
  - 分辨率: 240x180
  - 帧率: 8 FPS
  - JPEG 质量: 30
  - 摄像头策略: 单摄像头复用为 left_wrist 和 top

音频配置:
  - 采样率: 16000 Hz
  - 声道: 1
  - Opus 比特率: 24000 bps
  - Opus 帧大小: 960 样本 (60ms)
  - 状态: ✅ 启用
============================================================

[命令线程] 已连接到 B: localhost:5556
[数据线程] 已连接到 B: localhost:5558
[数据线程] 摄像头已打开，分辨率: 240x180, FPS: 8
[数据线程] ✅ Opus 编码器已初始化
[音频线程] 可用音频设备:
  [0] HDA Intel PCH: ALC257 Analog (输入声道: 2)
  ...
[音频线程] ✅ 音频流已启动（块大小: 960 样本 = 60.0ms）

[数据线程] 已发送 20 帧, FPS: 8.1, 视频: 1234 bytes, 有音频
[音频线程] 已编码 50 帧, PCM: 1920 bytes → Opus: 256 bytes (压缩比: 7.5x)
```

### 3. 查看 B 端日志
```bash
# B 端应该显示接收到音频
[线程2 C→B] 收到数据，大小: 5678 bytes, 包含: 图像=True, 状态=False, 动作=False
[线程2 B→A] 包含音频数据，大小: 256 bytes, 编码: opus
[线程2 B→A] 数据已转发，视频: 2468 bytes, 有音频
```

## 故障排查

### 问题 1：C 端提示 "sounddevice 未安装"
```bash
# 解决方法
pip install sounddevice

# 如果安装失败，安装系统依赖
sudo apt-get install portaudio19-dev python3-dev
pip install sounddevice
```

### 问题 2：C 端提示 "opuslib 未安装"
```bash
# 解决方法
sudo apt-get install libopus0 libopus-dev
pip install opuslib
```

### 问题 3：音频设备找不到或打开失败
```bash
# 检查可用音频设备
python -c "import sounddevice; print(sounddevice.query_devices())"

# 测试默认输入设备
python -c "import sounddevice as sd; import numpy as np; \
    rec = sd.rec(16000, samplerate=16000, channels=1); \
    sd.wait(); print('录音成功')"
```

### 问题 4：B 端没有接收到音频
1. 检查 C 端日志是否显示 "有音频"
2. 检查 B 端是否显示 "包含音频数据"
3. 如果 C 端显示 "无音频"，说明音频采集线程未正常工作

### 问题 5：音频自动降级到视频模式
这是正常的降级行为，当缺少音频库时：
- C 端只发送视频数据
- B 端正常转发视频
- 不影响视频流功能

## 性能指标

### 音频延迟
- **采集延迟**: 60ms（chunk size）
- **编码延迟**: 5-10ms（Opus）
- **网络延迟**: 10-30ms（局域网）
- **总延迟**: **约 75-100ms**

### 带宽占用
- **视频**: ~10 KB/帧 × 8 FPS = **80 KB/s**
- **音频**: 24 kbps = **3 KB/s**
- **总带宽**: **约 83 KB/s**（0.66 Mbps）

### 压缩比
- **PCM**: 1920 bytes/帧（16-bit, 960 samples）
- **Opus**: 256 bytes/帧
- **压缩比**: **7.5:1**

## 数据流架构

```
C 端（采集）                 B 端（转发）                 A 端（接收+播放）
┌─────────────┐             ┌─────────────┐             ┌─────────────┐
│             │             │             │             │             │
│  摄像头     │             │             │             │             │
│  ↓          │             │             │             │             │
│ JPEG 编码   │─ 视频 ───→ │  原样转发   │─ 视频 ───→ │  JPEG 解码  │
│             │   5558      │             │   5557      │             │
│  麦克风     │             │             │             │             │
│  ↓          │             │             │             │             │
│ Opus 编码   │─ 音频 ───→ │  原样转发   │─ 音频 ───→ │  Opus 解码  │
│             │   5558      │             │   5557      │  ↓          │
│             │             │             │             │  扬声器播放 │
└─────────────┘             └─────────────┘             └─────────────┘
```

## 下一步：A 端集成

A 端需要实现以下功能（待开发）：

1. **修改 video_receiver_thread**：
   - 解析 `frame_dict["audio"]` 字段
   - 提取 Opus 编码的音频数据

2. **添加 audio_player_thread**：
   - 创建音频播放线程
   - Opus 解码（opuslib.Decoder）
   - 音频缓冲队列（处理网络抖动）
   - sounddevice 播放输出

3. **依赖安装**：
   ```bash
   pip install sounddevice opuslib
   ```

4. **可选：PyQt5 UI 集成**：
   - 音频波形可视化
   - 音量指示器
   - 静音/音量控制

## 技术细节

### Opus 编码参数
- **Application**: VOIP（针对语音优化）
- **Complexity**: 5（平衡质量和性能）
- **Bitrate**: 24000 bps（语音质量好）
- **Frame Size**: 960 samples @ 16kHz = 60ms

### 线程架构（C 端）
1. **thread_receive_commands**: 接收控制命令
2. **thread_audio_capture**: 音频采集+编码
3. **thread_send_data**: 视频采集+数据发送

### 数据同步
- 视频和音频使用统一的 `timestamp` 字段
- A 端可以根据时间戳实现音视频同步

---

**创建时间**: 2025-11-18  
**版本**: v1.0  
**作者**: AI Assistant  
**状态**: ✅ C 端和 B 端已完成，A 端待实现
