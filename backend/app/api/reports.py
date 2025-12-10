"""
Эндпоинты для отчётов.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models, schemas
from ..db import get_db
from ..deps import get_or_create_user_and_household
from ..utils import extract_merchant_from_text

router = APIRouter()


@router.get("/summary", response_model=schemas.ReportSummary)
def report_summary(
    days: int = Query(14, ge=1, le=365),
    telegram_id: int | None = Query(default=None),
    user_id: int | None = Query(default=None, description="Фильтр по конкретному пользователю"),
    db: Session = Depends(get_db),
):
    """
    Краткий отчёт: СУММА РАСХОДОВ и разрез по категориям за N дней.
    (Доходы сюда не включаем, это отдельный отчёт баланса.)
    
    Если указан user_id — показываем только расходы этого пользователя.
    
    Пример:
    GET /report/summary?telegram_id=123456789&days=14
    GET /report/summary?telegram_id=123456789&days=14&user_id=5
    """
    since = datetime.utcnow() - timedelta(days=days)
    user, household = get_or_create_user_and_household(db, telegram_id)

    query = db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id,
        models.Transaction.date >= since,
        models.Transaction.kind == "expense",
    )

    # Фильтр по пользователю (если указан)
    if user_id is not None:
        query = query.filter(models.Transaction.user_id == user_id)

    txs = query.all()

    total_amount = float(sum(t.amount for t in txs)) if txs else 0.0

    # Группировка по категориям
    rows = (
        db.query(
            models.Transaction.category,
            func.sum(models.Transaction.amount).label("total"),
        )
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
            models.Transaction.kind == "expense",
        )
    )

    if user_id is not None:
        rows = rows.filter(models.Transaction.user_id == user_id)

    rows = rows.group_by(models.Transaction.category).all()

    by_category = [
        schemas.CategorySummary(
            category=row[0],
            amount=float(row[1]),
        )
        for row in rows
    ]

    currency = "RUB"
    if txs:
        currency = txs[0].currency

    return schemas.ReportSummary(
        total_amount=total_amount,
        currency=currency,
        by_category=by_category,
    )


@router.get("/balance", response_model=schemas.BalanceReport)
def report_balance(
    days: int = Query(30, ge=1, le=365),
    telegram_id: int | None = Query(default=None),
    user_id: int | None = Query(default=None, description="Фильтр по конкретному пользователю"),
    db: Session = Depends(get_db),
):
    """
    Баланс за период:
    - общие доходы
    - общие расходы
    - итог (доходы - расходы)
    
    Если указан user_id — показываем только операции этого пользователя.
    
    Пример:
    GET /report/balance?telegram_id=123456789&days=30
    GET /report/balance?telegram_id=123456789&days=30&user_id=5
    """
    since = datetime.utcnow() - timedelta(days=days)
    user, household = get_or_create_user_and_household(db, telegram_id)

    query = db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id,
        models.Transaction.date >= since,
    )

    # Фильтр по пользователю (если указан)
    if user_id is not None:
        query = query.filter(models.Transaction.user_id == user_id)

    txs = query.all()

    expenses = float(sum(t.amount for t in txs if t.kind == "expense"))
    incomes = float(sum(t.amount for t in txs if t.kind == "income"))

    currency = "RUB"
    if txs:
        currency = txs[0].currency

    net = incomes - expenses

    return schemas.BalanceReport(
        days=days,
        expenses_total=expenses,
        incomes_total=incomes,
        net=net,
        currency=currency,
    )


@router.get("/members", response_model=schemas.MembersReport)
def report_members(
    days: int = Query(30, ge=1, le=365),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Отчёт по людям: кто сколько потратил (расходы) за N дней.
    
    Пример:
    GET /report/members?telegram_id=123456789&days=30
    """
    since = datetime.utcnow() - timedelta(days=days)
    user, household = get_or_create_user_and_household(db, telegram_id)

    # Сумма расходов по каждому пользователю семьи
    rows = (
        db.query(
            models.User.id.label("user_id"),
            models.User.name,
            models.User.telegram_id,
            func.sum(models.Transaction.amount).label("total"),
        )
        .join(models.Transaction, models.Transaction.user_id == models.User.id)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
            models.Transaction.kind == "expense",
        )
        .group_by(models.User.id, models.User.name, models.User.telegram_id)
        .order_by(func.sum(models.Transaction.amount).desc())
        .all()
    )

    # Определяем валюту: из любой подходящей транзакции, либо из семьи
    tx_any = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
            models.Transaction.kind == "expense",
        )
        .first()
    )

    currency = tx_any.currency if tx_any else household.currency

    members = [
        schemas.MemberExpenseSummary(
            user_id=row.user_id,
            name=row.name,
            telegram_id=row.telegram_id,
            amount=float(row.total),
        )
        for row in rows
    ]

    return schemas.MembersReport(
        days=days,
        currency=currency,
        members=members,
    )


@router.get("/shops", response_model=schemas.ShopsReport)
def report_shops(
    days: int = Query(30, ge=1, le=365),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Отчёт по магазинам (merchant) за N дней.
    
    Использует поле Transaction.merchant, если оно пустое —
    пытается найти по тексту description.
    
    Пример:
    GET /report/shops?telegram_id=123456789&days=30
    """
    since = datetime.utcnow() - timedelta(days=days)
    user, household = get_or_create_user_and_household(db, telegram_id)

    # Берём только расходы за период
    txs = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
            models.Transaction.kind == "expense",
        )
        .all()
    )

    totals: dict[str, float] = {}

    for tx in txs:
        # Используем merchant из базы
        merchant = tx.merchant
        
        # Если пусто — пробуем вытащить из description
        if not merchant:
            merchant = extract_merchant_from_text(tx.description)
        
        # Если всё ещё пусто — пробуем из строкового поля category
        if not merchant:
            merchant = extract_merchant_from_text(tx.category)

        if not merchant:
            continue

        amount = float(tx.amount or 0)
        totals[merchant] = totals.get(merchant, 0.0) + amount

    # Собираем список, убираем нулевые
    shops = [
        schemas.ShopSummary(merchant=name, amount=round(total, 2))
        for name, total in totals.items()
        if total > 0
    ]

    # Сортируем по сумме
    shops.sort(key=lambda s: s.amount, reverse=True)

    return schemas.ShopsReport(
        days=days,
        currency=household.currency,
        shops=shops,
    )
