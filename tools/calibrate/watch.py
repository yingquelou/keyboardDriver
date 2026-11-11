# -*- coding: utf-8 -*-
"""--watch：老用法，常驻把每个键的 HID 码翻译成 VK 名，不判定、不留档。"""

from . import device
from .constants import MODIFIER_BITS
from .text import usage_text

def watch_mode(dev, ep):
    reader = device.Reader(dev, ep)
    print('')
    print('=== 键盘信息查看（--watch） ===')
    print('按下任意键，程序打印其 HID 码与按 usage 换出的 VK 名；按 Ctrl+C 退出。')
    print('Num Lock 灯位不同会显示不同的 HID 码（固件切层），属正常现象。')
    try:
        while True:
            got = reader.wait_change(1.0)
            if got is None:
                continue
            added, removed, mod_down, mod_up = got
            for bit, name in MODIFIER_BITS:
                if mod_down & bit:
                    print('修饰键 %s 按下' % name)
                if mod_up & bit:
                    print('修饰键 %s 抬起' % name)
            for usage in added:
                print('按下 %s' % usage_text(usage))
            for usage in removed:
                print('抬起 %s' % usage_text(usage))
    except KeyboardInterrupt:
        print('')
        print('信息查看已退出。')
