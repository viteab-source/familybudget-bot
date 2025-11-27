import json
import os
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")


def get_model_uri() -> str:
    """URI модели YandexGPT."""
    if not YANDEX_FOLDER_ID:
        raise RuntimeError("YANDEX_FOLDER_ID не задан. Проверь .env")
    return f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite/latest"


# --- Нормализация категорий после ответа модели ---


def normalize_category(raw: str | None) -> str | None:
    """
    Приводим категорию к аккуратному виду:
    - убираем лишние пробелы
    - приводим к единому набору категорий (Продукты, Химия, Игрушки и т.п.)
    """
    if not raw:
        return None

    s = raw.strip().lower()

    # Базовые маппинги по ключевым словам
    if any(x in s for x in ["пятёрочк", "дикси", "магнит", "лента", "ашан", "перекр", "вкусвилл", "окей"]):
        # по умолчанию считаем это продуктовым магазином
        # дальше конкретику (корм, химия и т.п.) модель попытается отразить
        # в описании, но категория будет "Продукты"
        return "Продукты"

    # Корм для животных
    if any(x in s for x in ["корм", "кошк", "кот", "собак", "животн"]):
        return "Корм для животных"

    # Алкоголь
    if any(x in s for x in ["алкогол", "пиво", "вино", "водка", "коньяк", "сидр", "шампан"]):
        return "Алкоголь"

    # Бытовая химия
    if any(x in s for x in ["химия", "моющ", "порошок", "уборка", "средство для", "clean", "domestos", "fairy"]):
        return "Химия"

    # Игрушки / дети
    if any(x in s for x in ["игрушк", "лего", "конструктор", "кукла", "машинка"]) or "дет" in s:
        return "Дети / Игрушки"

    # Кафе / рестораны
    if any(x in s for x in ["кафе", "ресторан", "бар", "кофейня", "coffee", "kfc", "макдональдс", "макдоналдс", "макдак", "burger king", "бургеркинг"]):
        return "Кафе и рестораны"

    # Такси / транспорт
    if any(x in s for x in ["такси", "yandex go", "яндекс.такси", "яндекс такси", "uber"]):
        return "Такси"

    if any(x in s for x in ["метро", "транспорт", "проезд", "трамвай", "автобус"]):
        return "Транспорт"

    # Авто
    if any(x in s for x in ["заправк", "бензин", "топливо", "gas", "shell", "лукойл", "газпромнефть"]):
        return "Авто / Топливо"

    # Одежда / обувь
    if any(x in s for x in ["одежд", "обув", "зара", "zara", "uniqo", "uniqlo", "hm", "h&m"]):
        return "Одежда и обувь"

    # Общая "продукты", если модель так уже и вернула:
    if "продукт" in s or "еда" in s or s in ["продукты", "магазин"]:
        return "Продукты"

    # Чистим базовый вариант: первая буква заглавная, остальное как есть
    return s.capitalize()


def parse_text_to_transaction(text: str) -> dict:
    """
    Вызывает YandexGPT, чтобы из произвольного текста сделать JSON транзакции.
    Возвращает dict с ключами:
    - amount (float)
    - currency (str)
    - category (str | None)
    - description (str | None)
    - date (str в формате YYYY-MM-DD, если удалось определить)
    """

    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        raise RuntimeError("YANDEX_API_KEY или YANDEX_FOLDER_ID не заданы. Проверь .env")

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    today = datetime.utcnow().date()
    today_str = today.strftime("%Y-%m-%d")
    current_year = today.year

    # ВАЖНО: здесь мы описываем, какие категории хотим видеть
    system_prompt = f"""
Ты помощник по семейным финансам.

Твоя задача — из короткого человеческого текста про покупку или расход
сделать СТРОГО один JSON-объект с полями:

{{
  "amount": число (в рублях или евро, без текста),
  "currency": "RUB" или "EUR",
  "category": "строка категории на русском",
  "description": "краткое описание магазина/расхода",
  "date": "YYYY-MM-DD"
}}

Текущая дата: {today_str}, текущий год: {current_year}.

Важные правила по сумме:

- Сумма может быть написана ЦИФРАМИ ("2435", "2 435₽") или СЛОВАМИ
  на русском ("две тысячи четыреста тридцать пять рублей").
- Всегда переводи сумму в число (float), например 2435.0.
- Если в тексте несколько сумм, выбери основную сумму покупки.

Рекомендуемый набор категорий (используй их, когда подходит по смыслу):

- "Продукты" — еда, покупки в супермаркетах и продуктовых магазинах
  ("Пятёрочка", "Магнит", "Лента", "Ашан", "Перекрёсток",
   "Дикси", "Окей", "ВкусВилл" и т.п.).
- "Химия" — бытовая химия (порошок, средства для уборки, мытья посуды
  и т.п.).
- "Корм для животных" — корм, наполнители и т.п. для кошек, собак
  и других животных.
- "Алкоголь" — пиво, вино, водка, коньяк и т.п.
- "Дети / Игрушки" — игрушки, детские товары, конструкторы, куклы и т.п.
- "Кафе и рестораны" — кафе, рестораны, фастфуд, доставка еды.
- "Такси" — поездки на такси (Яндекс.Такси, Yandex Go, Uber).
- "Транспорт" — метро, автобус, трамвай, проездные билеты.
- "Авто / Топливо" — заправка, бензин, обслуживание автомобиля.
- "Одежда и обувь" — покупки одежды, обуви и аксессуаров.
- Если не подходит ничего — выбирай более общую категорию по смыслу,
  например "Другое" или "Дом".

Отдельные подсказки:

- Если в тексте упоминается продуктовый магазин
  ("Пятёрочка", "Магнит", "Лента", "Ашан", "Перекрёсток", "Дикси",
   "Окей", "ВкусВилл"), то чаще всего категория "Продукты",
  но если явно указано "корм для кошки", "корм для собаки" —
  можно выбрать "Корм для животных".
- Если указано что-то из бытовой химии (порошок, средство для уборки),
  выбирай "Химия".
- Если указано, что покупали игрушку, конструктор и т.п. — "Дети / Игрушки".
- Если есть слова "пиво", "вино", "водка", "алкоголь" — "Алкоголь".

Дата:

- date — в формате YYYY-MM-DD.
- Если дата явно указана ("26.09.2024", "2024-09-26") — используй её,
  корректно распарсив.
- Если есть слова "сегодня", "вчера", "позавчера" — рассчитай дату
  относительно сегодняшней даты {today_str}.
- Если ничего не сказано про дату, используй сегодняшнюю дату {today_str}.

Формат ответа:

- Всегда возвращай ТОЛЬКО JSON, без пояснений и без лишнего текста.
- amount — число, а не строка.
- currency определи по тексту (₽, RUB → "RUB"; €, EUR → "EUR";
  если ничего не сказано — по умолчанию "RUB").
- category — используй один из предложенных вариантов, если это возможно.
"""

    payload = {
        "modelUri": get_model_uri(),
        "completionOptions": {
            "stream": False,
            "temperature": 0.1,
            "maxTokens": 200,
        },
        "messages": [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": text},
        ],
    }

    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "x-folder-id": YANDEX_FOLDER_ID,
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # YandexGPT обычно возвращает текст в поле result.alternatives[0].message.text
    raw_text = data["result"]["alternatives"][0]["message"]["text"]

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        cleaned = raw_text.strip().strip("```").strip()
        parsed = json.loads(cleaned)

    # Нормализуем категорию
    parsed_category = parsed.get("category")
    parsed["category"] = normalize_category(parsed_category)

    return parsed
