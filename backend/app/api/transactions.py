"""
Эндпоинты для работы с транзакциями (расходы/доходы).
"""
import csv
import logging
from io import StringIO
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..deps import get_or_create_user_and_household
from ..utils import attach_budget_info_to_tx, extract_merchant_from_text
from ..ai import parse_text_to_transaction

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=schemas.TransactionRead)
def create_transaction(
    tx: schemas.TransactionCreate,
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Создать транзакцию (расход или доход).
    
    kind:
    - "expense" (по умолчанию) — расход
    - "income" — доход
    
    Пример:
    POST /transactions?telegram_id=123456789
    Body: {
        "amount": 2435,
        "currency": "RUB",
        "description": "Пятёрочка продукты",
        "category": "Продукты",
        "kind": "expense"
    }
    """
    user, household = get_or_create_user_and_household(db, telegram_id)
    
    kind = (tx.kind or "expense").lower()
    if kind not in ("expense", "income"):
        raise HTTPException(
            status_code=400,
            detail="kind должен быть 'expense' или 'income'",
        )
    
    # Ищем или создаём категорию
    category_id = None
    if tx.category:
        cat_name = tx.category.strip()
        category = (
            db.query(models.Category)
            .filter(
                models.Category.household_id == household.id,
                models.Category.name == cat_name,
            )
            .first()
        )
        
        if not category:
            category = models.Category(
                household_id=household.id,
                name=cat_name,
            )
            db.add(category)
            db.commit()
            db.refresh(category)
        
        category_id = category.id
    
    # Определяем merchant (магазин)
    merchant = extract_merchant_from_text(tx.description)
    
    db_tx = models.Transaction(
        household_id=household.id,
        user_id=user.id if user else None,
        amount=tx.amount,
        currency=tx.currency or household.currency,
        description=tx.description,
        category=tx.category,
        category_id=category_id,
        merchant=merchant,
        kind=kind,
        date=tx.date or datetime.utcnow(),
    )
    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)
    
    # Дополняем транзакцию данными по бюджету (если есть)
    attach_budget_info_to_tx(db, household, db_tx)
    
    return db_tx


@router.get("", response_model=List[schemas.TransactionRead])
def list_transactions(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    kind: str | None = Query(
        default=None,
        description="Фильтр по типу: expense / income",
    ),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Список транзакций.
    Можно фильтровать по дате и по типу операции (расход/доход).
    
    Пример:
    GET /transactions?telegram_id=123456789&kind=expense
    """
    user, household = get_or_create_user_and_household(db, telegram_id)
    
    query = db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id
    )
    
    if start_date:
        query = query.filter(models.Transaction.date >= start_date)
    if end_date:
        query = query.filter(models.Transaction.date <= end_date)
    
    if kind is not None:
        kind = kind.lower()
        if kind not in ("expense", "income"):
            raise HTTPException(
                status_code=400,
                detail="kind должен быть 'expense' или 'income'",
            )
        query = query.filter(models.Transaction.kind == kind)
    
    transactions = query.order_by(models.Transaction.date.desc()).all()
    
    return transactions


@router.get("/last", response_model=schemas.TransactionRead)
def get_last_transaction(
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Получить последнюю транзакцию пользователя.
    
    Пример:
    GET /transactions/last?telegram_id=123456789
    """
    user, household = get_or_create_user_and_household(db, telegram_id)
    
    if not user:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required",
        )
    
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
        raise HTTPException(
            status_code=404,
            detail="У тебя ещё нет транзакций",
        )
    
    return tx


@router.post("/delete-last", response_model=schemas.TransactionRead)
def delete_last_transaction(
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Удалить последнюю транзакцию пользователя и вернуть её данные.
    
    Пример:
    POST /transactions/delete-last?telegram_id=123456789
    """
    user, household = get_or_create_user_and_household(db, telegram_id)
    
    if not user:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required",
        )
    
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
        raise HTTPException(
            status_code=404,
            detail="У тебя нет транзакций для удаления",
        )
    
    db.delete(tx)
    db.commit()
    
    return tx


@router.post("/edit-last", response_model=schemas.TransactionRead)
def edit_last_transaction(
    new_amount: float | None = Query(default=None),
    new_description: str | None = Query(default=None),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Изменить последнюю транзакцию пользователя.
    
    Можно изменить:
    - Сумму (new_amount)
    - Описание (new_description)
    
    Примеры:
    POST /transactions/edit-last?telegram_id=123456789&new_amount=1500
    POST /transactions/edit-last?telegram_id=123456789&new_description=Ужин в кафе
    POST /transactions/edit-last?telegram_id=123456789&new_amount=1500&new_description=Ужин
    """
    user, household = get_or_create_user_and_household(db, telegram_id)
    
    if not user:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required",
        )
    
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
        raise HTTPException(
            status_code=404,
            detail="У тебя нет транзакций для изменения",
        )
    
    # Обновляем поля
    if new_amount is not None:
        tx.amount = new_amount
    
    if new_description is not None and new_description.strip():
        tx.description = new_description.strip()
        # Пересчитываем merchant при изменении описания
        tx.merchant = extract_merchant_from_text(tx.description)
    
    db.commit()
    db.refresh(tx)
    
    # Дополняем данными по бюджету
    attach_budget_info_to_tx(db, household, tx)
    
    return tx


@router.post("/set-category-last", response_model=schemas.TransactionRead)
def set_last_transaction_category(
    category: str = Query(..., description="Новая категория"),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Поменять категорию у последней транзакции пользователя.
    
    Пример:
    POST /transactions/set-category-last?telegram_id=123456789&category=Продукты
    """
    user, household = get_or_create_user_and_household(db, telegram_id)
    
    if not user:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required",
        )
    
    category = category.strip()
    if not category:
        raise HTTPException(
            status_code=400,
            detail="Категория не может быть пустой",
        )
    
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
        raise HTTPException(
            status_code=404,
            detail="У тебя нет транзакций",
        )
    
    # Ищем или создаём категорию
    cat_obj = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == category,
        )
        .first()
    )
    
    if not cat_obj:
        cat_obj = models.Category(
            household_id=household.id,
            name=category,
        )
        db.add(cat_obj)
        db.commit()
        db.refresh(cat_obj)
    
    # Обновляем транзакцию
    tx.category = category
    tx.category_id = cat_obj.id
    
    db.commit()
    db.refresh(tx)
    
    # Дополняем данными по бюджету
    attach_budget_info_to_tx(db, household, tx)
    
    return tx


@router.post("/parse-and-create", response_model=schemas.TransactionRead)
def parse_and_create_transaction(
    body: schemas.ParseTextRequest,
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Разбор свободного текста через YandexGPT + создание транзакции (расход).
    
    Пример:
    POST /transactions/parse-and-create?telegram_id=123456789
    Body: {"text": "Перекрёсток продукты 2435₽ вчера"}
    
    ИИ извлечёт:
    - amount: 2435
    - category: "Продукты"
    - description: "Перекрёсток"
    - date: вчера
    """
    user, household = get_or_create_user_and_household(db, telegram_id)
    
    # Вызываем ИИ для разбора текста
    try:
        parsed = parse_text_to_transaction(body.text)
        logger.debug(f"AI parsed result: {parsed}")
    except Exception as e:
        logger.error(f"AI parse error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка разбора текста через ИИ: {e}",
        )
    
    # Нормализуем сумму
    amount = float(parsed.get("amount", 0))
    if amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="ИИ не смог определить сумму",
        )
    
    currency = parsed.get("currency", "RUB")
    category_name = parsed.get("category")
    description = parsed.get("description")
    
    # Дата
    date_str = parsed.get("date")
    tx_date = datetime.utcnow()
    if date_str:
        try:
            tx_date = datetime.fromisoformat(date_str)
        except ValueError:
            pass
    
    # Ищем или создаём категорию
    category_id = None
    if category_name:
        cat_name = category_name.strip()
        category = (
            db.query(models.Category)
            .filter(
                models.Category.household_id == household.id,
                models.Category.name == cat_name,
            )
            .first()
        )
        
        if not category:
            category = models.Category(
                household_id=household.id,
                name=cat_name,
            )
            db.add(category)
            db.commit()
            db.refresh(category)
        
        category_id = category.id
    
    # Определяем merchant
    # Объединяем description + category + исходный текст для поиска
    combined_text = f"{description} {category_name} {body.text}"
    merchant = extract_merchant_from_text(combined_text)
    
    # Создаём транзакцию
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
    
    # Дополняем данными по бюджету
    attach_budget_info_to_tx(db, household, db_tx)
    
    # Добавляем candidate_categories из AI (для умных кнопок)
    candidate_cats = parsed.get("candidate_categories", [])
    # Используем setattr чтобы добавить поле в объект (не в БД)
    db_tx.candidate_categories = candidate_cats
    
    return db_tx


@router.post("/suggest-categories")
async def suggest_categories_only(
    body: schemas.ParseTextRequest,
    telegram_id: int = Query(None),
    db: Session = Depends(get_db)
):
    """
    Предложить категории БЕЗ создания транзакции (для /aiadd в боте).
    
    Возвращает топ-3 категории, которые реально существуют в семье.
    
    Пример:
    POST /transactions/suggest-categories?telegram_id=123456789
    Body: {"text": "Магнит 500"}
    
    Response: {
        "text": "Магнит 500",
        "amount": 500.0,
        "currency": "RUB",
        "suggestions": ["Продукты", "Химия и бытовое", "Другое"],
        "confidence": 0.8
    }
    """
    user, household = get_or_create_user_and_household(db, telegram_id)
    
    # Вызываем AI для разбора
    try:
        parsed = parse_text_to_transaction(body.text)
        logger.debug(f"AI suggest result: {parsed}")
    except Exception as e:
        logger.error(f"AI parse error in suggest: {e}")
        raise HTTPException(status_code=500, detail=f"AI parse error: {e}")
    
    amount = float(parsed.get('amount', 0))
    if amount == 0:
        raise HTTPException(status_code=400, detail="No amount detected")
    
    # Получаем существующие категории семьи
    existing_cats = db.query(models.Category).filter(
        models.Category.household_id == household.id
    ).all()
    
    # Создаём нормализованный словарь: lowercase -> оригинальное имя
    cat_names_map = {cat.name.strip().lower(): cat.name for cat in existing_cats}
    
    # AI предлагает топ-3 категории
    ai_suggestions = parsed.get('candidate_categories', [])
    
    # Фильтруем: оставляем только те, что реально есть в семье (case-insensitive)
    suggestions = []
    for ai_cat in ai_suggestions[:3]:
        normalized = ai_cat.strip().lower()
        if normalized in cat_names_map:
            suggestions.append(cat_names_map[normalized])
    
    # Если после фильтрации пусто, добавляем основную категорию AI или создаём её
    if not suggestions:
        main_category = parsed.get('category', 'Другое')
        # Ищем или создаём категорию
        cat_obj = (
            db.query(models.Category)
            .filter(
                models.Category.household_id == household.id,
                models.Category.name == main_category,
            )
            .first()
        )
        
        if not cat_obj:
            cat_obj = models.Category(
                household_id=household.id,
                name=main_category,
            )
            db.add(cat_obj)
            db.commit()
            logger.info(f"Created new category: {main_category}")
        
        suggestions = [main_category]
    
    return {
        "text": body.text,
        "amount": amount,
        "currency": parsed.get('currency', 'RUB'),
        "suggestions": suggestions,
        "confidence": 0.8  # TODO: реальная вероятность из YandexGPT
    }


@router.get("/export/csv")
def export_transactions_csv(
    days: int = Query(30, ge=1, le=365),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Экспорт транзакций в CSV за последние N дней.
    
    Пример:
    GET /transactions/export/csv?telegram_id=123456789&days=30
    """
    since = datetime.utcnow() - timedelta(days=days)
    user, household = get_or_create_user_and_household(db, telegram_id)
    
    txs = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
        )
        .order_by(models.Transaction.date.asc())
        .all()
    )
    
    def generate():
        output = StringIO()
        writer = csv.writer(output, delimiter=";")
        
        writer.writerow(
            [
                "id",
                "date",
                "kind",
                "amount",
                "currency",
                "category",
                "description",
            ]
        )
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        
        for tx in txs:
            writer.writerow(
                [
                    tx.id,
                    tx.date.strftime("%Y-%m-%d %H:%M:%S") if tx.date else "",
                    tx.kind,
                    float(tx.amount),
                    tx.currency,
                    tx.category or "",
                    tx.description or "",
                ]
            )
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
    
    headers = {
        "Content-Disposition": f'attachment; filename="transactions_{days}d.csv"'
    }
    
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers=headers,
    )
