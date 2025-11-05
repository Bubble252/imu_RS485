# 🎉 CH340 RS485设备 - Linux完整解决方案

## ✅ 问题已解决！

您的CH340 RS485设备现在已经完全适配Linux系统，可以正常使用了！

## 📋 解决的问题

1. **✅ BRLTTY冲突** - 已完全移除，不再干扰CH340设备
2. **✅ 设备识别** - /dev/ttyUSB0 正常创建和识别
3. **✅ 权限问题** - 设备权限正确设置，可读写
4. **✅ 程序错误** - 修复了线程同步和退出时的错误
5. **✅ 自动检测** - 程序能自动找到和配置CH340设备

## 🚀 如何使用

### 快速启动：
```bash
cd /home/bubble/桌面/WIT_RS485
source .venv/bin/activate
python test.py
```

### 简化版启动：
```bash
cd /home/bubble/桌面/WIT_RS485
source .venv/bin/activate
python simple_test.py
```

## 📊 设备信息

- **设备类型**: CH340 USB转串口
- **设备路径**: `/dev/ttyUSB0`
- **USB ID**: `1a86:7523`
- **波特率**: 115200
- **Modbus地址**: 0x50 (可修改)

## 🔧 如果遇到问题

### 设备未找到：
```bash
# 1. 检查设备连接
lsusb | grep CH340

# 2. 重新插拔设备
# 物理重新插拔USB设备

# 3. 检查权限
ls -la /dev/ttyUSB0
```

### 权限问题：
```bash
# 临时解决
sudo chmod 666 /dev/ttyUSB0

# 永久解决（需要重新登录）
sudo usermod -a -G dialout $USER
```

## 📁 项目文件说明

- **`test.py`** - 主测试程序（带自动检测）
- **`simple_test.py`** - 简化测试程序
- **`device_model.py`** - 核心设备驱动类
- **`setup_ch340.sh`** - 自动设置脚本
- **`fix_brltty_conflict.sh`** - BRLTTY冲突解决脚本
- **`auto_fix_ch340.py`** - 自动修复工具
- **`find_serial_device.py`** - 串口设备检测工具
- **`ch340_diagnostic.py`** - 设备诊断工具

## 🔍 数据格式

程序会读取以下传感器数据：
- **加速度**: AccX, AccY, AccZ (单位: g)
- **角速度**: AsX, AsY, AsZ (单位: °/s)
- **磁场**: HX, HY, HZ (单位: Gauss)
- **角度**: AngX, AngY, AngZ (单位: °)

## 🛠️ 自定义配置

### 修改Modbus地址：
在`test.py`中修改：
```python
addrLis = [0x50]  # 改为您的设备地址
```

### 修改波特率：
```python
device = device_model.DeviceModel("设备名", "/dev/ttyUSB0", 115200, addrLis, updateData)
#                                                        ^^^^^^ 修改这里
```

### 修改数据回调：
```python
def updateData(DeviceModel):
    print(DeviceModel.deviceData)
    # 添加您的数据处理逻辑
```

## 🎯 成功标志

当您看到以下输出时，说明一切正常：
```
✅ 找到CH340设备: /dev/ttyUSB0
✅ 权限正常
使用串口: /dev/ttyUSB0
初始化设备模型
/dev/ttyUSB0已打开
启动Data-Received-Thread
设备打开成功
循环读取开始
程序运行中，按 Ctrl+C 停止...
```

## 📞 故障排除

如果程序运行但没有数据，请检查：
1. **传感器连接** - 确保WIT传感器正确连接到RS485转换器
2. **供电** - 确保传感器供电正常
3. **地址配置** - 确认传感器Modbus地址是否为0x50
4. **接线** - 检查RS485的A、B线是否正确连接

## 🎉 恭喜！

您已经成功将Windows版本的WIT RS485代码适配到Linux系统！
设备现在可以在Linux下正常工作了。

---

**创建时间**: 2025年11月5日  
**适配系统**: Ubuntu Linux  
**设备型号**: CH340 USB转RS485  
**状态**: ✅ 完全可用