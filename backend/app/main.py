from datetime import datetime, timedelta

from fastapi import FastAPI, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal, get_db
from . import models, schemas

app = FastAPI(title="FamilyBudget API")


# При старте приложения:
# 1) создаём таблицы
# 2) создаём одну семью по умолчанию, если её ещё нет
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        default_household = db.query(models.Household).first()
        if default_household is None:
            default_household = models.Household(
                name="Default family",
                currency="RUB",
                privacy_mode="OPEN",
            )
            db.add(default_household)
            db.commit()
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/transactions", response_model=schemas.TransactionRead)
def create_transaction(
    tx: schemas.TransactionCreate,
    db: Session = Depends(get_db),
):
    # Берём первую (и пока единственную) семью
    household = db.query(models.Household).first()

    # На всякий случай: если по какой-то причине семьи нет — создадим
    if household is None:
        household = models.Household(
            name="Default family",
            currency="RUB",
            privacy_mode="OPEN",
        )
        db.add(household)
        db.commit()
        db.refresh(household)

    db_tx = models.Transaction(
        household_id=household.id,
        user_id=None,
        amount=tx.amount,
        currency=tx.currency,
        description=tx.description,
        category=tx.category,
        date=tx.date or datetime.utcnow(),
    )

    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)

    return db_tx


@app.get("/transactions", response_model=list[schemas.TransactionRead])
def list_transactions(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Transaction)

    if start_date:
        query = query.filter(models.Transaction.date >= start_date)
    if end_date:
        query = query.filter(models.Transaction.date <= end_date)

    transactions = query.order_by(models.Transaction.date.desc()).all()
    return transactions


@app.get("/report/summary", response_model=schemas.ReportSummary)
def report_summary(
    days: int = 14,
    db: Session = Depends(get_db),
):
    """Краткий отчёт: сумма и разрез по категориям за N дней."""
    since = datetime.utcnow() - timedelta(days=days)

    # Все транзакции за период
    txs = (
        db.query(models.Transaction)
        .filter(models.Transaction.date >= since)
        .all()
    )

    total_amount = float(sum(t.amount for t in txs)) if txs else 0.0

    # Группировка по категориям
    rows = (
        db.query(
            models.Transaction.category,
            func.sum(models.Transaction.amount).label("total"),
        )
        .filter(models.Transaction.date >= since)
        .group_by(models.Transaction.category)
        .all()
    )

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
