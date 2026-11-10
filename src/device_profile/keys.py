# -*- coding: utf-8 -*-
"""键表与层：HID→VK 映射表、层切换键与切层策略。

**体量大、变动频繁，单独成文件**。换键盘时主要改这里的 ``C`` / ``XL`` / ``XN`` /
``CONSUMER`` 四张表；层名与轮转顺序见 ``LAYER_ORDER``。
"""

from ._win32 import win32con

# ============================================================
# 层切换键与层顺序
# ============================================================
# 层切换键：实测 MI_00 原始报告上报 HID usage 0x53（数字锁定键位），与原始驱动一致。
# 该键只负责切换映射层，不注入系统（不触发 Num Lock 锁定状态），也不参与自动重复。
LAYER_TOGGLE_HID = 0x53
LAYER_ORDER = ('letter', 'number')
DEFAULT_LAYER_NAME = 'letter'


def is_layer_toggle(hid_code):
    """是否为本设备的层切换键（不注入、不重复）"""
    return hid_code == LAYER_TOGGLE_HID


def next_layer_name(current_name):
    """按 LAYER_ORDER 轮转下一层；只有一层时返回原名（等于不切换）"""
    try:
        index = LAYER_ORDER.index(current_name)
    except ValueError:
        return DEFAULT_LAYER_NAME
    return LAYER_ORDER[(index + 1) % len(LAYER_ORDER)]


def get_vk(layer_name, hid_code):
    """按层取虚拟键码，未映射返回 None"""
    layer = LAYERS.get(layer_name)
    if layer is None:
        return None
    return layer.get(hid_code)


def get_consumer_vk(usage):
    """根据消费类 usage 获取虚拟键码，未映射时返回 None"""
    return CONSUMER.get(usage)


# ---------- 用户维护的三个独立子集（请按实际键盘填写） ----------

# ---- C：字母层与数字层共用的映射（交集） ----
C = {
    # 字母（字母层和数字层都输出字母）
    0x04: ord('A'), 0x05: ord('B'), 0x06: ord('C'), 0x07: ord('D'),
    0x08: ord('E'), 0x09: ord('F'), 0x0A: ord('G'), 0x0B: ord('H'),

                    0x11: ord('N'),
    0x14: ord('Q'), 0x15: ord('R'), 0x16: ord('S'), 0x17: ord('T'),
    0x19: ord('V'), 0x1A: ord('W'), 0x1B: ord('X'),
    0x1C: ord('Y'), 0x1D: ord('Z'),

    # 数字（字母层和数字层都输出数字）
    0x1E: ord('1'), 0x1F: ord('2'), 0x20: ord('3'), 0x21: ord('4'),
    0x22: ord('5'), 0x23: ord('6'),


    # 功能键（两层共用）
    0x28: win32con.VK_RETURN,   0x29: win32con.VK_ESCAPE,
    0x2A: win32con.VK_BACK,     0x2B: win32con.VK_TAB,
    0x2C: win32con.VK_SPACE,    0x2D: win32con.VK_OEM_MINUS,
    0x2E: win32con.VK_OEM_PLUS, 0x2F: win32con.VK_OEM_4,
    0x30: win32con.VK_OEM_6,    0x31: win32con.VK_OEM_5,

    0x34: win32con.VK_OEM_7,    0x35: win32con.VK_OEM_3,
    0x36: win32con.VK_OEM_COMMA,

                                0x39: win32con.VK_CAPITAL,
    0x3A: win32con.VK_F1,       0x3B: win32con.VK_F2,
    0x3C: win32con.VK_F3,       0x3D: win32con.VK_F4,
    0x3E: win32con.VK_F5,       0x3F: win32con.VK_F6,
    0x40: win32con.VK_F7,       0x41: win32con.VK_F8,
    0x42: win32con.VK_F9,       0x43: win32con.VK_F10,
    0x44: win32con.VK_F11,      0x45: win32con.VK_F12,
    0x46: win32con.VK_SNAPSHOT,

    # 编辑键（两层共用，若需要不同可放在 XL/XN）
    0x47: win32con.VK_SCROLL,   0x4C: win32con.VK_DELETE,
    # 0x53（数字锁定键位）是层切换键，由 LAYER_TOGGLE_HID 截获，
    # 不注入系统、不切换 Num Lock 状态，因此这里不能映射，否则会与层切换冲突。

    # 切换键（两层都忽略）
    0x58: win32con.VK_RETURN,

    # 方向键
    0x50: win32con.VK_LEFT,         0x4A: win32con.VK_HOME,
    0x4F: win32con.VK_RIGHT,        0x4D: win32con.VK_END,
    0x52: win32con.VK_UP,           0x4B: win32con.VK_PRIOR,
    0x51: win32con.VK_DOWN,         0x4E: win32con.VK_NEXT
}

# ---- XL：仅属于字母层的映射（字母层独有） ----
XL = {
    # 期望格式:一行表示同一个实体键
    0x0D: ord('J'),                 0x59: win32con.VK_NUMPAD1,
    0x0E: ord('K'),                 0x5a: win32con.VK_NUMPAD2,
    0x0F: ord('L'),                 0x5b: win32con.VK_NUMPAD3,
    0x18: ord('U'),                 0x5c: win32con.VK_NUMPAD4,
    0x0C: ord('I'),                 0x5d: win32con.VK_NUMPAD5,
    0x12: ord('O'),                 0x5e: win32con.VK_NUMPAD6,
    0x24: ord('7'),                 0x5f: win32con.VK_NUMPAD7,
    0x25: ord('8'),                 0x60: win32con.VK_NUMPAD8,
    0x26: ord('9'),                 0x61: win32con.VK_NUMPAD9,
    0x10: ord('M'),                 0x62: win32con.VK_NUMPAD0,
    0x27: ord('0'),                 0x55: win32con.VK_MULTIPLY,
    0x13: ord('P'),                 0x56: win32con.VK_SUBTRACT,
    0x33: win32con.VK_OEM_1,        0x57: win32con.VK_ADD,
    0x38: win32con.VK_OEM_2,        0x54: win32con.VK_DIVIDE,
    0x37: win32con.VK_OEM_PERIOD,   0x63: win32con.VK_DECIMAL
}

# ---- XN：仅属于数字层的映射（数字层独有） ----
XN = {
    0x0D: win32con.VK_NUMPAD1,      0x59: ord('J'),
    0x0E: win32con.VK_NUMPAD2,      0x5a: ord('K'),
    0x0F: win32con.VK_NUMPAD3,      0x5b: ord('L'),
    0x18: win32con.VK_NUMPAD4,      0x5c: ord('U'),
    0x0C: win32con.VK_NUMPAD5,      0x5d: ord('I'),
    0x12: win32con.VK_NUMPAD6,      0x5e: ord('O'),
    0x24: win32con.VK_NUMPAD7,      0x5f: ord('7'),
    0x25: win32con.VK_NUMPAD8,      0x60: ord('8'),
    0x26: win32con.VK_NUMPAD9,      0x61: ord('9'),
    0x10: win32con.VK_NUMPAD0,      0x62: ord('M'),
    0x27: win32con.VK_MULTIPLY,     0x55: ord('0'),
    0x13: win32con.VK_SUBTRACT,     0x56: ord('P'),
    0x33: win32con.VK_ADD,          0x57: win32con.VK_OEM_1,
    0x38: win32con.VK_DIVIDE,       0x54: win32con.VK_OEM_2,
    0x37: win32con.VK_DECIMAL,      0x63: win32con.VK_OEM_PERIOD
}

# 合并 C、XL 得到字母层；合并 C、XN 得到数字层
LAYERS = {
    'letter': {**C, **XL},
    'number': {**C, **XN},
}

# ---------- 消费类（Consumer Page）按键映射 ----------
# 该键盘的音量/多媒体/浏览器键不在键盘接口上，而是由 MI_01 的消费类集合
# 上报（Report ID 1，16 位 usage），这里按 Windows 原生驱动的映射关系补充。
CONSUMER = {
    # 音量 / 播放控制
    0xE2: win32con.VK_VOLUME_MUTE,
    0xE9: win32con.VK_VOLUME_UP,
    0xEA: win32con.VK_VOLUME_DOWN,
    0xB5: win32con.VK_MEDIA_NEXT_TRACK,
    0xB6: win32con.VK_MEDIA_PREV_TRACK,
    0xB7: win32con.VK_MEDIA_STOP,
    0xCD: win32con.VK_MEDIA_PLAY_PAUSE,

    # 启动应用类
    0x183: win32con.VK_LAUNCH_MEDIA_SELECT,
    0x18A: win32con.VK_LAUNCH_MAIL,
    0x192: win32con.VK_LAUNCH_APP2,
    0x194: win32con.VK_LAUNCH_APP1,

    # 浏览器
    0x196: win32con.VK_BROWSER_HOME,
    0x221: win32con.VK_BROWSER_SEARCH,
    0x223: win32con.VK_BROWSER_HOME,
    0x224: win32con.VK_BROWSER_BACK,
    0x225: win32con.VK_BROWSER_FORWARD,
    0x226: win32con.VK_BROWSER_STOP,
    0x227: win32con.VK_BROWSER_REFRESH,
    0x22A: win32con.VK_BROWSER_FAVORITES,
}
