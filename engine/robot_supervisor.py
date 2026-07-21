from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import Event as ThreadEvent, Lock
from time import monotonic, sleep
from typing import Any, Callable, Dict, List, Optional, Protocol


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkerState(str, Enum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    RESTARTING = "RESTARTING"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


class RestartDecision(str, Enum):
    NONE = "NONE"
    RESTART = "RESTART"
    DISABLE = "DISABLE"


class RobotWorker(Protocol):
    def start(self) -> Any:
        ...

    def stop(self) -> Any:
        ...

    def health(self) -> Any:
        ...


@dataclass(slots=True)
class WorkerConfig:
    name: str
    symbol: Optional[str] = None
    enabled: bool = True
    heartbeat_timeout_seconds: float = 60.0
    max_restarts: int = 3
    restart_cooldown_seconds: float = 1.0
    critical: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Worker name boÅŸ olamaz.")
        if self.symbol is not None:
            self.symbol = self.symbol.strip().upper()
        if self.heartbeat_timeout_seconds <= 0:
            raise ValueError("heartbeat_timeout_seconds pozitif olmalÄ±dÄ±r.")
        if self.max_restarts < 0:
            raise ValueError("max_restarts negatif olamaz.")
        if self.restart_cooldown_seconds < 0:
            raise ValueError("restart_cooldown_seconds negatif olamaz.")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata sÃ¶zlÃ¼k olmalÄ±dÄ±r.")


@dataclass(slots=True)
class WorkerRuntime:
    config: WorkerConfig
    worker: RobotWorker
    state: WorkerState = WorkerState.CREATED
    health_status: HealthStatus = HealthStatus.UNKNOWN
    restart_count: int = 0
    last_started_at: Optional[datetime] = None
    last_stopped_at: Optional[datetime] = None
    last_heartbeat_at: Optional[datetime] = None
    last_health_check_at: Optional[datetime] = None
    last_error: Optional[str] = None
    disabled_reason: Optional[str] = None
    state_history: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.record_state(self.state, "created")

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def active(self) -> bool:
        return self.state in {
            WorkerState.STARTING,
            WorkerState.RUNNING,
            WorkerState.DEGRADED,
            WorkerState.RESTARTING,
        }

    def record_state(self, state: WorkerState, reason: Optional[str] = None) -> None:
        self.state = WorkerState(state)
        self.state_history.append(
            {
                "state": self.state.value,
                "timestamp": utc_now().isoformat(),
                "reason": reason,
            }
        )

    def heartbeat(self, at: Optional[datetime] = None) -> None:
        self.last_heartbeat_at = at or utc_now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "symbol": self.config.symbol,
            "enabled": self.config.enabled,
            "critical": self.config.critical,
            "state": self.state.value,
            "health_status": self.health_status.value,
            "restart_count": self.restart_count,
            "last_started_at": self.last_started_at.isoformat() if self.last_started_at else None,
            "last_stopped_at": self.last_stopped_at.isoformat() if self.last_stopped_at else None,
            "last_heartbeat_at": self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None,
            "last_health_check_at": self.last_health_check_at.isoformat() if self.last_health_check_at else None,
            "last_error": self.last_error,
            "disabled_reason": self.disabled_reason,
            "metadata": dict(self.config.metadata),
            "state_history": list(self.state_history),
        }


@dataclass(slots=True)
class SupervisorConfig:
    health_check_interval_seconds: float = 5.0
    stop_on_critical_failure: bool = False
    auto_restart: bool = True
    loop_sleep_seconds: float = 0.1
    history_limit: int = 1000

    def __post_init__(self) -> None:
        if self.health_check_interval_seconds <= 0:
            raise ValueError("health_check_interval_seconds pozitif olmalÄ±dÄ±r.")
        if self.loop_sleep_seconds <= 0:
            raise ValueError("loop_sleep_seconds pozitif olmalÄ±dÄ±r.")
        if self.history_limit <= 0:
            raise ValueError("history_limit pozitif olmalÄ±dÄ±r.")


@dataclass(slots=True)
class SupervisorEvent:
    event_type: str
    worker_name: Optional[str]
    message: str
    created_at: datetime = field(default_factory=utc_now)
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "worker_name": self.worker_name,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "payload": dict(self.payload),
        }


class RobotSupervisor:
    def __init__(self, config: Optional[SupervisorConfig] = None) -> None:
        self.config = config or SupervisorConfig()
        self._workers: Dict[str, WorkerRuntime] = {}
        self._events: List[SupervisorEvent] = []
        self._lock = Lock()
        self._stop_event = ThreadEvent()
        self._running = False
        self._last_health_check_monotonic = monotonic()

    @property
    def running(self) -> bool:
        return self._running

    def _add_event(
        self,
        event_type: str,
        message: str,
        worker_name: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            self._events.append(
                SupervisorEvent(
                    event_type=event_type,
                    worker_name=worker_name,
                    message=message,
                    payload=payload or {},
                )
            )
            if len(self._events) > self.config.history_limit:
                self._events = self._events[-self.config.history_limit :]

    def register_worker(self, config: WorkerConfig, worker: RobotWorker) -> WorkerRuntime:
        if worker is None:
            raise TypeError("worker gereklidir.")
        for method_name in ("start", "stop", "health"):
            if not hasattr(worker, method_name):
                raise TypeError(f"worker {method_name} metoduna sahip olmalÄ±dÄ±r.")
        with self._lock:
            if config.name in self._workers:
                raise ValueError("Worker adÄ± zaten kayÄ±tlÄ±.")
            runtime = WorkerRuntime(config=config, worker=worker)
            self._workers[config.name] = runtime
        self._add_event("WORKER_REGISTERED", "Worker kaydedildi.", config.name)
        return runtime

    def unregister_worker(self, name: str) -> WorkerRuntime:
        runtime = self.get_worker(name)
        if runtime.active:
            self.stop_worker(name)
        with self._lock:
            removed = self._workers.pop(name)
        self._add_event("WORKER_UNREGISTERED", "Worker kaydÄ± kaldÄ±rÄ±ldÄ±.", name)
        return removed

    def get_worker(self, name: str) -> WorkerRuntime:
        with self._lock:
            return self._workers[name]

    def workers(self) -> List[WorkerRuntime]:
        with self._lock:
            return list(self._workers.values())

    def start_worker(self, name: str) -> WorkerRuntime:
        runtime = self.get_worker(name)
        if not runtime.config.enabled:
            raise RuntimeError("Devre dÄ±ÅŸÄ± worker baÅŸlatÄ±lamaz.")
        if runtime.active and runtime.state != WorkerState.RESTARTING:
            return runtime

        runtime.record_state(WorkerState.STARTING, "start requested")
        try:
            runtime.worker.start()
            runtime.last_started_at = utc_now()
            runtime.last_error = None
            runtime.disabled_reason = None
            runtime.heartbeat()
            runtime.health_status = HealthStatus.HEALTHY
            runtime.record_state(WorkerState.RUNNING, "started")
            self._add_event("WORKER_STARTED", "Worker baÅŸlatÄ±ldÄ±.", name)
        except Exception as exc:
            runtime.last_error = f"{exc.__class__.__name__}: {exc}"
            runtime.health_status = HealthStatus.UNHEALTHY
            runtime.record_state(WorkerState.FAILED, runtime.last_error)
            self._add_event(
                "WORKER_START_FAILED",
                "Worker baÅŸlatÄ±lamadÄ±.",
                name,
                {"error": runtime.last_error},
            )
        return runtime

    def stop_worker(self, name: str) -> WorkerRuntime:
        runtime = self.get_worker(name)
        if runtime.state in {WorkerState.STOPPED, WorkerState.CREATED}:
            runtime.record_state(WorkerState.STOPPED, "already stopped")
            return runtime

        runtime.record_state(WorkerState.STOPPING, "stop requested")
        try:
            runtime.worker.stop()
            runtime.last_stopped_at = utc_now()
            runtime.health_status = HealthStatus.UNKNOWN
            runtime.record_state(WorkerState.STOPPED, "stopped")
            self._add_event("WORKER_STOPPED", "Worker durduruldu.", name)
        except Exception as exc:
            runtime.last_error = f"{exc.__class__.__name__}: {exc}"
            runtime.health_status = HealthStatus.UNHEALTHY
            runtime.record_state(WorkerState.FAILED, runtime.last_error)
            self._add_event(
                "WORKER_STOP_FAILED",
                "Worker durdurulamadÄ±.",
                name,
                {"error": runtime.last_error},
            )
        return runtime

    def start_all(self) -> List[WorkerRuntime]:
        results = []
        for runtime in self.workers():
            if runtime.config.enabled:
                results.append(self.start_worker(runtime.name))
        return results

    def stop_all(self) -> List[WorkerRuntime]:
        results = []
        for runtime in self.workers():
            if runtime.active or runtime.state == WorkerState.FAILED:
                results.append(self.stop_worker(runtime.name))
        return results

    @staticmethod
    def _normalize_health(value: Any) -> HealthStatus:
        if isinstance(value, HealthStatus):
            return value
        if isinstance(value, bool):
            return HealthStatus.HEALTHY if value else HealthStatus.UNHEALTHY
        if isinstance(value, str):
            return HealthStatus(value.upper())
        if isinstance(value, dict):
            raw = value.get("status", value.get("health"))
            if raw is None:
                return HealthStatus.UNKNOWN
            return RobotSupervisor._normalize_health(raw)
        return HealthStatus.UNKNOWN

    def evaluate_restart(self, runtime: WorkerRuntime) -> RestartDecision:
        if not runtime.config.enabled:
            return RestartDecision.DISABLE
        if runtime.health_status != HealthStatus.UNHEALTHY:
            return RestartDecision.NONE
        if not self.config.auto_restart:
            return RestartDecision.NONE
        if runtime.restart_count >= runtime.config.max_restarts:
            return RestartDecision.DISABLE
        return RestartDecision.RESTART

    def restart_worker(self, name: str) -> WorkerRuntime:
        runtime = self.get_worker(name)
        if runtime.restart_count >= runtime.config.max_restarts:
            runtime.config.enabled = False
            runtime.disabled_reason = "maximum restart count reached"
            runtime.record_state(WorkerState.FAILED, runtime.disabled_reason)
            self._add_event("WORKER_DISABLED", "Worker yeniden baÅŸlatma limiti nedeniyle kapatÄ±ldÄ±.", name)
            return runtime

        runtime.record_state(WorkerState.RESTARTING, "restart requested")
        self._add_event("WORKER_RESTARTING", "Worker yeniden baÅŸlatÄ±lÄ±yor.", name)
        try:
            runtime.worker.stop()
        except Exception:
            pass

        if runtime.config.restart_cooldown_seconds > 0:
            sleep(runtime.config.restart_cooldown_seconds)

        runtime.restart_count += 1
        return self.start_worker(name)

    def check_worker_health(
        self,
        name: str,
        *,
        now: Optional[datetime] = None,
    ) -> WorkerRuntime:
        runtime = self.get_worker(name)
        now = now or utc_now()
        runtime.last_health_check_at = now

        if not runtime.config.enabled:
            runtime.health_status = HealthStatus.UNKNOWN
            return runtime

        if runtime.last_heartbeat_at is not None:
            timeout = timedelta(seconds=runtime.config.heartbeat_timeout_seconds)
            if now - runtime.last_heartbeat_at > timeout:
                runtime.health_status = HealthStatus.UNHEALTHY
                runtime.last_error = "heartbeat timeout"
            else:
                try:
                    runtime.health_status = self._normalize_health(runtime.worker.health())
                except Exception as exc:
                    runtime.health_status = HealthStatus.UNHEALTHY
                    runtime.last_error = f"{exc.__class__.__name__}: {exc}"
        else:
            runtime.health_status = HealthStatus.UNKNOWN

        if runtime.health_status == HealthStatus.HEALTHY:
            if runtime.state != WorkerState.RUNNING:
                runtime.record_state(WorkerState.RUNNING, "health recovered")
        elif runtime.health_status == HealthStatus.DEGRADED:
            runtime.record_state(WorkerState.DEGRADED, "health degraded")
        elif runtime.health_status == HealthStatus.UNHEALTHY:
            runtime.record_state(WorkerState.FAILED, runtime.last_error or "unhealthy")
            self._add_event(
                "WORKER_UNHEALTHY",
                "Worker saÄŸlÄ±ksÄ±z.",
                name,
                {"error": runtime.last_error},
            )
            decision = self.evaluate_restart(runtime)
            if decision == RestartDecision.RESTART:
                self.restart_worker(name)
            elif decision == RestartDecision.DISABLE:
                runtime.config.enabled = False
                runtime.disabled_reason = "restart policy disabled worker"
                self._add_event("WORKER_DISABLED", "Worker devre dÄ±ÅŸÄ± bÄ±rakÄ±ldÄ±.", name)

        return runtime

    def check_all_health(self, *, now: Optional[datetime] = None) -> List[WorkerRuntime]:
        return [
            self.check_worker_health(runtime.name, now=now)
            for runtime in self.workers()
            if runtime.config.enabled
        ]

    def heartbeat(self, name: str, *, at: Optional[datetime] = None) -> WorkerRuntime:
        runtime = self.get_worker(name)
        runtime.heartbeat(at)
        return runtime

    def run_once(self) -> Dict[str, Any]:
        now = monotonic()
        if now - self._last_health_check_monotonic >= self.config.health_check_interval_seconds:
            self.check_all_health()
            self._last_health_check_monotonic = now

        if self.config.stop_on_critical_failure:
            critical_failure = any(
                item.config.critical and item.state == WorkerState.FAILED
                for item in self.workers()
            )
            if critical_failure:
                self.stop()
        return self.dashboard()

    def run(
        self,
        *,
        max_cycles: Optional[int] = None,
        max_runtime_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        if max_cycles is not None and max_cycles <= 0:
            raise ValueError("max_cycles pozitif olmalÄ±dÄ±r.")
        if max_runtime_seconds is not None and max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds pozitif olmalÄ±dÄ±r.")
        if self._running:
            raise RuntimeError("Supervisor zaten Ã§alÄ±ÅŸÄ±yor.")

        self._running = True
        self._stop_event.clear()
        started = monotonic()
        cycles = 0
        self._add_event("SUPERVISOR_STARTED", "Supervisor baÅŸlatÄ±ldÄ±.")

        try:
            self.start_all()
            while not self._stop_event.is_set():
                self.run_once()
                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break
                if (
                    max_runtime_seconds is not None
                    and monotonic() - started >= max_runtime_seconds
                ):
                    break
                sleep(self.config.loop_sleep_seconds)
        finally:
            self.stop_all()
            self._running = False
            self._add_event("SUPERVISOR_STOPPED", "Supervisor durduruldu.")
        return self.dashboard()

    def stop(self) -> None:
        self._stop_event.set()

    def events(self, limit: Optional[int] = None) -> List[SupervisorEvent]:
        with self._lock:
            items = list(self._events)
        if limit is None:
            return items
        if limit < 0:
            raise ValueError("limit negatif olamaz.")
        return items[-limit:] if limit else []

    def dashboard(self) -> Dict[str, Any]:
        workers = self.workers()
        state_counts: Dict[str, int] = {}
        health_counts: Dict[str, int] = {}
        for item in workers:
            state_counts[item.state.value] = state_counts.get(item.state.value, 0) + 1
            health_counts[item.health_status.value] = health_counts.get(item.health_status.value, 0) + 1

        return {
            "running": self.running,
            "worker_count": len(workers),
            "enabled_workers": sum(1 for item in workers if item.config.enabled),
            "active_workers": sum(1 for item in workers if item.active),
            "critical_failures": sum(
                1
                for item in workers
                if item.config.critical and item.state == WorkerState.FAILED
            ),
            "state_counts": state_counts,
            "health_counts": health_counts,
            "workers": [item.to_dict() for item in workers],
            "event_count": len(self.events()),
        }

