from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from engine.signal_engine import MIN_BARS, evaluate


@dataclass
class BacktestConfig:
    initial_cash: float = 100_000.0
    commission_rate: float = 0.001
    position_size_pct: float = 0.95

    entry_decisions: tuple[str, ...] = ("NET AL", "AL ADAY")
    minimum_entry_score: float = 62.0
    exit_score: float = 42.0

    use_signal_exit: bool = True
    max_holding_bars: int = 40

    use_next_bar_open: bool = True
    allow_reentry_same_bar: bool = False


def _empty_result(error: str) -> dict[str, Any]:
    return {
        "error": error,
        "metrics": {},
        "trades": pd.DataFrame(),
        "equity": pd.DataFrame(),
    }


def _calculate_max_drawdown(equity_values: pd.Series) -> float:
    if equity_values.empty:
        return 0.0

    running_peak = equity_values.cummax()
    drawdown = (equity_values / running_peak - 1.0) * 100
    return abs(float(drawdown.min()))


def _calculate_profit_factor(sales: pd.DataFrame) -> float:
    if sales.empty or "Net K/Z" not in sales.columns:
        return 0.0

    gross_profit = float(sales.loc[sales["Net K/Z"] > 0, "Net K/Z"].sum())
    gross_loss = abs(float(sales.loc[sales["Net K/Z"] < 0, "Net K/Z"].sum()))

    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0

    return gross_profit / gross_loss


def _calculate_expectancy(sales: pd.DataFrame) -> float:
    if sales.empty:
        return 0.0
    return float(sales["Net K/Z"].mean())


def _calculate_sharpe(equity: pd.DataFrame) -> float:
    if equity.empty or len(equity) < 3:
        return 0.0

    returns = equity["Bakiye"].pct_change().dropna()
    if returns.empty or returns.std(ddof=0) == 0:
        return 0.0

    return float((returns.mean() / returns.std(ddof=0)) * np.sqrt(252))


def run_backtest(
    frame: pd.DataFrame,
    config: BacktestConfig | None = None,
) -> dict[str, Any]:
    """
    AlphaScan PRO ortak sinyal motoru backtest'i.

    Kurallar:
    - Sinyal kapanmış mum üzerinde hesaplanır.
    - Varsayılan olarak işlem sonraki mumun açılışında gerçekleşir.
    - Stop ve hedef önce kontrol edilir.
    - Aynı mumda hem stop hem hedef görülürse ihtiyatlı davranıp stop seçilir.
    - Komisyon hem alışta hem satışta uygulanır.
    """
    config = config or BacktestConfig()

    if frame is None or frame.empty:
        return _empty_result("Backtest için veri bulunamadı.")

    data = frame.copy()
    data = data[~data.index.duplicated(keep="last")].sort_index()

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        return _empty_result(
            "Eksik OHLCV sütunları: " + ", ".join(missing)
        )

    if len(data) < MIN_BARS + 2:
        return _empty_result(
            f"Yetersiz veri: {len(data)} mum var, "
            f"en az {MIN_BARS + 2} mum gerekiyor."
        )

    cash = float(config.initial_cash)
    quantity = 0.0
    entry_price = 0.0
    entry_time = None
    entry_reason = ""
    entry_score = 0.0
    stop_price = 0.0
    target_price = 0.0
    entry_index = None
    total_commission = 0.0

    trade_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []

    start_index = MIN_BARS

    for signal_index in range(start_index, len(data) - 1):
        signal_frame = data.iloc[: signal_index + 1]
        signal = evaluate(signal_frame)

        signal_time = data.index[signal_index]
        next_index = signal_index + 1

        execution_price = (
            float(data["Open"].iloc[next_index])
            if config.use_next_bar_open
            else float(data["Close"].iloc[signal_index])
        )
        execution_time = (
            data.index[next_index]
            if config.use_next_bar_open
            else signal_time
        )

        current_close = float(data["Close"].iloc[signal_index])
        marked_equity = cash + quantity * current_close

        equity_rows.append(
            {
                "Tarih": signal_time,
                "Bakiye": marked_equity,
                "Nakit": cash,
                "Pozisyon Değeri": quantity * current_close,
            }
        )

        if quantity <= 0:
            may_enter = (
                signal.get("ok")
                and signal.get("decision") in config.entry_decisions
                and float(signal.get("score", 0)) >= config.minimum_entry_score
            )

            if not may_enter:
                continue

            available_budget = cash * config.position_size_pct
            buy_commission_rate = 1.0 + config.commission_rate
            quantity_to_buy = available_budget / (
                execution_price * buy_commission_rate
            )

            if quantity_to_buy <= 0:
                continue

            gross_cost = quantity_to_buy * execution_price
            buy_commission = gross_cost * config.commission_rate
            total_cost = gross_cost + buy_commission

            if total_cost > cash:
                continue

            cash -= total_cost
            quantity = quantity_to_buy
            entry_price = execution_price
            entry_time = execution_time
            entry_reason = str(signal.get("reason", ""))
            entry_score = float(signal.get("score", 0))
            stop_price = float(signal.get("stop", 0))
            target_price = float(signal.get("target", 0))
            entry_index = next_index
            total_commission += buy_commission

            trade_rows.append(
                {
                    "Tarih": execution_time,
                    "İşlem": "AL",
                    "Fiyat": execution_price,
                    "Miktar": quantity,
                    "Komisyon": buy_commission,
                    "Skor": entry_score,
                    "Neden": entry_reason,
                    "Stop": stop_price,
                    "Hedef": target_price,
                    "Net K/Z": np.nan,
                    "K/Z %": np.nan,
                    "Tutulan Mum": 0,
                }
            )
            continue

        # Açık pozisyon yönetimi
        bar_high = float(data["High"].iloc[next_index])
        bar_low = float(data["Low"].iloc[next_index])
        bar_close = float(data["Close"].iloc[next_index])

        exit_reason = None
        exit_price = None

        stop_hit = stop_price > 0 and bar_low <= stop_price
        target_hit = target_price > 0 and bar_high >= target_price

        if stop_hit and target_hit:
            # Mum içi sıra bilinmediği için ihtiyatlı varsayım.
            exit_reason = "STOP (aynı mumda hedef de görüldü)"
            exit_price = stop_price
        elif stop_hit:
            exit_reason = "STOP"
            exit_price = stop_price
        elif target_hit:
            exit_reason = "HEDEF"
            exit_price = target_price
        else:
            holding_bars = (
                next_index - entry_index
                if entry_index is not None
                else 0
            )

            if (
                config.use_signal_exit
                and signal.get("ok")
                and (
                    signal.get("decision") == "BEKLE"
                    or float(signal.get("score", 0)) < config.exit_score
                )
            ):
                exit_reason = (
                    f"SİNYAL ZAYIFLADI | "
                    f"Skor {float(signal.get('score', 0)):.1f}"
                )
                exit_price = execution_price
            elif (
                config.max_holding_bars > 0
                and holding_bars >= config.max_holding_bars
            ):
                exit_reason = "MAKSİMUM BEKLEME"
                exit_price = execution_price

        if exit_reason is None or exit_price is None:
            continue

        gross_revenue = quantity * exit_price
        sell_commission = gross_revenue * config.commission_rate
        net_revenue = gross_revenue - sell_commission
        cash += net_revenue
        total_commission += sell_commission

        entry_gross = quantity * entry_price
        entry_commission = entry_gross * config.commission_rate
        net_pnl = (
            net_revenue
            - entry_gross
            - entry_commission
        )
        pnl_pct = (
            net_pnl / (entry_gross + entry_commission) * 100
            if entry_gross > 0
            else 0.0
        )
        holding_bars = (
            next_index - entry_index
            if entry_index is not None
            else 0
        )

        trade_rows.append(
            {
                "Tarih": data.index[next_index],
                "İşlem": "SAT",
                "Fiyat": exit_price,
                "Miktar": quantity,
                "Komisyon": sell_commission,
                "Skor": float(signal.get("score", 0)),
                "Neden": exit_reason,
                "Stop": stop_price,
                "Hedef": target_price,
                "Net K/Z": net_pnl,
                "K/Z %": pnl_pct,
                "Tutulan Mum": holding_bars,
            }
        )

        quantity = 0.0
        entry_price = 0.0
        entry_time = None
        entry_reason = ""
        entry_score = 0.0
        stop_price = 0.0
        target_price = 0.0
        entry_index = None

        if not config.allow_reentry_same_bar:
            continue

    # Test sonunda açık pozisyonu son kapanıştan kapat
    if quantity > 0:
        final_price = float(data["Close"].iloc[-1])
        final_time = data.index[-1]
        gross_revenue = quantity * final_price
        sell_commission = gross_revenue * config.commission_rate
        net_revenue = gross_revenue - sell_commission
        cash += net_revenue
        total_commission += sell_commission

        entry_gross = quantity * entry_price
        entry_commission = entry_gross * config.commission_rate
        net_pnl = net_revenue - entry_gross - entry_commission
        pnl_pct = (
            net_pnl / (entry_gross + entry_commission) * 100
            if entry_gross > 0
            else 0.0
        )
        holding_bars = (
            len(data) - 1 - entry_index
            if entry_index is not None
            else 0
        )

        trade_rows.append(
            {
                "Tarih": final_time,
                "İşlem": "SAT",
                "Fiyat": final_price,
                "Miktar": quantity,
                "Komisyon": sell_commission,
                "Skor": np.nan,
                "Neden": "TEST SONU",
                "Stop": stop_price,
                "Hedef": target_price,
                "Net K/Z": net_pnl,
                "K/Z %": pnl_pct,
                "Tutulan Mum": holding_bars,
            }
        )

        quantity = 0.0

    final_equity = cash
    equity_rows.append(
        {
            "Tarih": data.index[-1],
            "Bakiye": final_equity,
            "Nakit": cash,
            "Pozisyon Değeri": 0.0,
        }
    )

    trades = pd.DataFrame(trade_rows)
    equity = pd.DataFrame(equity_rows)

    if equity.empty:
        equity = pd.DataFrame(
            [
                {
                    "Tarih": data.index[-1],
                    "Bakiye": final_equity,
                    "Nakit": final_equity,
                    "Pozisyon Değeri": 0.0,
                }
            ]
        )

    sales = (
        trades[trades["İşlem"] == "SAT"].copy()
        if not trades.empty
        else pd.DataFrame()
    )

    total_trades = len(sales)
    winners = int((sales["Net K/Z"] > 0).sum()) if not sales.empty else 0
    losers = int((sales["Net K/Z"] < 0).sum()) if not sales.empty else 0
    win_rate = winners / total_trades * 100 if total_trades else 0.0

    total_return_pct = (
        final_equity / config.initial_cash - 1
    ) * 100

    average_profit = (
        float(sales.loc[sales["Net K/Z"] > 0, "Net K/Z"].mean())
        if winners
        else 0.0
    )
    average_loss = (
        float(sales.loc[sales["Net K/Z"] < 0, "Net K/Z"].mean())
        if losers
        else 0.0
    )
    average_holding = (
        float(sales["Tutulan Mum"].mean())
        if total_trades
        else 0.0
    )

    first_close = float(data["Close"].iloc[start_index])
    last_close = float(data["Close"].iloc[-1])
    buy_hold_pct = (
        (last_close / first_close - 1) * 100
        if first_close > 0
        else 0.0
    )

    metrics = {
        "Başlangıç Bakiye": float(config.initial_cash),
        "Son Bakiye": float(final_equity),
        "Toplam Getiri %": float(total_return_pct),
        "Al-Tut Getirisi %": float(buy_hold_pct),
        "Toplam İşlem": int(total_trades),
        "Kazanan": int(winners),
        "Kaybeden": int(losers),
        "Başarı Oranı %": float(win_rate),
        "Kâr Faktörü": float(_calculate_profit_factor(sales)),
        "Maksimum Düşüş %": float(
            _calculate_max_drawdown(equity["Bakiye"])
        ),
        "Ortalama Kâr": float(average_profit),
        "Ortalama Zarar": float(average_loss),
        "Beklenen Değer": float(_calculate_expectancy(sales)),
        "Ortalama Tutulan Mum": float(average_holding),
        "Sharpe": float(_calculate_sharpe(equity)),
        "Toplam Komisyon": float(total_commission),
        "Mum Sayısı": int(len(data)),
    }

    return {
        "error": None,
        "metrics": metrics,
        "trades": trades,
        "equity": equity,
    }