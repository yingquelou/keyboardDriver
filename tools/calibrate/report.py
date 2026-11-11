# -*- coding: utf-8 -*-
"""结果文件与汇总：logs\\calibrate_<时间戳>.txt 的写入与屏幕汇总口径。"""

import datetime
import os

from .paths import LOG_DIR

class Log(object):
    """同时写屏幕与结果文件；结果文件放 logs\\（已被 .gitignore 忽略）"""

    def __init__(self):
        if not os.path.isdir(LOG_DIR):
            os.makedirs(LOG_DIR)
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.stamp = stamp
        self.path = os.path.join(LOG_DIR, 'calibrate_%s.txt' % stamp)
        self._file = open(self.path, 'w', encoding='utf-8-sig')

    def write(self, text=''):
        print(text)
        self._file.write(text + '\n')
        self._file.flush()

    def close(self):
        try:
            self._file.close()
        except Exception:
            pass



def summarize(log, rows):
    """汇总分三类：一致 / 无此键（可选项未采到）/ 失败（必要项超时或按错）

    切层映射偏差单列为「发现」，不计失败；跳过与未采集也不计失败。
    返回是否没有失败项。
    """
    total = len(rows)
    passed = [r for r in rows if r[3] == '一致']
    absent = [r for r in rows if r[3] == '无此键']
    no_report = [r for r in rows if r[3] == '无上报']
    findings = [r for r in rows if r[3] == '切层映射偏差（发现）']
    skipped = [r for r in rows if r[3] == '跳过']
    missed = [r for r in rows if r[3] == '未采集']
    failed = [r for r in rows
              if r[3] not in ('一致', '无此键', '无上报', '切层映射偏差（发现）',
                              '跳过', '未采集')]
    log.write('')
    log.write('=' * 62)
    log.write('汇总：共 %d 项，一致 %d，无此键 %d，失败 %d'
              % (total, len(passed), len(absent), len(failed)))
    if no_report:
        log.write('  无上报 %d（Fn 组合未收到键盘报告，可能由固件本地处理）'
                  % len(no_report))
    if findings:
        log.write('  发现（切层映射偏差） %d（不计失败，需确认配对）' % len(findings))
    if skipped:
        log.write('  跳过 %d（用户 skip/stop，不计失败）' % len(skipped))
    if missed:
        log.write('  未采集 %d（提前结束或中止）' % len(missed))
    if absent:
        log.write('  -- 无此键明细（可选项未收到任何报告，不计失败） --')
        for row in absent:
            log.write('   [%s] %s' % (row[0], row[1]))
    if no_report:
        log.write('  -- 无上报明细（Fn 组合，可能由固件本地处理，不计失败） --')
        for row in no_report:
            log.write('   [%s] %s' % (row[0], row[1]))
    if findings:
        log.write('  -- 切层映射偏差明细（发现） --')
        for row in findings:
            log.write('   [%s] %s：%s' % (row[0], row[1],
                                         row[4] if row[4] else '配对不符'))
    if failed:
        counts = {}
        for row in failed:
            counts[row[3]] = counts.get(row[3], 0) + 1
        log.write('  -- 失败明细 --')
        for name in ('未按灯位改报', '不应切层却改报', 'usage 不符', '按错键',
                     '来源不明（需复测）', '多键同帧', '超时未按'):
            if counts.get(name):
                log.write('  %s：%d' % (name, counts[name]))
        for row in failed:
            log.write('   [%s] %s：%s%s'
                      % (row[0], row[1], row[3],
                         ('（%s）' % row[4]) if row[4] else ''))
    log.write('结果文件：%s' % log.path)
    return len(failed) == 0
