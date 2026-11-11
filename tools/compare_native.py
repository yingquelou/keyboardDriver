# -*- coding: utf-8 -*-
"""compare_native.py —— 原生驱动与本实现注入的按键序列对照工具

用途：把“系统原生驱动处理的按键”和“本驱动注入的按键”分别录下来，逐键比较
      按下次数、首次重复延迟、重复间隔，作为判断本实现是否与原厂行为一致的依据。

用法：
    python compare_native.py record --out native.jsonl --label 原生
    python compare_native.py record --out ours.jsonl   --label 本实现
    python compare_native.py compare native.jsonl ours.jsonl

record
    安装 WH_KEYBOARD_LL 全局钩子，逐条记录 (相对时间, VK, 扫描码, flags, 是否注入)。
    按结束键（默认 F8）或 Ctrl+C 结束；也可用 --seconds 指定固定时长。
    录制时请按固定节奏操作：轻点若干次、再按住某个键约 3 秒。
    记录中 injected=True 表示事件带 LLKHF_INJECTED 标记（即由本驱动注入）。

compare
    把连续记录切分为“按键段”：同一 VK 的按下→抬起为一段，段内的重复 keydown
    即自动重复。对每个 VK 统计段数、每段重复次数、首延迟与重复间隔，逐键输出差异。

只依赖标准库 + ctypes（VK 常量名取自 keyboard_driver\\win32_compat，不 import pyusb），
不需要 pywin32，也不需要管理员权限。

边界：本脚本是仓库里唯一安装 LL 键盘钩子的地方。它看的是系统最终收到的按键
（VK + 注入标记 + 重复节奏），不是 HID usage、也不是原始报文——那两类分别用
calibrate 与 native_probe.py。
"""

import argparse
import ctypes
import datetime
import json
import os
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

WH_KEYBOARD_LL = 13
LLKHF_INJECTED = 0x10
LLKHF_UP = 0x80

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p)]


HOOKPROC = ctypes.WINFUNCTYPE(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.restype = wintypes.HANDLE
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HMODULE, wintypes.DWORD]
user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
user32.CallNextHookEx.restype = wintypes.LPARAM
user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                                wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]


# ---------- VK 名称（取自 win32_compat，避免依赖 pywin32） ----------
def _build_vk_names():
    try:
        from keyboard_driver import win32_compat as compat
    except ImportError:
        return {}
    names = {}
    for name in sorted(dir(compat)):
        if not name.startswith('VK_'):
            continue
        value = getattr(compat, name)
        names.setdefault(value, name[3:])
    return names


VK_NAMES = _build_vk_names()


def vk_text(vk):
    name = VK_NAMES.get(vk)
    if name:
        return "%s(0x%02X)" % (name, vk)
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return "%s(0x%02X)" % (chr(vk), vk)
    return "0x%02X" % vk


# ---------- 录制 ----------
def record(out_path, label, seconds=0, stop_vk=0x77):
    # 逐条写入并 flush：即使进程被意外终止，已录到的事件也不会丢
    out = open(out_path, "w", encoding="utf-8")
    state = {"running": True, "count": 0, "start": None}

    def on_event(n_code, w_param, l_param):
        if n_code == 0:
            info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if stop_vk and info.vkCode == stop_vk and not (info.flags & LLKHF_UP) and not info.flags & LLKHF_INJECTED:
                state["running"] = False
                return 1        # 吞掉结束键，避免它传给前台窗口
            item = {
                "t": round(time.perf_counter(), 4),
                "wall": datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "vk": int(info.vkCode),
                "scan": int(info.scanCode),
                "flags": int(info.flags),
                "down": not bool(info.flags & LLKHF_UP),
                "injected": bool(info.flags & LLKHF_INJECTED),
            }
            if state["start"] is None:
                state["start"] = item["t"]
            out.write(json.dumps(item, ensure_ascii=False) + "\n")
            out.flush()
            state["count"] += 1
            print("  %8.3f  %-24s %s%s"
                  % (item["t"] - state["start"],
                     vk_text(item["vk"]),
                     "按下" if item["down"] else "抬起",
                     " [注入]" if item["injected"] else ""))
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, HOOKPROC(on_event),
                                    kernel32.GetModuleHandleW(None), 0)
    if not hook:
        raise SystemExit("安装键盘钩子失败，错误码 %d" % ctypes.get_last_error())

    print("=== 录制模式（%s） ===" % label)
    if seconds:
        print("录制时长 %d 秒，到点自动结束。" % seconds)
    if stop_vk:
        print("按 %s 结束录制（该键会被吞掉，不传给前台窗口）。" % vk_text(stop_vk))
    print("请按固定节奏操作：轻点若干次，再按住某个字符键约 3 秒，最后按结束键。")
    print("每条事件实时显示在下方：")
    started = time.perf_counter()
    msg = wintypes.MSG()
    try:
        while state["running"]:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if seconds and time.perf_counter() - started >= seconds:
                break
            time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    finally:
        user32.UnhookWindowsHookEx(hook)
        out.close()

    print("\n已记录 %d 条事件，写入 %s" % (state["count"], out_path))


# ---------- 分析 ----------
def load(path):
    items = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def split_sessions(items):
    """按 VK 切成按键段：返回 {vk: [段, ...]}，每段为该次按住的 keydown 时间列表"""
    sessions = {}
    current = {}
    zero = items[0]["t"] if items else 0.0
    for item in items:
        vk = item["vk"]
        delta = item["t"] - zero
        if item["down"]:
            current.setdefault(vk, []).append(delta)
        else:
            if vk in current:
                sessions.setdefault(vk, []).append(current.pop(vk))
    for vk, downs in current.items():
        sessions.setdefault(vk, []).append(downs)
    return sessions


def summarize(sessions):
    """每个 VK 汇总：段数、最多重复次数、首延迟、重复间隔"""
    result = {}
    for vk, runs in sessions.items():
        repeats = max(len(run) for run in runs) - 1
        delays = []
        intervals = []
        for run in runs:
            if len(run) >= 2:
                delays.append(run[1] - run[0])
                intervals.extend(run[i + 1] - run[i] for i in range(1, len(run) - 1))
        result[vk] = {
            "runs": len(runs),
            "repeats": max(0, repeats),
            "delay": (sum(delays) / len(delays)) if delays else None,
            "interval": (sum(intervals) / len(intervals)) if intervals else None,
        }
    return result


def fmt_ms(value):
    return "-" if value is None else "%.0fms" % (value * 1000)


def compare(native_path, ours_path):
    native = summarize(split_sessions(load(native_path)))
    ours = summarize(split_sessions(load(ours_path)))

    print("%-28s %-9s %-9s %-9s %-9s %-9s %s"
          % ("VK", "原生段数", "本实现段", "原生首延迟", "本实现", "原生间隔", "本实现间隔"))
    print("-" * 100)
    diffs = []
    for vk in sorted(set(native) | set(ours)):
        n = native.get(vk)
        o = ours.get(vk)
        if n is None or o is None:
            diffs.append("%s 只出现在%s" % (vk_text(vk), "本实现" if n is None else "原生"))
        elif n["repeats"] != o["repeats"]:
            diffs.append("%s 重复次数不同：原生 %d / 本实现 %d"
                         % (vk_text(vk), n["repeats"], o["repeats"]))
        if n and o:
            if n["delay"] is not None and o["delay"] is not None and abs(n["delay"] - o["delay"]) > 0.05:
                diffs.append("%s 首延迟差 %.0fms（原生 %s / 本实现 %s）"
                             % (vk_text(vk), abs(n["delay"] - o["delay"]) * 1000,
                                fmt_ms(n["delay"]), fmt_ms(o["delay"])))
            if n["interval"] is not None and o["interval"] is not None \
                    and abs(n["interval"] - o["interval"]) > 0.015:
                diffs.append("%s 重复间隔差 %.1fms（原生 %s / 本实现 %s）"
                             % (vk_text(vk), abs(n["interval"] - o["interval"]) * 1000,
                                fmt_ms(n["interval"]), fmt_ms(o["interval"])))
        print("%-28s %-9s %-9s %-9s %-9s %-9s %s"
              % (vk_text(vk),
                 n["runs"] if n else "-", o["runs"] if o else "-",
                 fmt_ms(n["delay"]) if n else "-", fmt_ms(o["delay"]) if o else "-",
                 fmt_ms(n["interval"]) if n else "-", fmt_ms(o["interval"]) if o else "-"))

    print("\n差异清单（%d 项）：" % len(diffs))
    for item in diffs:
        print("  - " + item)
    if not diffs:
        print("  无差异")


def main():
    parser = argparse.ArgumentParser(description="原生驱动与本实现注入的按键序列对照工具")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="录制按键事件")
    rec.add_argument("--out", required=True, help="输出 jsonl 文件")
    rec.add_argument("--label", default="", help="本次录制的标签，例如 原生 / 本实现")
    rec.add_argument("--seconds", type=int, default=0, help="录制时长（秒），0 表示不自动结束")
    rec.add_argument("--stop-vk", type=lambda s: int(s, 0), default=0x77,
                     help="结束录制用的按键 VK，默认 0x77(F8)，0 表示禁用")

    cmp_parser = sub.add_parser("compare", help="比较两份录制结果")
    cmp_parser.add_argument("native", help="原生驱动的录制文件")
    cmp_parser.add_argument("ours", help="本实现的录制文件")

    args = parser.parse_args()
    if args.command == "record":
        record(args.out, args.label or args.out, args.seconds, args.stop_vk)
    else:
        compare(args.native, args.ours)


if __name__ == "__main__":
    main()
