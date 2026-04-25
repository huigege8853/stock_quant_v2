from stock_quant_v2.analytics_domain.services.warmup_service import WarmupService


def test_is_warmup_ready_true_when_enough_observations():
    assert WarmupService.is_warmup_ready(observation_count=20, warmup_bars=20) is True


def test_is_warmup_ready_false_when_insufficient_observations():
    assert WarmupService.is_warmup_ready(observation_count=19, warmup_bars=20) is False