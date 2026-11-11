# -*- coding: utf-8 -*-
"""probe_keyboard.py —— HID 集合层诊断（设备身份取自 device_profile 包）

只回答一个问题：这台机器上的 HID 接口各自暴露了哪些集合、端点、包长与 Report ID，
以及当前进程能不能以读权限打开它们。不做设备/驱动绑定判读（那是
``enum_usb_nodes.py``），不做按键语义判定（那是 ``calibrate``）。

独立脚本：只依赖 Python 标准库、ctypes（setupapi / hid.dll / kernel32）
与本仓库的 keyboard_driver\\device_profile\\identity.py（仅取 VID/PID），不使用 pyusb，不需要 Zadig，
不替换系统驱动，也不会独占键盘。

用法（建议在目标机上以管理员身份打开命令提示符）：
    python probe_keyboard.py            # 默认：只处理 VID/PID 匹配的集合 + 抓包
    python probe_keyboard.py --enum     # 只枚举与自检，不抓包
    python probe_keyboard.py --all      # 全量诊断：列出系统所有 HID 集合（不按 VID/PID 过滤）
退出抓包：在控制台按 q，或按 Ctrl+C。

边界：
    * 设备节点与驱动绑定（WinUSB/HidUsb/usbccgp、问题码、Zadig 条数）
      → ``enum_usb_nodes.py``（``--classes`` 保留原来的键盘/鼠标/HID 类列表）。
    * 键盘集合被系统驱动独占、读不到原始报告时，本脚本不再装键盘钩子；
      要看系统最终收到的按键，用 ``compare_native.py record``。
    * WinUSB 绑定下的描述符原文与 LED 实验 → ``native_probe.py``。
"""

import ctypes
import os
import struct
import sys
import time
import datetime
import platform
import threading
import traceback
from ctypes import wintypes

# 本文件位于 tools/：从 keyboard_driver/device_profile 包读取设备身份，避免在诊断脚本里重复硬编码
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from keyboard_driver.device_profile import VID, PID, NAME as DEVICE_NAME

GENERIC_READ = 0x80000000
FILE_SHARE_READ_WRITE = 0x00000003
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10

HIDP_STATUS_SUCCESS = 0x00110000
HIDP_INPUT = 0
HIDP_OUTPUT = 1

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
setupapi = ctypes.WinDLL('setupapi', use_last_error=True)
hid = ctypes.WinDLL('hid', use_last_error=True)


# ---------------- 结构体定义 ----------------
class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


GUID_DEVINTERFACE_HID = GUID(
    0x4D1E55B2, 0xF16F, 0x11CF,
    (ctypes.c_ubyte * 8)(0x88, 0xCB, 0x00, 0x11, 0x11, 0x00, 0x00, 0x30))


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("InterfaceClassGuid", GUID),
                ("Flags", wintypes.DWORD),
                ("Reserved", ctypes.c_void_p)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", wintypes.DWORD),
                ("VendorID", ctypes.c_ushort),
                ("ProductID", ctypes.c_ushort),
                ("VersionNumber", ctypes.c_ushort)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", ctypes.c_ushort),
                ("UsagePage", ctypes.c_ushort),
                ("InputReportByteLength", ctypes.c_ushort),
                ("OutputReportByteLength", ctypes.c_ushort),
                ("FeatureReportByteLength", ctypes.c_ushort),
                ("Reserved", ctypes.c_ushort * 17),
                ("NumberLinkCollectionNodes", ctypes.c_ushort),
                ("NumberInputButtonCaps", ctypes.c_ushort),
                ("NumberInputValueCaps", ctypes.c_ushort),
                ("NumberInputDataIndices", ctypes.c_ushort),
                ("NumberOutputButtonCaps", ctypes.c_ushort),
                ("NumberOutputValueCaps", ctypes.c_ushort),
                ("NumberOutputDataIndices", ctypes.c_ushort),
                ("NumberFeatureButtonCaps", ctypes.c_ushort),
                ("NumberFeatureValueCaps", ctypes.c_ushort),
                ("NumberFeatureDataIndices", ctypes.c_ushort)]


# 注意：真实布局里 Reserved 是 9 个 ULONG（36 字节），union 位于偏移 56，总长 72。
# 这里把 union 展开成等宽的扁平字段，只读取我们需要的 usage / 数据索引。
class HIDP_BUTTON_CAPS(ctypes.Structure):
    _fields_ = [("UsagePage", ctypes.c_ushort),
                ("ReportID", ctypes.c_ubyte),
                ("IsAlias", ctypes.c_ubyte),
                ("BitField", ctypes.c_ushort),
                ("LinkCollection", ctypes.c_ushort),
                ("LinkUsage", ctypes.c_ushort),
                ("LinkUsagePage", ctypes.c_ushort),
                ("IsRange", ctypes.c_ubyte),
                ("IsStringRange", ctypes.c_ubyte),
                ("IsDesignatorRange", ctypes.c_ubyte),
                ("IsAbsolute", ctypes.c_ubyte),
                ("ReportCount", ctypes.c_ushort),
                ("Reserved2", ctypes.c_ushort),
                ("Reserved", ctypes.c_ulong * 9),
                ("UsageMin", ctypes.c_ushort),
                ("UsageMax", ctypes.c_ushort),
                ("StringMin", ctypes.c_ushort),
                ("StringMax", ctypes.c_ushort),
                ("DesignatorMin", ctypes.c_ushort),
                ("DesignatorMax", ctypes.c_ushort),
                ("DataIndexMin", ctypes.c_ushort),
                ("DataIndexMax", ctypes.c_ushort)]


# ---------------- 原型声明 ----------------
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]

setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), ctypes.c_wchar_p,
                                          wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                                 ctypes.POINTER(GUID), wintypes.DWORD,
                                                 ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [wintypes.HANDLE,
                                                      ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                                                      ctypes.c_void_p, wintypes.DWORD,
                                                      ctypes.POINTER(wintypes.DWORD),
                                                      ctypes.c_void_p]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]

hid.HidD_GetAttributes.restype = wintypes.BOOL
hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetPreparsedData.restype = wintypes.BOOL
hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidD_GetProductString.restype = wintypes.BOOL
hid.HidD_GetProductString.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
hid.HidP_GetCaps.restype = ctypes.c_long
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetButtonCaps.restype = ctypes.c_long
hid.HidP_GetButtonCaps.argtypes = [ctypes.c_int, ctypes.POINTER(HIDP_BUTTON_CAPS),
                                   ctypes.POINTER(ctypes.c_ushort), ctypes.c_void_p]


# ---------------- 工具函数 ----------------
def now_str():
    return datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        traceback.print_exc()
        return False


def open_device(path, access):
    """打开 HID 集合；返回 (句柄, 错误码)，句柄无效时错误码有效"""
    ctypes.set_last_error(0)
    h = kernel32.CreateFileW(path, access, FILE_SHARE_READ_WRITE,
                             None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE or h is None:
        return None, ctypes.get_last_error()
    return h, 0


def hex_bytes(data):
    return ' '.join('%02X' % b for b in data)


_USAGE_NAMES = {
    (0x01, 0x02): '鼠标',
    (0x01, 0x06): '键盘',
    (0x01, 0x80): '系统控制',
    (0x0C, 0x01): '消费类',
}


def collection_label(page, usage, index):
    name = _USAGE_NAMES.get((page, usage))
    if name:
        return '#%d %s' % (index, name)
    return '#%d %04X:%04X' % (index, page, usage)


def read_button_caps(preparsed, report_type, count):
    """读取按钮 caps 原文，返回可打印的文本行"""
    if not count:
        return []
    arr = (HIDP_BUTTON_CAPS * count)()
    used = ctypes.c_ushort(count)
    status = hid.HidP_GetButtonCaps(report_type, arr, ctypes.byref(used), preparsed)
    if status != HIDP_STATUS_SUCCESS:
        return ['    读取按钮 caps 失败 0x%08X' % (status & 0xFFFFFFFF)]
    lines = []
    for i in range(used.value):
        c = arr[i]
        rid = ('0x%02X' % c.ReportID) if c.ReportID else '无'
        kind = '位图' if c.BitField else '数组'
        if c.IsRange:
            rng = '0x%04X..0x%04X（数据索引 %d..%d）' % (
                c.UsageMin, c.UsageMax, c.DataIndexMin, c.DataIndexMax)
        else:
            rng = '0x%04X（数据索引 %d）' % (c.UsageMin, c.DataIndexMin)
        lines.append('    按钮集 %d: ReportID=%s 类型=%s 数量=%d usage %04X:%s' % (
            i, rid, kind, c.ReportCount, c.UsagePage, rng))
    return lines


def query_collection(path, index):
    """读取单个 HID 集合的静态信息。任何失败都记录在返回的 dict 里，不再静默跳过"""
    info = {'index': index, 'path': path, 'vid': None, 'pid': None}
    h = None
    try:
        h, err = open_device(path, 0)          # 0 访问权限即可读属性/预解析数据
        if h is None:
            info['open0_err'] = err
            return info
        attrs = HIDD_ATTRIBUTES()
        attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
        if not hid.HidD_GetAttributes(h, ctypes.byref(attrs)):
            info['attr_err'] = ctypes.get_last_error()
            return info
        info['vid'] = attrs.VendorID
        info['pid'] = attrs.ProductID
        info['version'] = attrs.VersionNumber
        buf = ctypes.create_unicode_buffer(128)
        if hid.HidD_GetProductString(h, buf, ctypes.sizeof(buf)):
            info['product'] = buf.value

        preparsed = ctypes.c_void_p()
        if not hid.HidD_GetPreparsedData(h, ctypes.byref(preparsed)):
            info['preparsed_err'] = ctypes.get_last_error()
            return info
        try:
            caps = HIDP_CAPS()
            status = hid.HidP_GetCaps(preparsed, ctypes.byref(caps))
            if status != HIDP_STATUS_SUCCESS:
                info['caps_err'] = status
                return info
            info['usage_page'] = caps.UsagePage
            info['usage'] = caps.Usage
            info['in_len'] = caps.InputReportByteLength
            info['out_len'] = caps.OutputReportByteLength
            info['feat_len'] = caps.FeatureReportByteLength
            info['in_btn_count'] = caps.NumberInputButtonCaps
            info['out_btn_count'] = caps.NumberOutputButtonCaps
            info['in_btn_lines'] = read_button_caps(preparsed, HIDP_INPUT,
                                                    caps.NumberInputButtonCaps)
            info['out_btn_lines'] = read_button_caps(preparsed, HIDP_OUTPUT,
                                                     caps.NumberOutputButtonCaps)
        finally:
            hid.HidD_FreePreparsedData(preparsed)
        return info
    except Exception:
        info['exception'] = True
        print('  [异常] 处理接口失败，调用栈如下（路径 %s）：' % path)
        traceback.print_exc()
        return info
    finally:
        if h is not None:
            kernel32.CloseHandle(h)


def get_interface_path(dev_info, did):
    """取设备接口路径。不同系统/位数对 cbSize 的期望值不一致，这里逐个尝试并返回最后一次错误码"""
    ptr_size = struct.calcsize('P')
    sizes = []
    for s in ((8 if ptr_size == 8 else 6), 8, 6, 4 + ptr_size):
        if s not in sizes:
            sizes.append(s)
    last_err = 0
    for size in sizes:
        buf = ctypes.create_string_buffer(1024)
        ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0] = size
        need = wintypes.DWORD(0)
        ctypes.set_last_error(0)
        if setupapi.SetupDiGetDeviceInterfaceDetailW(dev_info, ctypes.byref(did), buf, 1024,
                                                     ctypes.byref(need), None):
            return ctypes.wstring_at(ctypes.addressof(buf) + 4), 0
        last_err = ctypes.get_last_error() or last_err
    return None, last_err


def collect_interfaces():
    """枚举全部 HID 设备接口（不做 VID/PID 过滤），返回 (info 列表, 统计)"""
    stats = {'devs_err': 0, 'enumerated': 0, 'detail_err': 0}
    infos = []
    ctypes.set_last_error(0)
    dev_info = setupapi.SetupDiGetClassDevsW(ctypes.byref(GUID_DEVINTERFACE_HID),
                                             None, None,
                                             DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if dev_info == INVALID_HANDLE_VALUE or dev_info is None:
        stats['devs_err'] = ctypes.get_last_error()
        return infos, stats
    try:
        n = 0
        while True:
            did = SP_DEVICE_INTERFACE_DATA()
            did.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            ctypes.set_last_error(0)
            if not setupapi.SetupDiEnumDeviceInterfaces(
                    dev_info, None, ctypes.byref(GUID_DEVINTERFACE_HID), n,
                    ctypes.byref(did)):
                err = ctypes.get_last_error()
                if err not in (0, 259):        # 259 = ERROR_NO_MORE_ITEMS
                    print('  [枚举] 第 %d 个接口枚举失败 err=%d' % (n, err))
                    stats['enum_err'] = err
                break
            n += 1
            stats['enumerated'] += 1
            path, err = get_interface_path(dev_info, did)
            if path is None:
                stats['detail_err'] += 1
                print('  [枚举] 第 %d 个接口取路径失败 err=%d' % (n - 1, err))
                continue
            infos.append(query_collection(path, len(infos)))
    except Exception:
        stats['exception'] = True
        print('  [异常] 枚举过程中出错：')
        traceback.print_exc()
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(dev_info)
    return infos, stats


def print_stats(stats, infos):
    print('\n---------- 枚举统计 ----------')
    if stats.get('devs_err'):
        print('  SetupDiGetClassDevs(GUID_DEVINTERFACE_HID): 失败 err=%d' % stats['devs_err'])
    else:
        print('  SetupDiGetClassDevs(GUID_DEVINTERFACE_HID): 成功')
    print('  SetupDiEnumDeviceInterfaces 枚举到设备接口: %d 个' % stats.get('enumerated', 0))
    print('  其中取设备路径失败: %d 个（err 见上方）' % stats.get('detail_err', 0))
    open_err = sum(1 for i in infos if i.get('open0_err'))
    attr_err = sum(1 for i in infos if i.get('attr_err'))
    caps_err = sum(1 for i in infos if i.get('preparsed_err') or i.get('caps_err'))
    exc = sum(1 for i in infos if i.get('exception'))
    matched = sum(1 for i in infos if i.get('vid') == VID and i.get('pid') == PID)
    same_vid = sum(1 for i in infos if i.get('vid') == VID)
    print('  0 权限打开失败: %d 个' % open_err)
    print('  HidD_GetAttributes 失败: %d 个' % attr_err)
    print('  HidD_GetPreparsedData/HidP_GetCaps 失败: %d 个' % caps_err)
    print('  处理异常: %d 个（调用栈见上方）' % exc)
    print('  VID=0x%04X 的集合: %d 个；其中 PID=0x%04X 的: %d 个' % (
        VID, same_vid, PID, matched))


def print_collection_info(info, show_path=True):
    head = '  [%d]' % info['index']
    vid = info.get('vid')
    pid = info.get('pid')
    if vid is not None:
        head += ' VID:PID=%04X:%04X' % (vid, pid)
    if info.get('product'):
        head += ' “%s”' % info['product']
    print(head)
    if show_path:
        print('      路径: %s' % info['path'])
    if info.get('open0_err'):
        print('      0 权限打开失败 err=%d' % info['open0_err'])
        return
    if info.get('attr_err'):
        print('      HidD_GetAttributes 失败 err=%d（读不到 VID/PID）' % info['attr_err'])
        return
    if info.get('preparsed_err') or info.get('caps_err'):
        print('      读取 caps 失败 preparsed_err=%s caps_err=0x%08X' % (
            info.get('preparsed_err'), (info.get('caps_err') or 0) & 0xFFFFFFFF))
        return
    page = info.get('usage_page', 0)
    usage = info.get('usage', 0)
    print('      Usage Page/Usage: %04X / %04X（%s）' % (
        page, usage, _USAGE_NAMES.get((page, usage), '其它/厂商自定义')))
    print('      输入报告 %d 字节，输出报告 %d 字节，Feature %d 字节' % (
        info.get('in_len', 0), info.get('out_len', 0), info.get('feat_len', 0)))
    print('      Report ID: %s' % ('存在（按 ID 区分报告）' if _has_report_id(info)
                                  else '无（报告首字节即数据）'))
    print('      NumberInputButtonCaps = %d，NumberOutputButtonCaps = %d' % (
        info.get('in_btn_count', 0), info.get('out_btn_count', 0)))
    for line in info.get('in_btn_lines', []):
        print(line)
    for line in info.get('out_btn_lines', []):
        print(line)


def _has_report_id(info):
    """从按钮 caps 文本里判断是否带 Report ID（有非 0 的 ReportID 即为带）"""
    for line in info.get('in_btn_lines', []) + info.get('out_btn_lines', []):
        if 'ReportID=0x' in line:
            return True
    return False


# ---------------- 抓包 ----------------
def reader_worker(info, stop_event):
    label = collection_label(info.get('usage_page', 0), info.get('usage', 0), info['index'])
    size = max(1, info.get('in_len', 0))
    h, err = open_device(info['path'], GENERIC_READ)
    if h is None:
        print('[%s] 以读权限打开失败 err=%d，该接口不抓包' % (label, err), flush=True)
        return
    buf = (ctypes.c_ubyte * size)()
    last = None
    try:
        while not stop_event.is_set():
            n = wintypes.DWORD(0)
            if not kernel32.ReadFile(h, buf, size, ctypes.byref(n), None):
                e = ctypes.get_last_error()
                if e not in (22, 1167, 1168, 1450):     # 设备拔出等正常结束
                    print('[%s] 读取失败 err=%d，该接口停止抓包' % (label, e), flush=True)
                break
            data = bytes(bytearray(buf[:n.value]))
            if data != last:                            # 只在内容变化时打印，避免刷屏
                print('%s [%s] %s' % (now_str(), label, hex_bytes(data)), flush=True)
                last = data
    finally:
        kernel32.CloseHandle(h)


# ---------------- 主流程 ----------------
def print_header():
    print('=' * 62)
    print('USB 无线键盘诊断  %s（VID:PID = %04X:%04X）' % (DEVICE_NAME, VID, PID))
    print('系统: %s' % platform.platform())
    print('Python: %s（%d 位，ctypes 指针 %d 字节）' % (
        platform.python_version(), struct.calcsize('P') * 8, struct.calcsize('P')))
    print('管理员权限: %s' % ('是' if is_admin() else '否（部分集合可能无法打开）'))
    print('模式: %s' % ('全量诊断(--all)' if '--all' in sys.argv
                       else ('仅枚举(--enum)' if '--enum' in sys.argv else '默认')))
    print('=' * 62)


def main():
    all_mode = '--all' in sys.argv
    enum_only = '--enum' in sys.argv

    print_header()

    infos, stats = collect_interfaces()
    print_stats(stats, infos)

    if all_mode:
        print('\n---------- 全部 HID 集合（共 %d 个） ----------' % len(infos))
        for info in infos:
            print_collection_info(info)
        same_vid = [i for i in infos if i.get('vid') == VID]
        print('\n---------- VID=0x%04X 的集合（不限 PID，共 %d 个） ----------' % (VID, len(same_vid)))
        if not same_vid:
            print('  没有 VID=0x%04X 的 HID 集合：设备可能未被 HID 驱动接管，'
                  '或实际 VID 与之不同（见下面的设备列表）。' % VID)
        else:
            for info in same_vid:
                print_collection_info(info)
        print('\n设备节点与驱动绑定（WinUSB/HidUsb/usbccgp、问题码）请运行：')
        print('  python tools\\enum_usb_nodes.py --classes')
        print('\n全量诊断结束。')
        return 0

    matched = [i for i in infos if i.get('vid') == VID and i.get('pid') == PID]
    if not matched:
        print('\n未找到匹配的 HID 集合（VID=%04X PID=%04X）。' % (VID, PID))
        print('下面是系统实际的枚举结果，用于判断设备到底被枚举成了什么：')
        if infos:
            print('\n---------- 全部 HID 集合 ----------')
            for info in infos:
                print_collection_info(info)
        else:
            print('\n（HID 接口枚举结果为 0，请看上面的枚举统计定位是哪一步）')
        print('\n设备节点与驱动绑定（WinUSB/HidUsb/usbccgp、问题码）请运行：')
        print('  python tools\\enum_usb_nodes.py --classes')
        print('\n建议：先运行 probe_keyboard.py --all 获取完整 HID 集合清单。')
        return 1

    print('\n---------- 匹配 VID/PID 的 HID 集合（共 %d 个） ----------' % len(matched))
    for info in matched:
        print_collection_info(info)

    # ---- 自检：能否以读权限打开（区分“权限不足”和“驱动独占”） ----
    print('\n---------- 自检：读权限打开结果 ----------')
    readable = []
    for info in matched:
        label = collection_label(info.get('usage_page', 0), info.get('usage', 0), info['index'])
        h, err = open_device(info['path'], GENERIC_READ)
        if h is None:
            print('  [%s] 读权限打开失败 err=%d（%s）' % (
                label, err,
                '通常是系统驱动独占，属正常现象' if err == 5 else '请检查权限'))
        else:
            kernel32.CloseHandle(h)
            print('  [%s] 读权限打开成功' % label)
            readable.append(info)
    keyboard_readable = any(i.get('usage_page') == 0x01 and i.get('usage') == 0x06
                            and i.get('in_len', 0) > 0 for i in readable)
    print('  => 可抓包接口 %d/%d，键盘集合原始报告%s' % (
        len(readable), len(matched), '可读' if keyboard_readable else '不可读'))

    if enum_only:
        print('\n仅枚举模式（--enum），结束。')
        return 0

    # ---- 抓包 ----
    stop_event = threading.Event()
    for info in readable:
        if not info.get('in_len'):
            continue
        t = threading.Thread(target=reader_worker, args=(info, stop_event), daemon=True)
        t.start()

    if not keyboard_readable:
        print('提示: 键盘集合被系统驱动独占，读不到原始报告。')
        print('      要看系统最终收到的按键（VK 序列、注入标记、重复节奏），请另开窗口运行：')
        print('        python tools\\compare_native.py record --out native.jsonl --label 原生')

    print('\n开始抓包，请在键盘上操作。按 q 或 Ctrl+C 结束。\n')
    try:
        import msvcrt
        while not stop_event.is_set():
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch in (b'q', b'Q', b'\x03'):
                    break
            time.sleep(0.02)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop_event.set()
        print('\n抓包结束。')

    return 0


if __name__ == '__main__':
    sys.exit(main())
