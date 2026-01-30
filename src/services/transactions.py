from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pandas as pd
from sqlmodel import select

from src.db import get_session
from src.models import Transaction, Account, Category, Owner, Payer, SplitMode


def create_transaction(
    dt: date,
    amount: float,
    description: str,
    account_id: int,
    category_id: int,
    owner: str = "petrus",
    paid_by: str = "petrus",
    split_mode: str = "none",
    card_label: Optional[str] = None,
) -> None:
    with get_session() as session:
        session.add(
            Transaction(
                date=dt,
                amount=float(amount),
                description=description,
                account_id=int(account_id),
                category_id=int(category_id),
                owner=Owner(owner),
                paid_by=Payer(paid_by),
                split_mode=SplitMode(split_mode),
                card_label=card_label,
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()


def update_transaction(t_id: int, **fields) -> None:
    with get_session() as session:
        tx = session.get(Transaction, t_id)
        if not tx:
            return

        for k, v in fields.items():
            if k == "owner":
                v = Owner(v)
            elif k == "paid_by":
                v = Payer(v)
            elif k == "split_mode":
                v = SplitMode(v)
            setattr(tx, k, v)

        tx.updated_at = datetime.utcnow()
        session.add(tx)
        session.commit()


def delete_transaction(t_id: int) -> None:
    with get_session() as session:
        tx = session.get(Transaction, t_id)
        if not tx:
            return
        session.delete(tx)
        session.commit()


def list_transactions(
    start: Optional[date] = None,
    end: Optional[date] = None,
    owner: Optional[str] = None,
    account_id: Optional[int] = None,
) -> pd.DataFrame:
    with get_session() as session:
        q = (
            select(Transaction, Account, Category)
            .join(Account, Transaction.account_id == Account.id)
            .join(Category, Transaction.category_id == Category.id)
        )

        if start:
            q = q.where(Transaction.date >= start)
        if end:
            q = q.where(Transaction.date <= end)
        if owner and owner != "todos":
            q = q.where(Transaction.owner == Owner(owner))
        if account_id:
            q = q.where(Transaction.account_id == account_id)

        rows = session.exec(q.order_by(Transaction.date.desc(), Transaction.id.desc())).all()

    data = []
    for tx, acc, cat in rows:
        data.append(
            {
                "id": tx.id,
                "date": tx.date,
                "amount": tx.amount,
                "description": tx.description,
                "account": acc.name,
                "account_id": acc.id,
                "account_type": acc.type.value if hasattr(acc.type, "value") else str(acc.type),
                "category": cat.name,
                "category_type": cat.type,
                "category_id": cat.id,
                "owner": tx.owner.value if hasattr(tx.owner, "value") else str(tx.owner),
                "paid_by": tx.paid_by.value if hasattr(tx.paid_by, "value") else str(tx.paid_by),
                "split_mode": tx.split_mode.value if hasattr(tx.split_mode, "value") else str(tx.split_mode),
                "card_label": tx.card_label or "",
            }
        )

    return pd.DataFrame(data)


def current_balance_for_account(account_id: int) -> float:
    with get_session() as session:
        acc = session.get(Account, account_id)
        if not acc:
            return 0.0
        rows = session.exec(select(Transaction.amount).where(Transaction.account_id == account_id)).all()
        tx_sum = sum(rows) if rows else 0.0
        return float(acc.initial_balance + tx_sum)
