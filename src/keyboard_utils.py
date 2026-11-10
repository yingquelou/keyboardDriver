# -*- coding: utf-8 -*-
"""keyboard_utils.py —— 通用键盘接管实现（设备差异全部来自 device_profile）

本文件只做与具体键盘无关的事：枚举设备、按角色识别接口、claim、读取循环、
按键注入、自动重复引擎、指示灯同步、日志。
VID/PID、接口角色、报告布局、消费类集合、指示灯输出报告格式全部通过 device_profile
取值；usage→VK 换算与重复语义来自通用模块 hid_usage（HID Usage Tables）——换键盘时
不要改本文件。
"""
import ctypes
import time
import usb.core
import usb.util
import usb.backend.libusb1
try:
    import win32api
    import win32con
except ImportError:                       # 未安装 pywin32 时退回 ctypes 兼容层
    import win32_compat as win32api
    win32con = win32api
import device_profile as profile
import hid_usage

# ---------- 引擎参数（与设备无关） ----------
READ_TIMEOUT_MS = 10            # 需要周期性检查自动重复，读超时不能太长
CONSUMER_READ_TIMEOUT_MS = 100

# ---------- 后端初始化 ----------
backend = usb.backend.libusb1.get_backend()
if backend is None:
    raise RuntimeError("无法加载 libusb 后端")

# ---------- usage → VK ----------
# 通用映射来自 hid_usage（HID Usage Tables），不区分"层"：设备在 Num Lock 灯位为 1 时
# 自己把字母区改报成小键盘 usage（J: 0x0D → 0x59），两者都能查到对应 VK。
def get_vk(hid_code):
    """键盘页 usage → 虚拟键码，未映射返回 None"""
    return hid_usage.get_vk(hid_code)

# ---------- 反向映射（校准用） ----------
_VK_NAME_MAP = {value: name for name, value in win32con.__dict__.items() if name.startswith('VK_')}

def get_vk_name(vk_value):
    """将虚拟键码转换为友好名称（用于校准）"""
    if 0x30 <= vk_value <= 0x39 or 0x41 <= vk_value <= 0x5A:
        return chr(vk_value)
    if 0x61 <= vk_value <= 0x7A:
        return chr(vk_value - 0x20)
    return _VK_NAME_MAP.get(vk_value, f"0x{vk_value:02X}")

def get_device_product(dev):
    """安全获取设备产品名称"""
    try:
        return usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "未知产品"
    except:
        return "未知产品"

# ---------- USB 枚举工具 ----------
# Windows 上复合设备由通用父驱动（usbccgp）为每个接口/接口集合建立独立 PDO，
# libusb 依据驱动绑定情况可能把它们枚举成多个 VID/PID 相同的“设备”，顺序不保证。
# 因此这里不写死接口号、也不假定第一个匹配项就是键盘，统一按描述符中的“角色”识别：
#   键盘接口 / 消费类接口的判定规则由 device_profile 提供。

def _candidate_devices():
    """返回所有 VID/PID 匹配的 libusb 设备候选（复合设备可能是多个）"""
    try:
        return list(usb.core.find(find_all=True, idVendor=profile.VID,
                                  idProduct=profile.PID, backend=backend))
    except Exception:
        return []

def _configurations(dev):
    """取设备全部配置描述符；拿不到时退回当前生效配置"""
    try:
        cfgs = _resolve(getattr(dev, 'configurations', None))
        if cfgs:
            return list(cfgs)
    except Exception:
        pass
    try:
        return [dev.get_active_configuration()]
    except Exception:
        return []

def _resolve(value):
    """pyusb 1.3 起 configurations/endpoints 等变成了方法，这里统一取值"""
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value

def _iter_settings(item):
    """列出配置下某个接口的所有备用设置（兼容属性/方法两种形态）"""
    if hasattr(item, 'bEndpointAddress'):
        return []
    settings = _resolve(getattr(item, 'alternate_settings', None))
    if settings:
        return list(settings)
    return [item]

def _iter_endpoints(setting):
    """列出某个备用设置下的端点（兼容属性/方法两种形态）"""
    eps = _resolve(getattr(setting, 'endpoints', None))
    if eps:
        return list(eps)
    result = []
    try:
        for sub in setting:
            if hasattr(sub, 'bEndpointAddress'):
                result.append(sub)
            else:
                result.extend(list(_resolve(getattr(sub, 'endpoints', None)) or []))
    except Exception:
        pass
    return result

def _walk_interfaces(dev):
    """遍历设备所有 (配置, 接口设置, 端点列表)，与枚举顺序无关"""
    for cfg in _configurations(dev):
        try:
            items = list(cfg)
        except Exception:
            continue
        for item in items:
            if hasattr(item, 'bEndpointAddress'):
                continue
            for setting in _iter_settings(item):
                yield cfg, setting, _iter_endpoints(setting)

# 端点方向/类型是 USB 规范常量；具体期望值由 device_profile 声明
_ENDPOINT_DIRECTIONS = {
    'in': usb.util.ENDPOINT_IN,
    'out': usb.util.ENDPOINT_OUT,
}
_ENDPOINT_TYPES = {
    'interrupt': usb.util.ENDPOINT_TYPE_INTR,
    'bulk': usb.util.ENDPOINT_TYPE_BULK,
    'isochronous': usb.util.ENDPOINT_TYPE_ISO,
}

def _find_data_endpoint(eps):
    """按 device_profile 声明的方向/类型取第一个端点"""
    want_dir = _ENDPOINT_DIRECTIONS.get(profile.ENDPOINT_DIRECTION, usb.util.ENDPOINT_IN)
    want_type = _ENDPOINT_TYPES.get(profile.ENDPOINT_TYPE, usb.util.ENDPOINT_TYPE_INTR)
    for ep in eps:
        if (usb.util.endpoint_direction(ep.bEndpointAddress) == want_dir and
                usb.util.endpoint_type(ep.bmAttributes) == want_type):
            return ep
    return None

def _ep_text(ep):
    direction = 'IN' if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN else 'OUT'
    etype = '中断' if usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_INTR else '其它'
    return f"0x{ep.bEndpointAddress:02X}({direction},{etype},{ep.wMaxPacketSize}字节,间隔{ep.bInterval})"

def _describe_candidates(devs):
    """打印候选设备/接口/端点清单（Win7 排查时按此对照）"""
    print(f"[信息] 匹配 VID:PID=0x{profile.VID:04X}:0x{profile.PID:04X} 的 libusb 设备候选: {len(devs)} 个")
    for idx, dev in enumerate(devs, 1):
        print(f"[信息] 候选 {idx}: bus={getattr(dev, 'bus', 0)} address={getattr(dev, 'address', 0)}")
        for cfg, setting, eps in _walk_interfaces(dev):
            ep_text = ', '.join(_ep_text(ep) for ep in eps) or '无'
            print(f"[信息]   配置{cfg.bConfigurationValue} 接口{setting.bInterfaceNumber}"
                  f" 类/子类/协议 {setting.bInterfaceClass}/{setting.bInterfaceSubClass}/"
                  f"{setting.bInterfaceProtocol} 端点: {ep_text}")

def _get_report_descriptor(dev, intf_no, timeout=200):
    """请求指定接口的 HID 报告描述符；接口不属于该设备节点时返回 None"""
    try:
        data = dev.ctrl_transfer(0x81, 0x06, 0x2200, intf_no, 1024, timeout=timeout)
        return bytes(data) if data else None
    except Exception:
        return None

def _hid_input_items(desc):
    """解析报告描述符，产出所有 Input 主项的 (usage_page, report_id, report_size_bits)

    本函数只负责按 HID 规范拆项；哪一项属于本设备的消费类集合，由
    device_profile.choose_consumer_report 决定（例如需要跳过 8 位的鼠标 AC Pan）。"""
    usage_page = 0
    report_id = 0
    report_size = 0
    i = 0
    n = len(desc)
    while i < n:
        prefix = desc[i]
        i += 1
        if prefix == 0xFE:          # 长项目：跳过
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
        value = 0
        for k in range(size):
            value |= desc[i + k] << (8 * k)
        i += size
        itype = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        if itype == 1:              # 全局项
            if tag == 0x0:          # Usage Page
                usage_page = value
            elif tag == 0x7:        # Report Size
                report_size = value
            elif tag == 0x8:        # Report ID
                report_id = value
        elif itype == 0 and tag == 0x8:
            # 主项 Input
            yield usage_page, report_id, report_size

def _is_timeout_error(e):
    """区分“读超时（端点可用、当前无数据）”和“端点/节点不可用”"""
    errno = getattr(e, 'errno', None)
    text = str(e).lower()
    return errno in (-7, 110, 10060) or 'timeout' in text or 'timed out' in text

def _probe_endpoint(dev, ep):
    """用极短超时读一次，确认该设备节点确实持有此端点"""
    try:
        dev.read(ep.bEndpointAddress, max(3, ep.wMaxPacketSize), timeout=1)
    except usb.core.USBError as e:
        return _is_timeout_error(e)
    except Exception:
        return False
    return True

def _try_set_configuration(dev):
    """尽力让配置生效（Windows 上可能返回 Resource busy，属正常）"""
    try:
        dev.set_configuration()
    except usb.core.USBError:
        pass

def _find_keyboard_interface(dev):
    """按角色找键盘接口（不依赖接口号）"""
    for cfg, setting, eps in _walk_interfaces(dev):
        if profile.is_keyboard_interface(setting) and _find_data_endpoint(eps) is not None:
            return setting
    return None

def _find_media_interface(dev):
    """按角色找消费类接口；返回 (接口设置, 端点, Report ID, usage 字节数)"""
    for cfg, setting, eps in _walk_interfaces(dev):
        if not profile.is_consumer_interface(setting):
            continue
        ep = _find_data_endpoint(eps)
        if ep is None:
            continue
        desc = _get_report_descriptor(dev, setting.bInterfaceNumber)
        if not desc:
            continue
        chosen = profile.choose_consumer_report(list(_hid_input_items(desc)))
        if chosen is None:
            continue
        report_id, usage_size = chosen
        return setting, ep, report_id, usage_size
    return None

# ---------- 设备操作 ----------
def find_device():
    """在所有候选中选键盘接口真正所在的设备节点（枚举顺序不保证，需按端点探测）"""
    devs = _candidate_devices()
    if not devs:
        raise ValueError("设备未找到")
    fallback = None
    for dev in devs:
        intf = _find_keyboard_interface(dev)
        if intf is None:
            continue
        if fallback is None:
            fallback = dev
        _try_set_configuration(dev)
        ep_in = _find_data_endpoint(_iter_endpoints(intf))
        # 1ms 探测读：不属于该节点的端点会立即报错；仅可能丢掉开机瞬间唯一一份报告
        if ep_in is not None and _probe_endpoint(dev, ep_in):
            return dev
    return fallback or devs[0]

def configure_device(dev):
    """配置设备并返回键盘数据端点"""
    try:
        dev.set_configuration()
    except usb.core.USBError as e:
        if "Resource busy" not in str(e):
            raise
    intf = _find_keyboard_interface(dev)
    if intf is None:
        raise ValueError("未找到键盘接口")
    ep_in = _find_data_endpoint(_iter_endpoints(intf))
    if ep_in is None:
        raise ValueError("未找到中断输入端点")
    return ep_in

def find_consumer_endpoint(verbose=False, dev=None):
    """在所有候选中定位可用的消费类接口，返回 (设备, 端点, 接口号) 或 None

    Win7/Win11 的枚举顺序、接口编号都可能不同，因此：
    - 接口由报告描述符（消费类 Usage Page）识别，不用写死的接口号；
    - 设备节点用 1ms 探测读确认，自动跳过不属于该接口的 PDO。
    - 传入 dev 时直接复用已打开的节点：同一进程重复打开同一复合设备会互相干扰
      （第二次 libusb 打开后读报告描述符会失败）。"""
    devs = [dev] if dev is not None else _candidate_devices()
    if verbose:
        _describe_candidates(devs)
    found = None
    for candidate in devs:
        # 未激活配置时部分后端读不到描述符，先尽力激活；已打开的节点不必再激活
        if dev is None:
            _try_set_configuration(candidate)
        media = _find_media_interface(candidate)
        if media is None:
            continue
        setting, ep, report_id, usage_size = media
        if verbose:
            print(f"[信息] 消费类接口 {setting.bInterfaceNumber} 端点 0x{ep.bEndpointAddress:02X}"
                  f" 报告描述符 Report ID={report_id} usage {usage_size} 字节")
        if not _probe_endpoint(candidate, ep):
            if verbose:
                print(f"[警告] 设备候选（接口 {setting.bInterfaceNumber}）探测读失败，跳过")
            continue
        try:
            usb.util.claim_interface(candidate, setting.bInterfaceNumber)
        except usb.core.USBError:
            # 驱动已占用时 claim 会失败，仍可继续尝试读取
            pass
        found = (candidate, ep, setting.bInterfaceNumber)
        break
    if found is None and verbose:
        print("[警告] 未找到可读的消费类接口（报告描述符中没有 Usage Page 0x%02X 的输入报告）"
              % profile.CONSUMER_USAGE_PAGE)
    return found

def read_report(dev, ep, timeout=READ_TIMEOUT_MS):
    """读取一份键盘报告；超时返回 None，其他 USB 错误抛给上层以触发重连"""
    read_size = profile.key_report_read_size(ep.wMaxPacketSize)
    try:
        return bytes(dev.read(ep.bEndpointAddress, read_size, timeout=timeout))
    except usb.core.USBError as e:
        if _is_timeout_error(e):
            return None
        raise

def read_consumer_report(dev, ep, timeout=CONSUMER_READ_TIMEOUT_MS):
    """读取一份消费类报告；超时返回 None，其他 USB 错误抛给上层"""
    read_size = profile.consumer_report_read_size(ep.wMaxPacketSize)
    try:
        return bytes(dev.read(ep.bEndpointAddress, read_size, timeout=timeout))
    except usb.core.USBError as e:
        if _is_timeout_error(e):
            return None
        raise

def parse_keyboard_report(raw):
    """解析键盘报告（布局由 device_profile 定义），返回 (修饰键字节, 键列表)"""
    return profile.parse_key_report(raw)

def parse_consumer_report(raw):
    """解析消费类报告（Report ID/usage 宽度与字节序由 device_profile 定义）"""
    return profile.parse_consumer_report(raw)

# ---------- 模拟按键 ----------
def simulate_key(vk_code, down=True):
    if vk_code is None:
        return
    flags = 0 if down else win32con.KEYEVENTF_KEYUP
    win32api.keybd_event(vk_code, 0, flags, 0)

# USB HID boot 键盘标准修饰键位图（bit -> VK），与具体设备无关
BOOT_MODIFIER_BITMAP = {
    0x01: win32con.VK_LCONTROL,
    0x02: win32con.VK_LSHIFT,
    0x04: win32con.VK_LMENU,
    0x08: win32con.VK_LWIN,
    0x10: win32con.VK_RCONTROL,
    0x20: win32con.VK_RSHIFT,
    0x40: win32con.VK_RMENU,
    0x80: win32con.VK_RWIN,
}

def simulate_modifiers(modifier_byte, prev_modifier_byte):
    global _repeat_mod, _repeat_hid
    for mask, vk in BOOT_MODIFIER_BITMAP.items():
        current = bool(modifier_byte & mask)
        previous = bool(prev_modifier_byte & mask)
        if current and not previous:
            simulate_key(vk, down=True)
            _modifier_down[vk] = time.monotonic()
            # 最近按下的键接管自动重复，先前的字符键/修饰键都停止重复
            _repeat_mod = vk
            _repeat_hid = None
        elif not current and previous:
            simulate_key(vk, down=False)
            _modifier_down.pop(vk, None)
            _repeat_mod_next.pop(vk, None)
            if vk == _repeat_mod:
                _repeat_mod = None

# ---------- 按键状态与自动重复 ----------
# 记录 hid_code -> 实际注入的虚拟键码。抬起时使用按下时的映射，
# 因此中途锁定状态变化（固件切层）不会让抬起错用另一个键码，不会残留按键。
_active_keys = {}
_key_down_time = {}   # hid_code -> 按下时刻（用于自动重复）
_repeat_next = {}     # hid_code -> 下一次重复时刻
# 原生键盘的自动重复只针对“最近按下的那个键”（含修饰键）：按住 A 再按 B，A 停止重复；
# 松开 B 也不会让 A 恢复重复。这里用单独变量记录当前重复对象。
_repeat_hid = None

# 修饰键不占键码槽，单独记录：原生同样会对按住的修饰键产生自动重复
_modifier_down = {}       # vk -> 按下时刻
_repeat_mod = None        # 当前参与重复的修饰键 vk
_repeat_mod_next = {}     # vk -> 下一次重复时刻

# 注入的按键不会触发系统自动重复（原生 HID 键盘的重复由键盘类驱动产生），
# 这里按系统设置的延迟/速率补发 keydown。
# 哪些键不参与重复（例如锁定键）由 hid_usage.repeats_key 决定。

_repeat_timing = None
_repeat_timing_at = 0

def _get_repeat_timing():
    """读取系统键盘重复延迟/速率（SPI_GETKEYBOARDDELAY / SPI_GETKEYBOARDSPEED）"""
    global _repeat_timing, _repeat_timing_at
    now = time.monotonic()
    if _repeat_timing and now - _repeat_timing_at < 5:
        return _repeat_timing
    delay_ms = 500     # 系统默认：500ms
    interval_ms = 33   # 系统默认：约 30 次/秒
    try:
        user32 = ctypes.windll.user32
        level = ctypes.c_uint(0)
        if user32.SystemParametersInfoW(0x0016, 0, ctypes.byref(level), 0):  # SPI_GETKEYBOARDDELAY
            delay_ms = 250 * (level.value + 1)
        speed = ctypes.c_uint(0)
        if user32.SystemParametersInfoW(0x000A, 0, ctypes.byref(speed), 0):  # SPI_GETKEYBOARDSPEED
            rate = 2.5 + speed.value * 0.5     # 2.5 ~ 18 次/秒（Windows 的实际换算）
            interval_ms = max(1, int(1000.0 / rate))
    except Exception:
        pass
    _repeat_timing = (delay_ms, interval_ms)
    _repeat_timing_at = now
    return _repeat_timing

def update_key_repeats(now=None):
    """按住键超过系统重复延迟后，按系统速率补发 keydown

    三路独立：普通键键槽、修饰键、消费类音量键。它们的重复目标互不相同，
    因此不使用互斥返回，避免音量键按住时被普通键的重复逻辑挡住。
    """
    if now is None:
        now = time.monotonic()
    global _consumer_repeat_next
    delay_ms, interval_ms = _get_repeat_timing()

    def _advance(next_time, start_time):
        """以“计划时刻”为基准推进，避免每次把唤醒延迟累加进间隔；落后太多时重置"""
        due = next_time
        if due is None:
            due = start_time + delay_ms / 1000.0
        if now < due:
            return due, False
        nxt = due + interval_ms / 1000.0
        if nxt < now:
            nxt = now + interval_ms / 1000.0
        return nxt, True

    if _repeat_hid is not None:
        vk = _active_keys.get(_repeat_hid)
        start = _key_down_time.get(_repeat_hid)
        if vk is not None and start is not None:
            nxt, fire = _advance(_repeat_next.get(_repeat_hid), start)
            _repeat_next[_repeat_hid] = nxt
            if fire:
                simulate_key(vk, down=True)

    if _repeat_mod is not None:
        start = _modifier_down.get(_repeat_mod)
        if start is not None:
            nxt, fire = _advance(_repeat_mod_next.get(_repeat_mod), start)
            _repeat_mod_next[_repeat_mod] = nxt
            if fire:
                simulate_key(_repeat_mod, down=True)

    if _consumer_repeat_vk is not None and _consumer_vk == _consumer_repeat_vk:
        nxt, fire = _advance(_consumer_repeat_next, _consumer_repeat_start)
        _consumer_repeat_next = nxt
        if fire:
            simulate_key(_consumer_repeat_vk, down=True)

def has_active_keys():
    """是否仍有按键处于按下状态（普通键、修饰键或音量键重复中）；用于选择 USB 读取超时"""
    return bool(_active_keys) or bool(_modifier_down) or _consumer_repeat_vk is not None

def release_all_keys():
    """释放所有当前按下的键（使用按下时记录的虚拟键码）"""
    global _repeat_hid, _repeat_mod, _consumer_repeat_vk, _consumer_repeat_next
    for vk in list(_active_keys.values()):
        simulate_key(vk, down=False)
    for vk in list(_modifier_down.keys()):
        simulate_key(vk, down=False)
    _active_keys.clear()
    _key_down_time.clear()
    _repeat_next.clear()
    _modifier_down.clear()
    _repeat_mod_next.clear()
    _repeat_hid = None
    _repeat_mod = None
    # 断线/退出时同步停掉音量键重复，避免定时器继续补发
    _consumer_repeat_vk = None
    _consumer_repeat_next = None

def simulate_keys(current_keys, prev_keys):
    """处理按键变化：按下注入、松开抬起。

    这里没有任何"层"的概念：设备上报什么 usage，就按 HID Usage Tables 换成 VK。
    Num Lock 的切层由固件完成（它按主机回写的灯位决定上报字母区还是小键盘 usage）。
    """
    global _repeat_hid, _repeat_mod
    now = time.monotonic()

    # 释放已松开的键：使用按下时记录的虚拟键码
    for hid_code in list(_active_keys.keys()):
        if hid_code not in current_keys:
            simulate_key(_active_keys.pop(hid_code), down=False)
            _key_down_time.pop(hid_code, None)
            _repeat_next.pop(hid_code, None)
            if hid_code == _repeat_hid:
                # 松开重复键后不再转移到其它仍按住的键（原生行为）
                _repeat_hid = None

    # 按下新按下的键
    for hid_code in current_keys:
        if hid_code in _active_keys:
            continue
        # 任何新按下的键都会接管自动重复，原目标立即停止
        _repeat_hid = None
        _repeat_mod = None
        vk = get_vk(hid_code)
        if vk is None:
            continue
        simulate_key(vk, down=True)
        _active_keys[hid_code] = vk
        _key_down_time[hid_code] = now
        _repeat_next.pop(hid_code, None)
        if hid_usage.repeats_key(vk):
            _repeat_hid = hid_code

    prev_keys[:] = list(current_keys)

# ---------- 消费类按键 ----------
# 消费类端点只在按下、抬起各上报一次，按住不会重发，因此长按重复由主机侧定时补发；
# 哪些消费类键参与重复由 hid_usage.repeats_consumer 决定。
_consumer_usage = 0
_consumer_vk = None
_consumer_repeat_vk = None     # 当前参与重复的消费类 VK（其它媒体键为 None）
_consumer_repeat_start = 0.0
_consumer_repeat_next = None

def simulate_consumer_usage(usage):
    """把消费类 usage 注入为对应虚拟键；usage 变为 0 时抬起并停止重复"""
    global _consumer_usage, _consumer_vk
    global _consumer_repeat_vk, _consumer_repeat_start, _consumer_repeat_next
    if usage == _consumer_usage:
        # 设备不重发报告，重复由 update_key_repeats 按系统节奏补发；
        # 这里直接忽略重复报告，避免与定时补发叠加成双倍速率
        return
    if _consumer_vk is not None:
        simulate_key(_consumer_vk, down=False)
        _consumer_vk = None
    _consumer_repeat_vk = None
    _consumer_repeat_next = None
    _consumer_usage = usage
    if usage:
        vk = hid_usage.get_consumer_vk(usage)
        if vk is not None:
            simulate_key(vk, down=True)
            _consumer_vk = vk
            # 只有 hid_usage 声明的“可重复”消费键参与长按（音量键）
            if hid_usage.repeats_consumer(vk):
                _consumer_repeat_vk = vk
                _consumer_repeat_start = time.monotonic()

# ---------- 指示灯同步 ----------
def read_lock_bitmap():
    """按系统真实锁定状态计算 LED 位图（位定义由 device_profile.LED_BITS 提供）"""
    user32 = ctypes.windll.user32
    bitmap = 0
    for bit, vk in profile.LED_BITS:
        if user32.GetKeyState(vk) & 1:
            bitmap |= bit
    return bitmap

def write_led_bitmap(dev, bitmap, timeout=100):
    """把 LED 位图写入键盘接口的输出报告（HID Set_Report）

    wValue = (0x02 << 8) | Report ID，wIndex = 接口号（键盘接口为 0）。
    报告长度与 Report ID 都由 device_profile 按描述符给出，不做任何猜测。
    """
    dev.ctrl_transfer(0x21, 0x09, 0x0200 | profile.LED_REPORT_ID, 0,
                      profile.led_report(bitmap), timeout=timeout)

# ---------- 导出 ----------
__all__ = [
    'find_device', 'configure_device', 'read_report', 'find_consumer_endpoint',
    'read_consumer_report', 'parse_keyboard_report', 'parse_consumer_report',
    'simulate_key', 'simulate_modifiers', 'simulate_keys', 'simulate_consumer_usage',
    'update_key_repeats', 'release_all_keys',
    'read_lock_bitmap', 'write_led_bitmap',
    'get_vk_name', 'get_device_product', 'get_vk',
]
