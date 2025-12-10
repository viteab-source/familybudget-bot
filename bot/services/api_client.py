"""
Клиент для взаимодействия с Backend API.
Все HTTP-запросы к backend проходят через этот модуль.
"""
import httpx
from typing import Optional


class APIClient:
    """
    Централизованный клиент для вызовов Backend API.
    
    Использование:
        client = APIClient(base_url="http://127.0.0.1:8000")
        me = await client.get_me(telegram_id=123456789)
    """

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def set_last_transaction_category(self, telegram_id: int, category: str) -> dict:
        """Изменить категорию последней транзакции"""
        url = f"{self.base_url}/transactions/set-category-last"
        params = {"telegram_id": telegram_id, "category": category}
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, params=params, timeout=10.0)
            resp.raise_for_status()
            return resp.json()

    # ==========================================
    # ПОЛЬЗОВАТЕЛИ
    # ==========================================

    async def get_me(self, telegram_id: int):
        """Получить информацию о пользователе и его семье."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/me",
                params={"telegram_id": telegram_id},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def set_user_name(self, telegram_id: int, name: str):
        """Установить имя пользователя."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/user/set-name",
                params={"telegram_id": telegram_id},
                json={"name": name},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    # ==========================================
    # СЕМЬИ
    # ==========================================

    async def get_household(self, telegram_id: int):
        """Получить информацию о семье."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/household",
                params={"telegram_id": telegram_id},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_household_invite(self, telegram_id: int):
        """Получить код приглашения в семью."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/household/invite",
                params={"telegram_id": telegram_id},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def join_household(self, telegram_id: int, code: str):
        """Присоединиться к семье по коду."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/household/join",
                params={"telegram_id": telegram_id},
                json={"code": code},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def rename_household(self, telegram_id: int, name: str):
        """Переименовать семью."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/household/rename",
                params={"telegram_id": telegram_id},
                json={"name": name},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def leave_household(self, telegram_id: int):
        """Выйти из семьи."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/household/leave",
                params={"telegram_id": telegram_id},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    # ==========================================
    # КАТЕГОРИИ
    # ==========================================

    async def get_categories(self, telegram_id: int):
        """Получить список категорий."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/categories",
                params={"telegram_id": telegram_id},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def create_category(self, telegram_id: int, name: str):
        """Создать категорию."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/categories",
                params={"telegram_id": telegram_id},
                json={"name": name},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def rename_category(self, telegram_id: int, old_name: str, new_name: str):
        """Переименовать категорию."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/categories/rename",
                params={
                    "telegram_id": telegram_id,
                    "old_name": old_name,
                    "new_name": new_name,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def merge_categories(self, telegram_id: int, source_name: str, target_name: str):
        """Объединить категории."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/categories/merge",
                params={
                    "telegram_id": telegram_id,
                    "source_name": source_name,
                    "target_name": target_name,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_category(self, telegram_id: int, name: str):
        """Удалить категорию."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/categories/delete",
                params={"telegram_id": telegram_id, "name": name},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    # ==========================================
    # ТРАНЗАКЦИИ
    # ==========================================

    async def create_transaction(
        self,
        telegram_id: int,
        amount: float,
        description: Optional[str] = None,
        category: Optional[str] = None,
        kind: str = "expense",
    ):
        """Создать транзакцию (расход/доход)."""
        async with httpx.AsyncClient() as client:
            payload = {
                "amount": amount,
                "currency": "RUB",
                "description": description,
                "category": category,
                "kind": kind,
            }
            resp = await client.post(
                f"{self.base_url}/transactions",
                params={"telegram_id": telegram_id},
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def parse_and_create(self, telegram_id: int, text: str):
        """Разбор текста через ИИ + создание транзакции."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/transactions/parse-and-create",
                params={"telegram_id": telegram_id},
                json={"text": text},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_last_transaction(self, telegram_id: int):
        """Получить последнюю транзакцию."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/transactions/last",
                params={"telegram_id": telegram_id},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_last_transaction(self, telegram_id: int):
        """Удалить последнюю транзакцию."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/transactions/delete-last",
                params={"telegram_id": telegram_id},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def edit_last_transaction(
        self,
        telegram_id: int,
        new_amount: Optional[float] = None,
        new_description: Optional[str] = None,
    ):
        """Изменить последнюю транзакцию."""
        params = {"telegram_id": telegram_id}
        if new_amount is not None:
            params["new_amount"] = new_amount
        if new_description is not None and new_description.strip():
            params["new_description"] = new_description.strip()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/transactions/edit-last",
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def set_last_transaction_category(self, telegram_id: int, category: str):
        """Изменить категорию последней транзакции."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/transactions/set-category-last",
                params={
                    "telegram_id": telegram_id,
                    "category": category,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def export_csv(self, telegram_id: int, days: int = 30):
        """Экспорт транзакций в CSV."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/transactions/export/csv",
                params={"days": days, "telegram_id": telegram_id},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.content

    # ==========================================
    # БЮДЖЕТЫ
    # ==========================================

    async def set_budget(self, telegram_id: int, category_name: str, limit_amount: float):
        """Установить лимит бюджета."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/budget/set",
                params={
                    "telegram_id": telegram_id,
                    "category_name": category_name,
                    "limit_amount": limit_amount,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_budget_status(self, telegram_id: int):
        """Получить статус бюджетов."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/budget/status",
                params={"telegram_id": telegram_id},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    # ==========================================
    # ОТЧЁТЫ
    # ==========================================

    async def get_summary_report(self, telegram_id: int, days: int = 14, user_id: Optional[int] = None):
        """Отчёт по расходам."""
        params = {"days": days, "telegram_id": telegram_id}
        if user_id is not None:
            params["user_id"] = user_id

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/report/summary",
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_balance_report(self, telegram_id: int, days: int = 30, user_id: Optional[int] = None):
        """Отчёт баланса."""
        params = {"days": days, "telegram_id": telegram_id}
        if user_id is not None:
            params["user_id"] = user_id

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/report/balance",
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_members_report(self, telegram_id: int, days: int = 30):
        """Отчёт по людям."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/report/members",
                params={"days": days, "telegram_id": telegram_id},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_shops_report(self, telegram_id: int, days: int = 30):
        """Отчёт по магазинам."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/report/shops",
                params={"telegram_id": telegram_id, "days": days},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    # ==========================================
    # НАПОМИНАНИЯ
    # ==========================================

    async def create_reminder(
        self,
        telegram_id: int,
        title: str,
        amount: Optional[float],
        interval_days: Optional[int],
    ):
        """Создать напоминание."""
        async with httpx.AsyncClient() as client:
            payload = {
                "title": title,
                "amount": amount,
                "currency": "RUB",
                "interval_days": interval_days,
                "next_run_at": None,
            }
            resp = await client.post(
                f"{self.base_url}/reminders",
                params={"telegram_id": telegram_id},
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def list_reminders(self, telegram_id: int):
        """Список активных напоминаний."""
        async with httpx.AsyncClient() as client:
            params = {"only_active": True, "telegram_id": telegram_id}
            resp = await client.get(
                f"{self.base_url}/reminders",
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_due_reminders(self, telegram_id: int):
        """Напоминания на сегодня."""
        async with httpx.AsyncClient() as client:
            params = {"telegram_id": telegram_id}
            resp = await client.get(
                f"{self.base_url}/reminders/due-today",
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def mark_reminder_paid(self, reminder_id: int, telegram_id: Optional[int] = None):
        """Отметить напоминание как оплаченное."""
        async with httpx.AsyncClient() as client:
            params = {}
            if telegram_id is not None:
                params["telegram_id"] = telegram_id

            resp = await client.post(
                f"{self.base_url}/reminders/{reminder_id}/mark-paid",
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
