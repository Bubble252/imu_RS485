import React, { useEffect, useState, useCallback } from 'react';
import { Layout, Row, Col, message, Badge } from 'antd';
import TrajectoryView3D from './components/TrajectoryView3D';
import IMUDashboard from './components/IMUDashboard';
import NoiseAnalysis from './components/NoiseAnalysis';
import ControlPanel from './components/ControlPanel';
import './App.css';

const { Header, Content } = Layout;

interface IMUData {
  roll: number;
  pitch: number;
  yaw: number;
}

interface Position {
  raw: number[];
  mapped: number[];
}

interface TrajectoryPoint {
  x: number;
  y: number;
  z: number;
  timestamp: number;
}

interface NoiseStats {
  std: number[];
  mean: number[];
  max: number[];
  min: number[];
}

interface AppData {
  timestamp: number;
  imu1: IMUData;
  imu2: IMUData;
  imu3: IMUData;
  position: Position;
  gripper: number;
  online_status: {
    imu1: boolean;
    imu2: boolean;
    imu3: boolean;
  };
  trajectory: TrajectoryPoint[];
  noise_analysis: {
    imu1: NoiseStats;
    imu2: NoiseStats;
    imu3: NoiseStats;
  };
  velocity: {
    x: number;
    y: number;
    z: number;
    magnitude: number;
  };
  stats: {
    total_messages: number;
    current_rate: number;
    uptime: number;
  };
  config: {
    L1: number;
    L2: number;
    yaw_mode: string;
  };
}

function App() {
  const [data, setData] = useState<AppData | null>(null);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  const connectWebSocket = useCallback(() => {
    console.log('🔌 正在连接WebSocket...');
    
    const websocket = new WebSocket('ws://localhost:8000/ws');
    
    websocket.onopen = () => {
      console.log('✅ WebSocket已连接');
      setConnected(true);
      setReconnectAttempts(0);
      message.success('已连接到服务器');
    };
    
    websocket.onmessage = (event) => {
      try {
        const newData = JSON.parse(event.data);
        
        // 忽略欢迎消息
        if (newData.type === 'welcome') {
          console.log('📨 收到欢迎消息:', newData.message);
          return;
        }
        
        // 更新数据
        setData(newData);
      } catch (error) {
        console.error('❌ 数据解析失败:', error);
      }
    };
    
    websocket.onerror = (error) => {
      console.error('❌ WebSocket错误:', error);
      message.error('连接出错');
    };
    
    websocket.onclose = () => {
      console.log('🔌 WebSocket已断开');
      setConnected(false);
      
      // 自动重连（最多尝试10次）
      if (reconnectAttempts < 10) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
        console.log(`⏳ ${delay/1000}秒后尝试重连...`);
        setTimeout(() => {
          setReconnectAttempts(prev => prev + 1);
          connectWebSocket();
        }, delay);
      } else {
        message.error('连接失败次数过多，请刷新页面重试');
      }
    };
    
    setWs(websocket);
    
    return () => {
      websocket.close();
    };
  }, [reconnectAttempts]);

  useEffect(() => {
    const cleanup = connectWebSocket();
    return cleanup;
  }, [connectWebSocket]);

  return (
    <Layout style={{ minHeight: '100vh', background: '#0a0e27' }}>
      <Header style={{ 
        background: '#1a1f3a', 
        padding: '0 24px', 
        display: 'flex', 
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1 style={{ 
            color: '#fff', 
            margin: 0, 
            fontSize: '24px',
            fontWeight: 600
          }}>
            🤖 IMU机械臂实时监控系统
          </h1>
          <Badge 
            status={connected ? 'success' : 'error'} 
            text={connected ? '已连接' : '未连接'} 
            style={{ color: '#fff' }}
          />
        </div>
        
        {data && (
          <div style={{ color: '#fff', fontSize: '14px' }}>
            <span>消息数: {data.stats.total_messages}</span>
            <span style={{ marginLeft: '20px' }}>频率: {data.stats.current_rate} Hz</span>
            <span style={{ marginLeft: '20px' }}>运行时间: {Math.floor(data.stats.uptime)}s</span>
          </div>
        )}
      </Header>
      
      <Content style={{ padding: '24px', background: '#0a0e27' }}>
        <Row gutter={[16, 16]}>
          {/* 左侧：3D轨迹可视化 */}
          <Col xs={24} lg={16}>
            <TrajectoryView3D 
              trajectory={data?.trajectory || []} 
              currentPosition={data?.position.mapped || [0, 0, 0]}
            />
          </Col>
          
          {/* 右侧：IMU状态仪表盘 */}
          <Col xs={24} lg={8}>
            <IMUDashboard 
              imu1={data?.imu1}
              imu2={data?.imu2}
              imu3={data?.imu3}
              onlineStatus={data?.online_status}
              gripper={data?.gripper}
              velocity={data?.velocity}
            />
          </Col>
        </Row>
        
        <Row gutter={[16, 16]} style={{ marginTop: '16px' }}>
          {/* 噪声分析图表 */}
          <Col xs={24} lg={16}>
            <NoiseAnalysis 
              noiseData={data?.noise_analysis}
            />
          </Col>
          
          {/* 控制面板 */}
          <Col xs={24} lg={8}>
            <ControlPanel 
              ws={ws} 
              config={data?.config}
            />
          </Col>
        </Row>
      </Content>
    </Layout>
  );
}

export default App;
