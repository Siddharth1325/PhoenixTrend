from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..domain import AssetType, Signal


@dataclass
class Context:
    """
    Shared normalized PhoenixTrend strategy context.

    Market analysis is calculated once before strategies run.
    Strategies consume this context and do not download data,
    place orders, or bypass risk/execution controls.
    """

    # Instrument
    symbol: str
    asset_type: AssetType = AssetType.EQUITY

    # Price
    price: float = 0.0
    open_price: float | None = None
    previous_close: float | None = None

    # Trend
    ema9: float | None = None
    ema20: float = 0.0
    ema50: float = 0.0
    ema200: float | None = None

    # VWAP
    vwap: float = 0.0

    # Momentum
    rsi: float = 50.0
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None

    # Volatility
    atr: float | None = None
    atr_pct: float | None = None

    # Bollinger Bands
    # These names intentionally match indicators.py,
    # decision_engine.py, and MeanReversion.
    bb_lower: float | None = None
    bb_middle: float | None = None
    bb_upper: float | None = None

    # Volume
    volume: float | None = None
    average_volume: float | None = None
    volume_ratio: float = 1.0

    # Session/reference levels
    day_high: float = 0.0
    day_low: float = 0.0

    # Opening Range Breakout levels
    opening_range_high: float | None = None
    opening_range_low: float | None = None

    # Market structure
    market_regime: str = "NEUTRAL"
    trend_strength: float = 0.0

    # Advanced indicators calculated from real OHLCV bars
    sma20: float | None = None
    sma50: float | None = None
    adx: float | None = None
    plus_di: float | None = None
    minus_di: float | None = None
    stochastic_k: float | None = None
    stochastic_d: float | None = None
    cci: float | None = None
    williams_r: float | None = None
    roc: float | None = None
    donchian_high: float | None = None
    donchian_low: float | None = None
    keltner_middle: float | None = None
    keltner_upper: float | None = None
    keltner_lower: float | None = None
    ichimoku_conversion: float | None = None
    ichimoku_base: float | None = None
    ichimoku_span_a: float | None = None
    ichimoku_span_b: float | None = None
    supertrend: float | None = None
    psar: float | None = None

    # Chart patterns
    patterns: list[dict[str, Any]] = field(default_factory=list)

    # Market-data metadata
    source: str | None = None
    as_of: str | None = None
    simulated: bool = False
    automatic_execution_safe: bool = False

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()

        if not self.symbol:
            raise ValueError("Context symbol is required.")

        if self.price <= 0:
            raise ValueError(
                "Context price must be greater than zero."
            )

        if self.ema20 <= 0:
            raise ValueError(
                "EMA20 must be greater than zero."
            )

        if self.ema50 <= 0:
            raise ValueError(
                "EMA50 must be greater than zero."
            )

        if self.vwap <= 0:
            raise ValueError(
                "VWAP must be greater than zero."
            )

        if not 0 <= self.rsi <= 100:
            raise ValueError(
                "RSI must be between 0 and 100."
            )

        if self.volume_ratio < 0:
            raise ValueError(
                "Volume ratio cannot be negative."
            )

        if self.atr is not None and self.atr < 0:
            raise ValueError(
                "ATR cannot be negative."
            )

        if self.atr_pct is not None and self.atr_pct < 0:
            raise ValueError(
                "ATR percentage cannot be negative."
            )

        if self.trend_strength < 0:
            raise ValueError(
                "Trend strength cannot be negative."
            )

        if (
            self.day_high > 0
            and self.day_low > 0
            and self.day_high < self.day_low
        ):
            raise ValueError(
                "day_high cannot be below day_low."
            )

        if (
            self.opening_range_high is not None
            and self.opening_range_low is not None
            and self.opening_range_high
            < self.opening_range_low
        ):
            raise ValueError(
                "opening_range_high cannot be below "
                "opening_range_low."
            )

        if (
            self.bb_upper is not None
            and self.bb_lower is not None
            and self.bb_upper < self.bb_lower
        ):
            raise ValueError(
                "bb_upper cannot be below bb_lower."
            )

        self.market_regime = (
            self.market_regime.strip().upper()
            or "NEUTRAL"
        )

    @property
    def bullish_trend(self) -> bool:
        return self.price > self.ema20 > self.ema50

    @property
    def bearish_trend(self) -> bool:
        return self.price < self.ema20 < self.ema50

    @property
    def above_vwap(self) -> bool:
        return self.price > self.vwap

    @property
    def below_vwap(self) -> bool:
        return self.price < self.vwap

    @property
    def high_relative_volume(self) -> bool:
        return self.volume_ratio >= 1.5

    def has_pattern(
        self,
        pattern_name: str,
    ) -> bool:
        requested = pattern_name.strip().lower()

        for pattern in self.patterns:
            name = str(
                pattern.get("name", "")
            ).strip().lower()

            if name == requested:
                return True

        return False

    def pattern_confidence(
        self,
        pattern_name: str,
    ) -> float:
        requested = pattern_name.strip().lower()

        for pattern in self.patterns:
            name = str(
                pattern.get("name", "")
            ).strip().lower()

            if name != requested:
                continue

            try:
                confidence = float(
                    pattern.get("confidence", 0.0)
                )
            except (TypeError, ValueError):
                return 0.0

            return max(
                0.0,
                min(confidence, 1.0),
            )

        return 0.0


class Strategy(ABC):
    """
    Base class for every PhoenixTrend strategy.

    A strategy returns:
        Signal -> actionable setup
        None   -> HOLD / no trade
    """

    name: str = "Base"

    @abstractmethod
    def signal(
        self,
        ctx: Context,
    ) -> Signal | None:
        raise NotImplementedError

    def score(
        self,
        ctx: Context,
    ) -> float:
        signal = self.signal(ctx)

        if signal is None:
            return 0.0

        return max(
            0.0,
            min(float(signal.confidence), 1.0),
        )

    def describe(
        self,
    ) -> dict[str, Any]:
        return {
            "name": self.name,
            "class": self.__class__.__name__,
            "module": self.__class__.__module__,
        }