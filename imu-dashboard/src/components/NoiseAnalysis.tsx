import React from 'react';
import { Card, Row, Col } from 'antd';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

interface NoiseStats {
  std: number[];
  mean: number[];
}

interface Props {
  noiseData?: {
    imu1?: NoiseStats;
    imu2?: NoiseStats;
    imu3?: NoiseStats;
  };
}

const NoiseAnalysis: React.FC<Props> = ({ noiseData }) => {
  const getNoiseLevel = (std: number[]) => {
    const maxStd = Math.max(...std);
    if (maxStd < 0.5) return { level: '优秀', color: '#52c41a' };
    if (maxStd < 1.5) return { level: '良好', color: '#1890ff' };
    if (maxStd < 3.0) return { level: '一般', color: '#fa8c16' };
    return { level: '较差', color: '#ff4d4f' };
  };

  return (
    <Card
      title="📈 噪声分析"
      style={{ background: '#1a1f3a', borderRadius: '12px' }}
      headStyle={{ background: '#1a1f3a', borderBottom: '1px solid #2a3f5f', color: '#fff' }}
      bodyStyle={{ background: '#1a1f3a' }}
    >
      <Row gutter={[16, 16]}>
        {['imu1', 'imu2', 'imu3'].map((imuKey, index) => {
          const imuData = noiseData?.[imuKey as keyof typeof noiseData];
          const std = imuData?.std || [0, 0, 0];
          const { level, color } = getNoiseLevel(std);
          
          return (
            <Col span={8} key={imuKey}>
              <div style={{ 
                background: '#2a3f5f', 
                padding: '12px', 
                borderRadius: '8px',
                border: `2px solid ${color}`
              }}>
                <div style={{ color: '#fff', marginBottom: '8px' }}>
                  IMU {index + 1}
                </div>
                <div style={{ fontSize: '12px', color: '#888' }}>
                  <div>Roll σ: {std[0].toFixed(3)}°</div>
                  <div>Pitch σ: {std[1].toFixed(3)}°</div>
                  <div>Yaw σ: {std[2].toFixed(3)}°</div>
                </div>
                <div style={{ 
                  marginTop: '8px', 
                  textAlign: 'center',
                  color: color,
                  fontWeight: 'bold'
                }}>
                  {level}
                </div>
              </div>
            </Col>
          );
        })}
      </Row>
    </Card>
  );
};

export default NoiseAnalysis;
