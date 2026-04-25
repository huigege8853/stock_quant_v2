from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from stock_quant_v2.strategy_domain.constants import (
    DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION,
    DEFAULT_PARAMETER_VALUES_MARKET_TIMING,
    DEPENDENCY_SPEC_JSON_ALPHA_SELECTION,
    DEPENDENCY_SPEC_JSON_MARKET_TIMING,
    FEATURE_SET_CODE,
    FEATURE_SET_VERSION,
    IMPLEMENTATION_REF_ALPHA_SELECTION,
    IMPLEMENTATION_REF_MARKET_TIMING,
    OUTPUT_CONTRACT_VERSION_SIGNAL_V1,
    PARAMETER_SCHEMA_JSON_ALPHA_SELECTION,
    PARAMETER_SCHEMA_JSON_MARKET_TIMING,
    STRATEGY_CODE_ALPHA_SELECTION,
    STRATEGY_CODE_MARKET_TIMING,
    STRATEGY_NAME_ALPHA_SELECTION,
    STRATEGY_NAME_MARKET_TIMING,
    STRATEGY_VERSION_CODE_V1,
    STRATEGY_VERSION_NO_V1,
)
from stock_quant_v2.strategy_domain.enums import LifecycleStatus, StrategyEngineType, StrategyType
from stock_quant_v2.strategy_domain.repositories import (
    StrategyDefinitionRepository,
    StrategyVersionRepository,
)


def _stable_json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _logic_hash(*parts: str) -> str:
    raw = "||".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def seed_alpha_selection_strategy(session: Session) -> int:
    definition_repo = StrategyDefinitionRepository(session)
    version_repo = StrategyVersionRepository(session)

    definition = definition_repo.get_by_code(STRATEGY_CODE_ALPHA_SELECTION)
    if definition is None:
        definition = definition_repo.create(
            strategy_code=STRATEGY_CODE_ALPHA_SELECTION,
            strategy_name=STRATEGY_NAME_ALPHA_SELECTION,
            strategy_type=StrategyType.SELECTION.value,
            engine_type=StrategyEngineType.RULE.value,
            market_scope="CN_A",
            bar_frequency="1d",
            description="M4 最小可用规则选股策略主链，消费 fs_daily_alpha_v1 输出 selection signal。",
            lifecycle_status=LifecycleStatus.ACTIVE.value,
            owner="system",
            tags_json=["m4", "selection", "rule", FEATURE_SET_CODE, FEATURE_SET_VERSION],
        )

    version = version_repo.get_by_definition_and_version_code(
        strategy_definition_id=definition.id,
        version_code=STRATEGY_VERSION_CODE_V1,
    )
    version = version_repo.upsert_version(
        existing=version,
        strategy_definition_id=definition.id,
        version_code=STRATEGY_VERSION_CODE_V1,
        version_no=STRATEGY_VERSION_NO_V1,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
        implementation_ref=IMPLEMENTATION_REF_ALPHA_SELECTION,
        dependency_spec_json=DEPENDENCY_SPEC_JSON_ALPHA_SELECTION,
        output_contract_version=OUTPUT_CONTRACT_VERSION_SIGNAL_V1,
        default_parameter_values_json=DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION,
        logic_hash=_logic_hash(
            STRATEGY_CODE_ALPHA_SELECTION,
            STRATEGY_VERSION_CODE_V1,
            IMPLEMENTATION_REF_ALPHA_SELECTION,
            _stable_json_dumps(DEPENDENCY_SPEC_JSON_ALPHA_SELECTION),
            _stable_json_dumps(DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION),
            _stable_json_dumps(PARAMETER_SCHEMA_JSON_ALPHA_SELECTION),
        ),
        description="消费 fs_daily_alpha_v1，输出 selection signal。",
    )
    version_repo.deactivate_other_currents(
        strategy_definition_id=definition.id,
        keep_strategy_version_id=version.id,
    )

    schema = version_repo.get_parameter_schema_by_version_id(version.id)
    version_repo.upsert_parameter_schema(
        existing=schema,
        strategy_version_id=version.id,
        schema_version_code="jsonschema_v1",
        parameter_schema_json=PARAMETER_SCHEMA_JSON_ALPHA_SELECTION,
        example_payload_json=DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION,
        validation_notes="weights 四项之和必须严格等于 1.0；top_n 不能超过当日可用样本数。",
    )

    return version.id


def seed_market_timing_strategy(session: Session) -> int:
    definition_repo = StrategyDefinitionRepository(session)
    version_repo = StrategyVersionRepository(session)

    definition = definition_repo.get_by_code(STRATEGY_CODE_MARKET_TIMING)
    if definition is None:
        definition = definition_repo.create(
            strategy_code=STRATEGY_CODE_MARKET_TIMING,
            strategy_name=STRATEGY_NAME_MARKET_TIMING,
            strategy_type=StrategyType.TIMING.value,
            engine_type=StrategyEngineType.RULE.value,
            market_scope="CN_A",
            bar_frequency="1d",
            description="M4 timing skeleton：输入 market_state_payload，输出 market-level timing signal。",
            lifecycle_status=LifecycleStatus.DRAFT.value,
            owner="system",
            tags_json=["m4", "timing", "rule", "market"],
        )

    version = version_repo.get_by_definition_and_version_code(
        strategy_definition_id=definition.id,
        version_code=STRATEGY_VERSION_CODE_V1,
    )
    version = version_repo.upsert_version(
        existing=version,
        strategy_definition_id=definition.id,
        version_code=STRATEGY_VERSION_CODE_V1,
        version_no=STRATEGY_VERSION_NO_V1,
        lifecycle_status=LifecycleStatus.DRAFT.value,
        implementation_ref=IMPLEMENTATION_REF_MARKET_TIMING,
        dependency_spec_json=DEPENDENCY_SPEC_JSON_MARKET_TIMING,
        output_contract_version=OUTPUT_CONTRACT_VERSION_SIGNAL_V1,
        default_parameter_values_json=DEFAULT_PARAMETER_VALUES_MARKET_TIMING,
        logic_hash=_logic_hash(
            STRATEGY_CODE_MARKET_TIMING,
            STRATEGY_VERSION_CODE_V1,
            IMPLEMENTATION_REF_MARKET_TIMING,
            _stable_json_dumps(DEPENDENCY_SPEC_JSON_MARKET_TIMING),
            _stable_json_dumps(DEFAULT_PARAMETER_VALUES_MARKET_TIMING),
            _stable_json_dumps(PARAMETER_SCHEMA_JSON_MARKET_TIMING),
        ),
        description="输入 market_state_payload，输出 market-level timing signal。",
    )
    version_repo.deactivate_other_currents(
        strategy_definition_id=definition.id,
        keep_strategy_version_id=version.id,
    )

    schema = version_repo.get_parameter_schema_by_version_id(version.id)
    version_repo.upsert_parameter_schema(
        existing=schema,
        strategy_version_id=version.id,
        schema_version_code="jsonschema_v1",
        parameter_schema_json=PARAMETER_SCHEMA_JSON_MARKET_TIMING,
        example_payload_json=DEFAULT_PARAMETER_VALUES_MARKET_TIMING,
        validation_notes="timing skeleton 当前不绑定具体 market state 表；先由上游显式提供 market_state_payload。",
    )

    return version.id