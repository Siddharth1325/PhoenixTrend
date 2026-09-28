from __future__ import annotations

from datetime import date, datetime, timezone
from math import isfinite
from typing import Any, Mapping, Sequence

from .options_chain import options_chain_service


class OptionsScanner:
    """
    PhoenixTrend options opportunity scanner.

    The scanner operates only on real contracts returned by
    OptionsChainService. It never synthesizes strikes, expirations, quotes,
    volume, open interest, implied volatility, Greeks, spreads, or contract
    symbols.

    Responsibilities:
        - retrieve a broker-backed options chain
        - validate and normalize scanner filters
        - calculate derived metrics only when their required source fields exist
        - calculate DTE from a provider-supplied expiration
        - calculate midpoint/spread from provider-supplied bid/ask
        - filter contracts by liquidity, spread, expiration and strike
        - preserve the normalized OptionsChainService contract
        - rank candidates deterministically from observed data
        - keep missing data as None instead of fabricating defaults

    This scanner does not authorize or execute trades.
    """

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 500

    def scan(
        self,
        underlying: str,
        *,
        min_open_interest: float | None = None,
        max_spread_percent: float | None = None,
        option_type: str | None = None,
        min_volume: float | None = None,
        min_dte: int | None = None,
        max_dte: int | None = None,
        expiration: str | date | datetime | None = None,
        min_strike: float | None = None,
        max_strike: float | None = None,
        min_implied_volatility: float | None = None,
        max_implied_volatility: float | None = None,
        tradable_only: bool = False,
        require_quote: bool = False,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        symbol = self._normalize_underlying(
            underlying
        )

        filters = self._validate_filters(
            min_open_interest=min_open_interest,
            max_spread_percent=max_spread_percent,
            option_type=option_type,
            min_volume=min_volume,
            min_dte=min_dte,
            max_dte=max_dte,
            expiration=expiration,
            min_strike=min_strike,
            max_strike=max_strike,
            min_implied_volatility=min_implied_volatility,
            max_implied_volatility=max_implied_volatility,
            tradable_only=tradable_only,
            require_quote=require_quote,
            limit=limit,
        )

        chain_filters: dict[str, Any] = {}

        if filters["option_type"] is not None:
            chain_filters["option_type"] = filters[
                "option_type"
            ]

        if filters["expiration"] is not None:
            chain_filters["expiration"] = filters[
                "expiration"
            ]

        if filters["min_strike"] is not None:
            chain_filters["min_strike"] = filters[
                "min_strike"
            ]

        if filters["max_strike"] is not None:
            chain_filters["max_strike"] = filters[
                "max_strike"
            ]

        if filters["min_open_interest"] is not None:
            chain_filters["min_open_interest"] = filters[
                "min_open_interest"
            ]

        if filters["min_volume"] is not None:
            chain_filters["min_volume"] = filters[
                "min_volume"
            ]

        if filters["max_spread_percent"] is not None:
            chain_filters["max_spread_percent"] = filters[
                "max_spread_percent"
            ]

        if filters["tradable_only"]:
            chain_filters["tradable"] = True

        chain = options_chain_service.chain(
            symbol,
            **chain_filters,
        )

        if not isinstance(
            chain,
            Mapping,
        ):
            raise RuntimeError(
                "OptionsChainService returned an invalid payload"
            )

        chain_result = dict(
            chain
        )

        if not bool(
            chain_result.get(
                "available"
            )
        ):
            return {
                **chain_result,
                "scanner_available": False,
                "scanned_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "filters": self._response_filters(
                    filters
                ),
                "source_contract_count": 0,
                "candidate_count": 0,
                "candidates": [],
            }

        raw_contracts = chain_result.get(
            "contracts"
        )

        if raw_contracts is None:
            raw_contracts = []

        if not isinstance(
            raw_contracts,
            Sequence,
        ) or isinstance(
            raw_contracts,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            raise RuntimeError(
                "OptionsChainService contracts payload is invalid"
            )

        today = datetime.now(
            timezone.utc
        ).date()

        candidates: list[dict[str, Any]] = []

        rejected_invalid = 0
        rejected_filters = 0

        for raw in raw_contracts:
            if not isinstance(
                raw,
                Mapping,
            ):
                rejected_invalid += 1
                continue

            candidate = self._candidate(
                symbol,
                raw,
                today=today,
            )

            if candidate is None:
                rejected_invalid += 1
                continue

            if not self._matches(
                candidate,
                filters,
            ):
                rejected_filters += 1
                continue

            candidate[
                "scanner_score"
            ] = self._scanner_score(
                candidate
            )

            candidates.append(
                candidate
            )

        candidates.sort(
            key=self._candidate_sort_key
        )

        safe_limit = filters[
            "limit"
        ]

        if len(candidates) > safe_limit:
            candidates = candidates[
                :safe_limit
            ]

        actionable_quote_count = sum(
            1
            for candidate in candidates
            if candidate.get(
                "bid"
            )
            is not None
            and candidate.get(
                "ask"
            )
            is not None
        )

        tradable_count = sum(
            1
            for candidate in candidates
            if candidate.get(
                "tradable"
            )
            is True
        )

        return {
            **chain_result,
            "scanner_available": True,
            "scanned_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "filters": self._response_filters(
                filters
            ),
            "source_contract_count": len(
                raw_contracts
            ),
            "rejected_invalid_count": rejected_invalid,
            "rejected_filter_count": rejected_filters,
            "candidate_count": len(
                candidates
            ),
            "quoted_candidate_count": actionable_quote_count,
            "tradable_candidate_count": tradable_count,
            "candidates": candidates,
        }

    def _candidate(
        self,
        underlying: str,
        raw: Mapping[str, Any],
        *,
        today: date,
    ) -> dict[str, Any] | None:
        item = dict(
            raw
        )

        contract_symbol = self._text(
            item.get(
                "symbol"
            )
        )

        provider_underlying = self._text(
            item.get(
                "underlying"
            )
        )

        normalized_underlying = (
            provider_underlying.upper()
            if provider_underlying
            else underlying
        )

        raw_option_type = (
            item.get(
                "option_type"
            )
            if item.get(
                "option_type"
            )
            is not None
            else item.get(
                "type"
            )
        )

        option_type = self._normalize_option_type(
            raw_option_type
        )

        strike = self._first_number(
            item,
            "strike",
            "strike_price",
        )

        expiration = self._normalize_expiration(
            item.get(
                "expiration"
            )
            or item.get(
                "expiration_date"
            )
            or item.get(
                "expiry"
            )
            or item.get(
                "expiry_date"
            )
        )

        days_to_expiration: int | None = None

        if expiration is not None:
            try:
                expiration_date = date.fromisoformat(
                    expiration
                )

                days_to_expiration = (
                    expiration_date
                    - today
                ).days

            except ValueError:
                days_to_expiration = None

        bid = self._first_number(
            item,
            "bid",
            "bid_price",
        )

        ask = self._first_number(
            item,
            "ask",
            "ask_price",
        )

        last = self._first_number(
            item,
            "last",
            "last_price",
            "price",
        )

        midpoint = self._first_number(
            item,
            "midpoint",
            "mid",
        )

        spread = self._first_number(
            item,
            "spread",
        )

        spread_percent = self._first_number(
            item,
            "spread_percent",
            "spread_pct",
        )

        if (
            bid is not None
            and ask is not None
            and bid >= 0
            and ask >= bid
        ):
            calculated_midpoint = (
                bid
                + ask
            ) / 2.0

            calculated_spread = (
                ask
                - bid
            )

            midpoint = calculated_midpoint
            spread = calculated_spread

            if calculated_midpoint > 0:
                spread_percent = (
                    calculated_spread
                    / calculated_midpoint
                ) * 100.0
            else:
                spread_percent = None

        volume = self._first_number(
            item,
            "volume",
            "day_volume",
        )

        open_interest = self._first_number(
            item,
            "open_interest",
            "oi",
        )

        implied_volatility = self._first_number(
            item,
            "implied_volatility",
            "iv",
        )

        tradable = self._bool(
            item.get(
                "tradable"
            )
        )

        status = self._text(
            item.get(
                "status"
            )
        )

        multiplier = self._first_number(
            item,
            "multiplier",
            "contract_multiplier",
        )

        delta = self._first_number(
            item,
            "delta",
        )

        gamma = self._first_number(
            item,
            "gamma",
        )

        theta = self._first_number(
            item,
            "theta",
        )

        vega = self._first_number(
            item,
            "vega",
        )

        rho = self._first_number(
            item,
            "rho",
        )

        quote_timestamp = self._text(
            item.get(
                "quote_timestamp"
            )
            or item.get(
                "as_of"
            )
            or item.get(
                "timestamp"
            )
        )

        candidate = dict(
            item
        )

        candidate.update(
            {
                "symbol": (
                    contract_symbol.upper()
                    if contract_symbol
                    else None
                ),
                "underlying": normalized_underlying,
                "option_type": option_type,
                "strike": strike,
                "expiration": expiration,
                "days_to_expiration": days_to_expiration,
                "bid": bid,
                "ask": ask,
                "last": last,
                "midpoint": midpoint,
                "spread": spread,
                "spread_percent": spread_percent,
                "volume": volume,
                "open_interest": open_interest,
                "implied_volatility": implied_volatility,
                "tradable": tradable,
                "status": status,
                "multiplier": multiplier,
                "delta": delta,
                "gamma": gamma,
                "theta": theta,
                "vega": vega,
                "rho": rho,
                "quote_timestamp": quote_timestamp,
            }
        )

        return candidate

    def _matches(
        self,
        candidate: Mapping[str, Any],
        filters: Mapping[str, Any],
    ) -> bool:
        requested_type = filters.get(
            "option_type"
        )

        if requested_type is not None:
            actual_type = candidate.get(
                "option_type"
            )

            if actual_type is None:
                return False

            if actual_type != requested_type:
                return False

        requested_expiration = filters.get(
            "expiration"
        )

        if requested_expiration is not None:
            actual_expiration = candidate.get(
                "expiration"
            )

            if actual_expiration is None:
                return False

            if actual_expiration != requested_expiration:
                return False

        min_open_interest = filters.get(
            "min_open_interest"
        )

        if min_open_interest is not None:
            open_interest = self._number(
                candidate.get(
                    "open_interest"
                )
            )

            if open_interest is None:
                return False

            if open_interest < min_open_interest:
                return False

        min_volume = filters.get(
            "min_volume"
        )

        if min_volume is not None:
            volume = self._number(
                candidate.get(
                    "volume"
                )
            )

            if volume is None:
                return False

            if volume < min_volume:
                return False

        max_spread_percent = filters.get(
            "max_spread_percent"
        )

        if max_spread_percent is not None:
            spread_percent = self._number(
                candidate.get(
                    "spread_percent"
                )
            )

            if spread_percent is None:
                return False

            if (
                spread_percent
                > max_spread_percent
            ):
                return False

        min_dte = filters.get(
            "min_dte"
        )

        if min_dte is not None:
            dte = candidate.get(
                "days_to_expiration"
            )

            if not isinstance(
                dte,
                int,
            ):
                return False

            if dte < min_dte:
                return False

        max_dte = filters.get(
            "max_dte"
        )

        if max_dte is not None:
            dte = candidate.get(
                "days_to_expiration"
            )

            if not isinstance(
                dte,
                int,
            ):
                return False

            if dte > max_dte:
                return False

        strike = self._number(
            candidate.get(
                "strike"
            )
        )

        min_strike = filters.get(
            "min_strike"
        )

        if min_strike is not None:
            if strike is None:
                return False

            if strike < min_strike:
                return False

        max_strike = filters.get(
            "max_strike"
        )

        if max_strike is not None:
            if strike is None:
                return False

            if strike > max_strike:
                return False

        implied_volatility = self._number(
            candidate.get(
                "implied_volatility"
            )
        )

        min_iv = filters.get(
            "min_implied_volatility"
        )

        if min_iv is not None:
            if implied_volatility is None:
                return False

            if implied_volatility < min_iv:
                return False

        max_iv = filters.get(
            "max_implied_volatility"
        )

        if max_iv is not None:
            if implied_volatility is None:
                return False

            if implied_volatility > max_iv:
                return False

        if filters.get(
            "tradable_only"
        ):
            if candidate.get(
                "tradable"
            ) is not True:
                return False

        if filters.get(
            "require_quote"
        ):
            bid = self._number(
                candidate.get(
                    "bid"
                )
            )

            ask = self._number(
                candidate.get(
                    "ask"
                )
            )

            if (
                bid is None
                or ask is None
                or bid < 0
                or ask < bid
            ):
                return False

        return True

    def _scanner_score(
        self,
        candidate: Mapping[str, Any],
    ) -> float | None:
        """
        Rank only from observed liquidity/execution-quality fields.

        The score is not a trade signal and does not predict profitability.
        Missing fields do not receive fabricated neutral values.
        """

        components: list[
            tuple[float, float]
        ] = []

        open_interest = self._number(
            candidate.get(
                "open_interest"
            )
        )

        if (
            open_interest is not None
            and open_interest >= 0
        ):
            oi_score = min(
                1.0,
                self._log_scale(
                    open_interest,
                    reference=10_000.0,
                ),
            )

            components.append(
                (
                    oi_score,
                    0.35,
                )
            )

        volume = self._number(
            candidate.get(
                "volume"
            )
        )

        if (
            volume is not None
            and volume >= 0
        ):
            volume_score = min(
                1.0,
                self._log_scale(
                    volume,
                    reference=5_000.0,
                ),
            )

            components.append(
                (
                    volume_score,
                    0.30,
                )
            )

        spread_percent = self._number(
            candidate.get(
                "spread_percent"
            )
        )

        if (
            spread_percent is not None
            and spread_percent >= 0
        ):
            spread_score = max(
                0.0,
                min(
                    1.0,
                    1.0
                    - (
                        spread_percent
                        / 20.0
                    ),
                ),
            )

            components.append(
                (
                    spread_score,
                    0.25,
                )
            )

        if isinstance(
            candidate.get(
                "tradable"
            ),
            bool,
        ):
            components.append(
                (
                    1.0
                    if candidate.get(
                        "tradable"
                    )
                    else 0.0,
                    0.10,
                )
            )

        if not components:
            return None

        total_weight = sum(
            weight
            for _, weight in components
        )

        if total_weight <= 0:
            return None

        score = sum(
            value * weight
            for value, weight in components
        ) / total_weight

        return round(
            score,
            6,
        )

    @staticmethod
    def _candidate_sort_key(
        candidate: Mapping[str, Any],
    ) -> tuple[Any, ...]:
        score = OptionsScanner._number(
            candidate.get(
                "scanner_score"
            )
        )

        open_interest = OptionsScanner._number(
            candidate.get(
                "open_interest"
            )
        )

        volume = OptionsScanner._number(
            candidate.get(
                "volume"
            )
        )

        spread = OptionsScanner._number(
            candidate.get(
                "spread_percent"
            )
        )

        expiration = str(
            candidate.get(
                "expiration"
            )
            or "9999-12-31"
        )

        strike = OptionsScanner._number(
            candidate.get(
                "strike"
            )
        )

        symbol = str(
            candidate.get(
                "symbol"
            )
            or ""
        )

        return (
            (
                -score
                if score is not None
                else float("inf")
            ),
            (
                -open_interest
                if open_interest is not None
                else float("inf")
            ),
            (
                -volume
                if volume is not None
                else float("inf")
            ),
            (
                spread
                if spread is not None
                else float("inf")
            ),
            expiration,
            (
                strike
                if strike is not None
                else float("inf")
            ),
            symbol,
        )

    def _validate_filters(
        self,
        *,
        min_open_interest: float | None,
        max_spread_percent: float | None,
        option_type: str | None,
        min_volume: float | None,
        min_dte: int | None,
        max_dte: int | None,
        expiration: str | date | datetime | None,
        min_strike: float | None,
        max_strike: float | None,
        min_implied_volatility: float | None,
        max_implied_volatility: float | None,
        tradable_only: bool,
        require_quote: bool,
        limit: int,
    ) -> dict[str, Any]:
        normalized_type = self._normalize_option_type(
            option_type
        )

        if (
            option_type is not None
            and normalized_type is None
        ):
            raise ValueError(
                "option_type must be call or put"
            )

        normalized_min_oi = self._optional_nonnegative(
            min_open_interest,
            "min_open_interest",
        )

        normalized_spread = self._optional_nonnegative(
            max_spread_percent,
            "max_spread_percent",
        )

        normalized_volume = self._optional_nonnegative(
            min_volume,
            "min_volume",
        )

        normalized_min_strike = self._optional_nonnegative(
            min_strike,
            "min_strike",
        )

        normalized_max_strike = self._optional_nonnegative(
            max_strike,
            "max_strike",
        )

        if (
            normalized_min_strike is not None
            and normalized_max_strike is not None
            and normalized_min_strike
            > normalized_max_strike
        ):
            raise ValueError(
                "min_strike cannot exceed max_strike"
            )

        normalized_min_iv = self._optional_nonnegative(
            min_implied_volatility,
            "min_implied_volatility",
        )

        normalized_max_iv = self._optional_nonnegative(
            max_implied_volatility,
            "max_implied_volatility",
        )

        if (
            normalized_min_iv is not None
            and normalized_max_iv is not None
            and normalized_min_iv
            > normalized_max_iv
        ):
            raise ValueError(
                "min_implied_volatility cannot exceed "
                "max_implied_volatility"
            )

        normalized_min_dte = self._optional_integer(
            min_dte,
            "min_dte",
        )

        normalized_max_dte = self._optional_integer(
            max_dte,
            "max_dte",
        )

        if (
            normalized_min_dte is not None
            and normalized_min_dte < 0
        ):
            raise ValueError(
                "min_dte cannot be negative"
            )

        if (
            normalized_max_dte is not None
            and normalized_max_dte < 0
        ):
            raise ValueError(
                "max_dte cannot be negative"
            )

        if (
            normalized_min_dte is not None
            and normalized_max_dte is not None
            and normalized_min_dte
            > normalized_max_dte
        ):
            raise ValueError(
                "min_dte cannot exceed max_dte"
            )

        normalized_expiration = self._normalize_expiration(
            expiration
        )

        if (
            expiration is not None
            and normalized_expiration is None
        ):
            raise ValueError(
                "Invalid expiration"
            )

        try:
            normalized_limit = int(
                limit
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ValueError(
                "limit must be an integer"
            ) from exc

        if normalized_limit <= 0:
            raise ValueError(
                "limit must be greater than zero"
            )

        normalized_limit = min(
            normalized_limit,
            self.MAX_LIMIT,
        )

        return {
            "min_open_interest": normalized_min_oi,
            "max_spread_percent": normalized_spread,
            "option_type": normalized_type,
            "min_volume": normalized_volume,
            "min_dte": normalized_min_dte,
            "max_dte": normalized_max_dte,
            "expiration": normalized_expiration,
            "min_strike": normalized_min_strike,
            "max_strike": normalized_max_strike,
            "min_implied_volatility": normalized_min_iv,
            "max_implied_volatility": normalized_max_iv,
            "tradable_only": bool(
                tradable_only
            ),
            "require_quote": bool(
                require_quote
            ),
            "limit": normalized_limit,
        }

    @staticmethod
    def _response_filters(
        filters: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            key: value
            for key, value in filters.items()
            if value is not None
        }

    @staticmethod
    def _normalize_underlying(
        value: Any,
    ) -> str:
        symbol = str(
            value
            or ""
        ).strip().upper()

        if not symbol:
            raise ValueError(
                "Underlying symbol is required"
            )

        if len(symbol) > 64:
            raise ValueError(
                "Underlying symbol is invalid"
            )

        allowed = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789"
            ".-/_:"
        )

        if any(
            character not in allowed
            for character in symbol
        ):
            raise ValueError(
                "Underlying symbol is invalid"
            )

        return symbol

    @staticmethod
    def _normalize_option_type(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(
            value
        ).strip().lower()

        if normalized in {
            "call",
            "calls",
            "c",
        }:
            return "call"

        if normalized in {
            "put",
            "puts",
            "p",
        }:
            return "put"

        return None

    @staticmethod
    def _normalize_expiration(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(
            value,
            datetime,
        ):
            return value.date().isoformat()

        if isinstance(
            value,
            date,
        ):
            return value.isoformat()

        text = str(
            value
        ).strip()

        if not text:
            return None

        candidate = text

        if candidate.endswith(
            "Z"
        ):
            candidate = (
                candidate[:-1]
                + "+00:00"
            )

        try:
            return datetime.fromisoformat(
                candidate
            ).date().isoformat()

        except ValueError:
            pass

        try:
            return date.fromisoformat(
                text[:10]
            ).isoformat()

        except ValueError:
            return None

    @staticmethod
    def _optional_nonnegative(
        value: Any,
        field: str,
    ) -> float | None:
        if value is None:
            return None

        number = OptionsScanner._number(
            value
        )

        if number is None:
            raise ValueError(
                f"{field} must be numeric"
            )

        if number < 0:
            raise ValueError(
                f"{field} cannot be negative"
            )

        return number

    @staticmethod
    def _optional_integer(
        value: Any,
        field: str,
    ) -> int | None:
        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                f"{field} must be an integer"
            )

        try:
            integer = int(
                value
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ValueError(
                f"{field} must be an integer"
            ) from exc

        if isinstance(
            value,
            float,
        ) and not value.is_integer():
            raise ValueError(
                f"{field} must be an integer"
            )

        return integer

    @staticmethod
    def _first_number(
        item: Mapping[str, Any],
        *keys: str,
    ) -> float | None:
        for key in keys:
            if key not in item:
                continue

            number = OptionsScanner._number(
                item.get(
                    key
                )
            )

            if number is not None:
                return number

        return None

    @staticmethod
    def _number(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return None

        try:
            number = float(
                value
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if not isfinite(
            number
        ):
            return None

        return number

    @staticmethod
    def _bool(
        value: Any,
    ) -> bool | None:
        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            int,
        ) and value in {
            0,
            1,
        }:
            return bool(
                value
            )

        if isinstance(
            value,
            str,
        ):
            normalized = (
                value
                .strip()
                .lower()
            )

            if normalized in {
                "true",
                "1",
                "yes",
                "y",
            }:
                return True

            if normalized in {
                "false",
                "0",
                "no",
                "n",
            }:
                return False

        return None

    @staticmethod
    def _text(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        text = str(
            value
        ).strip()

        return (
            text
            if text
            else None
        )

    @staticmethod
    def _log_scale(
        value: float,
        *,
        reference: float,
    ) -> float:
        if value <= 0:
            return 0.0

        if reference <= 1:
            return 1.0

        import math

        return max(
            0.0,
            min(
                1.0,
                math.log1p(
                    value
                )
                / math.log1p(
                    reference
                ),
            ),
        )


options_scanner = OptionsScanner()


__all__ = [
    "OptionsScanner",
    "options_scanner",
]