# -*- coding: utf-8 -*-
"""设备读取：键盘事件 Reader、消费类监听线程、Num Lock 灯位写入。

硬件原语统一从 keyboard_driver.transport 导入到本模块命名空间，其它模块一律用
``device.xxx`` 调用——需要替换/打桩时只改这一处，不必在各处重复打补丁。
"""

import queue
import threading
import time

from keyboard_driver.transport import (
    find_device, configure_device, read_report, parse_keyboard_report,
    get_device_product, write_led_bitmap,
    find_consumer_endpoint, read_consumer_report, parse_consumer_report,
)

from .constants import NUM_LED_BIT, POLL_MS
from .text import usage_text

def collect_consumer(monitor, event_time):
    """取键盘事件前后小窗口内的消费类 usage；等满窗口以确保同帧不丢

    只在监听已启动时等待这 200 ms；未启动立即返回，不改变原有的按键节奏。
    """
    if monitor is None or not monitor.active:
        return []
    wait = event_time + CONSUMER_WINDOW - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    return monitor.drain(event_time - CONSUMER_BACKDATE)


class Reader(object):
    def __init__(self, dev, ep, emit=None):
        self.dev = dev
        self.ep = ep
        self.emit = emit or print      # 抬起事件也要可见：向导写日志，--watch 直接打印
        self.modifier = 0
        self.keys = []
        self.last_raw = b''            # 最近一帧原始报告（--learn 用它留证）

    def _read_state(self, timeout_ms):
        """读一帧；超时或残包返回 None"""
        raw = read_report(self.dev, self.ep, timeout=timeout_ms)
        if raw is None:
            return None
        modifier, keys = parse_keyboard_report(raw)
        if keys is None:
            return None
        self.last_raw = raw
        return modifier, keys

    def sync(self):
        """把积压报告读空，用最后一帧当基线（避免上次残留的按键被算到下一个键）"""
        last = None
        while True:
            state = self._read_state(POLL_MS)
            if state is None:
                break
            last = state
        if last is not None:
            self.modifier, self.keys = last

    def wait_idle(self, timeout):
        """等到所有键与修饰键都松开；返回是否成功"""
        deadline = time.monotonic() + timeout
        while self.keys or self.modifier:
            if time.monotonic() >= deadline:
                return False
            state = self._read_state(POLL_MS)
            if state is None:
                continue
            self.modifier, self.keys = state
        return True

    def wait_change(self, timeout):
        """等到任何变化；返回 (新增键, 抬起键, 新按修饰位, 松开修饰位) 或 None"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self._read_state(POLL_MS)
            if state is None:
                continue
            modifier, keys = state
            added = [k for k in keys if k not in self.keys]
            removed = [k for k in self.keys if k not in keys]
            mod_down = modifier & ~self.modifier & 0xFF
            mod_up = self.modifier & ~modifier & 0xFF
            self.modifier, self.keys = modifier, keys
            if added or removed or mod_down or mod_up:
                return added, removed, mod_down, mod_up
        return None

    def wait_release(self, usage, timeout):
        """等某个 usage 抬起；返回 True=已抬起，False=超时"""
        deadline = time.monotonic() + timeout
        while usage in self.keys:
            if time.monotonic() >= deadline:
                return False
            state = self._read_state(POLL_MS)
            if state is None:
                continue
            for released in [k for k in self.keys if k not in state[1]]:
                self.emit('      抬起 %s' % usage_text(released))
            self.modifier, self.keys = state
        return True



def set_num_led(log, dev, on):
    """写 Num Lock 灯位来切换固件层；写不进去就无法做灯亮轮"""
    try:
        write_led_bitmap(dev, NUM_LED_BIT if on else 0)
    except Exception as e:
        log.write('错误：写 Num Lock 灯位失败（%s）' % e)
        log.write('      灯位写不进去，固件不会切层，本轮对照没有意义，已中止。')
        return False
    return True



CONSUMER_WINDOW = 0.20
CONSUMER_BACKDATE = 0.15


class ConsumerMonitor(object):
    """后台读消费类接口（接口 1），把 (时间, usage) 放进队列

    分类采集只读键盘接口，而 Fn 组合可能改走消费类接口（音量/多媒体等），
    所以再并行读一条：独立 daemon 线程 + 短超时读，键盘侧的 50 ms 轮询与
    非阻塞控制台模型都不动。查找/claim/读取失败一律降级为"只读键盘"，
    并在本轮开头与日志里如实说明，绝不因此让键盘侧采集失败。
    """

    def __init__(self, log, dev):
        self.log = log
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = None
        self.endpoint = None
        self.reason = None
        try:
            found = find_consumer_endpoint(verbose=False, dev=dev)
        except Exception as e:
            found = None
            self.reason = '查找消费类接口失败：%s' % e
        if found is None:
            self.reason = self.reason or ('未找到可读的消费类接口'
                                          '（描述符无消费类输入报告，或探测读/claim 失败）')
            return
        self.endpoint = found
        self.thread = threading.Thread(target=self._loop, name='consumer-monitor')
        self.thread.daemon = True
        self.thread.start()

    @property
    def active(self):
        return self.thread is not None

    def status_text(self):
        """本轮开头显示的一行状态；未启动时把原因说出来，不静默"""
        if not self.active:
            return '未启动（%s），本轮只读键盘接口' % self.reason
        _, ep, ifno = self.endpoint
        return ('已启动（接口 %d，端点 0x%02X），Fn 组合的消费类 usage 也会记录'
                % (ifno, ep.bEndpointAddress))

    def _loop(self):
        mon_dev, mon_ep, _ = self.endpoint
        while not self.stop_event.is_set():
            try:
                raw = read_consumer_report(mon_dev, mon_ep)
            except Exception as e:
                # 读取失败原地限流重试：不重开设备（重复打开同一复合设备会互相干扰），
                # 也不让主采集失败——键盘侧照常跑，只是这一轮少一条消费类证据。
                self.reason = '消费类接口读取失败：%s' % e
                self.log.write('    [警告] %s（降级：键盘侧采集不受影响，继续原地重试）'
                               % self.reason)
                self.stop_event.wait(0.5)
                continue
            usage = parse_consumer_report(raw)
            # 0x00 是"无键/释放帧"，与 None 一样不入队：否则每个按下帧都会被
            # 一条 "消费类 0x00 -> 未知" 跟一遍，条目数翻倍，还会污染配对。
            if usage:
                self.events.put((time.monotonic(), usage))

    def drain(self, since, keep_time=False):
        """取出时间戳不早于 since 的消费类 usage，并丢掉更早的残留

        ``keep_time`` 为真时返回 [(stamp, usage)]，供点名时打印相对窗口起点的
        时间偏移（如 +0.83s），下次才能回答"这一帧比开始等待早还是晚"。
        """
        got = []
        while True:
            try:
                stamp, usage = self.events.get_nowait()
            except queue.Empty:
                break
            if stamp >= since:
                got.append((stamp, usage) if keep_time else usage)
        return got

    def stop(self):
        """置停止位并 join，确保退出时不残留线程与接口占用"""
        self.stop_event.set()
        if self.thread is None:
            return
        self.thread.join(timeout=2.0)
        if self.thread.is_alive():
            self.log.write('    [警告] 消费类读取线程未在 2 秒内退出'
                           '（daemon 线程，进程退出时由系统回收）。')
        else:
            self.log.write('    消费类监听已停止（线程已收尾）。')
