# -*- coding: utf-8 -*-
"""run.py —— 计划任务 / 打包入口：写日志后启动 driver.main()

只负责工作目录与日志，不修改任何键盘逻辑；手动调试直接运行 ``python -m keyboard_driver``。
日志写在项目根目录下的 logs\\keyboard.log（超过 1 MB 时滚动为 keyboard.log.1）。

两种运行形态：
    python -m keyboard_driver.run          # 源码形态（项目根）
    python keyboard_driver\\run.py         # 源码形态（PyInstaller 入口也用它）
"""

import datetime
import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __package__:
    from . import paths
else:
    # 作为脚本运行（含 PyInstaller 把本文件当 __main__）：先让包可导入
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from keyboard_driver import paths

# 未打包时日志与工作目录用项目根；打包后（frozen）用 exe 同级目录，
# 避免写进临时解包目录导致日志丢失。
BASE_DIR = paths.app_dir()
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "keyboard.log")
MAX_LOG_BYTES = 1024 * 1024
FROZEN = paths.FROZEN


class _Tee(object):
    """打包为控制台程序时同时写日志与屏幕；无控制台（计划任务/重定向）时只写日志。"""

    def __init__(self, log_file, console):
        self._log = log_file
        self._console = console

    def write(self, text):
        self._log.write(text)
        if self._console is not None:
            try:
                self._console.write(text)
            except Exception:
                pass

    def flush(self):
        try:
            self._log.flush()
        except Exception:
            pass
        if self._console is not None:
            try:
                self._console.flush()
            except Exception:
                pass


def _rotate_log():
    """日志过大时滚动一份旧日志，避免长期运行把磁盘占满"""
    try:
        if os.path.getsize(LOG_PATH) > MAX_LOG_BYTES:
            backup = LOG_PATH + ".1"
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(LOG_PATH, backup)
    except OSError:
        pass


def _load_driver():
    """延迟导入驱动：包形态用相对导入，脚本形态用绝对导入"""
    if __package__:
        from . import driver
    else:
        from keyboard_driver import driver
    return driver


def main():
    os.chdir(BASE_DIR)
    if not os.path.isdir(LOG_DIR):
        os.makedirs(LOG_DIR)
    _rotate_log()

    log_file = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
    console = sys.stdout if FROZEN and sys.stdout is not None else None
    if console is not None and not getattr(console, "isatty", lambda: False)():
        console = None          # 被重定向/无控制台时不再重复写
    sys.stdout = _Tee(log_file, console)
    sys.stderr = _Tee(log_file, console)
    started = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=== %s 启动 ===" % started)
    result = 0
    try:
        # 不在这里调 paths.prepare_native_dlls()：导入 driver 时它会在导入 pyusb
        # 之前先执行，入口再调一次只是重复。
        _load_driver().main()
    except SystemExit as exc:
        print("主程序退出（SystemExit: %s）" % exc)
    except BaseException:
        print("主程序异常退出：")
        traceback.print_exc()
        result = 1
    finally:
        print("=== %s 结束 ===" %
              datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        try:
            log_file.flush()
        except Exception:
            pass
    return result


if __name__ == "__main__":
    sys.exit(main())
