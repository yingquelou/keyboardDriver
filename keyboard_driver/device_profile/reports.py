# -*- coding: utf-8 -*-
"""报告解析：键盘输入报告布局、消费类 Report ID 与 usage、单次读取长度。

换键盘时改这里：报告长度、修饰键位置、键槽区间、消费类 Report ID 字节序，
以及（有取舍时）``choose_consumer_report``。
"""

from .. import win32_compat as win32con

# ============================================================
# 键盘输入报告布局
# ============================================================
# 实测（Win11 + WinUSB 接管）：键盘接口（MI_00）使用 8 字节 boot 报告，无 Report ID：
#   raw[0]      8 位修饰键位图（bit0..7 = 左Ctrl/左Shift/左Alt/左Win/右Ctrl/右Shift/右Alt/右Win）
#   raw[1]      保留字节
#   raw[2:8]    6 个键码槽（HID usage，0 表示空槽）
KEY_REPORT_LENGTH = 8
MODIFIER_BYTE_INDEX = 0
KEY_SLOT_START = 2
KEY_SLOT_END = 8
KEY_REPORT_HAS_ID = False               # boot 协议：报告首字节就是修饰键位图


def parse_key_report(raw):
    """解析键盘报告，返回 (修饰键字节, 键列表)；长度不足时返回 (0, None)"""
    if raw is None:
        return 0, None
    data = bytes(raw)
    if len(data) < KEY_REPORT_LENGTH:
        return 0, None
    return data[MODIFIER_BYTE_INDEX], [b for b in data[KEY_SLOT_START:KEY_SLOT_END] if b != 0]


def key_report_read_size(max_packet_size):
    """单次读取长度：至少覆盖完整报告，且不小于端点包长"""
    return max(KEY_REPORT_LENGTH, max_packet_size)


# ============================================================
# 消费类报告（音量/多媒体/浏览器键）
# ============================================================
# 由 MI_01 的消费类集合上报：首字节 Report ID（1 = 消费类集合），
# 其后是 16 位 usage（小端）。格式来自 Win11 实际抓包。
CONSUMER_USAGE_PAGE = 0x0C              # 消费类集合所在的 HID Usage Page
CONSUMER_REPORT_ID = 1
CONSUMER_REPORT_ID_SIZE = 1
CONSUMER_USAGE_SIZE = 2
CONSUMER_USAGE_BITS = 16
CONSUMER_USAGE_BYTE_ORDER = 'little'


def choose_consumer_report(items):
    """从报告描述符的 Input 主项里选出消费类输入报告。

    items 为 [(usage_page, report_id, report_size_bits), ...]（由通用 KBD 描述符
    解析器产出）。这里负责设备侧的取舍策略：

    同一个描述符里可能有其它集合借用 Usage Page 0x0C（例如鼠标的 AC Pan，8 位），
    而消费类 usage 本身是 16 位的；实测本键盘的鼠标集合就夹在中间，
    因此优先取 Report Size >= 16 位的输入项，避免误认成 Report ID 2。

    返回 (Report ID, usage 字节数)；没有消费类输入项时返回 None。
    """
    fallback = None
    for usage_page, report_id, report_size in items:
        if usage_page != CONSUMER_USAGE_PAGE:
            continue
        if report_size >= CONSUMER_USAGE_BITS:
            return report_id, CONSUMER_USAGE_SIZE
        if fallback is None:
            fallback = (report_id, max(1, min(CONSUMER_USAGE_SIZE, report_size // 8)))
    return fallback


def consumer_report_read_size(max_packet_size):
    """单次读取长度：至少覆盖 Report ID + usage，且不小于端点包长"""
    return max(CONSUMER_REPORT_ID_SIZE + CONSUMER_USAGE_SIZE, max_packet_size)


def parse_consumer_report(raw):
    """解析消费类报告：返回 usage；不是消费类报告时返回 None。

    混流端点（同一个接口既报鼠标又报消费类）用首字节 Report ID 过滤，
    本键盘鼠标集合为 Report ID 2，会在这里被丢掉。
    """
    if raw is None:
        return None
    data = bytes(raw)
    if len(data) < CONSUMER_REPORT_ID_SIZE + CONSUMER_USAGE_SIZE:
        return None
    if data[0] != CONSUMER_REPORT_ID:
        return None
    start = CONSUMER_REPORT_ID_SIZE
    return int.from_bytes(data[start:start + CONSUMER_USAGE_SIZE],
                          CONSUMER_USAGE_BYTE_ORDER)


# ============================================================
# 指示灯输出报告（LED Page 0x08）
# ============================================================
# 键盘接口的输出报告来自报告描述符的 Output 主项：
#   05 08（Usage Page LED）19 01 29 05 15 00 25 01 95 05 75 01 91 02
#   → 5 个 1 位输出字段（Num/Caps/Scroll/Compose/Kana），再 3 位常量填充 = 1 字节，无 Report ID。
LED_REPORT_ID = 0
LED_REPORT_LENGTH = 1
# (位, 对应锁定状态的 VK)；位序按 HID 输出报告定义
LED_BITS = (
    (0x01, win32con.VK_NUMLOCK),
    (0x02, win32con.VK_CAPITAL),
    (0x04, win32con.VK_SCROLL),
)
# 锁定状态轮询间隔：只读系统状态，状态不变就不写 USB；10ms 让切层延迟接近原生。
LED_POLL_INTERVAL_S = 0.01
