# -*- coding: utf-8 -*-
"""策略：自动重复规则与指示灯能力。

与“某键映射到哪个 VK”无关，只描述行为：哪些键参与长按补发、指示灯能不能写、
位序与轮询间隔。换键盘且这些结论不同时改这里。
"""

from ._win32 import win32con

# ============================================================
# 自动重复策略
# ============================================================
# Windows 对锁定键不产生 typematic 重复（按住 NumLock 5 秒是 ToggleKeys 快捷键，
# 期间锁定状态不会反复翻转），因此锁定键不参与重复。
NO_REPEAT_VKS = frozenset({
    win32con.VK_CAPITAL, win32con.VK_NUMLOCK, win32con.VK_SCROLL,
})
# 消费类端点只在按下/抬起各上报一次，长按由主机侧补发；只有音量键参与重复
CONSUMER_REPEAT_VKS = (win32con.VK_VOLUME_UP, win32con.VK_VOLUME_DOWN)


def repeats_key(vk):
    """普通键/修饰键是否参与自动重复"""
    return vk is not None and vk not in NO_REPEAT_VKS


def repeats_consumer(vk):
    """消费类按键是否参与长按重复"""
    return vk in CONSUMER_REPEAT_VKS


# ============================================================
# 指示灯能力
# ============================================================
# 键盘接口（MI_00）的 HID 输出报告：5 位 LED（Num/Caps/Scroll/Compose/Kana）+ 3 位填充 = 1 字节。
# 实测结论（本键盘，WinUSB 接管模式）：
#   Set_Report（1 字节 / 2 字节）与各类位图写入均返回成功，但物理指示灯无任何反应，
#   接口 0 也只有 IN 端点（无中断 OUT 端点）。因此判定该键盘的指示灯在接管模式下不可控，
#   原生 HID 驱动下灯是正常的。默认不启用，只有显式 --led 才尝试。
LED_SUPPORTED = False
LED_REPORT_LENGTH = 1
LED_POLL_INTERVAL_S = 0.2      # 低频兜底轮询，避免无谓的 USB 流量
# (位, 对应锁定状态的 VK)；位序按 HID 输出报告定义
LED_BITS = (
    (0x01, win32con.VK_NUMLOCK),
    (0x02, win32con.VK_CAPITAL),
    (0x04, win32con.VK_SCROLL),
)
LED_UNAVAILABLE_HINT = "本设备在 WinUSB 接管模式下写灯返回成功但物理指示灯无反应"


def led_report(bitmap):
    """把 LED 位图打包成 HID 输出报告（按 LED_REPORT_LENGTH 与位序）"""
    mask = (1 << (8 * LED_REPORT_LENGTH)) - 1
    return int(bitmap & mask).to_bytes(LED_REPORT_LENGTH, 'little')
