# B_reverse_whole.py - 反向连接版本，支持LeRobot数据集保存
# 功能：
# 1. 接收来自A的控制命令，转发给C
# 2. 接收来自C的JSON数据（包含视频和机器人数据）
# 3. 将数据转换为lerobot格式并保存到本地
# 4. 同时将视频转发给A
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
# B 监听的端口 (给 A 接收控制命令)
SERVER_B_HOST = "0.0.0.0"
SERVER_B_PORT_FOR_A_COMMAND = 5555

# B 监听的端口 (给 A 推送视频流)
SERVER_B_PORT_FOR_A_VIDEO = 5557

# B 监听的端口 (让 C 主动连接 - 控制命令转发)
SERVER_B_PORT_FOR_C_COMMAND = 5556

# B 监听的端口 (让 C 主动连接 - 数据上传，包含视频和机器人数据)
SERVER_B_PORT_FOR_C_DATA = 5558

# LeRobot数据集配置
DEFAULT_REPO_ID = "real_robot_online_data"
DEFAULT_INSTRUCTION = "Real robot teleoperation data collection"
DEFAULT_FPS = 30
DEFAULT_HF_LEROBOT_HOME = Path("real_robot_data")
# ------------

class TorchSerializer:
    @staticmethod
    def to_bytes(obj) -> bytes:
        # 将 Python 对象序列化为字节
        return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def from_bytes(data: bytes):
        # 将字节反序列化为 Python 对象
        return pickle.loads(data)


class LeRobotDataHandler:
    """
    处理LeRobot数据集保存的类
    """
    def __init__(self, repo_id: str, instruction: str = "", fps: int = 30, 
                 data_root: Path = None, action_dim: int = 13, state_dim: int = 13,
                 image_shape: tuple = (480, 640, 3)):
        """
        初始化LeRobot数据集处理器
        
        Args:
            repo_id: 数据集仓库ID
            instruction: 任务指令
            fps: 视频帧率
            data_root: 数据保存根目录
            action_dim: 动作维度
            state_dim: 状态维度
            image_shape: 图像形状 (height, width, channel)
        """
        if LeRobotDataset is None:
            print("⚠️ LeRobotDataset不可用，数据集保存功能已禁用")
            self.dataset = None
            return
            
        self.instruction = instruction
        self.fps = fps
        
        # 设置输出路径
        if data_root is None:
            data_root = DEFAULT_HF_LEROBOT_HOME
        output_path = data_root / repo_id
        
        if output_path.exists():
            print(f"⚠️ 警告: 输出路径 {output_path} 已存在，将被删除")
            shutil.rmtree(output_path)
        print(f"📁 LeRobot数据集路径: {output_path}")
        
        # 创建LeRobot数据集
        self.dataset = LeRobotDataset.create(
            repo_id=repo_id,
            root=output_path,
            robot_type="MyDexHand",  # 可根据实际情况修改
            fps=fps,
            features={
                "observation.images.image": {
                    "dtype": "video",
                    "shape": image_shape,
                    "names": ["height", "width", "channel"],
                    "video_info": {
                        "video.fps": fps,
                        "video.codec": "h264",
                        "video.pix_fmt": "yuv420p",
                    }
                },
                "observation.state": {
                    "dtype": "float32",
                    "shape": (state_dim,),
                    "names": [f"state_{i}" for i in range(state_dim)],
                },
                "action": {
                    "dtype": "float32",
                    "shape": (action_dim,),
                    "names": [f"action_{i}" for i in range(action_dim)],
                },
            },
        )
        print("✅ LeRobot数据集已初始化，准备接收数据")
        self.frame_count = 0
    
    def add_frame(self, data_dict: dict):
        """
        添加一帧数据到数据集
        
        Args:
            data_dict: 包含以下字段的字典:
                - image 或 camera_1.rgb: 图像数据 (numpy array 或 bytes)
                - state 或 observation.state: 机器人状态 (numpy array 或 list)
                - action: 动作数据 (numpy array 或 list)
                - episode_end: 是否episode结束 (bool, 可选)
        """
        if self.dataset is None:
            return
        
        try:
            # 处理图像数据（支持多种字段名）
            image = data_dict.get("image") or data_dict.get("camera_1.rgb")
            if image is None:
                # 不打印警告，因为可能只是转发视频而不保存数据集
                return
            
            # 如果图像是bytes（JPEG编码），需要解码
            if isinstance(image, bytes):
                nparr = np.frombuffer(image, np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if image is None:
                    print("⚠️ 警告: 图像解码失败")
                    return
                # BGR转RGB（OpenCV使用BGR，但LeRobot通常使用RGB）
                if len(image.shape) == 3 and image.shape[2] == 3:
                    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # 确保图像是numpy array
            if not isinstance(image, np.ndarray):
                print("⚠️ 警告: 图像格式不正确")
                return
            
            # 处理状态数据（支持多种字段名）
            state = data_dict.get("state") or data_dict.get("observation.state")
            if state is None:
                # 尝试从其他字段构建状态（例如：euler_angles + throttle）
                euler = data_dict.get("euler_angles", {})
                throttle = data_dict.get("throttle", 0)
                if euler:
                    state = [
                        euler.get("roll", 0),
                        euler.get("pitch", 0),
                        euler.get("yaw", 0),
                        throttle
                    ]
                else:
                    print("⚠️ 警告: 数据中缺少state字段且无法构建")
                    return
            
            if not isinstance(state, np.ndarray):
                state = np.array(state, dtype=np.float32)
            else:
                state = state.astype(np.float32)
            
            # 处理动作数据
            action = data_dict.get("action")
            if action is None:
                # 如果没有action，可以使用state作为action（某些情况下）
                action = state.copy()
                print("⚠️ 警告: 数据中缺少action字段，使用state作为action")
            
            if not isinstance(action, np.ndarray):
                action = np.array(action, dtype=np.float32)
            else:
                action = action.astype(np.float32)
            
            # 准备帧数据
            frame_data = {
                "observation.images.image": image,
                "observation.state": state,
                "action": action,
            }
            
            # 添加到数据集
            self.dataset.add_frame(frame_data, self.instruction)
            self.frame_count += 1
            
            # 检查是否episode结束
            episode_end = data_dict.get("episode_end", False)
            if episode_end:
                print(f"📦 Episode结束，保存数据集 (总帧数: {self.frame_count})...")
                self.dataset.save_episode()
                print(f"✅ Episode已保存到 {self.dataset.root}")
                self.frame_count = 0
            elif self.frame_count % 100 == 0:
                print(f"📊 已收集 {self.frame_count} 帧数据...")
                
        except Exception as e:
            print(f"❌ 添加帧数据时出错: {e}")
            import traceback
            traceback.print_exc()


def parse_json_data(raw_data):
    """
    解析来自C的数据
    
    支持多种格式:
    1. Python字典（已通过pickle序列化）
    2. JSON字符串（bytes或str）
    3. 包含视频和机器人数据的字典
    
    Args:
        raw_data: 原始数据（bytes或dict）
    
    Returns:
        dict: 解析后的数据字典，包含:
            - image: 图像数据（numpy array或bytes）
            - state: 机器人状态（numpy array或list）
            - action: 动作数据（numpy array或list）
            - episode_end: episode结束标志（bool，可选）
            - 其他原始字段
    """
    # 如果已经是字典，直接返回
    if isinstance(raw_data, dict):
        return raw_data
    
    # 如果是bytes，先尝试pickle反序列化（最常见的情况）
    if isinstance(raw_data, bytes):
        try:
            # 先尝试pickle（C_real_video_reverse.py使用pickle）
            data = pickle.loads(raw_data)
            if isinstance(data, dict):
                return data
        except Exception as e:
            pass
        
        # 如果pickle失败，尝试JSON
        try:
            json_str = raw_data.decode('utf-8')
            data = json.loads(json_str)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"⚠️ 数据解析失败（既不是pickle也不是JSON）: {e}")
            return None
    
    # 如果是字符串，尝试解析JSON
    if isinstance(raw_data, str):
        try:
            return json.loads(raw_data)
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON解析失败: {e}")
            return None
    
    return None


def extract_video_for_forwarding(data_dict: dict) -> bytes:
    """
    从数据字典中提取视频数据，用于转发给A
    
    Args:
        data_dict: 包含视频数据的字典（支持多种字段名）
        
    Returns:
        bytes: 视频帧的字节数据（JPEG编码），如果提取失败返回None
    """
    # 支持多种字段名
    image = data_dict.get("image") or data_dict.get("camera_1.rgb")
    
    if image is None:
        return None
    
    # 如果图像是numpy array，需要编码为JPEG
    if isinstance(image, np.ndarray):
        # 如果是RGB，转换为BGR（OpenCV使用BGR）
        if len(image.shape) == 3 and image.shape[2] == 3:
            # 检查是否是RGB（通常LeRobot使用RGB）
            # 如果已经是BGR，直接使用；如果是RGB，转换为BGR
            # 这里假设如果是RGB格式，需要转换
            try:
                image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            except:
                # 如果转换失败，假设已经是BGR
                image_bgr = image
        else:
            image_bgr = image
        
        # 编码为JPEG
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
        result, encoded_frame = cv2.imencode('.jpg', image_bgr, encode_param)
        if result:
            return encoded_frame.tobytes()
        else:
            print("⚠️ 图像编码失败")
            return None
    
    # 如果已经是bytes，直接返回
    if isinstance(image, bytes):
        return image
    
    return None


def thread_command_handler():
    """
    线程1：处理控制命令流 (A -> B -> C)
    反向模式：C 主动连接 B
    支持 A 断开重连，自动恢复
    """
    context = None
    socket_from_a = None
    socket_to_c = None
    
    while True:
        try:
            if context is None:
                context = zmq.Context()
            
            # 接收来自 A 的控制命令 (PULL socket)
            if socket_from_a is None:
                socket_from_a = context.socket(zmq.PULL)
                socket_from_a.setsockopt(zmq.RCVTIMEO, 1000)  # 1秒超时
                socket_from_a.bind(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_FOR_A_COMMAND}")
                print(f"[线程1-命令] 监听 A 的命令: *:{SERVER_B_PORT_FOR_A_COMMAND}")
            
            # 等待 C 主动连接并接收命令 (PUSH socket - B 推送给 C)
            if socket_to_c is None:
                socket_to_c = context.socket(zmq.PUSH)
                socket_to_c.bind(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_FOR_C_COMMAND}")
                print(f"[线程1-命令] 等待 C 连接: *:{SERVER_B_PORT_FOR_C_COMMAND}")
            
            # 接收 A 的命令（带超时）
            try:
                message = socket_from_a.recv()
            except zmq.Again:
                continue
            
            command = TorchSerializer.from_bytes(message)
            print(f"\n[线程1 A→C] 收到控制命令: {command}")
            
            # 转发给 C（如果 C 已连接）
            try:
                socket_to_c.send(TorchSerializer.to_bytes(command), zmq.NOBLOCK)
                print(f"[线程1 A→C] 命令已转发给 C")
            except zmq.Again:
                print(f"[线程1 A→C] ⚠️ C 未连接，命令已丢弃")
            
        except zmq.ZMQError as e:
            print(f"[线程1-命令] ZMQ 错误: {e}")
            if socket_from_a:
                try:
                    socket_from_a.close()
                except:
                    pass
                socket_from_a = None
            time.sleep(1)
            
        except Exception as e:
            print(f"[线程1-命令] 错误: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(1)


def thread_data_handler(lerobot_handler: LeRobotDataHandler):
    """
    线程2：处理数据流 (C -> B -> A)
    反向模式：C 主动连接 B 并推送数据
    功能：
    1. 接收来自C的JSON数据（包含视频和机器人数据）
    2. 转换为lerobot格式并保存
    3. 提取视频并转发给A
    支持 C 断开重连，自动恢复
    """
    context = None
    socket_from_c = None
    socket_to_a = None
    
    while True:
        try:
            if context is None:
                context = zmq.Context()
            
            # 等待 C 主动连接并推送数据 (PULL socket - B 接收)
            if socket_from_c is None:
                socket_from_c = context.socket(zmq.PULL)
                socket_from_c.setsockopt(zmq.RCVTIMEO, 1000)  # 1秒超时
                socket_from_c.bind(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_FOR_C_DATA}")
                print(f"[线程2-数据] 等待 C 连接并推送数据: *:{SERVER_B_PORT_FOR_C_DATA}")
            
            # 向 A 推送视频流 (PUB socket)
            if socket_to_a is None:
                socket_to_a = context.socket(zmq.PUB)
                socket_to_a.setsockopt(zmq.SNDHWM, 1)  # 只保留最新1帧
                socket_to_a.setsockopt(zmq.LINGER, 0)  # 立即丢弃
                socket_to_a.bind(f"tcp://{SERVER_B_HOST}:{SERVER_B_PORT_FOR_A_VIDEO}")
                print(f"[线程2-数据] 向 A 发布视频: *:{SERVER_B_PORT_FOR_A_VIDEO}")
            
            # 接收 C 推送的数据（带超时）
            try:
                raw_data = socket_from_c.recv()
                
                # 解析数据
                data_dict = parse_json_data(raw_data)
                if data_dict is None:
                    print("[线程2-数据] ⚠️ 数据解析失败，跳过")
                    continue
                
                # 打印接收到的数据信息（降低频率）
                data_size = len(raw_data) if isinstance(raw_data, bytes) else 0
                has_image = "image" in data_dict or "camera_1.rgb" in data_dict
                has_state = "state" in data_dict or "observation.state" in data_dict
                has_action = "action" in data_dict
                print(f"[线程2 C→B] 收到数据，大小: {data_size} bytes, "
                      f"包含: 图像={has_image}, 状态={has_state}, 动作={has_action}")
                
                # 保存到LeRobot数据集
                if lerobot_handler is not None:
                    lerobot_handler.add_frame(data_dict)
                
                # 提取视频并转发给A
                video_bytes = extract_video_for_forwarding(data_dict)
                if video_bytes:
                    # 准备转发给A的数据格式（保持与A的兼容性）
                    video_frame = {
                        "image": video_bytes,
                        "encoding": "jpeg",
                        "timestamp": data_dict.get("timestamp", time.time()),
                        "resolution": data_dict.get("resolution", "640x480"),
                        "frame_count": data_dict.get("frame_count", 0),
                    }
                    socket_to_a.send(TorchSerializer.to_bytes(video_frame))
                    print(f"[线程2 B→A] 视频已转发给 A，大小: {len(video_bytes)} bytes")
                else:
                    print("[线程2 B→A] ⚠️ 无法提取视频数据，跳过转发")
                    
            except zmq.Again:
                # 超时，继续循环检查（C 可能未连接）
                continue
            
        except zmq.ZMQError as e:
            print(f"[线程2-数据] ZMQ 错误: {e}")
            if socket_from_c:
                try:
                    socket_from_c.close()
                except:
                    pass
                socket_from_c = None
            time.sleep(1)
            
        except Exception as e:
            print(f"[线程2-数据] 错误: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(1)


def run_server_b(repo_id: str = None, instruction: str = None, fps: int = None,
                 data_root: str = None, action_dim: int = 13, state_dim: int = 13,
                 image_shape: tuple = None):
    """
    主函数：启动服务器B
    
    Args:
        repo_id: LeRobot数据集仓库ID
        instruction: 任务指令
        fps: 视频帧率
        data_root: 数据保存根目录
        action_dim: 动作维度
        state_dim: 状态维度
        image_shape: 图像形状 (height, width, channel)
    """
    print("=" * 60)
    print("服务器 B 启动 - 反向连接模式 + LeRobot数据集保存")
    print("适用于 C 在 NAT 后面无法被直接访问的情况")
    print("✅ 支持 A 和 C 断开后自动重连")
    print("✅ 支持将数据保存为LeRobot格式")
    print("=" * 60)
    
    # 初始化LeRobot数据处理器
    if LeRobotDataset is not None:
        if image_shape is None:
            image_shape = (480, 640, 3)
        if data_root:
            data_root = Path(data_root)
        else:
            data_root = DEFAULT_HF_LEROBOT_HOME
        
        lerobot_handler = LeRobotDataHandler(
            repo_id=repo_id or DEFAULT_REPO_ID,
            instruction=instruction or DEFAULT_INSTRUCTION,
            fps=fps or DEFAULT_FPS,
            data_root=data_root,
            action_dim=action_dim,
            state_dim=state_dim,
            image_shape=image_shape
        )
    else:
        lerobot_handler = None
        print("⚠️ LeRobot数据集保存功能已禁用")
    
    # 启动线程1：命令处理
    command_thread = threading.Thread(target=thread_command_handler, daemon=True)
    command_thread.start()
    
    # 启动线程2：数据处理（包含视频转发和数据集保存）
    data_thread = threading.Thread(target=thread_data_handler, args=(lerobot_handler,), daemon=True)
    data_thread.start()
    
    print("\n两个线程已启动，等待 C 连接...")
    print("按 Ctrl+C 停止服务器\n")
    
    try:
        # 保持主线程运行
        command_thread.join()
        data_thread.join()
    except KeyboardInterrupt:
        print("\n\n服务器 B 正在关闭...")
        if lerobot_handler and lerobot_handler.dataset and lerobot_handler.frame_count > 0:
            print("保存未完成的episode...")
            try:
                lerobot_handler.dataset.save_episode()
                print("✅ 未完成的episode已保存")
            except:
                pass
        print("服务器 B 已关闭。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="B服务器 - 反向连接模式，支持LeRobot数据集保存")
    parser.add_argument("--repo-id", type=str, default=DEFAULT_REPO_ID,
                       help="LeRobot数据集仓库ID")
    parser.add_argument("--instruction", type=str, default=DEFAULT_INSTRUCTION,
                       help="任务指令")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS,
                       help="视频帧率")
    parser.add_argument("--data-root", type=str, default=str(DEFAULT_HF_LEROBOT_HOME),
                       help="数据保存根目录")
    parser.add_argument("--action-dim", type=int, default=13,
                       help="动作维度")
    parser.add_argument("--state-dim", type=int, default=13,
                       help="状态维度")
    parser.add_argument("--image-height", type=int, default=480,
                       help="图像高度")
    parser.add_argument("--image-width", type=int, default=640,
                       help="图像宽度")
    
    args = parser.parse_args()
    
    image_shape = (args.image_height, args.image_width, 3)
    
    run_server_b(
        repo_id=args.repo_id,
        instruction=args.instruction,
        fps=args.fps,
        data_root=args.data_root,
        action_dim=args.action_dim,
        state_dim=args.state_dim,
        image_shape=image_shape
    )
