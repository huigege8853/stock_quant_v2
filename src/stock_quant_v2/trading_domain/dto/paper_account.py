from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class PaperAccountCreateDTO:
    account_code: str
    account_name: str
    market_code: str
    base_currency: str
    initial_cash: Decimal
    account_type: str = "PAPER"
    status: str = "ACTIVE"
    opened_at: datetime | None = None


@dataclass(frozen=True)
class PaperAccountDTO:
    id: int
    account_code: str
    account_name: str
    account_type: str
    market_code: str
    base_currency: str
    initial_cash: Decimal
    status: str