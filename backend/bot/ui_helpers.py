"""
bot/ui_helpers.py — Вспомогательные функции для UI: форматирование, подтверждения
"""

from datetime import datetime
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from .api_client import api_get_categories, api_log_category_feedback
from .cache import ai_suggestions_cache


def format_amount(amount, currency: str) -> str:
    """
    Красиво форматируем сумму:
    123456.78 -> '123 457 RUB'
    """
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0

    # :,.0f — разделитель тысяч, без копеек
    text = f"{value:,.0f}".replace(",", " ")
    return f"{text} {currency}"


async def send_tx_confirmation(
    message: Message,
    tx: dict,
    source_text: str,
    via_ai: bool = False,
    prefix: str | None = None,
):
    """
    Красивое сообщение после записи расхода/дохода.
    tx — это json-ответ от бэкенда (/transactions или /transactions/parse-and-create).
    """

    # Базовые поля
    amount = float(tx.get("amount", 0) or 0)
    currency = tx.get("currency") or "RUB"
    category = tx.get("category") or "Без категории"
    description = tx.get("description") or ""
    kind = (tx.get("kind") or "expense").lower()

    # Дата
    date_raw = tx.get("date") or tx.get("created_at")
    pretty_date = ""
    if isinstance(date_raw, str):
        try:
            dt = datetime.fromisoformat(date_raw)
            pretty_date = dt.strftime("%d.%m.%Y")
        except ValueError:
            pretty_date = date_raw or ""
    elif isinstance(date_raw, datetime):
        pretty_date = date_raw.strftime("%d.%m.%Y")

    kind_text = "Расход" if kind == "expense" else "Доход"

    lines: list[str] = []

    # Префикс типа "Записал доход:" если передан
    if prefix:
        lines.append(prefix)
        lines.append("")

    lines.append(f"{kind_text}: {amount:.2f} {currency}")
    lines.append(f"Категория: {category}")

    if description:
        lines.append(f"Описание: {description}")

    if pretty_date:
        lines.append(f"Дата: {pretty_date}")

    # ---- БЛОК ПРО БЮДЖЕТ ----
    budget_limit = tx.get("budget_limit")
    budget_spent = tx.get("budget_spent")
    budget_percent = tx.get("budget_percent")

    # Бюджет показываем только для расходов и только если есть данные
    if (
        kind == "expense"
        and budget_limit is not None
        and budget_spent is not None
        and budget_percent is not None
    ):
        try:
            limit_val = float(budget_limit)
            spent_val = float(budget_spent)
            percent = float(budget_percent)
        except (TypeError, ValueError):
            limit_val = spent_val = percent = None

        if limit_val and percent is not None:
            lines.append("")

            if percent >= 100:
                lines.append(
                    f"🔴 Бюджет по категории почти или уже превышен!"
                )

                lines.append(
                    f"Потрачено {spent_val:.0f} из {limit_val:.0f} RUB ({percent:.1f}%)."
                )

            elif percent >= 80:
                lines.append(
                    f"🟡 Внимание: выбрано уже {percent:.1f}% бюджета "
                    f"({spent_val:.0f}/{limit_val:.0f} RUB)."
                )

    # ---- Если расход прописал ИИ, покажем исходный текст ----
    if via_ai:
        lines.append("")
        lines.append("🧠 Распознал это сообщение через ИИ:")
        lines.append(f"«{source_text}»")

    await message.answer("\n".join(lines))


async def send_ai_category_suggestions(
    message: Message,
    tx: dict,
    telegram_id: int,
    original_text: str | None = None,
):
    """
    После ИИ-расхода показываем кнопки категорий.
    v2: используем candidate_categories от backend и
    сохраняем всё в кэш для последующего логирования.
    """

    current_category = (tx.get("category") or "").strip()
    if not current_category:
        return

    suggestions: list[str] = []

    # 1. Кандидатные категории от backend (если есть)
    raw_candidates = tx.get("candidate_categories") or []

    if isinstance(raw_candidates, list):
        for val in raw_candidates:
            name = str(val or "").strip()
            if not name:
                continue

            if name not in suggestions:
                suggestions.append(name)

    # 2. Гарантируем, что текущая категория есть и стоит первой
    if current_category not in suggestions:
        suggestions.insert(0, current_category)
    else:
        suggestions = [current_category] + [
            c for c in suggestions if c != current_category
        ]

    # Ограничим размер
    suggestions = suggestions[:4]

    # 3. Если всё равно мало вариантов — добираем из /categories
    if len(suggestions) <= 1:
        try:
            cats = await api_get_categories(telegram_id)
        except Exception as e:
            print(f"Ошибка при получении категорий для подсказок: {e}")
            return

        names: list[str] = []

        for c in cats or []:
            name = (c.get("name") or "").strip()
            if not name:
                continue

            if name not in names:
                names.append(name)

        for name in names:
            if name == current_category:
                continue

            suggestions.append(name)

            if len(suggestions) >= 4:
                break

    # Убираем дубликаты ещё раз
    uniq: list[str] = []
    for name in suggestions:
        if name not in uniq:
            uniq.append(name)

    suggestions = uniq

    # Если всё равно одна категория — кнопки не нужны
    if len(suggestions) <= 1:
        return

    # 4. Сохраняем всё в кэш по (telegram_id, tx_id)
    tx_id = tx.get("id")
    if tx_id is not None:
        key = (telegram_id, int(tx_id))
        ai_suggestions_cache[key] = {
            "ai_category": current_category,
            "candidate_categories": tx.get("candidate_categories") or [],
            "suggestions": suggestions,
            "original_text": original_text,
        }

    # 5. Строим клавиатуру с tx_id в callback_data
    buttons: list[list[InlineKeyboardButton]] = []

    for name in suggestions:
        label = f"✅ {name}" if name == current_category else name
        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"setcat_ai:{tx_id}:{name}",
                )
            ]
        )

    # Отдельная кнопка, если ни одна категория не подходит
    buttons.append(
        [
            InlineKeyboardButton(
                text="Нет подходящей категории",
                callback_data=f"setcat_ai_other:{tx_id}",
            )
        ]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        "Если категория не та — выбери правильную:",
        reply_markup=keyboard,
    )
