from __future__ import annotations

from sqlmodel import select
from src.db import get_session
from src.models import Category

def list_categories() -> list[Category]:
    with get_session() as session:
        return list(session.exec(select(Category).order_by(Category.type, Category.name)).all())

def create_category(name: str, typ: str) -> None:
    with get_session() as session:
        session.add(Category(name=name, type=typ))
        session.commit()

def get_category_id_by_name(name: str) -> int | None:
    with get_session() as session:
        cat = session.exec(select(Category).where(Category.name == name)).first()
        return cat.id if cat else None
