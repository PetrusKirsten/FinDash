from __future__ import annotations

import pandas as pd
from datetime import date

from src.services.accounts import list_accounts
from src.services.transactions import list_transactions


def balances_by_account(include_credit: bool = True, as_of: date | None = None) -> pd.DataFrame:
    accs = list_accounts()

    # puxa todas transações e filtra por data se as_of foi passado
    txs = list_transactions()
    if not txs.empty and as_of is not None and "date" in txs.columns:
        txs = txs[txs["date"] <= as_of]

    out = []
    for a in accs:
        acc_type = a.type.value if hasattr(a.type, "value") else str(a.type)

        if not include_credit and acc_type == "credit":
            continue

        if txs.empty:
            bal = float(a.initial_balance)
        else:
            bal = float(a.initial_balance + txs.loc[txs["account_id"] == a.id, "amount"].sum())

        out.append({"account": a.name, "type": acc_type, "balance": bal})

    return pd.DataFrame(out).sort_values("account") if out else pd.DataFrame()


def cash_total_balance(as_of: date | None = None) -> float:
    df = balances_by_account(include_credit=False, as_of=as_of)
    if df.empty:
        return 0.0
    return float(df["balance"].sum())


def credit_outstanding_by_account(as_of: date | None = None) -> pd.DataFrame:
    df = balances_by_account(include_credit=True, as_of=as_of)
    if df.empty:
        return pd.DataFrame()

    credit_df = df[df["type"] == "credit"].copy()
    if credit_df.empty:
        return pd.DataFrame()

    credit_df["em_aberto"] = credit_df["balance"].apply(lambda x: max(0.0, -float(x)))
    credit_df["a_favor"] = credit_df["balance"].apply(lambda x: max(0.0, float(x)))

    return credit_df[["account", "em_aberto", "a_favor"]].sort_values("account")


def total_credit_outstanding(as_of: date | None = None) -> float:
    df = credit_outstanding_by_account(as_of=as_of)
    if df.empty:
        return 0.0
    return float(df["em_aberto"].sum())
