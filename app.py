from __future__ import annotations

# """Aplicação Streamlit de finanças pessoais.

# Este arquivo concentra:
# - bootstrap do banco + seed
# - utilitários de formatação e datas
# - renderização das 3 páginas principais (Dashboard, Transações, Config)
# - roteamento de navegação no `main()`

# Objetivo desta versão:
# - manter a mesma funcionalidade
# - melhorar legibilidade com funções por responsabilidade
# - documentar claramente as regras de negócio no fluxo de UI
# """

import calendar
from datetime import date

import pandas as pd
import streamlit as st

import plotly.express as px

from src.config import (
    COL_LABELS,
    CREDIT_LABELS,
    MESES_PT,
    OWNER_LABELS,
    PAGE_LABELS,
    PAYER_LABELS,
    SPLIT_LABELS,
    TIPO_LABELS,
)
from src.db import init_db
from src.services.accounts import create_account, list_accounts
from src.services.categories import create_category, get_category_id_by_name, list_categories
from src.services.dashboards import balances_by_account, cash_total_balance
from src.services.seed import seed_defaults
from src.services.transactions import (
    create_transaction,
    current_balance_for_account,
    delete_transaction,
    list_transactions,
    update_transaction,
)

# Bootstrap da aplicação: inicializa banco e dados persistentes (executa uma vez por sessão).
@st.cache_resource
def bootstrap() -> None:
    """Inicializa recursos persistentes da aplicação (executa uma vez por sessão)."""
    init_db()
    seed_defaults()


# -----------------------------------------------
# ----- Funções utilitárias para formatação -----
# -----------------------------------------------

def fmt_brl(x: float) -> str:
    """Formata valor numérico para moeda BRL com separadores pt-BR."""
    return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_month(d: date) -> str:
    meses_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    return f"{meses_pt[d.month - 1]} / {d.year}"


def fmt_owner(k: str) -> str:
    """Converte id interno de owner para label amigável."""
    return OWNER_LABELS.get(k, k)


def fmt_payer(k: str) -> str:
    """Converte id interno de pagador para label amigável."""
    return PAYER_LABELS.get(k, k)


def fmt_split(k: str) -> str:
    """Converte id interno de divisão para label amigável."""
    return SPLIT_LABELS.get(k, k)


def fmt_df(
    df: pd.DataFrame,
    rename: dict | None = None,
    hide: list[str] | None = None,
) -> pd.DataFrame:
    """Aplica transformações visuais em DataFrame para exibição no Streamlit.

    - `hide`: remove colunas técnicas/irrelevantes para UI.
    - `rename`: renomeia colunas para labels de negócio.
    """
    out = df.copy()
    if hide:
        cols_to_drop = [c for c in hide if c in out.columns]
        out = out.drop(columns=cols_to_drop)
    if rename:
        out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    return out


def config_2dp(df: pd.DataFrame) -> dict:
    """Gera `column_config` com 2 casas decimais para colunas numéricas."""
    cfg: dict[str, st.column_config.NumberColumn] = {}
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            cfg[col] = st.column_config.NumberColumn(format="%.2f")
    return cfg


def print_df(df: pd.DataFrame, **kwargs) -> None:
    """Wrapper de `st.dataframe` com padronização de colunas numéricas."""
    st.dataframe(df, column_config=config_2dp(df), **kwargs)


# ------------------------------
# ----- Funções auxiliares -----
# ------------------------------

def month_first(d: date) -> date:
    """Retorna o primeiro dia do mês da data informada."""
    return date(d.year, d.month, 1)


def month_last(d: date) -> date:
    last_day = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last_day)


def add_months(d: date, months: int) -> date:
    """Soma meses preservando o dia quando possível (com ajuste para fim de mês)."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    day = min(d.day, last_day)
    return date(y, m, day)


def get_fatura(d: date, start_day: int = 4, end_day: int = 3) -> tuple[date, date]:
    """Calcula o ciclo de fatura que contém `d`.

    Exemplo padrão:
    - início dia 4
    - fim dia 3 do mês seguinte
    """
    if d.day >= start_day:
        start = date(d.year, d.month, start_day)
        end = add_months(date(d.year, d.month, end_day), 1)
    else:
        start = add_months(date(d.year, d.month, start_day), -1)
        end = date(d.year, d.month, end_day)
    return start, end


def formata_data(start: date, end: date) -> str:
    """Texto amigável do intervalo de compras do ciclo de fatura."""
    return f"{start.strftime('%d/%m/%Y')} e {end.strftime('%d/%m/%Y')}"


def is_credit_account(accs: list, account_name: str) -> bool:
    """Informa se uma conta (pelo nome) é do tipo crédito."""
    acc = next((a for a in accs if a.name == account_name), None)
    return bool(acc and acc.type.value == "credit")


def tipo_label_for(tipo_value: str) -> str:
    """Mapeia valor interno de tipo para o label da UI (ex: `expense` -> `Despesa`)."""
    return next((label for label, value in TIPO_LABELS.items() if value == tipo_value), tipo_value)


def filtra_periodo(tx_df: pd.DataFrame, mode: str = "cash") -> None:
    """Renderiza resumo e tabelas de transações para um período.

    Modos:
    - `cash`: entradas, saídas e saldo
    - `credit`: somente total da fatura (despesas negativas)
    """
    if tx_df.empty:
        st.info("Sem transações no período.")
        return

    # Métricas de topo mudam conforme o contexto de análise.
    if mode == "cash":
        income = tx_df.loc[tx_df["amount"] > 0, "amount"].sum()
        expense = tx_df.loc[tx_df["amount"] < 0, "amount"].sum()
        saldo = income + expense

        c1, c2, c3 = st.columns(3)
        c1.metric("Entradas", fmt_brl(float(income)))
        c2.metric("Saídas", fmt_brl(float(abs(expense))))
        c3.metric("Saldo do período", fmt_brl(float(saldo)))

    elif mode == "credit":
        fatura = tx_df.loc[tx_df["amount"] < 0, "amount"].sum()
        st.metric("Fatura atual", fmt_brl(float(abs(fatura))))

    # ---- Gastos por categoria ----
    st.subheader("Gastos por categoria no período")
    by_cat = (
        tx_df[(tx_df["amount"] < 0) & (tx_df["category_type"] != "transfer")]
        .groupby("category", as_index=False)["amount"]
        .sum()
        .sort_values("amount")
    )

    if by_cat.empty:
        st.caption("Sem gastos (excluindo transferências) no período.")

    else:
        by_cat["amount"] = by_cat["amount"].abs()
        plot_categories(
            by_cat,
            name_col="category",
            value_col="amount",
        )                 
    
    # Tabela detalhada do período com labels de apresentação.
    st.subheader("Transações no período")
    show_df = tx_df.copy()

    if "owner" in show_df.columns:
        show_df["owner"] = show_df["owner"].map(fmt_owner)
    
    if "paid_by" in show_df.columns:
        show_df["paid_by"] = show_df["paid_by"].map(fmt_payer)
    
    if "split_mode" in show_df.columns:
        show_df["split_mode"] = show_df["split_mode"].map(fmt_split)

    tx_ui = fmt_df(
        show_df,
        rename=COL_LABELS,
        hide=["id", "account_id", "category_id", "account_type", "category_type"],
    )
    print_df(tx_ui, width="stretch", hide_index=True)                  


# -------------------------------------------- 
# ----- Funções auxiliares para os plots -----
# --------------------------------------------

def plot_accounts(
    df: pd.DataFrame,
    name_col: str = "account",
    value_col: str = "balance",
    title: str = "",
):

    if df.empty:
        st.info("Sem dados para exibir.")
        return

    plot_df = df.copy()
    plot_df = plot_df[plot_df[value_col] != 0]
    plot_df = plot_df.sort_values(value_col, ascending=False)

    if plot_df.empty:
        st.info("Todas as contas estão com saldo zerado.")
        return

    total = plot_df[value_col].sum()

    COLORS = [
        "#FEC937",  # BB| Mel 
        "#B02C2C",  # Santander | PP


        "#EF4444",
        "#F59E0B",
        "#10B981",
        "#06B6D4",
        "#8B5CF6",
        "#4F46E5",
    ]

    fig = px.pie(
        plot_df,
        names  = name_col,
        values = value_col,
        hole   = 0.60,
        color_discrete_sequence=COLORS,
    )

    #  Mostrar valores absolutos
    fig.update_traces(
        texttemplate="R$ %{value:.2f}",
        textposition="inside",
        hovertemplate="<b>%{label}</b><br>Saldo: R$ %{value:.2f}<extra></extra>",
    )

    #  Total no centro do donut
    fig.add_annotation(
        text=f"<b>{fmt_brl(total)}</b>",
        showarrow=False,
        font=dict(size=24),
        x=0.5,
        y=0.5
    )

    fig.update_layout(
        title      = title,
        height     = 300,
        width      = 500,
        margin     = dict(t=0, b=20, l=0, r=0),
        showlegend = True,
    )

    st.plotly_chart(fig, use_container_width=False)


def plot_credit(
    df: pd.DataFrame,
    name_col: str = "cartao",
    value_col: str = "fatura",
    title: str = "",
):
    if df.empty:
        st.info("Sem dados para exibir.")
        return

    plot_df = df.copy()
    plot_df = plot_df[plot_df[value_col] != 0]

    if plot_df.empty:
        st.info("Nenhuma fatura em aberto neste ciclo.")
        return

    # ordem alfabética da legenda / cores
    plot_df = plot_df.sort_values(by=name_col, ascending=True)

    total = plot_df[value_col].sum()

    COLORS = [
        "#B02C2C",  # Santander | Crédito

        "#4F46E5",
        "#06B6D4",
        "#10B981",
        "#F59E0B",
        "#8B5CF6",
    ]

    fig = px.pie(
        plot_df,
        names=name_col,
        values=value_col,
        hole=0.60,
        color_discrete_sequence=COLORS,
        category_orders={name_col: plot_df[name_col].tolist()},
    )

    fig.update_traces(
        sort=False,
        texttemplate="R$ %{value:.2f}",
        textposition="inside",
        hovertemplate="<b>%{label}</b><br>Fatura: R$ %{value:.2f}<extra></extra>",
    )

    fig.add_annotation(
        text=f"<b>{fmt_brl(total)}</b>",
        showarrow=False,
        font=dict(size=24),
        x=0.5,
        y=0.5,
    )

    fig.update_layout(
        title      = title,
        height     = 300,
        width      = 500,
        margin     = dict(t=0, b=20, l=0, r=0),
        showlegend = True,
    )

    st.plotly_chart(fig, use_container_width=False)


def plot_categories(
    df: pd.DataFrame,
    name_col: str = "category",
    value_col: str = "amount",
    title: str = "",
):
    if df.empty:
        st.info("Sem dados para exibir.")
        return

    plot_df = df.copy()
    plot_df = plot_df[plot_df[value_col] != 0]

    if plot_df.empty:
        st.info("Todas as categorias estão zeradas.")
        return

    plot_df = plot_df.sort_values(name_col)
    total = plot_df[value_col].sum()

    COLORS = [
        "#F59E0B",  # Alimentação
        "#B00000",  # Carro
        "#A21B5A",  # Casamento
        "#06B6D4",  # Moradia
        "#D0D0D0",  # Outros
        "#4F46E5",  # Pessoal
        "#C94690",  # Presentes
        "#DB81C7",  # Ratos
        "#34D5CA",  # Saúde
        "#007E54",  # Transporte
        "#EF4444",  # Taxas
    ]

    fig = px.pie(
        plot_df,
        names=name_col,
        values=value_col,
        hole=0.60,
        color_discrete_sequence=COLORS,
    )

    fig.update_traces(
        sort=False,
        texttemplate="R$ %{value:.2f}",
        textposition="outside",
        hovertemplate="<b>%{label}</b><br>Gasto: R$ %{value:.2f}<extra></extra>",
    )

    fig.add_annotation(
        # text=f"Total<br><b>{brl(total)}</b>",
        text=f"<b>{fmt_brl(total)}</b>",
        showarrow=False,
        font=dict(size=18),
        x=0.5,
        y=0.5,
    )

    fig.update_layout(
        title      = title,
        height     = 300,
        width      = 500,
        margin     = dict(t=50, b=20, l=100, r=0),
        showlegend = True,
    )

    st.plotly_chart(fig, use_container_width=False)


# -------------------------------------------------
# ----- Funções para renderização das páginas -----
# -------------------------------------------------

def page_dashboard(today: date) -> None:
    """Página inicial: visão consolidada de caixa + cartões de crédito."""

    # Bloco 1: caixa (contas não-crédito).
    st.subheader("Caixa")

    # st.metric("Saldo total", brl(cash_total_balance(as_of=today)))
    # st.caption("Saldos por conta")

    # Gráfico dos saldos por conta
    bal_df = balances_by_account(include_credit=False, as_of=today)
    if not bal_df.empty:
        plot_accounts(
            bal_df[["account", "balance"]],
            name_col="account",
            value_col="balance",
            # title="Distribuição do saldo por conta",
        )
    else:
        st.info("Nenhuma conta de caixa encontrada (conta corrente/poupança).")

    accs_dash = list_accounts()
    credit_ids = {a.id for a in accs_dash if a.type.value == "credit"}
    filter_labels = {"todos": "Todos"} | OWNER_LABELS

    # Filtro expandível para análise de gastos de caixa no período.
    with st.expander("Ver gastos"):

        filter_labels = {"todos": "Todos"} | OWNER_LABELS

        if "cash_month_offset" not in st.session_state:
            st.session_state["cash_month_offset"] = 0

        nav1, nav2, nav3, nav4 = st.columns([3, 1, 1, 1])

        ref_date   = add_months(today, int(st.session_state["cash_month_offset"]))
        cash_start = month_first(ref_date)
        cash_end   = month_last(ref_date)

        nav1.metric("Mês selecionado:", fmt_month(ref_date))
        
        with nav2:
            if st.button("◀ Anterior", key="cash_prev"):
                st.session_state["cash_month_offset"] -= 1
                st.rerun()
        
        with nav3:
            if st.button("⟳ Atual", key="cash_now"):
                st.session_state["cash_month_offset"] = 0
                st.rerun()
        
        with nav4:
            if st.button("Próximo ▶", key="cash_next"):
                st.session_state["cash_month_offset"] += 1
                st.rerun()

        c1, c2, c3 = st.columns(3)
        
        with c1:
            cash_owner = st.selectbox(
                COL_LABELS["owner"],
                options=list(filter_labels.keys()),
                format_func=lambda k: filter_labels[k],
                index=0,
                key="cash_owner",
            )

        accs_dash = list_accounts()
        credit_ids = {a.id for a in accs_dash if a.type.value == "credit"}
        cash_accounts = sorted([a.name for a in accs_dash if a.type.value != "credit"])

        cats_dash = list_categories()
        cash_categories = ["Todas"] + sorted([c.name for c in cats_dash])

        with c2:
            cash_account = st.selectbox(
                "Conta",
                options=["Todas"] + cash_accounts,
                index=0,
                key="cash_account_filter",
            )
        
        with c3:
            cash_category = st.selectbox(
                "Categoria",
                options=cash_categories,
                index=0,
                key="cash_category_filter",
            )

        tx_cash_all = list_transactions(start=cash_start, end=cash_end, owner=cash_owner)

        tx_cash = tx_cash_all[~tx_cash_all["account_id"].isin(credit_ids)] if not tx_cash_all.empty else tx_cash_all

        if not tx_cash.empty and cash_account != "Todas":
            tx_cash = tx_cash[tx_cash["account"] == cash_account]

        if not tx_cash.empty and cash_category != "Todas":
            tx_cash = tx_cash[tx_cash["category"] == cash_category]

        filtra_periodo(tx_cash, mode="cash")


    st.divider()  # ==============================

    # Bloco 2: cartões de crédito com navegação de ciclo (mês anterior/atual/próximo).
    st.subheader("Cartões de crédito")

    if "cc_cycle_offset" not in st.session_state:
        st.session_state["cc_cycle_offset"] = 0

    nav1, nav2, nav3, nav4 = st.columns([3, 1, 1, 1])

    ref_date = add_months(today, int(st.session_state["cc_cycle_offset"]))
    cycle_start, cycle_end = get_fatura(ref_date, start_day=4, end_day=3)

    nav1.metric("Faturas de:", fmt_month(ref_date))
    
    with nav2:
        if st.button("◀ Anterior", key="cc_prev"):
            st.session_state["cc_cycle_offset"] -= 1
            st.rerun()
    
    with nav3:
        if st.button("⟳ Atual", key="cc_now"):
            st.session_state["cc_cycle_offset"] = 0
            st.rerun()
    
    with nav4:
        if st.button("Próximo ▶", key="cc_next"):
            st.session_state["cc_cycle_offset"] += 1
            st.rerun()

    st.caption(f"Compras entre: {formata_data(cycle_start, cycle_end)}")

    tx_cycle_all = list_transactions(start=cycle_start, end=cycle_end, owner="todos")
    tx_credit_cycle = (
        tx_cycle_all[tx_cycle_all["account_id"].isin(credit_ids)]
        if not tx_cycle_all.empty
        else tx_cycle_all
    )

    # Resumo por cartão considera apenas despesas (valores negativos).
    if tx_credit_cycle.empty:
        st.info("Sem transações de cartão nesse ciclo.")
        credit_ui = pd.DataFrame(columns=["cartão", "fatura"])
    
    else:
        grp = (
            tx_credit_cycle[tx_credit_cycle["amount"] < 0]
            .groupby("account", as_index=False)["amount"]
            .sum()
            .rename(columns={"account": "cartão"})
        )
        grp["fatura"] = grp["amount"].abs()
        credit_ui = grp[["cartão", "fatura"]].sort_values("cartão")

    total_fatura = float(credit_ui["fatura"].sum()) if not credit_ui.empty else 0.0
    # st.metric("Total", brl(total_fatura))

    if not credit_ui.empty:
        plot_credit(
            credit_ui,
            name_col="cartão",
            value_col="fatura",
        )

    with st.expander("Ver faturas"):
        c1, c2 = st.columns(2)
        with c1:
            cc_owner = st.selectbox(
                "De quem",
                options=list(filter_labels.keys()),
                format_func=lambda k: filter_labels[k],
                index=0,
                key="cc_owner",
            )
        with c2:
            cc_cartão = st.selectbox(
                "Cartão",
                options=["todos"] + sorted([a.name for a in accs_dash if a.id in credit_ids]),
                index=0,
                key="cc_card",
            )

        tx_cc = tx_credit_cycle.copy()
        if cc_owner != "todos" and not tx_cc.empty:
            tx_cc = tx_cc[tx_cc["owner"] == cc_owner]
        if cc_cartão != "todos" and not tx_cc.empty:
            tx_cc = tx_cc[tx_cc["account"] == cc_cartão]

        filtra_periodo(tx_cc, mode="credit")


def form_new_transaction(accs: list, cats: list) -> None:
    """Formulário principal para lançamento de transações."""
    st.subheader("Lançar transação")

    acc_map = {a.name: a.id for a in accs}
    cats_by_type = {
        "income": [c for c in cats if c.type == "income"],
        "expense": [c for c in cats if c.type == "expense"],
        "transfer": [c for c in cats if c.type == "transfer"],
        "investment": [c for c in cats if c.type == "investment"],
    }

    if "last_tx" not in st.session_state:
        # Guarda defaults para acelerar lançamentos repetitivos.
        st.session_state.last_tx = {
            "tipo": "Despesa",
            "owner": list(OWNER_LABELS.keys())[0],
            "paid_by": list(PAYER_LABELS.keys())[0],
            "split_mode": list(SPLIT_LABELS.keys())[0],
            "account": accs[0].name,
            "category": None,
            "card_label": "",
        }

    if "new_account" not in st.session_state:
        st.session_state["new_account"] = st.session_state.last_tx["account"]

    # Flag de reset: limpa campos controlados sem perder toda a sessão.
    if st.session_state.get("_reset_new_tx_form", False):
        st.session_state["_reset_new_tx_form"] = False
        st.session_state["new_valor"] = 0.0
        st.session_state["new_desc"] = ""
        st.session_state["new_card"] = ""
        st.session_state["new_is_installment"] = False
        st.session_state["new_total_installments"] = 1
        st.session_state["new_current_installment"] = 1

    tipo_ui = st.radio(
        "Tipo",
        options=list(TIPO_LABELS.keys()),
        horizontal=True,
        index=list(TIPO_LABELS.keys()).index(st.session_state.last_tx["tipo"]),
        key="new_tipo",
    )

    r2c1, r2c2 = st.columns(2)
    with r2c1:
        dt = st.date_input("Data", value=date.today(), key="new_dt")
    
    with r2c2:
        valor = st.number_input("Valor", min_value=0.0, step=10.0, key="new_valor")

    p1, p2, p3 = st.columns(3)
    with p1:
        is_installment = st.checkbox("Parcelado?", value=False, key="new_is_installment")
    
    with p2:
        total_installments = st.number_input(
            "Total de parcelas",
            min_value=1,
            step=1,
            value=1,
            disabled=not is_installment,
            key="new_total_installments",
        )
    
    with p3:
        current_installment = st.number_input(
            "Parcela atual",
            min_value=1,
            step=1,
            value=1,
            disabled=not is_installment,
            key="new_current_installment",
        )

    r3c1, r3c2, r3c3 = st.columns([3, 2, 1])
    with r3c1:
        description = st.text_input("Descrição", value="", key="new_desc")

    with r3c2:
        # Categoria disponível depende do tipo escolhido (income/expense/...).
        tipo = TIPO_LABELS[tipo_ui]
        allowed = cats_by_type.get(tipo, cats)

        cat_names = [c.name for c in allowed]
        if not cat_names:
            st.warning(f"Sem categorias do tipo '{tipo}'. Crie uma na aba Config.")
            st.stop()

        last_cat = st.session_state.last_tx["category"]
        cat_default = last_cat if last_cat in cat_names else cat_names[0]

        cat_key = st.selectbox(
            "Categoria",
            options=cat_names,
            index=cat_names.index(cat_default),
            key="new_category",
        )

    with r3c3:
        # Campo "Final do Cartão" só faz sentido para conta de crédito.
        selected_acc_name = st.session_state.get(
            "new_account", st.session_state.last_tx["account"]
        )
        card_enabled = is_credit_account(accs, selected_acc_name)

        card_label = st.text_input(
            "Final do Cartão",
            value=st.session_state.last_tx["card_label"],
            key="new_card",
            help="Opcional (ex: 9124).",
            disabled=not card_enabled,
        )

    r4c1, r4c2, r4c3, r4c4 = st.columns(4)
    with r4c1:
        acc_names = list(acc_map.keys())
        acc_default = (
            st.session_state.last_tx["account"]
            if st.session_state.last_tx["account"] in acc_names
            else acc_names[0]
        )
        acc_key = st.selectbox(
            "Conta", options=acc_names, index=acc_names.index(acc_default), key="new_account"
        )

    with r4c2:
        owner_id = st.selectbox(
            "De quem é",
            options=list(OWNER_LABELS.keys()),
            format_func=fmt_owner,
            index=list(OWNER_LABELS.keys()).index(st.session_state.last_tx["owner"]),
            key="new_owner",
        )

    with r4c3:
        paid_by_id = st.selectbox(
            "Quem pagou",
            options=list(PAYER_LABELS.keys()),
            format_func=fmt_payer,
            index=list(PAYER_LABELS.keys()).index(st.session_state.last_tx["paid_by"]),
            key="new_paid_by",
        )

    with r4c4:
        split_mode = st.selectbox(
            "Divisão",
            options=list(SPLIT_LABELS.keys()),
            format_func=fmt_split,
            index=list(SPLIT_LABELS.keys()).index(st.session_state.last_tx["split_mode"]),
            key="new_split",
        )

    b1, _, b3 = st.columns([1, 3, 1])
    with b1:
        save = st.button("Lançar transação", type="primary")
    with b3:
        if st.button("Limpar"):
            st.session_state["_reset_new_tx_form"] = True
            st.rerun()

    if not save:
        return

    # Regras de integridade do parcelamento.
    if is_installment:
        n_total = int(total_installments)
        n_current = int(current_installment)
        if n_current > n_total:
            st.error("Parcela atual não pode ser maior que o total de parcelas.")
            st.stop()
    else:
        n_total = 1
        n_current = 1

    base_amount = round(float(valor), 2)
    # Na UI o usuário digita valor positivo; sinal é inferido pelo tipo.
    if TIPO_LABELS[tipo_ui] == "expense":
        base_amount = -base_amount

    account_id = acc_map[acc_key]
    category_id = next(c.id for c in cats if c.name == cat_key)
    card_to_save = (card_label.strip() or None) if is_credit_account(accs, acc_key) else None

    base_date = month_first(dt)

    # Fluxo A: lançamento único.
    if not is_installment:
        create_transaction(
            dt=dt,
            amount=base_amount,
            description=description.strip(),
            account_id=account_id,
            category_id=category_id,
            owner=owner_id,
            paid_by=paid_by_id,
            split_mode=split_mode,
            card_label=card_to_save,
        )
        st.success("Transação salva!")
    else:
        # Fluxo B: parcelado, gerando uma transação por mês.
        created = 0
        for parcela in range(n_current, n_total + 1):
            dtx = add_months(base_date, parcela - n_current)
            suffix = f" ({parcela}/{n_total})"
            desc_i = (description.strip() or "").rstrip()

            create_transaction(
                dt=dtx,
                amount=base_amount,
                description=(desc_i + suffix).strip(),
                account_id=account_id,
                category_id=category_id,
                owner=owner_id,
                paid_by=paid_by_id,
                split_mode=split_mode,
                card_label=card_to_save,
            )
            created += 1

        st.success(
            f"Parcelamento criado: {created} transações ({n_current}/{n_total} até {n_total}/{n_total})."
        )

    st.session_state.last_tx = {
        "tipo": tipo_ui,
        "owner": owner_id,
        "paid_by": paid_by_id,
        "split_mode": split_mode,
        "account": acc_key,
        "category": cat_key,
        "card_label": (card_label.strip() if is_credit_account(accs, acc_key) else ""),
    }

    st.session_state["_reset_new_tx_form"] = True
    st.rerun()


def invoice_payment(accs: list, cats: list) -> None:
    """Fluxo auxiliar para pagamento de fatura (2 lançamentos espelhados)."""
    st.subheader("Pagar fatura")
    
    with st.expander("Abrir pagamento de fatura"):
        cat_fatura_id = None
        cat_map = {c.name: c.id for c in cats}
        for k, v in cat_map.items():
            if "Pgto. de fatura" in k:
                cat_fatura_id = v
                break

        if cat_fatura_id is None:
            st.error("Categoria 'Pgto. de fatura' não encontrada. Verifique a seed.")
            return

        bank_accounts = [a for a in accs if a.type.value != "credit"]
        credit_accounts = [a for a in accs if a.type.value == "credit"]

        if not bank_accounts or not credit_accounts:
            st.warning("Voce precisa ter pelo menos 1 conta banco e 1 conta crédito.")
            return

        acc_map = {a.name: a.id for a in accs}

        c1, c2, c3 = st.columns(3)
        with c1:
            origem = st.selectbox("Conta origem (banco)", [a.name for a in bank_accounts])
        
        with c2:
            destino = st.selectbox("Conta destino (crédito)", [a.name for a in credit_accounts])
        
        with c3:
            valor = st.number_input("Valor do pagamento", value=0.0, step=50.0)

        pdata = st.date_input("Data do pagamento", value=date.today(), key="pay_date")
        desc = st.text_input("Descrição", value="Pgto. de fatura", key="pay_desc")

        if not st.button("Gerar pagamento (2 lançamentos)"):
            return

        if valor <= 0:
            st.error("Valor precisa ser > 0.")
            return

        origem_id = acc_map[origem]
        destino_id = acc_map[destino]

        # Lançamento 1: saída da conta bancária.
        create_transaction(
            dt=pdata,
            amount=-round(float(valor), 2),
            description=desc,
            account_id=origem_id,
            category_id=cat_fatura_id,
            owner="petrus",
            paid_by="petrus",
            split_mode="none",
            card_label=None,
        )
        # Lançamento 2: entrada na conta de crédito para abater fatura.
        create_transaction(
            dt=pdata,
            amount=+round(float(valor), 2),
            description=desc,
            account_id=destino_id,
            category_id=cat_fatura_id,
            owner="petrus",
            paid_by="petrus",
            split_mode="none",
            card_label=None,
        )
        st.success("Pagamento gerado (banco -X, crédito +X).")


def editor_transaction(accs: list, cats: list) -> None:
    """Lista, seleciona e permite atualizar/excluir transações existentes."""
    st.subheader("Editar ou excluir transações")
    with st.expander("Abrir edição de transações"):
        filter_labels = {"todos": "Todos"} | OWNER_LABELS

        f1, f2, f3 = st.columns(3)
        with f1:
            start = st.date_input(
                "Filtro inicio",
                value=date(date.today().year, date.today().month, 1),
                key="fstart",
            )
        with f2:
            end = st.date_input("Filtro fim", value=date.today(), key="fend")
        with f3:
            owner_filter = st.selectbox(
                "De quem",
                options=list(filter_labels.keys()),
                format_func=lambda k: filter_labels[k],
                index=0,
                key="fowner",
            )

        df = list_transactions(start=start, end=end, owner=owner_filter)
        if df.empty:
            st.info("Nada por aqui nesse filtro.")
            st.stop()

        show_df = df.copy()
        show_df["owner"] = show_df["owner"].map(fmt_owner)
        show_df["paid_by"] = show_df["paid_by"].map(fmt_payer)
        show_df["split_mode"] = show_df["split_mode"].map(fmt_split)

        tx_list_ui = fmt_df(show_df, rename=COL_LABELS, hide=["id", "account_id", "category_id"])
        print_df(tx_list_ui, width="stretch", hide_index=True)

        df_label = df.copy()
        df_label["label"] = (
            "ID "
            + df_label["id"].astype(str)
            + " | "
            + df_label["date"].astype(str)
            + " | "
            + df_label["amount"].map(lambda x: fmt_brl(float(x)))
            + " | "
            + df_label["category"].astype(str)
            + " | "
            + df_label["description"].astype(str).str.slice(0, 40)
        )

        selected_label = st.selectbox(
            "Selecionar transação para editar",
            options=df_label["label"].tolist(),
            key="selected_tx_label",
        )

        tx_id = int(selected_label.split("ID ")[1].split(" |")[0])

        if "last_selected_tx_id" not in st.session_state:
            st.session_state.last_selected_tx_id = None

        if st.session_state.last_selected_tx_id != tx_id:
            # Ao trocar a seleção, sincroniza os campos de edição no session_state.
            row = df[df["id"] == tx_id].iloc[0]
            st.session_state.edt_date = row["date"]
            st.session_state.edt_owner = row["owner"]
            st.session_state.edt_paid_by = row["paid_by"]
            st.session_state.edt_split = row["split_mode"]
            st.session_state.edt_amount = float(row["amount"])
            st.session_state.edt_desc = str(row["description"])
            st.session_state.edt_acc = row["account"]
            st.session_state.edt_cat = str(row["category"])
            st.session_state.edt_card = str(row["card_label"])
            st.session_state.last_selected_tx_id = tx_id
        else:
            row = df[df["id"] == tx_id].iloc[0]

        st.markdown("### Editar")

        acc_names = [a.name for a in accs]
        cat_names = [c.name for c in cats]

        row_amount = float(row["amount"])
        row_cat_type = row.get("category_type", "")
        # Tipo é informativo neste formulário (não editável).
        if row_cat_type == "transfer":
            tipo_edit_ui = tipo_label_for("transfer")
        elif row_amount < 0:
            tipo_edit_ui = tipo_label_for("expense")
        else:
            tipo_edit_ui = tipo_label_for("income")

        st.radio(
            "Tipo",
            options=list(TIPO_LABELS.keys()),
            horizontal=True,
            index=list(TIPO_LABELS.keys()).index(tipo_edit_ui),
            disabled=True,
        )

        er2c1, er2c2 = st.columns(2)
        with er2c1:
            edt_date = st.date_input("Data", key="edt_date")
        with er2c2:
            edt_amount = st.number_input("Valor", step=10.0, key="edt_amount")

        er3c1, er3c2, er3c3 = st.columns([3, 2, 1])
        with er3c1:
            edt_desc = st.text_input("Descrição", key="edt_desc")
        with er3c2:
            edt_cat = st.selectbox("Categoria", cat_names, key="edt_cat")
        with er3c3:
            selected_acc_name = st.session_state.get("edt_acc", row["account"])
            card_enabled = is_credit_account(accs, selected_acc_name)
            edt_card = st.text_input(
                "Final do Cartão",
                key="edt_card",
                disabled=not card_enabled,
                help="Opcional (ex: 9124).",
            )

        er4c1, er4c2, er4c3, er4c4 = st.columns(4)
        with er4c1:
            edt_acc = st.selectbox("Conta", acc_names, key="edt_acc")
        with er4c2:
            edt_owner = st.selectbox(
                "De quem é",
                options=list(OWNER_LABELS.keys()),
                format_func=fmt_owner,
                key="edt_owner",
            )
        with er4c3:
            edt_paid_by = st.selectbox(
                "Quem pagou",
                options=list(PAYER_LABELS.keys()),
                format_func=fmt_payer,
                key="edt_paid_by",
            )
        with er4c4:
            edt_split = st.selectbox(
                "Divisão",
                options=list(SPLIT_LABELS.keys()),
                format_func=fmt_split,
                key="edt_split",
            )

        b1, _, b3 = st.columns([1, 3, 1])
        with b1:
            do_update = st.button("Atualizar", type="primary")
        with b3:
            do_delete = st.button("Excluir")

        if do_update:
            acc_id = next(a.id for a in accs if a.name == edt_acc)
            cat_id = next(c.id for c in cats if c.name == edt_cat)
            card_to_save = (
                (str(edt_card).strip() or None) if is_credit_account(accs, edt_acc) else None
            )

            update_transaction(
                int(tx_id),
                date=edt_date,
                amount=round(float(edt_amount), 2),
                description=edt_desc.strip(),
                account_id=int(acc_id),
                category_id=int(cat_id),
                owner=edt_owner,
                paid_by=edt_paid_by,
                split_mode=edt_split,
                card_label=card_to_save,
            )
            st.success("Atualizado!")
            st.session_state.last_selected_tx_id = None
            st.rerun()

        if do_delete:
            delete_transaction(int(tx_id))
            st.warning("Excluido!")
            st.session_state.last_selected_tx_id = None
            st.rerun()


def page_transactions() -> None:
    """Página de transações: lançamento, pagamento de fatura e edição."""
    accs = list_accounts()
    cats = list_categories()

    if not accs or not cats:
        st.warning("Crie ao menos 1 conta e 1 categoria na aba Config.")
        st.stop()

    form_new_transaction(accs, cats)
    st.divider()  # ==============================
    invoice_payment(accs, cats)
    st.divider()  # ==============================
    editor_transaction(accs, cats)


def page_config() -> None:
    """Página de configuração: contas, ajuste de saldo e categorias."""
    st.subheader("Contas")
    accs = list_accounts()

    if accs:
        df_acc = pd.DataFrame([a.model_dump() for a in accs])[
            ["id", "name", "owner", "type", "initial_balance"]
        ]
        df_acc["owner"] = df_acc["owner"].map(lambda x: OWNER_LABELS.get(x, x))
        col_acc_pt = {
            "id"              : "ID",
            "name"            : "Conta",
            "owner"           : "Owner",
            "type"            : "Tipo",
            "initial_balance" : "Saldo inicial (R$)",
        }
        print_df(
            fmt_df(df_acc, rename=col_acc_pt, hide=["id", "type", "owner"]),
            width="stretch",
            hide_index=True,
        )

    with st.expander("Adicionar conta"):
        name = st.text_input("Nome da conta", value="")
        owner_id = st.selectbox(
            "Dono da conta",
            options=list(OWNER_LABELS.keys()),
            format_func=fmt_owner,
            index=0,
        )
        typ = st.selectbox("Tipo", ["checking", "credit", "savings"], index=0)
        if st.button("Criar conta"):
            if name.strip():
                create_account(name.strip(), owner_id, typ, 0.0)
                st.success("Conta criada! Recarregue a página se necessário.")
            else:
                st.error("Informe um nome.")

    st.divider()  # ==============================

    st.subheader("Ajuste de saldo")

    if not accs:
        st.warning("Crie uma conta primeiro.")
        st.stop()

    acc_label_to_id = {a.name: a.id for a in accs}
    acc_choice = st.selectbox("Conta para ajustar", list(acc_label_to_id.keys()))
    acc_id = acc_label_to_id[acc_choice]
    current = current_balance_for_account(acc_id)

    st.caption(f"Saldo calculado atual dessa conta: **{fmt_brl(current)}**")

    target = st.number_input(
        "Qual saldo voce quer que essa conta fique AGORA?",
        value=float(current),
        step=50.0,
    )

    adj_cat_id = get_category_id_by_name("Ajuste de saldo ⚖️")
    if adj_cat_id is None:
        # Fallback para cenários onde o nome da categoria varia levemente.
        adj_cat_id = next((c.id for c in list_categories() if "Ajuste de saldo" in c.name), None)
    if adj_cat_id is None:
        st.error("Categoria 'Ajuste de saldo' não existe (seed falhou?).")
    else:
        if st.button("Criar ajuste"):
            delta = float(target) - float(current)
            if abs(delta) < 0.00001:
                st.info("Ja esta batendo. Nenhum ajuste necessário.")
            else:
                create_transaction(
                    dt=date.today(),
                    amount=round(delta, 2),
                    description=f"Ajuste de saldo para {fmt_brl(target)}",
                    account_id=acc_id,
                    category_id=adj_cat_id,
                    owner="petrus",
                    paid_by="petrus",
                    split_mode="none",
                    card_label=None,
                )
                st.success(f"Ajuste criado: {fmt_brl(delta)}")

    st.divider()  # ==============================

    st.subheader("Categorias")

    cats = list_categories()
    if cats:
        df_cat = pd.DataFrame([c.model_dump() for c in cats])[["id", "name", "type"]]
        col_cat_pt = {"id": "ID", "name": "Categoria", "type": "Tipo"}
        print_df(fmt_df(df_cat, rename=col_cat_pt, hide=["id"]), width="stretch", hide_index=True)

    with st.expander("Adicionar categoria"):
        cname = st.text_input("Nome da categoria", value="")
        ctype = st.selectbox(
            "Tipo da categoria",
            ["income", "expense", "investment", "transfer"],
            index=1,
        )
        if st.button("Criar categoria"):
            if cname.strip():
                create_category(cname.strip(), ctype)
                st.success("Categoria criada! Recarregue a página se necessário.")
            else:
                st.error("Informe um nome.")


# --------------------------------------------------
# ----- Função principal para renderizar o app -----
# --------------------------------------------------

def main() -> None:
    """Ponto de entrada da aplicação."""

    # Inicialização global (db + seed) antes de renderizar a UI.
    bootstrap()
    st.set_page_config(page_title=PAGE_LABELS["title"], layout="wide")

    today = date.today()

    st.title(PAGE_LABELS["title"])
    page = st.sidebar.radio(
        PAGE_LABELS["nav"],
        [PAGE_LABELS["dash"], PAGE_LABELS["trans"], PAGE_LABELS["config"]],
    )

    # Roteamento simples por label da navegação lateral.
    if page == PAGE_LABELS["dash"]:
        page_dashboard(today)
    elif page == PAGE_LABELS["trans"]:
        page_transactions()
    elif page == PAGE_LABELS["config"]:
        page_config()


if __name__ == "__main__":
    main()
