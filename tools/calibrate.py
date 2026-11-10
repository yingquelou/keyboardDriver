# -*- coding: utf-8 -*-
import os
import sys
import time

# 本文件位于 tools/：把 src/ 加入模块搜索路径，避免依赖当前工作目录。
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import usb.core
from keyboard_utils import (
    find_device, configure_device, read_report, parse_keyboard_report,
    get_vk_name, get_vk
)

def calibrate_mode(dev, ep):
    prev_modifier = 0
    prev_keys = []
    print("\n=== 键盘校准模式（信息查看） ===")
    print("按下按键，程序会显示其 HID 键码和按 HID Usage Tables 换出的虚拟键码名称。")
    print("注意：设备在 Num Lock 灯位为 1 时会把字母区改报成小键盘 usage，")
    print("      所以同一个物理键在两种锁定状态下会显示不同的键码，这是正常现象。")
    print("按 Ctrl+C 退出校准模式。\n")

    try:
        while True:
            raw = read_report(dev, ep)
            modifier, current_keys = parse_keyboard_report(raw)
            # 修饰键变化单独显示（原生驱动里修饰键与普通键是分开更新的）
            if current_keys is not None and modifier != prev_modifier:
                changed = modifier ^ prev_modifier
                for bit, name in ((0x01, '左Ctrl'), (0x02, '左Shift'), (0x04, '左Alt'),
                                  (0x08, '左Win'), (0x10, '右Ctrl'), (0x20, '右Shift'),
                                  (0x40, '右Alt'), (0x80, '右Win')):
                    if changed & bit:
                        state = "按下" if modifier & bit else "抬起"
                        print(f"修饰键 {name} {state}")
                prev_modifier = modifier
            if current_keys is not None:
                new_keys = [k for k in current_keys if k not in prev_keys]
                if new_keys:
                    hid_code = new_keys[0]
                    vk = get_vk(hid_code)  # 通用 HID Usage Tables 映射
                    if vk is not None:
                        name = get_vk_name(vk)
                        print(f"键码 0x{hid_code:02X} -> {name}")
                    else:
                        print(f"键码 0x{hid_code:02X} -> 未映射")
                prev_keys = current_keys
            time.sleep(0.001)
    except KeyboardInterrupt:
        print("\n校准模式已退出。")
    except usb.core.USBError as e:
        # 读取出错（例如设备拔出）不应表现为崩溃
        print(f"\n读取中断: {e}")

def main():
    print("启动校准模式...")
    print("正在查找设备...")
    try:
        dev = find_device()
        try:
            import usb.util
            product = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "未知产品"
        except:
            product = "未知产品"
        print(f"找到设备: {product}")
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)

    try:
        ep = configure_device(dev)
        print(f"中断端点: 0x{ep.bEndpointAddress:02X}, 包大小: {ep.wMaxPacketSize}")
    except Exception as e:
        print(f"配置失败: {e}")
        sys.exit(1)

    calibrate_mode(dev, ep)

if __name__ == "__main__":
    main()
