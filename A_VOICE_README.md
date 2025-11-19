# A 端音频功能使用指南

## 概述

`triple_imu_rs485_publisher_dual_cam_UI_voice.py` 是在原有程序基础上添加了**音频接收和播放**功能的增强版本。

## 新增功能

### 1. 音频接收
- 从 B 端接收 Opus 编码的音频流（通过 5557 端口）
- 与视频流混合在同一个 ZMQ SUB socket 中接收
- 自动解析 `frame_dict["audio"]` 字段

### 2. 音频播放
- Opus 实时解码（16kHz, 单声道）
- 通过 sounddevice 输出到扬声器
- 音频缓冲队列（5帧）平滑网络抖动
- 自动处理下溢和丢帧

### 3. 开关控制
- 通过 `--enable-audio` 参数控制是否启用音频功能
- 如果缺少依赖库，会自动降级为纯视频模式
- 不影响原有的 IMU、视频、调试等功能

## 依赖安装

### 安装音频库

```bash
# 系统依赖（Ubuntu/Debian）
sudo apt-get install libopus0 libopus-dev portaudio19-dev

# Python 库
pip install sounddevice opuslib

# 验证安装
python -c "import sounddevice; print('sounddevice OK')"
python -c "import opuslib; print('opuslib OK')"
```

### 查看音频设备

```bash
python -c "import sounddevice as sd; print(sd.query_devices())"
```

## 使用方法

### 基本用法（启用音频）

```bash
python triple_imu_rs485_publisher_dual_cam_UI_voice.py \
    --online-only \
    -p /dev/ttyUSB1 \
    --b-host localhost --b-port 5555 \
    --enable-video --video-host localhost --video-port 5557 \
    --enable-audio \
    --enable-debug --debug-port 5560
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--enable-audio` | **启用音频接收和播放** | 禁用 |
| `--enable-video` | 启用视频接收 | 禁用 |
| `--video-host` | 视频/音频服务器地址 | localhost |
| `--video-port` | 视频/音频端口 | 5557 |

**重要说明**：
- 音频和视频通过**同一个端口** (5557) 接收
- 必须同时启用 `--enable-video` 和 `--enable-audio` 才能接收音频
- 如果只启用 `--enable-audio` 而不启用 `--enable-video`，音频不会工作

### 完整示例

#### 场景 1：只接收视频（原有功能）

```bash
python triple_imu_rs485_publisher_dual_cam_UI_voice.py \
    --online-only \
    -p /dev/ttyUSB1 \
    --enable-video --video-host localhost --video-port 5557
```

#### 场景 2：接收视频 + 音频

```bash
python triple_imu_rs485_publisher_dual_cam_UI_voice.py \
    --online-only \
    -p /dev/ttyUSB1 \
    --enable-video --video-host localhost --video-port 5557 \
    --enable-audio
```

#### 场景 3：完整功能（IMU + 视频 + 音频 + PyQt5 UI）

```bash
# 终端 1：启动 A 端主程序
python triple_imu_rs485_publisher_dual_cam_UI_voice.py \
    --online-only \
    -p /dev/ttyUSB1 \
    --enable-video --video-host localhost --video-port 5557 \
    --enable-audio \
    --enable-debug --debug-port 5560

# 终端 2：启动 PyQt5 UI（可选）
cd pyqt5_viewer
./start_viewer.sh
```

## 数据流架构

```
┌─────────────────────────────────────────────────────────┐
│              C 端（音频 + 视频采集）                      │
│  麦克风 → Opus编码 ──┐                                   │
│  摄像头 → JPEG编码 ──┴─→ pickle打包 → B端:5558          │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│              B 端（数据转发）                             │
│  接收 C 的数据 → 混合 audio+video → PUB → A端:5557     │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│         A 端（本程序 - 音频播放 + 视频显示）              │
│                                                          │
│  video_receiver_thread (主接收线程):                    │
│    SUB ← B端:5557                                        │
│      ├─ 解析 frame_dict["image.left_wrist"] → OpenCV   │
│      ├─ 解析 frame_dict["image.top"] → OpenCV          │
│      └─ 解析 frame_dict["audio"] → audio_buffer_queue  │
│                                                          │
│  audio_player_thread (音频播放线程):                    │
│    从 audio_buffer_queue 获取 Opus 数据                 │
│      → Opus解码 → sounddevice播放                       │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 运行日志示例

### 启动时（音频功能正常）

```
======================================================================
三IMU机械臂ZeroMQ发布器（RS485版本 - 双杆 + 机械爪 + 音频）
======================================================================
...
✓ 视频接收已启动: localhost:5557

🔊 启动音频播放线程
   采样率: 16000 Hz
   声道: 1
   帧大小: 960 样本 (60ms)
   缓冲大小: 5 帧

可用音频输出设备:
  [0] HDA Intel PCH: ALC257 Analog (输出声道: 2) (默认)
  ...
✓ Opus 解码器已创建
✓ 音频输出流已启动

✓ 音频接收和播放已启动: localhost:5557 (Opus解码)
```

### 运行时（音频数据接收）

```
📹 [视频] 接收帧 #30, 摄像头: [left_wrist+top], 延迟: 45.2ms
🔊 音频接收: 50 帧, 队列: 3/5, 编码: opus
🔊 音频播放: 50 帧, 队列: 3/5, 下溢: 0
```

### 启动时（音频库缺失）

```
⚠️ sounddevice 未安装，音频播放功能将被禁用
安装方法: pip install sounddevice
⚠️ opuslib 未安装，音频解码功能将被禁用
安装方法: pip install opuslib
...
⚠️  音频功能不可用（缺少 sounddevice 或 opuslib）
   安装方法: pip install sounddevice opuslib
```

## 音频配置

### 可调参数（文件内配置）

在 `triple_imu_rs485_publisher_dual_cam_UI_voice.py` 中：

```python
# === 音频配置 ===
AUDIO_SAMPLE_RATE = 16000      # 16kHz 采样率（与C端一致）
AUDIO_CHANNELS = 1              # 单声道
AUDIO_BUFFER_SIZE = 5           # 缓冲队列大小（帧数）
OPUS_FRAME_SIZE = 960          # Opus 帧大小（60ms @ 16kHz）
```

**调整建议**：
- **降低延迟**：减小 `AUDIO_BUFFER_SIZE` 到 2-3（可能出现卡顿）
- **更平滑播放**：增大 `AUDIO_BUFFER_SIZE` 到 8-10（增加延迟）

## 故障排查

### 问题 1：音频设备打开失败

**症状**：
```
❌ 音频播放线程异常: Error opening OutputStream: ...
```

**解决方法**：
```bash
# 检查设备
python -c "import sounddevice as sd; print(sd.query_devices())"

# 测试播放
python -c "import sounddevice as sd; import numpy as np; \
    sd.play(np.zeros((16000, 1), dtype='int16'), 16000); \
    sd.wait(); print('成功')"
```

### 问题 2：音频缓冲下溢（卡顿）

**症状**：
```
⚠️  音频缓冲下溢（10 次），等待数据...
```

**原因**：
- 网络延迟过高
- C 端音频采集不稳定
- B 端转发卡顿

**解决方法**：
1. 增大 `AUDIO_BUFFER_SIZE` 到 8-10
2. 检查 C 端和 B 端日志
3. 改善网络条件

### 问题 3：音频队列已满（丢帧）

**症状**：
```
⚠️  音频缓冲队列已满，丢弃旧帧
```

**原因**：
- 播放速度跟不上接收速度
- CPU 占用过高

**解决方法**：
1. 检查 CPU 使用率
2. 关闭不必要的程序
3. 减小 `AUDIO_BUFFER_SIZE`

### 问题 4：听不到声音

**检查清单**：
1. ✅ 确认启用了 `--enable-audio` 参数
2. ✅ 确认同时启用了 `--enable-video` 参数
3. ✅ 检查日志是否显示 "音频接收: X 帧"
4. ✅ 检查日志是否显示 "音频播放: X 帧"
5. ✅ 检查系统音量设置
6. ✅ 检查音频输出设备选择（扬声器 vs 耳机）

## 性能指标

| 指标 | 数值 |
|------|------|
| 音频延迟 | ~100-150ms（接收+缓冲+播放） |
| 音频带宽 | ~3 KB/s（24kbps Opus） |
| CPU 占用 | +5-10%（Opus 解码 + 播放） |
| 内存占用 | +10-20 MB（缓冲队列） |

## 与原版的区别

| 功能 | 原版 | Voice 版本 |
|------|------|-----------|
| IMU 数据采集 | ✅ | ✅ |
| 双视频接收 | ✅ | ✅ |
| 音频接收播放 | ❌ | ✅ |
| PyQt5 UI 支持 | ✅ | ✅ |
| 调试数据发布 | ✅ | ✅ |
| 轨迹绘制 | ✅ | ✅ |

**建议**：
- 如果不需要音频功能，继续使用原版 `triple_imu_rs485_publisher_dual_cam_UI.py`
- 如果需要音频功能，使用 Voice 版本并添加 `--enable-audio` 参数

## 相关文档

- **C 端音频采集**：`/home/bubble/桌面/WIT_RS485/whole3_2/C_real_video_audio.py`
- **B 端音频转发**：`/home/bubble/桌面/WIT_RS485/whole3_2/B_reverse_whole_voice.py`
- **音频集成文档**：`/home/bubble/桌面/WIT_RS485/whole3_2/AUDIO_INTEGRATION_README.md`
- **快速指南**：`/home/bubble/桌面/WIT_RS485/whole3_2/QUICKSTART_AUDIO.md`
- **PyQt5 UI 文档**：`/home/bubble/桌面/WIT_RS485/pyqt5_viewer/PYQT5_VIEWER_README.md`

---

**创建时间**: 2025-11-18  
**版本**: v1.0  
**文件名**: triple_imu_rs485_publisher_dual_cam_UI_voice.py  
**状态**: ✅ 完成，可以测试
