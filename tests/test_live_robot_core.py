from __future__ import annotations

import pytest

from engine.live_robot_core import (
    LiveRobotCore,
    RobotConfig,
    RobotStatus,
    SignalEvent,
    TaskStatus,
    TradeLifecycleStatus,
)


def build_robot() -> LiveRobotCore:
    return LiveRobotCore(
        RobotConfig(
            scan_interval_seconds=60,
            heartbeat_interval_seconds=30,
            max_queue_size=10,
            max_task_retries=2,
            markets=("CRYPTO", "COMMODITY"),
        )
    )


def test_robot_start_pause_resume_stop() -> None:
    robot = build_robot()

    robot.start()
    assert robot.status == RobotStatus.RUNNING

    robot.pause()
    assert robot.status == RobotStatus.PAUSED

    robot.resume()
    assert robot.status == RobotStatus.RUNNING

    robot.stop()
    assert robot.status == RobotStatus.STOPPED


def test_schedule_and_run_market_scan() -> None:
    robot = build_robot()
    robot.market_watcher.register_provider(
        "CRYPTO",
        lambda: [{"symbol": "BTC/USDT", "price": 100}],
    )
    robot.start()

    task_id = robot.schedule_scan("CRYPTO")
    task = robot.run_next_task()

    assert task is not None
    assert task.task_id == task_id
    assert task.status == TaskStatus.COMPLETED
    assert task.payload["result_count"] == 1


def test_task_retry_and_failure() -> None:
    robot = build_robot()
    robot.market_watcher.register_provider(
        "CRYPTO",
        lambda: (_ for _ in ()).throw(RuntimeError("feed error")),
    )
    robot.start()
    robot.schedule_scan("CRYPTO")

    first = robot.run_next_task()
    second = robot.run_next_task()

    assert first is not None
    assert first.status == TaskStatus.FAILED
    assert second is first
    assert second.attempts == 2
    assert second.error == "feed error"


def test_signal_dispatcher() -> None:
    robot = build_robot()
    received: list[str] = []
    robot.signal_dispatcher.register_handler(
        lambda signal: received.append(signal.symbol)
    )
    robot.start()

    results = robot.publish_signal(
        SignalEvent(
            symbol="BTC/USDT",
            market="CRYPTO",
            signal="BUY",
            score=75,
        )
    )

    assert received == ["BTC/USDT"]
    assert results == [None]
    assert len(robot.signal_dispatcher.history()) == 1


def test_trade_lifecycle_and_pnl() -> None:
    robot = build_robot()
    robot.start()
    trade = robot.create_trade(
        symbol="BTC/USDT",
        market="CRYPTO",
        side="LONG",
        quantity=2,
        entry_price=100,
        stop_price=95,
        target_price=110,
    )

    robot.transition_trade(
        trade.trade_id,
        TradeLifecycleStatus.QUEUED,
        reason="signal accepted",
    )
    robot.transition_trade(
        trade.trade_id,
        TradeLifecycleStatus.APPROVED,
        reason="trade gate approved",
    )
    robot.transition_trade(
        trade.trade_id,
        TradeLifecycleStatus.OPEN,
        reason="paper order filled",
    )
    robot.transition_trade(
        trade.trade_id,
        TradeLifecycleStatus.CLOSED,
        reason="target reached",
        exit_price=110,
    )

    assert trade.status == TradeLifecycleStatus.CLOSED
    assert trade.realized_pnl == 20
    assert len(trade.history) == 4


def test_invalid_trade_transition() -> None:
    robot = build_robot()
    robot.start()
    trade = robot.create_trade(
        symbol="ETH/USDT",
        market="CRYPTO",
        side="LONG",
        quantity=1,
        entry_price=100,
    )

    with pytest.raises(ValueError):
        robot.transition_trade(
            trade.trade_id,
            TradeLifecycleStatus.OPEN,
        )


def test_heartbeat_and_report() -> None:
    robot = build_robot()
    robot.start()

    heartbeat = robot.heartbeat()
    report = robot.robot_report()

    assert heartbeat["status"] == "RUNNING"
    assert heartbeat["pending_tasks"] == 0
    assert report["status"] == "RUNNING"
    assert report["last_heartbeat_at"] is not None
    assert report["log_count"] >= 2


def test_running_guard() -> None:
    robot = build_robot()

    with pytest.raises(RuntimeError):
        robot.schedule_scan("CRYPTO")
