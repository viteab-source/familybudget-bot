"""
Утилиты для форматирования сообщений Telegram.
"""

def truncate_message(text: str, max_length: int = 4096) -> list:
    """
    Разбивает длинное сообщение на части для Telegram.
    Telegram лимит: 4096 символов на сообщение.
    
    Примеры:
        >>> truncate_message("Hello", 10)
        ["Hello"]
        
        >>> truncate_message("A" * 5000, 100)
        ["A" * 100, "A" * 100, ...]
    """
    if len(text) <= max_length:
        return [text]
    
    parts = []
    current = ""
    
    for line in text.split("\n"):
        # Если добавление строки превысит лимит
        if len(current) + len(line) + 1 > max_length:
            if current:
                parts.append(current)
            current = line
        else:
            current += "\n" + line if current else line
    
    if current:
        parts.append(current)
    
    return parts


def format_error_message(error: str, max_length: int = 200) -> str:
    """
    Сокращает ошибку до 200 символов для красивого вывода.
    
    Примеры:
        >>> format_error_message("Error: " + "A" * 300)
        "Error: AAA... (сокращено)"
    """
    if len(error) > max_length:
        return error[:max_length-3] + "..."
    return error
