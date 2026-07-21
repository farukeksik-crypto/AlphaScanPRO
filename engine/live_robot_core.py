from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RobotStatus(str, Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TradeLifecycleStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    APPROVED = "APPROVED"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass
class RobotConfig:
    scan_interval_seconds: int = 60
    heartbeat_interval_seconds: int = 30
    max_queue_size: int = 1000
    max_task_retries: int = 3
    markets: tuple[str, ...] = ("CRYPTO",)


@dataclass
class RobotTask:
    task_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: uuid4().hex)
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    created_at: str = field(default_factory=utc_now_iso)
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass
class SignalEvent:
    symbol: str
    market: str
    signal: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    signal_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TradeLifecycle:
    symbol: str
    market: str
    side: str
    quantity: float
    entry_price: float
    trade_id: str = field(default_factory=lambda: uuid4().hex)
    status: TradeLifecycleStatus = TradeLifecycleStatus.CREATED
    stop_price: float | None = None
    target_price: float | None = None
    exit_price: float | None = None
    realized_pnl: float = 0.0
    reason: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    history: list[dict[str, Any]] = field(default_factory=list)

    def transition(
        self,
        status: TradeLifecycleStatus,
        *,
        reason: str = "",
        exit_price: float | None = None,
    ) -> None:
        allowed = {
            TradeLifecycleStatus.CREATED: {
                TradeLifecycleStatus.QUEUED,
                TradeLifecycleStatus.REJECTED,
                TradeLifecycleStatus.FAILED,
            },
            TradeLifecycleStatus.QUEUED: {
                TradeLifecycleStatus.APPROVED,
                TradeLifecycleStatus.REJECTED,
                TradeLifecycleStatus.FAILED,
            },
            TradeLifecycleStatus.APPROVED: {
                TradeLifecycleStatus.OPEN,
                TradeLifecycleStatus.FAILED,
            },
            TradeLifecycleStatus.OPEN: {
                TradeLifecycleStatus.CLOSED,
                TradeLifecycleStatus.FAILED,
            },
            TradeLifecycleStatus.CLOSED: set(),
            TradeLifecycleStatus.REJECTED: set(),
            TradeLifecycleStatus.FAILED: set(),
        }

        if status not in allowed[self.status]:
            raise ValueError(
                f"Geçersiz lifecycle geçişi: {self.status.value} -> {status.value}"
            )

        previous = self.status
        self.status = status
        self.reason = reason
        self.updated_at = utc_now_iso()

        if status == TradeLifecycleStatus.CLOSED:
            if exit_price is None:
                raise ValueError("CLOSED geçişinde exit_price gereklidir.")
            self.exit_price = float(exit_price)
            direction = 1.0 if self.side.upper() == "LONG" else -1.0
            self.realized_pnl = round(
                (self.exit_price - self.entry_price)
                * self.quantity
                * direction,
                8,
            )

        self.history.append(
            {
                "from": previous.value,
                "to": status.value,
                "reason": reason,
                "timestamp": self.updated_at,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class TaskQueue:
    def __init__(self, max_size: int = 1000) -> None:
        if max_size <= 0:
            raise ValueError("max_size 0'dan büyük olmalıdır.")
        self.max_size = int(max_size)
        self._items: list[RobotTask] = []

    def enqueue(self, task: RobotTask) -> str:
        if len(self._items) >= self.max_size:
            raise OverflowError("Görev kuyruğu kapasitesi doldu.")
        self._items.append(task)
        return task.task_id

    def dequeue(self) -> RobotTask | None:
        for task in self._items:
            if task.status == TaskStatus.PENDING:
                return task
        return None

    def get(self, task_id: str) -> RobotTask | None:
        return next(
            (task for task in self._items if task.task_id == task_id),
            None,
        )

    def pending_count(self) -> int:
        return sum(
            task.status == TaskStatus.PENDING
            for task in self._items
        )

    def snapshot(self) -> list[dict[str, Any]]:
        return [task.to_dict() for task in self._items]


class MarketWatcher:
    def __init__(self) -> None:
        self._providers: dict[str, Callable[[], list[dict[str, Any]]]] = {}

    def register_provider(
        self,
        market: str,
        provider: Callable[[], list[dict[str, Any]]],
    ) -> None:
        self._providers[market.upper()] = provider

    def watch(self, market: str) -> list[dict[str, Any]]:
        key = market.upper()
        provider = self._providers.get(key)
        if provider is None:
            raise KeyError(f"Market provider bulunamadı: {key}")
        result = provider()
        if not isinstance(result, list):
            raise TypeError("Market provider liste döndürmelidir.")
        return result


class SignalDispatcher:
    def __init__(self) -> None:
        self._handlers: list[Callable[[SignalEvent], Any]] = []
        self._history: list[SignalEvent] = []

    def register_handler(
        self,
        handler: Callable[[SignalEvent], Any],
    ) -> None:
        self._handlers.append(handler)

    def dispatch(self, signal: SignalEvent) -> list[Any]:
        self._history.append(signal)
        return [handler(signal) for handler in self._handlers]

    def history(self) -> list[dict[str, Any]]:
        return [signal.to_dict() for signal in self._history]


class LiveRobotCore:
    def __init__(
        self,
        config: RobotConfig | None = None,
    ) -> None:
        self.config = config or RobotConfig()
        self.status = RobotStatus.STOPPED
        self.task_queue = TaskQueue(self.config.max_queue_size)
        self.market_watcher = MarketWatcher()
        self.signal_dispatcher = SignalDispatcher()
        self.trades: dict[str, TradeLifecycle] = {}
        self.last_heartbeat_at: str | None = None
        self.started_at: str | None = None
        self.stopped_at: str | None = None
        self.logs: list[dict[str, Any]] = []

    def start(self) -> None:
        if self.status == RobotStatus.RUNNING:
            return
        self.status = RobotStatus.RUNNING
        self.started_at = utc_now_iso()
        self.stopped_at = None
        self._log("ROBOT_STARTED", "Robot çalıştırıldı.")

    def pause(self) -> None:
        if self.status != RobotStatus.RUNNING:
            raise RuntimeError("Sadece çalışan robot duraklatılabilir.")
        self.status = RobotStatus.PAUSED
        self._log("ROBOT_PAUSED", "Robot duraklatıldı.")

    def resume(self) -> None:
        if self.status != RobotStatus.PAUSED:
            raise RuntimeError("Sadece duraklatılmış robot devam ettirilebilir.")
        self.status = RobotStatus.RUNNING
        self._log("ROBOT_RESUMED", "Robot devam ettirildi.")

    def stop(self) -> None:
        self.status = RobotStatus.STOPPED
        self.stopped_at = utc_now_iso()
        self._log("ROBOT_STOPPED", "Robot durduruldu.")

    def heartbeat(self) -> dict[str, Any]:
        self.last_heartbeat_at = utc_now_iso()
        heartbeat = {
            "status": self.status.value,
            "timestamp": self.last_heartbeat_at,
            "pending_tasks": self.task_queue.pending_count(),
            "open_trades": sum(
                trade.status == TradeLifecycleStatus.OPEN
                for trade in self.trades.values()
            ),
        }
        self._log("HEARTBEAT", "Heartbeat üretildi.", heartbeat)
        return heartbeat

    def schedule_scan(self, market: str) -> str:
        self._require_running()
        key = market.upper()
        if key not in {item.upper() for item in self.config.markets}:
            raise ValueError(f"Market robot yapılandırmasında yok: {key}")
        task = RobotTask(
            task_type="MARKET_SCAN",
            payload={"market": key},
        )
        task_id = self.task_queue.enqueue(task)
        self._log("TASK_ENQUEUED", "Tarama görevi kuyruğa eklendi.", task.to_dict())
        return task_id

    def run_next_task(self) -> RobotTask | None:
        self._require_running()
        task = self.task_queue.dequeue()
        if task is None:
            return None

        task.status = TaskStatus.RUNNING
        task.attempts += 1
        task.started_at = utc_now_iso()
        task.error = None

        try:
            if task.task_type == "MARKET_SCAN":
                market = str(task.payload["market"])
                snapshots = self.market_watcher.watch(market)
                task.payload["result_count"] = len(snapshots)
                task.payload["results"] = snapshots
            else:
                raise ValueError(f"Bilinmeyen görev tipi: {task.task_type}")

            task.status = TaskStatus.COMPLETED
            task.completed_at = utc_now_iso()
            self._log("TASK_COMPLETED", "Görev tamamlandı.", task.to_dict())
        except Exception as exc:
            task.error = str(exc)
            if task.attempts < self.config.max_task_retries:
                task.status = TaskStatus.PENDING
            else:
                task.status = TaskStatus.FAILED
                task.completed_at = utc_now_iso()
            self._log("TASK_FAILED", "Görev hatası oluştu.", task.to_dict())

        return task

    def publish_signal(self, signal: SignalEvent) -> list[Any]:
        self._require_running()
        results = self.signal_dispatcher.dispatch(signal)
        self._log("SIGNAL_DISPATCHED", "Sinyal dağıtıldı.", signal.to_dict())
        return results

    def create_trade(
        self,
        *,
        symbol: str,
        market: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> TradeLifecycle:
        self._require_running()
        if quantity <= 0 or entry_price <= 0:
            raise ValueError("quantity ve entry_price 0'dan büyük olmalıdır.")

        trade = TradeLifecycle(
            symbol=symbol,
            market=market.upper(),
            side=side.upper(),
            quantity=float(quantity),
            entry_price=float(entry_price),
            stop_price=stop_price,
            target_price=target_price,
        )
        self.trades[trade.trade_id] = trade
        self._log("TRADE_CREATED", "Trade lifecycle oluşturuldu.", trade.to_dict())
        return trade

    def transition_trade(
        self,
        trade_id: str,
        status: TradeLifecycleStatus,
        *,
        reason: str = "",
        exit_price: float | None = None,
    ) -> TradeLifecycle:
        trade = self.trades.get(trade_id)
        if trade is None:
            raise KeyError(f"Trade bulunamadı: {trade_id}")
        trade.transition(
            status,
            reason=reason,
            exit_price=exit_price,
        )
        self._log("TRADE_TRANSITION", "Trade durumu değişti.", trade.to_dict())
        return trade

    def robot_report(self) -> dict[str, Any]:
        return {
            "config": asdict(self.config),
            "status": self.status.value,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "last_heartbeat_at": self.last_heartbeat_at,
            "task_queue": self.task_queue.snapshot(),
            "signal_history": self.signal_dispatcher.history(),
            "trades": [
                trade.to_dict()
                for trade in self.trades.values()
            ],
            "log_count": len(self.logs),
        }

    def _require_running(self) -> None:
        if self.status != RobotStatus.RUNNING:
            raise RuntimeError("Robot RUNNING durumunda olmalıdır.")

    def _log(
        self,
        event: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.logs.append(
            {
                "event": event,
                "message": message,
                "details": details or {},
                "timestamp": utc_now_iso(),
            }
        )
