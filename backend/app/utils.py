"""
Вспомогательные функции для backend.
"""
import secrets
import string
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models


# ==========================================
# КОНСТАНТЫ
# ==========================================

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


# ==========================================
# ФУНКЦИИ
# ==========================================

def extract_merchant_from_text(text: str | None) -> str | None:
    """
    Извлекает название магазина из текста.
    
    Примеры:
    - "Пятёрочка продукты 500р" → "Пятёрочка"
    - "wb одежда" → "Wildberries"
    - "кофе" → None
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
    Генерирует уникальный короткий код приглашения.
    Использует заглавные буквы и цифры (кроме похожих O0I1).
    
    Пример: "AB7K3F"
    """
    # Базовый алфавит: A-Z + 0-9
    alphabet = string.ascii_uppercase + string.digits
    # Убираем похожие символы, чтобы код было легче читать
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

    # Если совсем не повезло — ошибка
    raise HTTPException(
        status_code=500,
        detail="Не удалось сгенерировать код приглашения, попробуй ещё раз",
    )


def attach_budget_info_to_tx(
    db: Session,
    household: models.Household,
    tx: models.Transaction,
) -> None:
    """
    Дополняет объект транзакции информацией о бюджете:
    - budget_limit — лимит по категории на месяц
    - budget_spent — сколько уже потрачено
    - budget_percent — процент использования бюджета
    
    Работает только для расходов (kind="expense").
    """
    # Только для расходов и только если есть категория
    if tx.kind != "expense" or not tx.category_id:
        return

    tx_date = tx.date or datetime.utcnow()
    period_month = tx_date.strftime("%Y-%m")

    # Границы месяца
    month_start = datetime(tx_date.year, tx_date.month, 1)
    if tx_date.month == 12:
        next_month_start = datetime(tx_date.year + 1, 1, 1)
    else:
        next_month_start = datetime(tx_date.year, tx_date.month + 1, 1)

    # Ищем бюджет для этой категории
    budget = (
        db.query(models.CategoryBudget)
        .filter(
            models.CategoryBudget.household_id == household.id,
            models.CategoryBudget.category_id == tx.category_id,
            models.CategoryBudget.period_month == period_month,
        )
        .first()
    )

    if not budget:
        return

    # Считаем, сколько уже потрачено за месяц по этой категории
    spent = (
        db.query(func.sum(models.Transaction.amount))
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.category_id == tx.category_id,
            models.Transaction.kind == "expense",
            models.Transaction.date >= month_start,
            models.Transaction.date < next_month_start,
        )
        .scalar()
        or 0
    )

    limit_val = float(budget.limit_amount or 0)
    spent_val = float(spent)
    percent = (spent_val / limit_val * 100) if limit_val > 0 else 0.0

    # Вешаем на объект tx новые атрибуты — Pydantic их заберёт
    tx.budget_limit = limit_val
    tx.budget_spent = spent_val
    tx.budget_percent = round(percent, 1)


def format_amount(amount: float, currency: str = "RUB") -> str:
    """
    Форматирует сумму с разделителями.
    
    Примеры:
    - 123456.78 → "123 457 RUB"
    - 1500.0 → "1 500 RUB"
    """
    return f"{amount:,.0f} {currency}".replace(",", " ")
