# B_for_triple.py - 专门适配triple_imu_rs485_publisher.py
# 功能：
# 1. 接收来自A (triple) 的传感器数据 (PUB/SUB 5555)
# 2. 转发传感器数据给C
# 3. 接收来自C的视频数据
# 4. 转发视频给A (PUB 5557)
# 5. 支持LeRobot数据集保存

import json
import threading
import time
import pickle
import zmq
import cv2
import numpy as np
from pathlib import Path
import shutil
import argparse

# LeRobot imports
try:
    from lerobot.datasets.lerobot_dataset import HF_LEROBOT_HOME, LeRobotDataset
except ImportError:
    print("⚠️ 警告: 未找到lerobot库，数据集保存功能将不可用")
    print("请安装: pip install lerobot")
    LeRobotDataset = None

# --- 配置 ---
# B 订阅A (triple)的传感器数据
SERVER_B_HOST = "0.0.0.0"
SERVER_B_PORT_FROM_A_DATA = 5555  # SUB订阅triple的传感器数据

# B 向A推送视频流
SERVER_B_PORT_TO_A_VIDEO = 5557  # PUB发送视频给A

# B 向C转发传感器数据
SERVER_B_PORT_TO_C_DATA = 5556  # PUB发送给C

# B 从C接收视频数据
SERVER_B_PORT_FROM_C_VIDEO = 5558  # SUB接收C的视频

# LeRobot数据集配置
DEFAULT_REPO_ID = "triple_robot_data"
DEFAULT_INSTRUCTION = "Triple IMU teleoperation data"
DEFAULT_FPS = 5  # Triple默认5Hz
DEFAULT_HF_LEROBOT_HOME = Path("triple_robot_data")
# ------------

class TorchSerializer:
    @staticmethod
    def to_bytes(obj) -> bytes:
        return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def from_bytes(data: bytes):
        return pickle.loads(data)


class LeRobotDataHandler:
    """处理LeRobot数据集保存"""
    def __init__(self, repo_id: str, instruction: str = "", fps: int = 5, 
                 data_root: Path = None):
        """
        初始化LeRobot数据集处理器（适配triple数据格式）
        
        Triple数据格式:
        {
            "position": [x, y, z],           # 末端位置（米）
            "orientation": [roll, pitch, yaw], # 姿态（弧度）
            "gripper": 0.0-1.0,              # 夹爪
            "t": timestamp
        }
        """
        if LeRobotDataset is None:
            print("⚠️ LeRobotDataset不可用，数据集保存功能已禁用")
            self.dataset = None
            return
            
        self.instruction = instruction
        self.fps = fps
        
        if data_root is None:
            data_root = DEFAULT_HF_LEROBOT_HOME
        output_path = data_root / repo_id
        
        if output_path.exists():
            print(f"⚠️ 警告: 输出路径 {output_path} 已存在，将被删除")
            shutil.rmtree(output_path)
        print(f"📁 LeRobot数据集路径: {output_path}")
        
        # 创建LeRobot数据集（适配triple的7维数据）
        self.dataset = LeRobotDataset.create(
            repo_id=repo_id,
            root=output_path,
            robot_type="TripleIMU_Arm",
            fps=fps,
            features={
                "observation.state": {
                    "dtype": "float32",
                    "shape": (7,),  # [x, y, z, roll, pitch, yaw, gripper]
                    "names": ["x", "y", "z", "roll", "pitch", "yaw", "gripper"],
                },
                "action": {
                    "dtype": "float32",
                    "shape": (7,),
                    "names": ["x", "y", "z", "roll", "pitch", "yaw", "gripper"],
                },
            },
        )
        print("✅ LeRobot数据集已初始化（Triple IMU格式）")
        self.frame_count = 0
    
    def add_frame(self, triple_data: dict):
        """
        添加一帧triple数据到数据集
        
        Args:
            triple_data: Triple发送的数据字典
                {
                    "position": [x, y, z],
                    "orientation": [roll, pitch, yaw],
                    "gripper": 0.0-1.0,
                    "t": timestamp
                }
        """
        if self.dataset is None:
            return
        
        try:
            # 解析triple数据
            position = triple_data.get("position", [0, 0, 0])
            orientation = triple_data.get("orientation", [0, 0, 0])
            gripper = triple_data.get("gripper", 0.0)
            
            # 构造7维状态向量
            state = np.array([
                position[0],      # x
                position[1],      # y
                position[2],      # z
                orientation[0],   # roll (弧度)
                orientation[1],   # pitch (弧度)
                orientation[2],   # yaw (弧度)
                gripper           # gripper
            ], dtype=np.float32)
            
            # 使用state作为action（主遥操作模式）
            action = state.copy()
            
            # 准备帧数据
            frame_data = {
                "observation.state": state,
                "action": action,
            }
            
            # 添加到数据集
            self.dataset.add_frame(frame_data, self.instruction)
            self.frame_count += 1
            
            if self.frame_count % 100 == 0:
                print(f"📊 已收集 {self.frame_count} 帧triple数据...")
                
        except Exception as e:
            print(f"❌ 添加triple帧数据时出错: {e}")
            import traceback
            traceback.print_exc()


def thread_data_from_triple():
    """
    线程1：接收来自A (triple) 的传感器数据
    并转发给C
    """
    context = None
    socket_from_a = None
    socket_to_c = None
    lerobot_handler = None
    
    # 初始化LeRobot数据处理器
    if LeRobotDataset is not None:
        lerobot_handler = LeRobotDataHandler(
            repo_id=DEFAULT_REPO_ID,
            instruction=DEFAULT_INSTRUCTION,
            fps=DEFAULT_FPS
        )
    
    while True:
        try:
            if context is None:
                context = zmq.Context()
            
            # 订阅来自A (triple) 的传感器数据 (SUB socket)
            if socket_from_a is None:
                socket_from_a = context.socket(zmq.SUB)
                socket_from_a.setsockopt(zmq.RCVTIMEO, 1000)  # 1秒超时
                socket_from_a.setsockopt(zmq.CONFLATE, 1)  # 只保留最新消息
                # Triple使用bind，所以B需要connect
                socket_from_a.connect(f"tcp://localhost:{SERVER_B_PORT_FROM_A_DATA}")
                socket_from_a.setsockopt_string(zmq.SUBSCRIBE, "")  # 订阅所有消息
                print(f"[线程1-数据] 订阅 A (triple) 的传感器数据: localhost:{SERVER_B_PORT_FROM_A_DATA}")
            
            # 向C转发传感器数据 (PUB socket)
            if socket_to_c is None:
                socket_to_c = context.socket(zmq.PUB)
                socket_to_c.bind(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_TO_C_DATA}")
                print(f"[线程1-数据] 向C发布传感器数据: *:{SERVER_B_PORT_TO_C_DATA}")
            
            # 接收triple的传感器数据（带超时）
            try:
                message = socket_from_a.recv_string()
                triple_data = json.loads(message)
                
                # 打印接收到的数据（降低频率）
                if lerobot_handler is None or lerobot_handler.frame_count % 25 == 0:
                    pos = triple_data.get("position", [0, 0, 0])
                    ori = triple_data.get("orientation", [0, 0, 0])
                    gripper = triple_data.get("gripper", 0.0)
                    print(f"[线程1 A→B] 收到triple数据: "
                          f"位置=[{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}], "
                          f"姿态=[{ori[0]:.3f}, {ori[1]:.3f}, {ori[2]:.3f}], "
                          f"夹爪={gripper:.3f}")
                
                # 保存到LeRobot数据集
                if lerobot_handler is not None:
                    lerobot_handler.add_frame(triple_data)
                
                # 转发给C（使用JSON字符串）
                socket_to_c.send_string(message)
                
            except zmq.Again:
                # 超时，继续循环
                continue
            except json.JSONDecodeError as e:
                print(f"[线程1-数据] JSON解析失败: {e}")
                continue
                
        except zmq.ZMQError as e:
            print(f"[线程1-数据] ZMQ 错误: {e}")
            if socket_from_a:
                try:
                    socket_from_a.close()
                except:
                    pass
                socket_from_a = None
            time.sleep(1)
            
        except Exception as e:
            print(f"[线程1-数据] 错误: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(1)


def thread_video_to_triple():
    """
    线程2：接收来自C的视频数据
    并转发给A (triple)
    """
    context = None
    socket_from_c = None
    socket_to_a = None
    
    while True:
        try:
            if context is None:
                context = zmq.Context()
            
            # 订阅来自C的视频数据 (SUB socket)
            if socket_from_c is None:
                socket_from_c = context.socket(zmq.SUB)
                socket_from_c.setsockopt(zmq.RCVTIMEO, 1000)  # 1秒超时
                socket_from_c.setsockopt(zmq.CONFLATE, 1)  # 只保留最新消息
                socket_from_c.bind(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_FROM_C_VIDEO}")
                socket_from_c.setsockopt_string(zmq.SUBSCRIBE, "")  # 订阅所有消息
                print(f"[线程2-视频] 监听 C 的视频数据: *:{SERVER_B_PORT_FROM_C_VIDEO}")
            
            # 向A (triple) 推送视频流 (PUB socket)
            if socket_to_a is None:
                socket_to_a = context.socket(zmq.PUB)
                socket_to_a.setsockopt(zmq.SNDHWM, 1)  # 只保留最新1帧
                socket_to_a.setsockopt(zmq.LINGER, 0)  # 立即丢弃
                socket_to_a.bind(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_TO_A_VIDEO}")
                print(f"[线程2-视频] 向 A (triple) 发布视频: *:{SERVER_B_PORT_TO_A_VIDEO}")
            
            # 接收C的视频数据（带超时）
            try:
                video_data = socket_from_c.recv()
                
                # 解析视频数据（支持pickle和JSON）
                try:
                    frame_dict = pickle.loads(video_data)
                except:
                    try:
                        frame_dict = json.loads(video_data.decode('utf-8'))
                    except:
                        print("[线程2-视频] ⚠️ 视频数据解析失败")
                        continue
                
                # 转发给A（保持pickle格式，兼容triple的video_receiver_thread）
                socket_to_a.send(pickle.dumps(frame_dict))
                
                # 每30帧打印一次
                if isinstance(frame_dict, dict):
                    frame_count = frame_dict.get("frame_count", 0)
                    if frame_count % 30 == 0:
                        data_size = len(video_data) if isinstance(video_data, bytes) else 0
                        print(f"[线程2 C→A] 转发视频帧 #{frame_count}, 大小: {data_size} bytes")
                
            except zmq.Again:
                # 超时，继续循环
                continue
                
        except zmq.ZMQError as e:
            print(f"[线程2-视频] ZMQ 错误: {e}")
            if socket_from_c:
                try:
                    socket_from_c.close()
                except:
                    pass
                socket_from_c = None
            time.sleep(1)
            
        except Exception as e:
            print(f"[线程2-视频] 错误: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(1)


def run_server_b():
    """
    主函数：启动服务器B（专门适配triple）
    """
    print("=" * 70)
    print("服务器 B 启动 - Triple IMU适配模式")
    print("=" * 70)
    print("功能：")
    print("  1. 订阅A (triple)的传感器数据 (端口5555)")
    print("  2. 转发传感器数据给C (端口5556)")
    print("  3. 接收C的视频数据 (端口5558)")
    print("  4. 转发视频给A (端口5557)")
    print("  5. 保存数据为LeRobot格式")
    print("=" * 70)
    
    # 启动线程1：接收triple数据并转发给C
    data_thread = threading.Thread(target=thread_data_from_triple, daemon=True)
    data_thread.start()
    
    # 启动线程2：接收C视频并转发给triple
    video_thread = threading.Thread(target=thread_video_to_triple, daemon=True)
    video_thread.start()
    
    print("\n两个线程已启动")
    print("按 Ctrl+C 停止服务器\n")
    
    try:
        data_thread.join()
        video_thread.join()
    except KeyboardInterrupt:
        print("\n\n服务器 B 正在关闭...")
        print("服务器 B 已关闭。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="B服务器 - Triple IMU适配模式")
    parser.add_argument("--repo-id", type=str, default=DEFAULT_REPO_ID,
                       help="LeRobot数据集仓库ID")
    parser.add_argument("--instruction", type=str, default=DEFAULT_INSTRUCTION,
                       help="任务指令")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS,
                       help="数据采样率")
    
    args = parser.parse_args()
    
    # 更新全局配置
    DEFAULT_REPO_ID = args.repo_id
    DEFAULT_INSTRUCTION = args.instruction
    DEFAULT_FPS = args.fps
    
    run_server_b()
