# -*- coding: utf-8 -*-
"""enum_usb_nodes.py —— 只读枚举指定 VID/PID 的 USB 设备节点（父设备 + 复合设备各接口）

用途：确认一台机器上 MI_00 / MI_01 两个接口节点是否存在、各自绑定到哪个驱动，
      从而解释「Zadig 列表只显示一条，但 pyusb 实际能用两个接口」这类展示差异。
      （已知在 Win7 上 python 方式运行驱动正常，说明系统层两个接口可用；
        Zadig 的条目数取决于它列出的单位与过滤规则，不一定等于接口数。）

只依赖 Python 标准库 + ctypes（setupapi / cfgmgr32），不需要 pyusb、pywin32；
全部是只读查询，不安装、不修改、不重绑任何驱动。Python 3.x（32/64 位）均可运行。

用法：
    python enum_usb_nodes.py                  # VID/PID 默认取自 src\\device_profile\\identity.py
    python enum_usb_nodes.py --vid <HEX> --pid <HEX>
    python enum_usb_nodes.py --all-nodes      # 打印枚举到的全部 USB 节点（可能很长）
    python enum_usb_nodes.py --sample 5       # 自检时列出的示例节点个数（默认 3）

判读要点：
  * 本脚本看到的是 Windows 的「设备节点（devnode）」：复合设备由 usbccgp.sys
    为每个接口各建一个子节点，实例 ID 形如 USB\\VID_xxxx&PID_xxxx&MI_01\\...
    父节点实例 ID 形如 USB\\VID_xxxx&PID_xxxx\\...
  * Zadig（libwdi）用同一个 USB 枚举器列条目，但过滤规则不同：未勾
    "List All Devices" 时跳过带驱动键（SPDRP_DRIVER）的节点；勾上后不再按驱动
    过滤，但仍会跳过 USB hub 与 service=usbccgp 的复合父节点（除非再开 Include Hubs）。
  * 所以条目数 != 接口数：整设备被 WinUSB 接管时只有 1 个父节点（Zadig 1 条，
    但该设备仍可带多个接口）；逐接口绑定时每个 MI_xx 各 1 条。要判断属于哪种，
    看本脚本输出的节点列表与 service 即可。
"""

import argparse
import ctypes
import datetime
import os
import platform
import re
import sys
from ctypes import wintypes


def profile_defaults():
    """从 src\\device_profile\\identity.py 读取默认 VID/PID（避免在通用工具里重复硬编码）"""
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')
    sys.path.insert(0, src_dir)
    from device_profile import VID, PID
    return '%04X' % VID, '%04X' % PID

DIGCF_PRESENT = 0x02
DIGCF_ALLCLASSES = 0x04

SPDRP_DEVICEDESC = 0x00
SPDRP_HARDWAREID = 0x01
SPDRP_COMPATIBLEIDS = 0x02
SPDRP_SERVICE = 0x04
SPDRP_CLASS = 0x07
SPDRP_DRIVER = 0x09
SPDRP_LOCATION_INFORMATION = 0x0D

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

setupapi = ctypes.WinDLL('setupapi', use_last_error=True)
cfgmgr32 = ctypes.WinDLL('cfgmgr32', use_last_error=True)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("ClassGuid", GUID),
                ("DevInst", wintypes.DWORD),
                ("Reserved", ctypes.c_void_p)]


setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), ctypes.c_wchar_p,
                                         wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
setupapi.SetupDiEnumDeviceInfo.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                           ctypes.POINTER(SP_DEVINFO_DATA)]
setupapi.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [wintypes.HANDLE,
                                                 ctypes.POINTER(SP_DEVINFO_DATA),
                                                 ctypes.c_wchar_p, wintypes.DWORD,
                                                 ctypes.POINTER(wintypes.DWORD)]
setupapi.SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [wintypes.HANDLE,
                                                       ctypes.POINTER(SP_DEVINFO_DATA),
                                                       wintypes.DWORD,
                                                       ctypes.POINTER(wintypes.DWORD),
                                                       ctypes.c_void_p, wintypes.DWORD,
                                                       ctypes.POINTER(wintypes.DWORD)]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]

cfgmgr32.CM_Get_DevNode_Status.restype = ctypes.c_ulong
cfgmgr32.CM_Get_DevNode_Status.argtypes = [ctypes.POINTER(wintypes.DWORD),
                                           ctypes.POINTER(wintypes.DWORD),
                                           wintypes.DWORD, wintypes.DWORD]
cfgmgr32.CM_Get_Parent.restype = ctypes.c_ulong
cfgmgr32.CM_Get_Parent.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
                                   wintypes.DWORD]
cfgmgr32.CM_Get_Device_IDW.restype = ctypes.c_ulong
cfgmgr32.CM_Get_Device_IDW.argtypes = [wintypes.DWORD, ctypes.c_wchar_p,
                                       wintypes.DWORD, wintypes.DWORD]

# 常见问题码（CM_Get_DevNode_Status 的 problem number）
PROBLEM_TEXT = {
    0: '无问题',
    1: '未配置（设备未安装驱动前常见）',
    3: '驱动未加载',
    10: '无法启动（Code 10）',
    12: '资源不足/未配置',
    14: '需要重启',
    18: '需要重新安装驱动',
    19: '注册表配置失败',
    21: '系统将删除设备',
    22: '已禁用',
    24: '设备不存在',
    28: '未安装驱动（Code 28）',
    31: '无法加载所需驱动（Code 31）',
    39: '驱动损坏或缺失（Code 39）',
    43: '设备报告故障（Code 43）',
    45: '设备未连接',
}

# 状态位（cfgmgr32.h）
STATUS_FLAGS = [
    (0x00000001, 'DN_ROOT_ENUMERATED'),
    (0x00000002, 'DN_DRIVER_LOADED'),
    (0x00000004, 'DN_ENUM_LOADED'),
    (0x00000008, 'DN_STARTED'),
    (0x00000010, 'DN_MANUAL'),
    (0x00000020, 'DN_NEED_TO_ENUM'),
    (0x00000040, 'DN_NOT_FIRST_TIME'),
    (0x00000080, 'DN_HARDWARE_ENUM'),
    (0x00000100, 'DN_LIAR'),
    (0x00000200, 'DN_HAS_MARK'),
    (0x00000400, 'DN_HAS_PROBLEM'),
    (0x00000800, 'DN_FILTERED'),
    (0x00001000, 'DN_MOVED'),
    (0x00002000, 'DN_DISABLEABLE'),
    (0x00004000, 'DN_REMOVABLE'),
    (0x00008000, 'DN_PRIVATE_PROBLEM'),
    (0x00010000, 'DN_MF_PARENT'),
    (0x00020000, 'DN_MF_CHILD'),
    (0x00040000, 'DN_WILL_BE_REMOVED'),
]


def get_instance_id(devs, did):
    buf = ctypes.create_unicode_buffer(1024)
    need = wintypes.DWORD(0)
    if setupapi.SetupDiGetDeviceInstanceIdW(devs, ctypes.byref(did), buf, 1024,
                                            ctypes.byref(need)):
        return buf.value
    return None


def get_prop_multi(devs, did, prop):
    """读取 REG_MULTI_SZ 类型的注册表属性（HardwareID / CompatibleIDs）"""
    buf = ctypes.create_string_buffer(4096)
    need = wintypes.DWORD(0)
    typ = wintypes.DWORD(0)
    if not setupapi.SetupDiGetDeviceRegistryPropertyW(devs, ctypes.byref(did), prop,
                                                      ctypes.byref(typ), buf, 4096,
                                                      ctypes.byref(need)):
        return []
    data = bytes(bytearray(buf[:need.value]))
    return [p for p in data.decode('utf-16-le', 'ignore').split('\x00') if p]


def get_prop_text(devs, did, prop):
    parts = get_prop_multi(devs, did, prop)
    return parts[0] if parts else None


def get_status(devinst):
    status = wintypes.DWORD(0)
    problem = wintypes.DWORD(0)
    cr = cfgmgr32.CM_Get_DevNode_Status(ctypes.byref(status), ctypes.byref(problem),
                                        devinst, 0)
    if cr != 0:
        return None, None, cr
    return status.value, problem.value, 0


def status_text(status, problem):
    names = [name for bit, name in STATUS_FLAGS if status & bit]
    text = 'status=0x%08X(%s)' % (status, '|'.join(names) if names else '无标志')
    text += ' problem=%d(%s)' % (problem, PROBLEM_TEXT.get(problem, '未知'))
    return text


def get_parent_instance(devinst):
    parent = wintypes.DWORD(0)
    if cfgmgr32.CM_Get_Parent(ctypes.byref(parent), devinst, 0) != 0:
        return None
    buf = ctypes.create_unicode_buffer(1024)
    if cfgmgr32.CM_Get_Device_IDW(parent.value, buf, 1024, 0) != 0:
        return None
    return buf.value


def collect(flags):
    """用 SetupAPI 枚举 USB 枚举器下的设备节点，返回记录列表"""
    devs = setupapi.SetupDiGetClassDevsW(None, 'USB', None, flags | DIGCF_ALLCLASSES)
    if not devs or devs == INVALID_HANDLE_VALUE:
        return None
    records = []
    try:
        index = 0
        while True:
            did = SP_DEVINFO_DATA()
            did.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
            if not setupapi.SetupDiEnumDeviceInfo(devs, index, ctypes.byref(did)):
                break
            index += 1
            instance = get_instance_id(devs, did)
            if not instance:
                continue
            records.append({
                'instance': instance,
                'devinst': did.DevInst,
                'desc': get_prop_text(devs, did, SPDRP_DEVICEDESC),
                'service': get_prop_text(devs, did, SPDRP_SERVICE),
                'cls': get_prop_text(devs, did, SPDRP_CLASS),
                'driver_key': get_prop_text(devs, did, SPDRP_DRIVER),
                'hwids': get_prop_multi(devs, did, SPDRP_HARDWAREID),
                'compat': get_prop_multi(devs, did, SPDRP_COMPATIBLEIDS),
                'location': get_prop_text(devs, did, SPDRP_LOCATION_INFORMATION),
            })
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(devs)
    return records


def mi_of(instance):
    m = re.search(r'&MI_([0-9A-Fa-f]{2})', instance)
    return int(m.group(1), 16) if m else None


def is_match(instance, vid, pid):
    upper = instance.upper()
    return ('VID_%04X' % vid) in upper and ('PID_%04X' % pid) in upper


def brief(rec):
    mi = mi_of(rec['instance'])
    return 'MI_%02d' % mi if mi is not None else '父节点'


def print_node(rec, present):
    status, problem, cr = get_status(rec['devinst'])
    print('[%s] %s' % (brief(rec), rec['instance']))
    if cr == 0:
        state_text = status_text(status, problem)
    elif not present:
        state_text = ('非 present，节点已不在场（CM_Get_DevNode_Status CR=0x%X，'
                      'CR_NO_SUCH_DEVNODE 属预期）' % cr)
    else:
        state_text = 'CM_Get_DevNode_Status 失败 CR=0x%X' % cr
    print('    present=%s  状态=%s' % (
        '是' if present else '否（残留/非 present 记录）', state_text))
    print('    描述=%s  类=%s' % (rec['desc'] or '(无)', rec['cls'] or '(无)'))
    print('    服务(SPDRP_SERVICE)=%s' % (rec['service'] or '(无)'))
    print('    驱动键(SPDRP_DRIVER)=%s' % (rec['driver_key'] or '(无)'))
    if rec['hwids']:
        print('    HardwareID=%s' % ' | '.join(rec['hwids'][:4]))
    if rec['compat']:
        print('    CompatibleID=%s' % ' | '.join(rec['compat'][:4]))
    if rec['location']:
        print('    位置=%s' % rec['location'])
    parent = get_parent_instance(rec['devinst'])
    if parent:
        print('    父节点=%s' % parent)


def classify(rec, present):
    """返回三种状态之一：bound / present_unbound / absent"""
    if not present:
        return 'absent'
    status, problem, cr = get_status(rec['devinst'])
    if cr != 0:
        return 'present_unbound'
    if rec['service'] and problem == 0:
        return 'bound'
    return 'present_unbound'


def main():
    parser = argparse.ArgumentParser(
        description='只读枚举 VID/PID 对应的 USB 设备节点（父设备 + 复合设备接口）')
    parser.add_argument('--vid', default=None,
                        help='VID，十六进制（默认取 device_profile 包）')
    parser.add_argument('--pid', default=None,
                        help='PID，十六进制（默认取 device_profile 包）')
    parser.add_argument('--all-nodes', action='store_true',
                        help='打印枚举到的全部 USB 节点实例 ID')
    parser.add_argument('--sample', type=int, default=3,
                        help='自检时列出的示例节点个数（默认 3）')
    args = parser.parse_args()

    if not args.vid or not args.pid:
        try:
            default_vid, default_pid = profile_defaults()
        except Exception as exc:
            print('无法从 src\\device_profile\\identity.py 读取默认 VID/PID（%s）；'
                  '请用 --vid/--pid 指定' % exc)
            return 2
        args.vid = args.vid or default_vid
        args.pid = args.pid or default_pid

    try:
        vid = int(args.vid, 16)
        pid = int(args.pid, 16)
    except ValueError:
        print('VID/PID 必须是十六进制，例如 --vid 046D --pid C52B')
        return 2

    print('# enum_usb_nodes 只读诊断')
    print('时间: %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print('主机: %s / Python %s (%d 位)' % (
        platform.platform(),
        platform.python_version(),
        64 if ctypes.sizeof(ctypes.c_void_p) == 8 else 32))
    print('目标: VID_%04X&PID_%04X' % (vid, pid))

    present_records = collect(DIGCF_PRESENT)
    if present_records is None:
        print('\n[错误] SetupDiGetClassDevs(USB, DIGCF_PRESENT) 失败，err=%d'
              % ctypes.get_last_error())
        return 2
    all_records = collect(0)
    if all_records is None:
        print('\n[警告] 非 present 枚举失败，err=%d；仅按 present 节点判断'
              % ctypes.get_last_error())
        all_records = list(present_records)

    present_ids = set(r['instance'] for r in present_records)
    all_ids = set(r['instance'] for r in all_records)
    phantom_ids = all_ids - present_ids

    print('\n== 枚举自检（证明枚举路径本身可用） ==')
    print('USB 枚举器：present 节点 %d 个；含非 present 记录共 %d 个'
          % (len(present_records), len(all_records)))
    for rec in present_records[:max(0, args.sample)]:
        print('  示例: %s  [service=%s]' % (rec['instance'], rec['service'] or '(无)'))
    if args.all_nodes:
        print('  全部 present 节点实例 ID：')
        for rec in present_records:
            print('    %s' % rec['instance'])
        if phantom_ids:
            print('  全部非 present 记录实例 ID：')
            for instance in sorted(phantom_ids):
                print('    %s' % instance)

    matched_present = [r for r in present_records if is_match(r['instance'], vid, pid)]
    matched_phantom = [r for r in all_records
                       if is_match(r['instance'], vid, pid)
                       and r['instance'] not in present_ids]

    print('\n== 匹配 VID_%04X&PID_%04X 的节点 ==' % (vid, pid))
    if not matched_present and not matched_phantom:
        print('未找到匹配设备。')
        print('说明：这只代表“当前时刻系统里没有该 VID/PID 的 USB 设备节点”，')
        print('      不等于枚举失败（上面的自检已证明枚举路径可用）。')
        print('      可能原因：设备未插/未上电/未配对、插在不受支持的端口或集线器、')
        print('      父驱动没有创建接口子节点（Win7 上尤其要查这一点）。')
        return 0

    for rec in matched_present:
        print_node(rec, True)
    if matched_present:
        if matched_phantom:
            print('\n以下为当前不在场的历史残留记录（非 present）：')
    else:
        print('\n当前没有在场的匹配节点；以下仅为历史残留记录（非 present）：')
    for rec in matched_phantom:
        print_node(rec, False)
    if not matched_phantom:
        print('（没有匹配的非 present/残留记录）')

    # ---- 结论 ----
    print('\n== 结论 ==')
    if not matched_present:
        print('当前时刻设备不在场：下面只能看到历史残留记录，不能据此判断“接口缺失”。')
        print('请插好键盘后重新运行本脚本，再按下面三项判断 present 节点。')
    parent_nodes = [r for r in matched_present if mi_of(r['instance']) is None]
    child_nodes = [r for r in matched_present if mi_of(r['instance']) is not None]

    if parent_nodes:
        for rec in parent_nodes:
            print('父节点: %s' % rec['instance'])
            print('        service=%s%s' % (
                rec['service'] or '(无)',
                '（复合设备父驱动 usbccgp）' if (rec['service'] or '').lower() == 'usbccgp'
                else '（注意：不是 usbccgp，说明父设备被别的驱动整体接管）'))
    else:
        print('父节点: 未发现（只有接口子节点或只有残留记录）')

    if child_nodes:
        print('接口节点: %s' % ', '.join(sorted(brief(r) for r in child_nodes)))
        for rec in sorted(child_nodes, key=lambda r: mi_of(r['instance'])):
            state = classify(rec, True)
            status, problem, cr = get_status(rec['devinst'])
            if state == 'bound':
                print('  %s：存在且已绑定（service=%s，problem=%d）'
                      % (brief(rec), rec['service'], problem))
            else:
                print('  %s：存在但未绑定或报错（service=%s，problem=%s）'
                      % (brief(rec), rec['service'] or '(无)',
                         problem if cr == 0 else '查询失败'))
    else:
        print('接口节点: 未发现任何 MI_xx 子节点')
        for rec in parent_nodes:
            service = (rec['service'] or '').lower()
            if service == 'winusb':
                print('           父节点本身已绑定 WinUSB（整设备接管）：Zadig 只显示 1 条属正常，')
                print('           pyusb 仍可通过这一个设备节点访问它的多个接口。')
            elif service == 'usbccgp':
                print('           父节点是 usbccgp，但没有任何接口子节点：')
                print('           检查父设备问题码（上面状态行）与端口/供电，子 PDO 未创建。')
            else:
                print('           父节点被非 usbccgp/WinUSB 的驱动接管（service=%s）：'
                      % (rec['service'] or '(无)'))
                print('           这种整设备绑定下不会出现 MI_xx 子节点，Zadig 也只会列为 1 条。')

    if matched_phantom:
        print('残留记录: %s（曾经枚举过，当前不在场）'
              % ', '.join(brief(r) for r in matched_phantom))

    print('\n判读提示（对照 Zadig 列表）：')
    print('  * MI_00、MI_01 都在且都绑 WinUSB → Zadig 条目数的差异只是列表口径，')
    print('    不影响运行；按“文档记录项”处理，不需要改动（Win7 上 python 已实测可用两个接口）。')
    print('  * 只有父节点、service=WinUSB → 整设备接管：Zadig 只列 1 条是正常的，')
    print('    pyusb 仍可从该设备节点访问多个接口。')
    print('  * 节点“存在且已绑定”但 Zadig 未列出 → Zadig 按驱动键过滤；')
    print('    勾选 Options → List All Devices（必要时再开 Include Hubs）后应能看到。')
    print('  * 节点“存在但未绑定/报错” → 节点在系统里；Zadig 勾 List All Devices 也会列出，')
    print('    若仍看不到，检查是否被当作 hub / service=usbccgp 的复合父节点过滤。')
    print('  * 真的“未找到 MI_xx” → 系统层没有该节点，才需要按父节点问题码/端口继续查。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
