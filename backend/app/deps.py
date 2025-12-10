"""
Зависимости для FastAPI эндпоинтов.
Общие функции, которые используются в разных роутерах.
"""
from typing import Tuple
from sqlalchemy.orm import Session
from . import models
from .db import SessionLocal


def get_db():
    """
    Зависимость FastAPI для получения сессии БД.
    Автоматически закрывает сессию после запроса.
    
    Используется так:
    @app.get("/endpoint")
    def my_endpoint(db: Session = Depends(get_db)):
        ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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


def get_or_create_user_and_household(
    db: Session,
    telegram_id: int | None,
) -> Tuple[models.User | None, models.Household]:
    """
    Возвращает (user, household) для данного telegram_id.
    
    Логика:
    1. Если telegram_id = None → возвращаем дефолтную семью (для Swagger)
    2. Если пользователь существует → находим его семью
    3. Если пользователь новый → создаём его и новую семью
    
    Примеры:
    - user, household = get_or_create_user_and_household(db, 123456789)
    - user будет объектом User
    - household будет объектом Household
    """
    # 1. Если не знаем telegram_id — работаем по-старому (для Swagger)
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
        # Пользователь уже в семье
        household = membership.household
    else:
        # 4. Если ни в одной семье нет — создаём новую семью
        household = models.Household(
            name=f"Семья {telegram_id}",
            currency="RUB",
            privacy_mode="OPEN",
        )
        db.add(household)
        db.commit()
        db.refresh(household)

        # Привязываем пользователя к новой семье как owner
        membership = models.HouseholdMember(
            user_id=user.id,
            household_id=household.id,
            role="owner",
        )
        db.add(membership)
        db.commit()

    return user, household
