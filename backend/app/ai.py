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


def parse_text_to_transaction(text: str) -> dict:
    """
    Вызывает YandexGPT, чтобы из произвольного текста сделать JSON транзакции.
    Возвращает dict с ключами:
    - amount (float)
    - currency (str)
    - category (str | None)
    - description (str | None)
    - date (str в формате YYYY-MM-DD)
    """
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        raise RuntimeError("YANDEX_API_KEY или YANDEX_FOLDER_ID не заданы. Проверь .env")

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    today = datetime.utcnow().date()
    today_str = today.strftime("%Y-%m-%d")
    current_year = today.year

    system_prompt = f"""
Сегодняшняя дата: {today_str}.
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

Правила по сумме:

- Сумма может быть написана ЦИФРАМИ ("2435", "2 435₽") или СЛОВАМИ
  на русском ("две тысячи четыреста тридцать пять рублей").
- Ты ОБЯЗАН перевести сумму в число (float), например 2435.0.
- НИКОГДА не ставь 0.0, если по тексту видно, что была покупка.
  Если сомневаешься, всё равно оцени сумму по тексту.

Правила по дате:

- Если в тексте нет явной даты и нет слов "вчера", "сегодня", "позавчера" —
  используй сегодняшнюю дату ({today_str}).
- Если есть относительные слова ("вчера", "позавчера" и т.п.) —
  рассчитай фактическую дату относительно сегодняшнего дня ({today_str}).
- Если указан день и месяц без года ("26 сентября") — используй год {current_year}.
- Если явно указан год — используй его.

Остальные требования:

- Всегда возвращай ТОЛЬКО JSON, без пояснений и без лишнего текста.
- amount — число, а не строка (2435.0).
- category — короткая фраза: "Продукты", "Дети", "Такси", "Кафе", "Авто" и т.п.
- description — название магазина или что купили: "Пятёрочка", "садик", "Яндекс.Такси".
- currency определи по тексту (₽, RUB → "RUB"; €, EUR → "EUR"; если ничего не сказано — по умолчанию "RUB").
- date — в формате YYYY-MM-DD.
"""

    # Несколько ПРИМЕРОВ для модели (few-shot),
    # чтобы она точно научилась понимать сумму словами.
    example_1_user = "Пятёрочка, продукты, 2435₽ вчера"
    example_1_assistant = json.dumps(
        {
            "amount": 2435.0,
            "currency": "RUB",
            "category": "Продукты",
            "description": "Пятёрочка",
            "date": today_str,  # здесь не важно, главное показать формат
        },
        ensure_ascii=False,
    )

    example_2_user = "Перекрёсток, продукты, две тысячи четыреста тридцать пять рублей, вчера"
    example_2_assistant = json.dumps(
        {
            "amount": 2435.0,
            "currency": "RUB",
            "category": "Продукты",
            "description": "Перекрёсток",
            "date": today_str,
        },
        ensure_ascii=False,
    )

    payload = {
        "modelUri": get_model_uri(),
        "completionOptions": {
            "stream": False,
            "temperature": 0.1,
            "maxTokens": 200,
        },
        "messages": [
            {"role": "system", "text": system_prompt},

            # Пример 1: сумма цифрами
            {"role": "user", "text": example_1_user},
            {"role": "assistant", "text": example_1_assistant},

            # Пример 2: сумма словами
            {"role": "user", "text": example_2_user},
            {"role": "assistant", "text": example_2_assistant},

            # Твой реальный текст
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

    raw_text = data["result"]["alternatives"][0]["message"]["text"]

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        cleaned = raw_text.strip().strip("```").strip()
        parsed = json.loads(cleaned)

    return parsed
