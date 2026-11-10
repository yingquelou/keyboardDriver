# -*- coding: utf-8 -*-
"""device_profile —— 键盘设备描述包（当前设备：1EA7:0066 无线键盘）

本项目**唯一**允许出现"该键盘专有常量/分支"的地方：VID/PID、接口角色、报告布局、
消费类集合、HID→VK 映射表、层切换键与策略、自动重复策略、指示灯能力。

通用实现（keyboard.py / keyboard_utils.py / tools）只通过 ``device_profile.X``
或 ``from device_profile import X`` 取值，不再内嵌任何本键盘的专有常量。

包内按职责拆分（换键盘时**只改这个包**，文件名/导出名保持不变）：

    contract.py   设备契约：KeyboardDevice 基类，规定"一把键盘要提供什么"
                  （七组：身份、接口角色、键盘报告、消费类报告、键表与层、
                  重复策略、指示灯能力；仅必需项为 abstract）
    device.py     当前键盘对契约的实现（只做装配，委托下面四个模块）
    identity.py   身份与接口角色：VID/PID、接口判定、端点预期   ← 换 VID/PID 改这里
    reports.py    报告解析：键盘报告布局、消费类 Report ID 与 usage、读取长度
    keys.py       键表与层：C/XL/XN/CONSUMER 映射表、层切换键与切层策略
                  （体量大、变动频繁，改键位映射主要改这一个文件）
    policy.py     策略：自动重复规则、指示灯能力
    _win32.py     win32 常量入口与 VK 补全（私有，不对外）

本模块只做"实例化一份 + 导出"，不含实现：``PROFILE`` 是当前设备的唯一实例
（运行时单设备、单进程），下面把契约成员绑成模块级别名，保持原有导入方式。

接入指引见包内 README.md 与仓库根 README 的"接入另一把键盘"一节；
改完跑 ``python tools\\check_device_profile.py`` 做一致性自检。
"""

from ._win32 import win32con
from .contract import KeyboardDevice
from .device import Wireless1EA7_0066

# 当前设备实例：包内唯一，运行时不再创建第二份。
PROFILE = Wireless1EA7_0066()

# ---------- 1. 身份 ----------
NAME = PROFILE.name
VID = PROFILE.vid
PID = PROFILE.pid

# ---------- 2. 接口角色 ----------
INTERFACE_CLASS_HID = PROFILE.interface_class_hid
KEYBOARD_INTERFACE_SUBCLASS = PROFILE.keyboard_interface_subclass
KEYBOARD_INTERFACE_PROTOCOL = PROFILE.keyboard_interface_protocol
is_keyboard_interface = PROFILE.is_keyboard_interface
is_consumer_interface = PROFILE.is_consumer_interface
ENDPOINT_DIRECTION = PROFILE.endpoint_direction
ENDPOINT_TYPE = PROFILE.endpoint_type

# ---------- 3. 键盘报告 ----------
KEY_REPORT_LENGTH = PROFILE.key_report_length
MODIFIER_BYTE_INDEX = PROFILE.modifier_byte_index
KEY_SLOT_START = PROFILE.key_slot_start
KEY_SLOT_END = PROFILE.key_slot_end
KEY_REPORT_HAS_ID = PROFILE.key_report_has_id
parse_key_report = PROFILE.parse_key_report
key_report_read_size = PROFILE.key_report_read_size

# ---------- 4. 消费类报告 ----------
CONSUMER_USAGE_PAGE = PROFILE.consumer_usage_page
CONSUMER_REPORT_ID = PROFILE.consumer_report_id
CONSUMER_REPORT_ID_SIZE = PROFILE.consumer_report_id_size
CONSUMER_USAGE_SIZE = PROFILE.consumer_usage_size
CONSUMER_USAGE_BITS = PROFILE.consumer_usage_bits
CONSUMER_USAGE_BYTE_ORDER = PROFILE.consumer_usage_byte_order
choose_consumer_report = PROFILE.choose_consumer_report
consumer_report_read_size = PROFILE.consumer_report_read_size
parse_consumer_report = PROFILE.parse_consumer_report

# ---------- 5. 键表与层 ----------
LAYERS = PROFILE.layers
LAYER_ORDER = PROFILE.layer_order
DEFAULT_LAYER_NAME = PROFILE.default_layer_name
LAYER_TOGGLE_HID = PROFILE.layer_toggle_hid
CONSUMER = PROFILE.consumer_map
is_layer_toggle = PROFILE.is_layer_toggle
next_layer_name = PROFILE.next_layer_name
get_vk = PROFILE.get_vk
get_consumer_vk = PROFILE.get_consumer_vk

# C / XL / XN 是维护用的三个键表子集（历史导出名）。契约只要求 keymap_subsets
# 中的子表能被层表覆盖，未提供子表的设备这里退化为空表。
_keymap_subsets = PROFILE.keymap_subsets
C = _keymap_subsets.get('C', {})
XL = _keymap_subsets.get('XL', {})
XN = _keymap_subsets.get('XN', {})
del _keymap_subsets

# ---------- 6. 重复策略 ----------
NO_REPEAT_VKS = PROFILE.no_repeat_vks
CONSUMER_REPEAT_VKS = PROFILE.repeat_consumer_vks
repeats_key = PROFILE.repeats_key
repeats_consumer = PROFILE.repeats_consumer

# ---------- 7. 指示灯能力 ----------
LED_SUPPORTED = PROFILE.led_supported
LED_REPORT_LENGTH = PROFILE.led_report_length
LED_POLL_INTERVAL_S = PROFILE.led_poll_interval_s
LED_BITS = PROFILE.led_bits
LED_UNAVAILABLE_HINT = PROFILE.led_unavailable_hint
led_report = PROFILE.led_report

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
