# -*- coding: utf-8 -*-
"""hid_usage —— 通用 HID usage → Windows 虚拟键码（VK）映射。

这里是**与具体键盘无关**的通用知识，取自 HID Usage Tables：

* Usage Page 0x07（Keyboard/Keypad）→ VK，见 ``KEYMAP``
* Usage Page 0x0C（Consumer）→ VK，见 ``CONSUMER``
* 自动重复语义：锁定键不重复、音量键参与重复，见 ``repeats_key`` / ``repeats_consumer``

设备专有的东西（VID/PID、报告布局、指示灯输出格式）不在这里，放在 device_profile 包。
通用实现只把设备上报的 usage 交给这张表，不再维护"层表"或任何设备专有的特判——
键盘固件自己按 Num Lock 灯位切换上报的 usage（字母区 0x04..0x1D ↔ 小键盘 0x59..0x63 等），
主机侧只要按 usage 通用映射即可，与 Windows 原生 HID 键盘类的分工一致。

用 ``win32_compat`` 而不是 pywin32 的 win32con：这个模块是项目自带的纯常量表
（ctypes 版），不依赖 pywin32 是否安装。字母/数字键没有 VK_ 常量（Windows 规定
它们的虚拟键码就是 ASCII 码），因此这两组按下标规律生成。
"""

import win32_compat as win32con

KEYMAP = {}

# ---- 字母区 0x04..0x1D = A..Z：VK 即 ASCII ----
KEYMAP.update({0x04 + i: ord('A') + i for i in range(26)})
# ---- 数字行 0x1E..0x27 = 1..9, 0 ----
KEYMAP.update({0x1E + i: ord('1') + i for i in range(9)})
KEYMAP[0x27] = ord('0')

KEYMAP.update({
    # ---- 功能键与编辑键 ----
    0x28: win32con.VK_RETURN, 0x29: win32con.VK_ESCAPE, 0x2A: win32con.VK_BACK,
    0x2B: win32con.VK_TAB, 0x2C: win32con.VK_SPACE,
    0x2D: win32con.VK_OEM_MINUS, 0x2E: win32con.VK_OEM_PLUS,
    0x2F: win32con.VK_OEM_4, 0x30: win32con.VK_OEM_6, 0x31: win32con.VK_OEM_5,
    0x32: win32con.VK_OEM_5, 0x33: win32con.VK_OEM_1, 0x34: win32con.VK_OEM_7,
    0x35: win32con.VK_OEM_3, 0x36: win32con.VK_OEM_COMMA, 0x37: win32con.VK_OEM_PERIOD,
    0x38: win32con.VK_OEM_2, 0x39: win32con.VK_CAPITAL,

    0x3A: win32con.VK_F1, 0x3B: win32con.VK_F2, 0x3C: win32con.VK_F3,
    0x3D: win32con.VK_F4, 0x3E: win32con.VK_F5, 0x3F: win32con.VK_F6,
    0x40: win32con.VK_F7, 0x41: win32con.VK_F8, 0x42: win32con.VK_F9,
    0x43: win32con.VK_F10, 0x44: win32con.VK_F11, 0x45: win32con.VK_F12,
    0x46: win32con.VK_SNAPSHOT, 0x47: win32con.VK_SCROLL, 0x48: win32con.VK_PAUSE,
    0x49: win32con.VK_INSERT, 0x4A: win32con.VK_HOME, 0x4B: win32con.VK_PRIOR,
    0x4C: win32con.VK_DELETE, 0x4D: win32con.VK_END, 0x4E: win32con.VK_NEXT,
    0x4F: win32con.VK_RIGHT, 0x50: win32con.VK_LEFT,
    0x51: win32con.VK_DOWN, 0x52: win32con.VK_UP,

    # ---- 锁定键与小键盘 ----
    # 0x53（Num Lock）与 0x59..0x63（小键盘 1..9/0/小数点）必须同时存在：
    # 设备在 Num Lock 灯位为 1 时会把字母区改报成这些小键盘 usage。
    0x53: win32con.VK_NUMLOCK,
    0x54: win32con.VK_DIVIDE, 0x55: win32con.VK_MULTIPLY, 0x56: win32con.VK_SUBTRACT,
    0x57: win32con.VK_ADD, 0x58: win32con.VK_RETURN,
    0x59: win32con.VK_NUMPAD1, 0x5A: win32con.VK_NUMPAD2, 0x5B: win32con.VK_NUMPAD3,
    0x5C: win32con.VK_NUMPAD4, 0x5D: win32con.VK_NUMPAD5, 0x5E: win32con.VK_NUMPAD6,
    0x5F: win32con.VK_NUMPAD7, 0x60: win32con.VK_NUMPAD8, 0x61: win32con.VK_NUMPAD9,
    0x62: win32con.VK_NUMPAD0, 0x63: win32con.VK_DECIMAL,
    0x64: win32con.VK_OEM_102, 0x65: win32con.VK_APPS,

    # ---- F13..F24（少数键盘/迷你键盘带） ----
    0x68: win32con.VK_F13, 0x69: win32con.VK_F14, 0x6A: win32con.VK_F15,
    0x6B: win32con.VK_F16, 0x6C: win32con.VK_F17, 0x6D: win32con.VK_F18,
    0x6E: win32con.VK_F19, 0x6F: win32con.VK_F20, 0x70: win32con.VK_F21,
    0x71: win32con.VK_F22, 0x72: win32con.VK_F23, 0x73: win32con.VK_F24,

    # ---- 键盘页上的音量键（部分固件把它们放在键码槽里） ----
    0x7F: win32con.VK_VOLUME_MUTE, 0x80: win32con.VK_VOLUME_UP,
    0x81: win32con.VK_VOLUME_DOWN,

    # ---- 修饰键（正常情况下走修饰键字节，个别键盘会塞进键码槽） ----
    0xE0: win32con.VK_LCONTROL, 0xE1: win32con.VK_LSHIFT,
    0xE2: win32con.VK_LMENU, 0xE3: win32con.VK_LWIN,
    0xE4: win32con.VK_RCONTROL, 0xE5: win32con.VK_RSHIFT,
    0xE6: win32con.VK_RMENU, 0xE7: win32con.VK_RWIN,
})

# ============================================================
# Usage Page 0x0C：Consumer（媒体/浏览器/启动应用）
# ============================================================
# 与 Windows 原生消费类 HID 驱动的映射一致；只收录常用的、有对应 VK 的 usage，
# 未收录的 usage 视为"无映射"，注入时直接跳过。
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

# ============================================================
# 自动重复语义
# ============================================================
# Windows 对锁定键不产生 typematic 重复（按住 NumLock 5 秒是 ToggleKeys 快捷键，
# 期间锁定状态不会反复翻转），因此锁定键不参与重复。
NO_REPEAT_VKS = frozenset({
    win32con.VK_CAPITAL, win32con.VK_NUMLOCK, win32con.VK_SCROLL,
})
# 消费类端点只在按下/抬起各上报一次，长按由主机侧补发；只有音量键参与重复
CONSUMER_REPEAT_VKS = (win32con.VK_VOLUME_UP, win32con.VK_VOLUME_DOWN)


def get_vk(hid_code):
    """键盘页 usage → VK；未收录返回 ``None``。"""
    return KEYMAP.get(hid_code)


def get_consumer_vk(usage):
    """消费类 usage → VK；未收录返回 ``None``。"""
    return CONSUMER.get(usage)


def repeats_key(vk):
    """普通键/修饰键是否参与自动重复"""
    return vk is not None and vk not in NO_REPEAT_VKS


def repeats_consumer(vk):
    """消费类按键是否参与长按重复"""
    return vk in CONSUMER_REPEAT_VKS
