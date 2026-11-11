# -*- coding: utf-8 -*-
"""显示文案：VK / usage / 消费类 usage 的友好名称、预期文本与轮次标题。

只做"把值说成人话"，不含任何判定逻辑；判定口径见 judge.py。
"""

from keyboard_driver import usage as vk_map
from keyboard_driver import win32_compat as win32con

from .constants import NUMPAD_LABELS

_VK_NAME_MAP = {value: name for name, value in win32con.__dict__.items()
                if name.startswith('VK_')}


def get_vk_name(vk_value):
    """把虚拟键码转成校准报告里显示的友好名称"""
    if 0x30 <= vk_value <= 0x39 or 0x41 <= vk_value <= 0x5A:
        return chr(vk_value)
    return _VK_NAME_MAP.get(vk_value, '0x%02X' % vk_value)



def numpad_label(usage):
    """小键盘 usage → '小键盘 1'；不在 15 个之内返回 None"""
    name = NUMPAD_LABELS.get(usage)
    return '小键盘 %s' % name if name else None


def consumer_text(usage):
    """消费类 usage → '消费类 0xE9 -> VK_VOLUME_UP'；未知时明确标未知"""
    vk = vk_map.get_consumer_vk(usage)
    if vk is None:
        return '消费类 0x%02X -> 未知' % usage
    return '消费类 0x%02X -> %s' % (usage, get_vk_name(vk))



# ============================================================
# 文本工具
# ============================================================
def usage_text(usage):
    """usage → '0x0D -> J' / '0x66 -> 未映射'"""
    vk = vk_map.get_vk(usage)
    if vk is None:
        return '0x%02X -> 未映射' % usage
    return '0x%02X -> %s' % (usage, get_vk_name(vk))


def expected_text(spec, round_on):
    """当前轮的预期，用于提示与汇总"""
    name, off_usages, on_usage = spec
    if not round_on:
        return '或'.join(usage_text(u) for u in sorted(off_usages))
    if on_usage is not None:
        return usage_text(on_usage)
    return '小键盘 usage（且与灯灭轮不同）'



def round_label(round_on):
    return '灯亮（Num Lock 位=1）' if round_on else '灯灭（Num Lock 位=0）'


def round_short(round_on):
    return '灯亮轮' if round_on else '灯灭轮'


def hex_raw(raw):
    """原始报告 → '05 00 0D 00 00 00 00 00'"""
    return ' '.join('%02X' % b for b in (raw or b'')) or '空'
