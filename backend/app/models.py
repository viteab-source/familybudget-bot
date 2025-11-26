from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    # храним как строку, чтобы не зависеть от размера int
    telegram_id = Column(String, unique=True, index=True, nullable=False)

    full_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    language_code = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="user")
    reminders = relationship("Reminder", back_populates="user")
    memberships = relationship("HouseholdMember", back_populates="user")


class Household(Base):
    __tablename__ = "households"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    currency = Column(String, default="RUB")
    privacy_mode = Column(String, default="OPEN")

    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="household")
    reminders = relationship("Reminder", back_populates="household")
    members = relationship("HouseholdMember", back_populates="household")


class HouseholdMember(Base):
    __tablename__ = "household_members"

    id = Column(Integer, primary_key=True, index=True)

    household_id = Column(Integer, ForeignKey("households.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, default="MEMBER")

    created_at = Column(DateTime, default=datetime.utcnow)

    household = relationship("Household", back_populates="members")
    user = relationship("User", back_populates="memberships")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)

    household_id = Column(Integer, ForeignKey("households.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    amount = Column(Float, nullable=False)
    currency = Column(String, default="RUB")
    description = Column(String, nullable=True)
    category = Column(String, nullable=True)

    date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    household = relationship("Household", back_populates="transactions")
    user = relationship("User", back_populates="transactions")


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)

    household_id = Column(Integer, ForeignKey("households.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    title = Column(String, nullable=False)
    amount = Column(Float, nullable=True)
    currency = Column(String, default="RUB")

    interval_days = Column(Integer, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    household = relationship("Household", back_populates="reminders")
    user = relationship("User", back_populates="reminders")
