# -*- coding: utf-8 -*-
"""device_profile —— 键盘设备描述包（当前设备：1EA7:0066 无线键盘）

本项目**唯一**允许出现“该键盘专有常量/分支”的地方：VID/PID、接口角色、报告布局、
消费类集合、HID→VK 映射表、层切换键与策略、自动重复策略、指示灯能力。

通用实现（keyboard.py / keyboard_utils.py / tools）只通过 ``device_profile.X``
或 ``from device_profile import X`` 取值，不再内嵌任何本键盘的专有常量。

包内按职责拆分（换键盘时**只改这个包**，文件名/导出名保持不变）：

    identity.py   身份与接口角色：VID/PID、接口判定、端点预期   ← 换 VID/PID 改这里
    reports.py    报告解析：键盘报告布局、消费类 Report ID 与 usage、读取长度
    keys.py       键表与层：C/XL/XN/CONSUMER 映射表、层切换键与切层策略
                  （体量大、变动频繁，改键位映射主要改这一个文件）
    policy.py     策略：自动重复规则、指示灯能力
    _win32.py     win32 常量入口与 VK 补全（私有，不对外）

本模块自身只做导出，不含实现。接入指引见包内 README.md 与仓库根 README 的
“接入另一把键盘”一节。
"""

from ._win32 import win32con
from .identity import (
    NAME, VID, PID,
    INTERFACE_CLASS_HID,
    KEYBOARD_INTERFACE_SUBCLASS,
    KEYBOARD_INTERFACE_PROTOCOL,
    is_keyboard_interface, is_consumer_interface,
    ENDPOINT_DIRECTION, ENDPOINT_TYPE,
)
from .reports import (
    KEY_REPORT_LENGTH, MODIFIER_BYTE_INDEX,
    KEY_SLOT_START, KEY_SLOT_END, KEY_REPORT_HAS_ID,
    parse_key_report, key_report_read_size,
    CONSUMER_USAGE_PAGE,
    CONSUMER_REPORT_ID, CONSUMER_REPORT_ID_SIZE,
    CONSUMER_USAGE_SIZE, CONSUMER_USAGE_BITS, CONSUMER_USAGE_BYTE_ORDER,
    choose_consumer_report, consumer_report_read_size, parse_consumer_report,
)
from .keys import (
    LAYER_TOGGLE_HID, LAYER_ORDER, DEFAULT_LAYER_NAME,
    is_layer_toggle, next_layer_name, get_vk,
    C, XL, XN, LAYERS, CONSUMER, get_consumer_vk,
)
from .policy import (
    NO_REPEAT_VKS, CONSUMER_REPEAT_VKS, repeats_key, repeats_consumer,
    LED_SUPPORTED, LED_REPORT_LENGTH, LED_POLL_INTERVAL_S,
    LED_BITS, LED_UNAVAILABLE_HINT, led_report,
)

# 公共符号清单：与拆分前的单文件模块保持一致（当日志/诊断代码用 import * 时行为不变）。
# win32con 也在其中，因为旧单文件版本会把导入的 win32con 一并暴露。
__all__ = [
    'win32con',
    'NAME', 'VID', 'PID',
    'INTERFACE_CLASS_HID', 'KEYBOARD_INTERFACE_SUBCLASS', 'KEYBOARD_INTERFACE_PROTOCOL',
    'is_keyboard_interface', 'is_consumer_interface',
    'ENDPOINT_DIRECTION', 'ENDPOINT_TYPE',
    'KEY_REPORT_LENGTH', 'MODIFIER_BYTE_INDEX',
    'KEY_SLOT_START', 'KEY_SLOT_END', 'KEY_REPORT_HAS_ID',
    'parse_key_report', 'key_report_read_size',
    'CONSUMER_USAGE_PAGE',
    'CONSUMER_REPORT_ID', 'CONSUMER_REPORT_ID_SIZE',
    'CONSUMER_USAGE_SIZE', 'CONSUMER_USAGE_BITS', 'CONSUMER_USAGE_BYTE_ORDER',
    'choose_consumer_report', 'consumer_report_read_size', 'parse_consumer_report',
    'LAYER_TOGGLE_HID', 'LAYER_ORDER', 'DEFAULT_LAYER_NAME',
    'is_layer_toggle', 'next_layer_name', 'get_vk',
    'C', 'XL', 'XN', 'LAYERS', 'CONSUMER', 'get_consumer_vk',
    'NO_REPEAT_VKS', 'CONSUMER_REPEAT_VKS', 'repeats_key', 'repeats_consumer',
    'LED_SUPPORTED', 'LED_REPORT_LENGTH', 'LED_POLL_INTERVAL_S',
    'LED_BITS', 'LED_UNAVAILABLE_HINT', 'led_report',
]
