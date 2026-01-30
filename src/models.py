from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field


class Owner(str, Enum):
    petrus = "petrus"
    partner = "partner"
    both = "both"


class Payer(str, Enum):
    petrus = "petrus"
    partner = "partner"


class SplitMode(str, Enum):
    none = "none"
    equal = "equal"
    other_100 = "other_100"


class AccountType(str, Enum):
    checking = "checking"
    credit = "credit"
    savings = "savings"


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    owner: Owner = Field(default=Owner.petrus)
    type: AccountType = Field(default=AccountType.checking)
    initial_balance: float = Field(default=0.0)


class Category(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    type: str  # income | expense | investment | transfer


class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    date: date
    amount: float
    description: str = Field(default="")

    account_id: int
    category_id: int

    owner: Owner = Field(default=Owner.petrus)
    paid_by: Payer = Field(default=Payer.petrus)

    split_mode: SplitMode = Field(default=SplitMode.none)

    card_label: Optional[str] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
