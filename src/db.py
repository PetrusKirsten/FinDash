from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "finance.db"

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)

def init_db() -> None:
    SQLModel.metadata.create_all(engine)

def get_session() -> Session:
    return Session(engine)
