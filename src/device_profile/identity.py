# -*- coding: utf-8 -*-
"""身份与接口角色：VID/PID、接口判定、端点预期。

换键盘时**优先改这里**：VID/PID 与接口类/子类/协议、端点方向与类型。
"""

NAME = "1EA7:0066 无线键盘"
VID = 0x1EA7
PID = 0x0066

# ============================================================
# 接口角色（按描述符识别，不写死接口号）
# ============================================================
# 复合设备由 usbccgp 为每个接口/接口集合各建一个 PDO，libusb 可能枚举成多个
# 同 VID/PID 的“设备”，顺序不保证；因此用角色而不是接口号来定位。
INTERFACE_CLASS_HID = 0x03
KEYBOARD_INTERFACE_SUBCLASS = 0x01
KEYBOARD_INTERFACE_PROTOCOL = 0x01      # boot 键盘（键盘接口 3/1/1）


def is_keyboard_interface(setting):
    """键盘接口：HID 类 3 / 子类 1 / 协议 1"""
    return (getattr(setting, 'bInterfaceClass', 0) == INTERFACE_CLASS_HID
            and getattr(setting, 'bInterfaceSubClass', 0) == KEYBOARD_INTERFACE_SUBCLASS
            and getattr(setting, 'bInterfaceProtocol', 0) == KEYBOARD_INTERFACE_PROTOCOL)


def is_consumer_interface(setting):
    """消费类接口候选：HID 类且不是 boot 键盘（具体集合由报告描述符确认）"""
    if getattr(setting, 'bInterfaceClass', 0) != INTERFACE_CLASS_HID:
        return False
    return not is_keyboard_interface(setting)


# 端点预期：键盘与消费类都用中断 IN 端点
ENDPOINT_DIRECTION = 'in'
ENDPOINT_TYPE = 'interrupt'
