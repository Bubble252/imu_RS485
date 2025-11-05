# WIT RS485 Linux版本

这是一个用于Linux系统的WIT传感器RS485通信库。

## 系统要求

- Linux操作系统
- Python 3.6+
- pyserial库

## 安装依赖

```bash
pip3 install pyserial
```

## Linux串口设备说明

在Linux系统中，串口设备通常表现为以下形式：

- `/dev/ttyUSB0`, `/dev/ttyUSB1` - USB转串口设备
- `/dev/ttyACM0`, `/dev/ttyACM1` - USB CDC ACM设备
- `/dev/ttyS0`, `/dev/ttyS1` - 标准串口
- `/dev/ttyAMA0` - ARM设备串口(如树莓派)

## 权限设置

如果遇到权限问题，需要将用户添加到`dialout`组：

```bash
sudo usermod -a -G dialout $USER
```

添加后需要重新登录或重启系统。

## 使用方法

1. 确保传感器设备已连接到Linux系统
2. 运行程序：

```bash
python3 test.py
```

程序会自动检测可用的串口设备并尝试连接。

## 手动指定串口

如果需要手动指定串口，可以修改`test.py`文件中的串口名称：

```python
# 将自动检测的部分替换为：
device = device_model.DeviceModel("测试设备1", "/dev/ttyUSB0", 115200, addrLis, updateData)
```

## 故障排除

1. **串口权限问题**：确保用户在`dialout`组中
2. **找不到串口设备**：检查设备连接和驱动程序
3. **模块导入错误**：确保pyserial已正确安装

## 与Windows版本的区别

- 串口名称从`COM*`格式改为Linux的`/dev/tty*`格式
- 添加了自动串口检测功能
- 添加了权限和驱动程序检查提示

## 支持的传感器数据

- 加速度: AccX, AccY, AccZ
- 角速度: AsX, AsY, AsZ  
- 磁场: HX, HY, HZ
- 角度: AngX, AngY, AngZ