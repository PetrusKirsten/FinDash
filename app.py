from __future__ import annotations

import pandas as pd
import streamlit as st

from datetime import date

from src.db import init_db
from src.config import COL_LABELS, PAGE_LABELS, OWNER_LABELS, PAYER_LABELS, SPLIT_LABELS

from src.services.seed import seed_defaults
from src.services.dashboards import balances_by_account, total_balance
from src.services.accounts import list_accounts, create_account
from src.services.categories import list_categories, create_category, get_category_id_by_name
from src.services.transactions import (
    create_transaction, update_transaction, delete_transaction,
    list_transactions, current_balance_for_account
)


st.set_page_config(page_title=PAGE_LABELS["title"], layout="wide")

# init_db()
# seed_defaults()


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


st.title(PAGE_LABELS["title"])
page = st.sidebar.radio(
    PAGE_LABELS["nav"], 
    [PAGE_LABELS["dash"], PAGE_LABELS["trans"], PAGE_LABELS["config"]]
)


# -------- Dashboard --------
if page == PAGE_LABELS["dash"]:
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Saldo total (todas as contas)", brl(total_balance()))
    with col2:
        st.caption("Saldo por conta")

    bal_df = balances_by_account()
    if not bal_df.empty:
        saldo_ui = format_df(
            bal_df[["account", "balance"]],
            rename=COL_LABELS,
        )
        st.dataframe(saldo_ui, width='stretch', hide_index=True)

    st.divider()
    st.subheader("Resumo por período")

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
            "Owner",
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

        st.subheader("Gastos por categoria (período)")
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
            st.dataframe(by_cat, width='stretch', hide_index=True)

        st.subheader("Transações (período)")
        # mostra owner/payer/split com labels
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
            hide=["account_id", "category_id"],  # se existirem
        )
        st.dataframe(tx_ui, width='stretch', hide_index=True)


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
    cat_map = {f"{c.name}": c.id for c in cats}

    c1, c2, c3 = st.columns(3)
    with c1:
        dt = st.date_input("Data", value=date.today())
        owner_id = st.selectbox("De quem é", options=list(OWNER_LABELS.keys()), format_func=fmt_owner, index=0)
    with c2:
        paid_by_id = st.selectbox("Quem pagou", options=list(PAYER_LABELS.keys()), format_func=fmt_payer, index=0)
        split_mode = st.selectbox("Divisão", options=list(SPLIT_LABELS.keys()), format_func=fmt_split, index=0)
    with c3:
        amount = st.number_input("Valor (positivo entrada, negativo gasto)", value=0.0, step=10.0)
        description = st.text_input("Descrição", value="")

    c4, c5 = st.columns(2)
    with c4:
        acc_key = st.selectbox("Conta", list(acc_map.keys()))
    with c5:
        cat_key = st.selectbox("Categoria", list(cat_map.keys()))

    card_label = st.text_input("Final do Cartão", value="")

    if st.button("Salvar transação"):
        create_transaction(
            dt=dt,
            amount=float(amount),
            description=description.strip(),
            account_id=acc_map[acc_key],
            category_id=cat_map[cat_key],
            owner=owner_id,
            paid_by=paid_by_id,
            split_mode=split_mode,
            card_label=card_label.strip() or None,
        )
        st.success("Transação salva!")
    # ----------------------------------

    st.divider()

    # -------- Pagar fatura --------
    st.subheader("Pagar fatura")
    with st.expander("Abrir pagamento de fatura"):
        cat_fatura_id = None
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
                        origem_id = int(origem.split("id=")[1].replace(")", ""))
                        destino_id = int(destino.split("id=")[1].replace(")", ""))

                        create_transaction(
                            dt=pdata,
                            amount=-float(valor),
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
                            amount=+float(valor),
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
    st.subheader("Editar / Excluir transações")

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

    # tabela bonitinha (UI)
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

    st.divider()

    # ---- Seleção prática (label rico) ----
    df_label = df.copy()
    df_label["label"] = (
        "ID " + df_label["id"].astype(str)                + " | "
        + df_label["date"].astype(str)                    + " | " 
        + df_label["amount"].map(lambda x: brl(float(x))) + " | " 
        + df_label["category"].astype(str)                + " | " 
        + df_label["description"].astype(str).str.slice(0, 40)
    )

    selected_label = st.selectbox(
        "Selecionar transação para editar",
        options=df_label["label"].tolist(),
        key="selected_tx_label",
    )

    tx_id = int(selected_label.split("ID ")[1].split(" |"")[0])

    # ---- Sincronizar form quando tx_id muda ----
    if "last_selected_tx_id" not in st.session_state:
        st.session_state.last_selected_tx_id = None

    if st.session_state.last_selected_tx_id != tx_id:
        row = df[df["id"] == tx_id].iloc[0]

        # popula os widgets (a partir da linha selecionada)
        st.session_state.edt_date = row["date"]
        st.session_state.edt_owner = row["owner"]
        st.session_state.edt_paid_by = row["paid_by"]
        st.session_state.edt_split = row["split_mode"]
        st.session_state.edt_amount = float(row["amount"])
        st.session_state.edt_desc = str(row["description"])

        st.session_state.edt_acc = row["account"]
        st.session_state.edt_cat = str(row["category"])  # aqui é só o nome
        st.session_state.edt_card = str(row["card_label"])

        st.session_state.last_selected_tx_id = tx_id
    else:
        row = df[df["id"] == tx_id].iloc[0]

    # ---- Form de edição (controlado por session_state) ----
    st.markdown("### Editar")

    acc_names = [a.name for a in accs]
    cat_names = [c.name for c in cats]

    ec1, ec2, ec3 = st.columns(3)
    with ec1:
        edt_date = st.date_input("Data", key="edt_date")
        edt_owner = st.selectbox(
            "Owner",
            options=list(OWNER_LABELS.keys()),
            format_func=fmt_owner,
            key="edt_owner",
        )
    with ec2:
        edt_paid_by = st.selectbox(
            "Quem pagou?",
            options=list(PAYER_LABELS.keys()),
            format_func=fmt_payer,
            key="edt_paid_by",
        )
        edt_split = st.selectbox(
            "Divisão",
            options=list(SPLIT_LABELS.keys()),
            format_func=fmt_split,
            key="edt_split",
        )
    with ec3:
        edt_amount = st.number_input("Valor", step=10.0, key="edt_amount")
        edt_desc = st.text_input("Descrição", key="edt_desc")

    ec4, ec5 = st.columns(2)
    with ec4:
        edt_acc = st.selectbox("Conta", acc_names, key="edt_acc")
    with ec5:
        edt_cat = st.selectbox("Categoria", cat_names, key="edt_cat")

    edt_card = st.text_input("Card label (opcional)", key="edt_card")

    colA, colB = st.columns(2)
    with colA:
        if st.button("Atualizar"):
            acc_id = next(a.id for a in accs if a.name == edt_acc)
            cat_id = next(c.id for c in cats if c.name == edt_cat)  # <--- corrigido

            update_transaction(
                int(tx_id),
                date=edt_date,
                amount=float(edt_amount),
                description=edt_desc.strip(),
                account_id=int(acc_id),
                category_id=int(cat_id),
                owner=edt_owner,
                paid_by=edt_paid_by,
                split_mode=edt_split,
                card_label=(str(edt_card).strip() or None),
            )
            st.success("Atualizado!")
            # força recarregar o df e sincronizar com o mesmo tx_id
            st.session_state.last_selected_tx_id = None
            st.rerun()

    with colB:
        if st.button("Excluir"):
            delete_transaction(int(tx_id))
            st.warning("Excluído!")
            st.session_state.last_selected_tx_id = None
            st.rerun()


# -------- Config --------
elif page == PAGE_LABELS["config"]:
    
    # -------- Contas --------
    st.subheader("Contas")
    accs = list_accounts()
    if accs:
        df_acc = pd.DataFrame([a.model_dump() for a in accs])[["id", "name", "owner", "type", "initial_balance"]]
        df_acc["owner"] = df_acc["owner"].map(lambda x: OWNER_LABELS.get(x, x))        
        COL_ACC_PT = {
            "id": "ID",
            "name": "Conta",
            "owner": "Owner",
            "type": "Tipo",
            "initial_balance": "Saldo inicial",
        }
        st.dataframe(format_df(df_acc, rename=COL_ACC_PT, hide=["id", "type", "owner"]), width='stretch', hide_index=True)

    with st.expander("Adicionar conta"):
        name = st.text_input("Nome da conta", value="")
        owner_id = st.selectbox(
            "Owner da conta",
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

    st.divider()

    # -------- Ajuste de saldo --------
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
                    amount=delta,
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

    # -------- Categorias --------
    st.subheader("Categorias")

    cats = list_categories()
    if cats:
        df_cat = pd.DataFrame([c.model_dump() for c in cats])[["id", "name", "type"]]
        COL_CAT_PT = {"id": "ID", "name": "Categoria", "type": "Tipo"}
        st.dataframe(format_df(df_cat, rename=COL_CAT_PT, hide=["id"]), width='stretch', hide_index=True)

    # -------- Adicionar categoria --------
    with st.expander("Adicionar categoria"):
        cname = st.text_input("Nome da categoria", value="")
        ctype = st.selectbox("Tipo da categoria", ["income", "expense", "investment", "transfer"], index=1)
        if st.button("Criar categoria"):
            if cname.strip():
                create_category(cname.strip(), ctype)
                st.success("Categoria criada! Recarregue a página se necessário.")
            else:
                st.error("Informe um nome.")
