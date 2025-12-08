"""
backend/reset_db.py — Скрипт для очистки БД (с CASCADE)
"""

import os
import sys
from sqlalchemy import text

# Добавь путь к backend
sys.path.insert(0, os.path.dirname(__file__))

from app.db import Base, engine
from app import models

def reset_database():
    """Удалить и пересоздать все таблицы"""
    print("🧹 Очищаю базу данных...")
    
    try:
        with engine.connect() as conn:
            # Удалить все таблицы с CASCADE
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.commit()
            print("✓ Все таблицы удалены (CASCADE)")
    except Exception as e:
        print(f"⚠️ Ошибка при удалении: {e}")
    
    # Создать все таблицы заново
    Base.metadata.create_all(bind=engine)
    print("✓ Новые таблицы созданы")
    
    print("\n✅ База данных успешно очищена и пересоздана!")

if __name__ == "__main__":
    reset_database()
