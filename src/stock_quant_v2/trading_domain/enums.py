from enum import StrEnum


class PaperAccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


class PaperPortfolioStatus(StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


class PortfolioConstructionMode(StrEnum):
    EQUAL_WEIGHT_SELECTED = "EQUAL_WEIGHT_SELECTED"


class RebalanceFrequency(StrEnum):
    DAILY = "DAILY"


class TargetSide(StrEnum):
    LONG = "LONG"
    FLAT = "FLAT"


class TargetPositionStatus(StrEnum):
    PENDING = "PENDING"
    ORDERED = "ORDERED"
    SKIPPED = "SKIPPED"
    CANCELED = "CANCELED"


class TargetSource(StrEnum):
    SIGNAL_RUN = "SIGNAL_RUN"
    SCREEN_RESULT = "SCREEN_RESULT"
    MANUAL = "MANUAL"


class PaperOrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class PaperOrderType(StrEnum):
    MARKET = "MARKET"


class PriceFillRule(StrEnum):
    NEXT_OPEN = "NEXT_OPEN"


class TimeInForce(StrEnum):
    DAY = "DAY"


class PaperOrderStatus(StrEnum):
    NEW = "NEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"


class PaperFillStatus(StrEnum):
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"


class PaperPositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PaperLedgerEventType(StrEnum):
    TARGET_CREATED = "TARGET_CREATED"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_REJECTED = "ORDER_REJECTED"
    FILL_COMPLETED = "FILL_COMPLETED"
    POSITION_UPDATED = "POSITION_UPDATED"
    SNAPSHOT_CREATED = "SNAPSHOT_CREATED"
    CASH_CHANGED = "CASH_CHANGED"
    QUALITY_CHECKED = "QUALITY_CHECKED"