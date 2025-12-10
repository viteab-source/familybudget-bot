"""
Эндпоинты для работы с семьями (households).
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..deps import get_or_create_user_and_household
from ..utils import generate_invite_code

router = APIRouter()


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
    
    Генерирует короткий код (например: "AB7K3F").
    Код действует 30 дней.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    # Генерируем уникальный код
    code = generate_invite_code(db)

    invite = models.HouseholdInvite(
        household_id=household.id,
        code=code,
        created_by_user_id=user.id if user else None,
        # Код действует 30 дней
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
    
    Основной вариант:
    - код = строка из household_invites.code (например: "AB7K3F")
    
    Legacy-вариант (для старых инвайтов):
    - если код — число, пробуем трактовать как id семьи
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

    # Собираем список участников семьи
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
    telegram_id: int | None = Query(
        default=None,
        description="Telegram ID пользователя (для вызовов из бота)",
    ),
    db: Session = Depends(get_db),
):
    """
    Переименовать семью.
    Можно только owner/admin.
    """
    if telegram_id is None:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required for /household/rename",
        )

    user = (
        db.query(models.User)
        .filter(models.User.telegram_id == telegram_id)
        .first()
    )

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    membership = (
        db.query(models.HouseholdMember)
        .filter(models.HouseholdMember.user_id == user.id)
        .first()
    )

    if membership is None:
        raise HTTPException(status_code=400, detail="User has no household")

    if membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Only owner/admin can rename household",
        )

    household = (
        db.query(models.Household)
        .filter(models.Household.id == membership.household_id)
        .first()
    )

    if household is None:
        raise HTTPException(status_code=404, detail="Household not found")

    household.name = body.name
    db.commit()
    db.refresh(household)

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
    telegram_id: int | None = Query(
        default=None,
        description="Telegram ID пользователя (для вызовов из бота)",
    ),
    db: Session = Depends(get_db),
):
    """
    Выйти из текущей семьи.
    
    Правила:
    - Если пользователь не состоит в семье → 400
    - Если пользователь owner и в семье есть другие участники → 400
      (нужно сначала передать роль или удалить участников)
    - Если пользователь owner и он один в семье → удаляем и его membership,
      и саму семью
    - Если обычный участник → просто удаляем его membership
    """
    if telegram_id is None:
        raise HTTPException(
            status_code=400,
            detail="telegram_id is required for /household/leave",
        )

    # Находим пользователя
    user = (
        db.query(models.User)
        .filter(models.User.telegram_id == telegram_id)
        .first()
    )

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Находим его membership
    membership = (
        db.query(models.HouseholdMember)
        .filter(models.HouseholdMember.user_id == user.id)
        .first()
    )

    if membership is None:
        raise HTTPException(
            status_code=400,
            detail="User has no household to leave",
        )

    household = (
        db.query(models.Household)
        .filter(models.Household.id == membership.household_id)
        .first()
    )

    if household is None:
        raise HTTPException(status_code=404, detail="Household not found")

    # Считаем количество участников семьи
    members_count = (
        db.query(models.HouseholdMember)
        .filter(models.HouseholdMember.household_id == household.id)
        .count()
    )

    # Если он owner и есть ещё участники — запрещаем выход
    if membership.role == "owner" and members_count > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "Owner не может выйти из семьи, пока есть другие участники. "
                "Сначала передай права или удали участников."
            ),
        )

    # Если он owner и он один — удаляем семью целиком
    if membership.role == "owner" and members_count == 1:
        db.delete(membership)
        db.delete(household)
        db.commit()
        return {"status": "ok", "message": "Семья удалена, ты вышел из семьи"}

    # Обычный участник — просто удаляем membership
    db.delete(membership)
    db.commit()
    return {"status": "ok", "message": "Ты вышел из семьи"}
