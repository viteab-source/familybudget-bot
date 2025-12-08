"""
app/ai.py — ИСПРАВЛЕННАЯ ВЕРСИЯ (с fallback парсингом)
"""

import json
import os
import re
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
    """
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        raise RuntimeError("YANDEX_API_KEY или YANDEX_FOLDER_ID не заданы. Проверь .env")

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    today = datetime.utcnow().date()
    today_str = today.strftime("%Y-%m-%d")
    current_year = today.year

    system_prompt = f"""
Ты помощник по семейным финансам.

Твоя задача — из короткого текста про расход сделать СТРОГО один JSON-объект с полями:

{{
  "amount": число (целое или с точкой),
  "currency": "RUB" или "EUR",
  "category": "одна категория",
  "candidate_categories": ["категория1", "категория2"],
  "description": "описание",
  "date": "YYYY-MM-DD"
}}

ТЕКУЩАЯ ДАТА: {today_str}

КАТЕГОРИИ:
- Продукты
- Кафе и рестораны
- Дети
- Игрушки
- Животные
- Корма для животных
- Химия и бытовое
- Личная гигиена
- Одежда и обувь
- Дом и ремонт
- Техника и электроника
- Транспорт
- Такси
- Авто
- Алкоголь
- Кофе и чай
- Медицина и аптека
- Подписки и сервисы
- Развлечения
- Подарки
- Образование
- Коммуналка
- Аренда и ипотека
- Налоги и штрафы
- Связь и интернет
- Доход: зарплата
- Доход: бизнес
- Доход: перевод
- Доход: проценты
- Другое

ВАЖНО:
1. Сумму всегда парси как число (float).
2. Категория — ОДНА из списка.
3. candidate_categories — 1-2 похожих категории, первая = category.
4. ТОЛЬКО JSON, БЕЗ ТЕКСТА.
5. JSON должен быть валидным!
"""

    payload = {
        "modelUri": get_model_uri(),
        "completionOptions": {
            "stream": False,
            "temperature": 0.1,
            "maxTokens": 300,
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

    # Получаем текст от ИИ
    raw_text = data["result"]["alternatives"][0]["message"]["text"]

    # Попытка 1: прямой парсинг JSON
    try:
        parsed = json.loads(raw_text)
        return _validate_parsed(parsed)
    except json.JSONDecodeError:
        pass

    # Попытка 2: очистка от ```json
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        # Ищем первую и последнюю тройку бэктиков
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
    
    try:
        parsed = json.loads(cleaned)
        return _validate_parsed(parsed)
    except json.JSONDecodeError:
        pass

    # Попытка 3: извлечение JSON из текста (начинается с { и кончается на })
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            parsed = json.loads(json_str)
            return _validate_parsed(parsed)
        except json.JSONDecodeError:
            pass

    # Если всё не сработало, выбросим ошибку с контекстом
    raise ValueError(
        f"Не смог распарсить JSON от ИИ. Текст от ИИ:\n{raw_text}\n\nОчищенный: {cleaned}"
    )

def _validate_parsed(parsed: dict) -> dict:
    """Проверяет и чистит распарсенный JSON"""
    if not isinstance(parsed, dict):
        raise ValueError(f"Результат не словарь: {parsed}")
    
    # Гарантируем наличие ключевых полей
    if "amount" not in parsed:
        parsed["amount"] = 0.0
    
    if "currency" not in parsed:
        parsed["currency"] = "RUB"
    
    if "category" not in parsed:
        parsed["category"] = "Другое"
    
    if "description" not in parsed:
        parsed["description"] = ""
    
    if "date" not in parsed:
        parsed["date"] = datetime.utcnow().strftime("%Y-%m-%d")
    
    if "candidate_categories" not in parsed:
        parsed["candidate_categories"] = [parsed.get("category", "Другое")]
    
    # Чистим candidate_categories
    if not isinstance(parsed["candidate_categories"], list):
        parsed["candidate_categories"] = [str(parsed["candidate_categories"])]
    
    # Гарантируем, что первый элемент = category
    cat = str(parsed.get("category", "Другое")).strip()
    candidates = [c.strip() for c in parsed["candidate_categories"] if c]
    
    if not candidates or candidates[0] != cat:
        candidates = [cat] + [c for c in candidates if c != cat]
    
    parsed["candidate_categories"] = candidates[:3]  # Макс 3
    
    return parsed
