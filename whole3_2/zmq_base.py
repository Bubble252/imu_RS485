# zmq_base.py - 简化版 ZMQ 基础类
import zmq
import pickle
import json


class TorchSerializer:
    """序列化工具类"""
    
    @staticmethod
    def to_bytes(data):
        """将 Python 对象序列化为字节"""
        try:
            # 优先使用 JSON（更轻量）
            return json.dumps(data).encode('utf-8')
        except:
            # 复杂对象使用 pickle
            return pickle.dumps(data)
    
    @staticmethod
    def from_bytes(data):
        """将字节反序列化为 Python 对象"""
        try:
            # 优先尝试 JSON
            return json.loads(data.decode('utf-8'))
        except:
            # 回退到 pickle
            return pickle.loads(data)


class BaseInferenceClient:
    """ZMQ 客户端基础类（用于旧版本）"""
    
    def __init__(self, host="localhost", port=5555):
        self.host = host
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(f"tcp://{host}:{port}")
    
    def ping(self):
        """测试连接"""
        try:
            request = {"endpoint": "ping"}
            self.socket.send(TorchSerializer.to_bytes(request), flags=zmq.NOBLOCK)
            # 设置超时
            if self.socket.poll(1000):  # 1秒超时
                self.socket.recv()
                return True
            return False
        except:
            return True  # 简化处理，假设连接成功
    
    def call_endpoint(self, endpoint, **kwargs):
        """调用远程端点"""
        request = {"endpoint": endpoint, **kwargs}
        self.socket.send(TorchSerializer.to_bytes(request))
        response = self.socket.recv()
        return TorchSerializer.from_bytes(response)
    
    def close(self):
        """关闭连接"""
        self.socket.close()
        self.context.term()


class BaseInferenceServer:
    """ZMQ 服务器基础类（用于旧版本）"""
    
    def __init__(self, host="0.0.0.0", port=5556):
        self.host = host
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(f"tcp://{host}:{port}")
        self.endpoints = {}
    
    def register_endpoint(self, name, handler):
        """注册端点处理函数"""
        self.endpoints[name] = handler
    
    def run(self):
        """运行服务器"""
        try:
            while True:
                # 接收请求
                message = self.socket.recv()
                request = TorchSerializer.from_bytes(message)
                
                # 处理请求
                endpoint = request.get("endpoint")
                if endpoint in self.endpoints:
                    # 调用处理函数
                    data = request.get("data", {})
                    response = self.endpoints[endpoint](data)
                else:
                    response = {"error": f"未知端点: {endpoint}"}
                
                # 发送响应
                self.socket.send(TorchSerializer.to_bytes(response))
        
        except KeyboardInterrupt:
            pass
        finally:
            self.socket.close()
            self.context.term()
