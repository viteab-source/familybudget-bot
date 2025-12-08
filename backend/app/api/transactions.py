"""
api/transactions.py — Эндпоинты для транзакций.
POST /transactions — создать
GET /transactions — список
POST /transactions/parse-and-create — через ИИ
GET /transactions/last — последняя
POST /transactions/edit-last — редактировать последнюю
POST /transactions/set-category-last — поменять категорию последней
DELETE /transactions/delete-last — удалить последнюю
POST /transactions/category-feedback — логировать исправления
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..deps import get_or_create_user_and_household
from ..ai import parse_text_to_transaction
from ..utils import extract_merchant_from_text

logger = logging.getLogger("familybudget_api")

router = APIRouter()


def attach_budget_info_to_tx(
    db: Session,
    household: models.Household,
    tx: models.Transaction,
) -> None:
    """
    Дополнить объект транзакции полями:
    - budget_limit
    - budget_spent
    - budget_percent
    
    Если бюджета для категории нет — просто ничего не делаем.
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

    # Вешаем на объект tx новые атрибуты
    tx.budget_limit = limit_val
    tx.budget_spent = spent_val
    tx.budget_percent = round(percent, 1)


@router.post("/transactions", response_model=schemas.TransactionRead)
def create_transaction(
    tx: schemas.TransactionCreate,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Создать транзакцию вручную.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    # Ищем или создаём категорию
    category_id = None
    if tx.category:
        category = (
            db.query(models.Category)
            .filter(
                models.Category.household_id == household.id,
                models.Category.name == tx.category,
            )
            .first()
        )
        if not category:
            category = models.Category(
                household_id=household.id,
                name=tx.category,
            )
            db.add(category)
            db.commit()
            db.refresh(category)
        category_id = category.id

    # Определяем магазин из описания
    merchant = extract_merchant_from_text(tx.description)

    db_tx = models.Transaction(
        household_id=household.id,
        user_id=user.id if user else None,
        amount=tx.amount,
        currency=tx.currency,
        description=tx.description,
        category=tx.category,
        category_id=category_id,
        merchant=merchant,
        kind=tx.kind,
        date=tx.date or datetime.utcnow(),
    )

    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)

    attach_budget_info_to_tx(db, household, db_tx)

    return db_tx


@router.get("/transactions", response_model=List[schemas.TransactionRead])
def list_transactions(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Список транзакций за последние N дней.
    """
    since = datetime.utcnow() - timedelta(days=days)
    user, household = get_or_create_user_and_household(db, telegram_id)

    txs = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
        )
        .order_by(models.Transaction.date.desc())
        .all()
    )

    for tx in txs:
        attach_budget_info_to_tx(db, household, tx)

    return txs


@router.get("/transactions/last", response_model=Optional[schemas.TransactionRead])
def get_last_transaction(
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Получить последнюю транзакцию пользователя.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    if not user:
        return None

    tx = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.user_id == user.id,
        )
        .order_by(models.Transaction.created_at.desc())
        .first()
    )

    if tx:
        attach_budget_info_to_tx(db, household, tx)

    return tx


@router.post("/transactions/edit-last")
def edit_last_transaction(
    body: dict,  # {"amount": 2435, "description": "Новое описание"}
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Редактировать последнюю транзакцию (сумма, описание).
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    tx = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.user_id == user.id,
        )
        .order_by(models.Transaction.created_at.desc())
        .first()
    )

    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Обновляем поля
    if "amount" in body:
        tx.amount = float(body["amount"])

    if "description" in body:
        tx.description = body["description"]
        # Пересчитываем merchant, если изменилось описание
        merchant = extract_merchant_from_text(tx.description)
        if merchant:
            tx.merchant = merchant

    db.commit()
    db.refresh(tx)

    attach_budget_info_to_tx(db, household, tx)

    return tx


@router.post("/transactions/delete-last")
def delete_last_transaction(
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Удалить последнюю транзакцию пользователя.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    tx = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.user_id == user.id,
        )
        .order_by(models.Transaction.created_at.desc())
        .first()
    )

    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    db.delete(tx)
    db.commit()

    return {"status": "ok"}


@router.post("/transactions/set-category-last")
def set_category_last_transaction(
    body: dict,  # {"category": "Продукты"}
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Поменять категорию последней транзакции.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    tx = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.user_id == user.id,
        )
        .order_by(models.Transaction.created_at.desc())
        .first()
    )

    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    new_category = (body.get("category") or "").strip()
    if not new_category:
        raise HTTPException(
            status_code=400,
            detail="Категория не может быть пустой",
        )

    # Ищем или создаём категорию
    category = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == new_category,
        )
        .first()
    )

    if not category:
        category = models.Category(
            household_id=household.id,
            name=new_category,
        )
        db.add(category)
        db.commit()
        db.refresh(category)

    tx.category = new_category
    tx.category_id = category.id
    db.commit()
    db.refresh(tx)

    attach_budget_info_to_tx(db, household, tx)

    return tx


@router.post("/transactions/parse-and-create", response_model=schemas.TransactionRead)
def parse_and_create_transaction(
    body: schemas.ParseTextRequest,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Парсит свободный текст через ИИ и создаёт транзакцию.
    
    Пример:
    POST /transactions/parse-and-create
    {"text": "Перекрёсток продукты 2435 вчера"}
    
    Возвращает созданную транзакцию + candidate_categories.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    text = (body.text or "").strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="Текст не может быть пустым",
        )

    logger.info(f"Parsing text: {text}")

    # Вызываем ИИ
    try:
        ai_result = parse_text_to_transaction(text)
    except Exception as e:
        logger.error(f"AI parsing error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при парсинге: {str(e)}",
        )

    logger.info(f"AI result: {ai_result}")

    # Извлекаем данные из ИИ
    amount = ai_result.get("amount")
    if amount is None:
        raise HTTPException(
            status_code=400,
            detail="ИИ не смог определить сумму",
        )

    currency = ai_result.get("currency", "RUB")
    category_name = ai_result.get("category")
    candidate_categories = ai_result.get("candidate_categories", [])
    description = ai_result.get("description")
    date_str = ai_result.get("date")

    # Парсим дату
    try:
        if date_str:
            tx_date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            tx_date = datetime.utcnow()
    except ValueError:
        tx_date = datetime.utcnow()

    # Нормализуем candidate_categories
    if candidate_categories:
        # Чистим пустые строки
        candidate_categories = [c.strip() for c in candidate_categories if c and c.strip()]
        # Убираем дубли
        seen = set()
        unique_candidates = []
        for c in candidate_categories:
            c_lower = c.lower()
            if c_lower not in seen:
                unique_candidates.append(c)
                seen.add(c_lower)
        candidate_categories = unique_candidates
        
        # Гарантируем, что category (первый элемент) совпадает с основной категорией
        if category_name and candidate_categories:
            if candidate_categories[0].lower() != category_name.lower():
                # Удаляем category_name из кандидатов, если он там есть
                candidate_categories = [
                    c for c in candidate_categories 
                    if c.lower() != category_name.lower()
                ]
                # Вставляем category_name первым
                candidate_categories.insert(0, category_name)
    else:
        # Если кандидатов нет, создаём список с основной категорией
        if category_name:
            candidate_categories = [category_name]
        else:
            candidate_categories = []

    # Ищем или создаём категорию
    category_id = None
    if category_name:
        category = (
            db.query(models.Category)
            .filter(
                models.Category.household_id == household.id,
                models.Category.name == category_name,
            )
            .first()
        )
        if not category:
            category = models.Category(
                household_id=household.id,
                name=category_name,
            )
            db.add(category)
            db.commit()
            db.refresh(category)
        category_id = category.id

    # Определяем магазин
    merchant = extract_merchant_from_text(description or text)

    # Создаём транзакцию (по умолчанию расход)
    db_tx = models.Transaction(
        household_id=household.id,
        user_id=user.id if user else None,
        amount=amount,
        currency=currency,
        description=description,
        category=category_name,
        category_id=category_id,
        merchant=merchant,
        kind="expense",
        date=tx_date,
    )

    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)

    attach_budget_info_to_tx(db, household, db_tx)

    # Вешаем кандидатные категории в ответ
    db_tx.candidate_categories = candidate_categories

    logger.info(f"Transaction created: {db_tx.id}")

    return db_tx


@router.post("/transactions/category-feedback")
def save_category_feedback(
    body: schemas.CategoryFeedbackCreate,
    db: Session = Depends(get_db),
):
    """
    Логируем, как пользователь поправил категорию после ИИ.
    Это не влияет на деньги, только для аналитики/алиасов.
    """
    logger.info("CATEGORY_FEEDBACK: %s", body.dict())

    user, household = get_or_create_user_and_household(db, body.telegram_id)

    tx = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.id == body.transaction_id,
            models.Transaction.household_id == household.id,
        )
        .first()
    )

    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    record = models.TransactionCategoryFeedback(
        household_id=household.id,
        user_id=user.id if user else None,
        transaction_id=tx.id,
        original_category=(body.original_category or "").strip() or None,
        chosen_category=(body.chosen_category or "").strip(),
        candidate_categories_json=json.dumps(body.candidate_categories or []),
        original_text=(body.original_text or None),
    )

    db.add(record)
    db.commit()

    return {"status": "ok"}
