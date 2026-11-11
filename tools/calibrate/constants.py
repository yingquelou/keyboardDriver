# -*- coding: utf-8 -*-
"""默认参数与设备事实常量（换键盘需重新确认的部分集中在这里）。

预期值全部由 ``usage.KEYMAP`` 反查生成（按 VK 找 usage），本包不另抄一份映射表：
换 ``usage`` 的映射时，向导与分类采集的提示、判定自动跟着变。
"""

from keyboard_driver import win32_compat as win32con
from keyboard_driver import device_profile as profile
from keyboard_driver import usage

# ---------- 参数默认值 ----------
POLL_MS = 50            # 单次读超时：决定事件粒度，也决定空闲时的 CPU 占用
TIMEOUT_DEFAULT = 15.0  # 每个键的等待秒数
ATTEMPTS_DEFAULT = 3    # 每个键的最多尝试次数（超时/按错/多键同帧都会重试）

# ---------- 待测键清单（默认向导） ----------
# 这里只写"要测哪些物理键"（字母键名）与"灯亮轮已实测过的 usage"；
# 灯灭轮的预期 usage 由 usage.KEYMAP 按 VK 反查生成，不在这里抄映射表。
KEY_NAMES = ('J', 'K', 'L', 'U', 'I', 'O')

# 灯亮轮（Num Lock 位=1）实测过的 usage：J → 0x59（本项目 Win11 实测）。
# 其余键为 None —— 表示按通用规则判定：必须改报成小键盘 usage 且与灯灭轮不同。
MEASURED_ON_USAGE = {'J': 0x59}


def usages_for_vk(vk):
    """usage.KEYMAP 里映射到该 VK 的全部键盘 usage"""
    return frozenset(u for u, value in usage.KEYMAP.items() if value == vk)


def _build_spec(name):
    """(显示名, 灯灭轮可接受的 usage 集合, 灯亮轮实测 usage 或 None)"""
    # 字母键的 VK 就是 ASCII 大写（usage 顶部注释说明），故用 ord 而不是 VK_ 常量
    off_usages = usages_for_vk(ord(name))
    if not off_usages:
        raise SystemExit('usage.KEYMAP 里找不到键 %s 的 usage，无法生成预期' % name)
    return (name, off_usages, MEASURED_ON_USAGE.get(name))


KEY_SPECS = {name: _build_spec(name) for name in KEY_NAMES}
KEY_PLAN = tuple(KEY_SPECS[name] for name in KEY_NAMES)

MODIFIER_BITS = (
    (0x01, '左Ctrl'), (0x02, '左Shift'), (0x04, '左Alt'), (0x08, '左Win'),
    (0x10, '右Ctrl'), (0x20, '右Shift'), (0x40, '右Alt'), (0x80, '右Win'),
)

# 灯亮轮允许出现的切层 usage 全集：HID Usage Tables（Keyboard/Keypad 页）里
# 0x54 '/'、0x55 '*'、0x56 '-'、0x57 '+'、0x59..0x62 小键盘 1..9/0、0x63 '.'，共 15 个。
# 不含 0x58（小键盘 Enter），也不含 0x64 之后的 usage。
NUMPAD_USAGES = frozenset([0x54, 0x55, 0x56, 0x57] + list(range(0x59, 0x64)))
NUMPAD_LABELS = {
    0x54: '/', 0x55: '*', 0x56: '-', 0x57: '+',
    0x59: '1', 0x5A: '2', 0x5B: '3', 0x5C: '4', 0x5D: '5',
    0x5E: '6', 0x5F: '7', 0x60: '8', 0x61: '9', 0x62: '0', 0x63: '.',
}

# 灯亮轮只有下面这 15 颗实体键会改报为小键盘 usage，其余键两轮必须完全一致。
# 7 8 9 0 U I O P J K L ; M . / —— 与键帽上的 15 个小键盘副标注一一对应。
# "'"（0x34）、","（0x36）实测不切层，不在集合内。
# 换键盘要重新实测；可用 --layer-key 覆盖整个集合。
LAYER_KEYS = frozenset(('7', '8', '9', '0', 'U', 'I', 'O', 'P',
                        'J', 'K', 'L', ';', 'M', '.', '/'))

# 灯亮轮每个物理键的确定目标 usage（键帽副标注，--layer-pair 可覆盖）。
# 正好用完 HID 的 15 个小键盘 usage：0x54 '/'、0x55 '*'、0x56 '-'、0x57 '+'、
# 0x59..0x63 小键盘 1..9/0/.，不含 0x58（小键盘 Enter，本键盘键帽上也没有该副标注）。
MEASURED_LAYER_TARGETS = {
    '7': 0x5F, '8': 0x60, '9': 0x61, '0': 0x55,
    'U': 0x5C, 'I': 0x5D, 'O': 0x5E, 'P': 0x56,
    'J': 0x59, 'K': 0x5A, 'L': 0x5B, ';': 0x57,
    'M': 0x62, '.': 0x63, '/': 0x54,
}

# Num Lock 指示灯位来自 device_profile，不写死
NUM_LED_BIT = 0x01
for _bit, _vk in profile.LED_BITS:
    if _vk == win32con.VK_NUMLOCK:
        NUM_LED_BIT = _bit
