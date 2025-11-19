# 音频功能快速启动指南

## 📦 已创建的文件

1. **C_real_video_audio.py** - 新的 C 端程序（视频+音频采集）
2. **B_reverse_whole_voice.py** - 修改后的 B 端程序（支持音频转发）
3. **AUDIO_INTEGRATION_README.md** - 完整技术文档
4. **install_audio_deps.sh** - 依赖安装脚本
5. **test_audio_c.sh** - 音频功能测试脚本

## 🚀 快速开始

### 步骤 1: 安装依赖（C 端本地执行）

```bash
cd /home/bubble/桌面/WIT_RS485/whole3_2

# 方式 1: 使用安装脚本（推荐）
./install_audio_deps.sh

# 方式 2: 手动安装
sudo apt-get install -y libopus0 libopus-dev portaudio19-dev
pip install sounddevice opuslib
```

### 步骤 2: 测试音频功能（可选）

```bash
./test_audio_c.sh
```

预期输出：
```
==========================================
音频功能测试脚本
==========================================

1. 检查音频依赖库...
✅ sounddevice 已安装
✅ opuslib 已安装
✅ opencv-python 已安装

2. 可用音频设备:
   [0] HDA Intel PCH: ALC257 Analog

3. 测试音频录制（3秒）...
   开始录音...
   ✅ 录音成功
   数据形状: (48000, 1)
   数据类型: int16

==========================================
✅ 所有测试通过！可以运行 C_real_video_audio.py
==========================================
```

### 步骤 3: 部署 B 端到远程服务器

```bash
# 上传新的 B 端文件到远程服务器
scp -i ./capri_yhx_2237 -P 2237 \
    -o "ProxyCommand ssh -i ./leo_tmp_2258.txt -p 2258 -W %h:%p root@202.112.113.78" \
    B_reverse_whole_voice.py \
    root@202.112.113.74:/data7/yhx/lerobot_data_collection/
```

### 步骤 4: 启动系统

#### 4.1 启动 B 端（远程服务器）

```bash
# SSH 到远程服务器
./connect.sh

# 在远程服务器上
cd /data7/yhx/lerobot_data_collection
python B_reverse_whole_voice.py --repo-id my_audio_dataset
```

#### 4.2 启动 C 端（本地）

```bash
# 新终端
cd /home/bubble/桌面/WIT_RS485/whole3_2
python C_real_video_audio.py
```

**预期输出**：
```
======================================================================
服务器 C 启动 - 视频 + 音频采集版本（Opus 编码）
======================================================================
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
======================================================================

[命令线程] 已连接到 B: localhost:5556
[数据线程] 已连接到 B: localhost:5558
[数据线程] 摄像头已打开，分辨率: 240x180, FPS: 8
[数据线程] ✅ Opus 编码器已初始化

[音频线程] 可用音频设备:
  [0] HDA Intel PCH: ALC257 Analog
[音频线程] ✅ 音频流已启动（块大小: 960 样本 = 60.0ms）

[数据线程] 已发送 20 帧, FPS: 8.0, 视频: 5432 bytes, 有音频
[音频线程] 已编码 50 帧, PCM: 1920 bytes → Opus: 256 bytes (压缩比: 7.5x)
```

## 📊 数据流架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         C 端（本地）                              │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────────────┐   │
│  │ 摄像头    │   │ 麦克风    │   │                          │   │
│  │  ↓       │   │  ↓       │   │  单摄像头复用策略：      │   │
│  │ JPEG编码 │   │ Opus编码  │   │  - left_wrist: 摄像头   │   │
│  │          │   │          │   │  - top: 同一摄像头      │   │
│  └──────────┘   └──────────┘   └──────────────────────────┘   │
│         ↓              ↓                                        │
│         └──────────────┴─ 混合发送（5558端口）                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    B 端（远程服务器）                             │
│         ┌─────────────────────────────────┐                     │
│         │  接收 C 的数据（5558 PULL）      │                     │
│         │  - 视频（JPEG，双摄像头字段）    │                     │
│         │  - 音频（Opus编码）              │                     │
│         └─────────────────────────────────┘                     │
│                    ↓                ↓                            │
│         ┌──────────────┐  ┌──────────────┐                     │
│         │ LeRobot保存  │  │ 转发给A      │                     │
│         │ （视频数据）  │  │ （5557 PUB） │                     │
│         └──────────────┘  └──────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      A 端（本地）- 待实现                         │
│         ┌─────────────────────────────────┐                     │
│         │  接收 B 的数据（5557 SUB）       │                     │
│         │  - 视频（JPEG解码 → 显示）       │                     │
│         │  - 音频（Opus解码 → 播放）       │                     │
│         └─────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

## 🔍 验证音频功能

### C 端日志检查
✅ 正常：
```
[数据线程] 已发送 20 帧, FPS: 8.0, 视频: 5432 bytes, 有音频
[音频线程] 已编码 50 帧, PCM: 1920 bytes → Opus: 256 bytes
```

❌ 异常：
```
[数据线程] 已发送 20 帧, FPS: 8.0, 视频: 5432 bytes, 无音频
⚠️ sounddevice 未安装，音频功能将被禁用
```

### B 端日志检查
✅ 正常：
```
[线程2 C→B] 收到数据，大小: 7890 bytes, 包含: 图像=True, 状态=False, 动作=False
[线程2 B→A] 包含音频数据，大小: 256 bytes, 编码: opus
[线程2 B→A] 数据已转发，视频: 10864 bytes, 有音频
```

❌ 异常：
```
[线程2 B→A] 数据已转发，视频: 10864 bytes, 无音频
```

## 🔧 配置调整

### 调整音频质量（C_real_video_audio.py）

```python
# 更高质量（更大带宽）
AUDIO_SAMPLE_RATE = 24000      # 24kHz
OPUS_BITRATE = 32000           # 32kbps

# 更低延迟（更小缓冲）
AUDIO_CHUNK_SIZE = 480         # 30ms @ 16kHz
OPUS_FRAME_SIZE = 480

# 更高压缩（更低带宽）
OPUS_BITRATE = 16000           # 16kbps
OPUS_COMPLEXITY = 3            # 降低复杂度
```

### 调整视频质量

```python
# 更高质量
VIDEO_WIDTH = 320
VIDEO_HEIGHT = 240
JPEG_QUALITY = 50

# 更高帧率
VIDEO_FPS = 15
```

## 📝 重要说明

### 单摄像头策略
- C 端只有一个摄像头
- 发送时将同一视频帧复制为 `left_wrist` 和 `top`
- B 端和 A 端无需修改，保持兼容性

### 音频自动降级
如果缺少音频库（sounddevice 或 opuslib）：
- C 端自动禁用音频功能
- 只发送视频数据
- 不影响现有视频流功能

### 性能指标
- **音频延迟**: ~75-100ms（采集+编码+网络）
- **视频延迟**: 与原版相同
- **带宽**: 视频 80 KB/s + 音频 3 KB/s = **83 KB/s**
- **压缩比**: Opus 约 7.5:1

## 🚨 故障排查

### 问题：音频设备打开失败
```bash
# 检查设备
python3 -c "import sounddevice; print(sounddevice.query_devices())"

# 测试录音
python3 -c "import sounddevice as sd; \
    rec = sd.rec(16000, samplerate=16000, channels=1); \
    sd.wait(); print('成功')"
```

### 问题：Opus 编码失败
```bash
# 检查 opuslib 安装
python3 -c "import opuslib; print(opuslib.api.version.get_version_string())"

# 重新安装
sudo apt-get install --reinstall libopus0 libopus-dev
pip uninstall opuslib
pip install opuslib
```

### 问题：B 端没有接收到音频
1. 检查 C 端是否显示 "有音频"
2. 检查 C 端音频线程是否正常启动
3. 检查网络连接（ping B 端）

## 📚 相关文档

- **完整技术文档**: [AUDIO_INTEGRATION_README.md](AUDIO_INTEGRATION_README.md)
- **原版 C 端**: C_real_video_reverse_ultra.py
- **原版 B 端**: B_reverse_whole.py
- **使用说明**: 使用说明.md

## ⏭️ 下一步：A 端集成

A 端需要实现：
1. 解析 `frame_dict["audio"]` 字段
2. Opus 解码（opuslib.Decoder）
3. 音频缓冲队列
4. sounddevice 播放输出
5. PyQt5 UI 音频可视化（可选）

详见 [AUDIO_INTEGRATION_README.md](AUDIO_INTEGRATION_README.md) 的 "下一步：A 端集成" 章节。

---

**创建时间**: 2025-11-18  
**版本**: v1.0  
**状态**: ✅ C 端和 B 端完成，可以开始测试
