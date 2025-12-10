"""
Эндпоинты для работы с пользователями.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .. import models, schemas
from ..db import get_db
from ..deps import get_or_create_user_and_household

# Создаём роутер — это как мини-приложение внутри FastAPI
router = APIRouter()


@router.get("/me", response_model=schemas.MeResponse)
def get_me(
    telegram_id: int | None = Query(
        default=None,
        description="Telegram ID пользователя (для вызовов из бота)",
    ),
    db: Session = Depends(get_db),
):
    """
    Информация о текущем пользователе и его семье.
    
    Возвращает:
    - Данные пользователя (user_id, telegram_id, name)
    - Данные семьи (household_id, household_name, currency)
    - Роль пользователя в семье (owner/admin/member)
    - Список всех участников семьи
    """
    if telegram_id is None:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required for /me",
        )

    # Находим или создаём пользователя по telegram_id
    user = (
        db.query(models.User)
        .filter(models.User.telegram_id == telegram_id)
        .first()
    )

    if user is None:
        user = models.User(telegram_id=telegram_id)
        db.add(user)
        db.commit()
        db.refresh(user)

    # Проверяем, есть ли у него семья
    membership = (
        db.query(models.HouseholdMember)
        .filter(models.HouseholdMember.user_id == user.id)
        .first()
    )

    if membership is None:
        # Создаём новую семью и привязываем пользователя как owner
        household = models.Household(
            name=f"Семья {telegram_id}",
            currency="RUB",
            privacy_mode="OPEN",
        )
        db.add(household)
        db.commit()
        db.refresh(household)

        membership = models.HouseholdMember(
            household_id=household.id,
            user_id=user.id,
            role="owner",
        )
        db.add(membership)
        db.commit()
        db.refresh(membership)
    else:
        household = (
            db.query(models.Household)
            .filter(models.Household.id == membership.household_id)
            .first()
        )
        if household is None:
            raise HTTPException(
                status_code=500,
                detail="Household not found for membership",
            )

    # Собираем всех участников семьи
    member_rows = (
        db.query(models.HouseholdMember)
        .join(models.User, models.HouseholdMember.user_id == models.User.id)
        .filter(models.HouseholdMember.household_id == household.id)
        .all()
    )

    members = [
        schemas.MemberShort(
            id=m.user.id,
            name=m.user.name,
            telegram_id=m.user.telegram_id,
            role=m.role,
        )
        for m in member_rows
    ]

    return schemas.MeResponse(
        user_id=user.id,
        telegram_id=user.telegram_id,
        name=user.name,
        household_id=household.id,
        household_name=household.name,
        currency=household.currency,
        privacy_mode=household.privacy_mode,
        role=membership.role,
        members=members,
    )


@router.post("/user/set-name")
def set_user_name(
    body: schemas.UserSetNameRequest,
    telegram_id: int | None = Query(
        default=None,
        description="Telegram ID пользователя (для вызовов из бота)",
    ),
    db: Session = Depends(get_db),
):
    """
    Обновить имя пользователя (display name).
    
    Это имя будет видно в семье и отчётах.
    
    Пример:
    POST /user/set-name?telegram_id=123456789
    Body: {"name": "Витя"}
    """
    if telegram_id is None:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required for /user/set-name",
        )

    user, household = get_or_create_user_and_household(db, telegram_id)

    if user is None:
        raise HTTPException(
            status_code=500,
            detail="User not found for given telegram_id",
        )

    user.name = body.name

    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    return {"status": "ok"}
