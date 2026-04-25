from __future__ import annotations

import math

import pandas as pd


class RuleSelectionService:
    @staticmethod
    def build_feature_matrix(
        feature_rows: list[tuple[int, str, object]],
        required_feature_codes: list[str],
    ) -> pd.DataFrame:
        if not feature_rows:
            raise RuntimeError("未读取到 feature rows。")

        df = pd.DataFrame(
            feature_rows,
            columns=["instrument_id", "feature_code", "feature_value_numeric"],
        )

        pivot = (
            df.pivot_table(
                index="instrument_id",
                columns="feature_code",
                values="feature_value_numeric",
                aggfunc="last",
            )
            .reset_index()
            .rename_axis(None, axis=1)
        )

        missing_cols = [col for col in required_feature_codes if col not in pivot.columns]
        if missing_cols:
            raise RuntimeError(f"feature snapshot 缺少必须特征列: {missing_cols}")

        return pivot

    @staticmethod
    def compute_alpha_selection(
        feature_df: pd.DataFrame,
        runtime_params: dict,
    ) -> pd.DataFrame:
        work = feature_df.copy()

        numeric_cols = [
            "feat_mom_20",
            "feat_trend_strength_20",
            "feat_volatility_rank_20",
            "feat_tradability_score",
            "feat_tradable_flag",
        ]
        for col in numeric_cols:
            work[col] = pd.to_numeric(work[col], errors="coerce")

        if runtime_params["require_tradable_flag"]:
            pass_values = runtime_params["tradable_flag_pass_values"]
            work = work[work["feat_tradable_flag"].isin(pass_values)]
            if work.empty:
                raise RuntimeError(
                    "应用 tradable_flag 过滤后无可用样本。"
                    f" pass_values={pass_values}"
                )

        work = work.dropna(
            subset=[
                "feat_mom_20",
                "feat_trend_strength_20",
                "feat_volatility_rank_20",
                "feat_tradability_score",
            ]
        )

        if work.empty:
            raise RuntimeError("经过 feature non-null 过滤后，没有可用样本。")

        work["mom_pct"] = work["feat_mom_20"].rank(method="average", pct=True, ascending=True)
        work["trend_pct"] = work["feat_trend_strength_20"].rank(method="average", pct=True, ascending=True)
        work["tradability_pct"] = work["feat_tradability_score"].rank(method="average", pct=True, ascending=True)
        work["low_vol_pct"] = work["feat_volatility_rank_20"].rank(method="average", pct=True, ascending=False)

        weights = runtime_params["weights"]
        work["raw_score"] = (
            weights["mom"] * work["mom_pct"]
            + weights["trend"] * work["trend_pct"]
            + weights["low_vol"] * work["low_vol_pct"]
            + weights["tradability"] * work["tradability_pct"]
        )

        raw_min = float(work["raw_score"].min())
        raw_max = float(work["raw_score"].max())

        if math.isclose(raw_min, raw_max, rel_tol=0.0, abs_tol=1e-12):
            work["normalized_score"] = 1.0
        else:
            work["normalized_score"] = (work["raw_score"] - raw_min) / (raw_max - raw_min)

        work = work.sort_values(["raw_score", "instrument_id"], ascending=[False, True]).reset_index(drop=True)
        work["rank_in_batch"] = work.index + 1
        work["universe_size"] = len(work)

        selected = work[work["normalized_score"] >= runtime_params["min_score"]].copy()
        selected = selected.head(runtime_params["top_n"]).copy()
        selected["confidence_score"] = selected["normalized_score"]
        return selected