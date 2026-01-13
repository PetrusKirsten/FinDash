import pandas as pd
from pathlib import Path

# Columns for the transactions CSV file
COLUMNS = ["date", "amount", "description", "category", "type", "user"]

def load_transactions(file_path):
    """Load transactions from CSV. Create file with header if it doesn't exist."""
    path = Path(file_path)
    # If file exists, try to read it
    if path.exists():
        try:
            df = pd.read_csv(path)
        except Exception:
            df = pd.DataFrame(columns=COLUMNS)
    else:
        # Ensure directory exists and create an empty CSV
        path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(columns=COLUMNS)
        df.to_csv(path, index=False)
    # Make sure DataFrame has all required columns
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = []
    return df

def save_transactions(df, file_path):
    """Save transactions DataFrame to CSV."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
