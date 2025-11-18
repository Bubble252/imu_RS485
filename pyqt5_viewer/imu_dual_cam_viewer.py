#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMU双摄像头可视化查看器 - PyQt5主窗口
使用ZMQ订阅triple_imu_rs485_publisher发布的调试数据（5560端口）
实时显示：双摄像头视频、IMU数据、3D轨迹、曲线图
"""

import sys
import time
import pickle
import threading
from collections import deque

import zmq
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QStatusBar
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QFont

from widgets.video_panel import VideoPanelWidget
from widgets.imu_panel import IMUPanelWidget
from widgets.trajectory_3d import Trajectory3DWidget
from widgets.chart_panel import ChartPanelWidget
from widgets.control_panel import ControlPanelWidget


class ZMQDataReceiver(QThread):
    """
    ZMQ数据接收线程 - 从5560端口订阅调试数据
    使用信号通知主线程更新UI
    """
    data_received = pyqtSignal(dict)  # 发送完整数据字典到主线程
    connection_status = pyqtSignal(bool, str)  # (connected, message)
    
    def __init__(self, zmq_host="localhost", zmq_port=5560, parent=None):
        super().__init__(parent)
        self.zmq_host = zmq_host
        self.zmq_port = zmq_port
        self.running = True
        self.socket = None
        self.context = None
        
    def run(self):
        """接收线程主循环"""
        try:
            # 创建ZMQ上下文和SUB socket
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.SUB)
            self.socket.connect(f"tcp://{self.zmq_host}:{self.zmq_port}")
            self.socket.setsockopt_string(zmq.SUBSCRIBE, "")  # 订阅所有消息
            self.socket.setsockopt(zmq.RCVTIMEO, 2000)  # 2秒超时
            
            self.connection_status.emit(True, f"已连接到 {self.zmq_host}:{self.zmq_port}")
            print(f"✓ ZMQ订阅已连接: tcp://{self.zmq_host}:{self.zmq_port}")
            
            no_data_count = 0
            
            while self.running:
                try:
                    # 接收pickle序列化数据
                    data_bytes = self.socket.recv()
                    data = pickle.loads(data_bytes)
                    
                    # 发送到主线程
                    self.data_received.emit(data)
                    no_data_count = 0
                    
                except zmq.Again:
                    # 超时，无数据
                    no_data_count += 1
                    if no_data_count == 1:
                        self.connection_status.emit(False, "等待数据...")
                    elif no_data_count > 5:
                        self.connection_status.emit(False, f"无数据 ({no_data_count}次超时)")
                    
                except Exception as e:
                    print(f"❌ 数据接收错误: {e}")
                    self.connection_status.emit(False, f"接收错误: {e}")
                    time.sleep(0.5)
        
        except Exception as e:
            print(f"❌ ZMQ连接失败: {e}")
            self.connection_status.emit(False, f"连接失败: {e}")
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """清理资源"""
        try:
            if self.socket:
                self.socket.close()
            if self.context:
                self.context.term()
        except:
            pass
    
    def stop(self):
        """停止线程"""
        self.running = False
        self.wait()


class IMUDualCamViewer(QMainWindow):
    """主窗口类"""
    
    def __init__(self, zmq_host="localhost", zmq_port=5560):
        super().__init__()
        self.zmq_host = zmq_host
        self.zmq_port = zmq_port
        
        # 数据缓存
        self.trajectory_buffer = deque(maxlen=500)  # 轨迹点（最多500个）
        self.chart_buffer = deque(maxlen=100)       # 曲线数据（最近100个）
        self.last_data = None
        
        # UI组件
        self.video_panel = None
        self.imu_panel = None
        self.trajectory_panel = None
        self.chart_panel = None
        self.control_panel = None
        
        # ZMQ接收线程
        self.zmq_receiver = None
        
        # 统计信息
        self.ui_update_count = 0
        self.last_fps_time = time.time()
        self.ui_fps = 0.0
        
        self.init_ui()
        self.start_zmq_receiver()
        
        # 定期更新FPS
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_fps)
        self.fps_timer.start(1000)  # 每秒更新
    
    def init_ui(self):
        """初始化UI布局"""
        self.setWindowTitle("IMU 3D Visualization & Dual Camera Viewer")
        self.setGeometry(100, 100, 1600, 1000)
        
        # 中央窗口
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # === 左侧：控制面板 + IMU数据 ===
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        # 控制面板
        self.control_panel = ControlPanelWidget()
        self.control_panel.reset_clicked.connect(self.on_reset_clicked)
        self.control_panel.export_clicked.connect(self.on_export_clicked)
        left_layout.addWidget(self.control_panel)
        
        # IMU数据面板
        self.imu_panel = IMUPanelWidget()
        left_layout.addWidget(self.imu_panel)
        
        left_layout.addStretch()
        left_widget.setMaximumWidth(300)
        
        # === 中间：双摄像头 ===
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)
        middle_layout.setContentsMargins(5, 5, 5, 5)
        
        self.video_panel = VideoPanelWidget()
        middle_layout.addWidget(self.video_panel)
        
        # === 右侧：3D轨迹 + 曲线图 ===
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        # 3D轨迹
        self.trajectory_panel = Trajectory3DWidget()
        right_layout.addWidget(self.trajectory_panel, 3)
        
        # 曲线图
        self.chart_panel = ChartPanelWidget()
        right_layout.addWidget(self.chart_panel, 2)
        
        # === 组装布局 ===
        main_layout.addWidget(left_widget, 1)
        main_layout.addWidget(middle_widget, 2)
        main_layout.addWidget(right_widget, 2)
        
        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("等待连接...")
    
    def start_zmq_receiver(self):
        """启动ZMQ接收线程"""
        self.zmq_receiver = ZMQDataReceiver(self.zmq_host, self.zmq_port)
        self.zmq_receiver.data_received.connect(self.on_data_received)
        self.zmq_receiver.connection_status.connect(self.on_connection_status)
        self.zmq_receiver.start()
    
    def on_data_received(self, data):
        """处理接收到的数据"""
        try:
            self.last_data = data
            self.ui_update_count += 1
            
            # 更新各个面板
            self.update_video_panel(data)
            self.update_imu_panel(data)
            self.update_trajectory(data)
            self.update_charts(data)
            self.update_control_panel(data)
            
        except Exception as e:
            print(f"⚠️  UI更新错误: {e}")
    
    def update_video_panel(self, data):
        """更新视频显示"""
        video_left = data.get("video_left")
        video_top = data.get("video_top")
        self.video_panel.update_frames(video_left, video_top)
    
    def update_imu_panel(self, data):
        """更新IMU数据"""
        imu_data = {
            "imu1": data.get("imu1", {}),
            "imu2": data.get("imu2", {}),
            "imu3": data.get("imu3", {}),
            "online_status": data.get("online_status", {}),
            "gripper": data.get("gripper", 0.0)
        }
        self.imu_panel.update_data(imu_data)
    
    def update_trajectory(self, data):
        """更新3D轨迹"""
        position = data.get("position", {})
        mapped_pos = position.get("mapped", [0, 0, 0])
        
        # 添加到轨迹缓冲区
        self.trajectory_buffer.append({
            "pos": mapped_pos,
            "timestamp": data.get("timestamp", time.time())
        })
        
        # 传递给3D组件
        self.trajectory_panel.update_trajectory(list(self.trajectory_buffer))
    
    def update_charts(self, data):
        """更新曲线图"""
        # 添加到曲线缓冲区
        self.chart_buffer.append({
            "timestamp": data.get("timestamp", time.time()),
            "imu1": data.get("imu1", {}),
            "imu2": data.get("imu2", {}),
            "imu3": data.get("imu3", {})
        })
        
        # 传递给曲线组件
        self.chart_panel.update_charts(list(self.chart_buffer))
    
    def update_control_panel(self, data):
        """更新控制面板状态"""
        stats = data.get("stats", {})
        online = data.get("online_status", {})
        
        self.control_panel.update_status(
            connected=True,
            publish_rate=stats.get("publish_rate", 0),
            message_count=stats.get("publish_count", 0),
            video_fps=stats.get("video_frame_count", 0),
            imu_online=f"{sum(online.values())}/3"
        )
    
    def on_connection_status(self, connected, message):
        """连接状态变化"""
        if connected:
            self.status_bar.showMessage(f"✓ {message}", 3000)
        else:
            self.status_bar.showMessage(f"⚠ {message}")
    
    def update_fps(self):
        """更新UI FPS"""
        current_time = time.time()
        elapsed = current_time - self.last_fps_time
        if elapsed > 0:
            self.ui_fps = self.ui_update_count / elapsed
            self.ui_update_count = 0
            self.last_fps_time = current_time
            
            self.status_bar.showMessage(f"UI FPS: {self.ui_fps:.1f} | 轨迹点: {len(self.trajectory_buffer)}")
    
    def on_reset_clicked(self):
        """重置按钮点击"""
        self.trajectory_buffer.clear()
        self.chart_buffer.clear()
        self.trajectory_panel.clear_trajectory()
        print("✓ 已重置轨迹和曲线数据")
    
    def on_export_clicked(self):
        """导出按钮点击"""
        print("⚠️  导出功能待实现")
        # TODO: 保存轨迹数据到CSV/JSON文件
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        print("\n正在关闭UI...")
        if self.zmq_receiver:
            self.zmq_receiver.stop()
        event.accept()


def main():
    """主函数"""
    import argparse
    import signal
    
    parser = argparse.ArgumentParser(description="IMU双摄像头可视化查看器")
    parser.add_argument("--host", default="localhost", help="ZMQ服务器地址")
    parser.add_argument("--port", type=int, default=5560, help="ZMQ订阅端口")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    
    # 设置全局字体
    font = QFont("Arial", 9)
    app.setFont(font)
    
    window = IMUDualCamViewer(zmq_host=args.host, zmq_port=args.port)
    window.show()
    
    # 设置信号处理器，让Ctrl+C能正常退出
    def signal_handler(signum, frame):
        print("\n\n🛑 收到退出信号，正在关闭...")
        window.close()
        app.quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 设置定时器让Python解释器能处理信号
    timer = QTimer()
    timer.start(500)  # 每500ms触发一次，让信号能被处理
    timer.timeout.connect(lambda: None)
    
    print(f"\n🎨 PyQt5 UI已启动")
    print(f"📡 订阅地址: tcp://{args.host}:{args.port}")
    print(f"💡 按Ctrl+C或关闭窗口退出\n")
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
