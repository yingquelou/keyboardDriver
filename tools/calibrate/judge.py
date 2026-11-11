# -*- coding: utf-8 -*-
"""分类采集的判定口径：两轮断言、切层配对、清单/Fn 的"照实记录"。

判定只看设备事实上报（usage / 修饰位图），清单里的 expect 只作提示，不参与比对。
"""

from .constants import LAYER_KEYS, NUMPAD_USAGES
from .text import numpad_label, usage_text

def _pair_text(usage):
    return '%s（0x%02X）' % (numpad_label(usage) or '小键盘 usage', usage)


def target_expected(target, round_on, layer_pairs=None, layer_keys=None):
    """分类采集的预期文本；灯亮轮按实测配对与"是否参与切层"给出确定目标"""
    if target.expect:
        # 清单文件/键帽给出的预期只是提示，判定不拿它比对
        return '%s（仅提示，不参与判定）' % target.expect
    if target.fn:
        return '键盘改报的 usage、消费类 usage，或没有报告（Fn 通常不上报）'
    if target.mod_bit:
        return '修饰键位图 0x%02X（第 0 字节）' % target.mod_bit
    layer_keys = LAYER_KEYS if layer_keys is None else layer_keys
    text = '或'.join(usage_text(u) for u in sorted(target.vks))
    if round_on:
        if target.label in layer_keys:
            pair = (layer_pairs or {}).get(target.label)
            if pair is not None:
                text += '；灯亮轮预期改报为 %s' % _pair_text(pair)
            else:
                text += ('；灯亮轮预期改报为 15 个小键盘 usage 之一（尚未配对，'
                         '只要求与灯灭轮不同）')
        else:
            text += '；该键不参与切层，灯亮轮应与灯灭轮完全相同'
    return text


def _judge_record(target, added):
    """清单/Fn 这类"照实记录"目标收到键盘报告时的判定：不做"按错"推断

    Fn 通常不上报，Fn+Fn 键的后果由固件决定：可能改报成另一个键盘 usage，
    也可能同时/单独走消费类接口，还可能不发。清单文件里的键同理——预期只是提示。
    这里只负责把键盘接口这一侧收到的东西记全（同帧多个 usage 也全部列出）。
    """
    usages = '、'.join(usage_text(u) for u in added)
    if target.fn:
        return ('一致', '键盘接口收到 %s（%d 个 usage；Fn 组合的结果由固件决定，'
                        '消费类 usage 需另接消费类接口才能看到）'
                % (usages, len(added)))
    return ('一致', '键盘接口收到 %s（%d 个 usage；清单里的预期只是提示，不参与判定）'
            % (usages, len(added)))


def _unexplained(target, usage, plan_usages):
    """灯亮轮收到既非本键常规、也非小键盘 usage 的报文"""
    if plan_usages and usage in plan_usages:
        return ('按错键', '点名 %s，实收 %s（按到了本类另一颗键）'
                % (target.label, usage_text(usage)))
    return ('来源不明（需复测）',
            '点名 %s，实收 %s，既不是本键常规 usage 也不在 15 个小键盘 usage 内；'
            '原样记录，需真机复测' % (target.label, usage_text(usage)))


def judge_target(target, round_on, usage, layer_pairs=None, plan_usages=None,
                 off_usage=None, layer_keys=None):
    """分类采集的判定；返回 (结论, 说明)

    设备事实（实测，换键盘需重新确认）：
      1. 灯亮轮只有 LAYER_KEYS 这 15 颗会改报为小键盘 usage，
         且必须落在 HID 的 15 个小键盘 usage 内、与灯灭轮不同；
      2. 其余键两轮 usage 必须完全相同，发生变化即失败。
    切层键落在 15 个内但配对不符记为「切层映射偏差（发现）」，不算失败；
    会切层的键没改报记「未按灯位改报」；不该切层的键改报记「不应切层却改报」。
    """
    layer_pairs = layer_pairs or {}
    layer_keys = LAYER_KEYS if layer_keys is None else layer_keys
    if not round_on:
        if usage in target.vks:
            return '一致', ''
        if usage in NUMPAD_USAGES:
            return ('usage 不符', '灯灭轮却报 %s，Num Lock 灯位可能不是 0'
                    % _pair_text(usage))
        return ('按错键', '点名 %s，实收 %s（预期 %s）'
                % (target.label, usage_text(usage), target_expected(target, round_on)))

    pair = layer_pairs.get(target.label)
    if target.label not in layer_keys:
        # 不该切层的键：两轮 usage 必须相同
        if off_usage is not None:
            if usage == off_usage:
                return '一致', ''
            return ('不应切层却改报',
                    '灯灭轮 %s → 灯亮轮 %s；该键不参与切层，两轮 usage 本应完全相同。'
                    '它不在设备事实的 15 颗之内，可能为误按，请复核该次'
                    % (usage_text(off_usage), usage_text(usage)))
        if usage in target.vks:
            return '一致', '（只跑了灯亮轮，未做两轮比对；该键不参与切层，仍报常规 usage）'
        return ('不应切层却改报',
                '只跑了灯亮轮，实收 %s；该键不参与切层，需与灯灭轮比对确认；'
                '因不在设备事实的 15 颗之内，也可能为误按，请复核该次'
                % usage_text(usage))

    # 会切层的键：必须改报，且落在 15 个小键盘 usage 内
    if usage in NUMPAD_USAGES:
        if pair is not None and usage != pair:
            return ('切层映射偏差（发现）',
                    '本键实测配对为 %s，实收 %s：需确认是否为该键的稳定改报'
                    % (_pair_text(pair), _pair_text(usage)))
        if pair is not None:
            return ('一致', '该键在灯亮轮上报为%s（0x%02X），属于预期切换，不是按错'
                    % (numpad_label(usage), usage))
        return ('一致', '该键尚未配对，实测上报 %s，且与灯灭轮不同；'
                        '记下来纳入配对表后复核' % _pair_text(usage))
    if off_usage is not None and usage == off_usage:
        want = ('应改报为 %s' % _pair_text(pair)) if pair else '应改报为 15 个小键盘 usage 之一'
        return ('未按灯位改报',
                '本键属于会切层的实体键，灯亮轮仍报灯灭轮的 %s；%s'
                % (usage_text(usage), want))
    if usage in target.vks:
        want = ('应改报为 %s' % _pair_text(pair)) if pair else '应改报为 15 个小键盘 usage 之一'
        return ('未按灯位改报',
                '本键属于会切层的实体键，灯亮轮仍报 %s；%s' % (usage_text(usage), want))
    return _unexplained(target, usage, plan_usages)
