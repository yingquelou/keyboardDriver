# -*- coding: utf-8 -*-
"""单键采集（--learn）：按一个记一个，发现未知 usage，可起名并导出 KEYMAP 草稿。"""

import datetime
import os
import re
import time

from . import console, device
from .constants import MODIFIER_BITS
from .paths import LOG_DIR
from .text import hex_raw, round_label, round_short, usage_text

def _vk_const(text):
    """把用户输入规范成 win32con.VK_xxx；不是 VK 常量名则返回 None"""
    if not text:
        return None
    name = text.strip()
    if name.lower().startswith('win32con.'):
        name = name[len('win32con.'):]
    if re.match(r'(?i)^vk_[a-z0-9_]+$', name):
        return 'win32con.' + name.upper()
    return None


class LearnDraft(object):
    """一轮采集的结果：usage → 名称，按首次出现排序并去重"""

    def __init__(self, round_on, path, product, stamp):
        self.round_on = round_on
        self.path = path
        self.product = product
        self.stamp = stamp
        self.entries = []
        self.seen = {}
        self.mod_notes = []
        self.pending = []       # 还没处理命名提示的键（后进先出：命名给最近那个）

    def record(self, usage, raw, mods, same_frame):
        """记录一个新 usage；已记录过则返回 False"""
        if usage in self.seen:
            return False
        entry = {
            'usage': usage,
            'raw': raw,
            'mods': mods,
            'name': None,
            'order': len(self.entries) + 1,
            'same_frame': same_frame,
        }
        self.entries.append(entry)
        self.seen[usage] = entry
        self.pending.append(entry)
        return True

    def take_pending(self):
        """取出最近一个等待命名的键；没有则返回 None"""
        return self.pending.pop() if self.pending else None

    def items_text(self):
        result = []
        for entry in self.entries:
            const = _vk_const(entry['name'])
            result.append('0x%02X -> %s' % (entry['usage'], const or '未命名'))
        return result


def render_draft(draft, sibling):
    """生成可直接粘贴进 usage.py 的文本；两份草稿互相注明"""
    lines = [
        '# ===== tools/calibrate --learn 采集草稿：%s =====' % round_label(draft.round_on),
        '# 采集时间：%s' % datetime.datetime.strptime(draft.stamp, '%Y%m%d_%H%M%S')
                                 .strftime('%Y-%m-%d %H:%M:%S'),
        '# 设备：%s' % draft.product,
        '# 说明：本次采集内 usage 去重，按首次出现顺序排列；',
        '#       未命名的行是占位注释，确认后去掉行首 # 并替换 VK_???。',
    ]
    if sibling is None:
        lines.append('# 对照：本轮未采集（--rounds 只跑了单轮）')
    else:
        lines.append('# 对照：%s（%s）' % (os.path.basename(sibling.path),
                                        round_short(sibling.round_on)))
        lines.append('#       该轮记录：%s' % ('、'.join(sibling.items_text()) or '无'))
    lines.append('')
    lines.append('KEYMAP.update({')
    for entry in draft.entries:
        note = '第 %d 个（%s' % (entry['order'], round_short(draft.round_on))
        if entry['same_frame']:
            note += '，同帧多键'
        if entry['mods']:
            note += '，同时按着 %s' % entry['mods']
        note += '，原始 %s）' % hex_raw(entry['raw'])
        const = _vk_const(entry['name'])
        if const:
            lines.append('    0x%02X: %s,    # %s' % (entry['usage'], const, note))
        else:
            extra = ('；备注名：%s' % entry['name']) if entry['name'] else ''
            lines.append('    # 0x%02X: win32con.VK_???    # %s%s'
                         % (entry['usage'], note, extra))
    lines.append('})')
    if draft.mod_notes:
        lines.append('')
        lines.append('# ---- 修饰键位图变化（走修饰键字节，不进 KEYMAP，仅供核对）----')
        for note in draft.mod_notes:
            lines.append('# %s' % note)
    return '\n'.join(lines)


def _consume_line(log, draft, text):
    """处理一行控制台输入；返回 True 表示本轮结束

    空行 = 跳过命名；done/q/quit = 结束本轮；其它文本 = 给最近记录的那个键命名。
    """
    command = text.strip()
    if command.lower() in ('done', 'q', 'quit'):
        log.write('    收到 done，结束本轮。')
        return True
    entry = draft.take_pending()
    if not command:
        if entry is not None:
            log.write('    跳过命名 %s' % usage_text(entry['usage']))
        return False
    if entry is None:
        log.write('    命名已忽略（没有待命名的键）：%s' % command)
        return False
    entry['name'] = command
    log.write('    命名 %s -> %s' % (usage_text(entry['usage']), command))
    return False




def collect_learn_round(log, dev, reader, round_on, product, stamp, inbox):
    """采集一轮；返回 LearnDraft，灯位写不进去时返回 None

    采集循环不阻塞在控制台输入上：记录完一个键立刻回到等待下一个键，
    ``done``/命名由 ConsoleInbox 后台线程收到的行触发。
    """
    draft = LearnDraft(round_on,
                       os.path.join(LOG_DIR, 'learn_%s_%s.txt'
                                    % (stamp, 'on' if round_on else 'off')),
                       product, stamp)
    log.write('')
    log.write('=' * 62)
    log.write('【采集：%s】' % round_label(round_on))
    log.write('=' * 62)
    if not device.set_num_led(log, dev, round_on):
        return None
    if round_on:
        log.write('已把 Num Lock 灯位写为 1，请确认外置键盘的 Num Lock 指示灯已亮。')
    else:
        log.write('已把 Num Lock 灯位写为 0，请确认外置键盘的 Num Lock 指示灯已灭。')
    log.write('按一个键 → 记录 usage 与原始报告 → 立刻回到等待下一个键（不需要回车）。')
    log.write('一次只针对一个键：常规键、厂商自定义键、Fn 组合都可以，不用提前准备清单。')
    log.write('起名可选：在两次按键之间输入名字并回车，作用于最近记录的那个键；')
    log.write('空回车跳过命名，输入 done 结束本轮，或随时 Ctrl+C。')
    if inbox.closed:
        log.write('注意：控制台输入不可用（stdin 已关闭），本轮只能用 Ctrl+C 结束。')
    else:
        log.write('（起名/done 需要另一把键盘或屏幕键盘，这把键盘的接口已被本脚本独占。）')
    reader.sync()

    try:
        while True:
            kind, payload = console.next_event(reader, inbox)
            if kind == 'line':
                if _consume_line(log, draft, payload):
                    break
                continue
            if kind != 'change':
                continue
            added, removed, mod_down, mod_up = payload
            for bit, name in MODIFIER_BITS:
                if mod_down & bit:
                    log.write('    修饰键 %s 按下（位图 0x%02X）' % (name, bit))
                    draft.mod_notes.append('修饰键 %s 按下（修饰键位图 0x%02X）' % (name, bit))
                if mod_up & bit:
                    log.write('    修饰键 %s 抬起（位图 0x%02X）' % (name, bit))
                    draft.mod_notes.append('修饰键 %s 抬起（修饰键位图 0x%02X）' % (name, bit))
            for released in removed:
                log.write('    抬起 %s（不是新键，不记录）' % usage_text(released))
            if not added:
                continue
            raw = reader.last_raw
            same_frame = len(added) > 1
            if same_frame:
                log.write('    同一帧上报 %d 个键：%s'
                          % (len(added), '、'.join(usage_text(u) for u in added)))
            else:
                log.write('    按下 %s（原始 %s）' % (usage_text(added[0]), hex_raw(raw)))
            mods = '、'.join(name for bit, name in MODIFIER_BITS
                            if reader.modifier & bit) or None
            fresh = []
            for usage in added:
                if draft.record(usage, raw, mods, same_frame):
                    fresh.append(usage)
                else:
                    log.write('      %s 本次采集已记录过，跳过（继续按下一个键）'
                              % usage_text(usage))
            for usage in fresh:
                log.write('      已记录 %s（原始 %s）' % (usage_text(usage), hex_raw(raw)))
            if fresh:
                log.write('      （可选）输入名字并回车可命名；继续按下一个键即跳过。')
    except KeyboardInterrupt:
        log.write('')
        log.write('    已结束本轮采集（Ctrl+C）。')
    return draft


def learn_mode(log, dev, ep, args):
    """单键采集入口：逐轮采集后写两份草稿（互相注明）"""
    product = device.get_device_product(dev)
    reader = device.Reader(dev, ep, emit=log.write)
    rounds = {'both': (False, True), 'off': (False,), 'on': (True,)}[args.rounds]
    inbox = console.ConsoleInbox()
    drafts = {}
    failed = False
    for round_on in rounds:
        draft = collect_learn_round(log, dev, reader, round_on, product, log.stamp, inbox)
        if draft is None:
            failed = True
            break
        drafts[round_on] = draft
    for round_on, draft in drafts.items():
        text = render_draft(draft, drafts.get(not round_on))
        try:
            with open(draft.path, 'w', encoding='utf-8') as handle:
                handle.write(text + '\n')
        except OSError as e:
            log.write('错误：写草稿失败（%s）' % e)
            failed = True
            continue
        log.write('')
        log.write('=' * 62)
        log.write('草稿（%s）：%s' % (round_label(draft.round_on), draft.path))
        log.write('=' * 62)
        for line in text.splitlines():
            log.write(line)
    return 1 if failed else 0
