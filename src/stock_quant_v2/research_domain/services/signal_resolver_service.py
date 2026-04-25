from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class SignalSummary:
    signal_run_id: int
    selected_count: int
    eligible_universe_size: int | None
    score_min: Any | None
    score_max: Any | None
    score_avg: Any | None


class SignalResolverService:
    def __init__(self, session: Session):
        self.session = session

    def _columns(self, table_name: str) -> set[str]:
        rows = self.session.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).scalars().all()

        if not rows:
            raise RuntimeError(f"table not found or has no columns: {table_name}")

        return set(rows)

    @staticmethod
    def _pick(
        columns: set[str],
        candidates: list[str],
        *,
        required: bool = True,
    ) -> str | None:
        for candidate in candidates:
            if candidate in columns:
                return candidate

        if required:
            raise RuntimeError(
                "none of candidate columns exists: " + ", ".join(candidates)
            )
        return None

    def resolve_strategy_version_id(
        self,
        *,
        strategy_code: str,
        version_code: str,
    ) -> int:
        sv_cols = self._columns("strategy_version")

        direct_strategy_code_col = self._pick(
            sv_cols,
            ["strategy_code", "code"],
            required=False,
        )
        version_col = self._pick(
            sv_cols,
            ["version_code", "version", "code"],
            required=True,
        )

        if direct_strategy_code_col:
            row = self.session.execute(
                text(
                    f"""
                    select id
                    from strategy_version
                    where {direct_strategy_code_col} = :strategy_code
                      and {version_col} = :version_code
                    order by id desc
                    limit 1
                    """
                ),
                {
                    "strategy_code": strategy_code,
                    "version_code": version_code,
                },
            ).first()

            if row:
                return int(row[0])

        sd_cols = self._columns("strategy_definition")

        definition_fk_col = self._pick(
            sv_cols,
            ["strategy_definition_id", "definition_id", "strategy_id"],
            required=True,
        )
        strategy_code_col = self._pick(
            sd_cols,
            ["strategy_code", "code"],
            required=True,
        )

        row = self.session.execute(
            text(
                f"""
                select sv.id
                from strategy_version sv
                join strategy_definition sd
                  on sv.{definition_fk_col} = sd.id
                where sd.{strategy_code_col} = :strategy_code
                  and sv.{version_col} = :version_code
                order by sv.id desc
                limit 1
                """
            ),
            {
                "strategy_code": strategy_code,
                "version_code": version_code,
            },
        ).first()

        if not row:
            raise RuntimeError(
                f"strategy_version not found: {strategy_code}:{version_code}"
            )

        return int(row[0])

    def resolve_signal_run_id(
        self,
        *,
        strategy_version_id: int,
        as_of_date: date,
        effective_date: date | None,
        source_signal_run_id: int | None,
    ) -> int:
        if source_signal_run_id is not None:
            return source_signal_run_id

        sig_cols = self._columns("strategy_signal")

        strategy_version_col = self._pick(
            sig_cols,
            ["strategy_version_id"],
            required=True,
        )
        as_of_col = self._pick(
            sig_cols,
            ["as_of_date", "signal_date", "trade_date"],
            required=True,
        )
        effective_col = self._pick(
            sig_cols,
            ["effective_date"],
            required=False,
        )

        where_parts = [
            f"{strategy_version_col} = :strategy_version_id",
            f"{as_of_col} = :as_of_date",
        ]
        params: dict[str, Any] = {
            "strategy_version_id": strategy_version_id,
            "as_of_date": as_of_date,
        }

        if effective_date is not None and effective_col:
            where_parts.append(f"{effective_col} = :effective_date")
            params["effective_date"] = effective_date

        row = self.session.execute(
            text(
                f"""
                select run_id
                from strategy_signal
                where {" and ".join(where_parts)}
                group by run_id
                order by run_id desc
                limit 1
                """
            ),
            params,
        ).first()

        if not row:
            raise RuntimeError(
                "strategy_signal run not found for "
                f"strategy_version_id={strategy_version_id}, "
                f"as_of_date={as_of_date}, effective_date={effective_date}"
            )

        return int(row[0])

    def load_signal_summary(
        self,
        *,
        signal_run_id: int,
        strategy_version_id: int,
        as_of_date: date,
        effective_date: date | None,
        include_reason_codes: list[str],
        exclude_reason_codes: list[str],
    ) -> SignalSummary:
        sig_cols = self._columns("strategy_signal")

        strategy_version_col = self._pick(
            sig_cols,
            ["strategy_version_id"],
            required=True,
        )
        as_of_col = self._pick(
            sig_cols,
            ["as_of_date", "signal_date", "trade_date"],
            required=True,
        )
        effective_col = self._pick(
            sig_cols,
            ["effective_date"],
            required=False,
        )
        reason_col = self._pick(
            sig_cols,
            ["reason_code"],
            required=False,
        )

        # M4 alpha_selection:v1 的正式研究评分字段。
        # 当前样例确认 raw_score = 0.84932365，与 M4 已验收 score_max 一致。
        score_col = self._pick(
            sig_cols,
            [
                "raw_score",
                "score",
                "signal_score",
                "rank_score",
                "score_value",
            ],
            required=False,
        )

        universe_size_col = self._pick(
            sig_cols,
            ["universe_size", "eligible_universe_size"],
            required=False,
        )

        where_parts = [
            "run_id = :signal_run_id",
            f"{strategy_version_col} = :strategy_version_id",
            f"{as_of_col} = :as_of_date",
        ]
        params: dict[str, Any] = {
            "signal_run_id": signal_run_id,
            "strategy_version_id": strategy_version_id,
            "as_of_date": as_of_date,
        }

        if effective_date is not None and effective_col:
            where_parts.append(f"{effective_col} = :effective_date")
            params["effective_date"] = effective_date

        if reason_col and include_reason_codes:
            placeholders = []
            for i, code in enumerate(include_reason_codes):
                key = f"include_reason_{i}"
                placeholders.append(f":{key}")
                params[key] = code
            where_parts.append(f"{reason_col} in ({', '.join(placeholders)})")

        if reason_col and exclude_reason_codes:
            placeholders = []
            for i, code in enumerate(exclude_reason_codes):
                key = f"exclude_reason_{i}"
                placeholders.append(f":{key}")
                params[key] = code
            where_parts.append(f"{reason_col} not in ({', '.join(placeholders)})")

        score_expr = (
            f"""
            min({score_col}) as score_min,
            max({score_col}) as score_max,
            avg({score_col}) as score_avg
            """
            if score_col
            else """
            null as score_min,
            null as score_max,
            null as score_avg
            """
        )

        universe_expr = (
            f"max({universe_size_col}) as eligible_universe_size"
            if universe_size_col
            else "null as eligible_universe_size"
        )

        row = self.session.execute(
            text(
                f"""
                select
                    count(*) as selected_count,
                    {universe_expr},
                    {score_expr}
                from strategy_signal
                where {" and ".join(where_parts)}
                """
            ),
            params,
        ).mappings().one()

        eligible_universe_size = row["eligible_universe_size"]
        if eligible_universe_size is not None:
            eligible_universe_size = int(eligible_universe_size)

        return SignalSummary(
            signal_run_id=signal_run_id,
            selected_count=int(row["selected_count"] or 0),
            eligible_universe_size=eligible_universe_size,
            score_min=row["score_min"],
            score_max=row["score_max"],
            score_avg=row["score_avg"],
        )