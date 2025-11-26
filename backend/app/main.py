# backend/app/main.py

from datetime import datetime, timedelta
import csv
from io import StringIO

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .db import Base, engine, SessionLocal, get_db
from . import models, schemas
from .ai import parse_text_to_transaction


app = FastAPI(title="FamilyBudget API")


# ---- ВСПОМОГАТЕЛЬНОЕ ----

def get_or_create_default_household(db: Session) -> models.Household:
    """Возвращает первую (дефолтную) семью, при отсутствии — создаёт."""
    household = db.query(models.Household).first()
    if household is None:
        household = models.Household(
            name="Default family",
            currency="RUB",
            privacy_mode="OPEN",
        )
        db.add(household)
        db.commit()
        db.refresh(household)
    return household


# ---- СТАРТ ПРИЛОЖЕНИЯ ----

@app.on_event("startup")
def on_startup():
    # Создаём все таблицы в Postgres, если их ещё нет
    Base.metadata.create_all(bind=engine)

    # Инициализируем дефолтную семью
    db = SessionLocal()
    try:
        get_or_create_default_household(db)
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ---- ТРАНЗАКЦИИ ----

@app.post("/transactions", response_model=schemas.TransactionRead)
def create_transaction(
    tx: schemas.TransactionCreate,
    db: Session = Depends(get_db),
):
    household = get_or_create_default_household(db)

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

    return query.order_by(models.Transaction.date.desc()).all()


@app.get("/report/summary", response_model=schemas.ReportSummary)
def report_summary(
    days: int = 14,
    db: Session = Depends(get_db),
):
    """Краткий отчёт: сумма и разрез по категориям за N дней."""
    since = datetime.utcnow() - timedelta(days=days)

    txs = (
        db.query(models.Transaction)
        .filter(models.Transaction.date >= since)
        .all()
    )

    total_amount = float(sum(t.amount for t in txs)) if txs else 0.0

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

    currency = txs[0].currency if txs else "RUB"

    return schemas.ReportSummary(
        total_amount=total_amount,
        currency=currency,
        by_category=by_category,
    )


# ---- ТРАНЗАКЦИЯ ЧЕРЕЗ ИИ ----

@app.post("/transactions/parse-and-create", response_model=schemas.TransactionRead)
def parse_and_create_transaction(
    body: schemas.ParseTextRequest,
    db: Session = Depends(get_db),
):
    """
    Принимает сырой текст (типa "Пятёрочка продукты 2435₽ вчера"),
    вызывает YandexGPT, создаёт транзакцию и возвращает её.
    """

    # 1. Парсим текст через YandexGPT
    try:
        parsed = parse_text_to_transaction(body.text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"AI parse error: {e}")

    # 2. Достаём поля из ответа
    try:
        amount = float(parsed["amount"])
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"Некорректная сумма в ответе ИИ: {parsed!r}",
        )

    currency = parsed.get("currency") or "RUB"
    description = parsed.get("description") or body.text
    category = parsed.get("category")

    date_str = parsed.get("date")
    if date_str:
        try:
            date = datetime.fromisoformat(date_str)
        except ValueError:
            date = datetime.utcnow()
    else:
        date = datetime.utcnow()

    # 3. Создаём транзакцию
    household = get_or_create_default_household(db)

    db_tx = models.Transaction(
        household_id=household.id,
        user_id=None,
        amount=amount,
        currency=currency,
        description=description,
        category=category,
        date=date,
    )

    try:
        db.add(db_tx)
        db.commit()
        db.refresh(db_tx)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    return db_tx


# ---- НАПОМИНАНИЯ ----

@app.post("/reminders", response_model=schemas.ReminderRead)
def create_reminder(
    rem: schemas.ReminderCreate,
    db: Session = Depends(get_db),
):
    """
    Создать напоминание.
    next_run_at, если не задан, ставим на сегодня.
    """
    household = get_or_create_default_household(db)

    next_run_at = rem.next_run_at or datetime.utcnow()

    db_rem = models.Reminder(
        household_id=household.id,
        title=rem.title,
        amount=rem.amount,
        currency=rem.currency or household.currency,
        interval_days=rem.interval_days,
        next_run_at=next_run_at,
        is_active=True,
    )

    try:
        db.add(db_rem)
        db.commit()
        db.refresh(db_rem)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    return db_rem


@app.get("/reminders", response_model=list[schemas.ReminderRead])
def list_reminders(
    only_active: bool = Query(False),
    telegram_id: int | None = None,  # сейчас не используем, но бот может его слать
    db: Session = Depends(get_db),
):
    """
    Список напоминаний.
    only_active=true — только активные.
    telegram_id пока игнорируем, позже привяжем к пользователям.
    """
    query = db.query(models.Reminder)

    if only_active:
        query = query.filter(models.Reminder.is_active.is_(True))

    return query.order_by(models.Reminder.next_run_at.asc()).all()


@app.get("/reminders/due-today", response_model=list[schemas.ReminderRead])
def reminders_due_today(
    telegram_id: int | None = None,  # тоже пока просто принимаем
    db: Session = Depends(get_db),
):
    """
    Напоминания, которые нужно оплатить сегодня (и всё, что просрочено).
    """
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    tomorrow_start = today_start + timedelta(days=1)

    query = (
        db.query(models.Reminder)
        .filter(
            models.Reminder.is_active.is_(True),
            models.Reminder.next_run_at < tomorrow_start,
        )
        .order_by(models.Reminder.next_run_at.asc())
    )

    return query.all()


@app.post("/reminders/{reminder_id}/mark-paid", response_model=schemas.ReminderRead)
def mark_reminder_paid(
    reminder_id: int,
    db: Session = Depends(get_db),
):
    """
    Отметить напоминание как оплачено:
    - создаём транзакцию (если есть amount)
    - сдвигаем next_run_at на interval_days или выключаем напоминание
    """
    rem = db.query(models.Reminder).get(reminder_id)
    if not rem:
        raise HTTPException(status_code=404, detail="Reminder not found")

    now = datetime.utcnow()
    household = get_or_create_default_household(db)

    # Создаём транзакцию, если есть сумма
    if rem.amount is not None:
        tx = models.Transaction(
            household_id=household.id,
            user_id=None,
            amount=rem.amount,
            currency=rem.currency,
            description=rem.title,
            category="Напоминания",
            date=now,
        )
        db.add(tx)

    # Обновляем next_run_at / деактивируем
    if rem.interval_days:
        rem.next_run_at = now + timedelta(days=rem.interval_days)
    else:
        rem.is_active = False

    try:
        db.commit()
        db.refresh(rem)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    return rem


# ---- ЭКСПОРТ В CSV ----

@app.get("/transactions/export/csv")
def export_transactions_csv(
    days: int = 30,
    db: Session = Depends(get_db),
):
    """
    Экспорт всех транзакций за последние N дней в CSV.
    Используется ботом в команде /export.
    """
    since = datetime.utcnow() - timedelta(days=days)

    txs = (
        db.query(models.Transaction)
        .filter(models.Transaction.date >= since)
        .order_by(models.Transaction.date.asc())
        .all()
    )

    output = StringIO()
    writer = csv.writer(output)

    # Заголовок
    writer.writerow(
        ["id", "date", "amount", "currency", "category", "description", "created_at"]
    )

    for tx in txs:
        writer.writerow(
            [
                tx.id,
                tx.date.isoformat() if tx.date else "",
                float(tx.amount) if tx.amount is not None else "",
                tx.currency or "",
                tx.category or "",
                tx.description or "",
                tx.created_at.isoformat() if tx.created_at else "",
            ]
        )

    output.seek(0)

    filename = f"transactions_{days}d.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers=headers,
    )
