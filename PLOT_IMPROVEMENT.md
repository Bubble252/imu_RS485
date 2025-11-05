# 三IMU RS485发布器 - 绘图功能改进说明

## 改进概述

已将 `triple_imu_rs485_publisher.py` 的绘图功能升级，完全借鉴 `dual_imu_euler.py` 和 `dual_imu_publisher.py` 的实现。

## 改进前 vs 改进后

### 改进前（简单版本）
```python
# 只有2个子图
fig = plt.figure(figsize=(12, 5))
- 子图1: 3D轨迹
- 子图2: XY平面投影

# 问题：
❌ 中文标签显示为方框（字体警告）
❌ 缺少XZ、YZ平面投影
❌ 缺少时间序列图
❌ 缺少详细统计信息
❌ 非交互环境下会报错
```

### 改进后（完整版本）
```python
# 6个子图（2x3布局）
fig = plt.figure(figsize=(18, 10))
- 子图1: 3D轨迹
- 子图2: XY平面投影（俯视图）
- 子图3: XZ平面投影（侧视图）
- 子图4: YZ平面投影（正视图）
- 子图5-6: 位置vs时间（占据两个位置）

# 改进点：
✅ 设置中文字体支持，避免字体警告
✅ 添加所有3个投影视图
✅ 添加位置随时间变化图
✅ 添加详细统计信息（采样频率、轨迹长度等）
✅ 优雅处理非交互环境
✅ 使用bbox_inches='tight'保存图片
```

## 新增功能详解

### 1. 中文字体支持
```python
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial Unicode MS', 'SimHei']
matplotlib.rcParams['axes.unicode_minus'] = False
```
**效果**: 消除所有中文字符警告（如"末端轨迹"等）

### 2. 完整的6子图布局

#### 子图1: 3D轨迹
- 蓝色线条显示完整轨迹
- 绿色圆圈标记起点
- 红色叉标记终点
- 黑色圆圈标记原点（基座）

#### 子图2-4: 三个投影视图
- **XY投影（俯视图）**: 观察水平面运动
- **XZ投影（侧视图）**: 观察垂直面运动
- **YZ投影（正视图）**: 观察另一垂直面运动
- 所有投影使用`axis('equal')`保证比例正确

#### 子图5-6: 时间序列
- X、Y、Z三条曲线同时显示
- 红色=X，绿色=Y，蓝色=Z
- 可以观察位置随时间的变化趋势

### 3. 详细统计信息

```
轨迹统计:
  总点数: 100                      ← 记录的数据点数量
  持续时间: 9.90 秒                ← 从开始到结束的时间
  采样频率: 10.1 Hz                ← 平均采样率
  轨迹总长度: 0.9896 m (989.6 mm) ← 累计运动距离

位置范围:
  X: [0.2000, 0.4000] m            ← X轴活动范围
  Y: [-0.1000, 0.1000] m           ← Y轴活动范围
  Z: [0.0000, 0.0000] m            ← Z轴活动范围（本例为平面运动）
```

### 4. 错误处理改进

```python
try:
    plt.show()
except:
    print("✓ 图表已生成（非交互环境，仅保存文件）")
```
**效果**: 在SSH或无显示环境下不会报错，仅保存文件

## 文件对比

| 特性 | 改进前 | 改进后 |
|------|--------|--------|
| 子图数量 | 2个 | 6个 |
| 投影视图 | 1个(XY) | 3个(XY, XZ, YZ) |
| 时间序列 | ❌ | ✅ |
| 中文支持 | ⚠️警告 | ✅完美 |
| 统计信息 | ❌ | ✅完整 |
| 图片质量 | 262KB | 337KB |
| 布局优化 | 基本 | tight_layout |
| 错误处理 | 基本 | 完善 |

## 使用示例

### 运行主程序
```bash
# 启动发布器并采集数据
python triple_imu_rs485_publisher.py --online-only

# 按Ctrl+C停止后，会自动生成轨迹图
# 输出文件: trajectory_rs485.png
```

### 测试绘图功能
```bash
# 使用模拟数据测试绘图
python test_plot.py

# 输出文件: trajectory_rs485_test.png
```

## 图表解读指南

### 1. 3D轨迹图（左上）
- **用途**: 全局视角观察机械臂末端的完整运动
- **关键点**: 
  - 绿色起点：初始位置
  - 红色终点：最终位置
  - 黑色原点：基座位置

### 2. XY投影（中上）
- **用途**: 俯视视角，观察水平面运动
- **适用**: 分析机械臂在工作台面的覆盖范围
- **axis('equal')**: 保证X、Y比例一致

### 3. XZ投影（右上）
- **用途**: 侧视视角，观察高度变化
- **适用**: 分析机械臂的抬升/下降动作

### 4. YZ投影（左下）
- **用途**: 正视视角，观察前后和高度变化
- **适用**: 分析机械臂的前伸/回缩动作

### 5. 位置vs时间（底部）
- **用途**: 时域分析，观察运动速度和加速度
- **关键点**:
  - 陡峭的斜率 = 快速运动
  - 平坦的曲线 = 静止或慢速
  - 震荡 = 抖动或振动

## 技术细节

### 数据流程
```
RS485采集 → 运动学计算 → 轨迹记录 → 停止程序 → 绘图函数 → PNG文件
            ↓
    trajectory_positions (deque)
    trajectory_timestamps (deque)
```

### 内存优化
```python
trajectory_positions = deque(maxlen=1000)
trajectory_timestamps = deque(maxlen=1000)
```
- 使用deque自动限制最多1000个点
- 避免长时间运行内存溢出
- 1000点 @ 5Hz = 200秒 = 3.3分钟

### 性能考虑
- **图片分辨率**: 150 DPI（平衡质量和文件大小）
- **图片尺寸**: 18x10英寸（2700x1500像素）
- **文件大小**: ~300-400KB（PNG格式）

## 常见问题

### Q: 为什么有中文字符警告？
A: 已修复。新版本设置了中文字体回退列表。

### Q: 可以调整图片分辨率吗？
A: 可以。修改`plt.savefig()`的dpi参数：
```python
plt.savefig('trajectory_rs485.png', dpi=300)  # 更高质量
```

### Q: 如何只保存特定投影？
A: 注释掉不需要的子图即可：
```python
# 只保留3D和XY投影
# ax3 = fig.add_subplot(2, 3, 3)  # 注释掉XZ投影
# ax4 = fig.add_subplot(2, 3, 4)  # 注释掉YZ投影
```

### Q: 能实时显示轨迹吗？
A: 当前版本在程序结束后显示。如需实时显示，需要添加动画功能：
```python
from matplotlib.animation import FuncAnimation
# 需要重构代码以支持实时更新
```

## 与蓝牙版本的差异

| 特性 | RS485版本 | 蓝牙版本 |
|------|-----------|----------|
| 数据源 | device_model (串口) | bleak (蓝牙) |
| 采集方式 | 同步轮询 | 异步回调 |
| 轨迹记录 | publisher_loop中 | display_euler_angles中 |
| 绘图逻辑 | ✅完全一致 | ✅完全一致 |
| 输出文件 | trajectory_rs485.png | trajectory.png |

## 未来改进方向

### 1. 交互式3D可视化
```python
# 使用plotly实现可旋转的3D图
import plotly.graph_objects as go
```

### 2. 动画导出
```python
# 导出为GIF或MP4动画
from matplotlib.animation import FuncAnimation, PillowWriter
```

### 3. 数据导出
```python
# 导出轨迹数据为CSV
import pandas as pd
df = pd.DataFrame(trajectory_positions, columns=['x', 'y', 'z'])
df.to_csv('trajectory.csv')
```

### 4. 实时绘图模式
```python
# 边采集边显示（需要修改架构）
plt.ion()  # 开启交互模式
# 在publisher_loop中定期更新图表
```

## 总结

✅ **完成度**: 100%，完全借鉴了dual_imu_euler.py的绘图逻辑
✅ **兼容性**: 无字体警告，支持无显示环境
✅ **功能性**: 6个子图，完整统计信息
✅ **可维护性**: 代码结构清晰，易于扩展

改进后的绘图功能为机械臂运动分析提供了全面的可视化支持！
