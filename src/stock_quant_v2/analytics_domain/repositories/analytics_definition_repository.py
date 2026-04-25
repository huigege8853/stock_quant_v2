from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.analytics.factor_definition import MetaFactorDefinition
from stock_quant_v2.db.models.analytics.feature_definition import MetaFeatureDefinition
from stock_quant_v2.db.models.analytics.feature_set_definition import MetaFeatureSetDefinition
from stock_quant_v2.db.models.analytics.indicator_definition import MetaIndicatorDefinition
from stock_quant_v2.db.models.analytics.label_definition import MetaLabelDefinition


class AnalyticsDefinitionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active_indicator_definitions(self, indicator_codes: list[str] | None = None) -> list[MetaIndicatorDefinition]:
        stmt = select(MetaIndicatorDefinition).where(MetaIndicatorDefinition.is_active.is_(True))
        if indicator_codes:
            stmt = stmt.where(MetaIndicatorDefinition.indicator_code.in_(indicator_codes))
        stmt = stmt.order_by(MetaIndicatorDefinition.id.asc())
        return list(self.session.execute(stmt).scalars().all())

    def upsert_indicator_definition(self, payload: dict) -> MetaIndicatorDefinition:
        stmt = select(MetaIndicatorDefinition).where(
            MetaIndicatorDefinition.indicator_code == payload["indicator_code"],
            MetaIndicatorDefinition.version == payload.get("version", "v1"),
        )
        existing = self.session.execute(stmt).scalar_one_or_none()

        if existing is None:
            existing = MetaIndicatorDefinition(**payload)
            self.session.add(existing)
        else:
            for key, value in payload.items():
                setattr(existing, key, value)

        self.session.flush()
        return existing

    def get_active_factor_definitions(self, factor_codes: list[str] | None = None) -> list[MetaFactorDefinition]:
        stmt = select(MetaFactorDefinition).where(MetaFactorDefinition.is_active.is_(True))
        if factor_codes:
            stmt = stmt.where(MetaFactorDefinition.factor_code.in_(factor_codes))
        stmt = stmt.order_by(MetaFactorDefinition.id.asc())
        return list(self.session.execute(stmt).scalars().all())

    def upsert_factor_definition(self, payload: dict) -> MetaFactorDefinition:
        stmt = select(MetaFactorDefinition).where(
            MetaFactorDefinition.factor_code == payload["factor_code"],
            MetaFactorDefinition.version == payload.get("version", "v1"),
        )
        existing = self.session.execute(stmt).scalar_one_or_none()

        if existing is None:
            existing = MetaFactorDefinition(**payload)
            self.session.add(existing)
        else:
            for key, value in payload.items():
                setattr(existing, key, value)

        self.session.flush()
        return existing

    def get_active_feature_definitions(self, feature_codes: list[str] | None = None) -> list[MetaFeatureDefinition]:
        stmt = select(MetaFeatureDefinition).where(MetaFeatureDefinition.is_active.is_(True))
        if feature_codes:
            stmt = stmt.where(MetaFeatureDefinition.feature_code.in_(feature_codes))
        stmt = stmt.order_by(MetaFeatureDefinition.id.asc())
        return list(self.session.execute(stmt).scalars().all())

    def upsert_feature_definition(self, payload: dict) -> MetaFeatureDefinition:
        stmt = select(MetaFeatureDefinition).where(
            MetaFeatureDefinition.feature_code == payload["feature_code"],
            MetaFeatureDefinition.version == payload.get("version", "v1"),
        )
        existing = self.session.execute(stmt).scalar_one_or_none()

        if existing is None:
            existing = MetaFeatureDefinition(**payload)
            self.session.add(existing)
        else:
            for key, value in payload.items():
                setattr(existing, key, value)

        self.session.flush()
        return existing

    def get_active_feature_set_definitions(self, feature_set_codes: list[str] | None = None) -> list[MetaFeatureSetDefinition]:
        stmt = select(MetaFeatureSetDefinition).where(MetaFeatureSetDefinition.is_active.is_(True))
        if feature_set_codes:
            stmt = stmt.where(MetaFeatureSetDefinition.feature_set_code.in_(feature_set_codes))
        stmt = stmt.order_by(MetaFeatureSetDefinition.id.asc())
        return list(self.session.execute(stmt).scalars().all())

    def upsert_feature_set_definition(self, payload: dict) -> MetaFeatureSetDefinition:
        stmt = select(MetaFeatureSetDefinition).where(
            MetaFeatureSetDefinition.feature_set_code == payload["feature_set_code"],
            MetaFeatureSetDefinition.version == payload.get("version", "v1"),
        )
        existing = self.session.execute(stmt).scalar_one_or_none()

        if existing is None:
            existing = MetaFeatureSetDefinition(**payload)
            self.session.add(existing)
        else:
            for key, value in payload.items():
                setattr(existing, key, value)

        self.session.flush()
        return existing

    def get_active_label_definitions(self, label_codes: list[str] | None = None) -> list[MetaLabelDefinition]:
        stmt = select(MetaLabelDefinition).where(MetaLabelDefinition.is_active.is_(True))
        if label_codes:
            stmt = stmt.where(MetaLabelDefinition.label_code.in_(label_codes))
        stmt = stmt.order_by(MetaLabelDefinition.id.asc())
        return list(self.session.execute(stmt).scalars().all())

    def upsert_label_definition(self, payload: dict) -> MetaLabelDefinition:
        stmt = select(MetaLabelDefinition).where(
            MetaLabelDefinition.label_code == payload["label_code"],
            MetaLabelDefinition.version == payload.get("version", "v1"),
        )
        existing = self.session.execute(stmt).scalar_one_or_none()

        if existing is None:
            existing = MetaLabelDefinition(**payload)
            self.session.add(existing)
        else:
            for key, value in payload.items():
                setattr(existing, key, value)

        self.session.flush()
        return existing