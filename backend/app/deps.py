"""
deps.py — Общие зависимости для FastAPI.
Содержит функции, которые используются как Depends() в эндпоинтах.
"""

from fastapi import HTTPException, Query
from sqlalchemy.orm import Session
from .db import get_db
from . import models


def get_or_create_user_and_household(
    db: Session,
    telegram_id: int | None,
) -> tuple[models.User | None, models.Household]:
    """
    Возвращает (user, household) для данного telegram_id.
    Если telegram_id не передан (None) — используем глобальную Default family
    и user=None. Это нужно, чтобы всё работало через Swagger / ручные запросы.
    """
    # 1. Если не знаем telegram_id — работаем по-старому
    if telegram_id is None:
        household = get_or_create_default_household(db)
        return None, household

    # 2. Ищем пользователя по telegram_id
    user = (
        db.query(models.User)
        .filter(models.User.telegram_id == telegram_id)
        .first()
    )

    # Если не нашли — создаём
    if user is None:
        user = models.User(
            telegram_id=telegram_id,
            name=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # 3. Ищем его участие в какой-либо семье
    membership = (
        db.query(models.HouseholdMember)
        .filter(models.HouseholdMember.user_id == user.id)
        .first()
    )

    if membership:
        household = membership.household
    else:
        # 4. Если ни в одной семье нет — создаём новую семью и привязываем его
        household = models.Household(
            name=f"Семья {telegram_id}",
            currency="RUB",
            privacy_mode="OPEN",
        )
        db.add(household)
        db.commit()
        db.refresh(household)

        membership = models.HouseholdMember(
            user_id=user.id,
            household_id=household.id,
            role="owner",
        )
        db.add(membership)
        db.commit()

    return user, household


def get_or_create_default_household(db: Session) -> models.Household:
    """
    Берём первую семью в базе, если её нет — создаём.
    Нужна для Swagger / ручных запросов без telegram_id.
    """
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
