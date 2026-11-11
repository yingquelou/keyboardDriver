# -*- coding: utf-8 -*-
"""分类采集（--learn --categories）：逐类逐项点名、两轮判定、skip/stop/done、类小结。

``--categories-file`` 的类在 run 之前注册进来，之后的流程与内建类完全一致。
"""

import time

from . import catalog, catalog_file, console, device, report
from .catalog_file import apply_category_file
from .constants import (LAYER_KEYS, MEASURED_LAYER_TARGETS, MODIFIER_BITS)
from .judge import judge_target, target_expected, _judge_record
from .planning import (ask_categories, build_plan, parse_categories,
                       parse_layer_keys, parse_layer_pairs)
from .text import consumer_text, hex_raw, round_label, usage_text


def _consumer_events_text(got, window_start):
    """[(stamp, usage)] → '0xB6 -> 上一曲(+0.83s)、…'；偏移是本键开始等待后的秒数"""
    return '、'.join('%s(+%.2fs)' % (consumer_text(usage), stamp - window_start)
                     for stamp, usage in got)


def plan_for_round(plan, round_on):
    """灯亮轮去掉只跑单轮的类（fn 的消费类报表与 Num Lock 层无关，两轮结果相同）"""
    if not round_on:
        return list(plan)
    return [entry for entry in plan if entry[0] not in catalog.SINGLE_ROUND_CATEGORIES]


def _wait_target(log, reader, target, round_on, timeout, inbox,
                 layer_pairs=None, plan_usages=None,
                 layer_keys=None, off_seen=None, observed=None, monitor=None):
    """在一次等待窗口内取结论；返回 (结论, 说明, 动作)

    动作：None=正常取到结论，'stop'=用户结束当前类，'done'=用户结束整轮/整次运行。
    ``monitor`` 是已启动的消费类监听；没有时行为与之前完全一致。
    """
    window_start = time.monotonic()
    if monitor is not None and monitor.active:
        # 清掉上一颗键/上一窗口的残留：否则上一颗的消费类 usage 会被算进本键，
        # 出现"本键窗口里没有自己的 usage 却判一致"的假阳性。
        monitor.drain(window_start)
    deadline = window_start + timeout
    while True:
        if time.monotonic() >= deadline:
            if monitor is not None and monitor.active:
                got = monitor.drain(window_start - device.CONSUMER_BACKDATE,
                                    keep_time=True)
                if got:
                    text = _consumer_events_text(got, window_start)
                    if target.record:
                        if target.fn:
                            return ('一致', '键盘接口无报告；收到 %s（Fn 组合走了消费类接口）'
                                    % text, None)
                        return ('一致', '键盘接口无报告；收到 %s（走的是消费类接口）'
                                % text, None)
                    return ('超时未按', '%g 秒内没有检测到键盘按键；期间收到 %s'
                            % (timeout, text), None)
            return '超时未按', '%g 秒内没有检测到按键' % timeout, None
        kind, payload = console.next_event(reader, inbox)
        if kind == 'line':
            command = payload.strip().lower()
            if command in ('done', 'q', 'quit'):
                log.write('    收到 done，结束本次采集（已完成部分照常落盘）。')
                return '未采集', '用户输入 done 结束本次采集', 'done'
            if command in ('stop', 'next'):
                log.write('    收到 stop，结束当前类，继续下一类。')
                return '跳过', '用户输入 stop 结束本类', 'stop'
            if command in ('skip', 's'):
                log.write('    已跳过本键，继续下一个键。')
                return '跳过', '用户输入 skip', None
            if command:
                log.write('    未知命令：%s（可用：skip 跳过本键、stop 结束本类、'
                          'done 结束整次、Ctrl+C 退出）' % payload)
            continue
        if kind != 'change':
            # Fn 组合、以及清单文件里没有结构化预期的条目，可能只走消费类接口：
            # 收到就立刻打印并推进，不等窗口到期。常规键/切层键仍以键盘接口的报告为准
            # （消费类只做旁证）。
            if (target.record and (target.fn or not target.vks)
                    and monitor is not None and monitor.active):
                got = monitor.drain(window_start, keep_time=True)
                if got:
                    text = _consumer_events_text(got, window_start)
                    log.write('    上报 %s' % text)
                    if target.fn:
                        return ('一致', '键盘接口无报告；收到 %s（Fn 组合走了消费类接口）'
                                % text, None)
                    return ('一致', '键盘接口无报告；收到 %s（清单项照实记录，'
                            '走的是消费类接口）' % text, None)
            continue
        added, removed, mod_down, mod_up = payload
        for bit, mod_name in MODIFIER_BITS:
            if mod_down & bit:
                log.write('    修饰键 %s 按下' % mod_name)
            if mod_up & bit:
                log.write('    修饰键 %s 抬起' % mod_name)
        for released in removed:
            log.write('    抬起 %s' % usage_text(released))
        if target.mod_bit:
            if mod_down & target.mod_bit:
                log.write('    上报 修饰键位图 0x%02X（原始 %s）'
                          % (target.mod_bit, hex_raw(reader.last_raw)))
                return '一致', '', None
            if mod_down:
                names = '、'.join(m for b, m in MODIFIER_BITS if mod_down & b)
                return ('按错键', '按到了修饰键：%s，本键应为 %s'
                        % (names, target.label), None)
            if added:
                return ('按错键', '按到了 %s，本键应为修饰键 %s'
                        % ('、'.join(usage_text(u) for u in added), target.label), None)
            continue
        if mod_down:
            names = '、'.join(m for b, m in MODIFIER_BITS if mod_down & b)
            return '按错键', '按到了修饰键：%s' % names, None
        if target.record:
            if not added:
                continue
            log.write('    上报 %s（原始 %s）'
                      % ('、'.join(usage_text(u) for u in added), hex_raw(reader.last_raw)))
            if observed is not None:
                observed[target.label] = added[0]
            verdict, detail = _judge_record(target, added)
            consumer = device.collect_consumer(monitor, time.monotonic())
            if consumer:
                detail = '%s；同时收到 %s' % (
                    detail, '、'.join(consumer_text(u) for u in consumer))
            for usage in added:
                if not reader.wait_release(usage, timeout):
                    log.write('    警告：等不到抬起（可能一直按着），继续。')
            return verdict, detail, None
        if len(added) > 1:
            return ('多键同帧', '同一帧出现 %d 个键：%s'
                    % (len(added), '、'.join(usage_text(u) for u in added)), None)
        if not added:
            continue
        usage = added[0]
        log.write('    上报 %s（原始 %s）' % (usage_text(usage), hex_raw(reader.last_raw)))
        if observed is not None:
            observed[target.label] = usage
        verdict, detail = judge_target(
            target, round_on, usage, layer_pairs, plan_usages,
            off_usage=(off_seen or {}).get(target.label), layer_keys=layer_keys)
        consumer = device.collect_consumer(monitor, time.monotonic())
        if consumer:
            detail = '%s；同时收到 %s' % (
                (detail or ''), '、'.join(consumer_text(u) for u in consumer))
        if verdict == '一致' and not reader.wait_release(usage, timeout):
            log.write('    警告：等不到抬起（可能一直按着），继续。')
        return verdict, detail, None


def measure_target(log, reader, target, round_on, timeout, attempts, inbox, index, total,
                   layer_pairs=None, plan_usages=None, layer_keys=None,
                   off_seen=None, observed=None, monitor=None):
    """点名一个键直到得到结论；返回 (结论, 说明, 动作)

    按错/超时只重试本键，重试用完就记下结论继续下一个键——一次按错不会让整类作废。
    可选项（target.optional）重试用完仍完全没收到报告时改记「无此键」，不计失败。
    """
    verdict, detail = '超时未按', '%g 秒内没有检测到按键' % timeout
    for attempt in range(1, attempts + 1):
        if not reader.wait_idle(5.0):
            log.write('    提示：还有按键没松开，等待超时，继续。')
        reader.sync()
        log.write('')
        log.write('  [%s] 请按 %s（%d/%d%s；按下后松开；预期 %s）'
                  % (target.label, target.pos or target.label, index, total,
                     '，可选项' if target.optional else '',
                     target_expected(target, round_on, layer_pairs, layer_keys)))
        log.write('        %g 秒内没有按键将判为超时%s'
                  % (timeout, '' if attempt == 1 else '（第 %d 次尝试）' % attempt))
        if target.note:
            log.write('        备注：%s' % target.note)
        verdict, detail, action = _wait_target(log, reader, target, round_on,
                                               timeout, inbox,
                                               layer_pairs, plan_usages,
                                               layer_keys, off_seen, observed,
                                               monitor)
        if action:
            return verdict, detail, action
        if verdict in ('一致', '跳过', '切层映射偏差（发现）'):
            return verdict, detail, None
        if target.record and target.optional and verdict == '超时未按':
            if target.fn:
                if monitor is not None and monitor.active:
                    log.write('    -> Fn 组合在键盘与消费类接口都没有上报：可能由固件本地'
                              '处理。记「无上报」，不计失败，继续下一个键。')
                    return ('无上报', '键盘与消费类接口均无上报（可能由固件本地处理）', None)
                log.write('    -> Fn 组合没有收到任何键盘报告：可能由固件本地处理，或走的是'
                          '本轮未监听的消费类接口。记「无上报」，不计失败，继续下一个键。')
                return ('无上报', '键盘接口无上报（可能由固件本地处理，或走本轮未监听的'
                                  '消费类接口）', None)
            log.write('    -> 清单项可选项：没有收到任何报告，记「无上报」，'
                      '不计失败，继续下一个键。')
            if monitor is not None and monitor.active:
                return ('无上报', '清单项可选项：键盘与消费类接口均无上报', None)
            return ('无上报', '清单项可选项：键盘接口无上报', None)
        if attempt < attempts:
            log.write('    -> %s%s，重试本键（输入 skip 跳过本键、stop 结束本类、'
                      'done 结束整次）'
                      % (verdict, ('（%s）' % detail) if detail else ''))
    if target.optional and verdict == '超时未按':
        log.write('    -> 可选项：%d 次尝试都没有收到任何报告，记「无此键」'
                  '（该键盘可能没有这个键），自动进入下一个键。' % attempts)
        return ('无此键', '可选项：%d 次尝试内没有收到任何报告（该键盘可能没有这个键）'
                % attempts, None)
    if verdict == '超时未按':
        log.write('    -> 必要项：%d 次尝试都没有收到任何报告，记为失败。'
                  '若这把键盘确实没有此键，可用 --optional 把该类改为可选项。' % attempts)
        return verdict, detail, None
    log.write('    -> 本键记为 %s，继续下一个键（不影响其它键）。' % verdict)
    return verdict, detail, None


def _class_summary(targets, stat):
    """一类完成后的小结：记录了几项、无此键/偏差/失败的是哪些键"""
    parts = []
    for name in ('一致', '无此键', '无上报', '切层映射偏差（发现）', '未按灯位改报',
                 '不应切层却改报', 'usage 不符', '按错键',
                 '来源不明（需复测）', '多键同帧', '超时未按', '跳过', '未采集'):
        labels = stat.get(name)
        if labels:
            parts.append('%s %d（%s）' % (name, len(labels), '、'.join(labels)))
    return '共 %d 项：%s' % (len(targets), '；'.join(parts) or '无')


NO_REPORT_LIMIT = 3      # 连续这么多项完全收不到报告，先确认是不是设备没就绪
NO_REPORT_WAIT = 20.0    # 停下来询问时的等待秒数；无输入按中止处理


def _confirm_alive(log, inbox, silent):
    """连续 N 项没有任何报告时的守卫；返回 True=继续，False=中止

    连按键都一帧没收到，通常不是这些键不存在，而是驱动没停、键盘断连或接口不对；
    直接把它们记成「无此键」会把整类误判成缺键，所以先停下来明确问一句。
    """
    log.write('')
    log.write('!' * 62)
    log.write('连续 %d 项完全没有收到任何按键报告（不只是超时，是一帧都没有）。' % silent)
    log.write('这更像是设备没就绪或接口不对，而不是这些键都不存在：')
    log.write('  1) python -m keyboard_driver 等驱动是否已经停止？')
    log.write('  2) 接收器/键盘是否还连着，接口是否仍绑着 WinUSB？')
    log.write('  3) 刚才那几项可以稍后重跑同一类复核。')
    if inbox.closed:
        log.write('控制台输入不可用，按中止处理（已采部分照常落盘）。')
        return False
    log.write('输入 continue 继续采集，或 abort 中止；%g 秒内无输入按中止处理。'
              % NO_REPORT_WAIT)
    deadline = time.monotonic() + NO_REPORT_WAIT
    while time.monotonic() < deadline:
        line = inbox.poll()
        if line is None:
            time.sleep(0.05)
            continue
        command = line.strip().lower()
        if command in ('continue', 'c', 'yes', 'y', 'skip', 's'):
            log.write('继续采集（若仍旧没有任何报告，后面还会再提示）。')
            return True
        if command in ('abort', 'a', 'no', 'n', 'done', 'q', 'quit', 'stop'):
            log.write('已中止本轮采集。')
            return False
        if command:
            log.write('  未知命令：%s（continue 继续 / abort 中止）' % line)
    log.write('%g 秒内没有输入，按中止处理。' % NO_REPORT_WAIT)
    return False


def run_range_round(log, dev, reader, round_on, plan, timeout, attempts, rows, inbox,
                    layer_pairs=None, layer_keys=None, off_seen=None, observed=None,
                    monitor=None):
    """按类别跑一轮；返回 'ok' / 'done'（用户结束整次）/ 'abort'（连续无报告中止）
    / 'led_fail'（灯位写不进去）

    ``plan`` 是 [(类名, 说明, 目标元组)]，已按 --required/--optional 覆盖过。
    ``layer_pairs`` 是灯亮轮的逐键配对表（默认取实测值，可被 --layer-pair 覆盖）；
    ``layer_keys`` 是"会切层"的实体键集合；``off_seen`` 是灯灭轮已实测到的 usage，
    用于灯亮轮做两轮比对；``observed`` 收集本轮实际收到的 usage。
    """
    layer_pairs = dict(layer_pairs or MEASURED_LAYER_TARGETS)
    layer_keys = LAYER_KEYS if layer_keys is None else layer_keys
    plan_usages = frozenset(u for _, _, targets in plan
                            for target in targets for u in target.vks)
    label = round_label(round_on)
    log.write('')
    log.write('=' * 62)
    log.write('【分类采集：%s】' % label)
    log.write('=' * 62)
    if not device.set_num_led(log, dev, round_on):
        return 'led_fail'
    log.write('已把 Num Lock 灯位写为 %d，请确认外置键盘的 Num Lock 指示灯已%s。'
              % (1 if round_on else 0, '亮' if round_on else '灭'))
    has_fn = any(category == 'fn' for category, _, _ in plan)
    has_non_fn = any(category != 'fn' for category, _, _ in plan)
    if has_fn:
        log.write('   常规类不需要 Fn，提示一颗就只按那一颗；fn 类需要按住 Fn 再按提示的 F 键。')
        log.write('   Fn 本身通常不上报，Fn 组合的结果可能是改报、消费类 usage 或无上报。')
    else:
        log.write('   本模式不需要 Fn，也不需要按组合键；提示一颗就只按那一颗。')
    log.write('   消费类监听：%s。'
              % (monitor.status_text() if monitor is not None
                 else '未启用（只读键盘接口）'))
    if round_on and has_non_fn:
        log.write('   灯亮轮同一颗物理键可能被固件改报为小键盘 usage（例如字母区 J 报')
        log.write('   0x59 = 小键盘 1），属于正常切层，不是按错；仍按点名的那一颗即可。')
        log.write('   判定按实测配对逐键比对（15 个小键盘 usage）；落在其中但配对不符')
        log.write('   记为「切层映射偏差（发现）」，不算失败；不落其中才记失败。')
        log.write('   其余键两轮 usage 必须完全相同，发生改报即记失败。')
    log.write('   无需回车：按完一个键自动进入下一个；skip 跳过本键，')
    log.write('   stop 结束本类，done 结束整次（已采的照常落盘）。')
    log.write('   分类采集不起名：键名就是点名给出的名字，实收与预期不符会照实标注。')
    reader.sync()
    ended = False
    aborted = False
    silent = 0              # 连续"完全没有报告"的项数
    silent_required = False  # 这段连续项里是否含必要项
    for cat_index, (category, summary, targets) in enumerate(plan):
        if ended or aborted:
            reason = '本轮已提前结束' if ended else '连续多项无报告，已中止'
            for target in targets:
                rows.append((label, target.label,
                             target_expected(target, round_on, layer_pairs, layer_keys),
                             '未采集', reason))
            continue
        log.write('')
        log.write('-' * 62)
        log.write('【%s】%s' % (category, summary))
        log.write('-' * 62)
        if category in catalog.SINGLE_ROUND_CATEGORIES:
            log.write('   本类必须按住 Fn；单独按只会出主功能键 F1..F10（无 Fn 副功能）。')
            log.write('   只跑一轮：Fn 组合的消费类报表与 Num Lock 层无关。')
            log.write('   Fn 组合通常只走消费类接口，收到即刻打印并进入下一项。')
        opt_labels = [t.label for t in targets if t.optional]
        if opt_labels:
            log.write('  可选项（重试用完仍无报告会自动记「无此键」，不计失败）：%s'
                      % '、'.join(opt_labels))
        stat = {}
        class_stopped = False
        for index, target in enumerate(targets, 1):
            if ended or class_stopped or aborted:
                rows.append((label, target.label,
                             target_expected(target, round_on, layer_pairs, layer_keys),
                             '未采集', '本类已提前结束'))
                stat.setdefault('未采集', []).append(target.label)
                continue
            verdict, detail, action = measure_target(log, reader, target, round_on,
                                                    timeout, attempts, inbox,
                                                    index, len(targets),
                                                    layer_pairs, plan_usages,
                                                    layer_keys, off_seen, observed,
                                                    monitor)
            log.write('  判定：%s%s' % (verdict, ('（%s）' % detail) if detail else ''))
            rows.append((label, target.label,
                         target_expected(target, round_on, layer_pairs, layer_keys),
                         verdict, detail))
            stat.setdefault(verdict, []).append(target.label)
            if verdict in ('超时未按', '无此键'):
                silent += 1
                if not target.optional:
                    silent_required = True
            else:
                silent = 0
                silent_required = False
            if action == 'done':
                ended = True
            elif action == 'stop':
                class_stopped = True
            if (not ended and not class_stopped and silent >= NO_REPORT_LIMIT
                    and silent_required):
                if _confirm_alive(log, inbox, silent):
                    silent = 0
                    silent_required = False
                else:
                    aborted = True
        if ended:
            log.write('  【%s】已提前结束：%s' % (category, _class_summary(targets, stat)))
            log.write('  done 之后不再进入后续类别与后续轮次。')
            break
        log.write('  【%s 完成】%s' % (category, _class_summary(targets, stat)))
        if class_stopped:
            log.write('  （本类由 stop 提前结束，剩余键记未采集）')
        if aborted:
            log.write('  连续 %d 项没有任何报告，本轮采集已中止。' % NO_REPORT_LIMIT)
            log.write('  已采部分照常落盘；请检查驱动/连接后重跑本类。')
            break
        if cat_index + 1 < len(plan):
            nxt, nxt_summary, nxt_targets = plan[cat_index + 1]
            log.write('  -> 继续下一类：%s（%s）。直接按下一类的第一个键「%s」即可继续；'
                      '输入 done 结束整次。'
                      % (nxt, nxt_summary, nxt_targets[0].label))
    return 'abort' if aborted else ('done' if ended else 'ok')



def range_mode(log, dev, ep, args):
    """分类采集入口：先选类，再在类内逐个点名；两轮判定并落盘"""
    inbox = console.ConsoleInbox()
    categories_file = getattr(args, 'categories_file', None)
    if categories_file and not apply_category_file(
            log, categories_file, getattr(args, 'categories_file_only', False)):
        return 1
    if args.categories:
        categories = parse_categories(log, args.categories)
    else:
        categories = ask_categories(log, inbox)
    if categories is None:
        return 1
    plan = build_plan(log, categories, args.required, args.optional)
    if plan is None:
        return 1
    layer_pairs = dict(MEASURED_LAYER_TARGETS)
    overrides = parse_layer_pairs(log, args.layer_pair)
    if overrides is None:
        return 1
    layer_pairs.update(overrides)
    layer_keys = parse_layer_keys(log, args.layer_key)
    if args.layer_key is not None and layer_keys is None:
        return 1
    if layer_keys is None:
        layer_keys = LAYER_KEYS
    attempts = 1 if args.no_retry else max(1, args.attempts)
    total = sum(len(targets) for _, _, targets in plan)
    optional_total = sum(1 for _, _, targets in plan for t in targets if t.optional)
    reader = device.Reader(dev, ep, emit=log.write)
    rounds = {'both': (False, True), 'off': (False,), 'on': (True,)}[args.rounds]
    log.write('')
    log.write('本次选中 %d 类，共 %d 个键/轮（必要项 %d，可选项 %d）；按类别逐个点名。'
              % (len(plan), total, total - optional_total, optional_total))
    for name, summary, targets in plan:
        optional_count = sum(1 for t in targets if t.optional)
        if optional_count == 0:
            mark = '必要'
        elif optional_count == len(targets):
            mark = '可选'
        else:
            mark = '部分可选'
        log.write('  %-10s %-6s %s' % (name, mark, summary))
    log.write('按错或超时会重试本键；可选项重试用完仍无报告时记「无此键」并自动继续，')
    log.write('不计失败；必要项超时记为失败（可用 --optional 把某类整体改为可选）。')
    log.write('设备事实（实测）：灯亮轮只有 %d 颗键会改报小键盘 usage（%s）；'
              % (len(layer_keys), ' '.join(sorted(layer_keys))))
    log.write('其余键两轮 usage 必须完全相同，发生改报即记失败（换键盘需重新确认）。')
    log.write('切层键落在 15 个小键盘 usage 内但配对不符记「切层映射偏差（发现）」，')
    log.write('不算失败；不落 15 个之内、或该改报却没改报，都记失败。')
    log.write('skip 跳过本键，stop 结束当前类，done 结束整次（已完成部分照常落盘）。')
    log.write('若连续 %d 项完全收不到任何报告，会先停下来确认设备是否就绪。'
              % NO_REPORT_LIMIT)
    if inbox.closed:
        log.write('注意：控制台输入不可用（stdin 已关闭），只能按 Ctrl+C 结束。')
    else:
        log.write('（skip/stop/done 需要另一把键盘或屏幕键盘，这把键盘的接口已被本脚本独占。）')
    rows = []
    observed = {}
    off_seen = {}
    # 消费类监听：Fn 组合可能改走接口 1。启动失败/读取失败都只降级，不影响键盘侧采集。
    monitor = device.ConsumerMonitor(log, dev)
    log.write('消费类监听：%s。' % monitor.status_text())
    try:
        for round_on in rounds:
            round_plan = plan_for_round(plan, round_on)
            if not round_plan:
                log.write('')
                log.write('跳过灯亮轮：选中的类都只跑单轮（%s）。'
                          % '、'.join(sorted(catalog.SINGLE_ROUND_CATEGORIES)))
                continue
            status = run_range_round(log, dev, reader, round_on, round_plan,
                                     args.timeout, attempts, rows, inbox,
                                     layer_pairs=layer_pairs, layer_keys=layer_keys,
                                     off_seen=off_seen if round_on else None,
                                     observed=None if round_on else observed,
                                     monitor=monitor)
            if not round_on:
                off_seen = dict(observed)
            if status == 'led_fail':
                return 1
            if status == 'done':
                log.write('')
                log.write('done：本次采集到此结束，不再执行后续轮次。')
                break
            if status == 'abort':
                log.write('')
                log.write('本轮因连续无报告而中止，不再执行后续轮次。')
                break
    except KeyboardInterrupt:
        log.write('')
        log.write('已中断（Ctrl+C），下面是已完成部分的汇总。')
    finally:
        monitor.stop()
    return 0 if report.summarize(log, rows) else 1
