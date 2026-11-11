# -*- coding: utf-8 -*-
"""项目路径：脚本按自身位置解析，可从任意工作目录启动。"""

import os

# 本文件在 tools/calibrate/：上三级是项目根
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(BASE_DIR, "logs")
