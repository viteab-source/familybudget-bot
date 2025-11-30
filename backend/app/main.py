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


# -----------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------


def get_or_create_default_household(db: Session) -> models.Household:
    """
    Берём первую (и пока единственную) семью.
    Если её нет — создаём.
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
    # 1. Если не знаем telegram_id — работаем по старинке
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
            name=None,  # потом можно сделать команду /setname
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
    Информация только о семье (без деталей по самому пользователю).
    """

    if telegram_id is None:
        # Для Swagger можно оставить без telegram_id, но из бота он всегда есть.
        # В таком случае просто берём первую семью.
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
    # Определяем семью по telegram_id
    user, household = get_or_create_user_and_household(db, telegram_id)

    # Берём только транзакции этой семьи
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

    # Берём только расходы этой семьи
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

    # Суммируем по категориям только внутри этой семьи
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
    try:
        parsed = parse_text_to_transaction(body.text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"AI parse error: {e}")

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

    user, household = get_or_create_user_and_household(db, telegram_id)

    db_tx = models.Transaction(
        household_id=household.id,
        user_id=user.id if user else None,
        amount=amount,
        currency=currency,
        description=description,
        category=category,
        kind="expense",  # из текста считаем, что это расход
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
    (Пока привязка к конкретному пользователю по telegram_id не используется,
    но параметр оставляем для бота.)
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    next_run_at = rem.next_run_at
    if next_run_at is None and rem.interval_days:
        # если не указана конкретная дата — берём сегодня
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
    Параметр telegram_id оставляем для совместимости с ботом.
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
