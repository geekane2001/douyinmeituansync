"""
日志工具模块 - 统一日志管理
"""
import logging
import os


def setup_logger(log_file='update_products_log.txt', level=logging.INFO):
    """配置日志系统"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
        ]
    )
    return logging.getLogger(__name__)


def log_to_file(message, log_file='update_products_log.txt'):
    """直接写入日志文件"""
    logging.info(message)
