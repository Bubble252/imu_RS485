#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
依赖检查脚本 - 验证PyQt5 UI所需的所有依赖
"""

import sys

print("=" * 50)
print("  IMU双摄像头可视化查看器 - 依赖检查")
print("=" * 50)
print()

dependencies = {
    "PyQt5": "PyQt5",
    "pyqtgraph": "pyqtgraph",
    "PyOpenGL": "OpenGL",
    "pyzmq": "zmq",
    "opencv-python": "cv2",
    "numpy": "numpy",
    "pickle": "pickle"
}

missing = []
installed = []

for package_name, import_name in dependencies.items():
    try:
        __import__(import_name)
        installed.append(package_name)
        print(f"✓ {package_name:20} 已安装")
    except ImportError:
        missing.append(package_name)
        print(f"✗ {package_name:20} 未安装")

print()
print("=" * 50)

if missing:
    print(f"⚠️  缺少 {len(missing)} 个依赖包")
    print()
    print("请运行以下命令安装:")
    print(f"pip3 install {' '.join(missing)}")
    print()
    sys.exit(1)
else:
    print(f"✓ 所有依赖 ({len(installed)}) 已安装!")
    print()
    print("可以运行以下命令启动UI:")
    print("./start_viewer.sh")
    print()
    sys.exit(0)
