#!/usr/bin/env python3
"""
快速验证脚本 - 检查集成是否正确
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, '/home/bubble/桌面/WIT_RS485')

def test_imports():
    """测试导入"""
    print("="*60)
    print("1. 测试导入...")
    print("="*60)
    
    try:
        # 测试主程序导入
        import triple_imu_rs485_publisher_dual_cam_UI_voice as main_prog
        print("✓ 主程序模块导入成功")
        
        # 测试UI导入
        sys.path.insert(0, '/home/bubble/桌面/WIT_RS485/pyqt5_viewer')
        from widgets.gripper_control import GripperControlWidget
        from widgets.audio_waveform import AudioWaveformWidget
        print("✓ 夹爪控制widget导入成功")
        print("✓ 音频波形widget导入成功")
        
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False


def test_functions():
    """测试函数定义"""
    print("\n" + "="*60)
    print("2. 测试函数定义...")
    print("="*60)
    
    try:
        import triple_imu_rs485_publisher_dual_cam_UI_voice as main_prog
        
        # 检查关键函数
        assert hasattr(main_prog, 'debug_publisher_thread'), "缺少 debug_publisher_thread"
        assert hasattr(main_prog, 'ui_command_receiver_thread'), "缺少 ui_command_receiver_thread"
        assert hasattr(main_prog, 'audio_player_thread'), "缺少 audio_player_thread"
        
        print("✓ debug_publisher_thread 存在")
        print("✓ ui_command_receiver_thread 存在")
        print("✓ audio_player_thread 存在")
        
        # 检查全局变量
        assert hasattr(main_prog, 'latest_audio_waveform'), "缺少 latest_audio_waveform"
        assert hasattr(main_prog, 'latest_audio_rms'), "缺少 latest_audio_rms"
        assert hasattr(main_prog, 'audio_data_lock'), "缺少 audio_data_lock"
        
        print("✓ 音频可视化全局变量存在")
        
        return True
    except Exception as e:
        print(f"❌ 函数检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_constants():
    """测试常量定义"""
    print("\n" + "="*60)
    print("3. 测试常量定义...")
    print("="*60)
    
    try:
        import triple_imu_rs485_publisher_dual_cam_UI_voice as main_prog
        
        # 检查端口常量
        assert hasattr(main_prog, 'DEFAULT_DEBUG_PORT'), "缺少 DEFAULT_DEBUG_PORT"
        assert hasattr(main_prog, 'DEFAULT_UI_COMMAND_PORT'), "缺少 DEFAULT_UI_COMMAND_PORT"
        
        print(f"✓ DEFAULT_DEBUG_PORT = {main_prog.DEFAULT_DEBUG_PORT}")
        print(f"✓ DEFAULT_UI_COMMAND_PORT = {main_prog.DEFAULT_UI_COMMAND_PORT}")
        
        return True
    except Exception as e:
        print(f"❌ 常量检查失败: {e}")
        return False


def test_widget_signals():
    """测试widget信号"""
    print("\n" + "="*60)
    print("4. 测试Widget信号...")
    print("="*60)
    
    try:
        # 需要QApplication才能创建widget
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                app = QApplication(sys.argv)
        except ImportError:
            print("⚠️  PyQt5未安装，跳过widget测试")
            return True
        
        sys.path.insert(0, '/home/bubble/桌面/WIT_RS485/pyqt5_viewer')
        from widgets.gripper_control import GripperControlWidget
        from widgets.audio_waveform import AudioWaveformWidget
        
        # 创建widget
        gripper_widget = GripperControlWidget()
        audio_widget = AudioWaveformWidget()
        
        print("✓ GripperControlWidget 创建成功")
        print("✓ AudioWaveformWidget 创建成功")
        
        # 检查信号
        assert hasattr(gripper_widget, 'gripper_command'), "缺少 gripper_command 信号"
        assert hasattr(gripper_widget, 'gripper_value_changed'), "缺少 gripper_value_changed 信号"
        
        print("✓ 夹爪控制信号存在")
        
        # 测试方法
        assert hasattr(gripper_widget, 'update_from_robot'), "缺少 update_from_robot 方法"
        assert hasattr(audio_widget, 'update_audio_data'), "缺少 update_audio_data 方法"
        
        print("✓ 更新方法存在")
        
        return True
    except Exception as e:
        print(f"❌ Widget检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_structure():
    """测试文件结构"""
    print("\n" + "="*60)
    print("5. 测试文件结构...")
    print("="*60)
    
    base_dir = '/home/bubble/桌面/WIT_RS485'
    
    files_to_check = [
        'triple_imu_rs485_publisher_dual_cam_UI_voice.py',
        'pyqt5_viewer/imu_dual_cam_viewer.py',
        'pyqt5_viewer/widgets/gripper_control.py',
        'pyqt5_viewer/widgets/audio_waveform.py',
        'pyqt5_viewer/widgets/__init__.py',
        'start_ui_system.sh',
        'test_ui_integration.md',
        'INTEGRATION_SUMMARY.md',
    ]
    
    all_exist = True
    for file_path in files_to_check:
        full_path = os.path.join(base_dir, file_path)
        if os.path.exists(full_path):
            print(f"✓ {file_path}")
        else:
            print(f"❌ 缺少: {file_path}")
            all_exist = False
    
    # 检查启动脚本权限
    script_path = os.path.join(base_dir, 'start_ui_system.sh')
    if os.path.exists(script_path):
        import stat
        st = os.stat(script_path)
        is_executable = bool(st.st_mode & stat.S_IXUSR)
        if is_executable:
            print("✓ start_ui_system.sh 可执行")
        else:
            print("⚠️  start_ui_system.sh 不可执行")
    
    return all_exist


def main():
    """主函数"""
    print("\n" + "="*60)
    print("PyQt5 UI 集成验证脚本")
    print("="*60 + "\n")
    
    results = []
    
    # 运行所有测试
    results.append(("导入测试", test_imports()))
    results.append(("函数定义测试", test_functions()))
    results.append(("常量定义测试", test_constants()))
    results.append(("Widget信号测试", test_widget_signals()))
    results.append(("文件结构测试", test_file_structure()))
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")
        all_passed = all_passed and passed
    
    print("="*60)
    
    if all_passed:
        print("\n🎉 所有测试通过！集成正确。")
        print("\n下一步：")
        print("  1. 启动主程序（启用--enable-debug）")
        print("  2. 启动UI: cd pyqt5_viewer && python imu_dual_cam_viewer.py")
        print("  或使用快速启动脚本:")
        print("  ./start_ui_system.sh")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查上述错误。")
        return 1


if __name__ == '__main__':
    sys.exit(main())
