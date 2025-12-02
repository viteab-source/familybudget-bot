from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    BigInteger,
)
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # связи
    households = relationship("HouseholdMember", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    reminders = relationship("Reminder", back_populates="user")


class Household(Base):
    __tablename__ = "households"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    currency = Column(String(10), nullable=False, default="RUB")
    privacy_mode = Column(String(20), nullable=False, default="OPEN")
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship(
        "HouseholdMember",
        back_populates="household",
        cascade="all, delete-orphan",
    )
    transactions = relationship("Transaction", back_populates="household")
    reminders = relationship("Reminder", back_populates="household")

    # НОВОЕ: категории
    categories = relationship(
        "Category",
        back_populates="household",
        cascade="all, delete-orphan",
    )

    # НОВОЕ: приглашения в семью
    invites = relationship(
        "HouseholdInvite",
        back_populates="household",
        cascade="all, delete-orphan",
    )


class HouseholdMember(Base):
    __tablename__ = "household_members"

    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(
        Integer,
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(20), nullable=False, default="member")
    created_at = Column(DateTime, default=datetime.utcnow)

    household = relationship("Household", back_populates="members")
    user = relationship("User", back_populates="households")


class Category(Base):
    """
    Категория расходов/доходов.

    Пока минимально:
    - name — название категории
    - household_id — к какой семье относится
    - parent_id / sort_order — на будущее (иерархия и порядок).
    """

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)

    household_id = Column(
        Integer,
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )

    name = Column(String(50), nullable=False)

    parent_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    sort_order = Column(Integer, nullable=True)

    household = relationship("Household", back_populates="categories")
    parent = relationship("Category", remote_side=[id])
    transactions = relationship("Transaction", back_populates="category_ref")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)

    household_id = Column(
        Integer,
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="RUB")
    description = Column(String, nullable=True)
    # Название магазина / сервиса (опционально)
    merchant = Column(String(100), nullable=True)

    # Старое строковое поле категории — пока оставляем,
    # чтобы ничего не сломать в отчётах и боте.
    category = Column(String(50), nullable=True)

    # НОВОЕ: ссылка на таблицу categories
    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    # НОВОЕ: тип операции — расход или доход
    # expense — расход, income — доход
    kind = Column(String(20), nullable=False, default="expense", index=True)

    date = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    household = relationship("Household", back_populates="transactions")
    user = relationship("User", back_populates="transactions")
    category_ref = relationship("Category", back_populates="transactions")


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)

    household_id = Column(
        Integer,
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    title = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(10), nullable=False, default="RUB")
    interval_days = Column(Integer, nullable=True)  # каждые N дней
    next_run_at = Column(DateTime, nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    household = relationship("Household", back_populates="reminders")
    user = relationship("User", back_populates="reminders")

class CategoryBudget(Base):
    __tablename__ = "category_budgets"

    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    limit_amount = Column(Numeric(12, 2), nullable=False, default=0)
    period_month = Column(String, nullable=False)  # YYYY-MM (например "2025-12")

    created_at = Column(DateTime, default=datetime.utcnow)

    household = relationship("Household", backref="category_budgets")
    category = relationship("Category")

class HouseholdInvite(Base):
    """
    Приглашения в семью.

    code — короткий рандомный код (6–8 символов),
    по которому можно присоединиться к семье.
    """

    __tablename__ = "household_invites"

    id = Column(Integer, primary_key=True, index=True)

    household_id = Column(
        Integer,
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )

    code = Column(String(16), unique=True, index=True, nullable=False)

    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    household = relationship("Household", back_populates="invites")
    created_by_user = relationship("User")
