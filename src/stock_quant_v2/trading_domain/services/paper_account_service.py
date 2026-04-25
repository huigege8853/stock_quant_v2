from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.constants import (
    DEFAULT_BASE_CURRENCY,
    DEFAULT_INITIAL_CASH,
    DEFAULT_MARKET_CODE,
    DEFAULT_PAPER_ACCOUNT_CODE,
)
from stock_quant_v2.trading_domain.dto.paper_account import PaperAccountCreateDTO
from stock_quant_v2.trading_domain.repositories.paper_account_repository import (
    PaperAccountRepository,
)


class PaperAccountService:
    def __init__(self, session: Session):
        self.session = session
        self.account_repo = PaperAccountRepository(session)

    def get_or_create_default_account(
        self,
        account_code: str = DEFAULT_PAPER_ACCOUNT_CODE,
        account_name: str = "CN A Default Paper Account",
        market_code: str = DEFAULT_MARKET_CODE,
        base_currency: str = DEFAULT_BASE_CURRENCY,
        initial_cash: Decimal = DEFAULT_INITIAL_CASH,
    ):
        dto = PaperAccountCreateDTO(
            account_code=account_code,
            account_name=account_name,
            market_code=market_code,
            base_currency=base_currency,
            initial_cash=initial_cash,
            account_type="PAPER",
            status="ACTIVE",
            opened_at=datetime.now(timezone.utc),
        )
        return self.account_repo.get_or_create(dto)