# backend/app/utils.py

"""
Вспомогательные функции для backend.
"""

from difflib import SequenceMatcher
from typing import Optional, Tuple

import secrets
import string
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models


# ==========================================
# КОНСТАНТЫ
# ==========================================

# Пороги похожести категорий
AUTO_FIX_THRESHOLD = 0.95   # >= 0.95 — считаем, что это просто опечатка, исправляем автоматически
SUGGEST_THRESHOLD = 0.80    # 0.80–0.95 — спрашиваем у пользователя подтверждение

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
# РАБОТА С КАТЕГОРИЯМИ И ОПЕЧАТКАМИ
# ==========================================

def normalize_category_name(name: str) -> str:
    """
    Приводим название категории к каноническому виду:
    - обрезаем пробелы в начале/конце;
    - переводим в нижний регистр;
    - схлопываем повторяющиеся пробелы.
    """
    return " ".join(name.strip().lower().split())


def find_similar_category(
    db: Session,
    household_id: int,
    raw_name: str,
) -> Tuple[Optional[models.Category], float]:
    """
    Ищет самую похожую категорию для raw_name внутри одного household.

    Возвращает:
        (Category | None, similarity_score от 0.0 до 1.0)

    similarity_score — результат SequenceMatcher, чем ближе к 1.0, тем строки более похожи.
    """
    normalized = normalize_category_name(raw_name)
    if not normalized:
        return None, 0.0

    categories = (
        db.query(models.Category)
        .filter(models.Category.household_id == household_id)
        .all()
    )

    best_category: Optional[models.Category] = None
    best_score: float = 0.0

    for category in categories:
        cat_norm = normalize_category_name(category.name)
        score = SequenceMatcher(None, normalized, cat_norm).ratio()
        if score > best_score:
            best_score = score
            best_category = category

    return best_category, best_score


def resolve_category_with_typos(
    db: Session,
    household_id: int,
    raw_name: str,
    force_new: bool = False,
) -> Tuple[models.Category, Optional[str], bool]:
    """
    Возвращает кортеж:
        applied_category  — категорию, которую реально используем в транзакции;
        original_name     — исходное имя, если оно отличается от applied_category.name
                            (например, пользователь ввёл с опечаткой);
        needs_confirmation — нужно ли спросить пользователя
                             «Похоже, ты имел в виду ... ?».

    force_new=True — принудительно создать новую категорию с raw_name,
    не пытаясь искать похожие (нужно для кнопки «Оставить "Такиси"»).
    """
    raw_name = raw_name.strip()
    normalized = normalize_category_name(raw_name)

    # 0. Если просили насильно создать новую категорию — делаем и выходим
    if force_new:
        new_cat = models.Category(
            household_id=household_id,
            name=raw_name,
        )
        db.add(new_cat)
        db.flush()
        return new_cat, None, False

    # 1. Пробуем точное совпадение (без учёта регистра)
    existing = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household_id,
            func.lower(models.Category.name) == normalized,
        )
        .first()
    )
    if existing:
        # Никаких опечаток, просто используем категорию
        return existing, None, False

    # 2. Ищем похожую категорию
    similar_category, score = find_similar_category(db, household_id, raw_name)

    if similar_category is None or score < SUGGEST_THRESHOLD:
        # Ничего похожего — создаём новую категорию
        new_cat = models.Category(
            household_id=household_id,
            name=raw_name,
        )
        db.add(new_cat)
        db.flush()
        return new_cat, None, False

    # 3. Очень сильное совпадение — автоисправление без вопроса
    if score >= AUTO_FIX_THRESHOLD:
        # applied = похожая, но помним, что пользователь вводил raw_name
        return similar_category, raw_name, False

    # 4. Среднее совпадение — предлагаем пользователю подтвердить
    return similar_category, raw_name, True


# ==========================================
# ПРОЧИЕ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def extract_merchant_from_text(text: Optional[str]) -> Optional[str]:
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
