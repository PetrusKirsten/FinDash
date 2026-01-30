from __future__ import annotations

import pandas as pd
from src.services.accounts import list_accounts
from src.services.transactions import list_transactions

def balances_by_account() -> pd.DataFrame:
    accs = list_accounts()
    txs = list_transactions()

    out = []
    if txs.empty:
        for a in accs:
            out.append({
                "account": a.name,
                "account_id": a.id,
                "type": a.type.value,
                "balance": float(a.initial_balance),
            })
        return pd.DataFrame(out).sort_values("account")

    for a in accs:
        bal = float(a.initial_balance + txs.loc[txs["account_id"] == a.id, "amount"].sum())
        out.append({
            "account": a.name,
            "account_id": a.id,
            "type": a.type.value,
            "balance": bal,
        })

    return pd.DataFrame(out).sort_values("account")

def total_balance() -> float:
    df = balances_by_account()
    if df.empty:
        return 0.0
    return float(df["balance"].sum())
