from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TransactionBase(BaseModel):
    amount: float
    currency: str = "RUB"
    description: str | None = None
    category: str | None = None
    date: datetime | None = None  # если не передать, возьмём текущую дату


class TransactionCreate(TransactionBase):
    """Модель для создания транзакции (то, что приходит от клиента)."""
    pass


class TransactionRead(TransactionBase):
    """Модель для ответа API (то, что отдаем наружу)."""
    id: int
    created_at: datetime

    # Разрешаем Pydantic создавать модель из ORM-объекта SQLAlchemy
    model_config = ConfigDict(from_attributes=True)
    
class CategorySummary(BaseModel):
    category: str | None = None
    amount: float


class ReportSummary(BaseModel):
    total_amount: float
    currency: str
    by_category: list[CategorySummary]

class ParseTextRequest(BaseModel):
    text: str

from datetime import datetime
from pydantic import BaseModel


class ReminderBase(BaseModel):
    title: str
    amount: float | None = None
    currency: str = "RUB"
    interval_days: int | None = None
    next_run_at: datetime | None = None


class ReminderCreate(ReminderBase):
    """То, что приходит от бота при создании напоминания."""
    pass


class ReminderRead(ReminderBase):
    """То, что отдаём наружу (в т.ч. в бота)."""
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True
