"""
Настройка логирования для Backend.
"""
import logging
import sys
from datetime import datetime


def setup_logging():
    """
    Настраивает логирование для всего приложения.
    
    Логи выводятся:
    - В консоль (для разработки)
    - В файл backend/logs/app.log (опционально)
    """
    
    # Создаём форматтер (как будут выглядеть логи)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Обработчик для вывода в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Настраиваем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    # Создаём логгер для нашего приложения
    app_logger = logging.getLogger("familybudget.backend")
    app_logger.setLevel(logging.INFO)
    
    # Отключаем лишние логи от библиотек
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    return app_logger


# Создаём логгер для использования в модулях
logger = setup_logging()
