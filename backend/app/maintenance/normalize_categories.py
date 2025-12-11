# backend/app/maintenance/normalize_categories.py

"""
Скрипт для нормализации категорий.

Что делает:
1. Для каждой семьи (household_id) ищет категории,
   которые отличаются только регистром имени:
   - "Такси", "такси", "ТАКСИ" → остаётся одна категория.
2. Все транзакции и бюджеты переводит на "каноническую"
   категорию, дубликаты удаляет.

⚠️ Скрипт НЕ меняет схему БД, только данные.
Запускается вручную из консоли.
"""

from collections import defaultdict

from sqlalchemy.orm import Session

from ..db import SessionLocal
from .. import models


def choose_canonical_category(categories: list[models.Category]) -> models.Category:
    """
    Выбираем "главную" категорию из группы дубликатов.

    Принцип:
    - стараемся оставить более "красивое" имя:
      * с первой заглавной буквой
      * в формате Title Case
    - при равенстве берём категорию с минимальным id
    """
    def score(cat: models.Category) -> tuple[int, int]:
        name = (cat.name or "").strip()
        nice_score = 0
        if name and name[0].isupper():
            nice_score += 1
        if name == name.title():
            nice_score += 1
        # минус, чтобы сначала шли более "красивые"
        return (-nice_score, cat.id)

    return sorted(categories, key=score)[0]


def merge_case_insensitive_duplicates(session: Session) -> int:
    """
    Ищет и сливает дубликаты категорий, отличающиеся только регистром.

    Возвращает количество групп, в которых были изменения.
    """
    categories: list[models.Category] = (
        session.query(models.Category)
        .order_by(models.Category.household_id, models.Category.id)
        .all()
    )

    # Ключ: (household_id, name_lower) -> список категорий
    groups: dict[tuple[int, str], list[models.Category]] = defaultdict(list)
    for cat in categories:
        name = (cat.name or "").strip()
        if not name:
            continue
        key = (cat.household_id, name.lower())
        groups[key].append(cat)

    changed_groups = 0

    for (household_id, norm_name), cats in groups.items():
        if len(cats) <= 1:
            continue

        canonical = choose_canonical_category(cats)
        duplicates = [c for c in cats if c.id != canonical.id]

        dup_ids = [c.id for c in duplicates]

        print(
            f"\n[household_id={household_id}] нормализуем категории с именем '{norm_name}':"
        )
        for c in cats:
            mark = "*" if c.id == canonical.id else " "
            print(f"  {mark} id={c.id} name='{c.name}'")

        # Переносим транзакции
        tx_update_count = (
            session.query(models.Transaction)
            .filter(models.Transaction.category_id.in_(dup_ids))
            .update(
                {
                    models.Transaction.category_id: canonical.id,
                    models.Transaction.category: canonical.name,
                },
                synchronize_session=False,
            )
        )

        # Переносим бюджеты по категориям
        budget_update_count = (
            session.query(models.CategoryBudget)
            .filter(models.CategoryBudget.category_id.in_(dup_ids))
            .update(
                {models.CategoryBudget.category_id: canonical.id},
                synchronize_session=False,
            )
        )

        print(
            f"  → перевели {tx_update_count} транзакций "
            f"и {budget_update_count} бюджетов на категорию id={canonical.id}"
        )

        # Удаляем дубликаты категорий
        for dup in duplicates:
            session.delete(dup)
            print(f"  × удалили категорию id={dup.id} name='{dup.name}'")

        changed_groups += 1

    return changed_groups


def main() -> None:
    session = SessionLocal()
    try:
        print("=== Запуск нормализации категорий (дубликаты по регистру) ===")
        changed = merge_case_insensitive_duplicates(session)
        if changed == 0:
            print("Дубликатов по регистру не найдено – изменений нет.")
        else:
            print(f"\nГотово. Изменения в {changed} группах категорий.")
        session.commit()
    except Exception as e:
        print(f"\nОШИБКА, откатываем транзакцию: {e}")
        session.rollback()
        raise
    finally:
        session.close()
        print("Сессия БД закрыта.")


if __name__ == "__main__":
    main()
