from __future__ import annotations

from typing import Type

from .base import Strategy
from .breakout import BreakoutStrategy
from .gapgo import GapAndGoStrategy
from .meanreversion import MeanReversionStrategy
from .momentum import MomentumStrategy
from .orb import ORBStrategy
from .pullback import PullbackStrategy
from .swingtrend import SwingTrendStrategy
from .trendfollowing import TrendFollowingStrategy
from .vwap import VWAPStrategy
from .adx_trend_strength import ADXTrendStrengthStrategy
from .supertrend import SupertrendStrategy
from .donchian_breakout import DonchianBreakoutStrategy
from .volume_breakout import VolumeBreakoutStrategy
from .multi_factor_confluence import MultiFactorConfluenceStrategy
from .keltner_channel_breakout import KeltnerChannelBreakoutStrategy
from .keltner_mean_reversion import KeltnerMeanReversionStrategy
from .atr_breakout import ATRBreakoutStrategy
from .atr_trailing_trend import ATRTrailingTrendStrategy
from .parabolic_sar_trend import ParabolicSARTrendStrategy
from .ichimoku_cloud_trend import IchimokuCloudTrendStrategy
from .ichimoku_breakout import IchimokuBreakoutStrategy
from .stochastic_reversal import StochasticReversalStrategy
from .stochastic_momentum import StochasticMomentumStrategy
from .cci_reversal import CCIReversalStrategy
from .cci_trend import CCITrendStrategy
from .williams_r_reversal import WilliamsRReversalStrategy
from .roc_momentum import ROCMomentumStrategy
from .price_channel_breakout import PriceChannelBreakoutStrategy
from .pivot_point_reversal import PivotPointReversalStrategy
from .vwap_deviation_reversion import VWAPDeviationReversionStrategy
from .opening_range_momentum import OpeningRangeMomentumStrategy
from .volume_weighted_momentum import VolumeWeightedMomentumStrategy
from .relative_strength_rotation import RelativeStrengthRotationStrategy
from .regime_adaptive import RegimeAdaptiveStrategy
from .ema_crossover import EMACrossoverStrategy
from .macd_momentum import MACDMomentumStrategy
from .bollinger_breakout import BollingerBreakoutStrategy
from .bollinger_mean_reversion import BollingerMeanReversionStrategy
from .rsi_reversal import RSIReversalStrategy


# ============================================================
# REGISTERED PHOENIXTREND STRATEGIES
# ============================================================


STRATEGY_CLASSES: dict[str, Type[Strategy]] = {
    strategy_class.name: strategy_class
    for strategy_class in (
        MomentumStrategy,
        BreakoutStrategy,
        VWAPStrategy,
        ORBStrategy,
        GapAndGoStrategy,
        SwingTrendStrategy,
        PullbackStrategy,
        MeanReversionStrategy,
        TrendFollowingStrategy,
        ADXTrendStrengthStrategy,
        SupertrendStrategy,
        DonchianBreakoutStrategy,
        VolumeBreakoutStrategy,
        MultiFactorConfluenceStrategy,
        KeltnerChannelBreakoutStrategy,
        KeltnerMeanReversionStrategy,
        ATRBreakoutStrategy,
        ATRTrailingTrendStrategy,
        ParabolicSARTrendStrategy,
        IchimokuCloudTrendStrategy,
        IchimokuBreakoutStrategy,
        StochasticReversalStrategy,
        StochasticMomentumStrategy,
        CCIReversalStrategy,
        CCITrendStrategy,
        WilliamsRReversalStrategy,
        ROCMomentumStrategy,
        PriceChannelBreakoutStrategy,
        PivotPointReversalStrategy,
        VWAPDeviationReversionStrategy,
        OpeningRangeMomentumStrategy,
        VolumeWeightedMomentumStrategy,
        RelativeStrengthRotationStrategy,
        RegimeAdaptiveStrategy,
        EMACrossoverStrategy,
        MACDMomentumStrategy,
        BollingerBreakoutStrategy,
        BollingerMeanReversionStrategy,
        RSIReversalStrategy,
    )
}


# ============================================================
# STRATEGY REGISTRY
# ============================================================


class StrategyRegistry:
    """
    Central registry for PhoenixTrend strategies.

    Responsibilities:

    - list registered strategies
    - normalize strategy names
    - resolve user/API strategy names
    - create fresh strategy instances
    - apply optional strategy configuration

    The registry does NOT decide which strategy is best.

    Strategy selection belongs to StrategySelector.
    """


    def list_strategies(
        self,
    ) -> list[str]:

        return list(
            STRATEGY_CLASSES.keys()
        )


    @staticmethod
    def _normalize(
        value: str,
    ) -> str:

        return (
            (value or "")
            .strip()
            .lower()
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
        )


    def resolve_name(
        self,
        name: str,
    ) -> str:

        wanted = self._normalize(
            name
        )

        if not wanted:
            raise ValueError(
                "Strategy name is required."
            )

        for canonical in (
            STRATEGY_CLASSES
        ):

            if (
                self._normalize(
                    canonical
                )
                == wanted
            ):
                return canonical

        available = ", ".join(
            self.list_strategies()
        )

        raise ValueError(
            f"Unknown strategy '{name}'. "
            f"Available strategies: {available}"
        )


    def exists(
        self,
        name: str,
    ) -> bool:

        try:

            self.resolve_name(
                name
            )

            return True

        except ValueError:

            return False


    def create(
        self,
        name: str,
        **config,
    ) -> Strategy:

        canonical = (
            self.resolve_name(
                name
            )
        )

        strategy_class = (
            STRATEGY_CLASSES[
                canonical
            ]
        )

        strategy = (
            strategy_class()
        )


        # Apply only known strategy configuration fields.
        #
        # This allows things such as thresholds to be tuned
        # without allowing arbitrary attributes to be added.

        for key, value in (
            config.items()
        ):

            if not hasattr(
                strategy,
                key,
            ):
                raise ValueError(
                    f"Strategy '{canonical}' "
                    f"does not support configuration "
                    f"field '{key}'."
                )

            setattr(
                strategy,
                key,
                value,
            )


        return strategy


    # Backward-compatible alias.
    get = create

    @staticmethod
    def _category_for(
        name: str,
    ) -> str:
        value = name.lower()

        if any(
            token in value
            for token in (
                "mean reversion",
                "reversion",
                "reversal",
            )
        ):
            return "Mean Reversion"

        if any(
            token in value
            for token in (
                "breakout",
                "orb",
                "gap",
                "price channel",
                "donchian",
            )
        ):
            return "Breakout"

        if any(
            token in value
            for token in (
                "momentum",
                "roc",
            )
        ):
            return "Momentum"

        if any(
            token in value
            for token in (
                "swing",
                "pullback",
                "pivot",
            )
        ):
            return "Swing"

        if any(
            token in value
            for token in (
                "trend",
                "supertrend",
                "crossover",
                "adx",
                "parabolic",
                "ichimoku cloud",
            )
        ):
            return "Trend Following"

        if any(
            token in value
            for token in (
                "relative strength",
                "regime",
                "multi factor",
                "confluence",
            )
        ):
            return "Adaptive"

        if "vwap" in value:
            return "Scalping"

        return "Systematic"

    @staticmethod
    def _timeframe_for(
        name: str,
    ) -> str:
        value = name.lower()

        if any(
            token in value
            for token in (
                "orb",
                "opening range",
                "gap",
                "vwap",
            )
        ):
            return "Intraday"

        if any(
            token in value
            for token in (
                "swing",
                "relative strength rotation",
            )
        ):
            return "Swing"

        return "Adaptive"

    @staticmethod
    def _indicator_names(
        name: str,
        configurable: dict,
    ) -> list[str]:
        source = (
            name
            + " "
            + " ".join(
                configurable.keys()
            )
        ).lower()

        checks = (
            ("EMA", ("ema",)),
            ("VWAP", ("vwap",)),
            ("RSI", ("rsi",)),
            ("MACD", ("macd",)),
            ("ATR", ("atr",)),
            ("ADX", ("adx",)),
            ("Bollinger Bands", ("bollinger",)),
            ("Keltner Channel", ("keltner",)),
            ("Ichimoku", ("ichimoku",)),
            ("Stochastic", ("stochastic",)),
            ("CCI", ("cci",)),
            ("Williams %R", ("williams",)),
            ("ROC", ("roc",)),
            ("Supertrend", ("supertrend",)),
            ("Parabolic SAR", ("parabolic", "sar")),
            ("Volume", ("volume",)),
            ("Price Structure", ("breakout", "channel", "pivot", "range")),
        )

        output: list[str] = []

        for label, tokens in checks:
            if any(
                token in source
                for token in tokens
            ):
                output.append(label)

        return output[:8]

    @staticmethod
    def _summary_for(
        strategy: Strategy,
    ) -> str:
        raw = (
            strategy.__class__.__doc__
            or ""
        )

        lines = [
            line.strip()
            for line in raw.splitlines()
            if line.strip()
        ]

        if not lines:
            return (
                f"{strategy.name} systematic "
                "PhoenixTrend strategy."
            )

        return " ".join(
            lines[:2]
        )

    def describe(
        self,
        name: str,
    ) -> dict:

        canonical = (
            self.resolve_name(
                name
            )
        )

        strategy = (
            self.create(
                canonical
            )
        )

        configurable = {}
        for key in dir(strategy):
            if key.startswith("_") or key in {"name"}:
                continue
            value = getattr(strategy, key)
            if isinstance(value, (bool, int, float, str)):
                configurable[key] = value

        return {
            "name": canonical,
            "class": strategy.__class__.__name__,
            "module": strategy.__class__.__module__,
            "summary": self._summary_for(
                strategy
            ),
            "category": self._category_for(
                canonical
            ),
            "timeframe": self._timeframe_for(
                canonical
            ),
            "markets": [
                "Broker-supported assets"
            ],
            "indicators": self._indicator_names(
                canonical,
                configurable,
            ),
            "risk_model": "Shared RiskEngine",
            "editing_supported": bool(configurable),
            "configuration_editable": bool(configurable),
            "default_configuration": configurable,
        }


    def catalog(
        self,
    ) -> list[dict]:

        return [
            self.describe(
                name
            )
            for name in (
                self.list_strategies()
            )
        ]