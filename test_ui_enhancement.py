#!/usr/bin/env python3
"""
UI增强功能快速测试脚本
测试新增的UI元素是否正常工作
"""

import numpy as np
import cv2
import time

# 模拟全局变量
gripper_value = 0.5
latest_audio_waveform = np.random.randint(-16000, 16000, size=256, dtype=np.int16)
latest_audio_rms = 0.3
AUDIO_ENABLED = True

class MockLock:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass

gripper_lock = MockLock()
audio_waveform_lock = MockLock()

def draw_enhanced_ui(frame, camera_name, frame_count, latency):
    """
    在视频帧上绘制增强UI元素：
    1. 基础信息（摄像头名称、帧号、延迟）
    2. 夹爪状态条
    3. 音频波形和音量指示器
    4. 键盘提示
    """
    global gripper_value, latest_audio_waveform, latest_audio_rms
    
    h, w = frame.shape[:2]
    
    # ============ 1. 基础信息 ============
    cv2.putText(frame, f"{camera_name} - Frame: {frame_count}", 
               (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    
    if latency > 0:
        cv2.putText(frame, f"Latency: {latency:.1f}ms", 
                   (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    
    # ============ 2. 夹爪状态条 ============
    gripper_bar_y = h - 80
    gripper_bar_height = 30
    gripper_bar_width = w - 40
    gripper_bar_x = 20
    
    # 背景框
    cv2.rectangle(frame, (gripper_bar_x, gripper_bar_y), 
                 (gripper_bar_x + gripper_bar_width, gripper_bar_y + gripper_bar_height),
                 (50, 50, 50), -1)
    
    # 夹爪进度条
    with gripper_lock:
        gripper_fill = int(gripper_bar_width * gripper_value)
        if gripper_fill > 0:
            if gripper_value < 0.3:
                color = (0, 0, 255)
            elif gripper_value < 0.7:
                color = (0, 255, 255)
            else:
                color = (0, 255, 0)
            
            cv2.rectangle(frame, (gripper_bar_x, gripper_bar_y),
                         (gripper_bar_x + gripper_fill, gripper_bar_y + gripper_bar_height),
                         color, -1)
        
        gripper_text = f"Gripper: {gripper_value:.2f} (1=Open, 2=Close)"
        cv2.putText(frame, gripper_text,
                   (gripper_bar_x + 5, gripper_bar_y - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    cv2.rectangle(frame, (gripper_bar_x, gripper_bar_y), 
                 (gripper_bar_x + gripper_bar_width, gripper_bar_y + gripper_bar_height),
                 (200, 200, 200), 2)
    
    # ============ 3. 音频波形和音量 ============
    if AUDIO_ENABLED:
        audio_panel_y = h - 40
        audio_panel_height = 35
        audio_panel_x = 20
        audio_panel_width = w - 40
        
        cv2.rectangle(frame, (audio_panel_x, audio_panel_y),
                     (audio_panel_x + audio_panel_width, audio_panel_y + audio_panel_height),
                     (30, 30, 30), -1)
        
        with audio_waveform_lock:
            if latest_audio_waveform is not None and len(latest_audio_waveform) > 0:
                waveform_width = min(audio_panel_width - 100, 200)
                waveform_x = audio_panel_x + 5
                waveform_center_y = audio_panel_y + audio_panel_height // 2
                
                waveform_normalized = latest_audio_waveform.astype(np.float32) / 32767.0
                waveform_pixels = (waveform_normalized * 15).astype(np.int32)
                
                step = max(1, len(waveform_pixels) // waveform_width)
                waveform_display = waveform_pixels[::step][:waveform_width]
                
                points = []
                for i, val in enumerate(waveform_display):
                    x = waveform_x + i
                    y = waveform_center_y - val
                    points.append((x, y))
                
                if len(points) > 1:
                    points_array = np.array(points, np.int32)
                    cv2.polylines(frame, [points_array], False, (0, 255, 0), 1)
                
                cv2.line(frame, (waveform_x, waveform_center_y),
                        (waveform_x + waveform_width, waveform_center_y),
                        (100, 100, 100), 1)
            
            # VU Meter
            volume_bar_x = audio_panel_x + audio_panel_width - 90
            volume_bar_width = 80
            volume_bar_height = 20
            volume_bar_y = audio_panel_y + 8
            
            cv2.rectangle(frame, (volume_bar_x, volume_bar_y),
                         (volume_bar_x + volume_bar_width, volume_bar_y + volume_bar_height),
                         (50, 50, 50), -1)
            
            volume_fill = int(volume_bar_width * min(latest_audio_rms * 2, 1.0))
            if volume_fill > 0:
                if latest_audio_rms < 0.3:
                    vol_color = (0, 255, 0)
                elif latest_audio_rms < 0.7:
                    vol_color = (0, 255, 255)
                else:
                    vol_color = (0, 0, 255)
                
                cv2.rectangle(frame, (volume_bar_x, volume_bar_y),
                             (volume_bar_x + volume_fill, volume_bar_y + volume_bar_height),
                             vol_color, -1)
            
            cv2.rectangle(frame, (volume_bar_x, volume_bar_y),
                         (volume_bar_x + volume_bar_width, volume_bar_y + volume_bar_height),
                         (200, 200, 200), 1)
            
            cv2.putText(frame, "Audio",
                       (audio_panel_x + 5, audio_panel_y + 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
        
        cv2.rectangle(frame, (audio_panel_x, audio_panel_y),
                     (audio_panel_x + audio_panel_width, audio_panel_y + audio_panel_height),
                     (100, 100, 100), 1)
    
    # ============ 4. 键盘提示 ============
    hint_y = h - 100
    cv2.putText(frame, "Press '1' to Open | '2' to Close | 'q' to Quit",
               (10, hint_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    
    return frame


def main():
    print("UI增强功能测试")
    print("=" * 50)
    print("测试内容：")
    print("  1. 夹爪状态条（颜色变化）")
    print("  2. 音频波形显示")
    print("  3. 音量表（VU Meter）")
    print("  4. 键盘控制（按 '1' '2' 'q'）")
    print("=" * 50)
    print()
    
    # 创建测试画面
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (40, 40, 40)  # 深灰背景
    
    # 添加一些测试内容
    cv2.putText(frame, "TEST VIDEO FEED", (200, 240), 
               cv2.FONT_HERSHEY_SIMPLEX, 1.5, (100, 100, 100), 3)
    
    frame_count = 0
    start_time = time.time()
    
    print("窗口已打开，测试功能：")
    print("  - 夹爪会自动从0.0变化到1.0（观察颜色变化）")
    print("  - 音频波形会随机生成")
    print("  - 按 '1' '2' 可以手动控制夹爪")
    print("  - 按 'q' 退出")
    print()
    
    while True:
        frame_count += 1
        elapsed = time.time() - start_time
        
        # 模拟夹爪自动变化（0.0 -> 1.0 -> 0.0）
        global gripper_value, latest_audio_waveform, latest_audio_rms
        gripper_value = (np.sin(elapsed) + 1) / 2  # 0.0 - 1.0
        
        # 模拟音频数据
        latest_audio_waveform = np.random.randint(-16000, 16000, size=256, dtype=np.int16)
        latest_audio_waveform = (np.sin(np.linspace(0, 10, 256)) * 16000).astype(np.int16)
        latest_audio_rms = (np.sin(elapsed * 2) + 1) / 4 + 0.1  # 0.1 - 0.6
        
        # 绘制UI
        test_frame = frame.copy()
        test_frame = draw_enhanced_ui(test_frame, "Test Camera", frame_count, 127.5)
        
        cv2.imshow('UI Enhancement Test', test_frame)
        
        # 键盘处理
        key = cv2.waitKey(30) & 0xFF
        if key == ord('q'):
            print("\n退出测试")
            break
        elif key == ord('1'):
            gripper_value = min(1.0, gripper_value + 0.05)
            print(f"夹爪打开: {gripper_value:.2f}")
        elif key == ord('2'):
            gripper_value = max(0.0, gripper_value - 0.05)
            print(f"夹爪闭合: {gripper_value:.2f}")
        
        # 每5秒打印一次状态
        if frame_count % 150 == 0:
            print(f"[{frame_count}] 夹爪: {gripper_value:.2f}, 音量: {latest_audio_rms:.2f}")
    
    cv2.destroyAllWindows()
    print("测试完成！")


if __name__ == "__main__":
    main()
