from __future__ import annotations

from sqlmodel import select

from src.db import get_session
from src.models import Account, Owner, AccountType


def list_accounts() -> list[Account]:
    with get_session() as session:
        return list(session.exec(select(Account).order_by(Account.name)).all())


def create_account(name: str, owner: str, typ: str, initial_balance: float = 0.0) -> None:
    with get_session() as session:
        session.add(
            Account(
                name=name.strip(),
                owner=Owner(owner),
                type=AccountType(typ),
                initial_balance=float(initial_balance),
            )
        )
        session.commit()


def update_account_initial_balance(account_id: int, new_initial_balance: float) -> None:
    # (a gente não vai usar no teu fluxo, porque vamos ajustar saldo por transação)
    with get_session() as session:
        acc = session.get(Account, account_id)
        if not acc:
            return
        acc.initial_balance = float(new_initial_balance)
        session.add(acc)
        session.commit()


def get_account_by_name(name: str) -> Account | None:
    with get_session() as session:
        return session.exec(select(Account).where(Account.name == name)).first()
