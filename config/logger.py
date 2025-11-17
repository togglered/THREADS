import logging
import os
from datetime import datetime


BASE_LOG_DIR = "logs"
os.makedirs(BASE_LOG_DIR, exist_ok=True)

def setup_logger(name: str, subfolder: str, level=logging.INFO) -> logging.Logger:
    """
        Создает и настраивает отдельный логгер с собственным файлом.
    """
    log_dir = os.path.join(BASE_LOG_DIR, subfolder)
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(
        log_dir,
        f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    )
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False

    return logger

bot_logger = setup_logger("bot", "bot_logs")
scheduler_logger = setup_logger("scheduler", "scheduler_logs")
browser_logger = setup_logger("browser", "browser_logs")
