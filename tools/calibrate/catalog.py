# -*- coding: utf-8 -*-
"""待按目标 Target 与内建类别（a-z、0-9、symbols、control、f1-f12、fn、edit、arrows、modifiers）。

Target 只描述"这个物理键按下去应该看到什么"；类别是可勾选的最小单位。
``fn`` 类按实体键列 10 条（F11/F12 是 F1/F2 的 Fn 副标注，没有独立实体键）。
"""

from collections import namedtuple

from keyboard_driver import win32_compat as win32con

from .constants import MODIFIER_BITS, usages_for_vk

Target = namedtuple('Target', 'label vks mod_bit optional pos fn record expect note',
                    defaults=(False, False, '', ''))


def _key_target(label, vk, optional=False, pos=''):
    """常规键：可接受的 usage 由 usage 反查，缺映射直接报错而不是静默接受"""
    usages = usages_for_vk(vk)
    if not usages:
        raise SystemExit('usage.KEYMAP 里没有 VK 0x%02X（%s），分类清单无法生成'
                         % (vk, label))
    return Target(label, usages, 0, optional, pos)


def _modifier_target(label, bit, optional=False, pos=''):
    return Target(label, frozenset(), bit, optional, pos)


def _fn_target(label, pos, expect=''):
    """Fn 组合：没有可预期的常规 usage，收到什么就记什么；无报告也不算失败"""
    return Target(label, frozenset(), 0, True, pos, True, True, expect)


def _file_target(label, pos, expect, note, optional, fn):
    """清单文件里的键：照实记录；expect 只是点名提示，不参与判定"""
    return Target(label, frozenset(), 0, optional, pos, fn, True, expect, note)


# 灯亮轮实测的"字母区/符号区 → 小键盘"改报关系（本项目 1EA7:0066 实测）。
# 只用于点名时提示键帽副标注，帮助用户在两轮里按到同一颗物理键；不参与判定。
LAYER_LEGENDS = {
    '7': '7', '8': '8', '9': '9', '0': '*', 'P': '-',
    'J': '1', 'K': '2', 'L': '3', 'U': '4', 'I': '5', 'O': '6', 'M': '0',
    ';': '+', '/': '/', '.': '.',
}

# 顶行数字键在哪个字母上方；其余位置用于把"按哪一颗"说清楚。
_TOP_ABOVE = {'1': 'Q', '2': 'W', '3': 'E', '4': 'R', '5': 'T', '6': 'Y',
              '7': 'U', '8': 'I', '9': 'O', '0': 'P'}
_SYMBOL_POS = {
    '-': '顶行 0 与 Backspace 之间',
    '=': '顶行 - 的右侧',
    '[': '字母区 P 的右侧',
    ']': '符号键 [ 的右侧',
    '\\': 'Enter 正上方',
    ';': '字母区 L 的右侧',
    "'": '符号键 ; 的右侧',
    '`': '左上角 Esc 的下方',
    ',': '字母区 M 的右侧',
    '.': '符号键 , 的右侧',
    '/': '右下角 Shift 的左侧',
}
_CONTROL_POS = {
    'Esc': '左上角 Esc',
    'Tab': '左侧 Tab',
    'CapsLock': '左侧 CapsLock',
    'Enter': '右侧中部 Enter',
    'Backspace': '右上角 Backspace',
    'Space': '底部中间空格',
    'Menu': '右侧 Alt 旁的菜单键',
}
_EDIT_POS = {
    'PrintScreen': '右上角 PrintScreen',
    'ScrollLock': '右上角 ScrollLock',
    'Pause': '右上角 Pause',
    'Insert': '编辑簇上排 Insert',
    'Home': '编辑簇上排 Home',
    'PageUp': '编辑簇上排 PageUp',
    'Delete': '编辑簇上排 Delete',
    'End': '编辑簇下排 End',
    'PageDown': '编辑簇下排 PageDown',
}
_MODIFIER_POS = {
    '左Ctrl': '左下角 Ctrl', '左Shift': '左下角 Shift',
    '左Alt': '底部左侧 Alt', '左Win': '底部左侧 Win',
    '右Ctrl': '右下角 Ctrl', '右Shift': '右下角 Shift',
    '右Alt': '右下角 Alt', '右Win': '右下角 Alt 右侧的 Win',
}


def _with_legend(text, label, sep='，'):
    """把键帽副标注补进位置描述；没有实测副标注就原样返回"""
    legend = LAYER_LEGENDS.get(label)
    return '%s%s副标注 %s' % (text, sep, legend) if legend else text



CATEGORIES = {}
# 类是可勾选的最小单位；名字短、可组合，命令行里用逗号或空格分隔都行
CATEGORY_ORDER = ('a-z', '0-9', 'symbols', 'control',
                  'f1-f12', 'fn', 'edit', 'arrows', 'modifiers')
# --categories-file 读进来的类按文件里的顺序追加；同名内建类会被文件里的定义整体替换
EXTRA_CATEGORY_ORDER = []
# --categories-file-only：本次只认文件里的类，内建类不再可选
CATEGORIES_FROM_FILE_ONLY = False
CATEGORY_ALIASES = {
    'a-z': 'a-z', 'letters': 'a-z', 'letter': 'a-z', 'alpha': 'a-z',
    '0-9': '0-9', 'digits': '0-9', 'digit': '0-9', 'numbers': '0-9',
    'symbols': 'symbols', 'symbol': 'symbols', 'punct': 'symbols',
    'control': 'control', 'controls': 'control',
    'f1-f12': 'f1-f12', 'function': 'f1-f12', 'functions': 'f1-f12',
    'fn': 'fn', 'fn-combo': 'fn', 'fn-combos': 'fn',
    'edit': 'edit', 'editing': 'edit',
    'arrows': 'arrows', 'arrow': 'arrows',
    'modifiers': 'modifiers', 'mods': 'modifiers',
    'all': 'all',
}


def _add_category(name, summary, targets):
    CATEGORIES[name] = (summary, tuple(targets))


# 只跑一轮的类：Fn 组合的消费类报表与 Num Lock 层无关（实测灯灭/灯亮完全一致），
# 跑两遍只是让用户把同一排键按两次。
SINGLE_ROUND_CATEGORIES = frozenset(['fn'])


def category_order():
    """本次运行可选的类顺序：内建在前、清单文件里的类在后

    --categories-file-only 时只剩文件里的类；同名内建类仍占它原来的位置。
    """
    if CATEGORIES_FROM_FILE_ONLY:
        return tuple(EXTRA_CATEGORY_ORDER)
    return CATEGORY_ORDER + tuple(n for n in EXTRA_CATEGORY_ORDER
                                  if n not in CATEGORY_ORDER)


def resolve_category(item):
    """类名或别名 → 规范名；不在本次可选范围内返回 None"""
    key = str(item).strip()
    name = CATEGORY_ALIASES.get(key.lower())
    if name is None:
        for candidate in EXTRA_CATEGORY_ORDER:
            if candidate.lower() == key.lower():
                name = candidate
                break
    if name is None:
        return None
    if name != 'all' and name not in category_order():
        return None
    return name



_add_category('a-z', '字母键 A–Z（26 个）',
              [_key_target(chr(code), code,
                           pos=_with_legend('字母区 %s' % chr(code), chr(code)))
               for code in range(ord('A'), ord('Z') + 1)])
_add_category('0-9', '数字行 1–9、0（10 个，指顶行数字键，不是小键盘）',
              [_key_target(ch, ord(ch),
                           pos=_with_legend('顶行数字 %s（在 %s 上方）'
                                            % (ch, _TOP_ABOVE[ch]), ch))
               for ch in '1234567890'])
_add_category('symbols', "符号行 - = [ ] \\ ; ' ` , . /（11 个，美式布局）", [
    _key_target('-', win32con.VK_OEM_MINUS,
                pos=_with_legend(_SYMBOL_POS['-'], '-')),
    _key_target('=', win32con.VK_OEM_PLUS,
                pos=_with_legend(_SYMBOL_POS['='], '=')),
    _key_target('[', win32con.VK_OEM_4,
                pos=_with_legend(_SYMBOL_POS['['], '[')),
    _key_target(']', win32con.VK_OEM_6,
                pos=_with_legend(_SYMBOL_POS[']'], ']')),
    _key_target('\\', win32con.VK_OEM_5,
                pos=_with_legend(_SYMBOL_POS['\\'], '\\')),
    _key_target(';', win32con.VK_OEM_1,
                pos=_with_legend(_SYMBOL_POS[';'], ';')),
    _key_target("'", win32con.VK_OEM_7,
                pos=_with_legend(_SYMBOL_POS["'"], "'")),
    _key_target('`', win32con.VK_OEM_3,
                pos=_with_legend(_SYMBOL_POS['`'], '`')),
    _key_target(',', win32con.VK_OEM_COMMA,
                pos=_with_legend(_SYMBOL_POS[','], ',')),
    _key_target('.', win32con.VK_OEM_PERIOD,
                pos=_with_legend(_SYMBOL_POS['.'], '.')),
    _key_target('/', win32con.VK_OEM_2,
                pos=_with_legend(_SYMBOL_POS['/'], '/')),
])
_add_category('control', '控制键 Esc/Tab/CapsLock/Enter/Backspace/Space/Menu（7 个）', [
    _key_target('Esc', win32con.VK_ESCAPE, pos=_CONTROL_POS['Esc']),
    _key_target('Tab', win32con.VK_TAB, pos=_CONTROL_POS['Tab']),
    _key_target('CapsLock', win32con.VK_CAPITAL, pos=_CONTROL_POS['CapsLock']),
    _key_target('Enter', win32con.VK_RETURN, pos=_CONTROL_POS['Enter']),
    _key_target('Backspace', win32con.VK_BACK, pos=_CONTROL_POS['Backspace']),
    _key_target('Space', win32con.VK_SPACE, pos=_CONTROL_POS['Space']),
    _key_target('Menu', win32con.VK_APPS, pos=_CONTROL_POS['Menu']),
])
_F11_POS = '按住 Fn 按顶排第 2 颗（主标注 F1／Fn 副标注 F11）'
_F12_POS = '按住 Fn 按顶排第 3 颗（主标注 F2／Fn 副标注 F12）'
_add_category('f1-f12', '功能键 F1–F12（12 个；F11/F12 要按住 Fn 按顶排 F1/F2）',
              [_key_target('F%d' % i, getattr(win32con, 'VK_F%d' % i),
                           pos=('键盘顶部功能键行 F%d（从左数第 %d 颗）' % (i, i + 1))
                           if i <= 10 else (_F11_POS if i == 11 else _F12_POS))
               for i in range(1, 13)])
# Fn 组合：Fn 本身通常不上报，Fn+某颗键的后果取决于固件——可能改报成另一个键盘
# usage、可能发消费类 usage、也可能什么都不发（固件本地处理）。
# 因此整类按可选项处理：收到键盘 usage 就照实记录；完全没有报告记「无上报」，
# 不计失败、自动进入下一项。
# 顶排 10 颗 F 键（键帽照片逐颗确认）：F11/F12 是 F1/F2 的 Fn 副标注，
# 不存在独立的 F11/F12 实体键，所以按实体键列 10 条，而不是机械枚举到 12。
# expect 只是点名提示（键帽标注 + 实测日志），不参与判定。
# 2026-11-11 复测：按住 Fn 后 F3–F9 只走消费类接口，键盘接口零报告；
# F4/F5/F7 旧轮次看到的 0x47/0x47/0x5F 未复现，判定为当时按错。
_FN_KEYS = (
    ('F11', '键盘 0x44 -> VK_F11（实测）'),
    ('F12', '键盘 0x45 -> VK_F12（实测）'),
    ('♪', '消费类 0x183 -> VK_LAUNCH_MEDIA_SELECT（实测）'),
    ('⏮', '上一曲：消费类 0xB6（实测）'),
    ('⏯', '播放/暂停：消费类 0xCD（实测）'),
    ('⏭', '消费类 0xB5 -> VK_MEDIA_NEXT_TRACK（实测）'),
    ('🔇', '静音：消费类 0xE2（实测）'),
    ('音量−', '音量减：消费类 0xEA（实测）'),
    ('音量+', '音量加：消费类 0xE9（实测）'),
    ('Scroll Lock', '键盘 0x47 -> VK_SCROLL（实测）'),
)
_add_category('fn', 'Fn 组合（顶排 10 颗 F 键，可选项；F11/F12 是 F1/F2 的 Fn 副标注，'
                    '没有独立的 F11/F12 实体键）。本类必须按住 Fn；单独按只会出'
                    '主功能键 F1..F10（无 Fn 副功能）。', [
    _fn_target('F%d（Fn:%s）' % (index, sub),
               '按住 Fn 再按顶排第 %d 颗（主标注 F%d、Fn 副标注 %s）'
               % (index + 1, index, sub),
               expect)
    for index, (sub, expect) in enumerate(_FN_KEYS, 1)
])
# 编辑键与方向键在 60%/紧凑键盘上经常整块缺失，默认按可选项处理：
# 重试到上限仍收不到任何报告就记「无此键」并自动进入下一个键，不计失败。
_add_category('edit', '编辑键 PrintScreen/ScrollLock/Pause/Insert/Home/PageUp/'
                      'Delete/End/PageDown（9 个，可选项）', [
    _key_target('PrintScreen', win32con.VK_SNAPSHOT, optional=True,
                pos=_EDIT_POS['PrintScreen']),
    _key_target('ScrollLock', win32con.VK_SCROLL, optional=True,
                pos=_EDIT_POS['ScrollLock']),
    _key_target('Pause', win32con.VK_PAUSE, optional=True,
                pos=_EDIT_POS['Pause']),
    _key_target('Insert', win32con.VK_INSERT, optional=True,
                pos=_EDIT_POS['Insert']),
    _key_target('Home', win32con.VK_HOME, optional=True,
                pos=_EDIT_POS['Home']),
    _key_target('PageUp', win32con.VK_PRIOR, optional=True,
                pos=_EDIT_POS['PageUp']),
    _key_target('Delete', win32con.VK_DELETE, optional=True,
                pos=_EDIT_POS['Delete']),
    _key_target('End', win32con.VK_END, optional=True,
                pos=_EDIT_POS['End']),
    _key_target('PageDown', win32con.VK_NEXT, optional=True,
                pos=_EDIT_POS['PageDown']),
])
_add_category('arrows', '方向键 Up/Down/Left/Right（4 个，可选项）', [
    _key_target('Up', win32con.VK_UP, optional=True, pos='编辑簇下方的方向键 Up'),
    _key_target('Down', win32con.VK_DOWN, optional=True, pos='编辑簇下方的方向键 Down'),
    _key_target('Left', win32con.VK_LEFT, optional=True, pos='编辑簇下方的方向键 Left'),
    _key_target('Right', win32con.VK_RIGHT, optional=True, pos='编辑簇下方的方向键 Right'),
])
# 右 Win 在不少键盘上被换成 Fn 或干脆没有，单独按可选项处理；其余修饰键为必要项。
_add_category('modifiers', '修饰键 左右 Ctrl/Shift/Alt/Win（8 个；右Win 可选项）',
              [_modifier_target(label, bit, optional=(bit == 0x80),
                                pos=_MODIFIER_POS[label])
               for bit, label in MODIFIER_BITS])
