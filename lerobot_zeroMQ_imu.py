import os
import mujoco
import mujoco.viewer
import numpy as np
import time
import zmq
import json
import threading
import sys
from lerobot_kinematics import lerobot_IK, lerobot_FK, get_robot

sys.path.append('/home/bubble/桌面/lerobot-kinematics/lerobot_kinematics')
sys.path.append('/home/bubble/桌面/lerobot-kinematics/lerobot_kinematics/lerobot')
print(sys.path)
np.set_printoptions(linewidth=200)

# 此文件的整体功能是通过ZeroMQ接收位置姿态信息来控制机械臂的运动
# 接收的数据包含手腕位置(x,y,z)、姿态(roll,pitch,yaw)和夹爪状态
# 机械臂的运动是通过逆运动学计算得到的
# 逆运动学计算使用了lerobot_kinematics库中的lerobot_IK函数

# Set up the MuJoCo render backend
os.environ["MUJOCO_GL"] = "egl"

# Define joint names
JOINT_NAMES = ['shoulder_rotation_joint', 'shoulder_pitch_joint', 'ellbow_joint', 
               'wrist_pitch_joint', 'wrist_jaw_joint', 'wrist_roll_joint', 'gripper_joint']

# Absolute path of the XML model
xml_path = "./examples/scene_plus.xml"
mjmodel = mujoco.MjModel.from_xml_path(xml_path)
qpos_indices = np.array([mjmodel.jnt_qposadr[mjmodel.joint(name).id] for name in JOINT_NAMES])
mjdata = mujoco.MjData(mjmodel)

# Create robot
robot = get_robot('so100_plus')

# Define joint limits
control_qlimit = [[-2.1, -3.1, -0.0, -1.375, -1.40, -1.57, -0.15],
                  [ 2.1,  0.0,  3.1,  1.475,  1.40,  3.1,   1.5]]

# 手腕位置姿态限制
control_glimit = [[0.210, -0.4, -0.047, -3.1, -0.75, -1.5],
                  [0.420,  0.4,  0.360,   3.1,  1.45,  1.5]]

# Initialize target joint positions
init_qpos = np.array([0.0, -3.1, 3.0, 0.0, 0.0, 1.57, -0.157])
target_qpos = init_qpos.copy()
init_gpos = lerobot_FK(init_qpos[:6], robot=robot)
target_gpos = init_gpos.copy()

# ZeroMQ setup（匹配triple_imu_rs485_publisher.py的PUSH模式）
context = zmq.Context()
socket = context.socket(zmq.PULL)  # 改为PULL模式，匹配triple的PUSH
socket.bind("tcp://127.0.0.1:5559")  # 绑定到5559端口（独立端口，避免与B端5555冲突）
print(f"✓ ZeroMQ PULL socket已绑定到 tcp://127.0.0.1:5559")
print("  等待triple_imu_rs485_publisher.py连接...")

# Thread-safe variables
lock = threading.Lock()
received_data = None
new_data_available = False

def zmq_receiver():
    """ZeroMQ接收线程（PULL模式，从triple_imu_rs485_publisher.py接收）"""
    global received_data, new_data_available
    
    while True:
        try:
            # PULL模式会阻塞等待，不需要NOBLOCK
            message = socket.recv_string()
            data = json.loads(message)
            
            with lock:
                received_data = data
                new_data_available = True
                
            # 降低打印频率
            if np.random.rand() < 0.1:  # 10%概率打印
                print(f"接收到数据: pos={data.get('position', [])[:3]}, gripper={data.get('gripper', 0):.3f}")
            
        except json.JSONDecodeError:
            print("JSON解析错误")
        except Exception as e:
            print(f"ZeroMQ接收错误: {e}")

def validate_and_clamp_gpos(gpos):
    """验证并限制手腕位置姿态"""
    clamped_gpos = gpos.copy()
    
    for i in range(len(gpos)):
        if i < len(control_glimit[0]):
            clamped_gpos[i] = np.clip(gpos[i], control_glimit[0][i], control_glimit[1][i])
    
    return clamped_gpos

def validate_and_clamp_qpos(qpos):
    """验证并限制关节位置"""
    clamped_qpos = qpos.copy()
    
    for i in range(len(qpos)):
        if i < len(control_qlimit[0]):
            clamped_qpos[i] = np.clip(qpos[i], control_qlimit[0][i], control_qlimit[1][i])
    
    return clamped_qpos

# 启动ZeroMQ接收线程
zmq_thread = threading.Thread(target=zmq_receiver, daemon=True)
zmq_thread.start()

# Backup for target_gpos in case of invalid IK
target_gpos_last = init_gpos.copy()

try:
    # Launch the MuJoCo viewer
    with mujoco.viewer.launch_passive(mjmodel, mjdata) as viewer:
        import glfw

        # 找到当前 MuJoCo viewer 的 GLFW 窗口
        if hasattr(viewer, "glfw"):
            window = viewer.glfw.window
        elif hasattr(viewer, "context"):
            window = viewer.context.window
        else:
            window = None

        if window is not None:
            glfw.set_key_callback(window, lambda *args: None)

        start = time.time()
        while viewer.is_running() and time.time() - start < 1000:
            step_start = time.time()

            # 处理ZeroMQ接收到的数据
            with lock:
                if new_data_available and received_data is not None:
                    try:
                        # 解析接收到的数据
                        # 期望的数据格式: {"position": [x, y, z], "orientation": [roll, pitch, yaw], "gripper": gripper_value}
                        if "position" in received_data and "orientation" in received_data:
                            position = received_data["position"]
                            orientation = received_data["orientation"]
                            
                            # 构造新的目标位置姿态
                            new_target_gpos = np.array([
                                position[0],      # x
                                position[1],      # y  
                                position[2],      # z
                                orientation[0],   # roll
                                orientation[1],   # pitch
                                orientation[2]+0    # yaw
                            ])
                            
                            # 验证并限制位置姿态
                            new_target_gpos = validate_and_clamp_gpos(new_target_gpos)
                            target_gpos = new_target_gpos
                            
                            # 处理夹爪
                            if "gripper" in received_data:
                                gripper_value = received_data["gripper"]
                                # 限制夹爪值在合理范围内
                                gripper_value = np.clip(gripper_value, control_qlimit[0][6], control_qlimit[1][6])
                                target_qpos[6] = gripper_value
                        
                        elif "reset" in received_data and received_data["reset"]:
                            # 重置到初始位置
                            target_qpos = init_qpos.copy()
                            target_gpos = init_gpos.copy()
                            print("机械臂重置到初始位置")
                            
                    except (KeyError, IndexError, TypeError) as e:
                        print(f"数据格式错误: {e}")
                    
                    new_data_available = False

            print("target_gpos:", [f"{x:.3f}" for x in target_gpos])
            
            # 计算逆运动学
            fd_qpos = mjdata.qpos[qpos_indices][:6]
            qpos_inv, ik_success = lerobot_IK(fd_qpos[:6], target_gpos, robot=robot)
            
            if ik_success:  # Check if IK solution is valid
                # 构造新的目标关节位置
                new_target_qpos = np.concatenate((qpos_inv[:6], target_qpos[6:]))
                
                # 验证并限制关节位置
                new_target_qpos = validate_and_clamp_qpos(new_target_qpos)
                target_qpos = new_target_qpos
                
                mjdata.qpos[qpos_indices] = target_qpos

                mujoco.mj_step(mjmodel, mjdata)
                with viewer.lock():
                    viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT] = int(mjdata.time % 2)
                viewer.sync()
                
                target_gpos_last = target_gpos.copy()  # Save backup of target_gpos
            else:
                target_gpos = target_gpos_last.copy()  # Restore the last valid target_gpos
                print("逆运动学求解失败，恢复到上一个有效位置")
                
            # Time management to maintain simulation timestep
            time_until_next_step = mjmodel.opt.timestep - (time.time() - step_start)
            if time_until_next_step > 0:
                time.sleep(time_until_next_step)

except KeyboardInterrupt:
    print("用户中断仿真")
finally:
    socket.close()
    context.term()
    if 'viewer' in locals():
        viewer.close()
    print("程序结束")
