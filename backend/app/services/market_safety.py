from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..config import settings


class MarketSafetyService:
    """
    PhoenixTrend market-data safety gate.

    This service validates whether a market snapshot is safe
    enough to be used for unattended automatic execution.

    It does NOT:
        - generate trade signals
        - perform account risk checks
        - submit orders
        - approve unsupported providers

    Market Safety answers one question:

        "Can this market snapshot be trusted for automatic
         execution right now?"
    """

    REQUIRED_FIELDS = (
        "symbol",
        "price",
        "ema20",
        "ema50",
        "vwap",
        "rsi",
        "volume_ratio",
        "day_high",
        "day_low",
        "as_of",
        "source",
    )


    # ========================================================
    # VALIDATE
    # ========================================================

    def validate(
        self,
        market_data: dict[str, Any],
        require_provider_approval: bool | None = None,
    ) -> dict[str, Any]:

        reasons: list[str] = []
        warnings: list[str] = []

        if require_provider_approval is None:
            require_provider_approval = (
                settings.market_data_require_provider_approval
            )

        # ----------------------------------------------------
        # REQUIRED FIELDS
        # ----------------------------------------------------

        for key in self.REQUIRED_FIELDS:

            if market_data.get(key) is None:
                reasons.append(
                    f"Missing {key}"
                )

        # ----------------------------------------------------
        # BASIC NUMERIC VALIDATION
        # ----------------------------------------------------

        price = self._float(
            market_data.get("price")
        )

        ema20 = self._float(
            market_data.get("ema20")
        )

        ema50 = self._float(
            market_data.get("ema50")
        )

        vwap = self._float(
            market_data.get("vwap")
        )

        rsi = self._float(
            market_data.get("rsi"),
            default=None,
        )

        volume_ratio = self._float(
            market_data.get("volume_ratio"),
            default=None,
        )

        day_high = self._float(
            market_data.get("day_high")
        )

        day_low = self._float(
            market_data.get("day_low")
        )


        if price is not None and price <= 0:
            reasons.append(
                "Invalid market price"
            )

        if ema20 is not None and ema20 <= 0:
            reasons.append(
                "Invalid EMA20"
            )

        if ema50 is not None and ema50 <= 0:
            reasons.append(
                "Invalid EMA50"
            )

        if vwap is not None and vwap <= 0:
            reasons.append(
                "Invalid VWAP"
            )

        if (
            rsi is not None
            and not 0 <= rsi <= 100
        ):
            reasons.append(
                "RSI is outside valid range"
            )

        if (
            volume_ratio is not None
            and volume_ratio < 0
        ):
            reasons.append(
                "Invalid volume ratio"
            )

        if (
            day_high is not None
            and day_low is not None
            and day_high < day_low
        ):
            reasons.append(
                "Day high is below day low"
            )

        # ----------------------------------------------------
        # SIMULATED DATA
        # ----------------------------------------------------

        if bool(
            market_data.get(
                "simulated",
                False,
            )
        ):
            reasons.append(
                "Simulated market data cannot drive automatic execution"
            )

        # ----------------------------------------------------
        # PROVIDER HEALTH
        # ----------------------------------------------------

        if (
            market_data.get(
                "provider_healthy"
            )
            is False
        ):
            reasons.append(
                "Market provider reports unhealthy"
            )

        # ----------------------------------------------------
        # PROVIDER APPROVAL
        # ----------------------------------------------------

        if (
            require_provider_approval
            and market_data.get(
                "automatic_execution_safe"
            )
            is not True
        ):
            reasons.append(
                "Market provider is not approved for unattended execution"
            )

        # ----------------------------------------------------
        # FRESHNESS
        # ----------------------------------------------------

        as_of = market_data.get(
            "as_of"
        )

        age_seconds = None


        if as_of:

            parsed = self._parse_datetime(
                as_of
            )


            if parsed is None:

                reasons.append(
                    "Invalid market-data timestamp"
                )

            else:

                now = datetime.now(
                    timezone.utc
                )


                age_seconds = (
                    now - parsed
                ).total_seconds()


                if age_seconds < -5:

                    reasons.append(
                        "Market-data timestamp is in the future"
                    )


                elif (
                    age_seconds
                    > settings.market_data_max_age_seconds
                ):

                    reasons.append(
                        (
                            "Market data is stale "
                            f"({age_seconds:.1f}s old)"
                        )
                    )

        else:

            reasons.append(
                "Missing market-data timestamp"
            )

        # ----------------------------------------------------
        # SOURCE COUNT
        # ----------------------------------------------------

        try:

            source_count = int(
                market_data.get(
                    "source_count",
                    1,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            source_count = 1


        if source_count < 2:

            warnings.append(
                "Only one market-data source is present"
            )

        # ----------------------------------------------------
        # SOURCE NAME
        # ----------------------------------------------------

        source = str(
            market_data.get(
                "source",
                "",
            )
        ).strip()


        if not source:

            reasons.append(
                "Missing market-data source"
            )

        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        safe = (
            len(reasons) == 0
        )


        return {
            "safe": safe,

            "state": (
                "SAFE"
                if safe
                else "BLOCKED"
            ),

            "reasons": (
                reasons
            ),

            "warnings": (
                warnings
            ),

            "source": (
                source or None
            ),

            "source_count": (
                source_count
            ),

            "age_seconds": (
                round(
                    age_seconds,
                    3,
                )
                if age_seconds
                is not None
                else None
            ),

            "provider_approved": (
                market_data.get(
                    "automatic_execution_safe"
                )
                is True
            ),

            "provider_healthy": (
                market_data.get(
                    "provider_healthy"
                )
                is not False
            ),

            "simulated": bool(
                market_data.get(
                    "simulated",
                    False,
                )
            ),

            "checked_at": (
                datetime.now(
                    timezone.utc
                )
                .isoformat()
            ),
        }


    # ========================================================
    # HELPERS
    # ========================================================

    @staticmethod
    def _float(
        value: Any,
        default: float | None = 0.0,
    ) -> float | None:

        if value is None:
            return default

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return default


    @staticmethod
    def _parse_datetime(
        value: Any,
    ) -> datetime | None:

        if isinstance(
            value,
            datetime,
        ):

            dt = value

        else:

            try:

                text = str(
                    value
                ).strip()


                if text.endswith("Z"):
                    text = (
                        text[:-1]
                        + "+00:00"
                    )


                dt = (
                    datetime.fromisoformat(
                        text
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                return None


        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=timezone.utc
            )


        return dt.astimezone(
            timezone.utc
        )


    # ========================================================
    # STATUS
    # ========================================================

    def status(
        self,
    ) -> dict[str, Any]:

        return {
            "required": True,

            "unattended_execution_requires_provider_approval": (
                settings.market_data_require_provider_approval
            ),

            "max_market_data_age_seconds": (
                settings.market_data_max_age_seconds
            ),

            "simulated_data_allowed_for_automatic_execution": (
                False
            ),
        }


market_safety_service = (
    MarketSafetyService()
)