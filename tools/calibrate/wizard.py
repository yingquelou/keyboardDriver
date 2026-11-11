# -*- coding: utf-8 -*-
"""默认向导：两轮点名六个切层键，逐键判定（J/K/L/U/I/O）。"""

import time

from keyboard_driver import usage as vk_map

from . import device
from .constants import KEY_PLAN, KEY_SPECS, MODIFIER_BITS, NUMPAD_USAGES
from .text import expected_text, usage_text

def judge(spec, round_on, usage):
    """返回 (结论, 说明)；结论取值与汇总口径一致：一致 / usage 不符 / 按错键"""
    name, off_usages, on_usage = spec
    got = usage_text(usage)
    if vk_map.get_vk(usage) is None:
        return 'usage 不符', '上报 %s，usage 里没有这个 usage' % got
    if not round_on:
        if usage in off_usages:
            return '一致', ''
        if usage in NUMPAD_USAGES:
            return 'usage 不符', '灯灭轮却报小键盘 %s，Num Lock 灯位可能不是 0' % got
        return '按错键', '按到了 %s，本键应为 %s' % (got, expected_text(spec, round_on))
    if on_usage is not None:
        if usage == on_usage:
            return '一致', ''
        if usage in off_usages:
            return 'usage 不符', '仍报灯灭轮的 %s，固件没有按灯位改报' % got
        return ('按错键', '按到了 %s，本键在灯亮轮应为 %s'
                % (got, expected_text(spec, round_on)))
    if usage in off_usages:
        return 'usage 不符', '仍报灯灭轮的 %s，固件没有按灯位改报' % got
    if usage in NUMPAD_USAGES:
        return '一致', ''
    return '按错键', '按到了 %s，灯亮轮本键应改报为小键盘 usage' % got



def measure_key(log, reader, spec, round_on, timeout, attempts):
    """点名一个键直到得到结论；返回 (结论, 说明)"""
    name = spec[0]
    verdict, detail = '超时未按', '%g 秒内没有检测到按键' % timeout
    for attempt in range(1, attempts + 1):
        if not reader.wait_idle(5.0):
            log.write('    提示：还有按键没松开，等待超时，继续。')
        reader.sync()
        log.write('')
        log.write('  [%s] 请按 %s（按下后松开；预期 %s）'
                  % (name, name, expected_text(spec, round_on)))
        log.write('        %g 秒内没有按键将判为超时%s'
                  % (timeout, '' if attempt == 1 else '（第 %d 次尝试）' % attempt))
        verdict, detail = _wait_one(log, reader, spec, round_on, timeout)
        if verdict == '一致':
            return verdict, detail
        if attempt < attempts:
            log.write('    -> %s%s，重试本键' %
                      (verdict, ('（%s）' % detail) if detail else ''))
    return verdict, detail


def _wait_one(log, reader, spec, round_on, timeout):
    """在一次等待窗口内取结论；只有抬键/修饰键松开时继续等"""
    deadline = time.monotonic() + timeout
    while True:
        remain = deadline - time.monotonic()
        if remain <= 0:
            return '超时未按', '%g 秒内没有检测到按键' % timeout
        got = reader.wait_change(remain)
        if got is None:
            return '超时未按', '%g 秒内没有检测到按键' % timeout
        added, removed, mod_down, mod_up = got
        for bit, mod_name in MODIFIER_BITS:
            if mod_down & bit:
                log.write('    修饰键 %s 按下' % mod_name)
            if mod_up & bit:
                log.write('    修饰键 %s 抬起' % mod_name)
        for released in removed:
            log.write('    抬起 %s' % usage_text(released))
        if mod_down:
            names = '、'.join(m for b, m in MODIFIER_BITS if mod_down & b)
            return '按错键', '按到了修饰键：%s' % names
        if len(added) > 1:
            return ('多键同帧',
                    '同一帧出现 %d 个键：%s'
                    % (len(added), '、'.join(usage_text(u) for u in added)))
        if not added:
            continue
        usage = added[0]
        log.write('    上报 %s' % usage_text(usage))
        verdict, detail = judge(spec, round_on, usage)
        if verdict == '按错键':
            return verdict, detail
        if not reader.wait_release(usage, timeout):
            log.write('    警告：等不到抬起（可能一直按着），本次结论仍按上报值给出')
        return verdict, detail



def run_round(log, dev, reader, round_on, specs, timeout, attempts, rows):
    label = '灯亮（Num Lock 位=1）' if round_on else '灯灭（Num Lock 位=0）'
    log.write('')
    log.write('=' * 62)
    log.write('【%s】本键清单：%s' % (label, '、'.join(s[0] for s in specs)))
    log.write('=' * 62)
    if not device.set_num_led(log, dev, round_on):
        return False
    if round_on:
        log.write('已把 Num Lock 灯位写为 1，请确认外置键盘的 Num Lock 指示灯已亮。')
    else:
        log.write('已把 Num Lock 灯位写为 0，请确认外置键盘的 Num Lock 指示灯已灭。')
    log.write('   无需回车，直接按清单开始；每按完一个键会自动进入下一个键。')
    reader.sync()
    for spec in specs:
        log.write('')
        log.write('-' * 62)
        log.write('本键：%s    预期：%s' % (spec[0], expected_text(spec, round_on)))
        verdict, detail = measure_key(log, reader, spec, round_on, timeout, attempts)
        log.write('  判定：%s%s' % (verdict, ('（%s）' % detail) if detail else ''))
        rows.append((label, spec[0], expected_text(spec, round_on), verdict, detail))
    return True



def select_specs(log, keys_text):
    if not keys_text:
        return list(KEY_PLAN)
    wanted = [k.strip().upper() for k in keys_text.split(',') if k.strip()]
    unknown = [k for k in wanted if k not in KEY_SPECS]
    if unknown:
        log.write('错误：未知键名 %s（可选：%s）'
                  % ('、'.join(unknown), '、'.join(s[0] for s in KEY_PLAN)))
        return None
    return [spec for spec in KEY_PLAN if spec[0] in wanted]
