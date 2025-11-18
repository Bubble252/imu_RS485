#!/bin/bash
# 快速启动PyQt5 UI - 使用pyqt5_ui环境

# 激活pyqt5_ui环境并启动UI
source ~/miniconda3/etc/profile.d/conda.sh
conda activate pyqt5_ui

cd "$(dirname "$0")"
python imu_dual_cam_viewer.py "$@"
