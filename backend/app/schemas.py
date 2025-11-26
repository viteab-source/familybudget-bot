from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


# ---------- TRANSACTIONS ----------


class TransactionCreate(BaseModel):
    amount: float
    currency: str = "RUB"
    description: Optional[str] = None
    category: Optional[str] = None
    date: Optional[datetime] = None

    # кто именно создал (из Telegram)
    telegram_id: Optional[int] = None
    telegram_name: Optional[str] = None
    telegram_username: Optional[str] = None


class TransactionRead(BaseModel):
    id: int
    household_id: int
    user_id: Optional[int]

    amount: float
    currency: str
    description: Optional[str]
    category: Optional[str]
    date: datetime
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ParseTextRequest(BaseModel):
    text: str

    telegram_id: Optional[int] = None
    telegram_name: Optional[str] = None
    telegram_username: Optional[str] = None


class CategorySummary(BaseModel):
    category: Optional[str]
    amount: float


class ReportSummary(BaseModel):
    total_amount: float
    currency: str
    by_category: List[CategorySummary]


# ---------- REMINDERS ----------


class ReminderCreate(BaseModel):
    title: str
    amount: Optional[float] = None
    currency: str = "RUB"
    interval_days: Optional[int] = None
    next_run_at: Optional[datetime] = None

    telegram_id: Optional[int] = None
    telegram_name: Optional[str] = None
    telegram_username: Optional[str] = None


class ReminderRead(BaseModel):
    id: int
    household_id: Optional[int]
    user_id: Optional[int]

    title: str
    amount: Optional[float]
    currency: str
    interval_days: Optional[int]
    next_run_at: Optional[datetime]
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
