# -*- coding: utf-8 -*-
"""calibrate —— 键盘核对/采集工具（真机；pyusb 直读键盘接口）

四种入口（详见各子模块）：

    默认向导        wizard.py     点名六个切层键 → 等按下并抬起 → 判定 → 汇总
    --learn         learn.py      单键采集：按一个记一个，发现未知 usage，可起名并导出草稿
    --learn --categories
                    range_mode.py 分类采集：先选类（内建类或 --categories-file 读入），
                                  再在类内逐项点名；灯灭/灯亮两轮判定并落盘
    --watch         watch.py      纯被动翻译：只显示 HID 码 → VK 名，不判定、不留档

模块划分（每块只做一件事）：

    paths.py        项目根与 logs\\ 目录
    constants.py    参数默认值、向导键清单、HID 小键盘集合、切层集合与实测配对
    text.py         usage/VK/消费类的显示文案
    console.py      非阻塞控制台上行队列（后台线程读 stdin）
    device.py       设备读取：键盘 Reader、消费类监听、Num Lock 灯位写入
    report.py       结果文件（logs\\calibrate_<时间戳>.txt）与汇总口径
    wizard.py       默认向导
    learn.py        单键采集
    watch.py        --watch
    catalog.py      Target 与内建类别（a-z、0-9、……、fn、layer 之类由文件提供）
    catalog_file.py JSON 清单文件（--categories-file）的读取与注册
    planning.py     类名解析、--required/--optional、--layer-pair/--layer-key、交互选类
    judge.py        分类采集的判定口径（两轮断言、照实记录）
    range_mode.py   分类采集主流程（逐类逐项、skip/stop/done、类小结）
    cli.py          参数解析与入口分发

运行：``python -m calibrate``（在 tools 目录下）或 ``python tools\\calibrate``（项目根）。
约束：pyusb 直读会独占键盘接口，不能与 ``python -m keyboard_driver`` 同时运行；键盘接口需已绑 WinUSB。
"""

import os
import sys

# 本包位于 tools/calibrate/：把项目根加入模块搜索路径，按包名导入 keyboard_driver。
_ROOT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)
