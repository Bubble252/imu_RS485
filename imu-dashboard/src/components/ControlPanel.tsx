import React, { useState } from 'react';
import { Card, Button, Space, message } from 'antd';
import { ReloadOutlined, DownloadOutlined, SettingOutlined } from '@ant-design/icons';

interface Props {
  ws: WebSocket | null;
  config?: {
    L1: number;
    L2: number;
    yaw_mode: string;
  };
}

const ControlPanel: React.FC<Props> = ({ ws, config }) => {
  const [loading, setLoading] = useState(false);

  const sendCommand = (command: string) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      message.error('WebSocket未连接');
      return;
    }

    setLoading(true);
    ws.send(JSON.stringify({ command }));
    
    setTimeout(() => {
      setLoading(false);
      message.success(`命令已发送: ${command}`);
    }, 500);
  };

  return (
    <Card
      title={<><SettingOutlined /> 控制面板</>}
      style={{ background: '#1a1f3a', borderRadius: '12px' }}
      headStyle={{ background: '#1a1f3a', borderBottom: '1px solid #2a3f5f', color: '#fff' }}
      bodyStyle={{ background: '#1a1f3a' }}
    >
      {/* 配置信息 */}
      {config && (
        <div style={{ 
          background: '#2a3f5f', 
          padding: '12px', 
          borderRadius: '8px',
          marginBottom: '16px',
          color: '#fff'
        }}>
          <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>
            系统配置
          </div>
          <div style={{ fontSize: '12px', color: '#888' }}>
            <div>L1 (杆1长度): {config.L1 * 1000} mm</div>
            <div>L2 (杆2长度): {config.L2 * 1000} mm</div>
            <div>Yaw归零模式: {config.yaw_mode}</div>
          </div>
        </div>
      )}

      {/* 控制按钮 */}
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Button
          type="primary"
          icon={<ReloadOutlined />}
          block
          loading={loading}
          onClick={() => sendCommand('reset_trajectory')}
        >
          重置轨迹
        </Button>

        <Button
          icon={<DownloadOutlined />}
          block
          loading={loading}
          onClick={() => sendCommand('export_data')}
        >
          导出数据
        </Button>
      </Space>

      {/* 帮助信息 */}
      <div style={{ 
        marginTop: '16px', 
        padding: '12px', 
        background: '#2a3f5f',
        borderRadius: '8px',
        fontSize: '12px',
        color: '#888'
      }}>
        <div style={{ fontWeight: 600, marginBottom: '4px', color: '#fff' }}>提示:</div>
        <div>• 使用鼠标拖拽旋转3D视图</div>
        <div>• 滚轮缩放视图</div>
        <div>• 重置轨迹可清空历史数据</div>
      </div>
    </Card>
  );
};

export default ControlPanel;
