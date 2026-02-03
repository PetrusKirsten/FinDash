from __future__ import annotations

from sqlmodel import select
from src.db import get_session
from src.models import Account, Category

DEFAULT_ACCOUNTS = [
    ("BB | PP",             "petrus", "checking",  0.0),
    ("Santander | PP",      "petrus", "checking",  0.0),
    ("Santander | Crédito", "petrus", "credit",    0.0),
]

# categorias exatamente como na planilha + "Ajuste de saldo"
DEFAULT_CATEGORIES = [
    ("Alimentação 🍽️",     "expense"),
    ("Juros 📈",           "income"),
    ("Moradia 🏠",         "expense"),
    ("Outros 📦",          "expense"),
    ("Pagamento 💵",       "income"),
    ("Pessoal 👤",         "expense"),
    ("Pgto. de fatura 💳", "transfer"),
    ("Transporte 🚗",      "expense"),
    ("Casamento 💍",       "expense"),
    ("Presentes 🎁",       "expense"),
    ("Ratos 🐀",           "expense"),
    ("Ajuste de saldo ⚖️", "transfer"),
]

def seed_defaults() -> None:
    with get_session() as session:
        has_accounts = session.exec(select(Account).limit(1)).first() is not None
        has_categories = session.exec(select(Category).limit(1)).first() is not None

        if not has_accounts:
            for name, owner, typ, bal in DEFAULT_ACCOUNTS:
                session.add(Account(name=name, owner=owner, type=typ, initial_balance=bal))

        if not has_categories:
            for name, typ in DEFAULT_CATEGORIES:
                session.add(Category(name=name, type=typ))

        session.commit()
