import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from dotenv import load_dotenv
import httpx

# Загружаем переменные окружения из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


async def api_create_transaction(
    amount: float,
    description: str | None = None,
    category: str | None = None,
):
    """Прямое создание транзакции через /transactions."""
    async with httpx.AsyncClient() as client:
        payload = {
            "amount": amount,
            "currency": "RUB",
            "description": description,
            "category": category,
        }
        resp = await client.post(
            f"{API_BASE_URL}/transactions",
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_get_report(days: int = 14):
    """Краткий отчёт через /report/summary."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/report/summary",
            params={"days": days},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def api_parse_and_create(text: str):
    """Разбор свободного текста через YandexGPT + создание транзакции."""
    async with httpx.AsyncClient() as client:
        payload = {"text": text}
        resp = await client.post(
            f"{API_BASE_URL}/transactions/parse-and-create",
            json=payload,
            timeout=20.0,
        )
        resp.raise_for_status()
        return resp.json()


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не найден. Проверь файл .env")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def cmd_start(message: Message):
        await message.answer(
            "Привет! 👋\n"
            "Я FamilyBudget Bot.\n\n"
            "Сейчас я умею:\n"
            "• /add — добавить расход в формате: /add 2435 Пятёрочка продукты\n"
            "• /aiadd — добавить расход свободным текстом с ИИ\n"
            "  пример: /aiadd Пятёрочка продукты 2435₽ вчера\n"
            "• /report — отчёт за последние 14 дней\n"
            "• /help — подсказка"
        )

    @dp.message(Command("help"))
    async def cmd_help(message: Message):
        await message.answer(
            "Доступные команды:\n"
            "/start — начать работу\n"
            "/help — помощь\n\n"
            "/add СУММА описание — добавить расход вручную\n"
            "  пример: /add 2435 Пятёрочка продукты\n\n"
            "/aiadd ТЕКСТ — добавить расход через ИИ (YandexGPT)\n"
            "  пример: /aiadd Пятёрочка продукты 2435₽ вчера\n\n"
            "/report — отчёт за последние 14 дней"
        )

    @dp.message(Command("add"))
    async def cmd_add(message: Message):
        """Простой формат: /add СУММА описание."""
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

        try:
            tx = await api_create_transaction(
                amount=amount,
                description=description,
            )
        except Exception as e:
            print(f"Ошибка при создании транзакции: {e}")
            await message.answer(
                "Не получилось сохранить расход 😔\n"
                "Попробуй позже."
            )
            return

        desc_text = tx.get("description") or "без описания"
        currency = tx.get("currency", "RUB")
        amount_saved = tx.get("amount", amount)

        await message.answer(
            f"Записал расход: {amount_saved} {currency}\n"
            f"Описание: {desc_text}"
        )

    @dp.message(Command("aiadd"))
    async def cmd_aiadd(message: Message):
        """
        Умный ввод: /aiadd Пятёрочка продукты 2435₽ вчера
        Текст после команды отправляем в YandexGPT.
        """
        text = message.text or ""
        parts = text.split(maxsplit=1)  # ['/aiadd', 'Пятёрочка продукты 2435₽ вчера']

        if len(parts) < 2:
            await message.answer(
                "Напиши расход после команды.\n\n"
                "Пример:\n"
                "/aiadd Пятёрочка продукты 2435₽ вчера"
            )
            return

        raw_text = parts[1]

        try:
            tx = await api_parse_and_create(raw_text)
        except Exception as e:
            print(f"Ошибка при разборе через ИИ: {e}")
            await message.answer(
                "Не получилось разобрать расход через ИИ 😔\n"
                "Попробуй ещё раз или используй /add."
            )
            return

        amount = tx.get("amount")
        currency = tx.get("currency", "RUB")
        description = tx.get("description") or raw_text
        category = tx.get("category") or "Без категории"
        date = tx.get("date")

        msg_lines = [
            "Записал расход через ИИ:",
            f"{amount} {currency}",
            f"Категория: {category}",
            f"Описание: {description}",
        ]
        if date:
            msg_lines.append(f"Дата: {date}")

        await message.answer("\n".join(msg_lines))

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

    print("Бот запущен. Нажми Ctrl+C, чтобы остановить.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
