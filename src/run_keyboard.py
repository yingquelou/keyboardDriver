# -*- coding: utf-8 -*-
"""run_keyboard.py —— 计划任务入口：写日志后启动 keyboard.main()

只负责工作目录与日志，不修改任何键盘逻辑；手动调试仍可直接运行 keyboard.py。
日志写在项目根目录下的 logs\\keyboard.log（超过 1 MB 时滚动为 keyboard.log.1）。
"""

import datetime
import os
import sys
import traceback

import app_paths

# 本文件位于 src/：未打包时模块搜索路径用自身目录、日志与工作目录用项目根；
# 打包后（frozen）用 exe 同级目录，避免写进临时解包目录导致日志丢失。
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = app_paths.app_dir()
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "keyboard.log")
MAX_LOG_BYTES = 1024 * 1024
FROZEN = app_paths.FROZEN


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


def main():
    os.chdir(BASE_DIR)
    if not FROZEN and SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)
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
        app_paths.prepare_native_dlls()
        import keyboard
        keyboard.main()
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
