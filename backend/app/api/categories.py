"""
api/categories.py — Эндпоинты для категорий.
GET /categories — список категорий
POST /categories — создать категорию
POST /categories/rename — переименовать
POST /categories/merge — объединить две категории
DELETE /categories — удалить категорию
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..deps import get_or_create_user_and_household


router = APIRouter()


@router.get("/categories", response_model=List[schemas.CategoryRead])
def list_categories(
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Список категорий для текущей семьи.
    
    Дополнительно:
    - берём все уникальные category из транзакций этой семьи;
    - для тех, которых ещё нет в таблице categories, создаём записи;
    - затем возвращаем полный список категорий.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    # 1) Уже существующие категории в таблице categories
    existing_q = db.query(models.Category.name).filter(
        models.Category.household_id == household.id
    )

    existing_names = {
        (name or "").strip().lower()
        for (name,) in existing_q.all()
        if name
    }

    # 2) Уникальные названия категорий из транзакций
    tx_categories = (
        db.query(models.Transaction.category)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.category.isnot(None),
            models.Transaction.category != "",
        )
        .distinct()
        .all()
    )

    created = False
    for (cat_name,) in tx_categories:
        if not cat_name:
            continue

        normalized = cat_name.strip().lower()
        if not normalized or normalized in existing_names:
            continue

        db_cat = models.Category(
            household_id=household.id,
            name=cat_name.strip(),
        )
        db.add(db_cat)
        existing_names.add(normalized)
        created = True

    if created:
        db.commit()

    # 3) Финальный список категорий
    categories = (
        db.query(models.Category)
        .filter(models.Category.household_id == household.id)
        .order_by(
            models.Category.sort_order.is_(None),  # None в конец
            models.Category.sort_order,
            models.Category.name,
        )
        .all()
    )

    return categories


@router.post("/categories", response_model=schemas.CategoryRead)
def create_category(
    category: schemas.CategoryCreate,
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Создать новую категорию для текущей семьи.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    name = category.name.strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail="Название категории не может быть пустым",
        )

    # Проверяем, нет ли уже такой категории
    existing = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == name,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Категория '{name}' уже существует",
        )

    db_cat = models.Category(
        household_id=household.id,
        name=name,
        parent_id=category.parent_id,
        sort_order=category.sort_order,
    )

    db.add(db_cat)
    db.commit()
    db.refresh(db_cat)

    return db_cat


@router.post("/categories/rename", response_model=schemas.CategoryRead)
def rename_category(
    body: dict,  # {"old_name": "Продукты", "new_name": "Еда"}
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Переименовать категорию и обновить все транзакции.
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    old_name = (body.get("old_name") or "").strip()
    new_name = (body.get("new_name") or "").strip()

    if not old_name or not new_name:
        raise HTTPException(
            status_code=400,
            detail="old_name и new_name не могут быть пустыми",
        )

    # Ищем категорию
    category = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == old_name,
        )
        .first()
    )

    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    # Проверяем, нет ли уже категории с новым именем
    existing_new = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == new_name,
        )
        .first()
    )

    if existing_new and existing_new.id != category.id:
        raise HTTPException(
            status_code=409,
            detail=f"Категория '{new_name}' уже существует",
        )

    # Переименовываем
    category.name = new_name
    db.commit()

    # Обновляем транзакции (старое строковое поле category)
    db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id,
        models.Transaction.category == old_name,
    ).update({models.Transaction.category: new_name})
    db.commit()

    db.refresh(category)
    return category


@router.post("/categories/merge")
def merge_categories(
    body: dict,  # {"from_category": "Еда", "to_category": "Продукты"}
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Объединить две категории:
    - перенести все транзакции из 'from_category' в 'to_category'
    - удалить 'from_category'
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    from_cat_name = (body.get("from_category") or "").strip()
    to_cat_name = (body.get("to_category") or "").strip()

    if not from_cat_name or not to_cat_name:
        raise HTTPException(
            status_code=400,
            detail="from_category и to_category не могут быть пустыми",
        )

    from_cat = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == from_cat_name,
        )
        .first()
    )

    to_cat = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == to_cat_name,
        )
        .first()
    )

    if not from_cat or not to_cat:
        raise HTTPException(status_code=404, detail="Одна из категорий не найдена")

    if from_cat.id == to_cat.id:
        raise HTTPException(
            status_code=400,
            detail="Нельзя объединить категорию саму с собой",
        )

    # Переносим все транзакции
    db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id,
        models.Transaction.category == from_cat_name,
    ).update({models.Transaction.category: to_cat_name})

    db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id,
        models.Transaction.category_id == from_cat.id,
    ).update({models.Transaction.category_id: to_cat.id})

    # Удаляем категорию
    db.delete(from_cat)
    db.commit()

    return {"status": "ok", "message": f"Категория '{from_cat_name}' объединена с '{to_cat_name}'"}


@router.delete("/categories")
def delete_category(
    name: str = Query(..., description="Название категории"),
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Удалить категорию (только если нет транзакций).
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    cat_name = name.strip()
    if not cat_name:
        raise HTTPException(
            status_code=400,
            detail="Название не может быть пустым",
        )

    category = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == cat_name,
        )
        .first()
    )

    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    # Проверяем наличие транзакций
    tx_count = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.category_id == category.id,
        )
        .count()
    )

    if tx_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Категория содержит {tx_count} транзакций, удаление невозможно",
        )

    db.delete(category)
    db.commit()

    return {"status": "ok", "message": f"Категория '{cat_name}' удалена"}
