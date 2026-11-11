# -*- coding: utf-8 -*-
"""``python -m calibrate`` / ``python tools\\calibrate`` 的入口；实现在 cli.main()。"""

import os
import sys

if __package__:
    from .cli import main
else:
    # 以目录形式直接运行（python tools\calibrate）：把 tools 目录加进搜索路径后按包导入
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from calibrate.cli import main

if __name__ == '__main__':
    sys.exit(main())
