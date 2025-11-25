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
