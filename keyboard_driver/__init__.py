# -*- coding: utf-8 -*-
"""keyboard_driver —— 用户态 HID 键盘驱动（libusb/WinUSB 接管）

模块划分（每块只做一件事）：

    __main__.py     驱动入口：``python -m keyboard_driver``
    driver.py       运行期编排：单实例、消费类/指示灯线程、主读取循环、断线重连
    transport.py    HID 运输与原语：枚举、claim、单次读取、注入状态机、灯位回写
    usage.py        通用 usage → VK 映射（与设备无关的 HID Usage Tables 对照表）
    win32_compat.py win32 兼容层：``keybd_event`` 与 VK 常量的 ctypes 实现
    paths.py        路径解析：源码形态与 PyInstaller 打包形态（frozen）
    run.py          计划任务 / 打包入口：写日志后启动 driver.main()
    device_profile/ 设备事实插槽（VID/PID、接口角色、报告布局）——换键盘只改这个包

本包不导入 pyusb：DLL 搜索路径必须先由 ``driver`` 在导入 pyusb 之前准备好。
"""
