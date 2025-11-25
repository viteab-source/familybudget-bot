from datetime import datetime

from fastapi import FastAPI, Depends
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
        # Проверяем, есть ли хоть одна семья
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


# Эндпоинт для создания транзакции
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

    # Создаём объект транзакции
    db_tx = models.Transaction(
        household_id=household.id,
        user_id=None,  # позже привяжем к конкретному пользователю
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


# Эндпоинт для получения списка транзакций
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
