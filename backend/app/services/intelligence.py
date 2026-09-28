from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .chart_patterns import chart_pattern_service
from .market import market_service
from .news import news_service


class IntelligenceService:
    """
    PhoenixTrend market-intelligence aggregation service.

    Combines available intelligence sources into one
    normalized snapshot.

    Current sources:

        Technical market data
        Chart patterns
        Financial news

    Future sources:

        Social sentiment
        SEC insider transactions
        Institutional / 13F activity

    IntelligenceService does NOT:

        - generate final BUY/SELL decisions
        - select the final strategy
        - create TradeIntent objects
        - bypass Market Safety
        - bypass Risk
        - execute orders
    """

    # ========================================================
    # SNAPSHOT
    # ========================================================

    def snapshot(
        self,
        symbol: str,
        news_limit: int = 10,
    ) -> dict[str, Any]:

        normalized_symbol = (
            str(symbol)
            .strip()
            .upper()
        )

        if not normalized_symbol:

            raise ValueError(
                "Symbol is required"
            )


        # ----------------------------------------------------
        # MARKET / TECHNICAL
        # ----------------------------------------------------

        market = market_service.context(
            normalized_symbol
        )


        bars = (
            market.get("bars")
            or []
        )


        technical = {
            key: value
            for key, value
            in market.items()
            if key != "bars"
        }


        # ----------------------------------------------------
        # CHART PATTERNS
        # ----------------------------------------------------

        if bars:

            patterns = (
                chart_pattern_service.analyze(
                    bars
                )
            )

        else:

            patterns = []


        # ----------------------------------------------------
        # NEWS
        # ----------------------------------------------------

        news = news_service.for_symbol(
            normalized_symbol,
            news_limit,
        )


        # ----------------------------------------------------
        # PROVIDER AVAILABILITY
        # ----------------------------------------------------

        providers = {
            "technical": {
                "available": True,
                "source": market.get(
                    "source"
                ),
                "simulated": bool(
                    market.get(
                        "simulated",
                        False,
                    )
                ),
            },

            "patterns": {
                "available": bool(
                    bars
                ),
                "source": (
                    "phoenixtrend-local"
                ),
            },

            "news": {
                "available": bool(
                    news
                ),
                "source": (
                    "yahoo-finance"
                ),
            },

            "social": {
                "available": False,
                "reason": (
                    "No social provider configured"
                ),
            },

            "insider": {
                "available": False,
                "reason": (
                    "No SEC insider adapter configured"
                ),
            },

            "institutional": {
                "available": False,
                "reason": (
                    "No institutional/13F adapter configured"
                ),
            },
        }


        # ----------------------------------------------------
        # EXECUTION SAFETY
        # ----------------------------------------------------

        # Intelligence itself never upgrades market data into
        # execution-grade data.
        #
        # The underlying market provider must explicitly
        # approve automatic execution.

        automatic_execution_safe = bool(
            market.get(
                "automatic_execution_safe",
                False,
            )
        )


        return {
            "symbol": (
                normalized_symbol
            ),

            "technical": (
                technical
            ),

            "patterns": (
                patterns
            ),

            "news": (
                news
            ),

            "social": (
                providers[
                    "social"
                ]
            ),

            "insider": (
                providers[
                    "insider"
                ]
            ),

            "institutional": (
                providers[
                    "institutional"
                ]
            ),

            "providers": (
                providers
            ),

            "automatic_execution_safe": (
                automatic_execution_safe
            ),

            "generated_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }


    # ========================================================
    # STATUS
    # ========================================================

    def status(
        self,
    ) -> dict[str, Any]:

        market_status = (
            market_service.status()
        )

        news_status = (
            news_service.status()
        )


        return {
            "technical": {
                "available": True,
                "provider": (
                    market_status.get(
                        "provider"
                    )
                ),
            },

            "patterns": {
                "available": True,
                "provider": (
                    "phoenixtrend-local"
                ),
            },

            "news": {
                "available": True,
                "provider": (
                    news_status.get(
                        "provider"
                    )
                ),
            },

            "social": {
                "available": False,
            },

            "insider": {
                "available": False,
            },

            "institutional": {
                "available": False,
            },

            "automatic_execution_safe": (
                bool(
                    market_status.get(
                        "automatic_execution_safe",
                        False,
                    )
                )
            ),
        }


intelligence_service = IntelligenceService()