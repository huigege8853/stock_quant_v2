from sqlalchemy.orm import Session

from stock_quant_v2.db.models.trading import TradingPaperAccount
from stock_quant_v2.trading_domain.dto.paper_account import PaperAccountCreateDTO


class PaperAccountRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, account_id: int) -> TradingPaperAccount | None:
        return (
            self.session.query(TradingPaperAccount)
            .filter(TradingPaperAccount.id == account_id)
            .one_or_none()
        )

    def get_by_code(self, account_code: str) -> TradingPaperAccount | None:
        return (
            self.session.query(TradingPaperAccount)
            .filter(TradingPaperAccount.account_code == account_code)
            .one_or_none()
        )

    def create(self, dto: PaperAccountCreateDTO) -> TradingPaperAccount:
        obj = TradingPaperAccount(
            account_code=dto.account_code,
            account_name=dto.account_name,
            account_type=dto.account_type,
            market_code=dto.market_code,
            base_currency=dto.base_currency,
            initial_cash=dto.initial_cash,
            status=dto.status,
            opened_at=dto.opened_at,
        )
        self.session.add(obj)
        self.session.flush()
        return obj

    def get_or_create(self, dto: PaperAccountCreateDTO) -> TradingPaperAccount:
        existing = self.get_by_code(dto.account_code)
        if existing is not None:
            return existing
        return self.create(dto)