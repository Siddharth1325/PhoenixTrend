from __future__ import annotations

from app.domain import AssetType, Side
from app.engines.strategy_picker import StrategyPicker
from app.services.strategy_management import strategy_management_service
from app.strategies.base import Context
from app.strategies.registry import StrategyRegistry


EXPECTED_STRATEGIES = {
    "Momentum", "Breakout", "GapAndGo", "MeanReversion", "ORB", "Pullback",
    "SwingTrend", "TrendFollowing", "VWAP", "EMA Crossover", "MACD Momentum",
    "Bollinger Breakout", "Bollinger Mean Reversion", "RSI Reversal",
    "ADX Trend Strength", "Supertrend", "Donchian Breakout", "Volume Breakout",
    "Multi-Factor Confluence", "Keltner Channel Breakout", "Keltner Mean Reversion",
    "ATR Breakout", "ATR Trailing Trend", "Parabolic SAR Trend",
    "Ichimoku Cloud Trend", "Ichimoku Breakout", "Stochastic Reversal",
    "Stochastic Momentum", "CCI Reversal", "CCI Trend", "Williams %R Reversal",
    "ROC Momentum", "Price Channel Breakout", "Pivot Point Reversal",
    "VWAP Deviation Reversion", "Opening Range Momentum", "Volume-Weighted Momentum",
    "Relative Strength Rotation", "Regime Adaptive Strategy",
}


def bullish_context() -> Context:
    return Context(
        symbol="AAPL", asset_type=AssetType.EQUITY, price=210.0,
        open_price=205.0, previous_close=204.0, ema9=209.0, ema20=208.0,
        ema50=202.0, ema200=190.0, vwap=207.0, rsi=62.0,
        macd=2.2, macd_signal=1.5, macd_histogram=0.7, atr=4.0, atr_pct=1.9,
        bb_lower=198.0, bb_middle=205.0, bb_upper=212.0, volume=2_000_000,
        average_volume=1_000_000, volume_ratio=2.0, day_high=211.0, day_low=203.0,
        opening_range_high=208.5, opening_range_low=204.0, market_regime="TRENDING",
        trend_strength=0.8, sma20=207.0, sma50=201.0, adx=31.0, plus_di=29.0,
        minus_di=14.0, stochastic_k=72.0, stochastic_d=65.0, cci=115.0,
        williams_r=-22.0, roc=4.2, donchian_high=209.5, donchian_low=195.0,
        keltner_middle=205.0, keltner_upper=209.0, keltner_lower=201.0,
        ichimoku_conversion=208.0, ichimoku_base=204.0, ichimoku_span_a=206.0,
        ichimoku_span_b=200.0, supertrend=204.0, psar=203.0,
        source="test-fixture", simulated=False, automatic_execution_safe=True,
    )


def test_registry_contains_exactly_39_expected_strategies():
    names = set(StrategyRegistry().list_strategies())
    assert names == EXPECTED_STRATEGIES
    assert len(names) == 39


def test_every_strategy_instantiates_and_evaluates_without_exception():
    registry = StrategyRegistry()
    ctx = bullish_context()
    for name in registry.list_strategies():
        strategy = registry.create(name)
        signal = strategy.signal(ctx)
        score = strategy.score(ctx)
        assert 0.0 <= float(score) <= 1.0, name
        if signal is not None:
            assert signal.symbol == "AAPL", name
            assert signal.strategy == name, name
            assert signal.side in {Side.BUY, Side.SELL}, name
            assert 0.0 <= float(signal.confidence) <= 1.0, name


def test_strategy_picker_resolves_all_builtins():
    picker = StrategyPicker()
    for name in EXPECTED_STRATEGIES:
        assert picker.exists(name)
        strategy = picker.pick(name)
        assert strategy.name == name


def test_custom_strategy_lifecycle_and_picker_wiring():
    name = "__PhoenixTrend Test Custom EMA__"
    existing = strategy_management_service.custom_get(name)
    if existing is not None:
        strategy_management_service.delete_custom(name)

    try:
        created = strategy_management_service.create_custom(
            name, "EMA Crossover", {"minimum_score": 0.7}
        )
        assert created["custom"] is True
        assert created["enabled"] is True

        picker = StrategyPicker()
        assert picker.exists(name)
        assert picker.is_enabled(name) is True
        assert picker.configuration(name)["minimum_score"] == 0.7

        instance = picker.pick(name, require_enabled=True)
        assert instance.name == name
        assert instance.minimum_score == 0.7

        strategy_management_service.set_custom_enabled(name, False)
        assert picker.is_enabled(name) is False

        try:
            picker.pick(name, require_enabled=True)
        except ValueError as exc:
            assert "disabled" in str(exc).lower()
        else:
            raise AssertionError("Disabled custom strategy was allowed for enabled workflow")

        strategy_management_service.set_custom_enabled(name, True)
        updated = strategy_management_service.update_custom_configuration(
            name, {"minimum_score": 0.75}
        )
        assert updated["configuration"]["minimum_score"] == 0.75

        reset = strategy_management_service.reset_custom_configuration(name)
        assert reset["configuration"] == {}
    finally:
        if strategy_management_service.custom_get(name) is not None:
            strategy_management_service.delete_custom(name)


def test_strategy_http_endpoints_are_wired():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/strategies")
    assert response.status_code == 200
    payload = response.json()
    builtins = [item for item in payload if not item.get("custom")]
    assert len(builtins) == 39
    assert EXPECTED_STRATEGIES == {item["name"] for item in builtins}

    detail = client.get("/api/strategies/EMA%20Crossover")
    assert detail.status_code == 200
    assert detail.json()["name"] == "EMA Crossover"

    performance = client.get("/api/strategies/EMA%20Crossover/performance")
    assert performance.status_code == 200
    assert performance.json()["strategy"] == "EMA Crossover"
