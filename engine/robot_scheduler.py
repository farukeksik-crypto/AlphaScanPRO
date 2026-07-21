from __future__ import annotations

import asyncio
import inspect
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SchedulerState(str, Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


@dataclass(slots=True)
class SchedulerConfig:
    heartbeat_interval: float = 5.0
    task_poll_interval: float = 0.1
    shutdown_timeout: float = 10.0
    max_consecutive_failures: int = 5
    restart_delay: float = 1.0
    daily_rollover_hour_utc: int = 0

    def __post_init__(self) -> None:
        if self.heartbeat_interval <= 0:
            raise ValueError("heartbeat_interval pozitif olmalıdır.")
        if self.task_poll_interval <= 0:
            raise ValueError("task_poll_interval pozitif olmalıdır.")
        if self.shutdown_timeout <= 0:
            raise ValueError("shutdown_timeout pozitif olmalıdır.")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures en az 1 olmalıdır.")
        if self.restart_delay < 0:
            raise ValueError("restart_delay negatif olamaz.")
        if not 0 <= self.daily_rollover_hour_utc <= 23:
            raise ValueError("daily_rollover_hour_utc 0-23 arasında olmalıdır.")


@dataclass(slots=True)
class ScheduledJob:
    name: str
    callback: Callable[[], Any]
    interval_seconds: float
    run_immediately: bool = False
    enabled: bool = True
    critical: bool = False
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    last_error: str = ""
    last_duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("job name boş olamaz.")
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds pozitif olmalıdır.")

    def schedule_from(self, now: datetime) -> None:
        if self.next_run_at is None:
            delay = 0.0 if self.run_immediately else self.interval_seconds
            self.next_run_at = now + timedelta_seconds(delay)

    def due(self, now: datetime) -> bool:
        return bool(self.enabled and self.next_run_at and now >= self.next_run_at)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["callback"] = getattr(self.callback, "__name__", type(self.callback).__name__)
        for key in ("last_run_at", "next_run_at"):
            value = data[key]
            data[key] = value.isoformat() if value else None
        return data


@dataclass(slots=True)
class SchedulerHealth:
    state: SchedulerState = SchedulerState.IDLE
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_heartbeat_at: Optional[datetime] = None
    loop_iterations: int = 0
    total_job_runs: int = 0
    total_job_failures: int = 0
    restart_count: int = 0
    current_day: Optional[str] = None
    last_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "last_heartbeat_at": (
                self.last_heartbeat_at.isoformat()
                if self.last_heartbeat_at else None
            ),
            "loop_iterations": self.loop_iterations,
            "total_job_runs": self.total_job_runs,
            "total_job_failures": self.total_job_failures,
            "restart_count": self.restart_count,
            "current_day": self.current_day,
            "last_error": self.last_error,
        }


def timedelta_seconds(seconds: float):
    from datetime import timedelta
    return timedelta(seconds=seconds)


class RobotScheduler:
    def __init__(
        self,
        config: Optional[SchedulerConfig] = None,
        *,
        live_data_engine: Any = None,
        paper_trading_engine: Any = None,
    ) -> None:
        self.config = config or SchedulerConfig()
        self.live_data_engine = live_data_engine
        self.paper_trading_engine = paper_trading_engine
        self.jobs: Dict[str, ScheduledJob] = {}
        self.health = SchedulerHealth()
        self.daily_reports: List[Dict[str, Any]] = []
        self._stop_event = asyncio.Event()
        self._running = False
        self._background_tasks: List[asyncio.Task[Any]] = []
        self._last_rollover_date: Optional[date] = None

    def add_job(
        self,
        name: str,
        callback: Callable[[], Any],
        *,
        interval_seconds: float,
        run_immediately: bool = False,
        enabled: bool = True,
        critical: bool = False,
    ) -> ScheduledJob:
        if name in self.jobs:
            raise ValueError(f"Job zaten mevcut: {name}")
        job = ScheduledJob(
            name=name,
            callback=callback,
            interval_seconds=interval_seconds,
            run_immediately=run_immediately,
            enabled=enabled,
            critical=critical,
        )
        job.schedule_from(utc_now())
        self.jobs[name] = job
        return job

    def remove_job(self, name: str) -> None:
        if name not in self.jobs:
            raise KeyError(name)
        self.jobs.pop(name)

    def enable_job(self, name: str) -> None:
        self.jobs[name].enabled = True
        self.jobs[name].schedule_from(utc_now())

    def disable_job(self, name: str) -> None:
        self.jobs[name].enabled = False

    async def _execute_callback(self, callback: Callable[[], Any]) -> Any:
        result = callback()
        if inspect.isawaitable(result):
            return await result
        return result

    async def run_job(self, name: str, *, now: Optional[datetime] = None) -> bool:
        if name not in self.jobs:
            raise KeyError(name)

        job = self.jobs[name]
        started = utc_now()
        job.last_run_at = now or started
        job.run_count += 1
        self.health.total_job_runs += 1

        try:
            await self._execute_callback(job.callback)
        except Exception as exc:
            job.failure_count += 1
            job.consecutive_failures += 1
            job.last_error = str(exc)
            self.health.total_job_failures += 1
            self.health.last_error = f"{job.name}: {exc}"
            self.health.state = SchedulerState.DEGRADED
            success = False
        else:
            job.success_count += 1
            job.consecutive_failures = 0
            job.last_error = ""
            if self.health.state == SchedulerState.DEGRADED:
                self.health.state = SchedulerState.RUNNING
            success = True
        finally:
            job.last_duration_seconds = (utc_now() - started).total_seconds()
            base = now or utc_now()
            job.next_run_at = base + timedelta_seconds(job.interval_seconds)

        if job.critical and job.consecutive_failures >= self.config.max_consecutive_failures:
            self.health.last_error = (
                f"Kritik job hata sınırına ulaştı: {job.name}"
            )
            await self.stop()

        return success

    async def run_due_jobs(self, *, now: Optional[datetime] = None) -> List[str]:
        current = now or utc_now()
        executed: List[str] = []
        for name, job in list(self.jobs.items()):
            if job.due(current):
                await self.run_job(name, now=current)
                executed.append(name)
        return executed

    async def heartbeat(self) -> None:
        self.health.last_heartbeat_at = utc_now()

    def _rollover_due(self, now: datetime) -> bool:
        current_date = now.date()
        if now.hour < self.config.daily_rollover_hour_utc:
            current_date = (now - timedelta_seconds(86400)).date()
        return self._last_rollover_date != current_date

    def build_daily_report(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        current = now or utc_now()
        report = {
            "date": current.date().isoformat(),
            "created_at": current.isoformat(),
            "scheduler": self.health.to_dict(),
            "jobs": {
                name: job.to_dict()
                for name, job in sorted(self.jobs.items())
            },
        }

        if self.live_data_engine is not None and hasattr(
            self.live_data_engine, "dashboard"
        ):
            report["live_data"] = self.live_data_engine.dashboard()

        if self.paper_trading_engine is not None and hasattr(
            self.paper_trading_engine, "dashboard"
        ):
            report["paper_trading"] = self.paper_trading_engine.dashboard()

        return report

    def perform_daily_rollover(
        self,
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        current = now or utc_now()
        report = self.build_daily_report(now=current)
        self.daily_reports.append(report)
        self._last_rollover_date = current.date()
        self.health.current_day = current.date().isoformat()
        return report

    async def _start_live_data(self) -> None:
        if self.live_data_engine is None:
            return
        if not hasattr(self.live_data_engine, "run_forever"):
            raise TypeError("live_data_engine run_forever metoduna sahip olmalıdır.")
        task = asyncio.create_task(
            self.live_data_engine.run_forever(),
            name="alphascan-live-data",
        )
        self._background_tasks.append(task)

    async def _stop_live_data(self) -> None:
        if self.live_data_engine is not None and hasattr(
            self.live_data_engine, "stop"
        ):
            result = self.live_data_engine.stop()
            if inspect.isawaitable(result):
                await result

    async def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self.health.state = SchedulerState.STARTING
        self.health.started_at = utc_now()
        self.health.stopped_at = None
        self.health.current_day = utc_now().date().isoformat()

        for job in self.jobs.values():
            job.schedule_from(utc_now())

        await self._start_live_data()
        self.health.state = SchedulerState.RUNNING

        try:
            while not self._stop_event.is_set():
                now = utc_now()
                self.health.loop_iterations += 1

                await self.run_due_jobs(now=now)

                if (
                    self.health.last_heartbeat_at is None
                    or (
                        now - self.health.last_heartbeat_at
                    ).total_seconds() >= self.config.heartbeat_interval
                ):
                    await self.heartbeat()

                if self._rollover_due(now):
                    self.perform_daily_rollover(now=now)

                await asyncio.sleep(self.config.task_poll_interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.health.state = SchedulerState.DEGRADED
            self.health.last_error = str(exc)
            raise
        finally:
            await self.shutdown()

    async def stop(self) -> None:
        self.health.state = SchedulerState.STOPPING
        self._stop_event.set()

    async def shutdown(self) -> None:
        if not self._running and self.health.state == SchedulerState.STOPPED:
            return

        self.health.state = SchedulerState.STOPPING
        self._stop_event.set()

        await self._stop_live_data()

        pending = [
            task for task in self._background_tasks
            if not task.done()
        ]
        for task in pending:
            task.cancel()

        if pending:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True),
                    timeout=self.config.shutdown_timeout,
                )
            except asyncio.TimeoutError:
                for task in pending:
                    task.cancel()

        self._background_tasks.clear()
        self._running = False
        self.health.state = SchedulerState.STOPPED
        self.health.stopped_at = utc_now()

    async def run_with_restarts(self, *, max_restarts: Optional[int] = None) -> None:
        restart_count = 0
        while True:
            try:
                await self.start()
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                restart_count += 1
                self.health.restart_count = restart_count
                self.health.last_error = str(exc)

                if max_restarts is not None and restart_count > max_restarts:
                    self.health.state = SchedulerState.STOPPED
                    return

                await asyncio.sleep(self.config.restart_delay)
                self._running = False
                self._stop_event = asyncio.Event()

    def dashboard(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "health": self.health.to_dict(),
            "jobs": {
                name: job.to_dict()
                for name, job in sorted(self.jobs.items())
            },
            "background_task_count": len(self._background_tasks),
            "daily_report_count": len(self.daily_reports),
            "latest_daily_report": (
                self.daily_reports[-1]
                if self.daily_reports
                else None
            ),
        }
