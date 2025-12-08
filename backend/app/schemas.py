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

    # Новое: данные по бюджету (если есть)
    budget_limit: Optional[float] = None
    budget_spent: Optional[float] = None
    budget_percent: Optional[float] = None

    # Кандидатные категории от ИИ (v2)
    candidate_categories: Optional[List[str]] = None

class CategoryFeedbackCreate(BaseModel):
    telegram_id: int
    transaction_id: int
    original_category: Optional[str] = None
    chosen_category: str
    candidate_categories: Optional[List[str]] = None
    original_text: Optional[str] = None

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
    Баланс за период:
    - расходы
    - доходы
    - итог (доходы - расходы)
    """

    days: int
    expenses_total: float
    incomes_total: float
    net: float
    currency: str

class MemberExpenseSummary(BaseModel):
    """
    Сумма расходов по одному участнику семьи за период.
    """
    user_id: int
    name: Optional[str] = None
    telegram_id: Optional[int] = None
    amount: float


class MembersReport(BaseModel):
    """
    Отчёт по людям:
    кто сколько потратил за период.
    """
    days: int
    currency: str
    members: List[MemberExpenseSummary]

class ShopSummary(BaseModel):
    merchant: str
    amount: float

    class Config:
        from_attributes = True


class ShopsReport(BaseModel):
    days: int
    currency: str
    shops: List[ShopSummary]

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
# ПОЛЬЗОВАТЕЛЬ И СЕМЬЯ
# -----------------------


class MemberShort(BaseModel):
    """Краткая информация об участнике семьи."""
    id: int
    name: Optional[str] = None
    telegram_id: Optional[int] = None
    role: str


class MeResponse(BaseModel):
    """
    Ответ для /me:
    кто я, какая семья и кто в ней.
    """
    user_id: int
    telegram_id: Optional[int] = None
    name: Optional[str] = None

    household_id: int
    household_name: str
    currency: str
    privacy_mode: str
    role: str  # роль текущего пользователя в семье

    members: List[MemberShort]


class HouseholdInfo(BaseModel):
    """
    Информация о семье и участниках (для /household).
    """
    id: int
    name: str
    currency: str
    privacy_mode: str
    members: List[MemberShort]


class HouseholdInvite(BaseModel):
    """
    Ответ для /household/invite
    (пока просто числовой код = id семьи).
    """
    code: str


class HouseholdJoinRequest(BaseModel):
    """
    Тело запроса для /household/join.
    """
    code: str


class HouseholdRenameRequest(BaseModel):
    """
    Тело запроса для /household/rename.
    """
    name: str


class UserSetNameRequest(BaseModel):
    """
    Тело запроса для /user/set-name.
    """
    name: str


# -----------------------
# ПРОЧЕЕ
# -----------------------


class ParseTextRequest(BaseModel):
    text: str

# -----------------------
# КАТЕГОРИИ 2.0
# -----------------------


class CategoryBase(BaseModel):
    """
    Базовая схема категории.
    household_id на клиенте не передаём — бекенд подставит сам.
    """
    name: str
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


class CategoryCreate(CategoryBase):
    """
    Тело запроса для создания категории.
    Пока совпадает с базовой схемой.
    """
    pass


class CategoryRead(CategoryBase):
    """
    То, что возвращаем наружу.
    """
    id: int

    class Config:
        orm_mode = True
