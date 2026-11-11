# -*- coding: utf-8 -*-
"""把命令行/交互输入翻译成采集计划：选类、必要/可选覆盖、切层配对与切层键覆盖。"""

import time

from .catalog import CATEGORIES, category_order, resolve_category
from .constants import NUMPAD_USAGES

def parse_categories(log, tokens):
    """把用户给的类名规范成按固定顺序排列的列表；无效返回 None

    允许逗号或空格分隔、可组合、``all`` 表示全部，别名见 CATEGORY_ALIASES；
    ``--categories-file`` 读进来的类直接用文件里的名字（大小写不敏感）。
    """
    wanted = []
    for token in tokens:
        for item in str(token).replace(',', ' ').split():
            name = resolve_category(item)
            if name is None:
                log.write('错误：未知类别 %s（可选：all、%s）'
                          % (item, '、'.join(category_order())))
                return None
            wanted.append(name)
    if not wanted:
        log.write('错误：没有选择任何类别（可选：all、%s）'
                  % '、'.join(category_order()))
        return None
    if 'all' in wanted:
        return list(category_order())
    return [name for name in category_order() if name in wanted]


def _parse_override(log, flag, tokens):
    """--required/--optional 的类名集合；未指定返回 None，名称非法也返回 None"""
    if tokens is None:
        return None
    names = set()
    for token in tokens:
        for item in str(token).replace(',', ' ').split():
            name = resolve_category(item)
            if name is None:
                log.write('错误：%s 里有未知类别 %s（可选：all、%s）'
                          % (flag, item, '、'.join(category_order())))
                return None
            if name == 'all':
                names.update(category_order())
            else:
                names.add(name)
    if not names:
        log.write('错误：%s 后面没有类别名（可选：all、%s）'
                  % (flag, '、'.join(category_order())))
        return None
    return names


def build_plan(log, categories, required_names, optional_names):
    """把默认必要/可选划分与 --required/--optional 合成本轮计划

    返回 [(类名, 说明, 目标元组)]；同一类同时出现在两个参数里时按必要项处理。
    """
    required = _parse_override(log, '--required', required_names)
    if required_names is not None and required is None:
        return None
    optional = _parse_override(log, '--optional', optional_names)
    if optional_names is not None and optional is None:
        return None
    plan = []
    for name in categories:
        summary, targets = CATEGORIES[name]
        if optional and name in optional:
            targets = tuple(t._replace(optional=True) for t in targets)
        if required and name in required:
            targets = tuple(t._replace(optional=False) for t in targets)
        plan.append((name, summary, targets))
    return plan


def parse_layer_pairs(log, tokens):
    """--layer-pair 的 KEY=USAGE 覆盖项；返回 dict，非法返回 None

    只允许 15 个小键盘 usage；键名必须是分类清单里出现过的名字。
    """
    if tokens is None:
        return {}
    labels = set(t.label for _, targets in CATEGORIES.values() for t in targets)
    pairs = {}
    for token in tokens:
        for item in str(token).replace(',', ' ').split():
            if '=' not in item:
                log.write('错误：--layer-pair 需要 键=usage 形式（例如 J=0x59），收到 %s'
                          % item)
                return None
            label, value = item.split('=', 1)
            label = label.strip()
            try:
                usage = int(value.strip(), 0)
            except ValueError:
                log.write('错误：--layer-pair %s 的 usage 不是数字：%s' % (label, value))
                return None
            if label not in labels:
                log.write('错误：--layer-pair 里的键 %s 不在分类清单里' % label)
                return None
            if usage not in NUMPAD_USAGES:
                log.write('错误：--layer-pair %s=0x%02X 不在 15 个小键盘 usage 内'
                          % (label, usage))
                return None
            pairs[label] = usage
    return pairs


def parse_layer_keys(log, tokens):
    """--layer-key 覆盖"会切层"的键集合；未指定返回 None，名称非法也返回 None"""
    if tokens is None:
        return None
    labels = set(t.label for _, targets in CATEGORIES.values() for t in targets)
    keys = set()
    for token in tokens:
        key = str(token).strip()
        if key not in labels:
            log.write('错误：--layer-key 里的键 %s 不在分类清单里' % key)
            return None
        keys.add(key)
    if not keys:
        log.write('错误：--layer-key 后面没有键名')
        return None
    return frozenset(keys)


def ask_categories(log, inbox):
    """交互式选类：打印菜单并等一行控制台输入（这把键盘的接口已被独占，需另一把键盘）"""
    log.write('')
    log.write('可选类别（类是最小单位，可单选、多选或 all）：')
    for name in category_order():
        log.write('  %-10s %s' % (name, CATEGORIES[name][0]))
    log.write('别名：a-z/letters、0-9/digits、f1-f12/function、modifiers/mods。')
    log.write('请输入要采的类别（逗号或空格分隔，回车确认；输入 done 取消）：')
    if inbox.closed:
        log.write('错误：控制台输入不可用（stdin 已关闭），请在命令行直接写 --categories。')
        return None
    while True:
        line = inbox.poll()
        if line is None:
            time.sleep(0.05)
            continue
        if line.strip().lower() in ('done', 'q', 'quit'):
            log.write('已取消。')
            return None
        categories = parse_categories(log, [line])
        if categories is not None:
            return categories
