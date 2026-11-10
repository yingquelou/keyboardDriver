# -*- coding: utf-8 -*-
"""当前设备（1EA7:0066 无线键盘）对 ``KeyboardDevice`` 契约的实现。

本文件只做**装配**：把契约成员接到 identity / reports 两个职责模块，
自身不含新的数据或算法。usage→VK 换算与自动重复语义不在这里（见 ``src/hid_usage.py``）：
固件自己按 Num Lock 灯位切换上报的 usage，主机侧按 HID Usage Tables 通用解释即可。

运行时仍然是单设备、单进程：包入口只实例化本类一次。
"""

from . import identity, reports
from .contract import KeyboardDevice


class Wireless1EA7_0066(KeyboardDevice):
    """1EA7:0066 无线键盘（WinUSB 接管，boot 键盘接口 + 消费类集合）。"""

    # ---- 1. 身份 ----
    name = identity.NAME
    vid = identity.VID
    pid = identity.PID

    # ---- 2. 接口角色 ----
    # 复合设备由 usbccgp 拆成多个同 VID/PID 的节点，按描述符角色识别，不按接口号。
    def is_keyboard_interface(self, setting):
        return identity.is_keyboard_interface(setting)

    def is_consumer_interface(self, setting):
        """HID 类且非 boot 键盘的接口为消费类候选（具体集合由描述符确认）。"""
        return identity.is_consumer_interface(setting)

    endpoint_direction = identity.ENDPOINT_DIRECTION
    endpoint_type = identity.ENDPOINT_TYPE

    # ---- 3. 键盘报告 ----
    # 实测 8 字节 boot 报告，无 Report ID：raw[0] 修饰键位图，raw[2:8] 6 个键码槽。
    key_report_length = reports.KEY_REPORT_LENGTH
    modifier_byte_index = reports.MODIFIER_BYTE_INDEX
    key_slot_start = reports.KEY_SLOT_START
    key_slot_end = reports.KEY_SLOT_END
    key_report_has_id = reports.KEY_REPORT_HAS_ID

    def parse_key_report(self, raw):
        """长度不足返回 ``(0, None)``；空槽（0）不进入键码列表。"""
        return reports.parse_key_report(raw)

    def key_report_read_size(self, max_packet_size):
        return reports.key_report_read_size(max_packet_size)

    # ---- 4. 消费类报告 ----
    # MI_01 消费类集合：Report ID 1 + 16 位小端 usage；描述符里混有 8 位 AC Pan，
    # 因此取舍规则覆写为"优先取 Report Size >= 16 位的输入项"。
    consumer_usage_page = reports.CONSUMER_USAGE_PAGE
    consumer_report_id = reports.CONSUMER_REPORT_ID
    consumer_report_id_size = reports.CONSUMER_REPORT_ID_SIZE
    consumer_usage_size = reports.CONSUMER_USAGE_SIZE
    consumer_usage_bits = reports.CONSUMER_USAGE_BITS
    consumer_usage_byte_order = reports.CONSUMER_USAGE_BYTE_ORDER

    def choose_consumer_report(self, items):
        return reports.choose_consumer_report(items)

    def consumer_report_read_size(self, max_packet_size):
        return reports.consumer_report_read_size(max_packet_size)

    def parse_consumer_report(self, raw):
        """首字节非 Report ID 1 的报文（鼠标/厂商报文）一律丢弃。"""
        return reports.parse_consumer_report(raw)

    # ---- 5. 指示灯输出报告 ----
    # 实测（2026-11-10，WinUSB 接管）：Output 主项为 5 位 LED + 3 位填充 = 1 字节，
    # 无 Report ID。写 Num Lock 位后设备立即把字母区改报小键盘 usage（J: 0x0D → 0x59），
    # 写回 0 后恢复，因此灯位回写是**功能必需**，不再是可选的装饰。
    led_supported = True
    led_report_id = reports.LED_REPORT_ID
    led_report_length = reports.LED_REPORT_LENGTH
    led_poll_interval_s = reports.LED_POLL_INTERVAL_S
    led_bits = reports.LED_BITS
