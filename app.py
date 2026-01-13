import streamlit as st
import pandas as pd
from pathlib import Path
from utils.data_manager import load_transactions, save_transactions

DATA_FILE = Path("data/transactions.csv")

# Carrega ou cria o DataFrame de transacoes

# Carregar transacoes existentes

# load existing transactions

# ensure file exists via data_manager

# Load transactions

df = load_transactions(DATA_FILE)

st.title("FinDash - Controle Financeiro")

# Sidebar form to add transactions
st.sidebar.header("Adicionar transação")
with st.sidebar.form("transaction_form"):
    date = st.date_input("Data")
    amount = st.number_input("Valor", value=0.0, step=0.01, format="%.2f")
    description = st.text_input("Descrição")
    category = st.text_input("Categoria")
    payment_type = st.selectbox("Tipo de pagamento", ["Débito", "Crédito", "PIX", "Renda"])
    user = st.selectbox("Usuário", ["eu", "parceiro"])
    submit = st.form_submit_button("Adicionar")

    if submit:
        new_row = {
            "date": date.strftime("%Y-%m-%d"),
            "amount": amount,
            "description": description,
            "category": category,
            "type": payment_type,
            "user": user,
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_transactions(df, DATA_FILE)
        st.success("Transação adicionada com sucesso.")

# Display transactions
st.subheader("Transações")
st.dataframe(df)

# Summary by category
if not df.empty:
    st.subheader("Resumo por categoria")
    summary = df.groupby("category")["amount"].sum().reset_index()
    st.bar_chart(data=summary, x="category", y="amount")
