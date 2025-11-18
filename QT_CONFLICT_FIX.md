# Qt冲突修复说明

## 问题描述

在lerobot conda环境中运行主程序时，程序退出时会尝试生成matplotlib 3D轨迹图，但由于环境中同时安装了`opencv-python`和`opencv-python-headless`，导致Qt插件冲突，程序崩溃并显示以下错误：

```
qt.qpa.plugin: Could not load Qt platform plugin "xcb"
已中止 (核心已转储)
```

## 根本原因

- matplotlib默认使用Qt后端进行3D绘图
- lerobot环境中opencv-python包含了Qt插件
- 与系统Qt库冲突，导致Qt平台插件加载失败

## 解决方案

已实现两个解决方案，可以配合使用：

### 方案1：使用Agg后端（推荐）

修改`plot_trajectory()`函数，默认使用matplotlib的Agg后端（非GUI模式）：

```python
def plot_trajectory(use_agg_backend=False):
    # 强制使用Agg后端，避免Qt冲突
    if use_agg_backend:
        matplotlib.use('Agg')
```

调用时传入`use_agg_backend=True`：

```python
plot_trajectory(use_agg_backend=True)
```

**效果**：
- 轨迹图会保存为PNG文件，不会尝试显示GUI窗口
- 完全避免Qt冲突
- 文件保存在运行目录，文件名如：`trajectory_YYYYMMDD_HHMMSS.png`

### 方案2：添加禁用标志

添加命令行参数`--disable-trajectory-plot`，可以完全跳过轨迹图生成：

```bash
python triple_imu_rs485_publisher_dual_cam_UI.py \
    --online-only \
    -p /dev/ttyUSB1 \
    --b-host localhost --b-port 5555 \
    --enable-video --video-host localhost --video-port 5557 \
    --enable-debug --debug-port 5560 \
    --disable-trajectory-plot  # 禁用matplotlib绘图
```

**效果**：
- 程序退出时不会尝试生成轨迹图
- 完全避免matplotlib相关的任何冲突
- 适合只使用PyQt5 UI查看数据的场景

## 推荐使用方式

### 场景1：需要保存轨迹图到文件
不添加`--disable-trajectory-plot`标志，程序会自动使用Agg后端保存PNG文件：

```bash
python triple_imu_rs485_publisher_dual_cam_UI.py \
    --online-only \
    -p /dev/ttyUSB1 \
    --enable-video --video-host localhost --video-port 5557 \
    --enable-debug --debug-port 5560
```

### 场景2：只使用PyQt5 UI，不需要matplotlib图
添加`--disable-trajectory-plot`标志，完全跳过绘图：

```bash
python triple_imu_rs485_publisher_dual_cam_UI.py \
    --online-only \
    -p /dev/ttyUSB1 \
    --enable-video --video-host localhost --video-port 5557 \
    --enable-debug --debug-port 5560 \
    --disable-trajectory-plot
```

## PyQt5 UI的优势

PyQt5 UI（`imu_dual_cam_viewer.py`）运行在独立的`pyqt5_ui`环境中，具有以下优势：

1. **实时3D轨迹**：使用PyQtGraph的GLViewWidget显示实时3D轨迹
2. **无Qt冲突**：环境中只有`opencv-python-headless`，无Qt冲突
3. **交互性强**：鼠标可以旋转、缩放、平移3D视图
4. **性能更好**：OpenGL加速，刷新率高达30-60Hz
5. **双摄像头**：同时显示left_wrist和top两个摄像头画面

**启动PyQt5 UI：**

```bash
./start_viewer.sh
# 或
conda activate pyqt5_ui
python imu_dual_cam_viewer.py
```

## 技术细节

### Agg后端特点
- 纯Python实现，不依赖GUI库
- 只能保存文件，不能显示窗口
- 输出格式：PNG, PDF, SVG等
- 性能较好，适合服务器环境

### 修改的代码位置

**triple_imu_rs485_publisher_dual_cam_UI.py**:

1. **第1028行** - 函数签名修改：
   ```python
   def plot_trajectory(use_agg_backend=False):
   ```

2. **第1040-1043行** - 添加Agg后端支持：
   ```python
   if use_agg_backend:
       matplotlib.use('Agg')
       print("ℹ️  使用matplotlib Agg后端（非GUI模式）")
   ```

3. **第1270行** - 添加命令行参数：
   ```python
   parser.add_argument("--disable-trajectory-plot", action="store_true",
                       help="禁用程序退出时的matplotlib 3D轨迹图生成（避免Qt冲突）")
   ```

4. **第1478-1487行** - 调用时使用Agg后端：
   ```python
   if not args.disable_trajectory_plot:
       try:
           if len(trajectory_positions) > 0:
               print("\n正在生成轨迹图...")
               plot_trajectory(use_agg_backend=True)
   ```

## 验证方法

1. **启动主程序**：
   ```bash
   python triple_imu_rs485_publisher_dual_cam_UI.py \
       --online-only \
       -p /dev/ttyUSB1 \
       --enable-video --video-host localhost --video-port 5557 \
       --enable-debug --debug-port 5560
   ```

2. **启动PyQt5 UI**：
   ```bash
   ./start_viewer.sh
   ```

3. **运行一段时间后按Ctrl+C退出主程序**

4. **预期结果**：
   - ✅ 主程序正常退出，无Qt错误
   - ✅ 生成轨迹图PNG文件（如果未禁用）
   - ✅ PyQt5 UI继续运行或干净退出

## 环境说明

- **主程序环境**：`lerobot`
  - Python 3.10.x
  - opencv-python + opencv-python-headless（Qt冲突源）
  - matplotlib with Agg backend

- **PyQt5 UI环境**：`pyqt5_ui`
  - Python 3.10.19
  - PyQt5 5.15.11
  - 只有opencv-python-headless（无Qt冲突）
  - PyQtGraph 0.14.0 + PyOpenGL 3.1.10

## 故障排除

### 如果仍然出现Qt错误

1. 确认使用了`use_agg_backend=True`参数
2. 或添加`--disable-trajectory-plot`标志完全禁用
3. 检查matplotlib是否在调用`use('Agg')`之前已经加载了Qt后端

### 如果PNG文件保存失败

1. 检查当前目录写权限
2. 查看终端输出的完整错误信息
3. 确认matplotlib已正确安装

## 相关文件

- `triple_imu_rs485_publisher_dual_cam_UI.py` - 主程序（已修复）
- `imu_dual_cam_viewer.py` - PyQt5 UI（无冲突）
- `start_viewer.sh` - UI启动脚本
- `环境说明.md` - 环境配置文档
- `PYQT5_VIEWER_README.md` - UI使用文档

---

**更新时间**: 2025-01-XX  
**修复版本**: v1.1  
**问题跟踪**: matplotlib Qt backend conflict in lerobot environment
