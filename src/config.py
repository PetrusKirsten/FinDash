OWNER_LABELS = {
    "petrus" : "Petrus",
    "partner": "Melissa",
    "both"   : "Ambos",
}

PAYER_LABELS = {
    "petrus" : "Petrus",
    "partner": "Melissa",
}

def owner_options():
    # lista de tuplas (id, label)
    return [(k, v) for k, v in OWNER_LABELS.items()]

def payer_options():
    return [(k, v) for k, v in PAYER_LABELS.items()]
