from __future__ import annotations

from dataclasses import dataclass

from .base import Context, Strategy
from ..domain import Side, Signal


@dataclass(frozen=True)
class ScoreCard:
    bullish: float
    bearish: float
    bullish_reasons: tuple[str, ...] = ()
    bearish_reasons: tuple[str, ...] = ()


class ConfigurableStrategy(Strategy):
    """Common scoring discipline for indicator-driven strategies.

    Subclasses calculate independent bullish and bearish evidence. This base
    class applies confidence thresholds, directional separation and consistent
    Signal construction. It never downloads data or places orders.
    """

    minimum_score = 0.62
    directional_edge = 0.08

    @staticmethod
    def clamp(value: float) -> float:
        return max(0.0, min(float(value), 1.0))

    @staticmethod
    def add(score: float, condition: bool, weight: float) -> float:
        return score + weight if condition else score

    def evaluate(self, ctx: Context) -> ScoreCard:
        raise NotImplementedError

    def score(self, ctx: Context) -> float:
        card = self.evaluate(ctx)
        return self.clamp(max(card.bullish, card.bearish))

    def signal(self, ctx: Context) -> Signal | None:
        card = self.evaluate(ctx)
        bullish = self.clamp(card.bullish)
        bearish = self.clamp(card.bearish)

        if bullish >= self.minimum_score and bullish - bearish >= self.directional_edge:
            return Signal(
                symbol=ctx.symbol,
                side=Side.BUY,
                strategy=self.name,
                confidence=round(bullish, 4),
                rationale=list(card.bullish_reasons) or [f"{self.name} bullish setup confirmed"],
            )

        if bearish >= self.minimum_score and bearish - bullish >= self.directional_edge:
            return Signal(
                symbol=ctx.symbol,
                side=Side.SELL,
                strategy=self.name,
                confidence=round(bearish, 4),
                rationale=list(card.bearish_reasons) or [f"{self.name} bearish setup confirmed"],
            )

        return None
