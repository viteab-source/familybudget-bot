"""
api/users.py — Эндпоинты для пользователей и семей.
Всё про /me, /household, /household/invite, /household/join и т.п.
"""

from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..deps import get_or_create_user_and_household, get_or_create_default_household
from ..utils import generate_invite_code


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


@router.get("/household", response_model=schemas.HouseholdInfo)
def get_household(
    telegram_id: int | None = Query(
        default=None,
        description="Telegram ID пользователя (для вызовов из бота)",
    ),
    db: Session = Depends(get_db),
):
    """
    Информация о семье и участниках.
    Если telegram_id не передан — берём первую семью (для Swagger).
    """
    if telegram_id is None:
        household = db.query(models.Household).first()
        if household is None:
            raise HTTPException(status_code=404, detail="Household not found")
    else:
        # Повторяем ту же логику, что и в /me
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

        membership = (
            db.query(models.HouseholdMember)
            .filter(models.HouseholdMember.user_id == user.id)
            .first()
        )

        if membership is None:
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

    return schemas.HouseholdInfo(
        id=household.id,
        name=household.name,
        currency=household.currency,
        privacy_mode=household.privacy_mode,
        members=members,
    )


@router.get("/household/invite", response_model=schemas.HouseholdInvite)
def get_household_invite(
    telegram_id: int | None = Query(
        default=None,
        description="Telegram ID пользователя (для вызовов из бота)",
    ),
    db: Session = Depends(get_db),
):
    """
    Получить код приглашения в семью текущего пользователя.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    # генерируем уникальный код
    code = generate_invite_code(db)

    invite = models.HouseholdInvite(
        household_id=household.id,
        code=code,
        created_by_user_id=user.id if user else None,
        # можно регулировать срок действия; пока на 30 дней
        expires_at=datetime.utcnow() + timedelta(days=30),
    )

    db.add(invite)
    db.commit()
    db.refresh(invite)

    return schemas.HouseholdInvite(code=invite.code)


@router.post("/household/join", response_model=schemas.HouseholdInfo)
def join_household(
    body: schemas.HouseholdJoinRequest,
    telegram_id: int | None = Query(
        default=None,
        description="Telegram ID пользователя (для вызовов из бота)",
    ),
    db: Session = Depends(get_db),
):
    """
    Присоединиться к семье по коду приглашения.
    """
    if telegram_id is None:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required for /household/join",
        )

    raw_code = (body.code or "").strip()

    if not raw_code:
        raise HTTPException(status_code=400, detail="Invite code is empty")

    normalized_code = raw_code.upper()

    household: models.Household | None = None

    # 1. Пытаемся найти инвайт по новому формату (рандомный код)
    invite = (
        db.query(models.HouseholdInvite)
        .filter(models.HouseholdInvite.code == normalized_code)
        .first()
    )

    if invite is not None:
        # Проверяем срок действия (если задан)
        if invite.expires_at and invite.expires_at < datetime.utcnow():
            raise HTTPException(status_code=404, detail="Invite code expired")

        household = invite.household
    else:
        # 2. Legacy: если код — число, трактуем как id семьи
        try:
            household_id = int(raw_code)
        except ValueError:
            raise HTTPException(status_code=404, detail="Invite code not found")

        household = (
            db.query(models.Household)
            .filter(models.Household.id == household_id)
            .first()
        )

        if household is None:
            raise HTTPException(status_code=404, detail="Household not found")

    # Находим/создаём пользователя по telegram_id
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

    # Проверяем, нет ли уже такого участника в этой семье
    membership = (
        db.query(models.HouseholdMember)
        .filter(
            models.HouseholdMember.user_id == user.id,
            models.HouseholdMember.household_id == household.id,
        )
        .first()
    )

    if membership is None:
        membership = models.HouseholdMember(
            user_id=user.id,
            household_id=household.id,
            role="member",
        )
        db.add(membership)
        db.commit()

    # Возвращаем инфо о семье
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

    return schemas.HouseholdInfo(
        id=household.id,
        name=household.name,
        currency=household.currency,
        privacy_mode=household.privacy_mode,
        members=members,
    )


@router.post("/household/rename", response_model=schemas.HouseholdInfo)
def rename_household(
    body: schemas.HouseholdRenameRequest,
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Переименовать семью."""
    user, household = get_or_create_user_and_household(db, telegram_id)

    new_name = (body.name or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Название не может быть пустым")

    household.name = new_name
    db.commit()

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

    return schemas.HouseholdInfo(
        id=household.id,
        name=household.name,
        currency=household.currency,
        privacy_mode=household.privacy_mode,
        members=members,
    )


@router.post("/household/leave")
def leave_household(
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Выйти из семьи."""
    if telegram_id is None:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required",
        )

    user, household = get_or_create_user_and_household(db, telegram_id)

    membership = (
        db.query(models.HouseholdMember)
        .filter(
            models.HouseholdMember.user_id == user.id,
            models.HouseholdMember.household_id == household.id,
        )
        .first()
    )

    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    # Проверяем условия выхода
    if membership.role == "owner":
        # owner может выйти только если он один в семье
        other_members = (
            db.query(models.HouseholdMember)
            .filter(
                models.HouseholdMember.household_id == household.id,
                models.HouseholdMember.id != membership.id,
            )
            .count()
        )
        if other_members > 0:
            raise HTTPException(
                status_code=403,
                detail="Owner не может выйти, если в семье ещё есть участники",
            )

        # Удаляем саму семью (каскадно удалит всех участников)
        db.delete(household)
        db.commit()
    else:
        # Обычный участник может просто выйти
        db.delete(membership)
        db.commit()

    return {"status": "ok"}


@router.post("/user/set-name")
def set_user_name(
    body: schemas.UserSetNameRequest,
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Установить имя пользователя."""
    if telegram_id is None:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required",
        )

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

    new_name = (body.name or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Имя не может быть пустым")

    user.name = new_name
    db.commit()

    return {"status": "ok", "name": user.name}
