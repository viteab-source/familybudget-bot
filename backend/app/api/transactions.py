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
from ..utils import attach_budget_info_to_tx, extract_merchant_from_text, resolve_category_with_typos
from ..ai import parse_text_to_transaction
  

router = APIRouter()
logger = logging.getLogger(__name__)

# ==========================================
# Вспомогательные функции
# ==========================================


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
    # 1. Находим (или создаём) пользователя и семью
    user, household = get_or_create_user_and_household(db, telegram_id)

    # 2. Проверяем тип операции
    kind = (tx.kind or "expense").lower()
    if kind not in ("expense", "income"):
        raise HTTPException(
            status_code=400,
            detail="kind должен быть 'expense' или 'income'",
        )

    # 3. Обрабатываем категорию с учётом опечаток
    category_id: int | None = None
    final_category_name: str | None = None

    raw_category_input: str | None = tx.category.strip() if tx.category else None
    suggested_category_name: str | None = None
    needs_confirmation: bool = False

    if raw_category_input:
        # Используем общий хелпер из utils.resolve_category_with_typos
        category_obj, _original_name, needs_confirmation = resolve_category_with_typos(
            db=db,
            household_id=household.id,
            raw_name=raw_category_input,
            force_new=False,
        )
        category_id = category_obj.id
        final_category_name = category_obj.name
        suggested_category_name = category_obj.name
    else:
        # Категорию не передали — оставляем как есть
        category_id = None
        final_category_name = None
        suggested_category_name = None
        needs_confirmation = False

    # 4. Определяем магазин (merchant) по описанию
    merchant = extract_merchant_from_text(tx.description)

    # 5. Создаём объект транзакции в БД
    db_tx = models.Transaction(
        household_id=household.id,
        user_id=user.id if user else None,
        amount=tx.amount,
        currency=tx.currency or household.currency,
        description=tx.description,
        # Строковое поле category храним в "исправленном" варианте
        category=final_category_name,
        category_id=category_id,
        merchant=merchant,
        kind=kind,
        date=tx.date or datetime.utcnow(),
    )
    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)

    # 6. Дополняем транзакцию данными по бюджету
    attach_budget_info_to_tx(db, household, db_tx)

    # 7. Навешиваем на объект дополнительные поля для схемы TransactionRead
    #    (Pydantic их заберёт, т.к. Config.from_attributes = True)
    db_tx.raw_category = raw_category_input           # что ввёл пользователь
    db_tx.suggested_category = suggested_category_name  # на что исправили
    db_tx.needs_confirmation = needs_confirmation     # нужно ли спрашивать подтверждение

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
    force_new: bool = Query(
        default=False,
        description=(
            "Если true — не искать похожие категории, "
            "а создать новую категорию с таким именем"
        ),
    ),
    db: Session = Depends(get_db),
):
    """
    Поменять категорию у последней транзакции пользователя.

    Пример:
    POST /transactions/set-category-last?telegram_id=123456789&category=Продукты
    """
    # 1. Находим пользователя и семью
    user, household = get_or_create_user_and_household(db, telegram_id)

    if not user:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required",
        )

    # 2. Проверяем, что категория не пустая
    category = category.strip()
    if not category:
        raise HTTPException(
            status_code=400,
            detail="Категория не может быть пустой",
        )

    # 3. Берём последнюю транзакцию пользователя
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

    # 4. Разруливаем категорию с учётом опечаток
    #    (тот же хелпер, что и в create_transaction)
    cat_obj, _original_name, needs_confirmation = resolve_category_with_typos(
        db=db,
        household_id=household.id,
        raw_name=category,
        force_new=force_new,
    )

    # 5. Обновляем транзакцию
    tx.category = cat_obj.name
    tx.category_id = cat_obj.id

    db.commit()
    db.refresh(tx)

    # 6. Дополняем данными по бюджету
    attach_budget_info_to_tx(db, household, tx)

    # 7. Навешиваем технические поля для ответа
    tx.raw_category = category                  # что ввёл пользователь
    tx.suggested_category = cat_obj.name        # на что исправили
    tx.needs_confirmation = needs_confirmation  # нужно ли спрашивать подтверждение

    return tx

@router.post("/parse-and-create", response_model=schemas.TransactionRead)
def parse_and_create_transaction(
    body: schemas.ParseAndCreateRequest,
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Разобрать текст через YandexGPT, применить локальные переопределения категорий
    и создать транзакцию.
    """
    import re

    user, household = get_or_create_user_and_household(db, telegram_id)
    if not user:
        raise HTTPException(status_code=400, detail="telegram_id is required")

    raw_text = body.text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="text is required")

    # --- 1. Нормализуем паттерн для поиска override ---
    normalized_pattern = raw_text.lower()
    normalized_pattern = re.sub(r"[0-9₽$€.,:/-]+", " ", normalized_pattern)
    normalized_pattern = re.sub(r"\s+", " ", normalized_pattern).strip()

    override = (
        db.query(models.CategoryOverride)
        .filter(
            models.CategoryOverride.household_id == household.id,
            models.CategoryOverride.user_id == user.id,
            models.CategoryOverride.normalized_pattern == normalized_pattern,
            models.CategoryOverride.counter >= 2,
        )
        .order_by(models.CategoryOverride.counter.desc())
        .first()
    )

    # --- 2. Вызываем YandexGPT ---
    parsed = parse_text_to_transaction(raw_text)

    amount = parsed.get("amount")
    if not amount or amount <= 0:
        raise HTTPException(status_code=400, detail="Не удалось определить сумму")

    description = parsed.get("description") or raw_text
    ai_category = parsed.get("category") or "Другое"
    candidate_categories: list[str] = parsed.get("candidate_categories") or [ai_category, "Другое"]

    # --- 3. Применяем локальный override категории ---
    final_category = ai_category
    if override:
        final_category = override.category

        # ставим override категорией №1 в candidatах
        normalized_candidates = [c.strip() for c in candidate_categories if c.strip()]
        if final_category not in normalized_candidates:
            candidate_categories.insert(0, final_category)
        else:
            # поднимаем её наверх
            candidate_categories = [final_category] + [
                c for c in normalized_candidates if c != final_category
            ]

    # нормализуем регистр для хранения
    final_category = final_category.strip().title()
    candidate_categories = [c.strip().title() for c in candidate_categories]

    # --- 4. Ищем/создаём Category ---
    category_id = None
    if final_category:
        category = (
            db.query(models.Category)
            .filter(
                models.Category.household_id == household.id,
                models.Category.name.ilike(final_category),
            )
            .first()
        )
        if not category:
            category = models.Category(household_id=household.id, name=final_category)
            db.add(category)
            db.commit()
            db.refresh(category)
        category_id = category.id

    # --- 5. Дата операции ---
    # parsed["date"] приходит как YYYY-MM-DD, если получилось распарсить
    parsed_date = parsed.get("date")
    if parsed_date:
        try:
            tx_date = datetime.strptime(parsed_date, "%Y-%m-%d")
        except ValueError:
            tx_date = datetime.utcnow()
    else:
        tx_date = datetime.utcnow()

    merchant = extract_merchant_from_text(description)

    db_tx = models.Transaction(
        household_id=household.id,
        user_id=user.id,
        amount=amount,
        currency=parsed.get("currency") or household.currency,
        description=description,
        category=final_category,
        category_id=category_id,
        merchant=merchant,
        kind="expense",
        date=tx_date,
    )

    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)

    # приклеиваем candidate_categories в атрибут, чтобы отдать в API
    db_tx.candidate_categories = candidate_categories  # type: ignore[attr-defined]

    attach_budget_info_to_tx(db, household, db_tx)

    return db_tx

@router.post("/suggest-categories", response_model=schemas.SuggestCategoriesResponse)
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
