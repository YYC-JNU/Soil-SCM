"""
模块: logging_config.py
功能: 日志配置与获取 (Q15 修复)

用法:
    from src.logging_config import setup_logging, get_logger
    setup_logging(log_dir="./output")      # 主程序入口调用一次
    logger = get_logger("phreeqc_engine")  # 模块级 logger
"""

import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_FILE_NAME = "soil_scm.log"


def setup_logging(log_dir="./output", level=logging.INFO,
                  console=True) -> logging.Logger:
    """初始化 soil_scm 根 logger: console + file 双输出 (幂等)

    参数:
        log_dir: 日志文件目录 (自动创建)
        level: 日志级别
        console: 是否同时输出到控制台

    返回:
        root logger
    """
    root = logging.getLogger("soil_scm")
    root.setLevel(level)

    # 幂等: 清除已有 handler, 避免重复输出
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(LOG_FORMAT)

    # 文件 handler
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_dir / LOG_FILE_NAME, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        ch.setFormatter(fmt)
        root.addHandler(ch)

    return root


def get_logger(name: str) -> logging.Logger:
    """获取 soil_scm.<name> 子 logger"""
    return logging.getLogger(f"soil_scm.{name}")
