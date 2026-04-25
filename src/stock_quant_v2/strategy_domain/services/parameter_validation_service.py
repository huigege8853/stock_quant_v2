from __future__ import annotations

import math


class ParameterValidationService:
    @staticmethod
    def validate_alpha_selection_params(params: dict) -> None:
        top_n = params["top_n"]
        min_score = params["min_score"]
        weights = params["weights"]
        tradable_flag_pass_values = params.get("tradable_flag_pass_values")

        if top_n < 1:
            raise ValueError("top_n 必须 >= 1")

        if not (0.0 <= min_score <= 1.0):
            raise ValueError("min_score 必须在 [0.0, 1.0] 范围内")

        expected_keys = {"mom", "trend", "low_vol", "tradability"}
        if set(weights.keys()) != expected_keys:
            raise ValueError(f"weights 键必须严格等于 {sorted(expected_keys)}")

        total_weight = sum(float(v) for v in weights.values())
        if not math.isclose(total_weight, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(f"weights 四项之和必须等于 1.0，当前为 {total_weight}")

        if params["require_tradable_flag"]:
            if tradable_flag_pass_values is None or len(tradable_flag_pass_values) == 0:
                raise ValueError(
                    "require_tradable_flag=true 时，必须显式提供 tradable_flag_pass_values。"
                )