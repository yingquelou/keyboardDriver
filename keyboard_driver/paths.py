# -*- coding: utf-8 -*-
"""统一处理"打包（PyInstaller）"与"直接运行源码"两种形态下的路径。

未打包时 __file__ 指向本文件，项目根 = keyboard_driver/ 的上一级；
打包后 __file__ 位于临时解包目录（onefile）或 _internal（6.x onedir），
不能再用来定位日志与配置，必须改用：
    sys.executable   -> exe 所在目录（可写，日志、venv、任务入口都放这里）
    sys._MEIPASS     -> 只读资源目录（onefile 下 libusb-1.0.dll 在此）
"""
import os
import sys

# PyInstaller 运行时注入 sys.frozen
FROZEN = bool(getattr(sys, "frozen", False))


def app_dir():
    """可写目录：打包后为 exe 同级目录；未打包为项目根目录。"""
    if FROZEN:
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir():
    """只读资源目录：onefile 为 sys._MEIPASS；onedir 为 exe 目录；未打包为 keyboard_driver/。"""
    if FROZEN:
        return getattr(sys, "_MEIPASS", app_dir())
    return os.path.dirname(os.path.abspath(__file__))


def prepare_native_dlls():
    """把 libusb-1.0.dll 所在目录加入 DLL 搜索路径。

    打包形态（行为不变）：
      - onedir：DLL 与 exe 同级（PyInstaller 5.x）或在 _internal 下，两种都加上；
      - onefile：DLL 被解包到 _MEIPASS，必须显式加入搜索路径。
    源码形态：项目根的 ``libusb\\x64`` 或 ``libusb\\x86``（按解释器位数）。
    这条分支是为登录自启准备的——schtasks 启动的进程不继承交互 shell 里的 PATH。
    """
    if FROZEN:
        candidates = []
        for base in (resource_dir(), app_dir()):
            candidates.append(base)
            candidates.append(os.path.join(base, "libusb"))
    else:
        arch = "x64" if sys.maxsize > 2 ** 32 else "x86"
        candidates = [os.path.join(app_dir(), "libusb", arch)]
    added = []
    for path in candidates:
        if os.path.isdir(path):
            added.append(path)
    if not added:
        return
    os.environ["PATH"] = os.pathsep.join(added + [os.environ.get("PATH", "")])
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        for path in added:
            try:
                add_dll_directory(path)
            except OSError:
                pass
