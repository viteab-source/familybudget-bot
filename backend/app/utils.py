"""
utils.py — Вспомогательные функции (не зависят от BD и FastAPI).
"""

import secrets
import string
from sqlalchemy.orm import Session
from . import models
from fastapi import HTTPException


INVITE_CODE_LENGTH = 8
MERCHANT_KEYWORDS = {
    "пятерочка": "Пятёрочка",
    "5ка": "Пятёрочка",
    "перекресток": "Перекрёсток",
    "перекрёсток": "Перекрёсток",
    "дикси": "Дикси",
    "магнит": "Магнит",
    "кб ": "Красное&Белое",
    "кб": "Красное&Белое",
    "к&б": "Красное&Белое",
    "красное&белое": "Красное&Белое",
    "лента": "Лента",
    "ашан": "Ашан",
    "wildberries": "Wildberries",
    "wb": "Wildberries",
    "озон": "Ozon",
    "ozon": "Ozon",
}


def extract_merchant_from_text(text: str | None) -> str | None:
    """
    Пытаемся определить магазин/сервис из текста.
    """
    if not text:
        return None

    low = text.lower()
    for key, merchant in MERCHANT_KEYWORDS.items():
        if key in low:
            return merchant

    return None


def generate_invite_code(db: Session, length: int = INVITE_CODE_LENGTH) -> str:
    """
    Генерирует уникальный короткий код приглашения из заглавных букв и цифр.
    Примеры кодов: AB7K3F, X9L2MD и т.п.
    """
    # Базовый алфавит: A-Z + 0-9
    alphabet = string.ascii_uppercase + string.digits

    # Убираем похожие символы, чтобы код было легче читать/вводить
    ambiguous = "O0I1"
    alphabet = "".join(ch for ch in alphabet if ch not in ambiguous)

    # До 20 попыток найти свободный код
    for _ in range(20):
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        exists = (
            db.query(models.HouseholdInvite)
            .filter(models.HouseholdInvite.code == code)
            .first()
        )
        if not exists:
            return code

    # Если совсем не повезло — кидаем 500-ю ошибку
    raise HTTPException(
        status_code=500,
        detail="Не удалось сгенерировать код приглашения, попробуй ещё раз",
    )


def format_amount(amount: float, currency: str = "RUB") -> str:
    """
    Форматирует сумму денег красиво (с пробелами и валютой).
    Пример: 2435.50 RUB → "2 435.50 ₽"
    """
    # Это просто для будущего; пока возвращаем как есть
    return f"{amount:,.2f} {currency}".replace(",", " ")
