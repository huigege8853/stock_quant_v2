from __future__ import annotations

from enum import StrEnum


class StrategyType(StrEnum):
    SELECTION = "selection"
    TIMING = "timing"
    ENTRY = "entry"
    EXIT = "exit"
    PORTFOLIO_CONSTRUCTION = "portfolio_construction"
    AI = "ai"


class StrategyEngineType(StrEnum):
    RULE = "rule"
    MODEL = "model"
    COMPOSITE = "composite"


class LifecycleStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class SignalRole(StrEnum):
    SELECTION = "selection"
    TIMING = "timing"
    ENTRY = "entry"
    EXIT = "exit"
    PORTFOLIO_CONSTRUCTION = "portfolio_construction"
    AI = "ai"


class SignalSide(StrEnum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"
    NA = "na"


class SignalAction(StrEnum):
    SELECT = "select"
    ENTER = "enter"
    EXIT = "exit"
    HOLD = "hold"
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"


class SubjectType(StrEnum):
    INSTRUMENT = "instrument"
    MARKET = "market"
    PORTFOLIO = "portfolio"


class ReasonCode(StrEnum):
    TOP_N_SELECTED = "TOP_N_SELECTED"
    BELOW_MIN_SCORE = "BELOW_MIN_SCORE"
    FEATURE_MISSING = "FEATURE_MISSING"
    NOT_TRADABLE = "NOT_TRADABLE"
    MARKET_RISK_ON = "MARKET_RISK_ON"
    MARKET_RISK_OFF = "MARKET_RISK_OFF"