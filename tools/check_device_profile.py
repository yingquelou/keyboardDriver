# -*- coding: utf-8 -*-
"""check_device_profile.py —— device_profile 一致性自检（纯离线，不碰真机）

验证"当前设备实现是否完整满足 ``KeyboardDevice`` 契约"：

- 契约强制力：基类不可直接实例化，实现类没有残留的 abstract 成员；
- 身份：name 非空、VID/PID 在 0..0xFFFF；
- 方法签名：实现的方法参数个数与契约一致（少一个/多一个都算不合格）；
- 键盘报告：长度为正、修饰键与键槽区间自洽、残包返回 ``(0, None)``、读取长度覆盖；
- 消费类报告：Report ID 与 usage 布局自洽、按 Report ID 过滤、长度不足丢弃；
- 通用映射：usage 覆盖字母区与小键盘 usage（0x0D 与 0x59 并存）、未映射返回
  ``None``、锁定键/可重复消费键的语义正确、包里不再暴露任何"层"概念；
- 指示灯：报告长度固定、Report ID 处理正确、位图截断正确、位定义合法；
- 导出表：``device_profile.__all__`` 与 ``transport.__all__`` 中的名字都存在、
  没有公共名漏出、不含层相关旧符号。

用法：
    python tools\\check_device_profile.py

退出码 0 = 全部通过；1 = 有失败项。新增/更换键盘后先跑这个脚本，再上真机。
"""

import inspect
import os
import sys

# 本文件位于 tools/：把项目根加入模块搜索路径，按包名导入 keyboard_driver。
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from keyboard_driver import device_profile as profile
from keyboard_driver import usage
from keyboard_driver import transport
from keyboard_driver import win32_compat as win32con
from keyboard_driver.device_profile.contract import KeyboardDevice

_passed = 0
_failures = []


def check(label, condition, detail=''):
    """记录一项检查；失败时打印原因并计入总失败数。"""
    global _passed
    if condition:
        _passed += 1
        print("[PASS] " + label)
        return True
    _failures.append(label)
    print("[FAIL] " + label + ('：' + detail if detail else ''))
    return False


def _positional_params(obj, name):
    """取某个可调用成员的位置参数个数；属性或不可调用时返回 None。"""
    try:
        attr = getattr(obj, name)
    except AttributeError:
        return None
    if not callable(attr):
        return None
    try:
        signature = inspect.signature(attr)
    except (TypeError, ValueError):
        return None
    return sum(1 for p in signature.parameters.values()
               if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD))


def check_instantiation():
    print("\n== 1. 契约强制力 ==")
    try:
        KeyboardDevice()
    except TypeError:
        check('契约基类不可直接实例化（abstract 生效）', True)
    else:
        check('契约基类不可直接实例化（abstract 生效）', False,
              'KeyboardDevice() 居然成功')
    leftover = sorted(getattr(type(profile.PROFILE), '__abstractmethods__', ()))
    check('实现类没有未实现的 abstract 成员', not leftover, ', '.join(leftover))


def check_identity():
    print("\n== 2. 身份 ==")
    check('NAME 为非空字符串', isinstance(profile.NAME, str) and bool(profile.NAME.strip()),
          repr(profile.NAME))
    for attr, label in (('VID', 'VID'), ('PID', 'PID')):
        value = getattr(profile, attr)
        check(label + ' 为 0..0xFFFF 的整数',
              isinstance(value, int) and 0 <= value <= 0xFFFF, repr(value))


def check_signatures():
    print("\n== 3. 方法签名 ==")
    names = sorted(name for name, value in vars(KeyboardDevice).items()
                   if callable(value) and not name.startswith('_'))
    for name in names:
        base_count = _positional_params(KeyboardDevice, name)
        impl_count = _positional_params(profile.PROFILE, name)
        if base_count is None:
            continue
        # 基类取到的是未绑定函数（含 self），实现取到的是绑定方法（不含 self）。
        expected = base_count - 1
        check('%s 参数个数与契约一致' % name, impl_count == expected,
              '契约 %d 个，实现 %r 个' % (expected, impl_count))


def check_key_report():
    print("\n== 4. 键盘报告 ==")
    length = profile.KEY_REPORT_LENGTH
    ok = check('KEY_REPORT_LENGTH 为正整数',
               isinstance(length, int) and length > 0, repr(length))
    if not ok:
        return
    check('MODIFIER_BYTE_INDEX 落在报告内',
          0 <= profile.MODIFIER_BYTE_INDEX < length, repr(profile.MODIFIER_BYTE_INDEX))
    check('键槽区间 0 <= start <= end <= 报告长度',
          0 <= profile.KEY_SLOT_START <= profile.KEY_SLOT_END <= length,
          '%r..%r / %r' % (profile.KEY_SLOT_START, profile.KEY_SLOT_END, length))
    check('parse_key_report(None) 返回 (0, None)',
          profile.parse_key_report(None) == (0, None))
    check('残包（长度-1）返回 (0, None)',
          profile.parse_key_report(b'\x00' * (length - 1)) == (0, None))
    check('全零完整报告解析为空键集',
          profile.parse_key_report(b'\x00' * length) == (0, []),
          repr(profile.parse_key_report(b'\x00' * length)))
    check('key_report_read_size 覆盖完整报告',
          profile.key_report_read_size(1) >= length)
    check('key_report_read_size 不小于端点包长',
          profile.key_report_read_size(64) >= 64)


def check_consumer_report():
    print("\n== 5. 消费类报告 ==")
    id_size = profile.CONSUMER_REPORT_ID_SIZE
    usage_size = profile.CONSUMER_USAGE_SIZE
    check('消费类读取长度覆盖 Report ID + usage',
          profile.consumer_report_read_size(1) >= id_size + usage_size)
    check('parse_consumer_report(None) 返回 None',
          profile.parse_consumer_report(None) is None)

    items = [(profile.CONSUMER_USAGE_PAGE, profile.CONSUMER_REPORT_ID,
              profile.CONSUMER_USAGE_BITS)]
    chosen = profile.choose_consumer_report(items)
    probe = bytes([profile.CONSUMER_REPORT_ID]) + int(0x00E9).to_bytes(
        usage_size, profile.CONSUMER_USAGE_BYTE_ORDER)
    if chosen is None:
        print("[SKIP] 该设备未声明消费类集合（choose_consumer_report 返回 None）")
        check('未声明消费类集合时解析恒为 None',
              profile.parse_consumer_report(probe) is None)
        return
    report_id, usage_bytes = chosen
    check('消费类 Report ID 与 usage 字节数合法',
          report_id > 0 and usage_bytes > 0, repr(chosen))
    check('消费类报告能解析出 usage',
          profile.parse_consumer_report(probe) == 0x00E9,
          repr(profile.parse_consumer_report(probe)))
    wrong_id = bytes([(report_id + 1) & 0xFF]) + probe[1:]
    check('Report ID 不符的报文被丢弃',
          profile.parse_consumer_report(wrong_id) is None)
    short = probe[:id_size + usage_size - 1]
    check('长度不足的报文被丢弃',
          profile.parse_consumer_report(short) is None)


def check_usage_map():
    print("\n== 6. 通用 usage 映射（usage） ==")
    # 反向断言：以下名字属于已删除的"软件层切换"方案，这里显式要求它们**不存在**，
    # 防止旧符号被重新引入。不是残留引用，不要当成待清理代码。
    check('device_profile 不再暴露层概念（回归防线）',
          not any(hasattr(profile, n) for n in
                  ('LAYERS', 'LAYER_ORDER', 'DEFAULT_LAYER_NAME', 'LAYER_TOGGLE_HID',
                   'is_layer_toggle', 'next_layer_name', 'keymap_subsets')))
    keymap = usage.KEYMAP
    check('KEYMAP 为非空映射', isinstance(keymap, dict) and bool(keymap),
          repr(type(keymap)))
    check('KEYMAP 的值全为整数 VK',
          all(isinstance(vk, int) for vk in keymap.values()))
    # 设备在 Num Lock 灯位为 1 时把字母区改报成小键盘 usage，
    # 因此这两组必须同时存在，主机才不需要"层"。
    check('字母区 usage（0x04..0x1D）全部可映射',
          all(0x04 + i in keymap for i in range(26)))
    check('小键盘 usage（0x59..0x63）全部可映射',
          all(0x59 + i in keymap for i in range(11)))
    check('0x0D -> VK_J', keymap.get(0x0D) == ord('J'), repr(keymap.get(0x0D)))
    check('0x59 -> VK_NUMPAD1', keymap.get(0x59) == win32con.VK_NUMPAD1,
          repr(keymap.get(0x59)))
    check('0x53 -> VK_NUMLOCK（锁定键按 usage 转发）',
          keymap.get(0x53) == win32con.VK_NUMLOCK, repr(keymap.get(0x53)))
    check('未映射 usage 返回 None', usage.get_vk(0xFFFF) is None)
    check('消费类映射非空且音量键可映射',
          bool(usage.CONSUMER)
          and usage.get_consumer_vk(0xE9) == win32con.VK_VOLUME_UP,
          repr(usage.get_consumer_vk(0xE9)))
    check('未映射消费类 usage 返回 None',
          usage.get_consumer_vk(0xFFFF) is None)


def check_policy():
    print("\n== 7. 重复语义与指示灯 ==")
    check('repeats_key(None) 为假', usage.repeats_key(None) is False)
    for vk in usage.NO_REPEAT_VKS:
        check('免重复键 0x%02X 不参与重复' % vk,
              usage.repeats_key(vk) is False)
    for vk in usage.CONSUMER_REPEAT_VKS:
        check('消费类重复键 0x%02X 参与重复' % vk,
              usage.repeats_consumer(vk) is True)
    check('未声明的消费类键不参与重复',
          usage.repeats_consumer(0) is False)

    length = profile.LED_REPORT_LENGTH
    report = profile.led_report(0xFF)
    check('led_report 返回固定长度的 bytes',
          isinstance(report, bytes) and len(report) == length, repr(report))
    if profile.LED_REPORT_ID:
        check('led_report 首字节为 Report ID',
              report[0] == profile.LED_REPORT_ID, repr(report))
        check('带 Report ID 时长度 = 1 + 报告长度',
              len(report) == length + 1, repr(report))
    else:
        check('无 Report ID 时首字节即位图', len(report) == length, repr(report))
    mask = (1 << (8 * length)) - 1 if length > 0 else 0
    check('led_report 按报告长度截断位图',
          int.from_bytes(report[-length:], 'little') == (0xFF & mask),
          repr(report))
    for bit, vk in profile.LED_BITS:
        check('LED 位定义 (0x%02X -> VK 0x%02X) 合法' % (bit, vk),
              isinstance(bit, int) and isinstance(vk, int) and bit > 0)
    if profile.LED_SUPPORTED:
        check('声明支持指示灯时位定义为非空', bool(profile.LED_BITS))
        check('LED 轮询间隔为正数',
              isinstance(profile.LED_POLL_INTERVAL_S, (int, float))
              and profile.LED_POLL_INTERVAL_S > 0,
              repr(profile.LED_POLL_INTERVAL_S))


def check_exports():
    print("\n== 8. 导出表 ==")
    exported = list(profile.__all__)
    check('device_profile.__all__ 无重复项', len(exported) == len(set(exported)),
          repr(len(exported)))
    missing = sorted(n for n in exported if not hasattr(profile, n))
    check('__all__ 中的名字都能从包里取到', not missing, ', '.join(missing))
    # 类名与子模块按设计不进 __all__（可直接导入，但不是对外承诺面）。
    intentional = {'PROFILE', 'KeyboardDevice', 'Wireless1EA7_0066',
                   'contract', 'device', 'identity', 'reports'}
    leaked = sorted(n for n in dir(profile)
                    if not n.startswith('_') and n not in exported and n not in intentional)
    check('没有公共名漏出 __all__', not leaked, ', '.join(leaked))
    check('__all__ 不含层相关旧符号',
          not any('layer' in n.lower() for n in exported))
    check('device_profile 不再转手 win32con（通用常量归 win32_compat）',
          not hasattr(profile, 'win32con') and 'win32con' not in exported)

    utils_all = list(transport.__all__)
    utils_missing = sorted(n for n in utils_all if not hasattr(transport, n))
    check('transport.__all__ 中的名字都存在', not utils_missing,
          ', '.join(utils_missing))
    check('transport 导出 has_active_keys（主循环按它切换读超时）',
          hasattr(transport, 'has_active_keys') and 'has_active_keys' in utils_all)
    check('transport 不再重复导出 usage→VK 换算（归 usage）',
          not hasattr(transport, 'get_vk')
          and not hasattr(transport, 'get_vk_name'))
    check('transport.__all__ 不含层相关旧符号',
          not any('layer' in n.lower() or 'toggle' in n.lower() for n in utils_all))


def main():
    print("device_profile 一致性自检：%s (%s)" % (profile.NAME, type(profile.PROFILE).__name__))
    check_instantiation()
    check_identity()
    check_signatures()
    check_key_report()
    check_consumer_report()
    check_usage_map()
    check_policy()
    check_exports()

    print("\n---- 结果：%d 项通过，%d 项失败 ----" % (_passed, len(_failures)))
    if _failures:
        print("失败项：")
        for item in _failures:
            print("  - " + item)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
