from __future__ import annotations

import calendar

import pandas as pd
import streamlit as st

from datetime import date

from src.db import init_db
from src.config import (
    COL_LABELS,
    PAGE_LABELS,
    OWNER_LABELS,
    TIPO_LABELS,
    CREDIT_LABELS,
    PAYER_LABELS,
    SPLIT_LABELS
)

from src.services.seed import seed_defaults
from src.services.dashboards import (
    balances_by_account,
    cash_total_balance,
    credit_outstanding_by_account,
    total_credit_outstanding,
)

from src.services.accounts import list_accounts, create_account
from src.services.categories import list_categories, create_category, get_category_id_by_name
from src.services.transactions import (
    create_transaction,
    update_transaction,
    delete_transaction,
    list_transactions,
    current_balance_for_account
)


@st.cache_resource
def bootstrap():
    init_db()
    seed_defaults()

bootstrap()


st.set_page_config(page_title=PAGE_LABELS["title"], layout="wide")


# -------- Funções auxiliares --------
def brl(x: float) -> str:
    return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_owner(k: str) -> str:
    return OWNER_LABELS.get(k, k)


def fmt_payer(k: str) -> str:
    return PAYER_LABELS.get(k, k)


def fmt_split(k: str) -> str:
    return SPLIT_LABELS.get(k, k)


def format_df(df: pd.DataFrame, rename: dict | None = None, hide: list[str] | None = None) -> pd.DataFrame:
    out = df.copy()
    if hide:
        cols_to_drop = [c for c in hide if c in out.columns]
        out = out.drop(columns=cols_to_drop)
    if rename:
        out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    return out


def month_first(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    day = min(d.day, last_day)
    return date(y, m, day)

# ------------------------------------
today = date.today()

st.header(PAGE_LABELS["title"])
page = st.sidebar.radio(
    PAGE_LABELS["nav"],
    [PAGE_LABELS["dash"], PAGE_LABELS["trans"], PAGE_LABELS["config"]]
)

# -------- Dashboard --------
if page == PAGE_LABELS["dash"]:

    # =========================
    # Caixa (sem cartão)
    # =========================
    st.subheader("Caixa")

    st.metric("Saldo total", brl(cash_total_balance(as_of=today)))
    st.caption("Saldos por conta")

    bal_df = balances_by_account(include_credit=False, as_of=today)
    if not bal_df.empty:
        saldo_ui = format_df(
            bal_df[["account", "balance"]],
            rename=COL_LABELS,
        )
        st.dataframe(saldo_ui, width="stretch", hide_index=True)
    else:
        st.info("Nenhuma conta de caixa encontrada (conta corrente/poupança).")
   
    # =========================
    st.divider()
    # =========================

    # =========================
    # Cartões (fatura)
    # =========================
    st.subheader("Cartões de crédito")
    st.metric("Total em aberto (cartões)", brl(total_credit_outstanding(as_of=today)))

    credit_df = credit_outstanding_by_account(as_of=today)
    if credit_df.empty:
        st.info("Nenhuma conta de crédito cadastrada.")
    else:
        credit_ui = format_df(credit_df, hide=['balance'], rename=CREDIT_LABELS)
        st.dataframe(credit_ui, width="stretch", hide_index=True)
    
    # =========================
    st.divider()
    # =========================

    # =========================
    # Resumo por período
    # =========================
    st.subheader("Resumo no período")

    today = date.today()
    default_start = date(today.year, today.month, 1)

    filter_labels = {"todos": "Todos"} | OWNER_LABELS

    c1, c2, c3 = st.columns(3)
    with c1:
        start = st.date_input("Início", value=default_start)
    with c2:
        end = st.date_input("Fim", value=today)
    with c3:
        owner_filter = st.selectbox(
            COL_LABELS["owner"],
            options=list(filter_labels.keys()),
            format_func=lambda k: filter_labels[k],
            index=0,
        )

    tx_df = list_transactions(start=start, end=end, owner=owner_filter)

    if tx_df.empty:
        st.info("Sem transações no período.")
    else:
        income = tx_df.loc[tx_df["amount"] > 0, "amount"].sum()
        expense = tx_df.loc[tx_df["amount"] < 0, "amount"].sum()
        saldo = income + expense

        a, b, c = st.columns(3)
        a.metric("Entradas", brl(float(income)))
        b.metric("Saídas", brl(float(abs(expense))))
        c.metric("Saldo do período", brl(float(saldo)))

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
            by_cat_ui = format_df(
                by_cat,
                rename=COL_LABELS,
                hide=["account_id"],
            )
            st.dataframe(by_cat_ui, width="stretch", hide_index=True)

        st.subheader("Transações no período")
        show_df = tx_df.copy()
        if "owner" in show_df.columns:
            show_df["owner"] = show_df["owner"].map(fmt_owner)
        if "paid_by" in show_df.columns:
            show_df["paid_by"] = show_df["paid_by"].map(fmt_payer)
        if "split_mode" in show_df.columns:
            show_df["split_mode"] = show_df["split_mode"].map(fmt_split)

        tx_ui = format_df(
            show_df,
            rename=COL_LABELS,
            hide=["account_id", "category_id", "account_type", "category_type"],
        )
        st.dataframe(tx_ui, width="stretch", hide_index=True)


# -------- Transações --------
elif page == PAGE_LABELS["trans"]:

    # -------- Lançar transação --------
    st.subheader("Lançar transação")

    accs = list_accounts()
    cats = list_categories()

    if not accs or not cats:
        st.warning("Crie ao menos 1 conta e 1 categoria na aba Config.")
        st.stop()

    acc_map = {f"{a.name}": a.id for a in accs}

    cats_by_type = {
        "income": [c for c in cats if c.type == "income"],
        "expense": [c for c in cats if c.type == "expense"],
        "transfer": [c for c in cats if c.type == "transfer"],
        "investment": [c for c in cats if c.type == "investment"],
    }

    if "last_tx" not in st.session_state:
        st.session_state.last_tx = {
            "tipo": "Despesa",
            "owner": list(OWNER_LABELS.keys())[0],
            "paid_by": list(PAYER_LABELS.keys())[0],
            "split_mode": list(SPLIT_LABELS.keys())[0],
            "account": accs[0].name,
            "category": None,
            "card_label": "",
        }

    # garante default da conta no session_state (pra usar no cartão)
    if "new_account" not in st.session_state:
        st.session_state["new_account"] = st.session_state.last_tx["account"]

    def is_credit_account(account_name: str) -> bool:
        acc = next((a for a in accs if a.name == account_name), None)
        return bool(acc and acc.type.value == "credit")

    # --- reset antes de instanciar widgets ---
    if st.session_state.get("_reset_new_tx_form", False):
        st.session_state["_reset_new_tx_form"] = False
        st.session_state["new_valor"] = 0.0
        st.session_state["new_desc"] = ""
        st.session_state["new_card"] = ""
        st.session_state["new_is_installment"] = False
        st.session_state["new_total_installments"] = 1
        st.session_state["new_current_installment"] = 1


    # =========================
    # Linha 1: Tipo (sozinho)
    # =========================
    tipo_ui = st.radio(
        "Tipo",
        options=["Despesa", "Entrada", "Transferência"],
        horizontal=True,
        index=["Despesa", "Entrada", "Transferência"].index(st.session_state.last_tx["tipo"]),
        key="new_tipo",
    )
    
    # =========================
    # Linha 2: Data e Valor
    # =========================
    r2c1, r2c2 = st.columns(2)
    with r2c1:
        dt = st.date_input("Data", value=date.today(), key="new_dt")
    with r2c2:
        valor = st.number_input("Valor", min_value=0.0, step=10.0, key="new_valor")

    # =========================
    # Parcelamento (opcional)
    # ========================= 
    p1, p2, p3 = st.columns([1, 1, 1])
    with p1:
        is_installment = st.checkbox("Parcelado?", value=False, key="new_is_installment")
    with p2:
        total_installments = st.number_input(
            "Total de parcelas (N)",
            min_value=1,
            step=1,
            value=1,
            disabled=not is_installment,
            key="new_total_installments",
        )
    with p3:
        current_installment = st.number_input(
            "Parcela atual (n)",
            min_value=1,
            step=1,
            value=1,
            disabled=not is_installment,
            key="new_current_installment",
        )


    # =========================
    # Linha 3: Descrição, Categoria, Final do cartão
    # =========================
    r3c1, r3c2, r3c3 = st.columns([3, 2, 1])

    with r3c1:
        description = st.text_input("Descrição", value="", key="new_desc")

    with r3c2:
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
        selected_acc_name = st.session_state.get("new_account", st.session_state.last_tx["account"])
        card_enabled = is_credit_account(selected_acc_name)

        card_label = st.text_input(
            "Final do Cartão",
            value=st.session_state.last_tx["card_label"],
            key="new_card",
            help="Opcional (ex: 9124).",
            disabled=not card_enabled,
        )

    # =========================
    # Linha 4: Conta, De quem é, Quem pagou, Divisão (iguais)
    # =========================
    r4c1, r4c2, r4c3, r4c4 = st.columns(4)

    with r4c1:
        acc_names = list(acc_map.keys())
        acc_default = st.session_state.last_tx["account"] if st.session_state.last_tx["account"] in acc_names else acc_names[0]
        acc_key = st.selectbox("Conta", options=acc_names, index=acc_names.index(acc_default), key="new_account")

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

    # =========================
    # Botões (Salvar esq, Limpar dir)
    # =========================
    b1, b2, b3 = st.columns([1, 3, 1])
    with b1:
        save = st.button("Lançar transação", type="primary")
    with b3:
        if st.button("Limpar"):
            st.session_state["_reset_new_tx_form"] = True
            st.rerun()

    if save:
        # validações parcelamento
        if is_installment:
            N = int(total_installments)
            n = int(current_installment)
            if n > N:
                st.error("Parcela atual (n) não pode ser maior que o total de parcelas (N).")
                st.stop()
        else:
            N = 1
            n = 1

        # aplica sinal automaticamente (valor informado é sempre positivo na UI)
        base_amount = round(float(valor), 2)
        if TIPO_LABELS[tipo_ui] == "expense":
            base_amount = -base_amount

        account_id = acc_map[acc_key]
        category_id = next(c.id for c in cats if c.name == cat_key)
        card_to_save = (card_label.strip() or None) if is_credit_account(acc_key) else None

        # data base: primeiro dia do mês
        base_date = month_first(dt)

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
            created = 0
            for parcela in range(n, N + 1):
                dtx = add_months(base_date, parcela - n)  # n no mês da data; futuras nos meses seguintes
                suffix = f" ({parcela}/{N})"
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

            st.success(f"Parcelamento criado: {created} transações ({n}/{N} até {N}/{N}).")

        # guarda defaults (B = último usado)
        st.session_state.last_tx = {
            "tipo": tipo_ui,
            "owner": owner_id,
            "paid_by": paid_by_id,
            "split_mode": split_mode,
            "account": acc_key,
            "category": cat_key,
            "card_label": (card_label.strip() if is_credit_account(acc_key) else ""),
        }

        st.session_state["_reset_new_tx_form"] = True
        st.rerun()
        # ----------------------------------

    # =========================
    st.divider()
    # =========================

    # ==============================
    # -------- Pagar fatura --------
    # ==============================
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
        else:
            bank_accounts = [a for a in accs if a.type.value != "credit"]
            credit_accounts = [a for a in accs if a.type.value == "credit"]

            if not bank_accounts or not credit_accounts:
                st.warning("Você precisa ter pelo menos 1 conta banco e 1 conta crédito (ex: Santander Crédito).")
            else:
                b1, b2, b3 = st.columns(3)
                with b1:
                    origem = st.selectbox("Conta origem (banco)", [f"{a.name}" for a in bank_accounts])
                with b2:
                    destino = st.selectbox("Conta destino (crédito)", [f"{a.name}" for a in credit_accounts])
                with b3:
                    valor = st.number_input("Valor do pagamento", value=0.0, step=50.0)

                pdata = st.date_input("Data do pagamento", value=date.today(), key="pay_date")
                desc = st.text_input("Descrição", value="Pgto. de fatura", key="pay_desc")

                if st.button("Gerar pagamento (2 lançamentos)"):
                    if valor <= 0:
                        st.error("Valor precisa ser > 0.")
                    else:
                        origem_id = acc_map[origem]
                        destino_id = acc_map[destino]

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
    # ----------------------------------

    st.divider()

    # -------- Editar transações --------
    st.subheader("Editar ou excluir transações")
    with st.expander("Abrir edição de transações"):
        filter_labels = {"todos": "Todos"} | OWNER_LABELS

        f1, f2, f3 = st.columns(3)
        with f1:
            start = st.date_input("Filtro início", value=date(date.today().year, date.today().month, 1), key="fstart")
        with f2:
            end = st.date_input("Filtro fim", value=date.today(), key="fend")
        with f3:
            owner_filter = st.selectbox(
                "Filtro owner",
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

        tx_list_ui = format_df(
            show_df,
            rename=COL_LABELS,
            hide=["account_id", "category_id"],
        )
        st.dataframe(tx_list_ui, width="stretch", hide_index=True)

        df_label = df.copy()
        df_label["label"] = (
            "ID " + df_label["id"].astype(str) + " | "
            + df_label["date"].astype(str) + " | "
            + df_label["amount"].map(lambda x: brl(float(x))) + " | "
            + df_label["category"].astype(str) + " | "
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

        def is_credit_account_edit(account_name: str) -> bool:
            acc = next((a for a in accs if a.name == account_name), None)
            return bool(acc and acc.type.value == "credit")

        row_amount = float(row["amount"])
        row_cat_type = row.get("category_type", "")
        if row_cat_type == "transfer":
            tipo_edit_ui = "Transferência"
        elif row_amount < 0:
            tipo_edit_ui = "Despesa"
        else:
            tipo_edit_ui = "Entrada"

        st.radio(
            "Tipo",
            options=["Despesa", "Entrada", "Transferência"],
            horizontal=True,
            index=["Despesa", "Entrada", "Transferência"].index(tipo_edit_ui),
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
            card_enabled = is_credit_account_edit(selected_acc_name)

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

        b1, b2, b3 = st.columns([1, 3, 1])
        with b1:
            do_update = st.button("Atualizar", type="primary")
        with b3:
            do_delete = st.button("Excluir")

        if do_update:
            acc_id = next(a.id for a in accs if a.name == edt_acc)
            cat_id = next(c.id for c in cats if c.name == edt_cat)
            card_to_save = (str(edt_card).strip() or None) if is_credit_account_edit(edt_acc) else None

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
            st.warning("Excluído!")
            st.session_state.last_selected_tx_id = None
            st.rerun()


# -------- Config --------
elif page == PAGE_LABELS["config"]:

    st.subheader("Contas")
    accs = list_accounts()
    if accs:
        df_acc = pd.DataFrame([a.model_dump() for a in accs])[["id", "name", "owner", "type", "initial_balance"]]
        df_acc["owner"] = df_acc["owner"].map(lambda x: OWNER_LABELS.get(x, x))
        COL_ACC_PT = {
            "id":              "ID",
            "name":            "Conta",
            "owner":           "Owner",
            "type":            "Tipo",
            "initial_balance": "Saldo inicial (R$)",
        }
        st.dataframe(format_df(df_acc, rename=COL_ACC_PT, hide=["id", "type", "owner"]), width="stretch", hide_index=True)

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

    # =========================
    st.divider()
    # =========================

    st.subheader("Ajuste de saldo")

    if not accs:
        st.warning("Crie uma conta primeiro.")
        st.stop()

    acc_label_to_id = {f"{a.name}": a.id for a in accs}
    acc_choice = st.selectbox("Conta para ajustar", list(acc_label_to_id.keys()))
    acc_id = acc_label_to_id[acc_choice]
    current = current_balance_for_account(acc_id)

    st.caption(f"Saldo calculado atual dessa conta: **{brl(current)}**")

    target = st.number_input("Qual saldo você quer que essa conta fique AGORA?", value=float(current), step=50.0)

    adj_cat_id = get_category_id_by_name("Ajuste de saldo ⚖️")
    if adj_cat_id is None:
        st.error("Categoria 'Ajuste de saldo' não existe (seed falhou?).")
    else:
        if st.button("Criar ajuste"):
            delta = float(target) - float(current)
            if abs(delta) < 0.00001:
                st.info("Já está batendo. Nenhum ajuste necessário.")
            else:
                create_transaction(
                    dt=date.today(),
                    amount=round(delta, 2),
                    description=f"Ajuste de saldo para {brl(target)}",
                    account_id=acc_id,
                    category_id=adj_cat_id,
                    owner="petrus",
                    paid_by="petrus",
                    split_mode="none",
                    card_label=None,
                )
                st.success(f"Ajuste criado: {brl(delta)}")

    st.divider()

    st.subheader("Categorias")

    cats = list_categories()
    if cats:
        df_cat = pd.DataFrame([c.model_dump() for c in cats])[["id", "name", "type"]]
        COL_CAT_PT = {"id": "ID", "name": "Categoria", "type": "Tipo"}
        st.dataframe(format_df(df_cat, rename=COL_CAT_PT, hide=["id"]), width="stretch", hide_index=True)

    with st.expander("Adicionar categoria"):
        cname = st.text_input("Nome da categoria", value="")
        ctype = st.selectbox("Tipo da categoria", ["income", "expense", "investment", "transfer"], index=1)
        if st.button("Criar categoria"):
            if cname.strip():
                create_category(cname.strip(), ctype)
                st.success("Categoria criada! Recarregue a página se necessário.")
            else:
                st.error("Informe um nome.")
