"""
bot/api_client.py — Все функции для работы с API бэкенда
"""

import httpx
from .config import API_BASE_URL


# ============= ПОЛЬЗОВАТЕЛИ И СЕМЬИ =============

async def api_get_me(telegram_id: int):
    """Получить информацию о пользователе и его семье (/me)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/me",
            params={"telegram_id": telegram_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_get_household(telegram_id: int):
    """Получить информацию о семье (/household)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/household",
            params={"telegram_id": telegram_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_get_household_invite(telegram_id: int):
    """Получить код приглашения в семью."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/household/invite",
            params={"telegram_id": telegram_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_join_household(telegram_id: int, code: str):
    """Присоединиться к семье по коду."""
    async with httpx.AsyncClient() as client:
        payload = {"code": code}
        resp = await client.post(
            f"{API_BASE_URL}/household/join",
            params={"telegram_id": telegram_id},
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_rename_household(telegram_id: int, name: str):
    """Переименовать семью."""
    async with httpx.AsyncClient() as client:
        payload = {"name": name}
        resp = await client.post(
            f"{API_BASE_URL}/household/rename",
            params={"telegram_id": telegram_id},
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_leave_household(telegram_id: int):
    """Выйти из семьи для данного пользователя."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/household/leave",
            params={"telegram_id": telegram_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_set_name(telegram_id: int, name: str):
    """Установить имя пользователя (display name)."""
    async with httpx.AsyncClient() as client:
        payload = {"name": name}
        resp = await client.post(
            f"{API_BASE_URL}/user/set-name",
            params={"telegram_id": telegram_id},
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


# ============= ТРАНЗАКЦИИ =============

async def api_create_transaction(
    telegram_id: int,
    amount: float,
    description: str | None = None,
    category: str | None = None,
    kind: str = "expense",
):
    """
    Прямое создание транзакции через /transactions.
    kind:
    - "expense" — расход
    - "income" — доход
    """
    async with httpx.AsyncClient() as client:
        payload = {
            "amount": amount,
            "currency": "RUB",
            "description": description,
            "category": category,
            "kind": kind,
        }

        resp = await client.post(
            f"{API_BASE_URL}/transactions",
            params={"telegram_id": telegram_id},
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_get_last_transaction(telegram_id: int):
    """Получить последнюю транзакцию пользователя."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/transactions/last",
            params={"telegram_id": telegram_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_delete_last_transaction(telegram_id: int):
    """Удалить последнюю транзакцию пользователя и вернуть её данные."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/transactions/delete-last",
            params={"telegram_id": telegram_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_edit_last_transaction(
    telegram_id: int,
    new_amount: float | None = None,
    new_description: str | None = None,
):
    """Изменить последнюю транзакцию пользователя."""
    params = {"telegram_id": telegram_id}
    if new_amount is not None:
        params["new_amount"] = new_amount
    if new_description is not None and new_description.strip():
        params["new_description"] = new_description.strip()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/transactions/edit-last",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_parse_and_create(telegram_id: int, text: str):
    """Разбор свободного текста через YandexGPT + создание транзакции (расход)."""
    async with httpx.AsyncClient() as client:
        payload = {"text": text}
        resp = await client.post(
            f"{API_BASE_URL}/transactions/parse-and-create",
            params={"telegram_id": telegram_id},
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_set_last_transaction_category(telegram_id: int, category: str):
    """Поменять категорию у последней транзакции пользователя."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/transactions/set-category-last",
            params={
                "telegram_id": telegram_id,
                "category": category,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_log_category_feedback(
    telegram_id: int,
    transaction_id: int,
    original_category: str | None,
    chosen_category: str,
    candidate_categories: list[str] | None,
    original_text: str | None,
):
    """
    Логируем, как пользователь поправил категорию после ИИ.
    Бэкенд ждёт тело типа CategoryFeedbackCreate.
    """
    payload = {
        "telegram_id": telegram_id,
        "transaction_id": transaction_id,
        "original_category": original_category,
        "chosen_category": chosen_category,
        "candidate_categories": candidate_categories or [],
        "original_text": original_text,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/transactions/category-feedback",
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


# ============= КАТЕГОРИИ =============

async def api_get_categories(telegram_id: int):
    """Получить список категорий текущей семьи."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/categories",
            params={"telegram_id": telegram_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_create_category(telegram_id: int, name: str):
    """Создать новую категорию для текущей семьи."""
    payload = {"name": name}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/categories",
            params={"telegram_id": telegram_id},
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_delete_category(telegram_id: int, name: str):
    """Удалить категорию по имени (если по ней нет операций)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/categories/delete",
            params={"telegram_id": telegram_id, "name": name},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_rename_category(telegram_id: int, old_name: str, new_name: str):
    """Переименовать категорию по имени."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/categories/rename",
            params={
                "telegram_id": telegram_id,
                "old_name": old_name,
                "new_name": new_name,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_merge_categories(telegram_id: int, source_name: str, target_name: str):
    """Слить категории: source -> target."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/categories/merge",
            params={
                "telegram_id": telegram_id,
                "source_name": source_name,
                "target_name": target_name,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


# ============= ОТЧЁТЫ =============

async def api_get_summary_report(
    telegram_id: int,
    days: int = 14,
    user_id: int | None = None,
    category: str | None = None,
):
    params = {"days": days, "telegram_id": telegram_id}
    if user_id is not None:
        params["user_id"] = user_id
    if category:
        params["category"] = category

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/report/summary",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_get_balance_report(
    telegram_id: int,
    days: int = 30,
    user_id: int | None = None,
    category: str | None = None,
):
    params = {"days": days, "telegram_id": telegram_id}
    if user_id is not None:
        params["user_id"] = user_id
    if category:
        params["category"] = category

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/report/balance",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_get_members_report(
    telegram_id: int,
    days: int = 30,
    category: str | None = None,
):
    """Отчёт по людям (расходы по каждому участнику семьи)."""
    params = {"days": days, "telegram_id": telegram_id}
    if category:
        params["category"] = category

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/report/members",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_report_shops(telegram_id: int, days: int = 30):
    """Отчёт по магазинам за N дней."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/report/shops",
            params={"telegram_id": telegram_id, "days": days},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_export_csv(telegram_id: int, days: int = 30):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/transactions/export/csv",
            params={"days": days, "telegram_id": telegram_id},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.content


# ============= НАПОМИНАНИЯ =============

async def api_create_reminder(
    telegram_id: int,
    title: str,
    amount: float | None,
    interval_days: int | None,
):
    async with httpx.AsyncClient() as client:
        payload = {
            "title": title,
            "amount": amount,
            "currency": "RUB",
            "interval_days": interval_days,
            "next_run_at": None,
        }

        params = {"telegram_id": telegram_id}
        resp = await client.post(
            f"{API_BASE_URL}/reminders",
            params=params,
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_list_reminders(telegram_id: int):
    async with httpx.AsyncClient() as client:
        params = {"only_active": True, "telegram_id": telegram_id}
        resp = await client.get(
            f"{API_BASE_URL}/reminders",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_get_due_reminders(telegram_id: int):
    async with httpx.AsyncClient() as client:
        params = {"telegram_id": telegram_id}
        resp = await client.get(
            f"{API_BASE_URL}/reminders/due-today",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_mark_reminder_paid(reminder_id: int, telegram_id: int | None = None):
    async with httpx.AsyncClient() as client:
        params = {}
        if telegram_id is not None:
            params["telegram_id"] = telegram_id
        resp = await client.post(
            f"{API_BASE_URL}/reminders/{reminder_id}/mark-paid",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
