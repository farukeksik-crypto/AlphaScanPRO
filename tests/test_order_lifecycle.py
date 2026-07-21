from __future__ import annotations

from datetime import timedelta

import pytest

from engine.order_lifecycle import (
    ExecutionDecision,
    Fill,
    OrderManager,
    OrderManagerConfig,
    OrderRecord,
    OrderRequest,
    OrderRuntimeBridge,
    OrderSide,
    OrderStatus,
    OrderType,
    SimulatedBroker,
    SimulatedBrokerConfig,
    utc_now,
)


def market_request(**kwargs):
    data = {
        "symbol": "BTCUSDT",
        "side": OrderSide.BUY,
        "quantity": 2,
    }
    data.update(kwargs)
    return OrderRequest(**data)


def test_request_normalization():
    item = market_request(symbol=" btcusdt ")
    assert item.symbol == "BTCUSDT"


def test_invalid_quantity():
    with pytest.raises(ValueError):
        market_request(quantity=0)


def test_limit_requires_price():
    with pytest.raises(ValueError):
        market_request(order_type=OrderType.LIMIT)


def test_request_to_dict():
    item = market_request()
    assert item.to_dict()["side"] == "BUY"


def test_fill_validation():
    with pytest.raises(ValueError):
        Fill(quantity=0, price=100)


def test_fill_gross_value():
    fill = Fill(quantity=2, price=100)
    assert fill.gross_value == 200


def test_record_initial_state():
    record = OrderRecord(market_request())
    assert record.status == OrderStatus.CREATED
    assert record.remaining_quantity == 2


def test_partial_fill():
    record = OrderRecord(market_request())
    record.add_fill(Fill(quantity=1, price=100))
    assert record.status == OrderStatus.PARTIALLY_FILLED
    assert record.remaining_quantity == 1


def test_full_fill():
    record = OrderRecord(market_request())
    record.add_fill(Fill(quantity=2, price=100))
    assert record.status == OrderStatus.FILLED
    assert record.is_terminal


def test_overfill_rejected():
    record = OrderRecord(market_request())
    with pytest.raises(ValueError):
        record.add_fill(Fill(quantity=3, price=100))


def test_average_price():
    record = OrderRecord(market_request(quantity=2))
    record.add_fill(Fill(quantity=1, price=100))
    record.add_fill(Fill(quantity=1, price=110))
    assert record.average_fill_price == 105


def test_total_commission():
    record = OrderRecord(market_request(quantity=2))
    record.add_fill(Fill(quantity=1, price=100, commission=0.1))
    record.add_fill(Fill(quantity=1, price=100, commission=0.2))
    assert record.total_commission == pytest.approx(0.3)


def test_terminal_status_block():
    record = OrderRecord(market_request())
    record.set_status(OrderStatus.CANCELLED)
    with pytest.raises(RuntimeError):
        record.set_status(OrderStatus.SUBMITTED)


def test_simulated_market_fill():
    broker = SimulatedBroker()
    record = OrderRecord(market_request())
    response = broker.submit(record, market_price=100)
    assert response.decision == ExecutionDecision.ACCEPTED
    assert response.fills[0].price == 100


def test_simulated_slippage_buy():
    broker = SimulatedBroker(SimulatedBrokerConfig(slippage_pct=1))
    record = OrderRecord(market_request())
    response = broker.submit(record, market_price=100)
    assert response.fills[0].price == 101


def test_simulated_slippage_sell():
    broker = SimulatedBroker(SimulatedBrokerConfig(slippage_pct=1))
    record = OrderRecord(market_request(side=OrderSide.SELL))
    response = broker.submit(record, market_price=100)
    assert response.fills[0].price == 99


def test_simulated_limit_fill():
    broker = SimulatedBroker()
    record = OrderRecord(
        market_request(order_type=OrderType.LIMIT, limit_price=95)
    )
    response = broker.submit(record)
    assert response.fills[0].price == 95


def test_simulated_reject_symbol():
    broker = SimulatedBroker(
        SimulatedBrokerConfig(reject_symbols=["BTCUSDT"])
    )
    response = broker.submit(OrderRecord(market_request()), market_price=100)
    assert response.decision == ExecutionDecision.FINAL
    assert response.error


def test_simulated_retry():
    broker = SimulatedBroker(
        SimulatedBrokerConfig(retry_failures=1)
    )
    record = OrderRecord(market_request())
    first = broker.submit(record, market_price=100)
    second = broker.submit(record, market_price=100)
    assert first.decision == ExecutionDecision.RETRY
    assert second.decision == ExecutionDecision.ACCEPTED


def test_manager_create_order():
    manager = OrderManager(SimulatedBroker())
    order = manager.create_order(market_request())
    assert manager.get_order(order.client_order_id) is order


def test_duplicate_id():
    manager = OrderManager(SimulatedBroker())
    request = market_request()
    manager.create_order(request)
    with pytest.raises(ValueError):
        manager.create_order(request)


def test_duplicate_active_order():
    manager = OrderManager(SimulatedBroker())
    manager.create_order(market_request())
    with pytest.raises(ValueError):
        manager.create_order(market_request())


def test_duplicate_can_be_disabled():
    manager = OrderManager(
        SimulatedBroker(),
        OrderManagerConfig(block_duplicate_active_orders=False),
    )
    manager.create_order(market_request())
    manager.create_order(market_request())
    assert len(manager.active_orders()) == 2


def test_queue_order():
    manager = OrderManager(SimulatedBroker())
    order = manager.create_order(market_request())
    manager.queue_order(order.client_order_id)
    assert order.status == OrderStatus.QUEUED
    assert manager.dashboard()["queued_orders"] == 1


def test_process_next():
    manager = OrderManager(SimulatedBroker())
    order = manager.create_order(market_request())
    manager.queue_order(order.client_order_id)
    result = manager.process_next(market_prices={"BTCUSDT": 100})
    assert result.status == OrderStatus.FILLED


def test_process_all():
    manager = OrderManager(
        SimulatedBroker(),
        OrderManagerConfig(block_duplicate_active_orders=False),
    )
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        item = manager.create_order(market_request(symbol=symbol))
        manager.queue_order(item.client_order_id)
    results = manager.process_all(
        market_prices={"BTCUSDT": 100, "ETHUSDT": 200}
    )
    assert len(results) == 2
    assert all(item.status == OrderStatus.FILLED for item in results)


def test_retry_requeued():
    manager = OrderManager(
        SimulatedBroker(SimulatedBrokerConfig(retry_failures=1)),
        OrderManagerConfig(max_retries=2),
    )
    order = manager.create_order(market_request())
    manager.queue_order(order.client_order_id)
    first = manager.process_next(market_prices={"BTCUSDT": 100})
    assert first.status == OrderStatus.QUEUED
    second = manager.process_next(market_prices={"BTCUSDT": 100})
    assert second.status == OrderStatus.FILLED


def test_retry_limit_failed():
    manager = OrderManager(
        SimulatedBroker(SimulatedBrokerConfig(retry_failures=5)),
        OrderManagerConfig(max_retries=1),
    )
    order = manager.create_order(market_request())
    manager.queue_order(order.client_order_id)
    manager.process_next(market_prices={"BTCUSDT": 100})
    result = manager.process_next(market_prices={"BTCUSDT": 100})
    assert result.status == OrderStatus.FAILED


def test_partial_fill_lifecycle():
    manager = OrderManager(
        SimulatedBroker(SimulatedBrokerConfig(partial_fill_ratio=0.5))
    )
    order = manager.create_order(market_request(quantity=2))
    manager.queue_order(order.client_order_id)
    first = manager.process_next(market_prices={"BTCUSDT": 100})
    assert first.status == OrderStatus.PARTIALLY_FILLED
    manager.queue_order(order.client_order_id)
    second = manager.process_next(market_prices={"BTCUSDT": 100})
    assert second.status == OrderStatus.FILLED


def test_cancel_order():
    manager = OrderManager(SimulatedBroker())
    order = manager.create_order(market_request())
    manager.queue_order(order.client_order_id)
    result = manager.cancel_order(order.client_order_id)
    assert result.status == OrderStatus.CANCELLED
    assert manager.dashboard()["queued_orders"] == 0


def test_expire_order():
    manager = OrderManager(
        SimulatedBroker(),
        OrderManagerConfig(order_timeout_seconds=1),
    )
    request = market_request()
    request.created_at = utc_now() - timedelta(seconds=5)
    order = manager.create_order(request)
    expired = manager.expire_orders()
    assert expired == [order]
    assert order.status == OrderStatus.EXPIRED


def test_history_limit():
    manager = OrderManager(
        SimulatedBroker(),
        OrderManagerConfig(
            block_duplicate_active_orders=False,
            history_limit=2,
        ),
    )
    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        manager.create_order(market_request(symbol=symbol))
    assert len(manager.history()) == 2


def test_dashboard():
    manager = OrderManager(SimulatedBroker())
    order = manager.create_order(market_request())
    manager.queue_order(order.client_order_id)
    manager.process_next(market_prices={"BTCUSDT": 100})
    data = manager.dashboard()
    assert data["total_orders"] == 1
    assert data["terminal_orders"] == 1
    assert data["filled_value"] == 200


def test_record_to_dict():
    record = OrderRecord(market_request())
    data = record.to_dict()
    assert data["status"] == "CREATED"
    assert data["request"]["symbol"] == "BTCUSDT"


def test_runtime_bridge():
    class Decision:
        symbol = "BTCUSDT"
        quantity = 1
        action = OrderSide.BUY
        score = 80
        reason = "test"

    manager = OrderManager(SimulatedBroker())
    bridge = OrderRuntimeBridge(manager)
    result = bridge.submit_decision(Decision(), market_price=100)
    assert result.status == OrderStatus.FILLED
    assert result.request.metadata["score"] == 80


def test_market_price_missing_retries():
    manager = OrderManager(
        SimulatedBroker(),
        OrderManagerConfig(max_retries=1),
    )
    order = manager.create_order(market_request())
    manager.queue_order(order.client_order_id)
    result = manager.process_next()
    assert result.status == OrderStatus.QUEUED


def test_invalid_manager_config():
    with pytest.raises(ValueError):
        OrderManagerConfig(max_retries=-1)


def test_invalid_broker_config():
    with pytest.raises(ValueError):
        SimulatedBrokerConfig(partial_fill_ratio=0)
