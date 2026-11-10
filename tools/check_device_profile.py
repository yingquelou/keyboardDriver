# -*- coding: utf-8 -*-
"""check_device_profile.py —— device_profile 一致性自检（纯离线，不碰真机）

验证"当前设备实现是否完整满足 ``KeyboardDevice`` 契约"：

- 契约强制力：基类不可直接实例化，实现类没有残留的 abstract 成员；
- 身份：name 非空、VID/PID 在 0..0xFFFF；
- 方法签名：实现的方法参数个数与契约一致（少一个/多一个都算不合格）；
- 键盘报告：长度为正、修饰键与键槽区间自洽、残包返回 ``(0, None)``、读取长度覆盖；
- 消费类报告：Report ID 与 usage 布局自洽、按 Report ID 过滤、长度不足丢弃；
- 键表与层：层顺序覆盖全部层、默认层在顺序内、子表被层完整覆盖、
  层切换键不出现在任何映射表中、轮转 N 次回到起始层；
- 重复策略：``None`` 不重复、锁定键不重复、声明可重复的消费键可重复；
- 指示灯：报告长度固定、位图截断正确；默认关闭时给出不可用说明。

用法：
    python tools\\check_device_profile.py

退出码 0 = 全部通过；1 = 有失败项。新增/更换键盘后先跑这个脚本，再上真机。
"""

import inspect
import os
import sys

# 本文件位于 tools/：把 src/ 加入模块搜索路径，避免依赖当前工作目录。
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import device_profile as profile
from device_profile.contract import KeyboardDevice

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


def check_layers():
    print("\n== 6. 键表与层 ==")
    layers = profile.LAYERS
    order = tuple(profile.LAYER_ORDER)
    if not check('LAYERS 为非空映射', isinstance(layers, dict) and bool(layers), repr(type(layers))):
        return
    check('LAYER_ORDER 与 LAYERS 的层集合一致',
          set(order) == set(layers), '%r vs %r' % (order, sorted(layers)))
    check('DEFAULT_LAYER_NAME 在层顺序内',
          profile.DEFAULT_LAYER_NAME in order, repr(profile.DEFAULT_LAYER_NAME))
    for layer_name in order:
        layer = layers.get(layer_name) or {}
        check("层 %r 非空且值为整数" % layer_name,
              bool(layer) and all(isinstance(vk, int) for vk in layer.values()),
              repr(layer.get(layer_name)))

    subsets = profile.PROFILE.keymap_subsets
    if not subsets:
        print("[SKIP] 该设备未声明 keymap_subsets，跳过子表覆盖检查")
    for subset_name, subset in subsets.items():
        covered = any(all(layer.get(hid) == vk for hid, vk in subset.items())
                      for layer in layers.values())
        check('子表 %s 被某一层完整覆盖' % subset_name, covered,
              '子表有 %d 项' % len(subset))

    toggle = profile.LAYER_TOGGLE_HID
    if toggle is None:
        check('未声明层切换键时 is_layer_toggle 恒为假',
              not profile.is_layer_toggle(0x53))
    else:
        check('层切换键本身被识别', profile.is_layer_toggle(toggle))
        check('其它 HID 码不被误判为层切换键',
              not profile.is_layer_toggle(toggle ^ 0x01))
        hit_layers = [name for name, layer in layers.items() if toggle in layer]
        check('层切换键不出现在任何映射表中', not hit_layers,
              '出现在 %r' % hit_layers)

    current = profile.DEFAULT_LAYER_NAME
    for _ in range(len(order)):
        current = profile.next_layer_name(current)
    check('层轮转 %d 次回到起始层' % len(order),
          current == profile.DEFAULT_LAYER_NAME, repr(current))

    first_layer = layers[order[0]]
    sample_hid, sample_vk = next(iter(first_layer.items()))
    check('get_vk 能按层取到映射值',
          profile.get_vk(order[0], sample_hid) == sample_vk)
    check('get_vk 对未映射键返回 None',
          profile.get_vk(order[0], 0xFFFF) is None)


def check_policy():
    print("\n== 7. 重复策略与指示灯 ==")
    check('repeats_key(None) 为假', profile.repeats_key(None) is False)
    for vk in profile.NO_REPEAT_VKS:
        check('免重复键 0x%02X 不参与重复' % vk,
              profile.repeats_key(vk) is False)
    for vk in profile.CONSUMER_REPEAT_VKS:
        check('消费类重复键 0x%02X 参与重复' % vk,
              profile.repeats_consumer(vk) is True)
    check('未声明的消费类键不参与重复',
          profile.repeats_consumer(0) is False)

    length = profile.LED_REPORT_LENGTH
    report = profile.led_report(0xFF)
    check('led_report 返回固定长度的 bytes',
          isinstance(report, bytes) and len(report) == length, repr(report))
    mask = (1 << (8 * length)) - 1 if length > 0 else 0
    check('led_report 按报告长度截断位图',
          int.from_bytes(profile.led_report(0x1FF), 'little') == (0x1FF & mask),
          repr(profile.led_report(0x1FF)))
    for bit, vk in profile.LED_BITS:
        check('LED 位定义 (0x%02X -> VK 0x%02X) 合法' % (bit, vk),
              isinstance(bit, int) and isinstance(vk, int) and bit > 0)
    if not profile.LED_SUPPORTED:
        check('默认关闭指示灯时给出不可用说明',
              isinstance(profile.LED_UNAVAILABLE_HINT, str)
              and bool(profile.LED_UNAVAILABLE_HINT.strip()),
              repr(profile.LED_UNAVAILABLE_HINT))


def main():
    print("device_profile 一致性自检：%s (%s)" % (profile.NAME, type(profile.PROFILE).__name__))
    check_instantiation()
    check_identity()
    check_signatures()
    check_key_report()
    check_consumer_report()
    check_layers()
    check_policy()

    print("\n---- 结果：%d 项通过，%d 项失败 ----" % (_passed, len(_failures)))
    if _failures:
        print("失败项：")
        for item in _failures:
            print("  - " + item)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
