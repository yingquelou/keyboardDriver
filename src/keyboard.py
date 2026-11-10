# -*- coding: utf-8 -*-
import sys
import time
import threading
import app_paths

# 打包形态下 libusb-1.0.dll 可能位于 sys._MEIPASS（onefile），
# 必须在导入 pyusb 后端与 keyboard_utils 之前把该目录加入 DLL 搜索路径。
app_paths.prepare_native_dlls()

import usb.core
import device_profile as profile
from keyboard_utils import (
    find_device, configure_device, read_report, find_consumer_endpoint,
    read_consumer_report, parse_keyboard_report, parse_consumer_report,
    simulate_modifiers, simulate_keys, simulate_key,
    simulate_consumer_usage, update_key_repeats, release_all_keys,
    has_active_keys, read_lock_bitmap, write_led_bitmap,
    get_device_product, get_current_layer_name
)

# USB 读取超时（毫秒）：没有按键按下时用较长超时，让读操作阻塞等待、显著降低空转 CPU；
# 有键按下（特别是自动重复进行中）时用短超时，减小重复补发的时间抖动。
IDLE_READ_TIMEOUT_MS = 100
ACTIVE_READ_TIMEOUT_MS = 2

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
            # 接口暂时不可用（例如设备刚断开）时静默重试；整体重连仍由主循环负责
            if not warned:
                print(f"[警告] 消费类接口读取失败: {e}（将静默重试）")
                warned = True
            if stop_event.wait(1.0):
                return
            found = find_consumer_endpoint()
            if found is not None:
                dev, ep = found[0], found[1]
            continue
        usage = parse_consumer_report(raw)
        if usage is not None:
            simulate_consumer_usage(usage)

# ---------- 指示灯线程 ----------
# 位图完全由系统真实锁定状态计算，不维护影子状态：
#   启动先同步一次，之后按 device_profile.LED_POLL_INTERVAL_S 兜底轮询，锁定状态一变就立即写。
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
    # 本设备在 WinUSB 接管模式下写灯返回成功但灯无反应，因此默认关闭；
    # 只有显式 --led 才启用，避免无意义的小流量与日志噪音。
    led_thread = None
    if enable_led:
        led_thread = threading.Thread(target=led_loop, args=(dev, stop_event), daemon=True)
        led_thread.start()
        print("[信息] 指示灯同步已启用（--led）")
    else:
        reason = profile.LED_UNAVAILABLE_HINT if not profile.LED_SUPPORTED else "设备默认关闭"
        print(f"[信息] 指示灯同步未启用（{reason}，如需尝试请加 --led）")

    print(f"开始监听键盘，当前层: {get_current_layer_name()}，按 Ctrl+C 退出。")
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
                # 处理普通键变化（包含层切换逻辑）
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
        simulate_consumer_usage(0)
        print("已释放所有按键。")

# ---------- 主程序（带自动重连） ----------
def main():
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

if __name__ == "__main__":
    main()
