from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log1p
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class OptionSelection:
    symbol: str | None
    rank: int
    selection_score: float | None
    selection_reasons: tuple[str, ...]
    contract: dict[str, Any]

    def dump(self) -> dict[str, Any]:
        return {
            **self.contract,
            "selection_score": self.selection_score,
            "selection_reasons": list(self.selection_reasons),
            "rank": self.rank,
        }


class OptionsSelector:
    """
    PhoenixTrend options-contract selector.

    This service ranks only contracts already returned by the real options
    chain/scanner pipeline.

    It does not:
        - create contracts
        - invent strikes or expirations
        - invent liquidity
        - invent Greeks
        - invent implied volatility
        - assume a missing quote is zero
        - assume a missing spread is acceptable
        - assume a missing tradability flag is True
        - convert missing metrics into neutral scores
        - authorize or execute an options trade

    Selection is based only on observed contract data.

    The selector intentionally separates:
        1. eligibility
        2. direction compatibility
        3. liquidity/execution quality
        4. optional strategy-specific preferences
        5. deterministic ranking

    Final execution still belongs to PhoenixTrend's normal safety, risk,
    capability and execution pipeline.
    """

    CALL = "CALL"
    PUT = "PUT"

    BUY = "BUY"
    SELL = "SELL"

    DEFAULT_LIMIT = 10
    MAX_LIMIT = 250

    def select(
        self,
        contracts: list[dict[str, Any]],
        *,
        direction: str | None = None,
        limit: int = DEFAULT_LIMIT,
        require_tradable: bool = False,
        require_quote: bool = False,
        min_open_interest: float | None = None,
        min_volume: float | None = None,
        max_spread_percent: float | None = None,
        min_dte: int | None = None,
        max_dte: int | None = None,
        target_dte: int | None = None,
        min_delta: float | None = None,
        max_delta: float | None = None,
        target_abs_delta: float | None = None,
        min_implied_volatility: float | None = None,
        max_implied_volatility: float | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(contracts, list):
            raise TypeError("contracts must be a list")

        safe_limit = self._normalize_limit(limit)

        if safe_limit == 0:
            return []

        wanted_type = self._direction_to_option_type(
            direction
        )

        filters = self._validate_filters(
            min_open_interest=min_open_interest,
            min_volume=min_volume,
            max_spread_percent=max_spread_percent,
            min_dte=min_dte,
            max_dte=max_dte,
            target_dte=target_dte,
            min_delta=min_delta,
            max_delta=max_delta,
            target_abs_delta=target_abs_delta,
            min_implied_volatility=min_implied_volatility,
            max_implied_volatility=max_implied_volatility,
        )

        selections: list[
            tuple[
                float | None,
                dict[str, Any],
                list[str],
            ]
        ] = []

        for raw_contract in contracts:
            if not isinstance(raw_contract, Mapping):
                continue

            contract = self._normalize_contract(
                raw_contract
            )

            option_type = contract.get(
                "option_type"
            )

            if wanted_type is not None:
                if option_type is None:
                    continue

                if option_type != wanted_type:
                    continue

            if require_tradable:
                if contract.get("tradable") is not True:
                    continue

            if require_quote:
                bid = self._num(
                    contract.get("bid")
                )
                ask = self._num(
                    contract.get("ask")
                )

                if (
                    bid is None
                    or ask is None
                    or bid < 0
                    or ask < bid
                ):
                    continue

            if not self._matches_filters(
                contract,
                filters,
            ):
                continue

            score, reasons = self._score(
                contract,
                target_dte=filters["target_dte"],
                target_abs_delta=filters[
                    "target_abs_delta"
                ],
            )

            selections.append(
                (
                    score,
                    contract,
                    reasons,
                )
            )

        selections.sort(
            key=self._sort_key
        )

        output: list[dict[str, Any]] = []

        for rank, (
            score,
            contract,
            reasons,
        ) in enumerate(
            selections[:safe_limit],
            start=1,
        ):
            selection = OptionSelection(
                symbol=self._text(
                    contract.get("symbol")
                ),
                rank=rank,
                selection_score=(
                    round(score, 6)
                    if score is not None
                    else None
                ),
                selection_reasons=tuple(reasons),
                contract=contract,
            )

            output.append(
                selection.dump()
            )

        return output

    def select_one(
        self,
        contracts: list[dict[str, Any]],
        *,
        direction: str | None = None,
        require_tradable: bool = False,
        require_quote: bool = False,
        min_open_interest: float | None = None,
        min_volume: float | None = None,
        max_spread_percent: float | None = None,
        min_dte: int | None = None,
        max_dte: int | None = None,
        target_dte: int | None = None,
        min_delta: float | None = None,
        max_delta: float | None = None,
        target_abs_delta: float | None = None,
        min_implied_volatility: float | None = None,
        max_implied_volatility: float | None = None,
    ) -> dict[str, Any] | None:
        selected = self.select(
            contracts,
            direction=direction,
            limit=1,
            require_tradable=require_tradable,
            require_quote=require_quote,
            min_open_interest=min_open_interest,
            min_volume=min_volume,
            max_spread_percent=max_spread_percent,
            min_dte=min_dte,
            max_dte=max_dte,
            target_dte=target_dte,
            min_delta=min_delta,
            max_delta=max_delta,
            target_abs_delta=target_abs_delta,
            min_implied_volatility=min_implied_volatility,
            max_implied_volatility=max_implied_volatility,
        )

        return selected[0] if selected else None

    def rank(
        self,
        contracts: list[dict[str, Any]],
        *,
        direction: str | None = None,
        limit: int = DEFAULT_LIMIT,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        return self.select(
            contracts,
            direction=direction,
            limit=limit,
            **kwargs,
        )

    def _normalize_contract(
        self,
        raw_contract: Mapping[str, Any],
    ) -> dict[str, Any]:
        contract = dict(raw_contract)

        option_type = self._normalize_option_type(
            self._first_value(
                contract,
                "option_type",
                "type",
                "contract_type",
                "right",
            )
        )

        symbol = self._first_text(
            contract,
            "symbol",
            "contract_symbol",
            "option_symbol",
        )

        strike = self._first_number(
            contract,
            "strike",
            "strike_price",
        )

        expiration = self._first_text(
            contract,
            "expiration",
            "expiration_date",
            "expiry",
            "expiry_date",
        )

        open_interest = self._first_number(
            contract,
            "open_interest",
            "oi",
        )

        volume = self._first_number(
            contract,
            "volume",
            "day_volume",
        )

        bid = self._first_number(
            contract,
            "bid",
            "bid_price",
        )

        ask = self._first_number(
            contract,
            "ask",
            "ask_price",
        )

        last = self._first_number(
            contract,
            "last",
            "last_price",
            "price",
        )

        midpoint = self._first_number(
            contract,
            "midpoint",
            "mid",
        )

        spread = self._first_number(
            contract,
            "spread",
        )

        spread_percent = self._first_number(
            contract,
            "spread_percent",
            "spread_pct",
        )

        if (
            bid is not None
            and ask is not None
            and bid >= 0
            and ask >= bid
        ):
            midpoint = (bid + ask) / 2.0
            spread = ask - bid

            if midpoint > 0:
                spread_percent = (
                    spread / midpoint
                ) * 100.0
            else:
                spread_percent = None

        dte = self._first_number(
            contract,
            "days_to_expiration",
            "dte",
        )

        implied_volatility = self._first_number(
            contract,
            "implied_volatility",
            "iv",
        )

        delta = self._first_number(
            contract,
            "delta",
        )

        gamma = self._first_number(
            contract,
            "gamma",
        )

        theta = self._first_number(
            contract,
            "theta",
        )

        vega = self._first_number(
            contract,
            "vega",
        )

        rho = self._first_number(
            contract,
            "rho",
        )

        tradable = self._first_bool(
            contract,
            "tradable",
            "is_tradable",
        )

        multiplier = self._first_number(
            contract,
            "multiplier",
            "contract_multiplier",
        )

        contract.update(
            {
                "symbol": (
                    symbol.upper()
                    if symbol
                    else None
                ),
                "option_type": option_type,
                "strike": strike,
                "expiration": expiration,
                "open_interest": open_interest,
                "volume": volume,
                "bid": bid,
                "ask": ask,
                "last": last,
                "midpoint": midpoint,
                "spread": spread,
                "spread_percent": spread_percent,
                "days_to_expiration": (
                    int(dte)
                    if dte is not None
                    and dte.is_integer()
                    else dte
                ),
                "implied_volatility": (
                    implied_volatility
                ),
                "delta": delta,
                "gamma": gamma,
                "theta": theta,
                "vega": vega,
                "rho": rho,
                "tradable": tradable,
                "multiplier": multiplier,
            }
        )

        return contract

    def _matches_filters(
        self,
        contract: Mapping[str, Any],
        filters: Mapping[str, Any],
    ) -> bool:
        min_open_interest = filters.get(
            "min_open_interest"
        )

        if min_open_interest is not None:
            open_interest = self._num(
                contract.get("open_interest")
            )

            if (
                open_interest is None
                or open_interest
                < min_open_interest
            ):
                return False

        min_volume = filters.get(
            "min_volume"
        )

        if min_volume is not None:
            volume = self._num(
                contract.get("volume")
            )

            if (
                volume is None
                or volume < min_volume
            ):
                return False

        max_spread_percent = filters.get(
            "max_spread_percent"
        )

        if max_spread_percent is not None:
            spread_percent = self._num(
                contract.get(
                    "spread_percent"
                )
            )

            if (
                spread_percent is None
                or spread_percent
                > max_spread_percent
            ):
                return False

        dte = self._num(
            contract.get(
                "days_to_expiration"
            )
        )

        min_dte = filters.get(
            "min_dte"
        )

        if min_dte is not None:
            if (
                dte is None
                or dte < min_dte
            ):
                return False

        max_dte = filters.get(
            "max_dte"
        )

        if max_dte is not None:
            if (
                dte is None
                or dte > max_dte
            ):
                return False

        delta = self._num(
            contract.get("delta")
        )

        min_delta = filters.get(
            "min_delta"
        )

        if min_delta is not None:
            if (
                delta is None
                or delta < min_delta
            ):
                return False

        max_delta = filters.get(
            "max_delta"
        )

        if max_delta is not None:
            if (
                delta is None
                or delta > max_delta
            ):
                return False

        iv = self._num(
            contract.get(
                "implied_volatility"
            )
        )

        min_iv = filters.get(
            "min_implied_volatility"
        )

        if min_iv is not None:
            if (
                iv is None
                or iv < min_iv
            ):
                return False

        max_iv = filters.get(
            "max_implied_volatility"
        )

        if max_iv is not None:
            if (
                iv is None
                or iv > max_iv
            ):
                return False

        return True

    def _score(
        self,
        contract: Mapping[str, Any],
        *,
        target_dte: int | None,
        target_abs_delta: float | None,
    ) -> tuple[
        float | None,
        list[str],
    ]:
        """
        Build a relative execution-quality score from observed values only.

        Each component is normalized independently. Missing components are
        excluded from both numerator and denominator.

        This is a contract-selection ranking score, not expected return,
        probability of profit, strategy confidence or trade authorization.
        """

        components: list[
            tuple[
                float,
                float,
                str,
            ]
        ] = []

        open_interest = self._num(
            contract.get(
                "open_interest"
            )
        )

        if (
            open_interest is not None
            and open_interest >= 0
        ):
            normalized = self._log_normalize(
                open_interest,
                reference=10_000.0,
            )

            components.append(
                (
                    normalized,
                    0.30,
                    (
                        "open interest "
                        f"{open_interest:g}"
                    ),
                )
            )

        volume = self._num(
            contract.get("volume")
        )

        if (
            volume is not None
            and volume >= 0
        ):
            normalized = self._log_normalize(
                volume,
                reference=5_000.0,
            )

            components.append(
                (
                    normalized,
                    0.25,
                    f"volume {volume:g}",
                )
            )

        spread_percent = self._num(
            contract.get(
                "spread_percent"
            )
        )

        if (
            spread_percent is not None
            and spread_percent >= 0
        ):
            normalized = max(
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
                    normalized,
                    0.25,
                    (
                        "spread "
                        f"{spread_percent:.4f}%"
                    ),
                )
            )

        tradable = contract.get(
            "tradable"
        )

        if isinstance(
            tradable,
            bool,
        ):
            components.append(
                (
                    1.0
                    if tradable
                    else 0.0,
                    0.05,
                    (
                        "broker reports tradable"
                        if tradable
                        else "broker reports not tradable"
                    ),
                )
            )

        dte = self._num(
            contract.get(
                "days_to_expiration"
            )
        )

        if (
            target_dte is not None
            and dte is not None
            and dte >= 0
        ):
            distance = abs(
                dte
                - float(target_dte)
            )

            denominator = max(
                float(target_dte),
                1.0,
            )

            normalized = max(
                0.0,
                1.0
                - (
                    distance
                    / denominator
                ),
            )

            components.append(
                (
                    normalized,
                    0.10,
                    (
                        f"DTE {dte:g}; "
                        f"target {target_dte}"
                    ),
                )
            )

        delta = self._num(
            contract.get("delta")
        )

        if (
            target_abs_delta is not None
            and delta is not None
        ):
            observed_abs_delta = abs(
                delta
            )

            distance = abs(
                observed_abs_delta
                - target_abs_delta
            )

            denominator = max(
                target_abs_delta,
                0.01,
            )

            normalized = max(
                0.0,
                1.0
                - (
                    distance
                    / denominator
                ),
            )

            components.append(
                (
                    normalized,
                    0.05,
                    (
                        "absolute delta "
                        f"{observed_abs_delta:.4f}; "
                        "target "
                        f"{target_abs_delta:.4f}"
                    ),
                )
            )

        if not components:
            return (
                None,
                [],
            )

        total_weight = sum(
            weight
            for _, weight, _ in components
        )

        if total_weight <= 0:
            return (
                None,
                [],
            )

        score = (
            sum(
                value * weight
                for value, weight, _ in components
            )
            / total_weight
        )

        reasons = [
            reason
            for _, _, reason in components
        ]

        return (
            score,
            reasons,
        )

    @staticmethod
    def _sort_key(
        row: tuple[
            float | None,
            dict[str, Any],
            list[str],
        ],
    ) -> tuple[Any, ...]:
        score, contract, _ = row

        open_interest = OptionsSelector._num(
            contract.get(
                "open_interest"
            )
        )

        volume = OptionsSelector._num(
            contract.get(
                "volume"
            )
        )

        spread = OptionsSelector._num(
            contract.get(
                "spread_percent"
            )
        )

        dte = OptionsSelector._num(
            contract.get(
                "days_to_expiration"
            )
        )

        strike = OptionsSelector._num(
            contract.get(
                "strike"
            )
        )

        symbol = str(
            contract.get(
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
            (
                dte
                if dte is not None
                else float("inf")
            ),
            (
                strike
                if strike is not None
                else float("inf")
            ),
            symbol,
        )

    @classmethod
    def _validate_filters(
        cls,
        *,
        min_open_interest: float | None,
        min_volume: float | None,
        max_spread_percent: float | None,
        min_dte: int | None,
        max_dte: int | None,
        target_dte: int | None,
        min_delta: float | None,
        max_delta: float | None,
        target_abs_delta: float | None,
        min_implied_volatility: float | None,
        max_implied_volatility: float | None,
    ) -> dict[str, Any]:
        normalized_min_oi = cls._nonnegative(
            min_open_interest,
            "min_open_interest",
        )

        normalized_min_volume = cls._nonnegative(
            min_volume,
            "min_volume",
        )

        normalized_max_spread = cls._nonnegative(
            max_spread_percent,
            "max_spread_percent",
        )

        normalized_min_dte = cls._integer(
            min_dte,
            "min_dte",
        )

        normalized_max_dte = cls._integer(
            max_dte,
            "max_dte",
        )

        normalized_target_dte = cls._integer(
            target_dte,
            "target_dte",
        )

        for field, value in (
            ("min_dte", normalized_min_dte),
            ("max_dte", normalized_max_dte),
            ("target_dte", normalized_target_dte),
        ):
            if (
                value is not None
                and value < 0
            ):
                raise ValueError(
                    f"{field} cannot be negative"
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

        normalized_min_delta = cls._num(
            min_delta
        )

        if (
            min_delta is not None
            and normalized_min_delta is None
        ):
            raise ValueError(
                "min_delta must be numeric"
            )

        normalized_max_delta = cls._num(
            max_delta
        )

        if (
            max_delta is not None
            and normalized_max_delta is None
        ):
            raise ValueError(
                "max_delta must be numeric"
            )

        if (
            normalized_min_delta is not None
            and normalized_max_delta is not None
            and normalized_min_delta
            > normalized_max_delta
        ):
            raise ValueError(
                "min_delta cannot exceed max_delta"
            )

        normalized_target_delta = cls._num(
            target_abs_delta
        )

        if target_abs_delta is not None:
            if normalized_target_delta is None:
                raise ValueError(
                    "target_abs_delta must be numeric"
                )

            normalized_target_delta = abs(
                normalized_target_delta
            )

            if normalized_target_delta > 1.0:
                raise ValueError(
                    "target_abs_delta cannot exceed 1"
                )

        normalized_min_iv = cls._nonnegative(
            min_implied_volatility,
            "min_implied_volatility",
        )

        normalized_max_iv = cls._nonnegative(
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

        return {
            "min_open_interest": normalized_min_oi,
            "min_volume": normalized_min_volume,
            "max_spread_percent": normalized_max_spread,
            "min_dte": normalized_min_dte,
            "max_dte": normalized_max_dte,
            "target_dte": normalized_target_dte,
            "min_delta": normalized_min_delta,
            "max_delta": normalized_max_delta,
            "target_abs_delta": normalized_target_delta,
            "min_implied_volatility": normalized_min_iv,
            "max_implied_volatility": normalized_max_iv,
        }

    @classmethod
    def _direction_to_option_type(
        cls,
        direction: Any,
    ) -> str | None:
        if direction is None:
            return None

        normalized = str(
            direction
        ).strip().upper()

        if not normalized:
            return None

        if normalized in {
            cls.BUY,
            "BULLISH",
            "LONG",
            cls.CALL,
            "CALLS",
            "C",
        }:
            return cls.CALL

        if normalized in {
            cls.SELL,
            "BEARISH",
            "SHORT",
            cls.PUT,
            "PUTS",
            "P",
        }:
            return cls.PUT

        if normalized in {
            "HOLD",
            "NEUTRAL",
            "NONE",
        }:
            return None

        raise ValueError(
            f"Unsupported options direction: {direction}"
        )

    @classmethod
    def _normalize_option_type(
        cls,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(
            value
        ).strip().upper()

        if normalized in {
            "CALL",
            "CALLS",
            "C",
        }:
            return cls.CALL

        if normalized in {
            "PUT",
            "PUTS",
            "P",
        }:
            return cls.PUT

        return None

    @staticmethod
    def _normalize_limit(
        value: Any,
    ) -> int:
        if isinstance(value, bool):
            raise ValueError(
                "limit must be an integer"
            )

        try:
            parsed = int(value)
        except (
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ValueError(
                "limit must be an integer"
            ) from exc

        if parsed < 0:
            raise ValueError(
                "limit cannot be negative"
            )

        return min(
            parsed,
            OptionsSelector.MAX_LIMIT,
        )

    @staticmethod
    def _nonnegative(
        value: Any,
        field: str,
    ) -> float | None:
        if value is None:
            return None

        number = OptionsSelector._num(
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
    def _integer(
        value: Any,
        field: str,
    ) -> int | None:
        if value is None:
            return None

        if isinstance(value, bool):
            raise ValueError(
                f"{field} must be an integer"
            )

        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ValueError(
                f"{field} must be an integer"
            ) from exc

        if (
            not isfinite(number)
            or not number.is_integer()
        ):
            raise ValueError(
                f"{field} must be an integer"
            )

        return int(number)

    @staticmethod
    def _log_normalize(
        value: float,
        *,
        reference: float,
    ) -> float:
        if value <= 0:
            return 0.0

        if reference <= 0:
            return 1.0

        denominator = log1p(
            reference
        )

        if denominator <= 0:
            return 1.0

        return max(
            0.0,
            min(
                1.0,
                log1p(value)
                / denominator,
            ),
        )

    @classmethod
    def _first_number(
        cls,
        source: Mapping[str, Any],
        *keys: str,
    ) -> float | None:
        for key in keys:
            if key not in source:
                continue

            value = cls._num(
                source.get(key)
            )

            if value is not None:
                return value

        return None

    @staticmethod
    def _num(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        if isinstance(value, bool):
            return None

        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if not isfinite(number):
            return None

        return number

    @classmethod
    def _first_bool(
        cls,
        source: Mapping[str, Any],
        *keys: str,
    ) -> bool | None:
        for key in keys:
            if key not in source:
                continue

            result = cls._bool(
                source.get(key)
            )

            if result is not None:
                return result

        return None

    @staticmethod
    def _bool(
        value: Any,
    ) -> bool | None:
        if isinstance(value, bool):
            return value

        if isinstance(
            value,
            int,
        ) and value in {
            0,
            1,
        }:
            return bool(value)

        if isinstance(value, str):
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
    def _first_value(
        source: Mapping[str, Any],
        *keys: str,
    ) -> Any:
        for key in keys:
            if key not in source:
                continue

            value = source.get(key)

            if value is not None:
                return value

        return None

    @staticmethod
    def _first_text(
        source: Mapping[str, Any],
        *keys: str,
    ) -> str | None:
        for key in keys:
            if key not in source:
                continue

            text = OptionsSelector._text(
                source.get(key)
            )

            if text is not None:
                return text

        return None

    @staticmethod
    def _text(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        text = str(value).strip()

        return text or None


options_selector = OptionsSelector()


__all__ = [
    "OptionSelection",
    "OptionsSelector",
    "options_selector",
]