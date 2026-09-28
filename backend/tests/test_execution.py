from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete

from app.db import SessionLocal, TradeRecord
from app.domain import AssetType, Side
from app.engines.strategy_picker import StrategyPicker
from app.services.analytics import analytics_service
from app.services.strategy_management import (
    strategy_management_service,
)
from app.strategies.base import Context
from app.strategies.registry import StrategyRegistry


EXPECTED_STRATEGIES = {
    "Momentum",
    "Breakout",
    "GapAndGo",
    "MeanReversion",
    "ORB",
    "Pullback",
    "SwingTrend",
    "TrendFollowing",
    "VWAP",
    "EMA Crossover",
    "MACD Momentum",
    "Bollinger Breakout",
    "Bollinger Mean Reversion",
    "RSI Reversal",
    "ADX Trend Strength",
    "Supertrend",
    "Donchian Breakout",
    "Volume Breakout",
    "Multi-Factor Confluence",
    "Keltner Channel Breakout",
    "Keltner Mean Reversion",
    "ATR Breakout",
    "ATR Trailing Trend",
    "Parabolic SAR Trend",
    "Ichimoku Cloud Trend",
    "Ichimoku Breakout",
    "Stochastic Reversal",
    "Stochastic Momentum",
    "CCI Reversal",
    "CCI Trend",
    "Williams %R Reversal",
    "ROC Momentum",
    "Price Channel Breakout",
    "Pivot Point Reversal",
    "VWAP Deviation Reversion",
    "Opening Range Momentum",
    "Volume-Weighted Momentum",
    "Relative Strength Rotation",
    "Regime Adaptive Strategy",
}


def bullish_context() -> Context:
    return Context(
        symbol="AAPL",
        asset_type=AssetType.EQUITY,
        price=210.0,
        open_price=205.0,
        previous_close=204.0,
        ema9=209.0,
        ema20=208.0,
        ema50=202.0,
        ema200=190.0,
        vwap=207.0,
        rsi=62.0,
        macd=2.2,
        macd_signal=1.5,
        macd_histogram=0.7,
        atr=4.0,
        atr_pct=1.9,
        bb_lower=198.0,
        bb_middle=205.0,
        bb_upper=212.0,
        volume=2_000_000,
        average_volume=1_000_000,
        volume_ratio=2.0,
        day_high=211.0,
        day_low=203.0,
        opening_range_high=208.5,
        opening_range_low=204.0,
        market_regime="TRENDING",
        trend_strength=0.8,
        sma20=207.0,
        sma50=201.0,
        adx=31.0,
        plus_di=29.0,
        minus_di=14.0,
        stochastic_k=72.0,
        stochastic_d=65.0,
        cci=115.0,
        williams_r=-22.0,
        roc=4.2,
        donchian_high=209.5,
        donchian_low=195.0,
        keltner_middle=205.0,
        keltner_upper=209.0,
        keltner_lower=201.0,
        ichimoku_conversion=208.0,
        ichimoku_base=204.0,
        ichimoku_span_a=206.0,
        ichimoku_span_b=200.0,
        supertrend=204.0,
        psar=203.0,
        source="test-fixture",
        simulated=False,
        automatic_execution_safe=True,
    )


def clear_trade_records():
    with SessionLocal() as session:
        session.execute(
            delete(
                TradeRecord
            )
        )

        session.commit()


def create_trade_record(
    *,
    intent_id: str,
    strategy: str,
    pnl: float | None,
    symbol: str = "AAPL",
):
    now = datetime.now(
        timezone.utc
    )

    with SessionLocal() as session:
        trade = TradeRecord(
            intent_id=intent_id,
            broker="test-broker",
            broker_order_id=(
                f"entry-{intent_id}"
            ),
            exit_broker_order_id=(
                f"exit-{intent_id}"
                if pnl is not None
                else None
            ),
            symbol=symbol,
            asset_type="EQUITY",
            strategy=strategy,
            execution_mode="AUTOMATIC",
            side="BUY",
            qty=1,
            order_type="market",
            time_in_force="day",
            reference_price=200.0,
            entry_price=200.0,
            exit_price=(
                200.0 + pnl
                if pnl is not None
                else None
            ),
            pnl=pnl,
            status=(
                "CLOSED"
                if pnl is not None
                else "FILLED"
            ),
            created_at=now,
            updated_at=now,
            opened_at=now,
            closed_at=(
                now
                if pnl is not None
                else None
            ),
        )

        session.add(
            trade
        )

        session.commit()


def test_registry_contains_exactly_39_expected_strategies():
    names = set(
        StrategyRegistry()
        .list_strategies()
    )

    assert (
        names
        == EXPECTED_STRATEGIES
    )

    assert len(
        names
    ) == 39


def test_every_strategy_instantiates_and_evaluates_without_exception():
    registry = (
        StrategyRegistry()
    )

    ctx = (
        bullish_context()
    )

    for name in (
        registry.list_strategies()
    ):
        strategy = (
            registry.create(
                name
            )
        )

        signal = (
            strategy.signal(
                ctx
            )
        )

        score = (
            strategy.score(
                ctx
            )
        )

        assert (
            0.0
            <= float(score)
            <= 1.0
        ), name

        if signal is not None:
            assert (
                signal.symbol
                == "AAPL"
            ), name

            assert (
                signal.strategy
                == name
            ), name

            assert (
                signal.side
                in {
                    Side.BUY,
                    Side.SELL,
                }
            ), name

            assert (
                0.0
                <= float(
                    signal.confidence
                )
                <= 1.0
            ), name


def test_strategy_picker_resolves_all_builtins():
    picker = (
        StrategyPicker()
    )

    for name in (
        EXPECTED_STRATEGIES
    ):
        assert (
            picker.exists(
                name
            )
        )

        strategy = (
            picker.pick(
                name
            )
        )

        assert (
            strategy.name
            == name
        )


def test_custom_strategy_lifecycle_and_picker_wiring():
    name = (
        "__PhoenixTrend Test "
        "Custom EMA__"
    )

    existing = (
        strategy_management_service
        .custom_get(
            name
        )
    )

    if existing is not None:
        (
            strategy_management_service
            .delete_custom(
                name
            )
        )

    try:
        created = (
            strategy_management_service
            .create_custom(
                name,
                "EMA Crossover",
                {
                    "minimum_score": 0.7
                },
            )
        )

        assert (
            created["custom"]
            is True
        )

        assert (
            created["enabled"]
            is True
        )

        picker = (
            StrategyPicker()
        )

        assert (
            picker.exists(
                name
            )
        )

        assert (
            picker.is_enabled(
                name
            )
            is True
        )

        assert (
            picker.configuration(
                name
            )[
                "minimum_score"
            ]
            == 0.7
        )

        instance = (
            picker.pick(
                name,
                require_enabled=True,
            )
        )

        assert (
            instance.name
            == name
        )

        assert (
            instance.minimum_score
            == 0.7
        )

        (
            strategy_management_service
            .set_custom_enabled(
                name,
                False,
            )
        )

        assert (
            picker.is_enabled(
                name
            )
            is False
        )

        try:
            picker.pick(
                name,
                require_enabled=True,
            )

        except ValueError as exc:
            assert (
                "disabled"
                in str(exc).lower()
            )

        else:
            raise AssertionError(
                "Disabled custom strategy "
                "was allowed for enabled "
                "workflow"
            )

        (
            strategy_management_service
            .set_custom_enabled(
                name,
                True,
            )
        )

        updated = (
            strategy_management_service
            .update_custom_configuration(
                name,
                {
                    "minimum_score": 0.75
                },
            )
        )

        assert (
            updated[
                "configuration"
            ][
                "minimum_score"
            ]
            == 0.75
        )

        reset = (
            strategy_management_service
            .reset_custom_configuration(
                name
            )
        )

        assert (
            reset[
                "configuration"
            ]
            == {}
        )

    finally:
        if (
            strategy_management_service
            .custom_get(
                name
            )
            is not None
        ):
            (
                strategy_management_service
                .delete_custom(
                    name
                )
            )


def test_analytics_uses_only_realized_trades():
    clear_trade_records()

    try:
        create_trade_record(
            intent_id="analytics-win",
            strategy="Momentum",
            pnl=25.0,
        )

        create_trade_record(
            intent_id="analytics-loss",
            strategy="Momentum",
            pnl=-10.0,
        )

        # Open trade must not participate in realized
        # performance.
        create_trade_record(
            intent_id="analytics-open",
            strategy="Momentum",
            pnl=None,
        )

        summary = (
            analytics_service
            .summary()
        )

        assert (
            summary[
                "total_trade_records"
            ]
            == 3
        )

        assert (
            summary[
                "closed_trades"
            ]
            == 2
        )

        assert (
            summary[
                "wins"
            ]
            == 1
        )

        assert (
            summary[
                "losses"
            ]
            == 1
        )

        assert (
            summary[
                "realized_pnl"
            ]
            == 15.0
        )

        assert (
            summary[
                "gross_profit"
            ]
            == 25.0
        )

        assert (
            summary[
                "gross_loss"
            ]
            == 10.0
        )

        assert (
            summary[
                "win_rate"
            ]
            == 50.0
        )

        assert (
            summary[
                "profit_factor"
            ]
            == 2.5
        )

        assert (
            summary[
                "total_return"
            ]
            is None
        )

    finally:
        clear_trade_records()


def test_strategy_analytics_returns_real_metrics():
    clear_trade_records()

    try:
        create_trade_record(
            intent_id="ema-win",
            strategy="EMA Crossover",
            pnl=30.0,
        )

        create_trade_record(
            intent_id="ema-loss",
            strategy="EMA Crossover",
            pnl=-10.0,
        )

        create_trade_record(
            intent_id="ema-flat",
            strategy="EMA Crossover",
            pnl=0.0,
        )

        performance = (
            analytics_service
            .strategy(
                "EMA Crossover"
            )
        )

        assert (
            performance
            is not None
        )

        assert (
            performance[
                "strategy"
            ]
            == "EMA Crossover"
        )

        assert (
            performance[
                "trades"
            ]
            == 3
        )

        assert (
            performance[
                "wins"
            ]
            == 1
        )

        assert (
            performance[
                "losses"
            ]
            == 1
        )

        assert (
            performance[
                "breakeven"
            ]
            == 1
        )

        assert (
            performance[
                "realized_pnl"
            ]
            == 20.0
        )

        assert (
            performance[
                "gross_profit"
            ]
            == 30.0
        )

        assert (
            performance[
                "gross_loss"
            ]
            == 10.0
        )

        assert (
            performance[
                "profit_factor"
            ]
            == 3.0
        )

        assert (
            performance[
                "average_trade"
            ]
            == 6.67
        )

        assert (
            performance[
                "average_win"
            ]
            == 30.0
        )

        assert (
            performance[
                "average_loss"
            ]
            == -10.0
        )

        assert (
            performance[
                "largest_win"
            ]
            == 30.0
        )

        assert (
            performance[
                "largest_loss"
            ]
            == -10.0
        )

        assert (
            performance[
                "total_return"
            ]
            is None
        )

    finally:
        clear_trade_records()


def test_strategy_analytics_name_lookup_is_normalized():
    clear_trade_records()

    try:
        create_trade_record(
            intent_id="normalized-ema",
            strategy="EMA Crossover",
            pnl=12.0,
        )

        expected = (
            analytics_service
            .strategy(
                "EMA Crossover"
            )
        )

        assert (
            expected
            is not None
        )

        underscore = (
            analytics_service
            .strategy(
                "ema_crossover"
            )
        )

        hyphen = (
            analytics_service
            .strategy(
                "ema-crossover"
            )
        )

        spaces = (
            analytics_service
            .strategy(
                "ema crossover"
            )
        )

        assert (
            underscore
            is not None
        )

        assert (
            hyphen
            is not None
        )

        assert (
            spaces
            is not None
        )

        assert (
            underscore[
                "realized_pnl"
            ]
            == 12.0
        )

        assert (
            hyphen[
                "realized_pnl"
            ]
            == 12.0
        )

        assert (
            spaces[
                "realized_pnl"
            ]
            == 12.0
        )

    finally:
        clear_trade_records()


def test_strategy_http_endpoints_are_wired():
    from fastapi.testclient import (
        TestClient,
    )

    from app.main import app

    clear_trade_records()

    client = TestClient(
        app
    )

    response = client.get(
        "/api/strategies"
    )

    assert (
        response.status_code
        == 200
    )

    payload = (
        response.json()
    )

    builtins = [
        item
        for item in payload
        if not item.get(
            "custom"
        )
    ]

    assert (
        len(
            builtins
        )
        == 39
    )

    assert (
        EXPECTED_STRATEGIES
        == {
            item["name"]
            for item in builtins
        }
    )

    detail = client.get(
        "/api/strategies/"
        "EMA%20Crossover"
    )

    assert (
        detail.status_code
        == 200
    )

    assert (
        detail.json()[
            "name"
        ]
        == "EMA Crossover"
    )

    performance = client.get(
        "/api/strategies/"
        "EMA%20Crossover/"
        "performance"
    )

    assert (
        performance.status_code
        == 200
    )

    body = (
        performance.json()
    )

    assert (
        body["strategy"]
        == "EMA Crossover"
    )

    assert (
        body["trades"]
        == 0
    )

    assert (
        body["wins"]
        == 0
    )

    assert (
        body["losses"]
        == 0
    )

    assert (
        body["win_rate"]
        is None
    )

    assert (
        body["realized_pnl"]
        is None
    )

    assert (
        body["total_return"]
        is None
    )


def test_strategy_http_endpoint_exposes_persisted_performance():
    from fastapi.testclient import (
        TestClient,
    )

    from app.main import app

    clear_trade_records()

    try:
        create_trade_record(
            intent_id="http-ema-win",
            strategy="EMA Crossover",
            pnl=50.0,
        )

        create_trade_record(
            intent_id="http-ema-loss",
            strategy="EMA Crossover",
            pnl=-20.0,
        )

        client = TestClient(
            app
        )

        performance = client.get(
            "/api/strategies/"
            "EMA%20Crossover/"
            "performance"
        )

        assert (
            performance.status_code
            == 200
        )

        body = (
            performance.json()
        )

        assert (
            body[
                "strategy"
            ]
            == "EMA Crossover"
        )

        assert (
            body[
                "trades"
            ]
            == 2
        )

        assert (
            body[
                "wins"
            ]
            == 1
        )

        assert (
            body[
                "losses"
            ]
            == 1
        )

        assert (
            body[
                "win_rate"
            ]
            == 50.0
        )

        assert (
            body[
                "realized_pnl"
            ]
            == 30.0
        )

        assert (
            body[
                "gross_profit"
            ]
            == 50.0
        )

        assert (
            body[
                "gross_loss"
            ]
            == 20.0
        )

        assert (
            body[
                "profit_factor"
            ]
            == 2.5
        )

        assert (
            body[
                "total_return"
            ]
            is None
        )

        strategies = client.get(
            "/api/strategies"
        )

        assert (
            strategies.status_code
            == 200
        )

        ema = next(
            item
            for item
            in strategies.json()
            if item.get("name")
            == "EMA Crossover"
        )

        assert (
            ema[
                "performance"
            ]
            is not None
        )

        assert (
            ema[
                "performance"
            ][
                "realized_pnl"
            ]
            == 30.0
        )

    finally:
        clear_trade_records()