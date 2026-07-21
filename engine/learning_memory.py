from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class ParameterVersion:
    version_id: str
    created_at: str
    parameters: dict[str, Any]
    source: str
    note: str
    parent_version_id: str | None
    status: str
    metrics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LearningDecision:
    accepted: bool
    action: str
    reason: str
    baseline_version_id: str | None
    candidate_version_id: str | None
    metric_name: str
    baseline_metric: float
    candidate_metric: float
    improvement_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LearningMemoryEngine:
    def __init__(self, storage_path: str | Path) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.storage_path.exists():
            self._write_state(
                {
                    "active_version_id": None,
                    "versions": [],
                    "events": [],
                }
            )

    def create_version(
        self,
        parameters: dict[str, Any],
        *,
        source: str = "MANUAL",
        note: str = "",
        metrics: dict[str, float] | None = None,
        parent_version_id: str | None = None,
        status: str = "CANDIDATE",
    ) -> ParameterVersion:
        state = self._read_state()

        if parent_version_id is None:
            parent_version_id = state.get("active_version_id")

        version = ParameterVersion(
            version_id=self._new_version_id(),
            created_at=self._now(),
            parameters=dict(parameters),
            source=str(source).upper(),
            note=note,
            parent_version_id=parent_version_id,
            status=str(status).upper(),
            metrics={
                key: float(value)
                for key, value in (metrics or {}).items()
            },
        )

        state["versions"].append(version.to_dict())
        self._append_event(
            state,
            event_type="VERSION_CREATED",
            payload={
                "version_id": version.version_id,
                "source": version.source,
                "status": version.status,
            },
        )
        self._write_state(state)
        return version

    def get_version(self, version_id: str) -> ParameterVersion | None:
        for item in self._read_state().get("versions", []):
            if item.get("version_id") == version_id:
                return ParameterVersion(**item)
        return None

    def list_versions(self) -> list[ParameterVersion]:
        return [
            ParameterVersion(**item)
            for item in self._read_state().get("versions", [])
        ]

    def get_active_version(self) -> ParameterVersion | None:
        state = self._read_state()
        active_id = state.get("active_version_id")
        return self.get_version(active_id) if active_id else None

    def activate_version(
        self,
        version_id: str,
        *,
        reason: str = "",
    ) -> ParameterVersion:
        state = self._read_state()
        found = False

        for item in state["versions"]:
            if item["version_id"] == version_id:
                item["status"] = "ACTIVE"
                found = True
            elif item.get("status") == "ACTIVE":
                item["status"] = "ARCHIVED"

        if not found:
            raise ValueError(f"Parametre sürümü bulunamadı: {version_id}")

        previous_id = state.get("active_version_id")
        state["active_version_id"] = version_id

        self._append_event(
            state,
            event_type="VERSION_ACTIVATED",
            payload={
                "version_id": version_id,
                "previous_version_id": previous_id,
                "reason": reason,
            },
        )
        self._write_state(state)

        version = self.get_version(version_id)
        if version is None:
            raise RuntimeError("Aktif sürüm okunamadı.")
        return version

    def compare_versions(
        self,
        baseline_version_id: str,
        candidate_version_id: str,
        *,
        metric_name: str = "expectancy",
        higher_is_better: bool = True,
        minimum_improvement_pct: float = 5.0,
        minimum_sample_size: int = 20,
        baseline_sample_size: int | None = None,
        candidate_sample_size: int | None = None,
    ) -> LearningDecision:
        baseline = self.get_version(baseline_version_id)
        candidate = self.get_version(candidate_version_id)

        if baseline is None:
            raise ValueError("Baseline sürümü bulunamadı.")
        if candidate is None:
            raise ValueError("Candidate sürümü bulunamadı.")

        baseline_metric = float(baseline.metrics.get(metric_name, 0.0))
        candidate_metric = float(candidate.metrics.get(metric_name, 0.0))

        baseline_samples = (
            int(baseline_sample_size)
            if baseline_sample_size is not None
            else int(baseline.metrics.get("sample_size", 0))
        )
        candidate_samples = (
            int(candidate_sample_size)
            if candidate_sample_size is not None
            else int(candidate.metrics.get("sample_size", 0))
        )

        if (
            baseline_samples < minimum_sample_size
            or candidate_samples < minimum_sample_size
        ):
            return LearningDecision(
                accepted=False,
                action="REJECT",
                reason="Karşılaştırma için yeterli örnek sayısı yok.",
                baseline_version_id=baseline.version_id,
                candidate_version_id=candidate.version_id,
                metric_name=metric_name,
                baseline_metric=baseline_metric,
                candidate_metric=candidate_metric,
                improvement_pct=0.0,
            )

        improvement_pct = self._improvement_pct(
            baseline_metric,
            candidate_metric,
            higher_is_better=higher_is_better,
        )
        accepted = improvement_pct >= float(minimum_improvement_pct)

        return LearningDecision(
            accepted=accepted,
            action="ACCEPT" if accepted else "REJECT",
            reason=(
                "Candidate sürüm gerekli iyileşme eşiğini geçti."
                if accepted
                else "Candidate sürüm gerekli iyileşme eşiğini geçemedi."
            ),
            baseline_version_id=baseline.version_id,
            candidate_version_id=candidate.version_id,
            metric_name=metric_name,
            baseline_metric=baseline_metric,
            candidate_metric=candidate_metric,
            improvement_pct=round(improvement_pct, 8),
        )

    def apply_decision(
        self,
        decision: LearningDecision,
        *,
        activate_if_accepted: bool = False,
    ) -> None:
        state = self._read_state()

        self._append_event(
            state,
            event_type="LEARNING_DECISION",
            payload=decision.to_dict(),
        )
        self._write_state(state)

        if (
            decision.accepted
            and activate_if_accepted
            and decision.candidate_version_id
        ):
            self.activate_version(
                decision.candidate_version_id,
                reason=decision.reason,
            )

    def rollback(
        self,
        *,
        target_version_id: str | None = None,
        reason: str = "MANUAL_ROLLBACK",
    ) -> ParameterVersion:
        state = self._read_state()
        active_id = state.get("active_version_id")

        if target_version_id is None:
            active = self.get_version(active_id) if active_id else None
            target_version_id = (
                active.parent_version_id
                if active is not None
                else None
            )

        if not target_version_id:
            raise ValueError("Rollback yapılacak hedef sürüm bulunamadı.")

        target = self.activate_version(
            target_version_id,
            reason=reason,
        )

        state = self._read_state()
        self._append_event(
            state,
            event_type="ROLLBACK",
            payload={
                "from_version_id": active_id,
                "to_version_id": target.version_id,
                "reason": reason,
            },
        )
        self._write_state(state)
        return target

    def event_log(self) -> list[dict[str, Any]]:
        return list(self._read_state().get("events", []))

    def learning_report(self) -> dict[str, Any]:
        state = self._read_state()
        versions = state.get("versions", [])
        events = state.get("events", [])

        return {
            "active_version_id": state.get("active_version_id"),
            "total_versions": len(versions),
            "candidate_versions": sum(
                item.get("status") == "CANDIDATE"
                for item in versions
            ),
            "active_versions": sum(
                item.get("status") == "ACTIVE"
                for item in versions
            ),
            "archived_versions": sum(
                item.get("status") == "ARCHIVED"
                for item in versions
            ),
            "total_events": len(events),
            "versions": versions,
            "events": events,
        }

    def export_report(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                self.learning_report(),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return target

    def _read_state(self) -> dict[str, Any]:
        return json.loads(
            self.storage_path.read_text(encoding="utf-8")
        )

    def _write_state(self, state: dict[str, Any]) -> None:
        temp = self.storage_path.with_suffix(
            self.storage_path.suffix + ".tmp"
        )
        temp.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(self.storage_path)

    def _append_event(
        self,
        state: dict[str, Any],
        *,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        state.setdefault("events", []).append(
            {
                "event_id": uuid4().hex,
                "created_at": self._now(),
                "event_type": event_type,
                "payload": payload,
            }
        )

    @staticmethod
    def _new_version_id() -> str:
        return f"PV-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid4().hex[:8]}"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _improvement_pct(
        baseline: float,
        candidate: float,
        *,
        higher_is_better: bool,
    ) -> float:
        if baseline == 0:
            if candidate == 0:
                return 0.0
            return 100.0 if (
                candidate > 0 if higher_is_better else candidate < 0
            ) else -100.0

        raw = (
            ((candidate - baseline) / abs(baseline)) * 100.0
            if higher_is_better
            else ((baseline - candidate) / abs(baseline)) * 100.0
        )
        return raw
