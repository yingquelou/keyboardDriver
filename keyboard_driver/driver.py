# -*- coding: utf-8 -*-
"""运行期编排：单实例、消费类/指示灯线程、主读取循环、断线重连。

USB 读写的原语（枚举、claim、单次读取、注入状态机、灯位回写）在 transport.py；
进程入口在 __main__.py，计划任务/日志外壳在 run.py；设备事实在 device_profile 包。本文件不重复这些职责。
"""
import ctypes
import sys
import time
import threading
from . import paths

# 打包形态下 libusb-1.0.dll 可能位于 sys._MEIPASS（onefile），
# 必须在导入 pyusb 后端与 transport 之前把该目录加入 DLL 搜索路径。
paths.prepare_native_dlls()

import usb.core
from . import device_profile as profile
from .transport import (
    find_device, configure_device, read_report, find_consumer_endpoint,
    read_consumer_report, parse_keyboard_report, parse_consumer_report,
    simulate_modifiers, simulate_keys,
    simulate_consumer_usage, update_key_repeats, release_all_keys,
    has_active_keys, read_lock_bitmap, write_led_bitmap,
    get_device_product
)

# USB 读取超时（毫秒）：没有按键按下时用较长超时，让读操作阻塞等待、显著降低空转 CPU；
# 有键按下（特别是自动重复进行中）时用短超时，减小重复补发的时间抖动。
IDLE_READ_TIMEOUT_MS = 100
ACTIVE_READ_TIMEOUT_MS = 2

# ---------- 单实例互斥 ----------
# WinUSB 允许同一接口被多个进程同时打开，两个实例会各读一份报告、各注入一次按键
# （表现为每个键触发两次）。用命名互斥体保证同一时刻只有一个实例。
# 句柄是进程级对象：进程退出（含崩溃）时由系统释放，所以异常退出不会留下永久占用的锁。
# 用 "Local\" 前缀：互斥范围是当前登录会话，与"只影响本会话的注入"一致。
# 名字里的 VID/PID 取自设备包，本文件不写死本键盘的身份。
INSTANCE_MUTEX_NAME = "Local\\KeyboardDriver_%04X_%04X" % (profile.VID, profile.PID)
ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
_kernel32.CreateMutexW.restype = ctypes.c_void_p
_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
_kernel32.CloseHandle.restype = ctypes.c_int


def acquire_single_instance():
    """取单实例互斥；已有实例时打印原因并退出，返回需在退出前释放的句柄"""
    handle = _kernel32.CreateMutexW(None, False, INSTANCE_MUTEX_NAME)
    if not handle:
        # 创建失败不阻断运行：宁可重复注入，也不要让用户完全没键盘
        print(f"[警告] 创建单实例互斥体失败（错误码 {ctypes.get_last_error()}），继续运行")
        return None
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(handle)
        print("[错误] 已有另一个键盘驱动实例在运行。")
        print("       同一接口被两个实例同时读取会让每个按键被注入两次，本次启动已取消。")
        print("       请先关闭已运行的实例（或结束残留的 python/keyboard 进程）再试。")
        sys.exit(1)
    return handle


def release_single_instance(handle):
    if handle:
        _kernel32.CloseHandle(handle)

# ---------- 消费类按键线程 ----------
# 音量/多媒体/浏览器键由消费类接口上报，与键盘接口分开。
# 用独立线程读取，避免阻塞键盘主循环；设备节点由描述符角色 + 探测读确定，
# 不依赖枚举顺序和写死的接口号。
def consumer_loop(dev, ep, stop_event):
    warned = False
    while not stop_event.is_set():
        try:
            raw = read_consumer_report(dev, ep)
        except Exception as e:
            # 不在这里重新打开设备：同一进程重复打开同一复合设备会互相干扰
            # （见 find_consumer_endpoint 的注释），那样"自愈"反而会弄坏媒体键。
            # 这里只记录并原地重试；节点被重新枚举时由主循环整体重连，
            # 重连成功后新线程会拿到主循环提供的设备与端点继续工作。
            if not warned:
                print(f"[警告] 消费类接口读取失败: {e}（原地重试，重连交由主循环）")
                warned = True
            if stop_event.wait(1.0):
                return
            continue
        usage = parse_consumer_report(raw)
        if usage is not None:
            simulate_consumer_usage(usage)

# ---------- 指示灯线程 ----------
# 位图完全由系统真实锁定状态计算，不维护影子状态：
#   启动先同步一次，之后按 device_profile.LED_POLL_INTERVAL_S 轮询，锁定状态一变就立即写。
# 这不只是"亮灯"：本设备按 Num Lock 灯位决定上报字母区还是小键盘 usage，
# 因此灯位回写是切层的必要一环（与原生 HID 键盘类的行为一致）。
# 写失败按 5 秒限流告警并在下一轮重试；任何异常都不会影响按键主循环。
def led_loop(dev, stop_event):
    last_bitmap = None
    last_warn = 0.0
    while not stop_event.is_set():
        try:
            bitmap = read_lock_bitmap()
        except Exception:
            bitmap = None
        if bitmap is not None and bitmap != last_bitmap:
            try:
                write_led_bitmap(dev, bitmap)
                last_bitmap = bitmap
            except Exception as e:
                now = time.monotonic()
                if now - last_warn > 5:
                    print(f"[警告] 指示灯写入失败: {e}（5 秒内不再重复告警）")
                    last_warn = now
        stop_event.wait(profile.LED_POLL_INTERVAL_S)

# ---------- 主循环（处理按键） ----------
def process_loop(dev, ep, enable_led=False):
    prev_modifier = 0
    prev_keys = []
    stop_event = threading.Event()
    consumer_thread = None

    # 媒体键接口：复用已打开的键盘节点（同一进程重复打开同一复合设备会互相干扰）
    media = find_consumer_endpoint(verbose=True, dev=dev)
    if media is not None:
        media_dev, media_ep, media_ifno = media
        print(f"[信息] 媒体键使用接口 {media_ifno}，端点 0x{media_ep.bEndpointAddress:02X}")
        consumer_thread = threading.Thread(
            target=consumer_loop, args=(media_dev, media_ep, stop_event), daemon=True)
        consumer_thread.start()
    else:
        print("[提示] 未找到可读的消费类接口，媒体键/音量键不可用。")

    # 指示灯同步线程：默认值由设备模块声明（LED_SUPPORTED）。
    # 本设备的切层依赖主机回写 Num Lock 灯位，所以默认必须启用；--no-led 只用于排障。
    led_thread = None
    if enable_led:
        led_thread = threading.Thread(target=led_loop, args=(dev, stop_event), daemon=True)
        led_thread.start()
        print("[信息] 指示灯同步已启用（锁定状态会回写设备，切层依赖它）")
    else:
        print("[警告] 指示灯同步被 --no-led 关闭：Num Lock 切层不会生效")

    print("开始监听键盘，按 Ctrl+C 退出。")
    try:
        while True:
            timeout = ACTIVE_READ_TIMEOUT_MS if has_active_keys() else IDLE_READ_TIMEOUT_MS
            raw = read_report(dev, ep, timeout)
            modifier, keys = parse_keyboard_report(raw)
            if keys is not None:
                # 处理修饰键变化
                if modifier != prev_modifier:
                    simulate_modifiers(modifier, prev_modifier)
                    prev_modifier = modifier
                # 处理普通键变化（含锁定键：按 usage 通用映射转发，见 usage）
                if keys != prev_keys:
                    simulate_keys(keys, prev_keys)
                    # 注意：simulate_keys 会修改 prev_keys，因此这里不需要再赋值
            # 注入的按键不会自动重复，按系统延迟/速率补发
            update_key_repeats()
            time.sleep(0.001)
    except KeyboardInterrupt:
        print("\n用户中断，清理...")
        raise
    finally:
        # 断线/中断都要回到干净状态：停消费类线程、抬起所有键
        stop_event.set()
        if consumer_thread is not None:
            consumer_thread.join(timeout=0.5)
        if led_thread is not None:
            led_thread.join(timeout=0.5)
        release_all_keys()
        print("已释放所有按键。")

# ---------- 主程序（带自动重连） ----------
def main():
    mutex = acquire_single_instance()   # 已有实例时在这里直接退出（exit 1）
    try:
        _run()
    finally:
        release_single_instance(mutex)


def _run():
    print("启动正常模式...")
    # 指示灯默认值由设备模块声明：--led 强制开启，--no-led 强制关闭
    if '--led' in sys.argv[1:]:
        enable_led = True
    elif '--no-led' in sys.argv[1:]:
        enable_led = False
    else:
        enable_led = profile.LED_SUPPORTED
    retry_interval = 5
    while True:
        try:
            print("正在查找设备...")
            dev = find_device()
            product = get_device_product(dev)
            print(f"找到设备: {product}")
            
            ep = configure_device(dev)
            print(f"中断端点: 0x{ep.bEndpointAddress:02X}, 包大小: {ep.wMaxPacketSize}")
            
            process_loop(dev, ep, enable_led)
            break
        
        except KeyboardInterrupt:
            print("\n程序已退出。")
            break
        
        except usb.core.USBError as e:
            print(f"USB 错误: {e}，{retry_interval}秒后重试...")
            time.sleep(retry_interval)
            continue
        
        except Exception as e:
            print(f"发生未预期错误: {e}，{retry_interval}秒后重试...")
            time.sleep(retry_interval)
            continue
