from engine.adaptive_strategy_engine import AdaptiveStrategyEngine


def regime(name, *, confidence=80.0, volatility="MEDIUM", allow=True):
    return {
        "regime": name,
        "confidence": confidence,
        "volatility_level": volatility,
        "allow_new_positions": allow,
    }


def test_bull_policy_is_growth_oriented():
    policy = AdaptiveStrategyEngine().build_policy(regime("BULL"))
    assert policy.allow_new_positions
    assert policy.profile == "TREND_AGGRESSIVE"
    assert policy.minimum_entry_score < 75
    assert policy.target2_multiplier > 1
    assert policy.position_size_multiplier == 1.0


def test_sideways_policy_is_more_selective_and_shorter_targeted():
    policy = AdaptiveStrategyEngine().build_policy(regime("SIDEWAYS"))
    assert policy.allow_new_positions
    assert policy.minimum_entry_score > 75
    assert policy.position_size_multiplier < 1
    assert policy.target1_multiplier < 1
    assert policy.smart_exit_score_delta < 0


def test_bear_policy_blocks_new_positions():
    policy = AdaptiveStrategyEngine().build_policy(regime("BEAR", allow=False))
    assert not policy.allow_new_positions
    assert policy.position_size_multiplier == 0
    assert policy.profile == "CAPITAL_PROTECTION"


def test_low_confidence_blocks_even_bull_regime():
    policy = AdaptiveStrategyEngine().build_policy(regime("BULL", confidence=40))
    assert not policy.allow_new_positions
    assert policy.position_size_multiplier == 0
    assert policy.minimum_entry_score >= 90


def test_extreme_volatility_reduces_size_and_raises_threshold():
    normal = AdaptiveStrategyEngine().build_policy(regime("RECOVERY", volatility="MEDIUM"))
    extreme = AdaptiveStrategyEngine().build_policy(regime("RECOVERY", volatility="EXTREME"))
    assert extreme.position_size_multiplier < normal.position_size_multiplier
    assert extreme.minimum_entry_score > normal.minimum_entry_score


def test_adjust_targets_preserves_entry_and_scales_reward_distance():
    engine = AdaptiveStrategyEngine()
    policy = engine.build_policy(regime("SIDEWAYS"))
    target1, target2 = engine.adjust_targets(100, 110, 120, policy)
    assert target1 == 108
    assert target2 == 115
