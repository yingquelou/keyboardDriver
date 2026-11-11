# -*- coding: utf-8 -*-
"""JSON 清单文件（--categories-file）：读取、校验、注册进本次运行。

格式见 ``load_category_file`` 的 docstring；本键盘的示例清单是 tools\\calibrate_keys.json。
文件里的类与内建类共存，同名类整体替换；``--categories-file-only`` 时内建类不再可选。
"""

import json

from . import catalog
from .catalog import _file_target

CATEGORY_FILE_VERSION = 1


def _category_text(entry, field):
    """取清单文件里的字符串字段；类型不对返回 None"""
    value = entry.get(field, '')
    if not isinstance(value, str):
        return None
    return value.strip()


def load_category_file(log, path):
    """读 JSON 清单文件 → [(类名, 说明, 目标元组)]；出错打印原因并返回 None

    格式（UTF-8，允许 BOM）::

        {"version": 1,
         "note": "整份清单的说明（可省）",
         "categories": [
           {"name": "fn", "summary": "说明（可省）", "note": "类备注（可省）",
            "optional": true, "fn": true,
            "keys": [{"label": "F1（Fn:F11）", "pos": "顶排第 2 颗…",
                      "expect": "键盘 0x44 -> VK_F11", "note": "待复测",
                      "optional": true, "fn": true}]}]}

    只有 label 必填，其余都可省；optional/fn 可写在类上作为该类的默认值。
    expect 只作为点名提示打印，不参与判定；note 在点名时作为「备注」输出。
    """
    try:
        with open(path, 'r', encoding='utf-8-sig') as handle:
            data = json.load(handle)
    except IOError as exc:
        log.write('错误：读不到清单文件 %s（%s）' % (path, exc))
        return None
    except ValueError as exc:
        log.write('错误：清单文件不是合法 JSON：%s（%s）' % (path, exc))
        return None
    if not isinstance(data, dict):
        log.write('错误：清单文件顶层必须是对象 {}，收到 %s' % type(data).__name__)
        return None
    version = data.get('version', CATEGORY_FILE_VERSION)
    if version != CATEGORY_FILE_VERSION:
        log.write('错误：清单文件 version=%r 不支持（本脚本支持 %d）'
                  % (version, CATEGORY_FILE_VERSION))
        return None
    entries = data.get('categories')
    if not isinstance(entries, list) or not entries:
        log.write('错误：清单文件缺少非空的 categories 列表')
        return None
    loaded = []
    seen = set()
    for entry_index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            log.write('错误：categories 第 %d 项必须是对象' % entry_index)
            return None
        name = entry.get('name')
        if not isinstance(name, str) or not name.strip():
            log.write('错误：categories 第 %d 项缺少 name（非空字符串）' % entry_index)
            return None
        name = name.strip()
        if name.lower() == 'all' or ',' in name or any(c.isspace() for c in name):
            log.write('错误：类名 %r 不能是 all，也不能含空格或逗号' % name)
            return None
        if name in seen:
            log.write('错误：类名 %s 在清单文件里重复出现' % name)
            return None
        seen.add(name)
        keys = entry.get('keys')
        if not isinstance(keys, list) or not keys:
            log.write('错误：类 %s 缺少非空的 keys 列表' % name)
            return None
        default_optional = bool(entry.get('optional', False))
        default_fn = bool(entry.get('fn', False))
        targets = []
        for key_index, item in enumerate(keys, 1):
            if not isinstance(item, dict):
                log.write('错误：类 %s 的 keys 第 %d 项必须是对象' % (name, key_index))
                return None
            label = item.get('label')
            if not isinstance(label, str) or not label.strip():
                log.write('错误：类 %s 的 keys 第 %d 项缺少 label（非空字符串）'
                          % (name, key_index))
                return None
            fields = {}
            for field in ('pos', 'expect', 'note'):
                value = _category_text(item, field)
                if value is None:
                    log.write('错误：类 %s 的 keys 第 %d 项 %s 必须是字符串'
                              % (name, key_index, field))
                    return None
                fields[field] = value
            targets.append(_file_target(
                label.strip(), fields['pos'], fields['expect'], fields['note'],
                bool(item.get('optional', default_optional)),
                bool(item.get('fn', default_fn))))
        summary = _category_text(entry, 'summary') or ''
        if not summary:
            summary = '%s（%d 项，来自清单文件）' % (name, len(targets))
        note = _category_text(entry, 'note') or ''
        if note:
            summary = '%s；备注：%s' % (summary, note)
        loaded.append((name, summary, tuple(targets)))
    file_note = _category_text(data, 'note') or ''
    if file_note:
        log.write('清单文件备注：%s' % file_note)
    log.write('已从清单文件读入 %d 类 / %d 项：%s'
              % (len(loaded), sum(len(t) for _, _, t in loaded), path))
    return loaded


def apply_category_file(log, path, file_only=False):
    """把清单文件里的类注册进本次运行；同名内建类用文件里的定义整体替换"""
    loaded = load_category_file(log, path)
    if loaded is None:
        return False
    catalog.CATEGORIES_FROM_FILE_ONLY = bool(file_only)
    for name, summary, targets in loaded:
        if name in catalog.CATEGORIES:
            log.write('清单文件覆盖内建类 %s：改用文件里的 %d 项。' % (name, len(targets)))
        catalog.CATEGORIES[name] = (summary, targets)
        if name not in catalog.EXTRA_CATEGORY_ORDER:
            catalog.EXTRA_CATEGORY_ORDER.append(name)
    if file_only:
        log.write('本次只认清单文件里的类，内建类不可选。')
    else:
        log.write('清单文件里的类与内建类共存，可在 --categories 里任选。')
    return True
