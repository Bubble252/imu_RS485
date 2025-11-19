#!/usr/bin/env python3
"""
检查音频设备支持的采样率
"""

import sounddevice as sd

print("=" * 70)
print("音频设备详细信息")
print("=" * 70)
print()

devices = sd.query_devices()

for i, dev in enumerate(devices):
    if dev['max_input_channels'] > 0:
        print(f"设备 [{i}]: {dev['name']}")
        print(f"  输入声道: {dev['max_input_channels']}")
        print(f"  默认采样率: {dev['default_samplerate']} Hz")
        
        # 测试常见采样率
        supported_rates = []
        test_rates = [8000, 11025, 16000, 22050, 32000, 44100, 48000]
        
        for rate in test_rates:
            try:
                sd.check_input_settings(
                    device=i,
                    channels=1,
                    samplerate=rate
                )
                supported_rates.append(rate)
            except:
                pass
        
        print(f"  支持的采样率: {supported_rates}")
        print()

print("=" * 70)
print()

# 显示默认设备
default_input = sd.query_devices(kind='input')
print(f"默认输入设备: {default_input['name']}")
print(f"  默认采样率: {default_input['default_samplerate']} Hz")
print(f"  输入声道: {default_input['max_input_channels']}")
