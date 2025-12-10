"""
Эндпоинты для работы с напоминаниями.
"""
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..deps import get_or_create_user_and_household

router = APIRouter()


@router.post("", response_model=schemas.ReminderRead)
def create_reminder(
    reminder: schemas.ReminderCreate,
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Создать напоминание.
    
    Пример:
    POST /reminders?telegram_id=123456789
    Body: {
        "title": "Коммуналка",
        "amount": 8000,
        "currency": "RUB",
        "interval_days": 30,
        "next_run_at": null
    }
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    # Если next_run_at не указан — берём сегодня
    next_run = reminder.next_run_at or datetime.utcnow()

    db_reminder = models.Reminder(
        household_id=household.id,
        user_id=user.id if user else None,
        title=reminder.title,
        amount=reminder.amount,
        currency=reminder.currency or household.currency,
        interval_days=reminder.interval_days,
        next_run_at=next_run,
        is_active=True,
    )

    db.add(db_reminder)
    db.commit()
    db.refresh(db_reminder)

    return db_reminder


@router.get("", response_model=List[schemas.ReminderRead])
def list_reminders(
    only_active: bool = Query(default=True, description="Показывать только активные"),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Список напоминаний семьи.
    
    Пример:
    GET /reminders?telegram_id=123456789&only_active=true
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    query = db.query(models.Reminder).filter(
        models.Reminder.household_id == household.id
    )

    if only_active:
        query = query.filter(models.Reminder.is_active == True)

    reminders = query.order_by(models.Reminder.next_run_at).all()

    return reminders


@router.get("/due-today", response_model=List[schemas.ReminderRead])
def get_due_reminders(
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Напоминания "на сегодня" — те, у которых next_run_at <= сегодня.
    
    Пример:
    GET /reminders/due-today?telegram_id=123456789
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    now = datetime.utcnow()

    reminders = (
        db.query(models.Reminder)
        .filter(
            models.Reminder.household_id == household.id,
            models.Reminder.is_active == True,
            models.Reminder.next_run_at <= now,
        )
        .order_by(models.Reminder.next_run_at)
        .all()
    )

    return reminders


@router.post("/{reminder_id}/mark-paid")
def mark_reminder_paid(
    reminder_id: int = Path(..., description="ID напоминания"),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Отметить напоминание как оплачено.
    
    Логика:
    - Если у напоминания есть сумма → создаёт транзакцию-расход
    - Если есть interval_days → сдвигает next_run_at на интервал
    - Если interval_days нет → делает напоминание неактивным
    
    Пример:
    POST /reminders/5/mark-paid?telegram_id=123456789
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
        raise HTTPException(
            status_code=404,
            detail="Напоминание не найдено",
        )

    # Создаём транзакцию, если есть сумма
    if reminder.amount:
        # Ищем или создаём категорию по названию напоминания
        category_name = reminder.title.strip()
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

        # Создаём транзакцию
        transaction = models.Transaction(
            household_id=household.id,
            user_id=reminder.user_id,
            amount=reminder.amount,
            currency=reminder.currency,
            description=reminder.title,
            category=category_name,
            category_id=category.id,
            kind="expense",
            date=datetime.utcnow(),
        )
        db.add(transaction)

    # Обновляем напоминание
    if reminder.interval_days:
        # Сдвигаем на интервал
        reminder.next_run_at = datetime.utcnow() + timedelta(days=reminder.interval_days)
    else:
        # Делаем неактивным
        reminder.is_active = False

    db.commit()

    return {
        "status": "ok",
        "message": "Напоминание отмечено как оплаченное",
        "reminder_id": reminder_id,
        "transaction_created": reminder.amount is not None,
    }
