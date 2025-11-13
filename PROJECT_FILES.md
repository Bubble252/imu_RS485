# 📁 IMU调试UI系统 - 文件清单

## ✅ 已生成的完整代码

### 🐍 后端服务

1. **debug_server.py** (421行)
   - FastAPI + WebSocket服务器
   - ZeroMQ订阅主程序调试数据
   - 数据处理：轨迹缓冲、噪声分析、速度计算
   - RESTful API端点
   - 自动重连机制

2. **requirements_debug_server.txt**
   - Python依赖包列表
   - 安装命令：`pip install -r requirements_debug_server.txt`

### ⚛️ 前端UI（React + TypeScript）

#### 配置文件
3. **imu-dashboard/package.json**
   - npm项目配置
   - 依赖包：React、Three.js、Ant Design、Chart.js

4. **imu-dashboard/tsconfig.json**
   - TypeScript编译配置

5. **imu-dashboard/public/index.html**
   - HTML入口文件

#### 源代码
6. **imu-dashboard/src/index.tsx**
   - React应用入口

7. **imu-dashboard/src/App.tsx** (210行)
   - 主应用组件
   - WebSocket连接管理
   - 自动重连逻辑
   - 布局组合

8. **imu-dashboard/src/App.css**
   - 全局样式

9. **imu-dashboard/src/index.css**
   - 基础样式

#### React组件
10. **imu-dashboard/src/components/TrajectoryView3D.tsx** (165行)
    - 3D轨迹可视化
    - Three.js场景渲染
    - 交互控制（旋转、缩放、平移）
    - 坐标轴、网格、标记点

11. **imu-dashboard/src/components/IMUDashboard.tsx** (155行)
    - IMU状态卡片（三个IMU）
    - 欧拉角实时显示
    - 夹爪开合度进度条
    - 运动速度统计

12. **imu-dashboard/src/components/NoiseAnalysis.tsx** (95行)
    - 噪声标准差统计
    - 噪声等级评估（优秀/良好/一般/较差）
    - 三个IMU的噪声对比

13. **imu-dashboard/src/components/ControlPanel.tsx** (100行)
    - 系统配置显示
    - 重置轨迹按钮
    - 导出数据按钮（预留）
    - 交互帮助提示

### 🔧 主程序修改

14. **triple_imu_rs485_publisher.py** (已修改)
    - **新增**：`debug_publisher_thread()` 函数（约150行）
    - **新增**：`--enable-debug` 和 `--debug-port` 参数
    - **新增**：ZeroMQ PUB socket（端口5560）
    - 发布频率：20Hz
    - 数据格式：JSON
    - 最小侵入：仅新增一个独立线程

### 🚀 启动和管理脚本

15. **start_debug_ui.sh** (190行)
    - 一键启动脚本
    - 依赖检查
    - 三种启动模式选择
    - 自动创建日志目录
    - 进程管理（PID记录）

16. **stop_debug_ui.sh** (50行)
    - 一键停止所有服务
    - 清理残留进程
    - 删除PID文件

### 📚 文档

17. **DEBUG_UI_README.md** (500+行)
    - 完整使用文档
    - 架构详解
    - 安装指南
    - API文档
    - 故障排查
    - 性能优化建议

18. **QUICK_START.md**
    - 快速开始指南
    - 新手友好
    - 测试数据流示例

19. **PROJECT_FILES.md** (本文件)
    - 文件清单
    - 架构总览

---

## 📊 代码统计

| 类别 | 文件数 | 代码行数（估算） |
|------|--------|------------------|
| Python后端 | 1 | ~420行 |
| TypeScript前端 | 9 | ~900行 |
| 配置文件 | 4 | ~100行 |
| Shell脚本 | 2 | ~240行 |
| 文档 | 3 | ~700行 |
| **总计** | **19** | **~2360行** |

---

## 🏗️ 目录结构

```
WIT_RS485/
├── triple_imu_rs485_publisher.py  (主程序，已修改)
├── debug_server.py                (后端服务，新增)
├── requirements_debug_server.txt  (后端依赖，新增)
├── start_debug_ui.sh              (启动脚本，新增，可执行)
├── stop_debug_ui.sh               (停止脚本，新增，可执行)
├── DEBUG_UI_README.md             (完整文档，新增)
├── QUICK_START.md                 (快速开始，新增)
├── PROJECT_FILES.md               (本文件，新增)
│
├── imu-dashboard/                 (前端项目，新增)
│   ├── package.json
│   ├── tsconfig.json
│   ├── public/
│   │   └── index.html
│   └── src/
│       ├── index.tsx
│       ├── index.css
│       ├── App.tsx
│       ├── App.css
│       └── components/
│           ├── TrajectoryView3D.tsx
│           ├── IMUDashboard.tsx
│           ├── NoiseAnalysis.tsx
│           └── ControlPanel.tsx
│
├── logs/                          (运行时生成)
│   ├── main_program.log
│   ├── backend.log
│   └── frontend.log
│
└── .pids/                         (运行时生成)
    ├── main.pid
    ├── backend.pid
    └── frontend.pid
```

---

## 🔄 数据流架构

```
┌──────────────────────────────────┐
│  主程序 (triple...py)             │
│  - IMU数据采集                     │
│  - 运动学计算                      │
│  - 主要功能：发布到B端和LeRobot     │
│  + 新增：调试数据发布线程           │
└────────┬─────────────────────────┘
         │ ZeroMQ PUB
         │ tcp://*:5560
         │ JSON格式，20Hz
         ↓
┌──────────────────────────────────┐
│  后端服务 (debug_server.py)       │
│  - ZeroMQ SUB订阅                 │
│  - 数据处理和增强                  │
│  - 轨迹缓冲、噪声分析、速度计算     │
└────────┬─────────────────────────┘
         │ WebSocket
         │ ws://localhost:8000/ws
         │ 实时双向通信
         ↓
┌──────────────────────────────────┐
│  前端UI (React)                   │
│  - 3D轨迹可视化 (Three.js)        │
│  - IMU仪表盘 (Ant Design)         │
│  - 噪声分析图表 (Chart.js)        │
│  - 交互控制面板                    │
└──────────────────────────────────┘
```

---

## 🎯 核心特性

### ✅ 已实现功能

1. **实时3D轨迹显示**
   - 最近1000个位置点
   - 起点/当前位置标记
   - 交互式3D控制

2. **IMU状态监控**
   - 三个IMU的欧拉角实时显示
   - 在线/离线状态指示
   - 夹爪开合度可视化

3. **噪声分析**
   - 标准差计算
   - 自动等级评估
   - 三IMU对比

4. **数据统计**
   - 消息计数
   - 接收频率
   - 运行时间
   - 速度计算

5. **交互控制**
   - 重置轨迹
   - 导出数据（预留接口）
   - WebSocket命令通信

6. **自动化部署**
   - 一键启动/停止
   - 依赖自动检查
   - 进程管理

### 🔮 预留扩展功能

- 数据录制和回放
- 实时参数调节
- 多设备支持
- 移动端适配
- AI异常检测

---

## 🚀 使用流程

### 开发环境

```bash
# 1. 安装依赖（首次）
pip install -r requirements_debug_server.txt
cd imu-dashboard && npm install && cd ..

# 2. 启动系统
./start_debug_ui.sh

# 3. 访问UI
# 浏览器打开 http://localhost:3000

# 4. 停止系统
./stop_debug_ui.sh
```

### 生产环境

```bash
# 前端构建
cd imu-dashboard
npm run build
# 将build/目录部署到Nginx

# 后端部署
# 使用systemd或supervisor管理进程
```

---

## 📝 下一步建议

1. **首次测试**：
   ```bash
   ./start_debug_ui.sh
   # 选择模式2（仅后端+前端，测试UI）
   ```

2. **连接真实硬件**：
   ```bash
   ./start_debug_ui.sh
   # 选择模式1（完整模式）
   ```

3. **定制UI**：
   - 修改颜色主题：编辑 `App.css`
   - 调整布局：编辑 `App.tsx`
   - 添加新图表：创建新组件

4. **性能优化**：
   - 降低发布频率（减少网络负载）
   - 减少轨迹缓冲区（节省内存）
   - 使用生产构建（提升UI性能）

---

## 🎊 总结

您现在拥有一个**完整的**、**专业级**的IMU调试UI系统：

- ✅ 零侵入主程序（仅增加一个线程）
- ✅ 现代化Web界面（React + Three.js）
- ✅ 实时数据可视化（3D轨迹 + 图表）
- ✅ 完善的文档（500+行使用指南）
- ✅ 自动化脚本（一键启动/停止）

**立即开始**: `./start_debug_ui.sh` 🚀
