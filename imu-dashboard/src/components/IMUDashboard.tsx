import React from 'react';
import { Card, Row, Col, Statistic, Progress, Tag } from 'antd';
import { RocketOutlined, ThunderboltOutlined } from '@ant-design/icons';

interface IMUData {
  roll: number;
  pitch: number;
  yaw: number;
}

interface Props {
  imu1?: IMUData;
  imu2?: IMUData;
  imu3?: IMUData;
  onlineStatus?: {
    imu1: boolean;
    imu2: boolean;
    imu3: boolean;
  };
  gripper?: number;
  velocity?: {
    x: number;
    y: number;
    z: number;
    magnitude: number;
  };
}

const IMUCard: React.FC<{ title: string; data?: IMUData; online: boolean }> = ({ 
  title, 
  data, 
  online 
}) => (
  <Card
    size="small"
    style={{ 
      background: '#2a3f5f', 
      marginBottom: '12px',
      border: online ? '2px solid #52c41a' : '2px solid #ff4d4f'
    }}
  >
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
      <span style={{ color: '#fff', fontWeight: 600 }}>{title}</span>
      <Tag color={online ? 'success' : 'error'}>
        {online ? '在线' : '离线'}
      </Tag>
    </div>
    
    {data && (
      <Row gutter={8}>
        <Col span={8}>
          <div style={{ color: '#888', fontSize: '12px' }}>Roll</div>
          <div style={{ color: '#1890ff', fontSize: '16px', fontWeight: 'bold' }}>
            {data.roll.toFixed(2)}°
          </div>
        </Col>
        <Col span={8}>
          <div style={{ color: '#888', fontSize: '12px' }}>Pitch</div>
          <div style={{ color: '#52c41a', fontSize: '16px', fontWeight: 'bold' }}>
            {data.pitch.toFixed(2)}°
          </div>
        </Col>
        <Col span={8}>
          <div style={{ color: '#888', fontSize: '12px' }}>Yaw</div>
          <div style={{ color: '#fa8c16', fontSize: '16px', fontWeight: 'bold' }}>
            {data.yaw.toFixed(2)}°
          </div>
        </Col>
      </Row>
    )}
  </Card>
);

const IMUDashboard: React.FC<Props> = ({ 
  imu1, 
  imu2, 
  imu3, 
  onlineStatus, 
  gripper,
  velocity
}) => {
  const gripperPercent = (gripper || 0) * 100;
  const velocityMag = velocity?.magnitude || 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* IMU状态卡片 */}
      <Card
        title="🎯 IMU传感器状态"
        style={{ background: '#1a1f3a', borderRadius: '12px' }}
        headStyle={{ background: '#1a1f3a', borderBottom: '1px solid #2a3f5f', color: '#fff' }}
        bodyStyle={{ background: '#1a1f3a' }}
      >
        <IMUCard 
          title="IMU 1 (杆1)" 
          data={imu1} 
          online={onlineStatus?.imu1 || false} 
        />
        <IMUCard 
          title="IMU 2 (杆2)" 
          data={imu2} 
          online={onlineStatus?.imu2 || false} 
        />
        <IMUCard 
          title="IMU 3 (机械爪)" 
          data={imu3} 
          online={onlineStatus?.imu3 || false} 
        />
      </Card>

      {/* 夹爪状态 */}
      <Card
        title="🤏 夹爪开合度"
        style={{ background: '#1a1f3a', borderRadius: '12px' }}
        headStyle={{ background: '#1a1f3a', borderBottom: '1px solid #2a3f5f', color: '#fff' }}
        bodyStyle={{ background: '#1a1f3a' }}
      >
        <Progress
          percent={gripperPercent}
          strokeColor={{
            '0%': '#ff4d4f',
            '100%': '#52c41a',
          }}
          format={percent => `${percent?.toFixed(1)}%`}
        />
        <div style={{ textAlign: 'center', marginTop: '8px', color: '#888', fontSize: '12px' }}>
          {gripperPercent < 30 ? '闭合' : gripperPercent > 70 ? '打开' : '中等'}
        </div>
      </Card>

      {/* 运动速度 */}
      <Card
        title={<><RocketOutlined /> 运动速度</>}
        style={{ background: '#1a1f3a', borderRadius: '12px' }}
        headStyle={{ background: '#1a1f3a', borderBottom: '1px solid #2a3f5f', color: '#fff' }}
        bodyStyle={{ background: '#1a1f3a' }}
      >
        <Statistic
          value={velocityMag}
          precision={4}
          suffix="m/s"
          valueStyle={{ color: velocityMag > 0.01 ? '#3f8600' : '#888' }}
        />
        {velocity && (
          <div style={{ marginTop: '12px', fontSize: '12px', color: '#888' }}>
            <div>Vx: {velocity.x.toFixed(4)} m/s</div>
            <div>Vy: {velocity.y.toFixed(4)} m/s</div>
            <div>Vz: {velocity.z.toFixed(4)} m/s</div>
          </div>
        )}
      </Card>
    </div>
  );
};

export default IMUDashboard;
