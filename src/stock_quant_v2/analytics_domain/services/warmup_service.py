from __future__ import annotations


class WarmupService:
    @staticmethod
    def is_warmup_ready(observation_count: int, warmup_bars: int) -> bool:
        if warmup_bars <= 0:
            return True
        return observation_count >= warmup_bars