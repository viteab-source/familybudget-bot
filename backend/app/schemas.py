from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


# -----------------------
# ТРАНЗАКЦИИ
# -----------------------


class TransactionBase(BaseModel):
    amount: float
    currency: str = "RUB"
    description: Optional[str] = None
    category: Optional[str] = None
    date: Optional[datetime] = None

    # НОВОЕ: тип операции
    # "expense" — расход, "income" — доход
    kind: str = "expense"

    class Config:
        from_attributes = True


class TransactionCreate(TransactionBase):
    pass


class TransactionRead(TransactionBase):
    id: int
    household_id: int
    user_id: Optional[int] = None
    created_at: datetime


# -----------------------
# ОТЧЁТЫ
# -----------------------


class CategorySummary(BaseModel):
    category: Optional[str]
    amount: float

    class Config:
        from_attributes = True


class ReportSummary(BaseModel):
    total_amount: float
    currency: str
    by_category: List[CategorySummary]


class BalanceReport(BaseModel):
    """
    Отчёт по балансу за период:
    доходы, расходы, итог.
    """

    days: int
    expenses_total: float
    incomes_total: float
    net: float  # incomes_total - expenses_total
    currency: str


# -----------------------
# НАПОМИНАНИЯ
# -----------------------


class ReminderBase(BaseModel):
    title: str
    amount: Optional[float] = None
    currency: str = "RUB"
    interval_days: Optional[int] = None
    next_run_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReminderCreate(ReminderBase):
    pass


class ReminderRead(ReminderBase):
    id: int
    household_id: int
    user_id: Optional[int] = None
    is_active: bool
    created_at: datetime


# -----------------------
# ВСПОМОГАТЕЛЬНОЕ
# -----------------------


class ParseTextRequest(BaseModel):
    text: str
