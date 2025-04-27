import os
import logging
from logging.handlers import RotatingFileHandler

# 登录配置
LOGIN_CONFIG = {
    "phone": "15623169098",  # 手机号
    "password": "Zc135790！",  # 密码
    "use_qr": False  # 改为True使用二维码登录
}

# 日志配置
LOG_CONFIG = {
    "level": logging.DEBUG,  # 修改为DEBUG级别
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "date_format": "%Y-%m-%d %H:%M:%S",
    "filename": os.path.join(os.path.dirname(__file__), "../logs/zhihuishu.log"),
    "max_bytes": 10 * 1024 * 1024,  # 10MB
    "backup_count": 5,
    "encoding": "utf-8"  # 添加编码设置
}

def setup_logging():
    """配置日志系统"""
    logger = logging.getLogger("zhihuishu")
    
    # 如果logger已经有处理器，说明已经配置过，直接返回
    if logger.handlers:
        return logger
        
    log_dir = os.path.dirname(LOG_CONFIG["filename"])
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 创建文件处理器
    file_handler = RotatingFileHandler(
        LOG_CONFIG["filename"],
        maxBytes=LOG_CONFIG["max_bytes"],
        backupCount=LOG_CONFIG["backup_count"],
        encoding=LOG_CONFIG["encoding"]
    )
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    
    # 创建格式化器
    formatter = logging.Formatter(
        fmt=LOG_CONFIG["format"],
        datefmt=LOG_CONFIG["date_format"]
    )
    
    # 设置处理器的格式化器
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 设置日志级别
    logger.setLevel(LOG_CONFIG["level"])
    
    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger