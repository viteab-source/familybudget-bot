from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Numeric,
)
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=False)
    language = Column(String, default="ru")
    created_at = Column(DateTime, default=datetime.utcnow)

    households = relationship("HouseholdMember", back_populates="user")


class Household(Base):
    __tablename__ = "households"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    currency = Column(String, default="RUB")
    privacy_mode = Column(String, default="OPEN")  # OPEN / AGGREGATED / ADMIN_ONLY
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship("HouseholdMember", back_populates="household")
    transactions = relationship("Transaction", back_populates="household")


class HouseholdMember(Base):
    __tablename__ = "household_members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    household_id = Column(Integer, ForeignKey("households.id"), nullable=False)
    role = Column(String, default="MEMBER")  # ADMIN / MEMBER

    user = relationship("User", back_populates="households")
    household = relationship("Household", back_populates="members")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="RUB")
    description = Column(String, nullable=True)
    category = Column(String, nullable=True)
    date = Column(DateTime, default=datetime.utcnow)

    created_at = Column(DateTime, default=datetime.utcnow)

    household = relationship("Household", back_populates="transactions")

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.sql import func

from .db import Base


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)          # Название: "Коммуналка", "Садик" и т.п.
    amount = Column(Float, nullable=True)           # Сумма платежа (можно не задавать)
    currency = Column(String(3), nullable=False, default="RUB")

    # Через сколько дней повторять (30 — раз в ~месяц, 7 — раз в неделю и т.д.)
    interval_days = Column(Integer, nullable=True)

    # Когда в следующий раз напомнить
    next_run_at = Column(DateTime(timezone=True), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

