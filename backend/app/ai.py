import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

# Модель по умолчанию — лёгкая и дешёвая, можно поменять на yandexgpt
def get_model_uri() -> str:
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
    - date (str в формате YYYY-MM-DD, если удалось определить)
    """

    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        raise RuntimeError("YANDEX_API_KEY или YANDEX_FOLDER_ID не заданы. Проверь .env")

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    system_prompt = """
Ты помощник по семейным финансам.
Твоя задача — из короткого человеческого текста про покупку или расход
сделать СТРОГО один JSON-объект с полями:

{
  "amount": число (в рублях или евро, без текста),
  "currency": "RUB" или "EUR",
  "category": "строка категории на русском",
  "description": "краткое описание магазина/расхода",
  "date": "YYYY-MM-DD"  // дата операции; если не указана, используй сегодняшнюю дату
}

Требования:

- Всегда возвращай ТОЛЬКО JSON, без пояснений и без лишнего текста.
- amount — число, а не строка (например, 2435.0).
- category — простое слово или короткая фраза: "Продукты", "Дети", "Такси", "Кафе", "Авто" и т.п.
- description — название магазина или что купили: "Пятёрочка", "садик", "Яндекс.Такси".
- currency определи по тексту (₽, RUB → "RUB"; €, EUR → "EUR"; если ничего не сказано — по умолчанию "RUB").
- date — в формате YYYY-MM-DD. Если в тексте есть слова "вчера", "сегодня", "позавчера" и т.п. —
  рассчитай правильную дату относительно сегодняшнего дня.
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
        # На всякий случай попробуем вычистить пробельчики
        cleaned = raw_text.strip().strip("```").strip()
        parsed = json.loads(cleaned)

    return parsed
