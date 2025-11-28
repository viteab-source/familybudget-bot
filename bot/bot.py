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
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")


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
            "/income СУММА описание — добавить доход вручную\n"
            "  пример: /income 50000 Зарплата\n\n"
            "/aiadd ТЕКСТ — добавить расход через ИИ (YandexGPT)\n"
            "  пример: /aiadd Перекрёсток продукты 2435₽ вчера\n\n"
            "/report [дней] — отчёт по расходам (по умолчанию 14)\n"
            "/balance [дней] — баланс доходы/расходы (по умолчанию 30)\n"
            "/export [дней] — экспорт в CSV (по умолчанию 30)\n\n"
            "Напоминания:\n"
            "/remind_add НАЗВАНИЕ СУММА ДНЕЙ\n"
            "  пример: /remind_add Коммуналка 8000 30\n"
            "/reminders — список активных напоминаний\n"
            "/remind_today — список платежей на сегодня\n"
            "/remind_pay ID — отметить напоминание как оплачено"
        )

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
