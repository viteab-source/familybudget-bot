"""
api/reports.py — Эндпоинты для отчётов.
GET /report/summary — по категориям
GET /report/balance — доходы/расходы/баланс
GET /report/members — по участникам
GET /report/shops — по магазинам
GET /transactions/export/csv — экспорт в CSV
"""

import csv
from datetime import datetime, timedelta
from io import StringIO
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..deps import get_or_create_user_and_household
from ..utils import extract_merchant_from_text

router = APIRouter()


@router.get("/report/summary", response_model=schemas.ReportSummary)
def get_report_summary(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
    category: str | None = Query(default=None, description="Фильтр по категории"),
):
    """
    Отчёт по расходам, группировано по категориям.
    Опционально фильтруем по одной категории.
    """
    since = datetime.utcnow() - timedelta(days=days)
    user, household = get_or_create_user_and_household(db, telegram_id)

    query = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.kind == "expense",
            models.Transaction.date >= since,
        )
    )

    # Если передан фильтр по категории
    if category:
        query = query.filter(
            models.Transaction.category == category
        )

    txs = query.all()

    # Считаем по категориям
    by_category = {}
    for tx in txs:
        cat = tx.category or "Без категории"
        by_category[cat] = by_category.get(cat, 0.0) + float(tx.amount)

    category_summaries = [
        schemas.CategorySummary(category=cat, amount=amount)
        for cat, amount in sorted(
            by_category.items(), key=lambda x: x[1], reverse=True
        )
    ]

    total = sum(float(tx.amount) for tx in txs)
    currency = household.currency

    return schemas.ReportSummary(
        total_amount=total,
        currency=currency,
        by_category=category_summaries,
    )


@router.get("/report/balance", response_model=schemas.BalanceReport)
def get_report_balance(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
    category: str | None = Query(default=None, description="Фильтр по категории"),
):
    """
    Баланс: доходы, расходы, чистый результат.
    Опционально фильтруем по одной категории.
    """
    since = datetime.utcnow() - timedelta(days=days)
    user, household = get_or_create_user_and_household(db, telegram_id)

    query = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
        )
    )

    # Если передан фильтр по категории
    if category:
        query = query.filter(
            models.Transaction.category == category
        )

    txs = query.all()

    expenses = sum(
        float(tx.amount) for tx in txs if tx.kind == "expense"
    )
    incomes = sum(
        float(tx.amount) for tx in txs if tx.kind == "income"
    )
    net = incomes - expenses

    return schemas.BalanceReport(
        days=days,
        expenses_total=expenses,
        incomes_total=incomes,
        net=net,
        currency=household.currency,
    )


@router.get("/report/members", response_model=schemas.MembersReport)
def get_report_members(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
    category: str | None = Query(default=None, description="Фильтр по категории"),
):
    """
    Отчёт по участникам: кто сколько потратил.
    Опционально фильтруем по одной категории.
    """
    since = datetime.utcnow() - timedelta(days=days)
    user, household = get_or_create_user_and_household(db, telegram_id)

    query = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.kind == "expense",
            models.Transaction.date >= since,
        )
    )

    # Если передан фильтр по категории
    if category:
        query = query.filter(
            models.Transaction.category == category
        )

    txs = query.all()

    # Группируем по пользователям
    by_user = {}
    for tx in txs:
        user_id = tx.user_id or 0
        if user_id not in by_user:
            by_user[user_id] = {
                "user": tx.user,
                "amount": 0.0,
            }
        by_user[user_id]["amount"] += float(tx.amount)

    members = [
        schemas.MemberExpenseSummary(
            user_id=user_id,
            name=info["user"].name if info["user"] else None,
            telegram_id=info["user"].telegram_id if info["user"] else None,
            amount=info["amount"],
        )
        for user_id, info in sorted(
            by_user.items(), key=lambda x: x[1]["amount"], reverse=True
        )
    ]

    return schemas.MembersReport(
        days=days,
        currency=household.currency,
        members=members,
    )


@router.get("/report/shops", response_model=schemas.ShopsReport)
def get_report_shops(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Отчёт по магазинам/сервисам: кому сколько потратили.
    """
    since = datetime.utcnow() - timedelta(days=days)
    user, household = get_or_create_user_and_household(db, telegram_id)

    txs = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.kind == "expense",
            models.Transaction.date >= since,
        )
        .all()
    )

    totals = {}
    for tx in txs:
        merchant = tx.merchant

        # 1. Если уже в транзакции есть merchant — используем его
        if not merchant:
            # 2. Если не заполнен — пробуем определить из описания/категории
            base_text = (tx.description or "") + " " + (tx.category or "")
            merchant = extract_merchant_from_text(base_text)

        if not merchant:
            continue

        totals[merchant] = totals.get(merchant, 0.0) + float(tx.amount)

    tx_any = txs[0] if txs else None
    currency = tx_any.currency if tx_any else household.currency

    shops = [
        schemas.ShopSummary(merchant=name, amount=totals[name])
        for name in sorted(totals.keys(), key=lambda k: totals[k], reverse=True)
    ]

    return schemas.ShopsReport(
        days=days,
        currency=currency,
        shops=shops,
    )


@router.get("/transactions/export/csv")
def export_transactions_csv(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Экспорт транзакций в CSV за последние N дней.
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
