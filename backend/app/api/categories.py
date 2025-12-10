"""
Эндпоинты для работы с категориями расходов/доходов.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..deps import get_or_create_user_and_household

router = APIRouter()


@router.get("", response_model=List[schemas.CategoryRead])
def list_categories(
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
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

    # 2) Уникальные строковые категории из транзакций (старое поле)
    tx_categories_q = (
        db.query(models.Transaction.category)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.category.isnot(None),
        )
        .distinct()
    )
    tx_categories = {cat.strip() for (cat,) in tx_categories_q.all() if cat and cat.strip()}

    # 3) Создаём категории, которых нет в таблице
    for cat_name in tx_categories:
        if cat_name.lower() not in existing_names:
            new_cat = models.Category(
                household_id=household.id,
                name=cat_name,
            )
            db.add(new_cat)
            existing_names.add(cat_name.lower())

    db.commit()

    # 4) Возвращаем все категории семьи
    categories = (
        db.query(models.Category)
        .filter(models.Category.household_id == household.id)
        .order_by(models.Category.name)
        .all()
    )

    return categories


@router.post("", response_model=schemas.CategoryRead)
def create_category(
    body: schemas.CategoryCreate,
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Создать новую категорию для текущей семьи.
    
    Пример:
    POST /categories?telegram_id=123456789
    Body: {"name": "Продукты"}
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    name = (body.name or "").strip()
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
            status_code=400,
            detail=f"Категория «{name}» уже существует",
        )

    category = models.Category(
        household_id=household.id,
        name=name,
        parent_id=body.parent_id,
        sort_order=body.sort_order,
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    return category


@router.post("/rename", response_model=schemas.CategoryRead)
def rename_category(
    old_name: str = Query(..., description="Старое название категории"),
    new_name: str = Query(..., description="Новое название категории"),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Переименовать категорию по имени.
    
    Также обновляет старое строковое поле Transaction.category
    для всех транзакций этой семьи.
    
    Пример:
    POST /categories/rename?old_name=Игрушки&new_name=Детям&telegram_id=123456789
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    old_name = old_name.strip()
    new_name = new_name.strip()

    if not old_name or not new_name:
        raise HTTPException(
            status_code=400,
            detail="Старое и новое название не могут быть пустыми",
        )

    # Ищем категорию по старому имени
    category = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == old_name,
        )
        .first()
    )

    if not category:
        raise HTTPException(
            status_code=404,
            detail=f"Категория «{old_name}» не найдена",
        )

    # Проверяем, нет ли уже категории с новым именем
    existing = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == new_name,
        )
        .first()
    )

    if existing and existing.id != category.id:
        raise HTTPException(
            status_code=400,
            detail=f"Категория «{new_name}» уже существует",
        )

    # Переименовываем
    category.name = new_name

    # Также обновляем старое строковое поле в транзакциях
    db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id,
        models.Transaction.category == old_name,
    ).update({"category": new_name})

    db.commit()
    db.refresh(category)

    return category


@router.post("/merge", response_model=schemas.CategoryRead)
def merge_categories(
    source_name: str = Query(..., description="Исходная категория (удаляется)"),
    target_name: str = Query(..., description="Целевая категория (остаётся)"),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Объединить две категории: source → target.
    
    - Все транзакции из source переносятся в target
    - source удаляется
    
    Пример:
    POST /categories/merge?source_name=Игрушки&target_name=Детям&telegram_id=123456789
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    source_name = source_name.strip()
    target_name = target_name.strip()

    if not source_name or not target_name:
        raise HTTPException(
            status_code=400,
            detail="Названия категорий не могут быть пустыми",
        )

    if source_name == target_name:
        raise HTTPException(
            status_code=400,
            detail="Исходная и целевая категория не могут быть одинаковыми",
        )

    # Ищем обе категории
    source_cat = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == source_name,
        )
        .first()
    )

    if not source_cat:
        raise HTTPException(
            status_code=404,
            detail=f"Категория «{source_name}» не найдена",
        )

    target_cat = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == target_name,
        )
        .first()
    )

    if not target_cat:
        raise HTTPException(
            status_code=404,
            detail=f"Категория «{target_name}» не найдена",
        )

    # Переносим все транзакции из source в target
    # 1) category_id
    db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id,
        models.Transaction.category_id == source_cat.id,
    ).update({"category_id": target_cat.id})

    # 2) старое строковое поле category
    db.query(models.Transaction).filter(
        models.Transaction.household_id == household.id,
        models.Transaction.category == source_name,
    ).update({"category": target_name})

    # Удаляем исходную категорию
    db.delete(source_cat)
    db.commit()
    db.refresh(target_cat)

    return target_cat


@router.post("/delete", response_model=schemas.CategoryRead)
def delete_category(
    name: str = Query(..., description="Название категории для удаления"),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Удалить категорию по имени (если по ней нет операций).
    
    Если есть транзакции — вернёт ошибку.
    В этом случае нужно использовать /categories/merge.
    
    Пример:
    POST /categories/delete?name=Игрушки&telegram_id=123456789
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    name = name.strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail="Название категории не может быть пустым",
        )

    # Ищем категорию
    category = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == name,
        )
        .first()
    )

    if not category:
        raise HTTPException(
            status_code=404,
            detail=f"Категория «{name}» не найдена",
        )

    # Проверяем, есть ли транзакции по этой категории
    has_transactions = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.household_id == household.id,
            models.Transaction.category_id == category.id,
        )
        .first()
    ) is not None

    if has_transactions:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Нельзя удалить категорию «{name}», по ней есть операции. "
                f"Используй /categories/merge для объединения с другой категорией."
            ),
        )

    db.delete(category)
    db.commit()

    return category



@router.post("/feedback")
def log_category_feedback(
    body: dict,
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Логирование обратной связи по категориям (для обучения AI).
    
    Когда пользователь меняет категорию, предложенную AI,
    мы сохраняем этот выбор для анализа и улучшения промптов.
    
    Пример:
    POST /categories/feedback?telegram_id=123456789
    Body: {
        "transaction_id": 42,
        "user_selected_category": "Продукты"
    }
    """
    from .. import models
    
    user, household = get_or_create_user_and_household(db, telegram_id)
    
    transaction_id = body.get("transaction_id")
    user_selected_category = body.get("user_selected_category", "").strip()
    
    if not user_selected_category:
        raise HTTPException(status_code=400, detail="user_selected_category required")
    
    # Получаем транзакцию для извлечения данных
    original_text = None
    ai_category = None
    
    if transaction_id:
        tx = db.query(models.Transaction).filter(
            models.Transaction.id == transaction_id,
            models.Transaction.household_id == household.id,
        ).first()
        
        if tx:
            original_text = tx.description
            ai_category = tx.category
    
    # Создаём запись обратной связи
    feedback = models.CategoryFeedback(
        household_id=household.id,
        user_id=user.id if user else None,
        transaction_id=transaction_id,
        original_text=original_text,
        ai_category=ai_category,
        user_selected_category=user_selected_category,
    )
    
    db.add(feedback)
    db.commit()
    
    return {"status": "ok", "message": "Feedback logged"}
