from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from stock_quant_v2.db.naming import NAMING_CONVENTION


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)