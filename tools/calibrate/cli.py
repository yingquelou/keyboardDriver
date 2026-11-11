# -*- coding: utf-8 -*-
"""命令行入口：参数解析与模式分发（向导 / --learn / --learn --categories / --watch）。"""

import argparse
import datetime
import sys

import usb.core

from . import catalog, constants, device, learn as learn_flow
from . import range_mode as range_flow
from . import report, watch, wizard

def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='键盘核对/采集工具：向导（默认）、单键采集（--learn）、'
                    '分类采集（--learn --categories）、被动翻译（--watch）')
    parser.add_argument('--keys',
                        help='只核对指定键，逗号分隔（可选：%s）'
                             % '、'.join(s[0] for s in constants.KEY_PLAN))
    parser.add_argument('--rounds', choices=('both', 'off', 'on'), default='both',
                        help='both=灯灭+灯亮（默认），off=只灯灭，on=只灯亮')
    parser.add_argument('--timeout', type=float, default=constants.TIMEOUT_DEFAULT,
                        help='每个键的等待秒数（默认 %g）' % constants.TIMEOUT_DEFAULT)
    parser.add_argument('--attempts', type=int, default=constants.ATTEMPTS_DEFAULT,
                        help='每个键最多尝试次数（默认 %d）' % constants.ATTEMPTS_DEFAULT)
    parser.add_argument('--no-retry', action='store_true',
                        help='失败不重试（等价于 --attempts 1）')
    parser.add_argument('--watch', action='store_true',
                        help='老用法：常驻打印每个键的 HID 码，不做判定')
    parser.add_argument('--learn', action='store_true',
                        help='单键采集：一次一个键，记录未知 usage 并导出 usage 草稿'
                             '（忽略 --keys）')
    parser.add_argument('--categories', '--cats', '--groups', nargs='*',
                        metavar='LIST',
                        help='配合 --learn 的分类采集：先选类，再在类内逐项点名。'
                             '可逗号/空格分隔多个或写 all；省略值则交互选择'
                             '（可选：%s）' % '、'.join(catalog.CATEGORY_ORDER))
    parser.add_argument('--required', nargs='+', metavar='CATEGORY',
                        help='配合 --learn --categories：把指定类整体当作必要项，'
                             '超时即记失败（默认必要项：a-z、0-9、symbols、control、f1-f12）')
    parser.add_argument('--optional', nargs='+', metavar='CATEGORY',
                        help='配合 --learn --categories：把指定类整体当作可选项，'
                             '重试用完仍无报告时记「无此键」并自动继续，不计失败'
                             '（默认可选项：edit、arrows、modifiers 里的右Win）。'
                             '同一类同时出现在两个参数里时按必要项处理')
    parser.add_argument('--layer-pair', nargs='+', metavar='KEY=USAGE',
                        help='配合 --learn --categories：增补/覆盖灯亮轮的逐键配对，'
                             '例如 J=0x59；usage 必须在 15 个小键盘 usage 内')
    parser.add_argument('--categories-file', metavar='PATH',
                        help='配合 --learn --categories：从 JSON 清单文件加载类别与键'
                             '（与内建类共存；同名类用文件里的定义整体替换）。'
                             '键只有 label 必填，pos/expect/note/optional/fn 都可省')
    parser.add_argument('--categories-file-only', action='store_true',
                        help='只认 --categories-file 里的类，内建类不再可选')
    parser.add_argument('--layer-key', nargs='+', metavar='KEY',
                        help='配合 --learn --categories：覆盖"灯亮轮会切层"的键集合'
                             '（默认 7 8 9 0 U I O P J K L ; M . /）')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    attempts = 1 if args.no_retry else max(1, args.attempts)

    log = report.Log()
    log.write('=' * 62)
    log.write('键盘核对/采集  %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    log.write('=' * 62)
    log.write('说明：本脚本用 pyusb 直读键盘接口，会独占该接口。')
    log.write('      不要与 python -m keyboard_driver 同时运行——驱动在跑时读不到键盘。')
    log.write('      键盘接口需已绑 WinUSB（Zadig），否则 find_device 会失败。')

    dev = None
    try:
        try:
            dev = device.find_device()
        except Exception as e:
            log.write('错误：没有找到键盘设备（%s）' % e)
            log.write('      请确认接收器已插好、接口已绑 WinUSB，并且驱动没有在运行。')
            return 1
        try:
            ep = device.configure_device(dev)
        except Exception as e:
            log.write('错误：配置键盘接口失败（%s）' % e)
            if getattr(e, 'errno', None) == 13 or 'ccess denied' in str(e):
                log.write('      接口被其它进程占用：最常见是 python -m keyboard_driver 正在运行，请先停止它。')
            else:
                log.write('      若驱动正在运行，请先停止它：同一接口不能被两个进程同时占用。')
            return 1
        log.write('设备：%s' % device.get_device_product(dev))
        log.write('端点：0x%02X（包大小 %d 字节）'
                  % (ep.bEndpointAddress, ep.wMaxPacketSize))

        if args.watch:
            watch.watch_mode(dev, ep)
            return 0

        if args.categories is not None and not args.learn:
            log.write('错误：--categories 只与 --learn 一起用（分类采集）。')
            log.write('      单键采集：--learn；常规键按类采集：--learn --categories all。')
            return 1

        if (args.required is not None or args.optional is not None
                or args.layer_pair is not None or args.layer_key is not None) \
                and not (args.learn and args.categories is not None):
            log.write('错误：--required/--optional/--layer-pair/--layer-key '
                      '只与 --learn --categories 一起用。')
            log.write('      例：--learn --categories all --optional edit arrows')
            return 1

        if args.learn:
            if args.keys:
                log.write('提示：--learn 会采集所有按下的键，--keys 不生效。')
            if args.categories is not None:
                return range_flow.range_mode(log, dev, ep, args)
            return learn_flow.learn_mode(log, dev, ep, args)

        specs = wizard.select_specs(log, args.keys)
        if specs is None:
            return 1
        rows = []
        reader = device.Reader(dev, ep, emit=log.write)
        rounds = {'both': (False, True), 'off': (False,), 'on': (True,)}[args.rounds]
        for round_on in rounds:
            if not wizard.run_round(log, dev, reader, round_on, specs,
                             args.timeout, attempts, rows):
                return 1
        return 0 if report.summarize(log, rows) else 1
    except usb.core.USBError as e:
        log.write('')
        log.write('读取中断：%s' % e)
        log.write('      通常是设备被拔出，或接口被其它进程抢占。')
        log.write('      若 python -m keyboard_driver 正在运行，请先停止它，再重跑本向导。')
        return 1
    except KeyboardInterrupt:
        log.write('')
        log.write('已中断（已完成的结论见结果文件）。')
        return 1
    finally:
        if dev is not None:
            try:
                device.write_led_bitmap(dev, 0)      # 退出时把 Num Lock 灯位恢复为 0
            except Exception:
                pass
        log.close()
