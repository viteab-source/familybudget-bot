import csv
from io import StringIO
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal, get_db
from . import models, schemas
from .ai import parse_text_to_transaction

app = FastAPI(title="FamilyBudget API")


# ---------- STARTUP ----------


@app.on_event("startup")
def on_startup():
    # Создаём таблицы
    Base.metadata.create_all(bind=engine)

    # Создаём одну семью по умолчанию, если её ещё нет
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


# ---------- ТРАНЗАКЦИИ ----------


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


@app.post("/transactions/parse-and-create", response_model=schemas.TransactionRead)
def parse_and_create_transaction(
    body: schemas.ParseTextRequest,
    db: Session = Depends(get_db),
):
    """
    Принимает сырой текст (типа "Пятёрочка продукты 2435₽ вчера"),
    вызывает YandexGPT, создаёт транзакцию и возвращает её.
    """
    # 1. Парсим текст через YandexGPT
    try:
        parsed = parse_text_to_transaction(body.text)
    except Exception as e:
        # Если что-то пошло не так с ИИ — вернём 400
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

    # Дата: пытаемся прочитать, если нет — сейчас
    date_str = parsed.get("date")
    if date_str:
        try:
            date = datetime.fromisoformat(date_str)
        except ValueError:
            date = datetime.utcnow()
    else:
        date = datetime.utcnow()

    # 3. Берём (или создаём) дефолтное household
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

    # 4. Создаём транзакцию
    db_tx = models.Transaction(
        household_id=household.id,
        user_id=None,  # позже привяжем к конкретному юзеру
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


@app.get("/transactions/export/csv")
def export_transactions_csv(
    days: int = 30,
    db: Session = Depends(get_db),
):
    """
    Экспорт транзакций за N дней в CSV (для импорта в Google Sheets).
    """
    since = datetime.utcnow() - timedelta(days=days)

    txs = (
        db.query(models.Transaction)
        .filter(models.Transaction.date >= since)
        .order_by(models.Transaction.date.asc())
        .all()
    )

    buf = StringIO()
    writer = csv.writer(buf)

    # Заголовки столбцов
    writer.writerow(
        ["id", "date", "amount", "currency", "category", "description", "created_at"]
    )

    for t in txs:
        writer.writerow(
            [
                t.id,
                t.date.isoformat() if t.date else "",
                float(t.amount),
                t.currency,
                t.category or "",
                t.description or "",
                t.created_at.isoformat()
                if getattr(t, "created_at", None)
                else "",
            ]
        )

    buf.seek(0)
    filename = f"transactions_last_{days}_days.csv"

    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- REMINDERS (НАПОМИНАНИЯ) ----------


@app.post("/reminders", response_model=schemas.ReminderRead)
def create_reminder(
    reminder: schemas.ReminderCreate,
    db: Session = Depends(get_db),
):
    """
    Создаёт напоминание.
    Если next_run_at не передали — поставим сегодня.
    """
    next_run = reminder.next_run_at or datetime.utcnow()

    db_rem = models.Reminder(
        title=reminder.title,
        amount=reminder.amount,
        currency=reminder.currency,
        interval_days=reminder.interval_days,
        next_run_at=next_run,
    )
    db.add(db_rem)
    db.commit()
    db.refresh(db_rem)
    return db_rem


@app.get("/reminders", response_model=list[schemas.ReminderRead])
def list_reminders(
    only_active: bool = True,
    db: Session = Depends(get_db),
):
    """
    Список напоминаний.
    Параметр only_active=true — только активные.
    """
    query = db.query(models.Reminder)
    if only_active:
        query = query.filter(models.Reminder.is_active == True)  # noqa: E712

    reminders = (
        query.order_by(models.Reminder.next_run_at.asc().nullslast()).all()
    )
    return reminders


@app.get("/reminders/due-today", response_model=list[schemas.ReminderRead])
def reminders_due_today(
    db: Session = Depends(get_db),
):
    """
    Напоминания, которые уже наступили:
    next_run_at <= сегодня, is_active = true.
    """
    today = datetime.utcnow().date()

    reminders = (
        db.query(models.Reminder)
        .filter(models.Reminder.is_active == True)  # noqa: E712
        .filter(models.Reminder.next_run_at != None)  # noqa: E711
        .filter(func.date(models.Reminder.next_run_at) <= today)
        .order_by(models.Reminder.next_run_at.asc())
        .all()
    )

    return reminders


@app.post("/reminders/{reminder_id}/mark-paid", response_model=schemas.ReminderRead)
def mark_reminder_paid(
    reminder_id: int,
    db: Session = Depends(get_db),
):
    """
    Отмечаем напоминание как оплачено:
    - создаём транзакцию (если есть сумма)
    - сдвигаем next_run_at на interval_days, либо деактивируем напоминание
    """
    rem: models.Reminder | None = (
        db.query(models.Reminder)
        .filter(models.Reminder.id == reminder_id)
        .first()
    )
    if not rem:
        raise HTTPException(status_code=404, detail="Reminder not found")

    # 0) берём (или создаём) дефолтную семью — как в create_transaction
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

    # 1) создаём транзакцию, если указана сумма
    if rem.amount:
        tx = models.Transaction(
            household_id=household.id,
            user_id=None,
            amount=rem.amount,
            currency=rem.currency,
            description=rem.title,
            category="Плановый платеж",
            date=datetime.utcnow(),
        )
        db.add(tx)

    # 2) обновляем next_run_at или выключаем напоминание
    if rem.interval_days:
        base_date = rem.next_run_at or datetime.utcnow()
        rem.next_run_at = base_date + timedelta(days=rem.interval_days)
    else:
        rem.is_active = False

    db.commit()
    db.refresh(rem)
    return rem
