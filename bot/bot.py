import asyncio
import os
from datetime import datetime
import logging

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, BufferedInputFile
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()
logger = logging.getLogger("familybudget_bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")


# Пользователи, которые сейчас подтверждают выход из семьи
pending_family_leave_confirmations: set[int] = set()


async def _clear_family_leave_confirmation(user_id: int, delay_seconds: int = 60):
    """
    Через delay_seconds секунд убираем запрос на подтверждение,
    если пользователь ничего не сделал.
    """
    await asyncio.sleep(delay_seconds)
    pending_family_leave_confirmations.discard(user_id)

# -----------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ API
# -----------------------


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

async def api_get_summary_report(telegram_id: int, days: int = 14):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/report/summary",
            params={"days": days, "telegram_id": telegram_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_get_balance_report(telegram_id: int, days: int = 30):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/report/balance",
            params={"days": days, "telegram_id": telegram_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()

async def api_get_members_report(telegram_id: int, days: int = 30):
    """Отчёт по людям (расходы по каждому участнику семьи)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/report/members",
            params={"days": days, "telegram_id": telegram_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()

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


async def api_export_csv(telegram_id: int, days: int = 30):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/transactions/export/csv",
            params={"days": days, "telegram_id": telegram_id},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.content


# -----------------------
# STT (пока не работает из-за прав, но код оставим)
# -----------------------


async def stt_recognize_ogg(data: bytes, lang: str = "ru-RU") -> str:
    if not YANDEX_API_KEY:
        raise RuntimeError("YANDEX_API_KEY не найден. Проверь .env")

    print(
        f"[STT] YANDEX_API_KEY starts with: {YANDEX_API_KEY[:6]}..., "
        f"len={len(YANDEX_API_KEY)}"
    )

    url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"

    params = {
        "lang": lang,
        "topic": "general",
        "format": "oggopus",
    }

    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            params=params,
            content=data,
            headers=headers,
        )

    print(f"[STT] HTTP status: {resp.status_code}")
    print(f"[STT] Raw body: {resp.text[:300]}")

    if resp.status_code == 401:
        raise RuntimeError(
            "STT 401 Unauthorized. "
            "Проверь YANDEX_API_KEY в .env и роли/область действия API-ключа."
        )

    resp.raise_for_status()
    payload = resp.json()

    if payload.get("error_code") is not None:
        code = payload.get("error_code")
        msg = payload.get("error_message", "")
        raise RuntimeError(f"STT error {code}: {msg}")

    return payload.get("result", "")


# -----------------------
# ОСНОВНАЯ ЛОГИКА БОТА
# -----------------------

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не найден. Проверь файл .env")

    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("==== Запуск FamilyBudget Bot ====")
    logger.info(f"API_BASE_URL = {API_BASE_URL}")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # /start
    @dp.message(CommandStart())
    async def cmd_start(message: Message):
        """
        /start

        1) Обычный старт — показывает помощь.
        2) Если пришёл deep-link вида `/start join_XXXX`,
           бот сразу пытается присоединить пользователя к семье по коду.
        """
        text = message.text or ""
        parts = text.split(maxsplit=1)

        # Проверяем, есть ли payload после /start
        if len(parts) > 1:
            payload = parts[1].strip()
            # Ожидаем формат join_ABCD123
            if payload.startswith("join_") and len(payload) > len("join_"):
                code = payload[len("join_") :].strip()
                telegram_id = message.from_user.id

                try:
                    info = await api_join_household(telegram_id, code)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        await message.answer(
                            "Приглашение с таким кодом не найдено "
                            "или уже устарело 😔"
                        )
                        return
                    if e.response.status_code == 400:
                        await message.answer("Неверный код приглашения 😔")
                        return

                    print(f"HTTP ошибка /start join_: {e}")
                    await message.answer(
                        "Не получилось присоединиться к семье 😔\n"
                        "Попробуй позже."
                    )
                    return
                except Exception as e:
                    print(f"Ошибка /start join_: {e}")
                    await message.answer(
                        "Не получилось присоединиться к семье 😔\n"
                        "Попробуй позже."
                    )
                    return

                # Успешно присоединили к семье — показываем состав семьи
                members = info.get("members") or []
                member_lines = []
                for m in members:
                    m_name = m.get("name") or "без имени"
                    role = m.get("role") or "member"
                    member_lines.append(f"- {m_name} ({role})")

                msg_lines = [
                    "Готово! 🎉",
                    f"Ты теперь в семье: {info.get('name')}",
                ]
                if member_lines:
                    msg_lines.append("")
                    msg_lines.append("Сейчас в семье:")
                    msg_lines.extend(member_lines)

                msg_lines.append(
                    "\nЧтобы в списке семьи было видно твоё имя, "
                    "отправь команду:\n/setname ТвоёИмя"
                )

                await message.answer("\n".join(msg_lines))
                return  # чтобы не выводить приветствие второй раз

        # Обычное приветствие, если это просто /start без кода
        await message.answer(
            "Привет! 👋\n"
            "Я FamilyBudget Bot.\n\n"
            "Для начала давай настроимся:\n"
            "1️⃣ Как тебя называть — команда:\n"
            "   /setname ТвоёИмя\n"
            "   пример: /setname Витя\n\n"
            "2️⃣ Как назвать семью — команда:\n"
            "   /family_rename Наша семья\n\n"
            "Дальше что я умею:\n"
            "• просто напиши: Перекрёсток продукты 2435₽ вчера — я сам пойму через ИИ\n"
            "• /aiadd — добавить расход через ИИ\n"
            "• /add — добавить расход вручную\n"
            "• /income — добавить доход вручную\n"
            "• /report — отчёт по расходам за последние 14 дней\n"
            "• /balance — баланс (доходы/расходы) за период\n"
            "• /export — экспорт расходов/доходов в CSV\n"
            "• /remind_add — создать напоминание\n"
            "• /reminders — список напоминаний\n"
            "• /remind_today — что нужно оплатить сегодня\n"
            "• /remind_pay — отметить напоминание как оплачено\n"
            "• /me — твой профиль и семья\n"
            "• /family — информация о семье\n"
            "• /family_invite — пригласить в семью\n"
            "• /family_join КОД — присоединиться к семье\n"
            "• /family_rename НОВОЕ_НАЗВАНИЕ — переименовать семью\n"
            "• /help — подсказка"
        )

    # /help
    @dp.message(Command("help"))
    async def cmd_help(message: Message):
        await message.answer(
            "Доступные команды:\n"
            "/start — начать работу\n"
            "/help — помощь\n\n"
            "/setname ИМЯ — как тебя называть\n"
            "/me — показать твой профиль и семью\n"
            "/family — информация о семье\n"
            "/family_invite — пригласить в семью (даёт код)\n"
            "/family_join КОД — присоединиться к семье по коду\n"
            "/family_rename НАЗВАНИЕ — переименовать семью\n\n"
            "/family_leave — выйти из семьи\n"            
            "/add СУММА описание — добавить расход вручную\n"
            "  пример: /add 2435 Пятёрочка продукты\n\n"
            "/income СУММА описание — добавить доход вручную\n"
            "  пример: /income 50000 Зарплата\n\n"
            "/aiadd ТЕКСТ — добавить расход через ИИ (YandexGPT)\n"
            "  пример: /aiadd Перекрёсток продукты 2435₽ вчера\n\n"
            "/report [дней] — отчёт по расходам (по умолчанию 14)\n"
            "/report_members [дней] — кто сколько потратил (по умолчанию 30)\n"       
            "/balance [дней] — баланс доходы/расходы (по умолчанию 30)\n"
            "/export [дней] — экспорт в CSV (по умолчанию 30)\n\n"
            "/categories — список категорий\n"
            "/setcat НАЗВАНИЕ — задать категорию для последнего расхода\n\n"
            "Напоминания:\n"
            "/remind_add НАЗВАНИЕ СУММА ДНЕЙ\n"
            "  пример: /remind_add Коммуналка 8000 30\n"
            "/reminders — список активных напоминаний\n"
            "/remind_today — список платежей на сегодня\n"
            "/remind_pay ID — отметить напоминание как оплачено"
        )

    @dp.message(Command("setname"))
    async def cmd_setname(message: Message):
        """
        Задать своё имя, которое будет видно в семье и отчётах.
        Формат: /setname Имя
        """
        text = message.text or ""
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            await message.answer(
                "Формат команды:\n"
                "/setname ИМЯ\n\n"
                "Пример:\n"
                "/setname Витя"
            )
            return

        name = parts[1].strip()
        telegram_id = message.from_user.id

        try:
            await api_set_name(telegram_id, name)
        except Exception as e:
            print(f"Ошибка /setname: {e}")
            await message.answer(
                "Не получилось сохранить имя 😔\n"
                "Попробуй позже."
            )
            return

        await message.answer(
            f"Готово ✅\n"
            f"Буду называть тебя: {name}"
        )

    # /me — кто я и какая семья
    @dp.message(Command("me"))
    async def cmd_me(message: Message):
        telegram_id = message.from_user.id

        try:
            info = await api_get_me(telegram_id)
        except Exception as e:
            print(f"Ошибка /me: {e}")
            await message.answer(
                "Не получилось получить информацию о профиле 😔\n"
                "Попробуй позже."
            )
            return

        lines = [
            "Твой профиль:",
            f"Имя: {info.get('name') or 'без имени'}",
            f"Telegram ID: {info.get('telegram_id')}",
            "",
            "Семья:",
            f"Название: {info.get('household_name')}",
            f"Валюта: {info.get('currency')}",
            f"Приватность: {info.get('privacy_mode')}",
            f"Твоя роль: {info.get('role')}",
        ]

        members = info.get("members") or []
        if members:
            lines.append("")
            lines.append("Участники семьи:")
            for m in members:
                m_name = m.get("name") or "без имени"
                role = m.get("role") or "member"
                lines.append(f"- {m_name} ({role})")

        await message.answer("\n".join(lines))

    # /family — инфа только про семью
    @dp.message(Command("family"))
    async def cmd_family(message: Message):
        telegram_id = message.from_user.id

        try:
            info = await api_get_household(telegram_id)
        except Exception as e:
            print(f"Ошибка /family: {e}")
            await message.answer(
                "Не получилось получить информацию о семье 😔\n"
                "Попробуй позже."
            )
            return

        lines = [
            "Твоя семья:",
            f"Название: {info.get('name')}",
            f"Валюта: {info.get('currency')}",
            f"Приватность: {info.get('privacy_mode')}",
        ]

        members = info.get("members") or []
        if members:
            lines.append("")
            lines.append("Участники:")
            for m in members:
                m_name = m.get("name") or "без имени"
                role = m.get("role") or "member"
                lines.append(f"- {m_name} ({role})")

        await message.answer("\n".join(lines))

    # /family_invite — получить код семьи
    @dp.message(Command("family_invite"))
    async def cmd_family_invite(message: Message):
        """
        /family_invite

        Даёт:
        - короткий код приглашения
        - (если возможно) ссылку вида https://t.me/Бот?start=join_КОД
        """
        telegram_id = message.from_user.id

        try:
            data = await api_get_household_invite(telegram_id)
        except Exception as e:
            print(f"Ошибка /family_invite: {e}")
            await message.answer(
                "Не получилось создать приглашение в семью 😔\n"
                "Попробуй позже."
            )
            return

        code = data.get("code")

        # Пытаемся собрать ссылку-приглашение
        invite_link = None
        try:
            me = await message.bot.get_me()
            if me.username:
                invite_link = f"https://t.me/{me.username}?start=join_{code}"
        except Exception as e:
            print(f"Ошибка при получении username бота: {e}")

        lines = [
            "Приглашение в семью:",
            "",
            f"Код: {code}",
            "",
            "Пусть второй человек отправит боту команду:",
            f"/family_join {code}",
        ]

        if invite_link:
            lines.append("")
            lines.append("Или просто перейдёт по ссылке:")
            lines.append(invite_link)

        await message.answer("\n".join(lines))


    # /family_join КОД — присоединиться к семье
    @dp.message(Command("family_join"))
    async def cmd_family_join(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            await message.answer(
                "Формат команды:\n"
                "/family_join КОД\n\n"
                "Код можно получить у того, кто уже в семье через /family_invite"
            )
            return

        code = parts[1].strip()
        telegram_id = message.from_user.id

        try:
            info = await api_join_household(telegram_id, code)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await message.answer("Семья с таким кодом не найдена 😔")
                return
            if e.response.status_code == 400:
                await message.answer("Неверный формат кода приглашения 😔")
                return
            print(f"HTTP ошибка /family_join: {e}")
            await message.answer(
                "Не получилось присоединиться к семье 😔\n"
                "Попробуй позже."
            )
            return
        except Exception as e:
            print(f"Ошибка /family_join: {e}")
            await message.answer(
                "Не получилось присоединиться к семье 😔\n"
                "Попробуй позже."
            )
            return

        members = info.get("members") or []
        member_lines = []
        for m in members:
            m_name = m.get("name") or "без имени"
            role = m.get("role") or "member"
            member_lines.append(f"- {m_name} ({role})")

        msg_lines = [
            "Готово! 🎉",
            f"Ты теперь в семье: {info.get('name')}",
        ]
        if member_lines:
            msg_lines.append("")
            msg_lines.append("Сейчас в семье:")
            msg_lines.extend(member_lines)

        msg_lines.append(
            "\nЧтобы в списке семьи было видно твоё имя, "
            "отправь команду:\n/setname ТвоёИмя"
        )

        await message.answer("\n".join(msg_lines))


    # /family_rename — переименовать семью
    @dp.message(Command("family_rename"))
    async def cmd_family_rename(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            await message.answer(
                "Формат команды:\n"
                "/family_rename НОВОЕ НАЗВАНИЕ\n\n"
                "Пример:\n"
                "/family_rename Наша семья"
            )
            return

        new_name = parts[1].strip()
        telegram_id = message.from_user.id

        try:
            info = await api_rename_household(telegram_id, new_name)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                await message.answer(
                    "Переименовать семью может только владелец (owner) или админ 😔"
                )
                return
            if e.response.status_code == 400:
                await message.answer(
                    "Сначала нужно создать семью (просто добавь расход или доход)."
                )
                return
            print(f"HTTP ошибка /family_rename: {e}")
            await message.answer(
                "Не получилось переименовать семью 😔\n"
                "Попробуй позже."
            )
            return
        except Exception as e:
            print(f"Ошибка /family_rename: {e}")
            await message.answer(
                "Не получилось переименовать семью 😔\n"
                "Попробуй позже."
            )
            return

        await message.answer(
            f"Готово ✅\n"
            f"Новое название семьи: {info.get('name')}"
        )

    # /family_leave — выйти из семьи (с подтверждением)
    @dp.message(Command("family_leave"))
    async def cmd_family_leave(message: Message):
        telegram_id = message.from_user.id

        # Первый вызов — только предупреждение и запрос подтверждения
        if telegram_id not in pending_family_leave_confirmations:
            pending_family_leave_confirmations.add(telegram_id)
            # Через минуту очистим запрос, если пользователь передумал
            asyncio.create_task(
                _clear_family_leave_confirmation(telegram_id, delay_seconds=60)
            )

            await message.answer(
                "⚠ Внимание!\n\n"
                "Если ты сейчас выйдешь из семьи, то:\n"
                "• семья будет удалена (если ты в ней один и ты владелец);\n"
                "• будут удалены все расходы, доходы, напоминания и инвайты этой семьи.\n\n"
                "Если ты ТОЧНО хочешь выйти и всё удалить — "
                "ещё раз отправь команду:\n/family_leave\n"
                "Команда действительна в течение 1 минуты."
            )
            return

        # Второй вызов — уже настоящее выполнение
        # (и мы сразу убираем флаг подтверждения)
        pending_family_leave_confirmations.discard(telegram_id)

        try:
            data = await api_leave_household(telegram_id)
        except httpx.HTTPStatusError as e:
            # Обрабатываем ожидаемые ошибки
            try:
                detail = e.response.json().get("detail", "")
            except Exception:
                detail = ""

            if e.response.status_code == 400:
                if "no household" in detail:
                    await message.answer("Ты и так ни в какой семье не состоишь 🙂")
                    return
                if "Owner не может" in detail:
                    await message.answer(
                        "Ты владелец семьи и в ней есть другие участники.\n"
                        "Сначала передай права или удали участников."
                    )
                    return
                await message.answer(detail or "Некорректный запрос.")
                return

            if e.response.status_code == 404:
                await message.answer(
                    "Не получилось найти пользователя или семью 😔"
                )
                return

            print(f"HTTP ошибка /family_leave: {e}")
            await message.answer(
                "Не получилось выйти из семьи 😔\n"
                "Попробуй позже."
            )
            return
        except Exception as e:
            print(f"Ошибка /family_leave: {e}")
            await message.answer(
                "Не получилось выйти из семьи 😔\n"
                "Попробуй позже."
            )
            return

        msg = data.get("message") or "Ты вышел из семьи."
        await message.answer(msg)

    

    # /add — расход
    @dp.message(Command("add"))
    async def cmd_add(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=2)

        if len(parts) < 2:
            await message.answer(
                "Формат команды:\n"
                "/add СУММА описание\n\n"
                "Пример:\n"
                "/add 2435 Пятёрочка продукты"
            )
            return

        amount_str = parts[1].replace(",", ".")

        try:
            amount = float(amount_str)
        except ValueError:
            await message.answer(
                "Не понял сумму 🤔\n"
                "Попробуй так:\n"
                "/add 2435 Пятёрочка продукты"
            )
            return

        description = parts[2] if len(parts) > 2 else None

        telegram_id = message.from_user.id

        try:
            tx = await api_create_transaction(
                telegram_id=telegram_id,
                amount=amount,
                description=description,
                kind="expense",
            )
        except Exception as e:
            print(f"Ошибка при создании транзакции: {e}")
            await message.answer(
                "Не получилось сохранить расход 😔\n"
                "Попробуй позже."
            )
            return

        await send_tx_confirmation(message, tx, description or "", via_ai=False)

    # /income — доход
    @dp.message(Command("income"))
    async def cmd_income(message: Message):
        """
        Формат: /income СУММА описание
        Пример: /income 50000 Зарплата
        """
        text = message.text or ""
        parts = text.split(maxsplit=2)

        if len(parts) < 2:
            await message.answer(
                "Формат команды:\n"
                "/income СУММА описание\n\n"
                "Пример:\n"
                "/income 50000 Зарплата"
            )
            return

        amount_str = parts[1].replace(",", ".")

        try:
            amount = float(amount_str)
        except ValueError:
            await message.answer(
                "Не понял сумму 🤔\n"
                "Пример: /income 50000 Зарплата"
            )
            return

        description = parts[2] if len(parts) > 2 else "Доход"

        telegram_id = message.from_user.id

        try:
            tx = await api_create_transaction(
                telegram_id=telegram_id,
                amount=amount,
                description=description,
                kind="income",
            )
        except Exception as e:
            print(f"Ошибка при создании дохода: {e}")
            await message.answer(
                "Не получилось сохранить доход 😔\n"
                "Попробуй позже."
            )
            return

        await send_tx_confirmation(
            message,
            tx,
            description,
            via_ai=False,
            prefix="Записал доход:",
        )

    # /remind_add — создать напоминание
    @dp.message(Command("remind_add"))
    async def cmd_remind_add(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=3)

        if len(parts) < 4:
            await message.answer(
                "Формат команды:\n"
                "/remind_add НАЗВАНИЕ СУММА ДНЕЙ\n\n"
                "Пример:\n"
                "/remind_add Коммуналка 8000 30"
            )
            return

        title = parts[1]
        amount_str = parts[2]
        days_str = parts[3]

        try:
            amount = float(amount_str.replace(",", "."))
        except ValueError:
            await message.answer(
                "Не понял сумму 🤔\n"
                "Пример: /remind_add Коммуналка 8000 30"
            )
            return

        try:
            interval_days = int(days_str)
        except ValueError:
            await message.answer(
                "Не понял, через сколько дней повторять.\n"
                "Пример: /remind_add Коммуналка 8000 30"
            )
            return

        telegram_id = message.from_user.id

        try:
            rem = await api_create_reminder(
                telegram_id=telegram_id,
                title=title,
                amount=amount,
                interval_days=interval_days,
            )
        except Exception as e:
            print(f"Ошибка при создании напоминания: {e}")
            await message.answer(
                "Не получилось создать напоминание 😔\n"
                "Попробуй позже."
            )
            return

        next_date_raw = rem.get("next_run_at")
        pretty_date = None
        if next_date_raw:
            try:
                pretty_date = datetime.fromisoformat(next_date_raw).strftime(
                    "%d.%m.%Y"
                )
            except ValueError:
                pretty_date = next_date_raw

        msg = [
            "Создал напоминание ✅",
            f"ID: {rem.get('id')}",
            f"Название: {rem.get('title')}",
            f"Сумма: {rem.get('amount')} {rem.get('currency')}",
            f"Каждые {rem.get('interval_days')} дней",
        ]
        if pretty_date:
            msg.append(f"Следующий раз: {pretty_date}")

        await message.answer("\n".join(msg))

    # /reminders — список активных напоминаний
    @dp.message(Command("reminders"))
    async def cmd_reminders(message: Message):
        telegram_id = message.from_user.id

        try:
            reminders = await api_list_reminders(telegram_id=telegram_id)
        except Exception as e:
            print(f"Ошибка при получении списка напоминаний: {e}")
            await message.answer(
                "Не получилось получить напоминания 😔\n"
                "Попробуй позже."
            )
            return

        if not reminders:
            await message.answer(
                "Пока нет активных напоминаний 🙂\n"
                "Создай первое через /remind_add"
            )
            return

        lines = ["Активные напоминания:"]
        for rem in reminders:
            next_date_raw = rem.get("next_run_at")
            pretty_date = None
            if next_date_raw:
                try:
                    pretty_date = datetime.fromisoformat(next_date_raw).strftime(
                        "%d.%m.%Y"
                    )
                except ValueError:
                    pretty_date = next_date_raw

            line = (
                f"[{rem.get('id')}] {rem.get('title')} — "
                f"{rem.get('amount')} {rem.get('currency')}"
            )
            if rem.get("interval_days"):
                line += f", каждые {rem.get('interval_days')} дней"
            if pretty_date:
                line += f", следующий раз: {pretty_date}"

            lines.append(line)

        await message.answer("\n".join(lines))

    # /remind_today — что нужно оплатить сегодня
    @dp.message(Command("remind_today"))
    async def cmd_remind_today(message: Message):
        telegram_id = message.from_user.id

        try:
            reminders = await api_get_due_reminders(telegram_id=telegram_id)
        except Exception as e:
            print(f"Ошибка при получении сегодняшних напоминаний: {e}")
            await message.answer(
                "Не получилось получить сегодняшние напоминания 😔\n"
                "Попробуй позже."
            )
            return

        if not reminders:
            await message.answer("На сегодня нет обязательных платежей ✅")
            return

        lines = ["Сегодня нужно оплатить:"]
        for rem in reminders:
            line = (
                f"[{rem.get('id')}] {rem.get('title')} — "
                f"{rem.get('amount')} {rem.get('currency')}"
            )
            if rem.get("interval_days"):
                line += f", каждые {rem.get('interval_days')} дней"
            lines.append(line)

        lines.append(
            "\nЧтобы отметить оплату, используй /remind_pay ID "
            "(например, /remind_pay 1)."
        )

        await message.answer("\n".join(lines))

    # /remind_pay — отметить напоминание как оплачено
    @dp.message(Command("remind_pay"))
    async def cmd_remind_pay(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            await message.answer(
                "Формат команды:\n"
                "/remind_pay ID\n\n"
                "Пример:\n"
                "/remind_pay 1"
            )
            return

        try:
            rem_id = int(parts[1])
        except ValueError:
            await message.answer("ID должен быть числом. Пример: /remind_pay 1")
            return

        telegram_id = message.from_user.id

        try:
            rem = await api_mark_reminder_paid(rem_id, telegram_id=telegram_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await message.answer("Напоминание с таким ID не найдено 😔")
                return
            print(f"HTTP ошибка при отметке напоминания: {e}")
            await message.answer("Не получилось обновить напоминание 😔 Попробуй позже.")
            return
        except Exception as e:
            print(f"Ошибка при отметке напоминания: {e}")
            await message.answer("Не получилось обновить напоминание 😔 Попробуй позже.")
            return

        next_date_raw = rem.get("next_run_at")
        pretty_date = None
        if next_date_raw and rem.get("is_active"):
            try:
                pretty_date = datetime.fromisoformat(next_date_raw).strftime("%d.%m.%Y")
            except ValueError:
                pretty_date = next_date_raw

        msg = [
            "Отметил напоминание как оплачено ✅",
            f"Название: {rem.get('title')}",
            f"Сумма: {rem.get('amount')} {rem.get('currency')}",
        ]
        if rem.get("interval_days") and pretty_date:
            msg.append(f"Следующий платёж: {pretty_date}")
        if not rem.get("interval_days"):
            msg.append("Напоминание одноразовое и теперь отключено.")

        await message.answer("\n".join(msg))

    # /aiadd — умный ввод расхода через ИИ
    @dp.message(Command("aiadd"))
    async def cmd_aiadd(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            await message.answer(
                "Напиши расход после команды.\n\n"
                "Пример:\n"
                "/aiadd Перекрёсток продукты 2435₽ вчера"
            )
            return

        raw_text = parts[1]
        telegram_id = message.from_user.id

        try:
            tx = await api_parse_and_create(telegram_id=telegram_id, text=raw_text)
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                data = e.response.json()
                detail = data.get("detail") or ""
            except Exception:
                pass

            print(f"HTTP ошибка при разборе текста через ИИ: {detail or e}")

            if isinstance(detail, str) and "Некорректная сумма" in detail:
                await message.answer(
                    "Похоже, я не увидел сумму в этом сообщении 🤔\n"
                    "Добавь число и валюту. Примеры:\n"
                    "• КБ Макс игрушки 750\n"
                    "• Перекрёсток продукты 2435₽ вчера"
                )
            else:
                await message.answer(
                    "Не получилось разобрать расход через ИИ 😔\n"
                    "Попробуй переформулировать сообщение или используй /add."
                )
            return
        except Exception as e:
            print(f"Ошибка при разборе свободного текста через ИИ: {e}")
            await message.answer(
                "Не получилось разобрать расход через ИИ 😔\n"
                "Попробуй ещё раз или используй /add."
            )
            return

        await send_tx_confirmation(message, tx, raw_text, via_ai=True)

    # /report — отчёт по расходам
    @dp.message(Command("report"))
    async def cmd_report(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=1)

        days = 14
        if len(parts) == 2:
            try:
                days = int(parts[1])
            except ValueError:
                await message.answer("Не понял количество дней. Пример: /report 14")
                return

        telegram_id = message.from_user.id

        try:
            report = await api_get_summary_report(telegram_id=telegram_id, days=days)
        except Exception as e:
            print(f"Ошибка при получении отчёта: {e}")
            await message.answer(
                "Не получилось получить отчёт 😔\n"
                "Попробуй позже."
            )
            return

        total = report.get("total_amount", 0)
        currency = report.get("currency", "RUB")
        by_cat = report.get("by_category", [])

        if not by_cat and total == 0:
            await message.answer(
                "Пока нет расходов за этот период 🙂\n"
                "Добавь расход через /add или /aiadd"
            )
            return

        lines = [
            f"Отчёт по расходам за последние {days} дней:",
            f"Всего расходов: {total:.2f} {currency}",
            "",
            "По категориям:",
        ]

        for item in by_cat:
            cat = item.get("category") or "Без категории"
            amt = item.get("amount", 0)
            lines.append(f"- {cat}: {amt:.2f} {currency}")

        await message.answer("\n".join(lines))

    # /report_members — расходы по людям
    @dp.message(Command("report_members"))
    async def cmd_report_members(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=1)

        days = 30
        if len(parts) == 2:
            try:
                days = int(parts[1])
            except ValueError:
                await message.answer(
                    "Не понял количество дней. Пример: /report_members 30"
                )
                return

        telegram_id = message.from_user.id

        try:
            report = await api_get_members_report(
                telegram_id=telegram_id,
                days=days,
            )
        except Exception as e:
            print(f"Ошибка при получении отчёта по людям: {e}")
            await message.answer(
                "Не получилось получить отчёт по людям 😔\n"
                "Попробуй позже."
            )
            return

        members = report.get("members") or []
        currency = report.get("currency", "RUB")

        if not members:
            await message.answer(
                f"За последние {days} дней расходов по людям нет 🙂"
            )
            return

        lines = [
            f"Расходы по людям за последние {days} дней:",
            "",
        ]

        for m in members:
            name = m.get("name") or "Без имени"
            amount = m.get("amount", 0.0)
            lines.append(f"- {name}: {amount:.2f} {currency}")

        await message.answer("\n".join(lines))

    # /categories — список категорий семьи
    @dp.message(Command("categories"))
    async def cmd_categories(message: Message):
        telegram_id = message.from_user.id

        try:
            cats = await api_get_categories(telegram_id)
        except Exception as e:
            print(f"Ошибка при получении категорий: {e}")
            await message.answer(
                "Не получилось получить категории 😔\n"
                "Попробуй позже."
            )
            return

        if not cats:
            await message.answer(
                "Пока нет сохранённых категорий.\n"
                "Они появятся, когда ты будешь задавать их через /setcat."
            )
            return

        lines = ["Категории твоей семьи:", ""]
        for c in cats:
            name = c.get("name") or "без названия"
            lines.append(f"- {name}")

        await message.answer("\n".join(lines))

    # /setcat НАЗВАНИЕ — задать категорию для последнего расхода
    @dp.message(Command("setcat"))
    async def cmd_setcat(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            await message.answer(
                "Напиши название категории.\n"
                "Пример: /setcat Продукты"
            )
            return

        category_name = parts[1].strip()
        if not category_name:
            await message.answer(
                "Название категории не может быть пустым.\n"
                "Пример: /setcat Продукты"
            )
            return

        telegram_id = message.from_user.id

        try:
            tx = await api_set_last_transaction_category(
                telegram_id=telegram_id,
                category=category_name,
            )
        except httpx.HTTPStatusError as e:
            try:
                detail = e.response.json().get("detail", "")
            except Exception:
                detail = ""

            if e.response.status_code == 404:
                await message.answer(
                    "У тебя ещё нет транзакций — нечему задавать категорию 🙂"
                )
                return
            if e.response.status_code == 400:
                await message.answer(detail or "Некорректное название категории.")
                return

            print(f"HTTP ошибка /setcat: {e}")
            await message.answer(
                "Не получилось сохранить категорию 😔\n"
                "Попробуй позже."
            )
            return
        except Exception as e:
            print(f"Ошибка /setcat: {e}")
            await message.answer(
                "Не получилось сохранить категорию 😔\n"
                "Попробуй позже."
            )
            return

        cat = tx.get("category") or category_name
        amount = tx.get("amount", 0.0)
        currency = tx.get("currency", "RUB")

        await message.answer(
            f"Готово ✅\n"
            f"Последний расход теперь в категории «{cat}» "
            f"({amount:.2f} {currency})."
        )

    # /balance — баланс доходы/расходы
    @dp.message(Command("balance"))
    async def cmd_balance(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=1)

        days = 30
        if len(parts) == 2:
            try:
                days = int(parts[1])
            except ValueError:
                await message.answer("Не понял количество дней. Пример: /balance 30")
                return

        telegram_id = message.from_user.id

        try:
            report = await api_get_balance_report(telegram_id=telegram_id, days=days)
        except Exception as e:
            print(f"Ошибка при получении баланса: {e}")
            await message.answer(
                "Не получилось получить баланс 😔\n"
                "Попробуй позже."
            )
            return

        expenses = report.get("expenses_total", 0.0)
        incomes = report.get("incomes_total", 0.0)
        net = report.get("net", 0.0)
        currency = report.get("currency", "RUB")

        sign = "➕" if net >= 0 else "➖"

        lines = [
            f"Баланс за последние {days} дней:",
            f"Доходы: {incomes:.2f} {currency}",
            f"Расходы: {expenses:.2f} {currency}",
            "",
            f"Итог: {sign} {net:.2f} {currency}",
        ]

        await message.answer("\n".join(lines))

    # /export — экспорт CSV
    @dp.message(Command("export"))
    async def cmd_export(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=1)

        days = 30
        if len(parts) == 2:
            try:
                days = int(parts[1])
            except ValueError:
                await message.answer("Не понял количество дней. Пример: /export 30")
                return

        telegram_id = message.from_user.id

        try:
            csv_bytes = await api_export_csv(telegram_id=telegram_id, days=days)
        except Exception as e:
            print(f"Ошибка при экспорте CSV: {e}")
            await message.answer("Не получилось сделать экспорт 😔 Попробуй позже.")
            return

        filename = f"transactions_{days}d.csv"
        file = BufferedInputFile(csv_bytes, filename=filename)

        await message.answer_document(
            document=file,
            caption=f"Экспорт транзакций за последние {days} дней.",
        )

    # Голосовые — как раньше (пока STT не работает)
    @dp.message(F.voice)
    async def handle_voice(message: Message):
        await message.answer("Секунду, распознаю голос и запишу расход... 🎧")

        try:
            file = await bot.get_file(message.voice.file_id)
            file_path = file.file_path
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                voice_resp = await client.get(file_url)
                voice_resp.raise_for_status()
                ogg_data = voice_resp.content
        except Exception as e:
            print(f"Ошибка при скачивании голосового: {e}")
            await message.answer(
                "Не получилось скачать голосовое сообщение 😔\n"
                "Попробуй ещё раз или напиши текстом."
            )
            return

        try:
            stt_text = await stt_recognize_ogg(ogg_data)
        except Exception as e:
            print(f"Ошибка STT: {e}")
            await message.answer(
                "Не получилось распознать голос 😔\n"
                "Попробуй ещё раз или напиши текстом."
            )
            return

        if not stt_text.strip():
            await message.answer(
                "Не разобрал, что сказано в голосовом 😔\n"
                "Попробуй ещё раз или напиши текстом."
            )
            return

        telegram_id = message.from_user.id

        try:
            tx = await api_parse_and_create(telegram_id=telegram_id, text=stt_text)
        except Exception as e:
            print(f"Ошибка при разборе текста из голосового через ИИ: {e}")
            await message.answer(
                "Голос распознал, но не получилось понять расход через ИИ 😔\n"
                "Попробуй ещё раз или напиши текстом."
            )
            return

        await send_tx_confirmation(
            message,
            tx,
            stt_text,
            via_ai=True,
            prefix="Распознал голос и записал расход через ИИ:",
        )

    # Любой текст без команды — как /aiadd (расход)
    @dp.message()
    async def handle_free_text(message: Message):
        text = (message.text or "").strip()
        if not text:
            return
        if text.startswith("/"):
            return

        telegram_id = message.from_user.id

        try:
            tx = await api_parse_and_create(telegram_id=telegram_id, text=text)
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                data = e.response.json()
                detail = data.get("detail") or ""
            except Exception:
                pass

            print(f"HTTP ошибка при разборе свободного текста через ИИ: {detail or e}")

            if isinstance(detail, str) and "Некорректная сумма" in detail:
                await message.answer(
                    "Похоже, я не увидел сумму в этом сообщении 🤔\n"
                    "Добавь число и валюту. Пример:\n"
                    "КБ Макс игрушки 750"
                )
            else:
                await message.answer(
                    "Не получилось разобрать это сообщение как расход 😔\n"
                    "Попробуй переформулировать или используй команду /aiadd."
                )
            return
        except Exception as e:
            print(f"Ошибка при разборе свободного текста через ИИ: {e}")
            await message.answer(
                "Не получилось разобрать это сообщение как расход 😔\n"
                "Можешь попробовать ещё раз или использовать команду /aiadd."
            )
            return

        await send_tx_confirmation(message, tx, text, via_ai=True)
    # Запускаем бесконечный цикл обработки апдейтов от Telegram
    logger.info("Бот запущен, ждём сообщения... Нажми Ctrl+C чтобы остановить.")

    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Бот остановлен.")

async def send_tx_confirmation(
    message: Message,
    tx: dict,
    source_text: str,
    via_ai: bool = False,
    prefix: str | None = None,
):
    amount = tx.get("amount")
    currency = tx.get("currency", "RUB")
    description = tx.get("description") or source_text
    category = tx.get("category") or "Без категории"
    date_raw = tx.get("date")
    kind = tx.get("kind", "expense")

    pretty_date = None
    if date_raw:
        try:
            pretty_date = datetime.fromisoformat(date_raw).strftime("%d.%m.%Y")
        except ValueError:
            pretty_date = date_raw

    lines = []

    if prefix:
        lines.append(prefix)
    else:
        if via_ai:
            if kind == "income":
                lines.append("Записал доход через ИИ:")
            else:
                lines.append("Записал расход через ИИ:")
        else:
            if kind == "income":
                lines.append("Записал доход:")
            else:
                lines.append("Записал расход:")

    lines.append(f"{amount} {currency}")
    lines.append(f"Категория: {category}")
    lines.append(f"Описание: {description}")
    if pretty_date:
        lines.append(f"Дата: {pretty_date}")

    await message.answer("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
