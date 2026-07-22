from engine.robot_engine import RobotConfig, RobotEngine
from engine.market_regime_engine import MarketRegimeEngine
from engine.multi_timeframe_intelligence import MultiTimeframeIntelligence


def make_robot(config=None):
    robot = RobotEngine.__new__(RobotEngine)
    robot.config = config or RobotConfig()
    robot.market_regime_engine = MarketRegimeEngine()
    robot.multi_timeframe_intelligence = MultiTimeframeIntelligence(regime_engine=robot.market_regime_engine)
    return robot


def test_missing_frames_preserve_backward_compatibility():
    result = make_robot().get_multi_timeframe_result(None)
    assert result["allow_new_positions"] is True
    assert result["position_size_multiplier"] == 1.0


def test_disabled_multi_timeframe_is_neutral():
    result = make_robot(RobotConfig(multi_timeframe_intelligence_enabled=False)).get_multi_timeframe_result({})
    assert result["dominant_regime"] == "DISABLED"
    assert result["minimum_entry_score_delta"] == 0.0
