from __future__ import annotations

from datetime import timedelta

import pytest

from engine.robot_supervisor import (
    HealthStatus,
    RestartDecision,
    RobotSupervisor,
    SupervisorConfig,
    WorkerConfig,
    WorkerState,
    utc_now,
)


class FakeWorker:
    def __init__(self, health_value=True, start_error=False, stop_error=False):
        self.health_value = health_value
        self.start_error = start_error
        self.stop_error = stop_error
        self.started = 0
        self.stopped = 0

    def start(self):
        if self.start_error:
            raise RuntimeError("start failed")
        self.started += 1

    def stop(self):
        if self.stop_error:
            raise RuntimeError("stop failed")
        self.stopped += 1

    def health(self):
        if isinstance(self.health_value, Exception):
            raise self.health_value
        return self.health_value


def make_supervisor(**kwargs):
    data = {
        "health_check_interval_seconds": 0.001,
        "loop_sleep_seconds": 0.001,
    }
    data.update(kwargs)
    return RobotSupervisor(SupervisorConfig(**data))


def test_worker_config_normalizes():
    config = WorkerConfig(name=" crypto ", symbol=" btcusdt ")
    assert config.name == "crypto"
    assert config.symbol == "BTCUSDT"


def test_invalid_worker_name():
    with pytest.raises(ValueError):
        WorkerConfig(name=" ")


def test_invalid_timeout():
    with pytest.raises(ValueError):
        WorkerConfig(name="x", heartbeat_timeout_seconds=0)


def test_register_worker():
    supervisor = make_supervisor()
    runtime = supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker())
    assert runtime.name == "w1"
    assert supervisor.dashboard()["worker_count"] == 1


def test_duplicate_worker_name():
    supervisor = make_supervisor()
    supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker())
    with pytest.raises(ValueError):
        supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker())


def test_worker_protocol_validation():
    supervisor = make_supervisor()
    with pytest.raises(TypeError):
        supervisor.register_worker(WorkerConfig(name="bad"), object())


def test_start_worker():
    supervisor = make_supervisor()
    worker = FakeWorker()
    runtime = supervisor.register_worker(WorkerConfig(name="w1"), worker)
    supervisor.start_worker("w1")
    assert runtime.state == WorkerState.RUNNING
    assert runtime.health_status == HealthStatus.HEALTHY
    assert worker.started == 1


def test_start_error():
    supervisor = make_supervisor()
    runtime = supervisor.register_worker(
        WorkerConfig(name="w1"),
        FakeWorker(start_error=True),
    )
    supervisor.start_worker("w1")
    assert runtime.state == WorkerState.FAILED
    assert runtime.last_error


def test_disabled_worker_cannot_start():
    supervisor = make_supervisor()
    supervisor.register_worker(
        WorkerConfig(name="w1", enabled=False),
        FakeWorker(),
    )
    with pytest.raises(RuntimeError):
        supervisor.start_worker("w1")


def test_stop_worker():
    supervisor = make_supervisor()
    worker = FakeWorker()
    runtime = supervisor.register_worker(WorkerConfig(name="w1"), worker)
    supervisor.start_worker("w1")
    supervisor.stop_worker("w1")
    assert runtime.state == WorkerState.STOPPED
    assert worker.stopped == 1


def test_stop_error():
    supervisor = make_supervisor()
    worker = FakeWorker(stop_error=True)
    runtime = supervisor.register_worker(WorkerConfig(name="w1"), worker)
    supervisor.start_worker("w1")
    supervisor.stop_worker("w1")
    assert runtime.state == WorkerState.FAILED


def test_start_all_only_enabled():
    supervisor = make_supervisor()
    w1 = FakeWorker()
    w2 = FakeWorker()
    supervisor.register_worker(WorkerConfig(name="w1"), w1)
    supervisor.register_worker(WorkerConfig(name="w2", enabled=False), w2)
    supervisor.start_all()
    assert w1.started == 1
    assert w2.started == 0


def test_stop_all():
    supervisor = make_supervisor()
    worker = FakeWorker()
    supervisor.register_worker(WorkerConfig(name="w1"), worker)
    supervisor.start_all()
    supervisor.stop_all()
    assert worker.stopped == 1


def test_unregister_worker():
    supervisor = make_supervisor()
    supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker())
    removed = supervisor.unregister_worker("w1")
    assert removed.name == "w1"
    assert supervisor.dashboard()["worker_count"] == 0


def test_health_bool():
    supervisor = make_supervisor()
    runtime = supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker(True))
    supervisor.start_worker("w1")
    supervisor.check_worker_health("w1")
    assert runtime.health_status == HealthStatus.HEALTHY


def test_health_string():
    supervisor = make_supervisor()
    runtime = supervisor.register_worker(
        WorkerConfig(name="w1"),
        FakeWorker("DEGRADED"),
    )
    supervisor.start_worker("w1")
    supervisor.check_worker_health("w1")
    assert runtime.health_status == HealthStatus.DEGRADED
    assert runtime.state == WorkerState.DEGRADED


def test_health_dict():
    supervisor = make_supervisor()
    runtime = supervisor.register_worker(
        WorkerConfig(name="w1"),
        FakeWorker({"status": "HEALTHY"}),
    )
    supervisor.start_worker("w1")
    supervisor.check_worker_health("w1")
    assert runtime.health_status == HealthStatus.HEALTHY


def test_health_exception():
    supervisor = make_supervisor(auto_restart=False)
    runtime = supervisor.register_worker(
        WorkerConfig(name="w1"),
        FakeWorker(RuntimeError("health failed")),
    )
    supervisor.start_worker("w1")
    supervisor.check_worker_health("w1")
    assert runtime.health_status == HealthStatus.UNHEALTHY


def test_heartbeat_timeout():
    supervisor = make_supervisor(auto_restart=False)
    runtime = supervisor.register_worker(
        WorkerConfig(name="w1", heartbeat_timeout_seconds=1),
        FakeWorker(True),
    )
    supervisor.start_worker("w1")
    runtime.last_heartbeat_at = utc_now() - timedelta(seconds=5)
    supervisor.check_worker_health("w1")
    assert runtime.health_status == HealthStatus.UNHEALTHY
    assert runtime.last_error == "heartbeat timeout"


def test_heartbeat_update():
    supervisor = make_supervisor()
    runtime = supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker())
    at = utc_now()
    supervisor.heartbeat("w1", at=at)
    assert runtime.last_heartbeat_at == at


def test_restart_decision_none():
    supervisor = make_supervisor()
    runtime = supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker())
    runtime.health_status = HealthStatus.HEALTHY
    assert supervisor.evaluate_restart(runtime) == RestartDecision.NONE


def test_restart_decision_restart():
    supervisor = make_supervisor()
    runtime = supervisor.register_worker(
        WorkerConfig(name="w1", max_restarts=2),
        FakeWorker(),
    )
    runtime.health_status = HealthStatus.UNHEALTHY
    assert supervisor.evaluate_restart(runtime) == RestartDecision.RESTART


def test_restart_decision_disable():
    supervisor = make_supervisor()
    runtime = supervisor.register_worker(
        WorkerConfig(name="w1", max_restarts=0),
        FakeWorker(),
    )
    runtime.health_status = HealthStatus.UNHEALTHY
    assert supervisor.evaluate_restart(runtime) == RestartDecision.DISABLE


def test_restart_worker():
    supervisor = make_supervisor()
    worker = FakeWorker()
    runtime = supervisor.register_worker(
        WorkerConfig(name="w1", restart_cooldown_seconds=0),
        worker,
    )
    supervisor.start_worker("w1")
    supervisor.restart_worker("w1")
    assert runtime.restart_count == 1
    assert worker.started == 2


def test_restart_limit_disables():
    supervisor = make_supervisor()
    runtime = supervisor.register_worker(
        WorkerConfig(name="w1", max_restarts=0),
        FakeWorker(),
    )
    supervisor.restart_worker("w1")
    assert runtime.config.enabled is False


def test_auto_restart_on_unhealthy():
    supervisor = make_supervisor()
    worker = FakeWorker(False)
    runtime = supervisor.register_worker(
        WorkerConfig(
            name="w1",
            max_restarts=1,
            restart_cooldown_seconds=0,
        ),
        worker,
    )
    supervisor.start_worker("w1")
    supervisor.check_worker_health("w1")
    assert runtime.restart_count == 1


def test_events():
    supervisor = make_supervisor()
    supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker())
    events = supervisor.events()
    assert events[0].event_type == "WORKER_REGISTERED"


def test_event_limit():
    supervisor = make_supervisor()
    supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker())
    supervisor.start_worker("w1")
    assert len(supervisor.events(1)) == 1


def test_dashboard_counts():
    supervisor = make_supervisor()
    supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker())
    supervisor.register_worker(
        WorkerConfig(name="w2", enabled=False),
        FakeWorker(),
    )
    data = supervisor.dashboard()
    assert data["worker_count"] == 2
    assert data["enabled_workers"] == 1


def test_run_max_cycles():
    supervisor = make_supervisor()
    worker = FakeWorker()
    supervisor.register_worker(WorkerConfig(name="w1"), worker)
    result = supervisor.run(max_cycles=2)
    assert result["running"] is False
    assert worker.started == 1
    assert worker.stopped == 1


def test_stop_flag():
    supervisor = make_supervisor()
    supervisor.stop()
    assert supervisor.running is False


def test_invalid_supervisor_config():
    with pytest.raises(ValueError):
        SupervisorConfig(health_check_interval_seconds=0)


def test_invalid_run_limits():
    supervisor = make_supervisor()
    with pytest.raises(ValueError):
        supervisor.run(max_cycles=0)
    with pytest.raises(ValueError):
        supervisor.run(max_runtime_seconds=0)


def test_runtime_to_dict():
    supervisor = make_supervisor()
    runtime = supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker())
    data = runtime.to_dict()
    assert data["name"] == "w1"
    assert data["state"] == "CREATED"


def test_event_to_dict():
    supervisor = make_supervisor()
    supervisor.register_worker(WorkerConfig(name="w1"), FakeWorker())
    data = supervisor.events()[0].to_dict()
    assert data["worker_name"] == "w1"
