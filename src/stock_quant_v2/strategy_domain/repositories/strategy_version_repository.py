from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.strategy.parameter_schema import StrategyParameterSchema
from stock_quant_v2.db.models.strategy.strategy_version import StrategyVersion


class StrategyVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_definition_and_version_code(
        self,
        *,
        strategy_definition_id: int,
        version_code: str,
    ) -> StrategyVersion | None:
        return self._session.execute(
            select(StrategyVersion).where(
                StrategyVersion.strategy_definition_id == strategy_definition_id,
                StrategyVersion.version_code == version_code,
            )
        ).scalar_one_or_none()

    def deactivate_other_currents(
        self,
        *,
        strategy_definition_id: int,
        keep_strategy_version_id: int,
    ) -> None:
        self._session.query(StrategyVersion).filter(
            StrategyVersion.strategy_definition_id == strategy_definition_id,
            StrategyVersion.id != keep_strategy_version_id,
            StrategyVersion.is_current.is_(True),
        ).update({"is_current": False}, synchronize_session=False)

    def upsert_version(
        self,
        *,
        existing: StrategyVersion | None,
        strategy_definition_id: int,
        version_code: str,
        version_no: int,
        lifecycle_status: str,
        implementation_ref: str,
        dependency_spec_json: dict,
        output_contract_version: str,
        default_parameter_values_json: dict,
        logic_hash: str,
        description: str | None,
    ) -> StrategyVersion:
        if existing is None:
            row = StrategyVersion(
                strategy_definition_id=strategy_definition_id,
                version_code=version_code,
                version_no=version_no,
                is_current=True,
                lifecycle_status=lifecycle_status,
                implementation_ref=implementation_ref,
                dependency_spec_json=dependency_spec_json,
                output_contract_version=output_contract_version,
                default_parameter_values_json=default_parameter_values_json,
                logic_hash=logic_hash,
                description=description,
            )
            self._session.add(row)
            self._session.flush()
            return row

        existing.version_no = version_no
        existing.is_current = True
        existing.lifecycle_status = lifecycle_status
        existing.implementation_ref = implementation_ref
        existing.dependency_spec_json = dependency_spec_json
        existing.output_contract_version = output_contract_version
        existing.default_parameter_values_json = default_parameter_values_json
        existing.logic_hash = logic_hash
        existing.description = description
        self._session.flush()
        return existing

    def get_parameter_schema_by_version_id(
        self,
        strategy_version_id: int,
    ) -> StrategyParameterSchema | None:
        return self._session.execute(
            select(StrategyParameterSchema).where(
                StrategyParameterSchema.strategy_version_id == strategy_version_id
            )
        ).scalar_one_or_none()

    def upsert_parameter_schema(
        self,
        *,
        existing: StrategyParameterSchema | None,
        strategy_version_id: int,
        schema_version_code: str,
        parameter_schema_json: dict,
        example_payload_json: dict | None,
        validation_notes: str | None,
    ) -> StrategyParameterSchema:
        if existing is None:
            row = StrategyParameterSchema(
                strategy_version_id=strategy_version_id,
                schema_version_code=schema_version_code,
                parameter_schema_json=parameter_schema_json,
                example_payload_json=example_payload_json,
                validation_notes=validation_notes,
            )
            self._session.add(row)
            self._session.flush()
            return row

        existing.schema_version_code = schema_version_code
        existing.parameter_schema_json = parameter_schema_json
        existing.example_payload_json = example_payload_json
        existing.validation_notes = validation_notes
        self._session.flush()
        return existing