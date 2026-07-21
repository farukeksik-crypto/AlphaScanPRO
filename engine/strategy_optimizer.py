from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from itertools import product
from math import isfinite
from statistics import mean, pstdev
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from engine.backtest_v2 import (
    BacktestBar,
    BacktestConfig,
    BacktestEngineV2,
    BacktestResult,
)


SignalFactory = Callable[
    [Mapping[str, Any]],
    Callable[[int, BacktestBar, Sequence[BacktestBar]], str],
]


@dataclass(slots=True)
class OptimizerWeights:
    net_profit_pct: float = 0.30
    win_rate: float = 0.15
    profit_factor: float = 0.20
    sharpe_ratio: float = 0.20
    max_drawdown_pct: float = 0.15

    def normalized(self) -> "OptimizerWeights":
        values = [
            self.net_profit_pct,
            self.win_rate,
            self.profit_factor,
            self.sharpe_ratio,
            self.max_drawdown_pct,
        ]
        total = sum(abs(value) for value in values)
        if total <= 0:
            raise ValueError("Optimizer ağırlıkları toplamı sıfır olamaz.")
        return OptimizerWeights(
            net_profit_pct=self.net_profit_pct / total,
            win_rate=self.win_rate / total,
            profit_factor=self.profit_factor / total,
            sharpe_ratio=self.sharpe_ratio / total,
            max_drawdown_pct=self.max_drawdown_pct / total,
        )


@dataclass(slots=True)
class OptimizationConfig:
    min_trades: int = 1
    top_n: int = 10
    train_ratio: float = 0.70
    walk_forward_folds: int = 3
    overfit_penalty: float = 0.35
    stability_weight: float = 0.25
    weights: OptimizerWeights = field(default_factory=OptimizerWeights)

    def __post_init__(self) -> None:
        if self.min_trades < 0:
            raise ValueError("min_trades negatif olamaz.")
        if self.top_n <= 0:
            raise ValueError("top_n pozitif olmalıdır.")
        if not 0.50 <= self.train_ratio < 1.0:
            raise ValueError("train_ratio 0.50 ile 1.0 arasında olmalıdır.")
        if self.walk_forward_folds <= 0:
            raise ValueError("walk_forward_folds pozitif olmalıdır.")
        if self.overfit_penalty < 0:
            raise ValueError("overfit_penalty negatif olamaz.")
        if self.stability_weight < 0:
            raise ValueError("stability_weight negatif olamaz.")


@dataclass(slots=True)
class ParameterEvaluation:
    parameters: Dict[str, Any]
    score: float
    backtest: BacktestResult
    rejected: bool = False
    rejection_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameters": dict(self.parameters),
            "score": self.score,
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
            "backtest": self.backtest.to_dict(),
        }


@dataclass(slots=True)
class WalkForwardFold:
    fold_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    best_parameters: Dict[str, Any]
    train_score: float
    test_score: float
    train_result: BacktestResult
    test_result: BacktestResult
    degradation: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fold_index": self.fold_index,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "best_parameters": dict(self.best_parameters),
            "train_score": self.train_score,
            "test_score": self.test_score,
            "degradation": self.degradation,
            "train_result": self.train_result.to_dict(),
            "test_result": self.test_result.to_dict(),
        }


@dataclass(slots=True)
class WalkForwardResult:
    folds: List[WalkForwardFold]
    average_train_score: float
    average_test_score: float
    average_degradation: float
    stability_score: float
    robust_parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "folds": [fold.to_dict() for fold in self.folds],
            "average_train_score": self.average_train_score,
            "average_test_score": self.average_test_score,
            "average_degradation": self.average_degradation,
            "stability_score": self.stability_score,
            "robust_parameters": dict(self.robust_parameters),
        }


@dataclass(slots=True)
class OptimizationReport:
    evaluations: List[ParameterEvaluation]
    best: Optional[ParameterEvaluation]
    walk_forward: Optional[WalkForwardResult]
    parameter_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_count": self.parameter_count,
            "best": self.best.to_dict() if self.best else None,
            "walk_forward": (
                self.walk_forward.to_dict()
                if self.walk_forward else None
            ),
            "evaluations": [
                evaluation.to_dict()
                for evaluation in self.evaluations
            ],
        }


class StrategyOptimizer:
    def __init__(
        self,
        *,
        base_backtest_config: Optional[BacktestConfig] = None,
        config: Optional[OptimizationConfig] = None,
    ) -> None:
        self.base_backtest_config = (
            base_backtest_config or BacktestConfig()
        )
        self.config = config or OptimizationConfig()
        self._weights = self.config.weights.normalized()

    @staticmethod
    def parameter_combinations(
        parameter_grid: Mapping[str, Iterable[Any]],
    ) -> List[Dict[str, Any]]:
        if not parameter_grid:
            return [{}]

        names = list(parameter_grid.keys())
        values = [list(parameter_grid[name]) for name in names]
        if any(not items for items in values):
            raise ValueError("Parametre grid değerleri boş olamaz.")

        return [
            dict(zip(names, combination))
            for combination in product(*values)
        ]

    def _safe_profit_factor(self, value: float) -> float:
        if not isfinite(value):
            return 5.0
        return min(max(value, 0.0), 5.0)

    def score_result(self, result: BacktestResult) -> float:
        if result.total_trades < self.config.min_trades:
            return float("-inf")

        profit_component = max(min(result.net_profit_pct, 1.0), -1.0)
        win_component = max(min(result.win_rate, 1.0), 0.0)
        profit_factor_component = (
            self._safe_profit_factor(result.profit_factor) / 5.0
        )
        sharpe_component = max(
            min(result.sharpe_ratio / 3.0, 1.0),
            -1.0,
        )
        drawdown_component = 1.0 - max(
            min(result.max_drawdown_pct, 1.0),
            0.0,
        )

        return (
            profit_component * self._weights.net_profit_pct
            + win_component * self._weights.win_rate
            + profit_factor_component * self._weights.profit_factor
            + sharpe_component * self._weights.sharpe_ratio
            + drawdown_component * self._weights.max_drawdown_pct
        )

    def _make_backtest_config(
        self,
        parameters: Mapping[str, Any],
    ) -> BacktestConfig:
        allowed = set(asdict(self.base_backtest_config))
        updates = {
            key: value
            for key, value in parameters.items()
            if key in allowed
        }
        return replace(self.base_backtest_config, **updates)

    def evaluate_parameters(
        self,
        *,
        bars: Sequence[BacktestBar],
        parameters: Mapping[str, Any],
        signal_factory: SignalFactory,
    ) -> ParameterEvaluation:
        backtest_config = self._make_backtest_config(parameters)
        signal_function = signal_factory(parameters)
        result = BacktestEngineV2(backtest_config).run(
            bars,
            signal_function,
        )
        score = self.score_result(result)
        rejected = not isfinite(score)
        reason = (
            f"Minimum işlem sayısı {self.config.min_trades} sağlanamadı."
            if rejected else ""
        )
        return ParameterEvaluation(
            parameters=dict(parameters),
            score=score,
            backtest=result,
            rejected=rejected,
            rejection_reason=reason,
        )

    def optimize(
        self,
        *,
        bars: Sequence[BacktestBar],
        parameter_grid: Mapping[str, Iterable[Any]],
        signal_factory: SignalFactory,
    ) -> OptimizationReport:
        if not bars:
            raise ValueError("Optimizasyon için bar verisi gereklidir.")

        combinations = self.parameter_combinations(parameter_grid)
        evaluations = [
            self.evaluate_parameters(
                bars=bars,
                parameters=parameters,
                signal_factory=signal_factory,
            )
            for parameters in combinations
        ]
        evaluations.sort(
            key=lambda item: item.score,
            reverse=True,
        )
        best = next(
            (
                evaluation
                for evaluation in evaluations
                if not evaluation.rejected
            ),
            None,
        )
        return OptimizationReport(
            evaluations=evaluations[: self.config.top_n],
            best=best,
            walk_forward=None,
            parameter_count=len(combinations),
        )

    def _fold_windows(
        self,
        total_bars: int,
    ) -> List[Tuple[int, int, int, int]]:
        if total_bars < 4:
            raise ValueError(
                "Walk-forward için en az 4 bar gereklidir."
            )

        fold_size = max(
            1,
            total_bars // (self.config.walk_forward_folds + 1),
        )
        windows: List[Tuple[int, int, int, int]] = []

        for fold_index in range(self.config.walk_forward_folds):
            train_end = fold_size * (fold_index + 1)
            test_end = min(
                total_bars,
                train_end + fold_size,
            )
            if train_end < 2 or test_end <= train_end:
                continue
            windows.append(
                (0, train_end, train_end, test_end)
            )

        if not windows:
            raise ValueError(
                "Walk-forward pencereleri oluşturulamadı."
            )
        return windows

    def _parameter_consensus(
        self,
        folds: Sequence[WalkForwardFold],
    ) -> Dict[str, Any]:
        if not folds:
            return {}

        keys = set().union(
            *(
                set(fold.best_parameters)
                for fold in folds
            )
        )
        consensus: Dict[str, Any] = {}

        for key in sorted(keys):
            values = [
                fold.best_parameters.get(key)
                for fold in folds
                if key in fold.best_parameters
            ]
            if not values:
                continue

            counts: Dict[str, int] = {}
            originals: Dict[str, Any] = {}
            for value in values:
                token = repr(value)
                counts[token] = counts.get(token, 0) + 1
                originals[token] = value

            winning_token = max(
                counts,
                key=lambda token: (counts[token], token),
            )
            consensus[key] = originals[winning_token]

        return consensus

    def walk_forward(
        self,
        *,
        bars: Sequence[BacktestBar],
        parameter_grid: Mapping[str, Iterable[Any]],
        signal_factory: SignalFactory,
    ) -> WalkForwardResult:
        windows = self._fold_windows(len(bars))
        folds: List[WalkForwardFold] = []

        for index, (
            train_start,
            train_end,
            test_start,
            test_end,
        ) in enumerate(windows, start=1):
            train_bars = bars[train_start:train_end]
            test_bars = bars[test_start:test_end]

            report = self.optimize(
                bars=train_bars,
                parameter_grid=parameter_grid,
                signal_factory=signal_factory,
            )
            if report.best is None:
                continue

            test_evaluation = self.evaluate_parameters(
                bars=test_bars,
                parameters=report.best.parameters,
                signal_factory=signal_factory,
            )
            train_score = report.best.score
            test_score = test_evaluation.score
            degradation = (
                max(0.0, train_score - test_score)
                if isfinite(test_score)
                else 1.0
            )

            folds.append(
                WalkForwardFold(
                    fold_index=index,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    best_parameters=dict(
                        report.best.parameters
                    ),
                    train_score=train_score,
                    test_score=test_score,
                    train_result=report.best.backtest,
                    test_result=test_evaluation.backtest,
                    degradation=degradation,
                )
            )

        if not folds:
            raise ValueError(
                "Walk-forward sonucu üretilemedi."
            )

        train_scores = [fold.train_score for fold in folds]
        test_scores = [fold.test_score for fold in folds]
        degradations = [fold.degradation for fold in folds]
        finite_tests = [
            value for value in test_scores if isfinite(value)
        ]
        average_test = (
            mean(finite_tests)
            if finite_tests else float("-inf")
        )
        variation = (
            pstdev(finite_tests)
            if len(finite_tests) > 1 else 0.0
        )
        stability = max(
            0.0,
            1.0
            - variation * self.config.stability_weight
            - mean(degradations) * self.config.overfit_penalty,
        )

        return WalkForwardResult(
            folds=folds,
            average_train_score=mean(train_scores),
            average_test_score=average_test,
            average_degradation=mean(degradations),
            stability_score=stability,
            robust_parameters=self._parameter_consensus(folds),
        )

    def optimize_with_walk_forward(
        self,
        *,
        bars: Sequence[BacktestBar],
        parameter_grid: Mapping[str, Iterable[Any]],
        signal_factory: SignalFactory,
    ) -> OptimizationReport:
        report = self.optimize(
            bars=bars,
            parameter_grid=parameter_grid,
            signal_factory=signal_factory,
        )
        report.walk_forward = self.walk_forward(
            bars=bars,
            parameter_grid=parameter_grid,
            signal_factory=signal_factory,
        )
        return report

    @staticmethod
    def dashboard(
        report: OptimizationReport,
    ) -> Dict[str, Any]:
        best = report.best
        walk_forward = report.walk_forward
        return {
            "parameter_count": report.parameter_count,
            "evaluated_count": len(report.evaluations),
            "best_parameters": (
                dict(best.parameters) if best else {}
            ),
            "best_score": best.score if best else None,
            "best_net_profit_pct": (
                best.backtest.net_profit_pct
                if best else None
            ),
            "best_win_rate": (
                best.backtest.win_rate if best else None
            ),
            "walk_forward_average_test_score": (
                walk_forward.average_test_score
                if walk_forward else None
            ),
            "walk_forward_stability_score": (
                walk_forward.stability_score
                if walk_forward else None
            ),
            "robust_parameters": (
                dict(walk_forward.robust_parameters)
                if walk_forward else {}
            ),
        }
