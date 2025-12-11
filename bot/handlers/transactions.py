"""
Команды для работы с транзакциями (расходы/доходы).
"""

import os

import httpx
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..services.api_client import APIClient
from ..config import API_BASE_URL, YANDEX_API_KEY

async def log_category_feedback(telegram_id: int, selected_category: str, transaction_id: int = None):
    """
    Логирует выбор пользователя для обучения AI.
    Отправляет данные на backend /api/categories/feedback
    """
    try:
        url = f"{API_BASE_URL}/categories/feedback"
        params = {"telegram_id": telegram_id}
        payload = {
            "transaction_id": transaction_id,
            "user_selected_category": selected_category,
        }
        async with httpx.AsyncClient() as client:
            await client.post(url, params=params, json=payload, timeout=5.0)
    except Exception:
        # Тихо игнорируем ошибки логирования (не критично)
        pass    

router = Router()
api = APIClient(API_BASE_URL)


# ==========================================
# FSM States
# ==========================================

class AddTransactionStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_description = State()
    waiting_for_category = State()


class AddIncomeStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_description = State()


class AIAddStates(StatesGroup):
    waiting_for_text = State()


class EditLastStates(StatesGroup):
    waiting_for_new_value = State()


class SetCategoryStates(StatesGroup):
    waiting_for_custom_category = State()
    waiting_for_correction_confirm = State()

# ==========================================
# Вспомогательные функции
# ==========================================

from datetime import datetime  # Вверху файла, рядом с остальными import

def format_transaction(tx: dict) -> str:
    """Форматирует транзакцию для вывода пользователю."""
    kind_emoji = "📤" if tx.get("kind") == "income" else "📥"
    amount = tx.get("amount", 0)
    currency = tx.get("currency", "RUB")
    description = tx.get("description") or "—"
    category = tx.get("category") or "Без категории"

    text = f"{kind_emoji} <b>{amount:,.0f} {currency}</b>\n"
    text += f"Описание: {description}\n"
    text += f"Категория: {category}"

    # Дата операции
    date_str = tx.get("date") or tx.get("created_at")
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str)
            text += f"\nДата: {dt:%d.%m.%Y}"
        except Exception:
            # Если формат неожиданный, просто игнорируем
            pass

    # Если есть данные по бюджету
    if tx.get("budget_limit"):
        limit = tx.get("budget_limit")
        spent = tx.get("budget_spent")
        percent = tx.get("budget_percent")
        text += f"\n\n💰 Бюджет: {spent:,.0f} / {limit:,.0f} ({percent}%)"
        if percent >= 100:
            text += " ⚠️ Превышен!"
        elif percent >= 80:
            text += " ⚡️"

    return text

async def transcribe_voice(file_path: str) -> str:
    """
    Преобразование голосового сообщения в текст через Yandex STT.
    """
    if not YANDEX_API_KEY:
        raise RuntimeError("YANDEX_API_KEY не настроен")

    url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}

    with open(file_path, "rb") as f:
        data = f.read()

    params = {
        "lang": "ru-RU",
        "format": "oggopus",
        "sampleRateHertz": 48000,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, params=params, content=data, timeout=30.0)
        resp.raise_for_status()
        result = resp.json()

    return result.get("result", "")


# ==========================================
# /add — добавить расход вручную
# ==========================================

@router.message(Command("add"))
async def cmd_add(message: types.Message, state: FSMContext):
    """Начало процесса добавления расхода."""
    await message.answer("💸 Введи сумму расхода:")
    await state.set_state(AddTransactionStates.waiting_for_amount)


@router.message(AddTransactionStates.waiting_for_amount)
async def process_add_amount(message: types.Message, state: FSMContext):
    """Обработка суммы."""
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Введи корректную сумму (например: 1500):")
        return

    await state.update_data(amount=amount)
    await message.answer("📝 Введи описание (или отправь '-' чтобы пропустить):")
    await state.set_state(AddTransactionStates.waiting_for_description)


@router.message(AddTransactionStates.waiting_for_description)
async def process_add_description(message: types.Message, state: FSMContext):
    """Обработка описания."""
    description = message.text.strip()
    if description == "-":
        description = None

    await state.update_data(description=description)
    await message.answer("🏷 Введи категорию (или '-' чтобы пропустить):")
    await state.set_state(AddTransactionStates.waiting_for_category)

@router.message(AddTransactionStates.waiting_for_category)
async def process_add_category(message: types.Message, state: FSMContext):
    """
    Обработка категории и создание транзакции.

    Новое:
    - если бэкенд нашёл опечатку и вернул suggested_category + needs_confirmation = True,
      показываем пользователю уточнение «Такси / Такиси?» с кнопками.
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    category = message.text.strip()
    if category == "-":
        category = None

    data = await state.get_data()
    amount = data["amount"]
    description = data.get("description")

    telegram_id = message.from_user.id

    try:
        # 1. Создаём транзакцию на бэке
        tx = await api.create_transaction(
            telegram_id=telegram_id,
            amount=amount,
            description=description,
            category=category,
            kind="expense",
        )

        # 2. Показываем обычное подтверждение расхода
        text = "✅ Расход добавлен:\n\n" + format_transaction(tx)
        await message.answer(text, parse_mode="HTML")

        # 3. Проверяем, не попросил ли бэкенд уточнить категорию
        raw_category = tx.get("raw_category")
        suggested_category = tx.get("suggested_category")
        needs_confirmation = tx.get("needs_confirmation", False)
        tx_id = tx.get("id")

        if (
            needs_confirmation
            and raw_category
            and suggested_category
            and raw_category != suggested_category
        ):
            # Сохраняем данные в состояние — пригодятся в callback'е
            await state.update_data(
                raw_category=raw_category,
                backend_category=suggested_category,
                tx_id=tx_id,
            )

            question_text = (
                f"🤔 Похоже, ты имел в виду «{suggested_category}», а не «{raw_category}».\n"
                f"Как сохранить?"
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"✅ {suggested_category}",
                            callback_data="catfix_accept_backend",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=f"Оставить «{raw_category}»",
                            callback_data="catfix_keep_raw",
                        )
                    ],
                ]
            )

            # Переключаемся в состояние ожидания подтверждения
            await state.set_state(SetCategoryStates.waiting_for_correction_confirm)
            await message.answer(question_text, reply_markup=kb)
        else:
            # Если подтверждение не нужно — просто выходим из FSM
            await state.clear()

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        await state.clear()

# ==========================================
# /income — добавить доход
# ==========================================

@router.message(Command("income"))
async def cmd_income(message: types.Message, state: FSMContext):
    """Начало процесса добавления дохода."""
    await message.answer("💰 Введи сумму дохода:")
    await state.set_state(AddIncomeStates.waiting_for_amount)


@router.message(AddIncomeStates.waiting_for_amount)
async def process_income_amount(message: types.Message, state: FSMContext):
    """Обработка суммы дохода."""
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Введи корректную сумму (например: 50000):")
        return

    await state.update_data(amount=amount)
    await message.answer("📝 Введи описание (или '-' чтобы пропустить):")
    await state.set_state(AddIncomeStates.waiting_for_description)


@router.message(AddIncomeStates.waiting_for_description)
async def process_income_description(message: types.Message, state: FSMContext):
    """Обработка описания и создание дохода."""
    description = message.text.strip()
    if description == "-":
        description = None

    data = await state.get_data()
    amount = data["amount"]
    telegram_id = message.from_user.id

    try:
        tx = await api.create_transaction(
            telegram_id=telegram_id,
            amount=amount,
            description=description,
            category="Доход",
            kind="income",
        )
        text = "✅ Доход добавлен:\n\n" + format_transaction(tx)
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

    await state.clear()


# ==========================================
# /aiadd — добавить через ИИ (текст)
# ==========================================

@router.message(Command("aiadd"))
async def cmd_aiadd(message: types.Message, state: FSMContext):
    """Начало процесса добавления через ИИ."""
    await message.answer(
        "🤖 Напиши расход свободным текстом.\n\n"
        "Примеры:\n"
        "• Пятёрочка продукты 2435₽\n"
        "• Кафе 1500\n"
        "• Бензин 3000 вчера"
    )
    await state.set_state(AIAddStates.waiting_for_text)

# ==========================================
# Обработчик смены категории (inline кнопки)
# ==========================================

@router.callback_query(F.data.startswith("setcat_"))
async def handle_category_change(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора категории через inline кнопки"""
    data = callback.data.replace("setcat_", "")
    telegram_id = callback.from_user.id

    if data == "custom":
        await callback.message.edit_text("✏️ Введи название категории:", reply_markup=None)
        await state.set_state(SetCategoryStates.waiting_for_custom_category)
        await callback.answer()
        return

    category = data

    try:
        tx = await api.set_last_transaction_category(telegram_id, category)
        new_text = "✅ Категория изменена:\n\n" + format_transaction(tx)
        await callback.message.edit_text(new_text, parse_mode="HTML", reply_markup=None)
        await callback.answer(f"✅ Категория: {category}")
        await log_category_feedback(telegram_id, category, tx.get("id"))
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.message(SetCategoryStates.waiting_for_custom_category)
async def process_custom_category(message: types.Message, state: FSMContext):
    """Обработка ввода своей категории с учётом возможной автокоррекции на бэкенде."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    raw_category = message.text.strip()

    if not raw_category:
        await message.answer("❌ Категория не может быть пустой. Попробуй ещё раз:")
        return

    telegram_id = message.from_user.id

    try:
        # Меняем категорию у последней транзакции
        tx = await api.set_last_transaction_category(telegram_id, raw_category)

        backend_category = tx.get("category") or raw_category

        # Если бэкенд фактически использовал другое имя категории — предлагаем подтвердить
        if backend_category != raw_category:
            # Сохраняем данные в состояние, чтобы знать выбор пользователя позже
            await state.update_data(
                raw_category=raw_category,
                backend_category=backend_category,
                tx_id=tx.get("id"),
            )

            text = (
                f"🤔 Похоже, ты имел в виду «{backend_category}», а не «{raw_category}».\n"
                f"Как сохранить?"
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"✅ {backend_category}",
                            callback_data="catfix_accept_backend",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=f"Оставить «{raw_category}»",
                            callback_data="catfix_keep_raw",
                        )
                    ],
                ]
            )

            await message.answer(text, reply_markup=kb)
            await state.set_state(SetCategoryStates.waiting_for_correction_confirm)
        else:
            # Имя категории не менялось — ведём себя как раньше
            text = "✅ Категория изменена:\n\n" + format_transaction(tx)
            await message.answer(text, parse_mode="HTML")

            # Логируем выбор для обучения AI
            await log_category_feedback(telegram_id, backend_category, tx.get("id"))

            # Выходим из состояния
            await state.clear()

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        await state.clear()

@router.callback_query(
    SetCategoryStates.waiting_for_correction_confirm,
    F.data.in_(["catfix_accept_backend", "catfix_keep_raw"]),
)
async def handle_category_correction_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение исправления категории после автокоррекции бэкендом."""
    data = await state.get_data()
    raw_category = data.get("raw_category")
    backend_category = data.get("backend_category")
    tx_id = data.get("tx_id")
    telegram_id = callback.from_user.id

    choice = callback.data

    try:
        if choice == "catfix_accept_backend":
            # Пользователь соглашается с исправленной категорией
            # Категория уже выставлена на бэкенде (backend_category), просто логируем feedback
            await log_category_feedback(telegram_id, backend_category, tx_id)
            await callback.message.edit_text(
                f"✅ Оставляем категорию «{backend_category}».\n"
                f"Твоё исправление поможет боту запоминать такие случаи.",
                reply_markup=None,
            )
        else:
            # Пользователь хочет оставить свою «кривую» категорию
            # Явно выставляем её на бэкенде
            tx = await api.set_last_transaction_category(telegram_id, raw_category)
            await log_category_feedback(telegram_id, raw_category, tx.get("id"))

            text = "✅ Категория изменена:\n\n" + format_transaction(tx)
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=None)

        await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
    finally:
        await state.clear()

@router.message(AIAddStates.waiting_for_text)
async def process_aiadd(message: types.Message, state: FSMContext):
    """Обработка текста через ИИ и создание транзакции."""
    text = message.text.strip()
    if not text:
        await message.answer("❌ Текст не может быть пустым. Попробуй ещё раз:")
        return

    telegram_id = message.from_user.id
    processing_msg = await message.answer("🤖 Обрабатываю через ИИ...")

    try:
        tx = await api.parse_and_create(telegram_id, text)
        await processing_msg.delete()

        result_text = "✅ Расход добавлен (ИИ):\n\n" + format_transaction(tx)

        selected_category = tx.get("category", "Без категории")
        candidate_cats = tx.get("candidate_categories", [])

        if candidate_cats:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            buttons = []

            # Кнопка с текущей категорией
            buttons.append([
                InlineKeyboardButton(
                    text=f"✅ {selected_category}",
                    callback_data=f"setcat_{selected_category}",
                )
            ])

            # Альтернативы от AI
            for cat in candidate_cats:
                if cat != selected_category:
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"📂 {cat}",
                            callback_data=f"setcat_{cat}",
                        )
                    ])

            # Кнопка "Другая категория"
            buttons.append([
                InlineKeyboardButton(
                    text="✏️ Другая категория",
                    callback_data="setcat_custom",
                )
            ])

            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            result_text += f"\n\n💡 Категория: {selected_category}\nИли выбери другую:"
            await message.answer(result_text, parse_mode="HTML", reply_markup=kb)
        else:
            await message.answer(result_text, parse_mode="HTML")
    except Exception as e:
        await processing_msg.delete()
        await message.answer(f"❌ Ошибка: {e}")

    await state.clear()


# ==========================================
# Обработка обычного текста (автоматический AI)
# ==========================================

@router.message(
    F.text
    & ~F.text.startswith("/")
    & ~F.text.in_(["📊 Отчёты", "🔔 Напоминания", "⚙️ Настройки", "❓ Помощь"])
)
async def handle_plain_text(message: types.Message, state: FSMContext):
    """
    Обработка любого текста (не команды, не кнопки меню) через AI.
    """
    current_state = await state.get_state()
    if current_state:
        return

    text = message.text.strip()
    telegram_id = message.from_user.id
    processing_msg = await message.answer("🤖 Обрабатываю...")

    try:
        tx = await api.parse_and_create(telegram_id, text)
        await processing_msg.delete()

        result_text = "✅ Добавлено:\n\n" + format_transaction(tx)

        selected_category = tx.get("category", "Без категории")
        candidate_cats = tx.get("candidate_categories", [])

        if candidate_cats:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            buttons = []

            # Кнопка с текущей категорией
            buttons.append([
                InlineKeyboardButton(
                    text=f"✅ {selected_category}",
                    callback_data=f"setcat_{selected_category}",
                )
            ])

            # Альтернативы от AI
            for cat in candidate_cats:
                if cat != selected_category:
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"📂 {cat}",
                            callback_data=f"setcat_{cat}",
                        )
                    ])

            # Кнопка "Другая категория"
            buttons.append([
                InlineKeyboardButton(
                    text="✏️ Другая категория",
                    callback_data="setcat_custom",
                )
            ])

            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            result_text += f"\n\n💡 Категория: {selected_category}\nИли выбери другую:"
            await message.answer(result_text, parse_mode="HTML", reply_markup=kb)
        else:
            await message.answer(result_text, parse_mode="HTML")
    except Exception:
        await processing_msg.delete()
        await message.answer("❌ Не удалось обработать. Попробуй:\n\"Магнит 500\" или \"Такси 350\"")


# ==========================================
# Голосовые сообщения (STT + ИИ)
# ==========================================

@router.message(F.voice)
async def handle_voice(message: types.Message):
    """Обработка голосового сообщения."""
    telegram_id = message.from_user.id
    processing_msg = await message.answer("🎤 Распознаю голос...")

    try:
        file_id = message.voice.file_id
        file = await message.bot.get_file(file_id)
        file_path = file.file_path

        local_path = f"/tmp/voice_{telegram_id}_{file_id}.ogg"
        await message.bot.download_file(file_path, local_path)

        text = await transcribe_voice(local_path)
        os.remove(local_path)

        if not text:
            await processing_msg.edit_text("❌ Не удалось распознать голос. Попробуй ещё раз.")
            return

        await processing_msg.edit_text(
            f"📝 Распознано: <i>{text}</i>\n\n🤖 Обрабатываю...", parse_mode="HTML"
        )

        tx = await api.parse_and_create(telegram_id, text)
        await processing_msg.delete()

        result_text = "✅ Расход добавлен (голос + ИИ):\n\n" + format_transaction(tx)
        await message.answer(result_text, parse_mode="HTML")
    except Exception as e:
        await processing_msg.delete()
        await message.answer(f"❌ Ошибка: {e}")


# ==========================================
# /last — последняя транзакция
# ==========================================

@router.message(Command("last"))
async def cmd_last(message: types.Message):
    """Показать последнюю транзакцию."""
    telegram_id = message.from_user.id

    try:
        tx = await api.get_last_transaction(telegram_id)
        text = "📋 Последняя операция:\n\n" + format_transaction(tx)
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ {e}")


# ==========================================
# /delete_last — удалить последнюю
# ==========================================

@router.message(Command("delete_last"))
async def cmd_delete_last(message: types.Message):
    """Удалить последнюю транзакцию."""
    telegram_id = message.from_user.id

    try:
        tx = await api.delete_last_transaction(telegram_id)
        text = "🗑 Удалена последняя операция:\n\n" + format_transaction(tx)
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ {e}")


# ==========================================
# /edit_last — изменить последнюю
# ==========================================

@router.message(Command("edit_last"))
async def cmd_edit_last(message: types.Message, state: FSMContext):
    """Начало редактирования последней транзакции."""
    await message.answer(
        "✏️ Что изменить?\n\n"
        "Напиши:\n"
        "• Новую сумму (например: 2500)\n"
        "• Новое описание (например: Кафе с коллегами)\n"
        "• Или отправь '-' для отмены"
    )
    await state.set_state(EditLastStates.waiting_for_new_value)


@router.message(EditLastStates.waiting_for_new_value)
async def process_edit_last(message: types.Message, state: FSMContext):
    """Обработка редактирования."""
    value = message.text.strip()

    if value == "-":
        await message.answer("Отменено.")
        await state.clear()
        return

    telegram_id = message.from_user.id

    new_amount = None
    new_description = None

    try:
        new_amount = float(value.replace(",", "."))
    except ValueError:
        new_description = value

    try:
        tx = await api.edit_last_transaction(
            telegram_id=telegram_id,
            new_amount=new_amount,
            new_description=new_description,
        )
        text = "✅ Последняя операция изменена:\n\n" + format_transaction(tx)
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

    await state.clear()
