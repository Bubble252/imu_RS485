#!/usr/bin/env python
"""
测试ZeroMQ PUSH/PULL连接
用于诊断A端和B端的通信问题
"""
import zmq
import pickle
import time

def test_push_connection(host="localhost", port=5555):
    """
    测试PUSH socket连接到B端
    """
    print(f"测试PUSH连接到 {host}:{port}...")
    
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    
    # 设置socket参数
    socket.setsockopt(zmq.SNDHWM, 10)
    socket.setsockopt(zmq.LINGER, 1000)
    socket.setsockopt(zmq.SNDTIMEO, 1000)
    
    # 连接
    address = f"tcp://{host}:{port}"
    socket.connect(address)
    print(f"✓ Socket已connect到 {address}")
    
    # 等待连接建立
    print("等待1秒让连接稳定...")
    time.sleep(1)
    
    # 发送测试消息
    for i in range(5):
        test_msg = {
            "type": "test",
            "message": f"测试消息 #{i+1}",
            "timestamp": time.time()
        }
        
        try:
            socket.send(pickle.dumps(test_msg), zmq.NOBLOCK)
            print(f"✓ 消息 #{i+1} 发送成功")
        except zmq.Again:
            print(f"⚠️ 消息 #{i+1} 发送失败：队列已满（B端可能未运行）")
        except Exception as e:
            print(f"❌ 消息 #{i+1} 发送异常: {e}")
        
        time.sleep(0.5)
    
    print("\n测试完成！")
    socket.close()
    context.term()


if __name__ == "__main__":
    import sys
    
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5555
    
    print("=" * 60)
    print("ZeroMQ PUSH/PULL 连接测试工具")
    print("=" * 60)
    print(f"目标: {host}:{port}")
    print("提示: 确保B端已经启动并监听该端口！")
    print("=" * 60)
    print()
    
    test_push_connection(host, port)
