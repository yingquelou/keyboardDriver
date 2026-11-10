# -*- coding: utf-8 -*-
"""当前设备（1EA7:0066 无线键盘）对 ``KeyboardDevice`` 契约的实现。

本文件只做**装配**：把契约成员接到 identity / reports / keys / policy 四个职责模块，
自身不含新的数据或算法。因此换键盘时依旧只改那四个模块的实测值；
只有当某组能力的**形状**与默认实现不同（例如消费类取舍规则、层切换键）时，
才在下面覆写对应成员。

运行时仍然是单设备、单进程：包入口只实例化本类一次。
"""

from . import identity, keys, policy, reports
from .contract import KeyboardDevice


class Wireless1EA7_0066(KeyboardDevice):
    """1EA7:0066 无线键盘（Win7 WinUSB 接管，boot 键盘接口 + 消费类集合）。"""

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

    # ---- 5. 键表与层 ----
    layers = keys.LAYERS
    layer_order = keys.LAYER_ORDER
    default_layer_name = keys.DEFAULT_LAYER_NAME
    # 0x53（数字锁定键位）：只切换映射层，不注入、不改系统 Num Lock、不重复。
    layer_toggle_hid = keys.LAYER_TOGGLE_HID
    consumer_map = keys.CONSUMER
    # C/XL/XN 是维护用的三个子集，合并成 letter / number 两层；自检会核对覆盖关系。
    keymap_subsets = {'C': keys.C, 'XL': keys.XL, 'XN': keys.XN}

    def is_layer_toggle(self, hid_code):
        return keys.is_layer_toggle(hid_code)

    def next_layer_name(self, current_name):
        return keys.next_layer_name(current_name)

    def get_vk(self, layer_name, hid_code):
        return keys.get_vk(layer_name, hid_code)

    def get_consumer_vk(self, usage):
        return keys.get_consumer_vk(usage)

    # ---- 6. 重复策略 ----
    # 锁定键不参与重复；消费类只有音量键长按补发。
    no_repeat_vks = policy.NO_REPEAT_VKS
    repeat_consumer_vks = policy.CONSUMER_REPEAT_VKS

    def repeats_key(self, vk):
        return policy.repeats_key(vk)

    def repeats_consumer(self, vk):
        return policy.repeats_consumer(vk)

    # ---- 7. 指示灯能力 ----
    # 实测：写灯返回成功但物理指示灯无反应（接口 0 只有 IN 端点），默认关闭。
    led_supported = policy.LED_SUPPORTED
    led_report_length = policy.LED_REPORT_LENGTH
    led_poll_interval_s = policy.LED_POLL_INTERVAL_S
    led_bits = policy.LED_BITS
    led_unavailable_hint = policy.LED_UNAVAILABLE_HINT

    def led_report(self, bitmap):
        return policy.led_report(bitmap)
