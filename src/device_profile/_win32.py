# -*- coding: utf-8 -*-
"""win32 常量入口：优先 pywin32，缺失时退回 ctypes 兼容层，并补全键表用到的 VK。

包内其它模块只从这里取 ``win32con``，避免每处重复 try/except；补全只在导入时做一次。
"""

try:
    import win32con
except ImportError:                       # 未安装 pywin32（例如 MSYS2/mingw 版 Python）
    import win32_compat as win32con

# ---------- 补全 win32con 缺失的 OEM / 媒体常量 ----------
_undefined_vk = {
    'VK_OEM_MINUS': 0xBD,
    'VK_OEM_1': 0xBA,
    'VK_OEM_5': 0xDC,
    'VK_OEM_COMMA': 0xBC,
    'VK_OEM_3': 0xC0,
    'VK_OEM_PERIOD': 0xBE,
    'VK_OEM_2': 0xBF,
    'VK_OEM_PLUS': 0xBB,
    'VK_OEM_4': 0xDB,
    'VK_OEM_7': 0xDE,
    'VK_OEM_6': 0xDD
}
_undefined_media_vk = {
    'VK_VOLUME_MUTE': 0xAD,
    'VK_VOLUME_DOWN': 0xAE,
    'VK_VOLUME_UP': 0xAF,
    'VK_MEDIA_NEXT_TRACK': 0xB0,
    'VK_MEDIA_PREV_TRACK': 0xB1,
    'VK_MEDIA_STOP': 0xB2,
    'VK_MEDIA_PLAY_PAUSE': 0xB3,
    'VK_LAUNCH_MAIL': 0xB4,
    'VK_LAUNCH_MEDIA_SELECT': 0xB5,
    'VK_LAUNCH_APP1': 0xB6,
    'VK_LAUNCH_APP2': 0xB7,
    'VK_BROWSER_BACK': 0xA6,
    'VK_BROWSER_FORWARD': 0xA7,
    'VK_BROWSER_REFRESH': 0xA8,
    'VK_BROWSER_STOP': 0xA9,
    'VK_BROWSER_SEARCH': 0xAA,
    'VK_BROWSER_FAVORITES': 0xAB,
    'VK_BROWSER_HOME': 0xAC
}
for _table in (_undefined_vk, _undefined_media_vk):
    for _key_name, _value in _table.items():
        if not hasattr(win32con, _key_name):
            setattr(win32con, _key_name, _value)
