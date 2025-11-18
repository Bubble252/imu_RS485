# 快速开始 - IMU双摄像头可视化UI

## 🚀 5分钟快速上手

### 步骤1: 检查依赖

```bash
cd /home/bubble/桌面/WIT_RS485/pyqt5_viewer
python3 check_dependencies.py
```

如果有缺失依赖，运行：
```bash
pip3 install PyQt5 pyqtgraph PyOpenGL pyzmq opencv-python numpy
```

### 步骤2: 启动主程序

```bash
cd /home/bubble/桌面/WIT_RS485
python triple_imu_rs485_publisher_dual_cam_UI.py \
    --online-only \
    --b-host localhost --b-port 5555 \
    --enable-video --video-host localhost --video-port 5557 \
    --enable-debug --debug-port 5560
```

### 步骤3: 启动可视化UI

```bash
cd /home/bubble/桌面/WIT_RS485/pyqt5_viewer
./start_viewer.sh
```

## 📋 预期结果

✅ 主程序终端输出：
```
🔧 启动调试数据发布线程: tcp://*:5560
✓ 调试数据PUB socket已绑定到端口 5560
```

✅ UI窗口显示：
- 左侧：控制面板、IMU数据表格、夹爪进度条
- 中间：两个视频窗口（left_wrist + top）
- 右侧：3D轨迹图、实时曲线图

✅ 状态栏显示：
```
✓ 已连接到 localhost:5560 | UI FPS: 25.3 | 轨迹点: 156
```

## 🐛 遇到问题？

### 问题1: "等待数据..." 一直不消失
- 检查主程序是否开启了 `--enable-debug`
- 确认5560端口没有被占用：`netstat -tuln | grep 5560`

### 问题2: 视频窗口显示"等待摄像头数据"
- 检查主程序是否开启了 `--enable-video`
- 确认B端正在转发视频（5557端口）

### 问题3: UI卡顿
- 降低主程序debug发布频率（修改sleep时间）
- 关闭OpenCV窗口显示（只用PyQt5 UI）

## 📖 详细文档

查看完整文档：`PYQT5_VIEWER_README.md`

## 💡 提示

- 按Ctrl+C或关闭窗口退出UI
- 点击"重置轨迹"按钮清空历史数据
- 鼠标拖动3D视图旋转、缩放、平移
