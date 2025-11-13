import React, { useRef } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Line, Sphere, Grid, Text } from '@react-three/drei';
import * as THREE from 'three';
import { Card } from 'antd';

interface TrajectoryPoint {
  x: number;
  y: number;
  z: number;
  timestamp: number;
}

interface Props {
  trajectory: TrajectoryPoint[];
  currentPosition: number[];
}

function TrajectoryLine({ points }: { points: TrajectoryPoint[] }) {
  if (points.length < 2) return null;
  
  // 转换为Three.js需要的格式
  const linePoints = points.map(p => new THREE.Vector3(p.x, p.y, p.z));
  
  return (
    <Line
      points={linePoints}
      color="cyan"
      lineWidth={2}
      dashed={false}
    />
  );
}

function CurrentPositionMarker({ position }: { position: number[] }) {
  return (
    <Sphere args={[0.01, 16, 16]} position={position as [number, number, number]}>
      <meshStandardMaterial 
        color="red" 
        emissive="red" 
        emissiveIntensity={0.5}
      />
    </Sphere>
  );
}

function StartPositionMarker({ position }: { position: number[] }) {
  return (
    <Sphere args={[0.008, 16, 16]} position={position as [number, number, number]}>
      <meshStandardMaterial 
        color="green" 
        emissive="green" 
        emissiveIntensity={0.5}
      />
    </Sphere>
  );
}

function AxisLabels() {
  return (
    <>
      <Text position={[0.3, 0, 0]} fontSize={0.02} color="red">X</Text>
      <Text position={[0, 0.3, 0]} fontSize={0.02} color="green">Y</Text>
      <Text position={[0, 0, 0.3]} fontSize={0.02} color="blue">Z</Text>
    </>
  );
}

const TrajectoryView3D: React.FC<Props> = ({ trajectory, currentPosition }) => {
  const startPosition = trajectory.length > 0 
    ? [trajectory[0].x, trajectory[0].y, trajectory[0].z]
    : [0, 0, 0];

  return (
    <Card
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>📊 3D轨迹实时显示</span>
          <span style={{ fontSize: '14px', fontWeight: 'normal', color: '#888' }}>
            轨迹点数: {trajectory.length}
          </span>
        </div>
      }
      style={{ 
        background: '#1a1f3a', 
        borderRadius: '12px',
        height: '600px'
      }}
      bodyStyle={{ 
        padding: 0, 
        height: 'calc(100% - 57px)',
        background: '#000'
      }}
      headStyle={{ 
        background: '#1a1f3a', 
        borderBottom: '1px solid #2a3f5f',
        color: '#fff'
      }}
    >
      <Canvas
        camera={{ position: [0.5, 0.5, 0.5], fov: 50 }}
        style={{ background: '#000' }}
      >
        {/* 灯光 */}
        <ambientLight intensity={0.5} />
        <pointLight position={[10, 10, 10]} intensity={1} />
        <pointLight position={[-10, -10, -10]} intensity={0.5} />
        
        {/* 网格和坐标轴 */}
        <Grid 
          args={[1, 1]} 
          cellSize={0.05} 
          cellThickness={0.5}
          cellColor="#333"
          sectionSize={0.2}
          sectionThickness={1}
          sectionColor="#666"
          fadeDistance={2}
          fadeStrength={1}
          followCamera={false}
        />
        
        {/* 坐标轴（使用三个线段） */}
        <Line points={[[0, 0, 0], [0.3, 0, 0]]} color="red" lineWidth={2} />
        <Line points={[[0, 0, 0], [0, 0.3, 0]]} color="green" lineWidth={2} />
        <Line points={[[0, 0, 0], [0, 0, 0.3]]} color="blue" lineWidth={2} />
        
        {/* 坐标轴标签 */}
        <AxisLabels />
        
        {/* 轨迹线 */}
        {trajectory.length > 0 && <TrajectoryLine points={trajectory} />}
        
        {/* 起始位置标记（绿色） */}
        {trajectory.length > 0 && <StartPositionMarker position={startPosition} />}
        
        {/* 当前位置标记（红色） */}
        {currentPosition && currentPosition.length === 3 && (
          <CurrentPositionMarker position={currentPosition} />
        )}
        
        {/* 原点标记（黑色球体） */}
        <Sphere args={[0.005, 16, 16]} position={[0, 0, 0]}>
          <meshStandardMaterial color="#fff" />
        </Sphere>
        
        {/* 相机控制 */}
        <OrbitControls 
          enableDamping
          dampingFactor={0.05}
          rotateSpeed={0.5}
          zoomSpeed={0.5}
        />
      </Canvas>
      
      {/* 底部信息栏 */}
      <div style={{
        position: 'absolute',
        bottom: '10px',
        left: '10px',
        background: 'rgba(0, 0, 0, 0.7)',
        color: '#fff',
        padding: '8px 12px',
        borderRadius: '4px',
        fontSize: '12px',
        fontFamily: 'monospace'
      }}>
        <div>当前位置: [{currentPosition.map(v => v.toFixed(3)).join(', ')}] m</div>
        {trajectory.length > 1 && (
          <div>
            运动时间: {(trajectory[trajectory.length - 1].timestamp - trajectory[0].timestamp).toFixed(1)}s
          </div>
        )}
      </div>
    </Card>
  );
};

export default TrajectoryView3D;
