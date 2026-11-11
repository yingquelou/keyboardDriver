# -*- coding: utf-8 -*-
"""device_profile —— 键盘设备描述包（当前设备：1EA7:0066 无线键盘）

本项目**唯一**允许出现"该键盘专有事实"的地方，而且只记录**报告布局类事实**：
VID/PID、接口角色、键盘/消费类报告布局、指示灯输出报告格式。

usage→VK 换算和自动重复语义不在这里，放在通用模块 ``keyboard_driver/usage.py``：
设备固件自己按 Num Lock 灯位切换上报的 usage，主机只扮演通用 HID 键盘类驱动。

包内按职责拆分（换键盘时**只改这个包**，文件名/导出名保持不变）：

    contract.py   设备契约：KeyboardDevice 基类，规定"一把键盘要提供什么"
                  （五组：身份、接口角色、键盘报告、消费类报告、指示灯输出报告；
                  仅必需项为 abstract）
    device.py     当前键盘对契约的实现（只做装配，委托下面两个模块）
    identity.py   身份与接口角色：VID/PID、接口判定、端点预期   ← 换 VID/PID 改这里
    reports.py    报告布局：键盘报告、消费类 Report ID 与 usage、指示灯输出报告

本模块只做"实例化一份 + 导出"，不含实现：``PROFILE`` 是当前设备的唯一实例
（运行时单设备、单进程），下面把契约成员绑成模块级别名，保持原有导入方式。

接入指引见包内 README.md 与仓库根 README 的"接入另一把键盘"一节；
改完跑 ``python tools\\check_device_profile.py`` 做一致性自检。
"""

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

# ---------- 5. 指示灯输出报告 ----------
LED_SUPPORTED = PROFILE.led_supported
LED_REPORT_ID = PROFILE.led_report_id
LED_REPORT_LENGTH = PROFILE.led_report_length
LED_POLL_INTERVAL_S = PROFILE.led_poll_interval_s
LED_BITS = PROFILE.led_bits
led_report = PROFILE.led_report

# 公共符号清单（当日志/诊断代码用 import * 时行为不变）。
__all__ = [
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
    'LED_SUPPORTED', 'LED_REPORT_ID', 'LED_REPORT_LENGTH', 'LED_POLL_INTERVAL_S',
    'LED_BITS', 'led_report',
]
