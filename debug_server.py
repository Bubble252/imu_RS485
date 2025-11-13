#!/usr/bin/env python
# coding:UTF-8
"""
IMU调试数据后端服务 - FastAPI + WebSocket
负责桥接主程序(ZeroMQ)和前端UI(WebSocket)

架构：
    主程序(triple_imu_rs485_publisher.py) 
        ↓ ZeroMQ PUB (port 5560)
    本服务(debug_server.py)
        ↓ WebSocket (port 8000)
    前端UI(React)

功能：
1. 订阅主程序的ZeroMQ调试数据流
2. 数据处理：轨迹缓冲、噪声分析、统计计算
3. WebSocket服务器：广播给所有连接的前端客户端
4. RESTful API：健康检查、配置查询

运行方法：
    python debug_server.py
    或
    uvicorn debug_server:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import zmq
import zmq.asyncio
import asyncio
import json
from typing import List, Dict, Any
import numpy as np
from collections import deque
import time
from datetime import datetime

# ===========================
# FastAPI应用初始化
# ===========================

app = FastAPI(
    title="IMU Debug Server",
    description="IMU机械臂实时调试数据服务 - WebSocket桥接",
    version="1.0.0"
)

# CORS配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===========================
# 全局状态管理
# ===========================

class DataManager:
    """数据管理器 - 缓冲、统计、分析"""
    
    def __init__(self, max_trajectory_points=1000, max_noise_samples=100):
        # 轨迹缓冲区（最近N个点）
        self.trajectory_buffer = deque(maxlen=max_trajectory_points)
        
        # 噪声分析缓冲区（用于计算标准差）
        self.noise_buffer = {
            "imu1": deque(maxlen=max_noise_samples),
            "imu2": deque(maxlen=max_noise_samples),
            "imu3": deque(maxlen=max_noise_samples)
        }
        
        # 统计信息
        self.stats = {
            "total_messages": 0,
            "start_time": time.time(),
            "last_update_time": 0,
            "current_rate": 0.0
        }
        
        # 最新数据
        self.latest_data = None
    
    def process_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理原始数据，添加增强信息
        
        增强内容：
        - 轨迹历史（最近50个点用于绘图）
        - 噪声分析（标准差、均值）
        - 速度计算（位置变化率）
        - 统计信息（消息计数、频率）
        """
        self.stats["total_messages"] += 1
        self.stats["last_update_time"] = time.time()
        
        # 计算实际接收频率
        if self.stats["total_messages"] % 20 == 0:
            elapsed = time.time() - self.stats["start_time"]
            self.stats["current_rate"] = self.stats["total_messages"] / elapsed if elapsed > 0 else 0.0
        
        # === 轨迹处理 ===
        if "position" in raw_data and "mapped" in raw_data["position"]:
            mapped_pos = raw_data["position"]["mapped"]
            self.trajectory_buffer.append({
                "x": mapped_pos[0],
                "y": mapped_pos[1],
                "z": mapped_pos[2],
                "timestamp": raw_data.get("timestamp", time.time())
            })
        
        # === 噪声分析 ===
        noise_analysis = {}
        for imu_name in ["imu1", "imu2", "imu3"]:
            if imu_name in raw_data:
                imu_data = raw_data[imu_name]
                sample = [
                    imu_data.get("roll", 0.0),
                    imu_data.get("pitch", 0.0),
                    imu_data.get("yaw", 0.0)
                ]
                self.noise_buffer[imu_name].append(sample)
                
                # 计算统计量（至少10个样本）
                if len(self.noise_buffer[imu_name]) >= 10:
                    samples_array = np.array(list(self.noise_buffer[imu_name]))
                    noise_analysis[imu_name] = {
                        "std": samples_array.std(axis=0).tolist(),  # 标准差 [roll, pitch, yaw]
                        "mean": samples_array.mean(axis=0).tolist(),  # 均值
                        "max": samples_array.max(axis=0).tolist(),  # 最大值
                        "min": samples_array.min(axis=0).tolist()   # 最小值
                    }
                else:
                    noise_analysis[imu_name] = {
                        "std": [0.0, 0.0, 0.0],
                        "mean": [0.0, 0.0, 0.0],
                        "max": [0.0, 0.0, 0.0],
                        "min": [0.0, 0.0, 0.0]
                    }
        
        # === 速度计算（位置变化率）===
        velocity = {"x": 0.0, "y": 0.0, "z": 0.0, "magnitude": 0.0}
        if len(self.trajectory_buffer) >= 2:
            last = self.trajectory_buffer[-1]
            prev = self.trajectory_buffer[-2]
            dt = last["timestamp"] - prev["timestamp"]
            if dt > 0:
                velocity = {
                    "x": (last["x"] - prev["x"]) / dt,
                    "y": (last["y"] - prev["y"]) / dt,
                    "z": (last["z"] - prev["z"]) / dt
                }
                velocity["magnitude"] = np.sqrt(velocity["x"]**2 + velocity["y"]**2 + velocity["z"]**2)
        
        # === 构造增强数据 ===
        enhanced_data = raw_data.copy()
        enhanced_data.update({
            "trajectory": list(self.trajectory_buffer)[-50:],  # 最近50个点
            "noise_analysis": noise_analysis,
            "velocity": velocity,
            "stats": {
                "total_messages": self.stats["total_messages"],
                "current_rate": round(self.stats["current_rate"], 2),
                "uptime": round(time.time() - self.stats["start_time"], 1)
            }
        })
        
        self.latest_data = enhanced_data
        return enhanced_data


# 全局数据管理器实例
data_manager = DataManager()


# ===========================
# WebSocket连接管理
# ===========================

class ConnectionManager:
    """管理所有WebSocket连接"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """接受新连接"""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"✅ 新客户端连接 | 当前连接数: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"❌ 客户端断开 | 当前连接数: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """广播给所有客户端"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"⚠️  发送失败，标记断开: {e}")
                disconnected.append(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)
    
    def get_connection_count(self) -> int:
        """获取当前连接数"""
        return len(self.active_connections)


manager = ConnectionManager()


# ===========================
# ZeroMQ异步监听
# ===========================

async def zmq_listener(zmq_port: int = 5560):
    """
    异步监听ZeroMQ数据流（从主程序订阅）
    
    使用zmq.asyncio实现真正的异步非阻塞
    """
    print(f"\n🔧 启动ZeroMQ监听器...")
    print(f"   订阅地址: tcp://localhost:{zmq_port}")
    
    # 使用asyncio版本的zmq
    context = zmq.asyncio.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://localhost:{zmq_port}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    print(f"✅ ZeroMQ订阅已连接\n")
    
    message_count = 0
    
    while True:
        try:
            # 异步接收（非阻塞）
            data_bytes = await socket.recv()
            data = json.loads(data_bytes.decode('utf-8'))
            
            message_count += 1
            
            # 数据处理和增强
            enhanced_data = data_manager.process_data(data)
            
            # 广播给所有WebSocket客户端
            if manager.get_connection_count() > 0:
                await manager.broadcast(enhanced_data)
            
            # 每100条打印一次日志
            if message_count % 100 == 0:
                print(f"📊 已处理 {message_count} 条消息 | "
                      f"WebSocket客户端: {manager.get_connection_count()} | "
                      f"接收频率: {enhanced_data['stats']['current_rate']:.1f} Hz")
        
        except Exception as e:
            print(f"❌ ZeroMQ接收错误: {e}")
            await asyncio.sleep(0.1)


# ===========================
# FastAPI路由定义
# ===========================

@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    print("="*70)
    print("🚀 IMU调试数据后端服务启动")
    print("="*70)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"WebSocket端点: ws://localhost:8000/ws")
    print(f"API文档: http://localhost:8000/docs")
    print("="*70 + "\n")
    
    # 创建后台任务监听ZeroMQ
    asyncio.create_task(zmq_listener())


@app.get("/")
async def root():
    """根路径 - 服务信息"""
    return {
        "service": "IMU Debug Server",
        "version": "1.0.0",
        "status": "running",
        "websocket": "/ws",
        "api_docs": "/docs",
        "connections": manager.get_connection_count(),
        "stats": data_manager.stats
    }


@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "connections": manager.get_connection_count(),
        "total_messages": data_manager.stats["total_messages"],
        "uptime": time.time() - data_manager.stats["start_time"]
    }


@app.get("/api/stats")
async def get_stats():
    """获取统计信息"""
    return {
        "stats": data_manager.stats,
        "connections": manager.get_connection_count(),
        "trajectory_points": len(data_manager.trajectory_buffer),
        "noise_samples": {
            k: len(v) for k, v in data_manager.noise_buffer.items()
        }
    }


@app.get("/api/latest")
async def get_latest_data():
    """获取最新数据（HTTP轮询备用方案）"""
    if data_manager.latest_data:
        return JSONResponse(content=data_manager.latest_data)
    else:
        return JSONResponse(
            status_code=404,
            content={"error": "No data available yet"}
        )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket端点 - 实时数据推送
    
    客户端可以发送控制命令（预留功能）：
    {
        "command": "reset_trajectory",  // 重置轨迹
        "command": "export_data"        // 导出数据
    }
    """
    await manager.connect(websocket)
    
    try:
        # 发送欢迎消息
        await websocket.send_json({
            "type": "welcome",
            "message": "Connected to IMU Debug Server",
            "timestamp": time.time()
        })
        
        while True:
            # 接收客户端消息（控制命令）
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=1.0
                )
                
                # 处理控制命令
                if "command" in data:
                    command = data["command"]
                    
                    if command == "reset_trajectory":
                        data_manager.trajectory_buffer.clear()
                        await websocket.send_json({
                            "type": "command_result",
                            "command": "reset_trajectory",
                            "status": "success"
                        })
                        print("🔄 轨迹已重置")
                    
                    elif command == "export_data":
                        # 导出数据（未来实现）
                        await websocket.send_json({
                            "type": "command_result",
                            "command": "export_data",
                            "status": "not_implemented"
                        })
                    
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Unknown command: {command}"
                        })
            
            except asyncio.TimeoutError:
                # 超时正常，继续循环
                await asyncio.sleep(0.01)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"⚠️  WebSocket错误: {e}")
        manager.disconnect(websocket)


# ===========================
# 主程序入口
# ===========================

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*70)
    print("启动方式：")
    print("  方式1（推荐）: python debug_server.py")
    print("  方式2（开发）: uvicorn debug_server:app --reload --port 8000")
    print("="*70 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
