import asyncio
import os
from datetime import datetime

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, BufferedInputFile
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

# Для распознавания голоса (пока у нас там 401, но оставляем код как есть)
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")


# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С БЭКЕНДОМ ----------


async def api_create_transaction(
    amount: float,
    description: str | None = None,
    category: str | None = None,
    telegram_id: int | None = None,
    telegram_name: str | None = None,
    telegram_username: str | None = None,
):
    """Прямое создание транзакции через /transactions."""
    async with httpx.AsyncClient() as client:
        payload = {
            "amount": amount,
            "currency": "RUB",
            "description": description,
            "category": category,
            "telegram_id": telegram_id,
            "telegram_name": telegram_name,
            "telegram_username": telegram_username,
        }
        resp = await client.post(
            f"{API_BASE_URL}/transactions",
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_get_report(days: int = 14):
    """Краткий отчёт через /report/summary (пока по всей семье)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/report/summary",
            params={"days": days},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_parse_and_create(
    text: str,
    telegram_id: int | None = None,
    telegram_name: str | None = None,
    telegram_username: str | None = None,
):
    """Разбор свободного текста через YandexGPT + создание транзакции."""
    async with httpx.AsyncClient() as client:
        payload = {
            "text": text,
            "telegram_id": telegram_id,
            "telegram_name": telegram_name,
            "telegram_username": telegram_username,
        }
        resp = await client.post(
            f"{API_BASE_URL}/transactions/parse-and-create",
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_create_reminder(
    title: str,
    amount: float | None,
    interval_days: int | None,
    telegram_id: int | None = None,
    telegram_name: str | None = None,
    telegram_username: str | None = None,
):
    """Создать напоминание через /reminders."""
    async with httpx.AsyncClient() as client:
        payload = {
            "title": title,
            "amount": amount,
            "currency": "RUB",
            "interval_days": interval_days,
            "next_run_at": None,
            "telegram_id": telegram_id,
            "telegram_name": telegram_name,
            "telegram_username": telegram_username,
        }
        resp = await client.post(
            f"{API_BASE_URL}/reminders",
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_list_reminders(telegram_id: int | None = None):
    """Получить список активных напоминаний."""
    params: dict[str, object] = {"only_active": True}
    if telegram_id is not None:
        params["telegram_id"] = telegram_id

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/reminders",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_get_due_reminders(telegram_id: int | None = None):
    """Получить напоминания, которые нужно оплатить сегодня (и просроченные)."""
    params: dict[str, object] = {}
    if telegram_id is not None:
        params["telegram_id"] = telegram_id

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/reminders/due-today",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_mark_reminder_paid(reminder_id: int):
    """Отметить напоминание как оплачено."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/reminders/{reminder_id}/mark-paid",
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_export_csv(days: int = 30) -> bytes:
    """Получить CSV с транзакциями за N дней."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/transactions/export/csv",
            params={"days": days},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.content


# ---------- РАСПОЗНАВАНИЕ ГОЛОСА (STT — ПОКА 401, НО КОД ОСТАВЛЯЕМ) ----------


async def stt_recognize_ogg(data: bytes, lang: str = "ru-RU") -> str:
    """
    Распознаёт речь из OGG/Opus (голосовое Telegram) через Yandex SpeechKit STT v1.
    Сейчас у нас 401 PermissionDenied, но код оставляем, чтобы потом вернуть.
    """
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


# ---------- ОСНОВНАЯ ЛОГИКА БОТА ----------


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не найден. Проверь файл .env")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # /start
    @dp.message(CommandStart())
    async def cmd_start(message: Message):
        await message.answer(
            "Привет! 👋\n"
            "Я FamilyBudget Bot.\n\n"
            "Сейчас я умею:\n"
            "• просто напиши: Перекрёсток продукты 2435₽ вчера — я сам пойму через ИИ\n"
            "• /aiadd — то же самое, но явно через ИИ\n"
            "• /add — ручной ввод суммы\n"
            "• /report — отчёт за последние 14 дней\n"
            "• /remind_add — создать напоминание\n"
            "• /reminders — список напоминаний\n"
            "• /remind_today — что нужно оплатить сегодня\n"
            "• /remind_pay — отметить напоминание как оплачено\n"
            "• /export — экспорт расходов в CSV\n"
            "• /help — подсказка"
        )

    # /help
    @dp.message(Command("help"))
    async def cmd_help(message: Message):
        await message.answer(
            "Доступные команды:\n"
            "/start — начать работу\n"
            "/help — помощь\n\n"
            "/add СУММА описание — добавить расход вручную\n"
            "  пример: /add 2435 Пятёрочка продукты\n\n"
            "/aiadd ТЕКСТ — добавить расход через ИИ (YandexGPT)\n"
            "  пример: /aiadd Перекрёсток продукты 2435₽ вчера\n\n"
            "Просто текстом (без команды):\n"
            "  Перекрёсток продукты 2435₽ вчера\n"
            "  Перекрёсток, продукты, две тысячи четыреста тридцать пять рублей, вчера\n\n"
            "/report — отчёт за последние 14 дней\n"
            "/export [дней] — экспорт расходов в CSV\n\n"
            "Напоминания:\n"
            "/remind_add НАЗВАНИЕ СУММА ДНЕЙ\n"
            "  пример: /remind_add Коммуналка 8000 30\n"
            "/reminders — список активных напоминаний\n"
            "/remind_today — список платежей на сегодня\n"
            "/remind_pay ID — отметить напоминание как оплачено"
        )

    # /add — ручной формат: /add 2435 Пятёрочка продукты
    @dp.message(Command("add"))
    async def cmd_add(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=2)  # ['/add', '2435', 'Пятёрочка продукты']

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

        from_user = message.from_user
        telegram_id = from_user.id if from_user else None
        telegram_name = from_user.full_name if from_user else None
        telegram_username = from_user.username if from_user else None

        try:
            tx = await api_create_transaction(
                amount=amount,
                description=description,
                telegram_id=telegram_id,
                telegram_name=telegram_name,
                telegram_username=telegram_username,
            )
        except Exception as e:
            print(f"Ошибка при создании транзакции: {e}")
            await message.answer(
                "Не получилось сохранить расход 😔\n"
                "Попробуй позже."
            )
            return

        await send_tx_confirmation(message, tx, description or "", via_ai=False)

    # /remind_add — создать напоминание
    @dp.message(Command("remind_add"))
    async def cmd_remind_add(message: Message):
        """
        Создать напоминание.
        Формат: /remind_add НАЗВАНИЕ СУММА ДНЕЙ
        Пример: /remind_add Коммуналка 8000 30
        """
        text = message.text or ""
        parts = text.split(maxsplit=3)  # ['/remind_add', 'Коммуналка', '8000', '30']

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

        from_user = message.from_user
        telegram_id = from_user.id if from_user else None
        telegram_name = from_user.full_name if from_user else None
        telegram_username = from_user.username if from_user else None

        try:
            rem = await api_create_reminder(
                title,
                amount,
                interval_days,
                telegram_id=telegram_id,
                telegram_name=telegram_name,
                telegram_username=telegram_username,
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
                pretty_date = datetime.fromisoformat(next_date_raw).strftime("%d.%m.%Y")
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
        from_user = message.from_user
        telegram_id = from_user.id if from_user else None

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
        """
        Показать, что нужно оплатить сегодня (и всё, что уже просрочено).
        """
        from_user = message.from_user
        telegram_id = from_user.id if from_user else None

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
        """
        Отметить напоминание как оплачено.
        Формат: /remind_pay ID
        Пример: /remind_pay 1
        """
        text = message.text or ""
        parts = text.split(maxsplit=1)  # ['/remind_pay', '1']

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

        try:
            rem = await api_mark_reminder_paid(rem_id)
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

    # /export — экспорт CSV
    @dp.message(Command("export"))
    async def cmd_export(message: Message):
        """
        Экспорт расходов в CSV-файл.
        Формат: /export [дней]
        Примеры:
          /export        -> 30 дней по умолчанию
          /export 90     -> 90 дней
        """
        text = message.text or ""
        parts = text.split(maxsplit=1)

        days = 30
        if len(parts) == 2:
            try:
                days = int(parts[1])
            except ValueError:
                await message.answer("Не понял количество дней. Пример: /export 30")
                return

        try:
            csv_bytes = await api_export_csv(days)
        except Exception as e:
            print(f"Ошибка при экспорте CSV: {e}")
            await message.answer("Не получилось сделать экспорт 😔 Попробуй позже.")
            return

        filename = f"transactions_{days}d.csv"
        file = BufferedInputFile(csv_bytes, filename=filename)

        await message.answer_document(
            document=file,
            caption=f"Экспорт расходов за последние {days} дней.",
        )

    # /aiadd — умный ввод через ИИ
    @dp.message(Command("aiadd"))
    async def cmd_aiadd(message: Message):
        """
        Умный ввод: /aiadd Перекрёсток продукты 2435₽ вчера
        Текст после команды отправляем в YandexGPT.
        """
        text = message.text or ""
        parts = text.split(maxsplit=1)  # ['/aiadd', 'Перекрёсток продукты 2435₽ вчера']

        if len(parts) < 2:
            await message.answer(
                "Напиши расход после команды.\n\n"
                "Пример:\n"
                "/aiadd Перекрёсток продукты 2435₽ вчера"
            )
            return

        raw_text = parts[1]

        from_user = message.from_user
        telegram_id = from_user.id if from_user else None
        telegram_name = from_user.full_name if from_user else None
        telegram_username = from_user.username if from_user else None

        try:
            tx = await api_parse_and_create(
                raw_text,
                telegram_id=telegram_id,
                telegram_name=telegram_name,
                telegram_username=telegram_username,
            )
        except Exception as e:
            print(f"Ошибка при разборе свободного текста через ИИ: {e}")
            await message.answer(
                "Не получилось разобрать расход через ИИ 😔\n"
                "Попробуй ещё раз или используй /add."
            )
            return

        await send_tx_confirmation(message, tx, raw_text, via_ai=True)

    # /report — отчёт по последним 14 дням
    @dp.message(Command("report"))
    async def cmd_report(message: Message):
        days = 14

        try:
            report = await api_get_report(days=days)
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
            f"Отчёт за последние {days} дней:",
            f"Всего расходов: {total:.2f} {currency}",
            "",
            "По категориям:",
        ]

        for item in by_cat:
            cat = item.get("category") or "Без категории"
            amt = item.get("amount", 0)
            lines.append(f"- {cat}: {amt:.2f} {currency}")

        await message.answer("\n".join(lines))

    # Голосовые — пока пытаемся, но из-за 401 может не работать
    @dp.message(F.voice)
    async def handle_voice(message: Message):
        await message.answer("Секунду, распознаю голос и запишу расход... 🎧")

        # 1) скачиваем голосовое из Telegram
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

        # 2) STT → текст
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

        from_user = message.from_user
        telegram_id = from_user.id if from_user else None
        telegram_name = from_user.full_name if from_user else None
        telegram_username = from_user.username if from_user else None

        # 3) Текст → транзакция через ИИ
        try:
            tx = await api_parse_and_create(
                stt_text,
                telegram_id=telegram_id,
                telegram_name=telegram_name,
                telegram_username=telegram_username,
            )
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

    # ---- ЛЮБОЙ ПРОСТОЙ ТЕКСТ -> ИИ (как /aiadd) ----
    @dp.message()
    async def handle_free_text(message: Message):
        text = (message.text or "").strip()
        if not text:
            return

        # Команды (начинаются с "/") сюда не должны попадать
        if text.startswith("/"):
            return

        from_user = message.from_user
        telegram_id = from_user.id if from_user else None
        telegram_name = from_user.full_name if from_user else None
        telegram_username = from_user.username if from_user else None

        try:
            tx = await api_parse_and_create(
                text,
                telegram_id=telegram_id,
                telegram_name=telegram_name,
                telegram_username=telegram_username,
            )
        except Exception as e:
            print(f"Ошибка при разборе свободного текста через ИИ: {e}")
            await message.answer(
                "Не получилось разобрать это сообщение как расход 😔\n"
                "Можешь попробовать ещё раз или использовать команду /aiadd."
            )
            return

        await send_tx_confirmation(message, tx, text, via_ai=True)

    print("Бот запущен. Нажми Ctrl+C, чтобы остановить.")
    await dp.start_polling(bot)


async def send_tx_confirmation(
    message: Message,
    tx: dict,
    source_text: str,
    via_ai: bool = False,
    prefix: str | None = None,
):
    """Формирует красивый ответ про записанный расход."""
    amount = tx.get("amount")
    currency = tx.get("currency", "RUB")
    description = tx.get("description") or source_text
    category = tx.get("category") or "Без категории"
    date_raw = tx.get("date")

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
            lines.append("Записал расход через ИИ:")
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
