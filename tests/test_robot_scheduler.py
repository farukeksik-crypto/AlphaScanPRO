from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from engine.robot_scheduler import (
    RobotScheduler,
    ScheduledJob,
    SchedulerConfig,
    SchedulerState,
)


def now():
    return datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


class FakeLiveData:
    def __init__(self):
        self.started = False
        self.stopped = False
        self._event = asyncio.Event()

    async def run_forever(self):
        self.started = True
        await self._event.wait()

    async def stop(self):
        self.stopped = True
        self._event.set()

    def dashboard(self):
        return {"started": self.started, "stopped": self.stopped}


class FakePaperTrading:
    def dashboard(self):
        return {"equity": 10000}


def test_config_validation():
    with pytest.raises(ValueError):
        SchedulerConfig(heartbeat_interval=0)
    with pytest.raises(ValueError):
        SchedulerConfig(max_consecutive_failures=0)


def test_add_job():
    scheduler = RobotScheduler()
    job = scheduler.add_job("scan", lambda: None, interval_seconds=1)
    assert job.name == "scan"
    assert "scan" in scheduler.jobs


def test_duplicate_job():
    scheduler = RobotScheduler()
    scheduler.add_job("scan", lambda: None, interval_seconds=1)
    with pytest.raises(ValueError):
        scheduler.add_job("scan", lambda: None, interval_seconds=1)


def test_remove_job():
    scheduler = RobotScheduler()
    scheduler.add_job("scan", lambda: None, interval_seconds=1)
    scheduler.remove_job("scan")
    assert "scan" not in scheduler.jobs


def test_enable_disable_job():
    scheduler = RobotScheduler()
    job = scheduler.add_job("scan", lambda: None, interval_seconds=1)
    scheduler.disable_job("scan")
    assert job.enabled is False
    scheduler.enable_job("scan")
    assert job.enabled is True


def test_run_sync_job():
    async def run():
        calls = []
        scheduler = RobotScheduler()
        scheduler.add_job(
            "scan",
            lambda: calls.append("ok"),
            interval_seconds=1,
            run_immediately=True,
        )
        success = await scheduler.run_job("scan", now=now())
        assert success is True
        assert calls == ["ok"]
        assert scheduler.jobs["scan"].success_count == 1
    asyncio.run(run())


def test_run_async_job():
    async def run():
        calls = []

        async def callback():
            calls.append("ok")

        scheduler = RobotScheduler()
        scheduler.add_job("scan", callback, interval_seconds=1)
        assert await scheduler.run_job("scan", now=now())
        assert calls == ["ok"]
    asyncio.run(run())


def test_failed_job():
    async def run():
        def fail():
            raise RuntimeError("boom")

        scheduler = RobotScheduler()
        scheduler.add_job("scan", fail, interval_seconds=1)
        success = await scheduler.run_job("scan", now=now())
        assert success is False
        assert scheduler.health.state == SchedulerState.DEGRADED
        assert scheduler.jobs["scan"].failure_count == 1
    asyncio.run(run())


def test_run_due_jobs():
    async def run():
        calls = []
        scheduler = RobotScheduler()
        job = scheduler.add_job("scan", lambda: calls.append(1), interval_seconds=5)
        job.next_run_at = now()
        executed = await scheduler.run_due_jobs(now=now())
        assert executed == ["scan"]
        assert calls == [1]
    asyncio.run(run())


def test_not_due_job():
    async def run():
        scheduler = RobotScheduler()
        job = scheduler.add_job("scan", lambda: None, interval_seconds=5)
        job.next_run_at = now() + timedelta(seconds=10)
        assert await scheduler.run_due_jobs(now=now()) == []
    asyncio.run(run())


def test_heartbeat():
    async def run():
        scheduler = RobotScheduler()
        await scheduler.heartbeat()
        assert scheduler.health.last_heartbeat_at is not None
    asyncio.run(run())


def test_daily_report():
    scheduler = RobotScheduler(
        live_data_engine=FakeLiveData(),
        paper_trading_engine=FakePaperTrading(),
    )
    scheduler.add_job("scan", lambda: None, interval_seconds=1)
    report = scheduler.build_daily_report(now=now())
    assert report["date"] == "2026-07-21"
    assert "live_data" in report
    assert "paper_trading" in report
    assert "jobs" in report


def test_daily_rollover():
    scheduler = RobotScheduler()
    report = scheduler.perform_daily_rollover(now=now())
    assert len(scheduler.daily_reports) == 1
    assert scheduler.health.current_day == "2026-07-21"
    assert report["date"] == "2026-07-21"


def test_live_data_start_stop():
    async def run():
        live = FakeLiveData()
        scheduler = RobotScheduler(
            SchedulerConfig(task_poll_interval=0.01),
            live_data_engine=live,
        )
        task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(0.03)
        assert live.started is True
        await scheduler.stop()
        await task
        assert live.stopped is True
        assert scheduler.health.state == SchedulerState.STOPPED
    asyncio.run(run())


def test_scheduler_runs_job():
    async def run():
        calls = []
        scheduler = RobotScheduler(
            SchedulerConfig(
                heartbeat_interval=0.01,
                task_poll_interval=0.005,
            )
        )
        scheduler.add_job(
            "scan",
            lambda: calls.append(1),
            interval_seconds=0.01,
            run_immediately=True,
        )
        task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(0.04)
        await scheduler.stop()
        await task
        assert len(calls) >= 1
        assert scheduler.health.loop_iterations >= 1
    asyncio.run(run())


def test_start_is_idempotent():
    async def run():
        scheduler = RobotScheduler()
        scheduler._running = True
        await scheduler.start()
        assert scheduler._running is True
    asyncio.run(run())


def test_shutdown_idempotent():
    async def run():
        scheduler = RobotScheduler()
        scheduler.health.state = SchedulerState.STOPPED
        await scheduler.shutdown()
        assert scheduler.health.state == SchedulerState.STOPPED
    asyncio.run(run())


def test_dashboard():
    scheduler = RobotScheduler()
    scheduler.add_job("scan", lambda: None, interval_seconds=1)
    data = scheduler.dashboard()
    assert "health" in data
    assert "jobs" in data
    assert data["daily_report_count"] == 0


def test_critical_failure_stops_scheduler():
    async def run():
        def fail():
            raise RuntimeError("boom")

        scheduler = RobotScheduler(
            SchedulerConfig(max_consecutive_failures=1)
        )
        scheduler.add_job(
            "critical",
            fail,
            interval_seconds=1,
            critical=True,
        )
        await scheduler.run_job("critical", now=now())
        assert scheduler.health.state == SchedulerState.STOPPING
    asyncio.run(run())


def test_scheduled_job_to_dict():
    job = ScheduledJob(
        name="scan",
        callback=lambda: None,
        interval_seconds=1,
    )
    job.schedule_from(now())
    data = job.to_dict()
    assert data["name"] == "scan"
    assert data["next_run_at"] is not None
