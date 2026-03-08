import re

COL_LABELS = {
    "account":       "Conta",
    "balance":       "Saldo (R$)",
    "date":          "Data",
    "amount":        "Valor (R$)",
    "description":   "Descrição",
    "category":      "Categoria",
    "category_type": "Tipo da categoria",
    "account_type":  "Tipo da conta",
    "owner":         "De quem",
    "paid_by":       "Quem pagou",
    "split_mode":    "Divisão",
    "card_label":    "Cartão (Final)",
    "id":            "ID",
}

PAGE_LABELS = {
    "title":  "💵💲🏦📊 Finanças | Pelissa",
    "nav":    "☰ Navegação",
    "dash":   "🏠 Início",
    "trans":  "📊 Transações",
    "config": "⚙️ Configs",
}

OWNER_LABELS = {
    "petrus":  "Petrus 🧙🏻‍♂️",
    "partner": "Melissa 🐝",
    "both":    "Ambos 👫",
}

TIPO_LABELS = {
    "Despesa":       "expense",
    "Entrada":       "income",
    "Transferência": "transfer",
}

CREDIT_LABELS = {
    "account":   "Cartão",
    "em_aberto": "Fatura (R$)",
    "a_favor":   "A favor (R$)",
    # "balance": "Saldo (debug)",  # se quiser mostrar, descomente no dashboards.py e aqui
}

PAYER_LABELS = {
    "petrus":  "Petrus",
    "partner": "Melissa",
}

SPLIT_LABELS = {
    "none":      "Não dividir",
    "equal":     "Dividir 50/50",
    "other_100": "100% do outro",
}

CATEGORY_COLORS = {
    "Alimentação 🍽️":     "#DB7629",
    "Carro 🚗":           "#10A674",
    "Casamento 💍":       "#63002E",
    "Moradia 🏠":         "#0068DF",
    "Outros 📦":          "#D0D0D0",
    "Pessoal 👤":         "#8B46E5",
    "Presentes 🎁":       "#C94690",
    "Ratos 🐀":           "#DB81C7",
    "Saúde ⚕️":           "#6EF4C8",
    "Taxas 📉":           "#EF4444",
    "Transporte 🚗":      "#007E54",
    "Viagem ✈️":          "#34A7FF",
    "Pgto. de fatura 💳": "#3B3B3B",
}

INSTALLMENT_RE = re.compile(r"\((\d+)\s*/\s*(\d+)\)\s*$")
