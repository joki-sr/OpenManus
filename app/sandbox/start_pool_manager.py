#!/usr/bin/env python3
"""
启动Pool Manager服务的便捷脚本
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.sandbox.core.pool_manager import main

if __name__ == "__main__":
    main()

