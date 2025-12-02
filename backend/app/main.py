from datetime import datetime, timedelta
import csv
from io import StringIO
from typing import List
import secrets
import string

from fastapi import FastAPI, Depends, HTTPException, Query

from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .db import Base, engine, SessionLocal, get_db
from . import models, schemas
from .ai import parse_text_to_transaction

app = FastAPI(title="FamilyBudget API")


# -----------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------

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

INVITE_CODE_LENGTH = 8

def attach_budget_info_to_tx(
    db: Session,
    household: models.Household,
    tx: models.Transaction,
) -> None:
    """
    Дополнить объект транзакции полями:
      - budget_limit
      - budget_spent
      - budget_percent
    Если бюджета для категории нет — просто ничего не делаем.
    """
    # Только для расходов и только если есть категория
    if tx.kind != "expense" or not tx.category_id:
        return

    tx_date = tx.date or datetime.utcnow()
    period_month = tx_date.strftime("%Y-%m")

    # Границы месяца
    month_start = datetime(tx_date.year, tx_date.month, 1)
    if tx_date.month == 12:
        next_month_start = datetime(tx_date.year + 1, 1, 1)
    else:
        next_month_start = datetime(tx_date.year, tx_date.month + 1, 1)

    # Ищем бюджет для этой категории
    budget = (
        db.query(models.CategoryBudget)
        .filter(
            models.CategoryBudget.household_id == household.id,
            models.CategoryBudget.category_id == tx.category_id,
            models.CategoryBudget.period_month == period_month,
        )
        .first()
    )
    if not budget:
        return

    # Считаем, сколько уже потрачено за месяц по этой категории
    spent = (
        db.query(func.sum(models.Transaction.amount))
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.category_id == tx.category_id,
            models.Transaction.kind == "expense",
            models.Transaction.date >= month_start,
            models.Transaction.date < next_month_start,
        )
        .scalar()
        or 0
    )

    limit_val = float(budget.limit_amount or 0)
    spent_val = float(spent)
    percent = (spent_val / limit_val * 100) if limit_val > 0 else 0.0

    # Вешаем на объект tx новые атрибуты — Pydantic их заберёт
    tx.budget_limit = limit_val
    tx.budget_spent = spent_val
    tx.budget_percent = round(percent, 1)

def generate_invite_code(db: Session, length: int = INVITE_CODE_LENGTH) -> str:
    """
    Генерирует уникальный короткий код приглашения из заглавных букв и цифр.

    Примеры кодов: AB7K3F, X9L2MD и т.п.
    """
    # Базовый алфавит: A-Z + 0-9
    alphabet = string.ascii_uppercase + string.digits

    # Убираем похожие символы, чтобы код было легче читать/вводить
    ambiguous = "O0I1"
    alphabet = "".join(ch for ch in alphabet if ch not in ambiguous)

    # До 20 попыток найти свободный код
    for _ in range(20):
        code = "".join(secrets.choice(alphabet) for _ in range(length))

        exists = (
            db.query(models.HouseholdInvite)
            .filter(models.HouseholdInvite.code == code)
            .first()
        )
        if not exists:
            return code

    # Если совсем не повезло — кидаем 500-ю ошибку
    raise HTTPException(
        status_code=500,
        detail="Не удалось сгенерировать код приглашения, попробуй ещё раз",
    )

# -----------------------
# СТАРТ ПРИЛОЖЕНИЯ
# -----------------------


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        get_or_create_default_household(db)
    finally:
        db.close()


# -----------------------
# СЕРВИС
# -----------------------


@app.get("/health")
def health_check():
    return {"status": "ok"}


# -----------------------
# ПОЛЬЗОВАТЕЛЬ И СЕМЬЯ
# -----------------------


@app.get("/me", response_model=schemas.MeResponse)
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


@app.get("/household", response_model=schemas.HouseholdInfo)
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

@app.get("/household/invite", response_model=schemas.HouseholdInvite)
def get_household_invite(
    telegram_id: int | None = Query(
        default=None,
        description="Telegram ID пользователя (для вызовов из бота)",
    ),
    db: Session = Depends(get_db),
):
    """
    Получить код приглашения в семью текущего пользователя.

    Теперь:
    - код = случайная строка (6–8 символов),
    - хранится в таблице household_invites.
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

@app.post("/household/join", response_model=schemas.HouseholdInfo)
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
    - код = строка из household_invites.code.

    Legacy-вариант (для старых инвайтов):
    - если код — число, пробуем трактовать как id семьи.
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

@app.post("/household/rename", response_model=schemas.HouseholdInfo)
def rename_household(
    body: schemas.HouseholdRenameRequest,
    telegram_id: int | None = Query(
        default=None,
        description="Telegram ID пользователя (для вызовов из бота)",
    ),
    db: Session = Depends(get_db),
):
    """
    Переименовать семью. Можно только owner/admin.
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


@app.post("/user/set-name")
def set_user_name(
    body: schemas.UserSetNameRequest,
    telegram_id: int | None = Query(
        default=None,
        description="Telegram ID пользователя (для вызовов из бота)",
    ),
    db: Session = Depends(get_db),
):
    """
    Обновить имя пользователя (display name), которое будет видно в семье и отчётах.
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

@app.post("/household/leave")
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
    - Если пользователь не состоит в семье → 400.
    - Если пользователь owner и в семье есть другие участники → 400
      (нужно сначала передать роль или удалить участников).
    - Если пользователь owner и он один в семье → удаляем и его membership,
      и саму семью.
    - Если обычный участник → просто удаляем его membership.
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

# -----------------------
# ТРАНЗАКЦИИ
# -----------------------


@app.post("/transactions", response_model=schemas.TransactionRead)
def create_transaction(
    tx: schemas.TransactionCreate,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Создать транзакцию (расход или доход).
    kind:
      - "expense" (по умолчанию)
      - "income"
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    kind = (tx.kind or "expense").lower()
    if kind not in ("expense", "income"):
        raise HTTPException(
            status_code=400,
            detail="kind должен быть 'expense' или 'income'",
        )

    db_tx = models.Transaction(
        household_id=household.id,
        user_id=user.id if user else None,
        amount=tx.amount,
        currency=tx.currency or household.currency,
        description=tx.description,
        category=tx.category,
        kind=kind,
        date=tx.date or datetime.utcnow(),
    )

    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)
    # Дополняем транзакцию данными по бюджету (если есть)
    attach_budget_info_to_tx(db, household, db_tx)
    return db_tx


@app.get("/transactions", response_model=list[schemas.TransactionRead])
def list_transactions(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    kind: str | None = Query(
        default=None,
        description="Фильтр по типу: expense / income",
    ),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Список транзакций.
    Можно фильтровать по дате и по типу операции (расход/доход).
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    query = db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id
    )

    if start_date:
        query = query.filter(models.Transaction.date >= start_date)
    if end_date:
        query = query.filter(models.Transaction.date <= end_date)

    if kind is not None:
        kind = kind.lower()
        if kind not in ("expense", "income"):
            raise HTTPException(
                status_code=400,
                detail="kind должен быть 'expense' или 'income'",
            )
        query = query.filter(models.Transaction.kind == kind)

    transactions = query.order_by(models.Transaction.date.desc()).all()
    return transactions


@app.get("/report/summary", response_model=schemas.ReportSummary)
def report_summary(
    days: int = Query(14, ge=1, le=365),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Краткий отчёт: СУММА РАСХОДОВ и разрез по категориям за N дней.
    (Доходы сюда не включаем, это отдельный отчёт баланса.)
    """
    since = datetime.utcnow() - timedelta(days=days)

    user, household = get_or_create_user_and_household(db, telegram_id)

    txs = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
            models.Transaction.kind == "expense",
        )
        .all()
    )

    total_amount = float(sum(t.amount for t in txs)) if txs else 0.0

    rows = (
        db.query(
            models.Transaction.category,
            func.sum(models.Transaction.amount).label("total"),
        )
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
            models.Transaction.kind == "expense",
        )
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


@app.get("/report/balance", response_model=schemas.BalanceReport)
def report_balance(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Баланс за период:
    - общие доходы
    - общие расходы
    - итог (доходы - расходы)
    """
    since = datetime.utcnow() - timedelta(days=days)

    user, household = get_or_create_user_and_household(db, telegram_id)

    txs = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
        )
        .all()
    )

    expenses = float(sum(t.amount for t in txs if t.kind == "expense"))
    incomes = float(sum(t.amount for t in txs if t.kind == "income"))

    currency = "RUB"
    if txs:
        currency = txs[0].currency

    net = incomes - expenses

    return schemas.BalanceReport(
        days=days,
        expenses_total=expenses,
        incomes_total=incomes,
        net=net,
        currency=currency,
    )

@app.get("/report/members", response_model=schemas.MembersReport)
def report_members(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Отчёт по людям: кто сколько потратил (расходы) за N дней.
    """
    since = datetime.utcnow() - timedelta(days=days)

    user, household = get_or_create_user_and_household(db, telegram_id)

    # Сумма расходов по каждому пользователю семьи
    rows = (
        db.query(
            models.User.id.label("user_id"),
            models.User.name,
            models.User.telegram_id,
            func.sum(models.Transaction.amount).label("total"),
        )
        .join(models.Transaction, models.Transaction.user_id == models.User.id)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
            models.Transaction.kind == "expense",
        )
        .group_by(models.User.id, models.User.name, models.User.telegram_id)
        .order_by(func.sum(models.Transaction.amount).desc())
        .all()
    )

    # Определяем валюту: из любой подходящей транзакции, либо из семьи
    tx_any = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
            models.Transaction.kind == "expense",
        )
        .first()
    )
    currency = tx_any.currency if tx_any else household.currency

    members = [
        schemas.MemberExpenseSummary(
            user_id=row.user_id,
            name=row.name,
            telegram_id=row.telegram_id,
            amount=float(row.total),
        )
        for row in rows
    ]

    return schemas.MembersReport(
        days=days,
        currency=currency,
        members=members,
    )


@app.get("/transactions/export/csv")
def export_transactions_csv(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Экспорт транзакций в CSV за последние N дней.
    """
    since = datetime.utcnow() - timedelta(days=days)

    user, household = get_or_create_user_and_household(db, telegram_id)

    txs = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.date >= since,
        )
        .order_by(models.Transaction.date.asc())
        .all()
    )

    def generate():
        output = StringIO()
        writer = csv.writer(output, delimiter=";")

        writer.writerow(
            [
                "id",
                "date",
                "kind",
                "amount",
                "currency",
                "category",
                "description",
            ]
        )
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for tx in txs:
            writer.writerow(
                [
                    tx.id,
                    tx.date.strftime("%Y-%m-%d %H:%M:%S") if tx.date else "",
                    tx.kind,
                    float(tx.amount),
                    tx.currency,
                    tx.category or "",
                    tx.description or "",
                ]
            )
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    headers = {
        "Content-Disposition": f'attachment; filename="transactions_{days}d.csv"'
    }

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers=headers,
    )

# -----------------------
# КАТЕГОРИИ 2.0
# -----------------------

@app.get("/categories", response_model=List[schemas.CategoryRead])
def list_categories(
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Список категорий для текущей семьи.

    Дополнительно:
    - берём все уникальные category из транзакций этой семьи;
    - для тех, которых ещё нет в таблице categories, создаём записи;
    - затем возвращаем полный список категорий.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    # 1) Уже существующие категории в таблице categories
    existing_q = db.query(models.Category.name).filter(
        models.Category.household_id == household.id
    )
    existing_names = {
        (name or "").strip().lower()
        for (name,) in existing_q.all()
        if name
    }

    # 2) Уникальные названия категорий из транзакций
    tx_categories = (
        db.query(models.Transaction.category)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.category.isnot(None),
            models.Transaction.category != "",
        )
        .distinct()
        .all()
    )

    created = False
    for (cat_name,) in tx_categories:
        if not cat_name:
            continue
        normalized = cat_name.strip().lower()
        if not normalized or normalized in existing_names:
            continue

        db_cat = models.Category(
            household_id=household.id,
            name=cat_name.strip(),
        )
        db.add(db_cat)
        existing_names.add(normalized)
        created = True

    if created:
        db.commit()

    # 3) Финальный список категорий
    categories = (
        db.query(models.Category)
        .filter(models.Category.household_id == household.id)
        .order_by(
            models.Category.sort_order.is_(None),  # None в конец
            models.Category.sort_order,
            models.Category.name,
        )
        .all()
    )
    return categories

@app.post("/categories", response_model=schemas.CategoryRead)
def create_category(
    category: schemas.CategoryCreate,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Создать новую категорию для текущей семьи.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    name = category.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название категории не может быть пустым")

    # Чуть защищаемся от дублей по имени внутри семьи (без учёта регистра)
    existing = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            func.lower(models.Category.name) == func.lower(name),
        )
        .first()
    )
    if existing:
        return existing

    # Swagger часто шлёт parent_id = 0 -> превращаем в NULL
    parent_id = category.parent_id
    if parent_id in (0, -1):
        parent_id = None

    db_cat = models.Category(
        household_id=household.id,
        name=name,
        parent_id=parent_id,
        sort_order=category.sort_order,
    )
    db.add(db_cat)
    db.commit()
    db.refresh(db_cat)
    return db_cat

@app.post("/categories/rename", response_model=schemas.CategoryRead)
def rename_category(
    old_name: str = Query(..., description="Старое название категории"),
    new_name: str = Query(..., description="Новое название категории"),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Переименовать категорию внутри текущей семьи.

    old_name / new_name — обычные строки.
    Поиск по имени — без учёта регистра.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    old_name_clean = old_name.strip()
    new_name_clean = new_name.strip()

    if not old_name_clean or not new_name_clean:
        raise HTTPException(
            status_code=400,
            detail="Старое и новое название категории не могут быть пустыми",
        )

    # Ищем категорию по старому имени
    cat = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            func.lower(models.Category.name) == func.lower(old_name_clean),
        )
        .first()
    )
    if not cat:
        raise HTTPException(
            status_code=404,
            detail=f"Категория «{old_name_clean}» не найдена",
        )

    # Проверяем, нет ли категории с таким новым именем
    duplicate = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            func.lower(models.Category.name) == func.lower(new_name_clean),
            models.Category.id != cat.id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=400,
            detail=f"Категория «{new_name_clean}» уже существует",
        )

    # Обновляем имя категории
    cat.name = new_name_clean

    # Обновляем строковое поле category у всех транзакций,
    # которые привязаны к этой категории
    db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id,
        models.Transaction.category_id == cat.id,
    ).update({"category": new_name_clean}, synchronize_session=False)

    db.commit()
    db.refresh(cat)
    return cat

@app.post("/categories/merge", response_model=schemas.CategoryRead)
def merge_categories(
    source_name: str = Query(..., description="Какую категорию объединяем (будет удалена)"),
    target_name: str = Query(..., description="В какую категорию переносим все данные"),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Слить две категории внутри текущей семьи.

    Все транзакции из source -> в target.
    source категория удаляется.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    source_name_clean = (source_name or "").strip()
    target_name_clean = (target_name or "").strip()

    if not source_name_clean or not target_name_clean:
        raise HTTPException(
            status_code=400,
            detail="Старое и новое название категории не могут быть пустыми",
        )

    if source_name_clean.lower() == target_name_clean.lower():
        raise HTTPException(
            status_code=400,
            detail="Нельзя объединить категорию саму с собой",
        )

    # 1. Ищем source категорию
    source_cat = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            func.lower(models.Category.name) == func.lower(source_name_clean),
        )
        .first()
    )
    if not source_cat:
        raise HTTPException(
            status_code=404,
            detail=f"Категория «{source_name_clean}» не найдена",
        )

    # 2. Ищем/создаём target категорию
    target_cat = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            func.lower(models.Category.name) == func.lower(target_name_clean),
        )
        .first()
    )
    if not target_cat:
        target_cat = models.Category(
            household_id=household.id,
            name=target_name_clean,
        )
        db.add(target_cat)
        db.flush()  # чтобы получить id

    # 3. Переносим транзакции из source в target
    db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id,
        models.Transaction.category_id == source_cat.id,
    ).update(
        {
            "category_id": target_cat.id,
            "category": target_cat.name,
        },
        synchronize_session=False,
    )

    # На всякий случай обновим транзакции, где category строкой совпадает
    db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id,
        models.Transaction.category_id.is_(None),
        func.lower(models.Transaction.category) == func.lower(source_name_clean),
    ).update(
        {
            "category_id": target_cat.id,
            "category": target_cat.name,
        },
        synchronize_session=False,
    )

    # 4. Удаляем старую категорию
    db.delete(source_cat)

    db.commit()
    db.refresh(target_cat)
    return target_cat

@app.post("/budget/set", response_model=dict)
def set_budget(
    category_name: str = Query(..., description="Название категории"),
    limit_amount: float = Query(..., description="Лимит на месяц"),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    user, household = get_or_create_user_and_household(db, telegram_id)

    now = datetime.utcnow()
    period_month = now.strftime("%Y-%m")

    category = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            func.lower(models.Category.name) == func.lower(category_name),
        )
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail=f"Категория «{category_name}» не найдена")

    budget = (
        db.query(models.CategoryBudget)
        .filter(
            models.CategoryBudget.household_id == household.id,
            models.CategoryBudget.category_id == category.id,
            models.CategoryBudget.period_month == period_month,
        )
        .first()
    )

    if not budget:
        budget = models.CategoryBudget(
            household_id=household.id,
            category_id=category.id,
            limit_amount=limit_amount,
            period_month=period_month,
        )
        db.add(budget)
    else:
        budget.limit_amount = limit_amount

    db.commit()
    return {"ok": True, "category": category.name, "limit": limit_amount, "period": period_month}

@app.get("/budget/status", response_model=dict)
def budget_status(
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Статус бюджетов по категориям за текущий месяц.
    Возвращает:
    {
      "month": "2025-12",
      "budgets": [
        { "category": "Продукты", "limit": 50000, "spent": 12345, "percent": 24.7 },
        ...
      ]
    }
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    now = datetime.utcnow()
    period_month = now.strftime("%Y-%m")

    # Границы текущего месяца: [month_start; next_month_start)
    month_start = datetime(now.year, now.month, 1)
    if now.month == 12:
        next_month_start = datetime(now.year + 1, 1, 1)
    else:
        next_month_start = datetime(now.year, now.month + 1, 1)

    budgets = (
        db.query(models.CategoryBudget)
        .filter(
            models.CategoryBudget.household_id == household.id,
            models.CategoryBudget.period_month == period_month,
        )
        .all()
    )

    result: list[dict] = []
    for b in budgets:
        spent = (
            db.query(func.sum(models.Transaction.amount))
            .filter(
                models.Transaction.household_id == household.id,
                models.Transaction.category_id == b.category_id,
                models.Transaction.kind == "expense",
                models.Transaction.date >= month_start,
                models.Transaction.date < next_month_start,
            )
            .scalar()
            or 0
        )

        percent = round((spent / b.limit_amount) * 100, 1) if b.limit_amount > 0 else 0

        result.append(
            {
                "category": b.category.name,
                "limit": b.limit_amount,
                "spent": spent,
                "percent": percent,
            }
        )

    return {"month": period_month, "budgets": result}

@app.post("/transactions/set-category-last", response_model=schemas.TransactionRead)
def set_last_transaction_category(
    category: str = Query(..., description="Новое название категории"),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Поменять категорию у последней транзакции текущего пользователя в этой семье.
    Параллельно создаём (или находим) категорию в таблице categories
    и привязываем транзакцию к ней.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    name = (category or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название категории не может быть пустым")

    tx = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.user_id == user.id,
        )
        .order_by(models.Transaction.created_at.desc())
        .first()
    )

    if not tx:
        raise HTTPException(status_code=404, detail="У тебя ещё нет транзакций")

    # Ищем существующую категорию (без учёта регистра)
    existing = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            func.lower(models.Category.name) == func.lower(name),
        )
        .first()
    )

    if existing:
        db_cat = existing
    else:
        db_cat = models.Category(
            household_id=household.id,
            name=name,
        )
        db.add(db_cat)
        db.flush()  # чтобы получить id без отдельного коммита

    # Обновляем транзакцию: и строковое поле, и ссылку на категорию
    tx.category = name
    tx.category_id = db_cat.id

    db.commit()
    db.refresh(tx)
    return tx

@app.post(
    "/transactions/parse-and-create",
    response_model=schemas.TransactionRead,
)
def parse_and_create_transaction(
    body: schemas.ParseTextRequest,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Парсит текст через YandexGPT, создаёт транзакцию и возвращает её.
    По умолчанию — РАСХОД (kind='expense').
    """
    # 1. Парсим текст через ИИ
    try:
        parsed = parse_text_to_transaction(body.text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"AI parse error: {e}")

    # 2. Сумма: сначала пробуем взять из ИИ, если он облажался — ищем число в исходном тексте
    raw_amount = parsed.get("amount") if isinstance(parsed, dict) else None
    amount: float | None = None

    # 2.1. Пытаемся распарсить то, что вернул ИИ
    if raw_amount is not None:
        try:
            amount = float(raw_amount)
        except Exception:
            amount = None

    # 2.2. Если ИИ не дал нормальную сумму (None или <= 0) — пробуем достать число из исходного текста
    if amount is None or amount <= 0:
        import re as _re

        match = _re.search(r"(\d+[.,]?\d*)", body.text)
        if match:
            num_str = match.group(1).replace(",", ".")
            try:
                amount = float(num_str)
            except Exception:
                amount = None

    # 2.3. Финальная проверка
    if amount is None or amount <= 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Некорректная сумма: сумма должна быть больше нуля. "
                "Скорее всего, в тексте не было числа или его не получилось разобрать."
            ),
        )

    # 3. Остальные поля из ИИ
    currency = parsed.get("currency") or "RUB"
    description = parsed.get("description") or body.text

    raw_category = parsed.get("category")
    category_name = (raw_category or "").strip() or None

    date_str = parsed.get("date")
    if date_str:
        try:
            date = datetime.fromisoformat(date_str)
        except ValueError:
            date = datetime.utcnow()
    else:
        date = datetime.utcnow()

    # 4. Находим/создаём пользователя и семью
    user, household = get_or_create_user_and_household(db, telegram_id)

    # 5. Привязываем категорию к таблице categories (если есть имя)
    category_obj = None
    if category_name:
        category_obj = (
            db.query(models.Category)
            .filter(
                models.Category.household_id == household.id,
                func.lower(models.Category.name) == func.lower(category_name),
            )
            .first()
        )
        if category_obj is None:
            # создаём новую категорию в этой семье
            category_obj = models.Category(
                household_id=household.id,
                name=category_name,
            )
            db.add(category_obj)
            db.flush()  # чтобы появился id

    # 6. Создаём транзакцию
    db_tx = models.Transaction(
        household_id=household.id,
        user_id=user.id if user else None,
        amount=amount,
        currency=currency,
        description=description,
        # строковое имя категории — либо из объекта, либо как есть
        category=category_obj.name if category_obj else category_name,
        # ссылка на категорию (если нашли/создали)
        category_id=category_obj.id if category_obj else None,
        kind="expense",
        date=date,
    )

    try:
        db.add(db_tx)
        db.commit()
        db.refresh(db_tx)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при сохранении транзакции: {e}",
        )

    # Дополняем транзакцию данными по бюджету (если есть)
    attach_budget_info_to_tx(db, household, db_tx)

    return db_tx


# -----------------------
# НАПОМИНАНИЯ
# -----------------------


@app.post("/reminders", response_model=schemas.ReminderRead)
def create_reminder(
    rem: schemas.ReminderCreate,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Создать напоминание.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    next_run_at = rem.next_run_at
    if next_run_at is None and rem.interval_days:
        next_run_at = datetime.utcnow()

    db_rem = models.Reminder(
        household_id=household.id,
        user_id=user.id if user else None,
        title=rem.title,
        amount=rem.amount,
        currency=rem.currency,
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
    only_active: bool = True,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Список напоминаний (по умолчанию только активные).
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    query = db.query(models.Reminder).filter(
        models.Reminder.household_id == household.id
    )

    if only_active:
        query = query.filter(models.Reminder.is_active.is_(True))

    reminders = query.order_by(models.Reminder.next_run_at.asc()).all()
    return reminders


@app.get(
    "/reminders/due-today",
    response_model=list[schemas.ReminderRead],
)
def reminders_due_today(
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Напоминания, которые нужно оплатить сегодня (и просроченные).
    """
    today = datetime.utcnow().date()
    tomorrow = today + timedelta(days=1)

    user, household = get_or_create_user_and_household(db, telegram_id)

    query = db.query(models.Reminder).filter(
        models.Reminder.household_id == household.id,
        models.Reminder.is_active.is_(True),
        models.Reminder.next_run_at < datetime.combine(
            tomorrow, datetime.min.time()
        ),
    )

    return query.order_by(models.Reminder.next_run_at.asc()).all()


@app.post(
    "/reminders/{reminder_id}/mark-paid",
    response_model=schemas.ReminderRead,
)
def mark_reminder_paid(
    reminder_id: int,
    db: Session = Depends(get_db),
):
    """
    Отметить напоминание как оплачено.
    Если интервал не задан — деактивируем напоминание.
    Если интервал есть — сдвигаем next_run_at на interval_days вперёд.
    """
    rem = (
        db.query(models.Reminder)
        .filter(models.Reminder.id == reminder_id)
        .first()
    )

    if rem is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    if not rem.interval_days:
        rem.is_active = False
        rem.next_run_at = None
    else:
        if rem.next_run_at is None:
            rem.next_run_at = datetime.utcnow()
        rem.next_run_at = rem.next_run_at + timedelta(days=rem.interval_days)

    try:
        db.commit()
        db.refresh(rem)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    return rem
