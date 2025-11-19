## 🔧 SSH 隧道端口映射速查表

### 完整端口列表（方案2 - 独立音频流）

| 端口 | 方向 | 用途 | 数据类型 | 必需 |
|------|------|------|---------|------|
| 5555 | A→B | 控制命令发送 | JSON | ✅ |
| 5556 | B→C | 控制命令转发 | JSON | ✅ |
| 5558 | C→B | 视频数据上传 | JPEG | ✅ |
| 5557 | B→A | 视频数据下发 | JPEG | ✅ |
| **5559** | **C→B** | **音频数据上传** ⭐ | **Opus** | **✅** |
| **5561** | **B→A** | **音频数据下发** ⭐ | **Opus** | **✅** |

### SSH 隧道命令（更新版）

```bash
# 方法1：前台登录 + 隧道（推荐用于调试）
ssh -i ./capri_yhx_2237 -p 2237 \
    -o "ProxyCommand ssh -i ./leo_tmp_2258.txt -p 2258 -W %h:%p root@202.112.113.78" \
    -L 5555:localhost:5555 \
    -L 5556:localhost:5556 \
    -L 5557:localhost:5557 \
    -L 5558:localhost:5558 \
    -L 5559:localhost:5559 \  # ⭐ 新增音频上传
    -L 5561:localhost:5561 \  # ⭐ 新增音频下发
    root@202.112.113.74

# 方法2：后台隧道（推荐用于长期运行）
ssh -f -N \
    -i ./capri_yhx_2237 -p 2237 \
    -o "ProxyCommand ssh -i ./leo_tmp_2258.txt -p 2258 -W %h:%p root@202.112.113.78" \
    -L 5555:localhost:5555 \
    -L 5556:localhost:5556 \
    -L 5557:localhost:5557 \
    -L 5558:localhost:5558 \
    -L 5559:localhost:5559 \  # ⭐ 新增音频上传
    -L 5561:localhost:5561 \  # ⭐ 新增音频下发
    root@202.112.113.74
```

### 验证隧道是否成功

```bash
# 检查所有端口（应该看到 6 个）
ss -tuln | grep -E "5555|5556|5557|5558|5559|5561"

# 预期输出：
# tcp   LISTEN 0  128  127.0.0.1:5555  0.0.0.0:*
# tcp   LISTEN 0  128  127.0.0.1:5556  0.0.0.0:*
# tcp   LISTEN 0  128  127.0.0.1:5557  0.0.0.0:*
# tcp   LISTEN 0  128  127.0.0.1:5558  0.0.0.0:*
# tcp   LISTEN 0  128  127.0.0.1:5559  0.0.0.0:*  ← 音频上传
# tcp   LISTEN 0  128  127.0.0.1:5561  0.0.0.0:*  ← 音频下发

# 或者统计个数
ss -tuln | grep -E "5555|5556|5557|5558|5559|5561" | wc -l
# 应该输出: 6
```

### 故障排查

**问题1：隧道建立失败**
```bash
# 检查 SSH 进程
ps aux | grep ssh | grep 5555

# 杀掉旧隧道
pkill -f "ssh.*5555"

# 重新建立
# 使用上面的 SSH 命令
```

**问题2：端口被占用**
```bash
# 查看端口占用
sudo lsof -i :5559
sudo lsof -i :5561

# 杀掉占用进程
sudo kill -9 <PID>
```

**问题3：音频不工作但视频正常**
```bash
# 只检查音频端口
ss -tuln | grep -E "5559|5561"

# 如果没有，说明隧道没有转发音频端口
# 需要重新建立隧道（加上 5559 和 5561）
```

### 迁移提示

**从旧版本（混合流）升级到新版本（独立流）**

| 项目 | 旧版本 | 新版本 | 操作 |
|-----|--------|--------|------|
| 端口数 | 4 个 | 6 个 (+2) | 更新 SSH 命令 |
| B 端脚本 | start_b_whole.sh | start_b_voice.sh | 使用新脚本 |
| C 端脚本 | C_real_video_reverse_ultra.py | C_real_video_audio.py | 替换文件 |
| A 端参数 | (无音频参数) | --audio-port 5561 | 添加参数 |

**重要**：
- ✅ 必须同时更新 SSH 隧道、B 端、C 端、A 端
- ❌ 不能只更新部分，否则音频不工作
- ⚠️ 旧的混合流版本仍然可用（不更新也能工作，只是音频质量差）

### 端口流向图

```
本地 A 端                    SSH 隧道              远程 B 端 (Docker)
═══════════                ═══════════            ══════════════════

控制命令 ──> localhost:5555 ──[隧道]──> 容器:5555 ──> ZMQ PULL
                                                     ↓
视频数据 <── localhost:5557 <─[隧道]─── 容器:5557 <── ZMQ PUB
音频数据 <── localhost:5561 <─[隧道]─── 容器:5561 <── ZMQ PUB ⭐
             (独立音频流)
             
             
本地 C 端                                         远程 B 端 (Docker)
═══════════                                      ══════════════════

控制命令 <── localhost:5556 <─[隧道]─── 容器:5556 <── ZMQ PUSH
视频数据 ──> localhost:5558 ──[隧道]──> 容器:5558 ──> ZMQ PULL
音频数据 ──> localhost:5559 ──[隧道]──> 容器:5559 ──> ZMQ PULL ⭐
             (独立音频流)
```

### 常用命令汇总

```bash
# 1. 建立后台隧道
ssh -f -N -i ./capri_yhx_2237 -p 2237 \
    -o "ProxyCommand ssh -i ./leo_tmp_2258.txt -p 2258 -W %h:%p root@202.112.113.78" \
    -L 5555:localhost:5555 -L 5556:localhost:5556 \
    -L 5557:localhost:5557 -L 5558:localhost:5558 \
    -L 5559:localhost:5559 -L 5561:localhost:5561 \
    root@202.112.113.74

# 2. 验证隧道
ss -tuln | grep -E "5555|5556|5557|5558|5559|5561" | wc -l  # 应该是 6

# 3. 登录服务器运行 B
./connect.sh
cd /data7/yhx/lerobot_data_collection
./start_b_voice.sh

# 4. 本地运行 C
cd ~/桌面/WIT_RS485/whole3_2
python C_real_video_audio.py

# 5. 本地运行 A
cd ~/桌面/WIT_RS485
python triple_imu_rs485_publisher_dual_cam_UI_voice.py \
    --online-only \
    --b-host localhost --b-port 5555 \
    --enable-video --video-host localhost --video-port 5557 \
    --enable-audio --audio-host localhost --audio-port 5561 \
    -p /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 \
    --enable-debug --debug-port 5560

# 6. 关闭系统
# Ctrl+C 停止 A, B, C
pkill -f "ssh.*5555"  # 关闭隧道
```
