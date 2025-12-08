"""
api/reminders.py — Эндпоинты для напоминаний.
GET /reminders — список напоминаний
POST /reminders — создать напоминание
GET /reminders/due-today — напоминания на сегодня
POST /reminders/{id}/mark-paid — отметить как оплачено (создаст расход и сдвинет дату)
"""

from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..deps import get_or_create_user_and_household

router = APIRouter()


@router.get("/reminders", response_model=List[schemas.ReminderRead])
def list_reminders(
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Список всех напоминаний для текущей семьи.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    reminders = (
        db.query(models.Reminder)
        .filter(models.Reminder.household_id == household.id)
        .order_by(models.Reminder.next_run_at)
        .all()
    )

    return reminders


@router.post("/reminders", response_model=schemas.ReminderRead)
def create_reminder(
    reminder: schemas.ReminderCreate,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Создать новое напоминание.
    
    Пример:
    {
        "title": "Коммуналка",
        "amount": 8000,
        "currency": "RUB",
        "interval_days": 30,
        "next_run_at": "2025-12-15T00:00:00"
    }
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    if not reminder.next_run_at:
        reminder.next_run_at = datetime.utcnow()

    db_reminder = models.Reminder(
        household_id=household.id,
        user_id=user.id if user else None,
        title=reminder.title,
        amount=reminder.amount,
        currency=reminder.currency,
        interval_days=reminder.interval_days,
        next_run_at=reminder.next_run_at,
        is_active=True,
    )

    db.add(db_reminder)
    db.commit()
    db.refresh(db_reminder)

    return db_reminder


@router.get("/reminders/due-today", response_model=List[schemas.ReminderRead])
def get_reminders_due_today(
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Получить напоминания, которые сработают сегодня.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    today_end = today_start + timedelta(days=1)

    reminders = (
        db.query(models.Reminder)
        .filter(
            models.Reminder.household_id == household.id,
            models.Reminder.is_active == True,
            models.Reminder.next_run_at >= today_start,
            models.Reminder.next_run_at < today_end,
        )
        .all()
    )

    return reminders


@router.post("/reminders/{reminder_id}/mark-paid")
def mark_reminder_paid(
    reminder_id: int,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Отметить напоминание как оплачено:
    1. Создаёт расход с суммой напоминания
    2. Сдвигает next_run_at на interval_days дней в будущее
    3. Если interval_days не задан — отключает напоминание
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    reminder = (
        db.query(models.Reminder)
        .filter(
            models.Reminder.id == reminder_id,
            models.Reminder.household_id == household.id,
        )
        .first()
    )

    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    # Создаём расход
    if reminder.amount and reminder.amount > 0:
        tx = models.Transaction(
            household_id=household.id,
            user_id=user.id if user else None,
            amount=reminder.amount,
            currency=reminder.currency,
            description=f"Напоминание: {reminder.title}",
            category=reminder.title,
            category_id=None,  # можно потом линковать на категорию
            kind="expense",
            date=datetime.utcnow(),
        )
        db.add(tx)
        db.commit()

    # Сдвигаем дату или отключаем напоминание
    if reminder.interval_days and reminder.interval_days > 0:
        reminder.next_run_at = datetime.utcnow() + timedelta(days=reminder.interval_days)
    else:
        reminder.is_active = False

    db.commit()
    db.refresh(reminder)

    return {"status": "ok", "next_run_at": reminder.next_run_at if reminder.is_active else None}


@router.post("/reminders/{reminder_id}/disable")
def disable_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Отключить напоминание.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    reminder = (
        db.query(models.Reminder)
        .filter(
            models.Reminder.id == reminder_id,
            models.Reminder.household_id == household.id,
        )
        .first()
    )

    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    reminder.is_active = False
    db.commit()

    return {"status": "ok"}


@router.delete("/reminders/{reminder_id}")
def delete_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Удалить напоминание.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    reminder = (
        db.query(models.Reminder)
        .filter(
            models.Reminder.id == reminder_id,
            models.Reminder.household_id == household.id,
        )
        .first()
    )

    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    db.delete(reminder)
    db.commit()

    return {"status": "ok"}
