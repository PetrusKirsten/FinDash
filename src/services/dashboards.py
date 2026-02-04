from __future__ import annotations

import pandas as pd

from src.services.accounts import list_accounts
from src.services.transactions import list_transactions


def balances_by_account(include_credit: bool = True) -> pd.DataFrame:
    accs = list_accounts()
    txs = list_transactions()

    out = []

    for a in accs:
        acc_type = a.type.value if hasattr(a.type, "value") else str(a.type)

        if not include_credit and acc_type == "credit":
            continue

        if txs.empty:
            bal = float(a.initial_balance)
        else:
            bal = float(a.initial_balance + txs.loc[txs["account_id"] == a.id, "amount"].sum())

        out.append(
            {
                "account": a.name,
                "account_id": a.id,
                "type": acc_type,
                "balance": bal,
            }
        )

    return pd.DataFrame(out).sort_values("account") if out else pd.DataFrame()


def cash_total_balance() -> float:
    """Saldo total excluindo contas de crédito (caixa disponível)."""
    df = balances_by_account(include_credit=False)
    if df.empty:
        return 0.0
    return float(df["balance"].sum())


def credit_outstanding_by_account() -> pd.DataFrame:
    """
    Para contas do tipo 'credit':
    - balance negativo => dívida (fatura em aberto)
    - em_aberto = max(0, -balance)
    - a_favor = max(0, balance)
    """
    df = balances_by_account(include_credit=True)
    if df.empty:
        return pd.DataFrame()

    credit_df = df[df["type"] == "credit"].copy()
    if credit_df.empty:
        return pd.DataFrame()

    credit_df["em_aberto"] = credit_df["balance"].apply(lambda x: max(0.0, -float(x)))
    credit_df["a_favor"] = credit_df["balance"].apply(lambda x: max(0.0, float(x)))

    # opcional: você pode esconder balance depois, mas eu deixo pra debug
    return credit_df[["account", "em_aberto", "a_favor", "balance"]].sort_values("account")


def total_credit_outstanding() -> float:
    df = credit_outstanding_by_account()
    if df.empty:
        return 0.0
    return float(df["em_aberto"].sum())
