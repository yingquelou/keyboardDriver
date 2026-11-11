# -*- coding: utf-8 -*-
"""native_probe.py —— "固件切层是否依赖主机 LED" 判定实验（只读，不注入按键）

背景：目标是让主机只扮演通用 HID 键盘类驱动——固件自己按原生逻辑切层并上报
对应 usage。要判定的是：在**完全不写 LED**的接管状态下按 Num Lock，同一实体键
的 usage 会不会从 0x0D（J）变成 0x59（小键盘 1）。

前提：设备接口已绑定 WinUSB（Zadig Replace Driver）。原生 HidUsb 下键盘集合
不允许用户态读取原始报告，本脚本会明确报错而不是静默降级。

安全约束：
  * 只读原始报告，绝不调用 SendInput / keybd_event / 注入任何按键；
  * 只有 led 子命令会写 LED Output 报告（按描述符算出的准确 Report ID 与长度），
    用于判定"接管下能否回写 LED"。

用法（绑定 WinUSB 后，用另一把键盘操作）：
    python tools\\native_probe.py info
    python tools\\native_probe.py capture --seconds 30
    python tools\\native_probe.py led --seconds 8
"""

import argparse
import ctypes
import datetime
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import usb.backend.libusb1
import usb.core
import usb.util

from keyboard_driver import device_profile as profile

user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.GetKeyState.restype = ctypes.c_short
user32.GetKeyState.argtypes = [ctypes.c_int]

VK_NUMLOCK = 0x90
VK_CAPITAL = 0x14
VK_SCROLL = 0x91

USAGE_PAGE_LED = 0x08
USAGE_NUM_LOCK = 0x01
USAGE_CAPS_LOCK = 0x02
USAGE_SCROLL_LOCK = 0x03


def now_str():
    return datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]


def hex_bytes(data):
    return ' '.join('%02X' % b for b in data)


def lock_state_text():
    """读取三个锁定键的系统切换状态（低位为开/关），用于记录两次 Num Lock 之间 OS 侧状态。"""
    def on(vk):
        return 'ON' if (user32.GetKeyState(vk) & 0x0001) else 'OFF'
    return '系统锁定状态: NumLock=%s CapsLock=%s ScrollLock=%s' % (
        on(VK_NUMLOCK), on(VK_CAPITAL), on(VK_SCROLL))


def resolve(value):
    """pyusb 1.3 起 configurations/endpoints 等变成了方法，统一取值。"""
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def get_backend():
    backend = usb.backend.libusb1.get_backend()
    if backend is None:
        raise SystemExit('无法加载 libusb 后端（检查 libusb-1.0.dll 是否与 Python 位数一致）')
    return backend


def iter_interfaces(dev):
    try:
        cfg = dev.get_active_configuration()
    except Exception:
        return
    try:
        for intf in cfg:
            yield intf
    except Exception:
        return


def find_in_endpoint(intf):
    eps = resolve(getattr(intf, 'endpoints', None)) or []
    for ep in eps:
        addr = ep.bEndpointAddress
        if (usb.util.endpoint_direction(addr) == usb.util.ENDPOINT_IN
                and usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_INTR):
            return ep
    return None


def find_out_endpoint(intf):
    eps = resolve(getattr(intf, 'endpoints', None)) or []
    for ep in eps:
        addr = ep.bEndpointAddress
        if (usb.util.endpoint_direction(addr) == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_INTR):
            return ep
    return None


def open_keyboard():
    """按角色找键盘接口并 claim；找不到/claim 不了时给出明确提示。"""
    backend = get_backend()
    devs = list(usb.core.find(find_all=True, idVendor=profile.VID,
                              idProduct=profile.PID, backend=backend))
    if not devs:
        raise SystemExit('libusb 未枚举到 %04X:%04X：请确认设备已插好且接口已绑定 WinUSB'
                         '（原生 HidUsb 下 libusb 看不到可 claim 的接口）'
                         % (profile.VID, profile.PID))
    problems = []
    for dev in devs:
        for intf in iter_interfaces(dev):
            if not profile.is_keyboard_interface(intf):
                continue
            ep = find_in_endpoint(intf)
            if ep is None:
                continue
            try:
                dev.set_configuration()
            except usb.core.USBError:
                pass
            try:
                usb.util.claim_interface(dev, intf.bInterfaceNumber)
            except usb.core.USBError as exc:
                problems.append('bus=%s addr=%s 接口%d: %s' % (
                    getattr(dev, 'bus', '?'), getattr(dev, 'address', '?'),
                    intf.bInterfaceNumber, exc))
                continue
            print('[信息] 使用设备 bus=%s addr=%s 接口%d（%02X/%02X/%02X），端点 %s'
                  % (getattr(dev, 'bus', '?'), getattr(dev, 'address', '?'),
                     intf.bInterfaceNumber, intf.bInterfaceClass,
                     intf.bInterfaceSubClass, intf.bInterfaceProtocol,
                     _ep_text(ep)))
            return dev, intf, ep
    detail = ('；'.join(problems)) if problems else '没有找到 3/1/1 键盘接口'
    raise SystemExit('无法打开键盘接口（%s）。请确认已用 Zadig 把 MI_00/MI_01 或父设备'
                     '替换为 WinUSB。' % detail)


def _ep_text(ep):
    return '0x%02X(IN,中断,%d字节,间隔%s)' % (
        ep.bEndpointAddress, ep.wMaxPacketSize, getattr(ep, 'bInterval', '?'))


def _ep_full_text(ep):
    direction = 'IN' if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN else 'OUT'
    types = {
        usb.util.ENDPOINT_TYPE_CTRL: '控制',
        usb.util.ENDPOINT_TYPE_ISO: '同步',
        usb.util.ENDPOINT_TYPE_BULK: '批量',
        usb.util.ENDPOINT_TYPE_INTR: '中断',
    }
    return '0x%02X 方向=%s 类型=%s 包长=%d 间隔=%s' % (
        ep.bEndpointAddress, direction,
        types.get(usb.util.endpoint_type(ep.bmAttributes), '?'),
        ep.wMaxPacketSize, getattr(ep, 'bInterval', '?'))


def report_interfaces(dev):
    """打印 pyusb 看到的接口/端点结构，并逐个尝试 claim（随即释放）。"""
    print('\n[pyusb 看到的接口与端点]')
    for intf in iter_interfaces(dev):
        role = '键盘' if profile.is_keyboard_interface(intf) else (
            '消费类' if profile.is_consumer_interface(intf) else '其他')
        print('  接口%d alt=%d 类/子类/协议=%02X/%02X/%02X（%s）'
              % (intf.bInterfaceNumber, intf.bAlternateSetting, intf.bInterfaceClass,
                 intf.bInterfaceSubClass, intf.bInterfaceProtocol, role))
        for ep in resolve(getattr(intf, 'endpoints', None)) or []:
            print('    端点 %s' % _ep_full_text(ep))
    print('\n[claim 测试]')
    for intf in iter_interfaces(dev):
        number = intf.bInterfaceNumber
        try:
            usb.util.claim_interface(dev, number)
        except usb.core.USBError as exc:
            print('  接口%d：claim 失败 —— %s（该接口多半仍由系统原生驱动服务）'
                  % (number, exc))
            continue
        print('  接口%d：claim 成功（随即释放）' % number)
        usb.util.release_interface(dev, number)


def hid_descriptor_length(intf):
    """从接口的 HID 描述符（bDescriptorType=0x21）取报告描述符的声明长度。"""
    extra = bytes(getattr(intf, 'extra', None) or b'')
    i = 0
    while i + 9 <= len(extra):
        length = extra[i]
        if length < 3:
            return None
        if extra[i + 1] == 0x21:
            return extra[i + 7] | (extra[i + 8] << 8)
        i += length
    return None


def get_report_descriptor(dev, intf):
    expected = hid_descriptor_length(intf)
    if expected:
        print('[信息] HID 描述符声明的报告描述符长度：%d 字节' % expected)
    data = None
    for bm in (0x81, 0x80):
        try:
            data = dev.ctrl_transfer(bm, 0x06, 0x2200, intf.bInterfaceNumber, 1024, timeout=500)
        except Exception as exc:
            print('[警告] 读取报告描述符失败（bmRequestType=0x%02X）：%s' % (bm, exc))
            continue
        if data and (not expected or len(data) == expected):
            return bytes(data)
    if not data:
        return None
    print('[警告] 报告描述符长度 %d 与 HID 描述符声明的 %s 不一致，解析结果可能不可信'
          % (len(data), expected if expected else '未知'))
    return bytes(data)


def parse_report_descriptor(desc):
    """解析 HID 报告描述符里的 Input/Output/Feature 主项。

    返回 (entries, cursors)：
      entries[kind] = [{page, report_id, size, count, bit_offset, usages}, ...]
      cursors[(kind, report_id)] = 该报告已占用的总位数
    """
    entries = {'input': [], 'output': [], 'feature': []}
    cursors = {}
    usage_page = 0
    report_id = 0
    report_size = 0
    report_count = 0
    usages = []
    usage_min = None
    usage_max = None
    i = 0
    n = len(desc)
    while i < n:
        prefix = desc[i]
        i += 1
        if prefix == 0xFE:                       # 长项目：跳过
            if i + 2 > n:
                break
            size = desc[i] | (desc[i + 1] << 8)
            i += 2 + size
            continue
        size = prefix & 0x03
        if size == 3:
            size = 4
        if i + size > n:
            break
        value = int.from_bytes(desc[i:i + size], 'little') if size else 0
        i += size
        itype = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        if itype == 1:                           # 全局项
            if tag == 0x0:
                usage_page = value
            elif tag == 0x7:
                report_size = value
            elif tag == 0x8:
                report_id = value
            elif tag == 0x9:
                report_count = value
        elif itype == 2:                         # 局部项
            if tag == 0x0:
                if size == 4:                    # 扩展 usage：高 16 位为 usage page
                    usages.append((value >> 16) & 0xFFFF)
                else:
                    usages.append(value)
            elif tag == 0x1:
                usage_min = value
            elif tag == 0x2:
                usage_max = value
        elif itype == 0:                         # 主项
            kind = {0x8: 'input', 0x9: 'output', 0xB: 'feature'}.get(tag)
            if kind is not None:
                expanded = list(usages)
                if (usage_min is not None and usage_max is not None
                        and len(expanded) < report_count):
                    expanded.extend(range(usage_min, usage_max + 1))
                key = (kind, report_id)
                start = cursors.get(key, 0)
                entries[kind].append({
                    'page': usage_page,
                    'report_id': report_id,
                    'size': report_size,
                    'count': report_count,
                    'bit_offset': start,
                    'usages': expanded,
                })
                cursors[key] = start + report_size * report_count
            usages = []
            usage_min = None
            usage_max = None
    return entries, cursors


def report_length(cursors, kind, report_id):
    """按描述符算该 Report ID 的报文总字节数（含 Report ID 字节）。"""
    bits = cursors.get((kind, report_id), 0)
    return (bits + 7) // 8 + (1 if report_id else 0)


def describe_entries(entries):
    for kind in ('input', 'output', 'feature'):
        for e in entries[kind]:
            usages = e['usages']
            if len(usages) > 12:
                usage_text = '%d 个 usage（0x%02X..0x%02X）' % (
                    len(usages), min(usages), max(usages))
            elif usages:
                usage_text = ', '.join('0x%02X' % u for u in usages)
            else:
                usage_text = '(无 usage/常量填充)'
            print('  %-7s page=0x%04X report_id=%-3d size=%d count=%-2d bit_offset=%-3d usages=%s'
                  % (kind, e['page'], e['report_id'], e['size'], e['count'],
                     e['bit_offset'], usage_text))


def led_bits(entries):
    """列出 LED Output 项里的 (usage, 绝对位偏移, 位宽, report_id)。"""
    result = []
    for e in entries['output']:
        if e['page'] != USAGE_PAGE_LED:
            continue
        for index in range(e['count']):
            usage = e['usages'][index] if index < len(e['usages']) else None
            result.append((usage, e['bit_offset'] + index * e['size'],
                           e['size'], e['report_id']))
    return result


def build_output(report_id, length, bits):
    """bits 为 [(绝对位偏移, 0/1)]；返回可直接 SET_REPORT 的 bytes。"""
    buf = bytearray(length)
    base = 1 if report_id else 0
    if report_id:
        buf[0] = report_id
    for bit_index, value in bits:
        byte_index = base + bit_index // 8
        mask = 1 << (bit_index % 8)
        if value:
            buf[byte_index] |= mask
        else:
            buf[byte_index] &= ~mask
    return bytes(buf)


def read_reports(dev, ep, seconds, prompt):
    size = max(profile.KEY_REPORT_LENGTH, ep.wMaxPacketSize)
    print('\n%s（%d 秒）' % (prompt, seconds))
    print('[起点] %s' % lock_state_text())
    end = time.monotonic() + seconds
    last = None
    count = 0
    total = 0
    while time.monotonic() < end:
        try:
            data = dev.read(ep.bEndpointAddress, size, timeout=200)
        except usb.core.USBError as exc:
            if (getattr(exc, 'errno', None) in (-7, 110)
                    or 'timeout' in str(exc).lower() or 'timed out' in str(exc).lower()):
                continue
            print('读取失败：%s' % exc)
            return count
        raw = bytes(data)
        total += 1
        if raw == last:                    # 设备不重发报告，只打印变化
            continue
        last = raw
        count += 1
        modifier, keys = profile.parse_key_report(raw)
        print('%s  len=%d  raw=%-24s mod=0x%02X  usages=%s  |  %s'
              % (now_str(), len(raw), hex_bytes(raw), modifier,
                 '[' + ', '.join('0x%02X' % k for k in (keys or [])) + ']',
                 lock_state_text()))
    print('[结束] 共收到 %d 份报告（%d 份内容变化）；%s'
          % (total, count, lock_state_text()))
    return count


def cmd_info(args):
    dev, intf, ep = open_keyboard()
    report_interfaces(dev)
    print('\n[键盘接口] 输入报告长度 insize=%s，端点 %s' % (
        profile.KEY_REPORT_LENGTH, _ep_text(ep)))
    desc = get_report_descriptor(dev, intf)
    if desc is None:
        return 2
    print('\n[报告描述符原始字节]（%d 字节）' % len(desc))
    for offset in range(0, len(desc), 16):
        print('  %04X  %s' % (offset, hex_bytes(desc[offset:offset + 16])))
    entries, cursors = parse_report_descriptor(desc)
    print('\n[报告描述符主项]（%d 字节）' % len(desc))
    describe_entries(entries)
    print('\n[按 Report ID 推算的报文长度]')
    ids = sorted({e['report_id'] for kind in entries for e in entries[kind]})
    for report_id in ids:
        print('  report_id=%d: input=%d 字节, output=%d 字节, feature=%d 字节' % (
            report_id,
            report_length(cursors, 'input', report_id),
            report_length(cursors, 'output', report_id),
            report_length(cursors, 'feature', report_id)))
    layout = led_bits(entries)
    print('\n[LED Output 位布局]')
    if not layout:
        print('  没有 Usage Page 0x08 的 Output 项 → 该接口不能按 LED 语义回写')
    for usage, bit, width, report_id in layout:
        if usage is None:
            continue
        name = {USAGE_NUM_LOCK: 'Num Lock', USAGE_CAPS_LOCK: 'Caps Lock',
                USAGE_SCROLL_LOCK: 'Scroll Lock'}.get(usage, 'usage 0x%02X' % usage)
        print('  %-11s bit=%-2d 宽度=%d report_id=%d' % (name, bit, width, report_id))
    usb.util.release_interface(dev, intf.bInterfaceNumber)
    return 0


def cmd_capture(args):
    dev, intf, ep = open_keyboard()
    try:
        read_reports(dev, ep, args.seconds,
                     '开始只读抓包。请按顺序操作：Num Lock → J → Num Lock → J')
    finally:
        usb.util.release_interface(dev, intf.bInterfaceNumber)
    return 0


def cmd_led(args):
    dev, intf, ep = open_keyboard()
    try:
        desc = get_report_descriptor(dev, intf)
        if desc is None:
            return 2
        entries, cursors = parse_report_descriptor(desc)
        layout = led_bits(entries)
        print('\n[LED Output 位布局]')
        for usage, bit, width, report_id in layout:
            print('  usage=0x%02X bit=%-2d 宽度=%d report_id=%d'
                  % (usage if usage is not None else 0, bit, width, report_id))
        if not layout:
            print('[结论] 描述符没有 Usage Page 0x08 的 Output 项，无法按 LED 语义回写。')
            return 2
        numlock = next((item for item in layout if item[0] == USAGE_NUM_LOCK), None)
        capslock = next((item for item in layout if item[0] == USAGE_CAPS_LOCK), None)
        if numlock is None:
            print('[结论] Output 项里没有 Num Lock 位，无法验证。')
            return 2
        report_id = numlock[3]
        length = report_length(cursors, 'output', report_id)
        out_ep = find_out_endpoint(intf)
        print('\n[写回路径] report_id=%d 报文长度=%d 字节（来自描述符）；中断 OUT 端点：%s'
              % (report_id, length, _ep_text(out_ep) if out_ep else '无'))

        def send(bits, label):
            payload = build_output(report_id, length, bits)
            print('\n%s [SET_REPORT] %s  data=%s' % (now_str(), label, hex_bytes(payload)))
            try:
                ret = dev.ctrl_transfer(0x21, 0x09, (0x02 << 8) | report_id,
                                        intf.bInterfaceNumber, payload, timeout=500)
                print('  控制传输返回：%r（返回成功 ≠ 物理灯有反应）' % (ret,))
            except Exception as exc:
                print('  控制传输失败：%s' % exc)
            if out_ep is not None:
                try:
                    written = dev.write(out_ep.bEndpointAddress, payload, timeout=500)
                    print('  中断 OUT 写入：%r 字节' % (written,))
                except Exception as exc:
                    print('  中断 OUT 写入失败：%s' % exc)
            return payload

        def hold(payload, seconds, prompt, reassert_s=0.0):
            """保持灯位不变并继续读报告，返回窗口内收到的普通键 usage 集合。

            灯亮不亮只能靠人眼看；但"写入是否落地"可以由固件行为自己回答：
            本设备按 Num Lock 灯位决定 J 上报 0x0D 还是 0x59。
            """
            size = max(profile.KEY_REPORT_LENGTH, ep.wMaxPacketSize)
            start_text = now_str()
            end_text = (datetime.datetime.now()
                        + datetime.timedelta(seconds=seconds)).strftime('%H:%M:%S.%f')[:-3]
            print('\n========== 窗口开始 %s ==========' % start_text)
            print(prompt)
            print('保持灯位 payload=%s，%d 秒，结束时间 %s，%s'
                  % (hex_bytes(payload), seconds, end_text,
                     '每 %.1f 秒重发一次' % reassert_s if reassert_s else '只写一次、不再重发'))
            print('这段时间内按下的键才计入判据；窗口开始前收到的报文已在预处理阶段丢弃。')
            print('[起点] %s' % lock_state_text())
            seen = set()
            seen_count = {}
            last = None
            total = 0
            changed = 0
            sends = 1
            start = time.monotonic()
            next_send = start + reassert_s if reassert_s else None
            while True:
                now = time.monotonic()
                if now - start >= seconds:
                    break
                if next_send is not None and now >= next_send:
                    try:
                        dev.ctrl_transfer(0x21, 0x09, (0x02 << 8) | report_id,
                                          intf.bInterfaceNumber, payload, timeout=500)
                        sends += 1
                    except Exception as exc:
                        print('  重发失败：%s' % exc)
                    next_send = now + reassert_s
                try:
                    data = dev.read(ep.bEndpointAddress, size, timeout=200)
                except usb.core.USBError as exc:
                    if (getattr(exc, 'errno', None) in (-7, 110)
                            or 'timeout' in str(exc).lower()
                            or 'timed out' in str(exc).lower()):
                        continue
                    print('读取失败：%s' % exc)
                    break
                raw = bytes(data)
                total += 1
                if raw == last:
                    continue
                last = raw
                changed += 1
                modifier, keys = profile.parse_key_report(raw)
                for key in (keys or []):
                    seen.add(key)
                    seen_count[key] = seen_count.get(key, 0) + 1
                print('  [窗口内] %s  len=%d  raw=%-24s mod=0x%02X  usages=%s  |  %s'
                      % (now_str(), len(raw), hex_bytes(raw), modifier,
                         '[' + ', '.join('0x%02X' % k for k in (keys or [])) + ']',
                         lock_state_text()))
            print('[窗口结束 %s] 读取 %d 份（变化 %d 次），灯位写入 %d 次；%s'
                  % (now_str(), total, changed, sends, lock_state_text()))
            if seen_count:
                print('[窗口内按键统计] %s' % ', '.join(
                    '0x%02X×%d' % (key, count) for key, count in sorted(seen_count.items())))
            return seen

        def drain(quiet_s=0.5, max_s=5.0):
            """丢弃端点里滞留的旧报文，避免它们混进窗口内的判据。"""
            size = max(profile.KEY_REPORT_LENGTH, ep.wMaxPacketSize)
            stale = []
            begin = time.monotonic()
            deadline = begin + quiet_s
            while time.monotonic() < deadline and time.monotonic() - begin < max_s:
                try:
                    data = dev.read(ep.bEndpointAddress, size, timeout=200)
                except usb.core.USBError as exc:
                    if (getattr(exc, 'errno', None) in (-7, 110)
                            or 'timeout' in str(exc).lower()
                            or 'timed out' in str(exc).lower()):
                        continue
                    print('[预处理] 读取失败：%s' % exc)
                    break
                stale.append(bytes(data))
                deadline = time.monotonic() + quiet_s
            if stale:
                print('[预处理] 丢弃 %d 份滞留旧报文（不计入判据）：%s'
                      % (len(stale), ' / '.join(hex_bytes(b) for b in stale)))
            else:
                print('[预处理] 端点无滞留报文。')

        drain()
        num_payload = send([(numlock[1], 1)], 'Num Lock 位 = 1（保持，请看一眼物理灯）')
        seen = hold(num_payload, args.seconds,
                    '保持 Num Lock 灯位=1：请看物理灯，并在窗口内至少按 5 次 J（间隔一两秒）',
                    args.reassert)
        if 0x59 in seen:
            print('[判定] 窗口内 J 上报 0x59：灯位写入已落地，固件按 Num Lock 灯位切层'
                  '（若此时物理灯不亮，说明灯的点亮条件另有约束，与切层无关）。')
        elif 0x0D in seen:
            print('[判定] 窗口内 J 全部上报 0x0D：灯位写入未落地（被覆盖或被固件忽略）。')
        else:
            print('[判定] 窗口内没有收到 J 报文，无法判定；请重跑并在此期间按 J。')

        zero_payload = send([(numlock[1], 0)], 'Num Lock 位 = 0（请再看一眼物理灯是否熄灭）')
        hold(zero_payload, min(5, args.seconds), '灯位回 0 后短暂保持（观察是否熄灭）')

        if capslock is not None and not args.num_only:
            caps_payload = send([(capslock[1], 1)], 'Caps Lock 位 = 1（保持）')
            seen_caps = hold(caps_payload, args.seconds,
                             '保持 Caps Lock 灯位=1：本键盘只有 Num Lock 一颗灯，'
                             '该位没有肉眼可验证的反馈，这里只测它是否影响切层',
                             args.reassert)
            if 0x59 in seen_caps:
                print('[判定] Caps 位=1 时 J 上报了 0x59，说明该位也参与切层（与预期不同）。')
            elif 0x0D in seen_caps:
                print('[判定] Caps 位=1 时 J 仍上报 0x0D：切层只由 Num Lock 位驱动，符合预期。')
            else:
                print('[判定] 窗口内没有按 J，Caps 位是否影响切层无法判断。')
            print('[提示] 本键盘没有 Caps 指示灯，写 bit1 无法用肉眼验证；'
                  '控制传输返回值只说明报文被接受，不能当作灯亮的证据。')
            caps_zero = send([(capslock[1], 0)], 'Caps Lock 位 = 0（复原）')
            hold(caps_zero, min(5, args.seconds), '灯位回 0 后短暂保持')

        print('\n[提示] 结论以“用户看到的灯亮/灭”为准；控制传输返回成功只说明报文被接受，'
              '不能单独当作灯亮的证据。实测：1 字节、report_id=0 的 Output 报告能正常驱动指示灯，'
              '早期“不可控”的结论来自错误的 2–3 字节裸包。')
        return 0
    finally:
        usb.util.release_interface(dev, intf.bInterfaceNumber)


def main():
    parser = argparse.ArgumentParser(description='原生语义判定实验（只读，不注入按键）')
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('info', help='打印报告描述符里的 Input/Output 主项与 LED 位布局')
    p_cap = sub.add_parser('capture', help='只读抓取键盘原始报告')
    p_cap.add_argument('--seconds', type=int, default=30)
    p_led = sub.add_parser('led', help='按描述符写 LED Output 报告并继续读报告')
    p_led.add_argument('--seconds', type=int, default=8)
    p_led.add_argument('--reassert', type=float, default=0.0,
                       help='保持期间每隔 N 秒重发一次灯位（0 = 只写一次）')
    p_led.add_argument('--num-only', action='store_true',
                       help='只测 Num Lock 灯位，跳过 Caps 位')
    args = parser.parse_args()
    if args.command == 'info':
        return cmd_info(args)
    if args.command == 'capture':
        return cmd_capture(args)
    if args.command == 'led':
        return cmd_led(args)
    parser.print_help()
    return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n已中断。')
        sys.exit(130)
