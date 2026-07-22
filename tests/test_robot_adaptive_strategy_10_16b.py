from engine.robot_engine import RobotConfig, RobotEngine


def make_robot(config=None):
    robot = RobotEngine.__new__(RobotEngine)
    robot.config = config or RobotConfig()
    from engine.market_regime_engine import MarketRegimeEngine
    from engine.adaptive_strategy_engine import AdaptiveStrategyEngine
    robot.market_regime_engine = MarketRegimeEngine()
    robot.adaptive_strategy_engine = AdaptiveStrategyEngine(
        base_minimum_entry_score=robot.config.minimum_score,
        base_trailing_atr_multiplier=robot.config.atr_trailing_multiplier,
        base_max_holding_hours=robot.config.max_holding_hours,
    )
    return robot


def test_disabled_adaptive_strategy_returns_neutral_policy():
    robot = make_robot(RobotConfig(adaptive_strategy_enabled=False))
    policy = robot.get_adaptive_strategy_policy(None)
    assert policy["profile"] == "DISABLED"
    assert policy["position_size_multiplier"] == 1.0
    assert policy["minimum_entry_score"] == robot.config.minimum_score


def test_missing_market_frame_is_blocked_when_adaptive_enabled():
    robot = make_robot()
    policy = robot.get_adaptive_strategy_policy(None)
    assert not policy["allow_new_positions"]
    assert policy["profile"] == "WAIT_FOR_DATA"
