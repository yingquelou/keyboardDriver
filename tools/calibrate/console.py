# -*- coding: utf-8 -*-
"""非阻塞控制台：后台线程读 stdin 成行，主循环永不阻塞在 input() 上。

分类采集与单键采集共用同一个队列：``skip``/``stop``/``done`` 由读键循环取出。
``next_event`` 把"控制台来了一行"与"键盘状态变了"收敛成同一个事件流。
"""

import queue
import sys
import threading
import time

class ConsoleInbox(object):
    """后台线程读控制台行，采集循环只做非阻塞取用。

    原来在提示处用 ``input()`` 等回车：键盘接口被本脚本独占后，这把键盘的
    回车根本到不了控制台，于是"记录一个键 → 卡在提示里"，之后按什么键都没反应。
    现在控制台输入由独立线程读进队列，采集循环在等待下一个键的间隙顺手取一行。
    """

    def __init__(self):
        self._queue = queue.Queue()
        self.closed = False                 # stdin 已 EOF / 不可用
        stream = getattr(sys, 'stdin', None)
        if stream is None:
            self.closed = True
            return
        thread = threading.Thread(target=self._pump, args=(stream,),
                                  name='console-inbox')
        thread.daemon = True
        thread.start()

    def _pump(self, stream):
        while True:
            try:
                line = stream.readline()
            except Exception:
                self.closed = True
                return
            if line == '':
                self.closed = True
                return
            self._queue.put(line.strip())

    def poll(self):
        """非阻塞取一行；没有输入时返回 None"""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None


# 键盘事件之后收集消费类 usage 的窗口，以及允许略微早于键盘事件的回溯量
# （两者同帧上报，先后顺序不固定）。窗口取 200 ms，落在 150–250 ms 的建议区间内。


def next_event(reader, inbox):
    """取下一个事件：('line', 文本) 或 ('change', 变化元组)，都没有时返回 (None, None)

    两边交替轮询，且每次只等很短一段，保证控制台输入不会卡住键盘读取，
    键盘读取也不会让 done 迟迟得不到处理。
    """
    line = inbox.poll()
    if line is not None:
        return 'line', line
    change = reader.wait_change(0.2)
    if change is not None:
        return 'change', change
    return None, None
