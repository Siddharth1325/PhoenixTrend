from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence

from ..broker import alpaca_broker


class OptionsChainService:
    """
    PhoenixTrend broker-backed options-chain service.

    Responsibilities
    ----------------
    * Detect whether the connected broker adapter exposes options-chain or
      options-contract discovery capability.
    * Retrieve real broker/provider option contracts.
    * Normalize broker payloads into a stable PhoenixTrend representation.
    * Preserve the raw provider payload for downstream consumers that require
      provider-specific fields.
    * Apply caller-requested filters only to fields actually supplied by the
      provider.
    * Never synthesize contracts, expirations, strikes, quotes, Greeks,
      open interest, volume, spreads, implied volatility, or tradability.
    * Fail closed when options-chain capability is unavailable.

    This service is read-only. It does not place orders and does not imply that
    a returned contract is executable. Final order execution must still pass
    broker capability, market safety, risk and execution validation.
    """

    METHOD_NAMES: tuple[str, ...] = (
        "options_chain",
        "get_options_chain",
        "option_contracts",
        "get_option_contracts",
    )

    CONTRACT_COLLECTION_KEYS: tuple[str, ...] = (
        "contracts",
        "options",
        "option_contracts",
        "data",
        "results",
    )

    SYMBOL_KEYS: tuple[str, ...] = (
        "symbol",
        "contract_symbol",
        "option_symbol",
        "ticker",
    )

    UNDERLYING_KEYS: tuple[str, ...] = (
        "underlying",
        "underlying_symbol",
        "underlying_ticker",
        "root_symbol",
    )

    TYPE_KEYS: tuple[str, ...] = (
        "type",
        "option_type",
        "contract_type",
        "right",
        "side",
    )

    STRIKE_KEYS: tuple[str, ...] = (
        "strike",
        "strike_price",
    )

    EXPIRATION_KEYS: tuple[str, ...] = (
        "expiration",
        "expiration_date",
        "expiry",
        "expiry_date",
        "expiration_timestamp",
    )

    BID_KEYS: tuple[str, ...] = (
        "bid",
        "bid_price",
    )

    ASK_KEYS: tuple[str, ...] = (
        "ask",
        "ask_price",
    )

    LAST_KEYS: tuple[str, ...] = (
        "last",
        "last_price",
        "price",
        "mark",
    )

    VOLUME_KEYS: tuple[str, ...] = (
        "volume",
        "day_volume",
    )

    OPEN_INTEREST_KEYS: tuple[str, ...] = (
        "open_interest",
        "openInterest",
        "oi",
    )

    IMPLIED_VOLATILITY_KEYS: tuple[str, ...] = (
        "implied_volatility",
        "impliedVolatility",
        "iv",
    )

    TRADABLE_KEYS: tuple[str, ...] = (
        "tradable",
        "is_tradable",
    )

    STATUS_KEYS: tuple[str, ...] = (
        "status",
        "contract_status",
    )

    MULTIPLIER_KEYS: tuple[str, ...] = (
        "multiplier",
        "contract_multiplier",
    )

    DELTA_KEYS: tuple[str, ...] = (
        "delta",
    )

    GAMMA_KEYS: tuple[str, ...] = (
        "gamma",
    )

    THETA_KEYS: tuple[str, ...] = (
        "theta",
    )

    VEGA_KEYS: tuple[str, ...] = (
        "vega",
    )

    RHO_KEYS: tuple[str, ...] = (
        "rho",
    )

    QUOTE_TIMESTAMP_KEYS: tuple[str, ...] = (
        "quote_timestamp",
        "quote_time",
        "timestamp",
        "as_of",
    )

    def available(self) -> bool:
        return self._resolve_method() is not None

    def capability(self) -> dict[str, Any]:
        resolved = self._resolve_method()

        if resolved is None:
            return {
                "available": False,
                "provider": "alpaca",
                "source": None,
                "method": None,
                "reason": (
                    "Connected broker adapter does not expose an "
                    "options-chain API"
                ),
            }

        method_name, _ = resolved

        return {
            "available": True,
            "provider": "alpaca",
            "source": f"broker:{method_name}",
            "method": method_name,
            "reason": None,
        }

    def chain(
        self,
        underlying: str,
        **filters: Any,
    ) -> dict[str, Any]:
        symbol = self._normalize_underlying(
            underlying
        )

        resolved = self._resolve_method()

        if resolved is None:
            return self._unavailable(
                symbol
            )

        method_name, method = resolved

        normalized_filters = self._normalize_filters(
            filters
        )

        payload = method(
            symbol,
            **normalized_filters["provider_filters"],
        )

        contracts = self._extract_contracts(
            payload
        )

        normalized_contracts: list[dict[str, Any]] = []

        rejected_contracts = 0

        for raw_contract in contracts:
            contract = self._normalize_contract(
                symbol,
                raw_contract,
            )

            if contract is None:
                rejected_contracts += 1
                continue

            if not self._matches_filters(
                contract,
                normalized_filters,
            ):
                continue

            normalized_contracts.append(
                contract
            )

        normalized_contracts.sort(
            key=self._contract_sort_key
        )

        limit = normalized_filters.get(
            "limit"
        )

        if isinstance(
            limit,
            int,
        ):
            normalized_contracts = (
                normalized_contracts[
                    :limit
                ]
            )

        as_of = self._payload_as_of(
            payload
        )

        provider = self._payload_provider(
            payload
        )

        return {
            "underlying": symbol,
            "available": True,
            "provider": provider,
            "source": f"broker:{method_name}",
            "method": method_name,
            "as_of": as_of,
            "contract_count": len(
                normalized_contracts
            ),
            "rejected_contract_count": (
                rejected_contracts
            ),
            "filters": normalized_filters[
                "response_filters"
            ],
            "contracts": normalized_contracts,
            "raw": payload,
        }

    def contracts(
        self,
        underlying: str,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        result = self.chain(
            underlying,
            **filters,
        )

        return list(
            result.get(
                "contracts",
                [],
            )
        )

    def calls(
        self,
        underlying: str,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        merged = dict(
            filters
        )

        merged[
            "option_type"
        ] = "call"

        return self.contracts(
            underlying,
            **merged,
        )

    def puts(
        self,
        underlying: str,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        merged = dict(
            filters
        )

        merged[
            "option_type"
        ] = "put"

        return self.contracts(
            underlying,
            **merged,
        )

    def expirations(
        self,
        underlying: str,
        **filters: Any,
    ) -> list[str]:
        contracts = self.contracts(
            underlying,
            **filters,
        )

        expirations = {
            str(
                contract[
                    "expiration"
                ]
            )
            for contract in contracts
            if contract.get(
                "expiration"
            )
        }

        return sorted(
            expirations
        )

    def strikes(
        self,
        underlying: str,
        *,
        expiration: str | date | datetime | None = None,
        option_type: str | None = None,
        **filters: Any,
    ) -> list[float]:
        merged = dict(
            filters
        )

        if expiration is not None:
            merged[
                "expiration"
            ] = expiration

        if option_type is not None:
            merged[
                "option_type"
            ] = option_type

        contracts = self.contracts(
            underlying,
            **merged,
        )

        strikes = {
            float(
                contract[
                    "strike"
                ]
            )
            for contract in contracts
            if self._number(
                contract.get(
                    "strike"
                )
            )
            is not None
        }

        return sorted(
            strikes
        )

    def find_contract(
        self,
        underlying: str,
        *,
        contract_symbol: str | None = None,
        expiration: str | date | datetime | None = None,
        strike: float | None = None,
        option_type: str | None = None,
        **filters: Any,
    ) -> dict[str, Any] | None:
        merged = dict(
            filters
        )

        if expiration is not None:
            merged[
                "expiration"
            ] = expiration

        if strike is not None:
            merged[
                "strike"
            ] = strike

        if option_type is not None:
            merged[
                "option_type"
            ] = option_type

        contracts = self.contracts(
            underlying,
            **merged,
        )

        normalized_contract_symbol = (
            str(
                contract_symbol
            )
            .strip()
            .upper()
            if contract_symbol
            else None
        )

        for contract in contracts:
            if (
                normalized_contract_symbol
                is not None
                and str(
                    contract.get(
                        "symbol"
                    )
                    or ""
                ).upper()
                != normalized_contract_symbol
            ):
                continue

            return contract

        return None

    def _resolve_method(
        self,
    ) -> tuple[str, Any] | None:
        for name in self.METHOD_NAMES:
            method = getattr(
                alpaca_broker,
                name,
                None,
            )

            if callable(
                method
            ):
                return (
                    name,
                    method,
                )

        return None

    def _extract_contracts(
        self,
        payload: Any,
    ) -> list[Any]:
        if payload is None:
            return []

        if isinstance(
            payload,
            Mapping,
        ):
            for key in self.CONTRACT_COLLECTION_KEYS:
                value = payload.get(
                    key
                )

                if value is None:
                    continue

                extracted = self._coerce_contract_collection(
                    value
                )

                if extracted is not None:
                    return extracted

            nested = payload.get(
                "option_chain"
            )

            if isinstance(
                nested,
                Mapping,
            ):
                for key in self.CONTRACT_COLLECTION_KEYS:
                    value = nested.get(
                        key
                    )

                    if value is None:
                        continue

                    extracted = self._coerce_contract_collection(
                        value
                    )

                    if extracted is not None:
                        return extracted

            if self._looks_like_contract(
                payload
            ):
                return [
                    dict(
                        payload
                    )
                ]

            return []

        extracted = self._coerce_contract_collection(
            payload
        )

        return (
            extracted
            if extracted is not None
            else []
        )

    def _coerce_contract_collection(
        self,
        value: Any,
    ) -> list[Any] | None:
        if value is None:
            return []

        if isinstance(
            value,
            Mapping,
        ):
            if self._looks_like_contract(
                value
            ):
                return [
                    dict(
                        value
                    )
                ]

            output: list[Any] = []

            for key, item in value.items():
                if isinstance(
                    item,
                    Mapping,
                ):
                    candidate = dict(
                        item
                    )

                    if not self._first_value(
                        candidate,
                        *self.SYMBOL_KEYS,
                    ):
                        candidate[
                            "symbol"
                        ] = str(
                            key
                        )

                    output.append(
                        candidate
                    )

            return output

        if isinstance(
            value,
            Sequence,
        ) and not isinstance(
            value,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            return list(
                value
            )

        if isinstance(
            value,
            Iterable,
        ) and not isinstance(
            value,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            try:
                return list(
                    value
                )
            except TypeError:
                return None

        return None

    def _normalize_contract(
        self,
        underlying: str,
        raw_contract: Any,
    ) -> dict[str, Any] | None:
        contract = self._object_to_mapping(
            raw_contract
        )

        if not contract:
            return None

        symbol = self._first_text(
            contract,
            *self.SYMBOL_KEYS,
        )

        provider_underlying = self._first_text(
            contract,
            *self.UNDERLYING_KEYS,
        )

        normalized_underlying = (
            provider_underlying.upper()
            if provider_underlying
            else underlying
        )

        option_type = self._normalize_option_type(
            self._first_value(
                contract,
                *self.TYPE_KEYS,
            )
        )

        strike = self._first_number(
            contract,
            *self.STRIKE_KEYS,
        )

        expiration = self._normalize_expiration(
            self._first_value(
                contract,
                *self.EXPIRATION_KEYS,
            )
        )

        bid = self._first_number(
            contract,
            *self.BID_KEYS,
        )

        ask = self._first_number(
            contract,
            *self.ASK_KEYS,
        )

        last = self._first_number(
            contract,
            *self.LAST_KEYS,
        )

        spread: float | None = None
        spread_percent: float | None = None
        midpoint: float | None = None

        if (
            bid is not None
            and ask is not None
            and bid >= 0
            and ask >= bid
        ):
            spread = ask - bid
            midpoint = (
                bid
                + ask
            ) / 2.0

            if midpoint > 0:
                spread_percent = (
                    spread
                    / midpoint
                ) * 100.0

        volume = self._first_number(
            contract,
            *self.VOLUME_KEYS,
        )

        open_interest = self._first_number(
            contract,
            *self.OPEN_INTEREST_KEYS,
        )

        implied_volatility = self._first_number(
            contract,
            *self.IMPLIED_VOLATILITY_KEYS,
        )

        multiplier = self._first_number(
            contract,
            *self.MULTIPLIER_KEYS,
        )

        tradable = self._first_bool(
            contract,
            *self.TRADABLE_KEYS,
        )

        status = self._first_text(
            contract,
            *self.STATUS_KEYS,
        )

        delta = self._first_number(
            contract,
            *self.DELTA_KEYS,
        )

        gamma = self._first_number(
            contract,
            *self.GAMMA_KEYS,
        )

        theta = self._first_number(
            contract,
            *self.THETA_KEYS,
        )

        vega = self._first_number(
            contract,
            *self.VEGA_KEYS,
        )

        rho = self._first_number(
            contract,
            *self.RHO_KEYS,
        )

        quote_timestamp = self._normalize_timestamp(
            self._first_value(
                contract,
                *self.QUOTE_TIMESTAMP_KEYS,
            )
        )

        normalized: dict[str, Any] = {
            "symbol": (
                symbol.upper()
                if symbol
                else None
            ),
            "underlying": normalized_underlying,
            "option_type": option_type,
            "strike": strike,
            "expiration": expiration,
            "bid": bid,
            "ask": ask,
            "last": last,
            "midpoint": midpoint,
            "spread": spread,
            "spread_percent": spread_percent,
            "volume": volume,
            "open_interest": open_interest,
            "implied_volatility": implied_volatility,
            "multiplier": multiplier,
            "tradable": tradable,
            "status": status,
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "rho": rho,
            "quote_timestamp": quote_timestamp,
            "raw": deepcopy(
                contract
            ),
        }

        return normalized

    def _normalize_filters(
        self,
        filters: Mapping[str, Any],
    ) -> dict[str, Any]:
        provider_filters = dict(
            filters
        )

        response_filters: dict[str, Any] = {}

        option_type_raw = self._pop_first(
            provider_filters,
            "option_type",
            "type",
            "contract_type",
            "right",
        )

        option_type = self._normalize_option_type(
            option_type_raw
        )

        if option_type_raw is not None:
            if option_type is None:
                raise ValueError(
                    "option_type must be call or put"
                )

            response_filters[
                "option_type"
            ] = option_type

        expiration_raw = self._pop_first(
            provider_filters,
            "expiration",
            "expiration_date",
            "expiry",
            "expiry_date",
        )

        expiration = self._normalize_expiration(
            expiration_raw
        )

        if expiration_raw is not None:
            if expiration is None:
                raise ValueError(
                    "Invalid expiration"
                )

            response_filters[
                "expiration"
            ] = expiration

        expiration_from_raw = self._pop_first(
            provider_filters,
            "expiration_from",
            "expiration_date_gte",
            "expiry_from",
        )

        expiration_from = self._normalize_expiration(
            expiration_from_raw
        )

        if expiration_from_raw is not None:
            if expiration_from is None:
                raise ValueError(
                    "Invalid expiration_from"
                )

            response_filters[
                "expiration_from"
            ] = expiration_from

        expiration_to_raw = self._pop_first(
            provider_filters,
            "expiration_to",
            "expiration_date_lte",
            "expiry_to",
        )

        expiration_to = self._normalize_expiration(
            expiration_to_raw
        )

        if expiration_to_raw is not None:
            if expiration_to is None:
                raise ValueError(
                    "Invalid expiration_to"
                )

            response_filters[
                "expiration_to"
            ] = expiration_to

        strike_raw = self._pop_first(
            provider_filters,
            "strike",
            "strike_price",
        )

        strike = self._number(
            strike_raw
        )

        if strike_raw is not None:
            if strike is None:
                raise ValueError(
                    "Invalid strike"
                )

            response_filters[
                "strike"
            ] = strike

        min_strike_raw = self._pop_first(
            provider_filters,
            "min_strike",
            "strike_gte",
            "strike_price_gte",
        )

        min_strike = self._number(
            min_strike_raw
        )

        if min_strike_raw is not None:
            if min_strike is None:
                raise ValueError(
                    "Invalid min_strike"
                )

            response_filters[
                "min_strike"
            ] = min_strike

        max_strike_raw = self._pop_first(
            provider_filters,
            "max_strike",
            "strike_lte",
            "strike_price_lte",
        )

        max_strike = self._number(
            max_strike_raw
        )

        if max_strike_raw is not None:
            if max_strike is None:
                raise ValueError(
                    "Invalid max_strike"
                )

            response_filters[
                "max_strike"
            ] = max_strike

        min_open_interest_raw = self._pop_first(
            provider_filters,
            "min_open_interest",
            "open_interest_gte",
        )

        min_open_interest = self._number(
            min_open_interest_raw
        )

        if min_open_interest_raw is not None:
            if min_open_interest is None:
                raise ValueError(
                    "Invalid min_open_interest"
                )

            response_filters[
                "min_open_interest"
            ] = min_open_interest

        min_volume_raw = self._pop_first(
            provider_filters,
            "min_volume",
            "volume_gte",
        )

        min_volume = self._number(
            min_volume_raw
        )

        if min_volume_raw is not None:
            if min_volume is None:
                raise ValueError(
                    "Invalid min_volume"
                )

            response_filters[
                "min_volume"
            ] = min_volume

        max_spread_percent_raw = self._pop_first(
            provider_filters,
            "max_spread_percent",
            "max_spread_pct",
        )

        max_spread_percent = self._number(
            max_spread_percent_raw
        )

        if max_spread_percent_raw is not None:
            if (
                max_spread_percent is None
                or max_spread_percent < 0
            ):
                raise ValueError(
                    "Invalid max_spread_percent"
                )

            response_filters[
                "max_spread_percent"
            ] = max_spread_percent

        tradable_raw = self._pop_first(
            provider_filters,
            "tradable",
        )

        tradable = self._coerce_bool(
            tradable_raw
        )

        if tradable_raw is not None:
            if tradable is None:
                raise ValueError(
                    "Invalid tradable filter"
                )

            response_filters[
                "tradable"
            ] = tradable

        limit_raw = self._pop_first(
            provider_filters,
            "limit",
        )

        limit: int | None = None

        if limit_raw is not None:
            try:
                limit = int(
                    limit_raw
                )
            except (
                TypeError,
                ValueError,
                OverflowError,
            ) as exc:
                raise ValueError(
                    "Invalid limit"
                ) from exc

            if limit <= 0:
                raise ValueError(
                    "limit must be greater than zero"
                )

            response_filters[
                "limit"
            ] = limit

        # Preserve provider-compatible forms of filters that were consumed
        # above. This allows a capable broker adapter to reduce the upstream
        # result set while PhoenixTrend still validates the returned contracts.
        if option_type is not None:
            provider_filters[
                "option_type"
            ] = option_type

        if expiration is not None:
            provider_filters[
                "expiration"
            ] = expiration

        if expiration_from is not None:
            provider_filters[
                "expiration_from"
            ] = expiration_from

        if expiration_to is not None:
            provider_filters[
                "expiration_to"
            ] = expiration_to

        if strike is not None:
            provider_filters[
                "strike"
            ] = strike

        if min_strike is not None:
            provider_filters[
                "min_strike"
            ] = min_strike

        if max_strike is not None:
            provider_filters[
                "max_strike"
            ] = max_strike

        if min_open_interest is not None:
            provider_filters[
                "min_open_interest"
            ] = min_open_interest

        if min_volume is not None:
            provider_filters[
                "min_volume"
            ] = min_volume

        if max_spread_percent is not None:
            provider_filters[
                "max_spread_percent"
            ] = max_spread_percent

        if tradable is not None:
            provider_filters[
                "tradable"
            ] = tradable

        if limit is not None:
            provider_filters[
                "limit"
            ] = limit

        return {
            "provider_filters": provider_filters,
            "response_filters": response_filters,
            "option_type": option_type,
            "expiration": expiration,
            "expiration_from": expiration_from,
            "expiration_to": expiration_to,
            "strike": strike,
            "min_strike": min_strike,
            "max_strike": max_strike,
            "min_open_interest": min_open_interest,
            "min_volume": min_volume,
            "max_spread_percent": max_spread_percent,
            "tradable": tradable,
            "limit": limit,
        }

    def _matches_filters(
        self,
        contract: Mapping[str, Any],
        filters: Mapping[str, Any],
    ) -> bool:
        option_type = filters.get(
            "option_type"
        )

        if option_type is not None:
            contract_type = contract.get(
                "option_type"
            )

            if contract_type is None:
                return False

            if contract_type != option_type:
                return False

        expiration = filters.get(
            "expiration"
        )

        contract_expiration = contract.get(
            "expiration"
        )

        if expiration is not None:
            if contract_expiration is None:
                return False

            if contract_expiration != expiration:
                return False

        expiration_from = filters.get(
            "expiration_from"
        )

        if expiration_from is not None:
            if contract_expiration is None:
                return False

            if contract_expiration < expiration_from:
                return False

        expiration_to = filters.get(
            "expiration_to"
        )

        if expiration_to is not None:
            if contract_expiration is None:
                return False

            if contract_expiration > expiration_to:
                return False

        strike = filters.get(
            "strike"
        )

        contract_strike = self._number(
            contract.get(
                "strike"
            )
        )

        if strike is not None:
            if contract_strike is None:
                return False

            if contract_strike != strike:
                return False

        min_strike = filters.get(
            "min_strike"
        )

        if min_strike is not None:
            if contract_strike is None:
                return False

            if contract_strike < min_strike:
                return False

        max_strike = filters.get(
            "max_strike"
        )

        if max_strike is not None:
            if contract_strike is None:
                return False

            if contract_strike > max_strike:
                return False

        min_open_interest = filters.get(
            "min_open_interest"
        )

        if min_open_interest is not None:
            open_interest = self._number(
                contract.get(
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
                contract.get(
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
                contract.get(
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

        tradable = filters.get(
            "tradable"
        )

        if tradable is not None:
            contract_tradable = contract.get(
                "tradable"
            )

            if not isinstance(
                contract_tradable,
                bool,
            ):
                return False

            if contract_tradable != tradable:
                return False

        return True

    @staticmethod
    def _contract_sort_key(
        contract: Mapping[str, Any],
    ) -> tuple[Any, ...]:
        expiration = str(
            contract.get(
                "expiration"
            )
            or "9999-12-31"
        )

        option_type = str(
            contract.get(
                "option_type"
            )
            or ""
        )

        strike = OptionsChainService._number(
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
            expiration,
            option_type,
            (
                strike
                if strike is not None
                else float("inf")
            ),
            symbol,
        )

    @staticmethod
    def _normalize_underlying(
        underlying: Any,
    ) -> str:
        symbol = str(
            underlying
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

    @classmethod
    def _normalize_expiration(
        cls,
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

        if isinstance(
            value,
            (int, float),
        ) and not isinstance(
            value,
            bool,
        ):
            number = cls._number(
                value
            )

            if number is None:
                return None

            try:
                return datetime.fromtimestamp(
                    number,
                    tz=timezone.utc,
                ).date().isoformat()
            except (
                ValueError,
                OSError,
                OverflowError,
            ):
                return None

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
            parsed_datetime = (
                datetime.fromisoformat(
                    candidate
                )
            )

            return (
                parsed_datetime
                .date()
                .isoformat()
            )

        except ValueError:
            pass

        try:
            return date.fromisoformat(
                text[:10]
            ).isoformat()

        except ValueError:
            return None

    @classmethod
    def _normalize_timestamp(
        cls,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(
            value,
            datetime,
        ):
            timestamp = value

            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(
                    tzinfo=timezone.utc
                )

            return timestamp.isoformat()

        if isinstance(
            value,
            (int, float),
        ) and not isinstance(
            value,
            bool,
        ):
            number = cls._number(
                value
            )

            if number is None:
                return None

            try:
                return datetime.fromtimestamp(
                    number,
                    tz=timezone.utc,
                ).isoformat()
            except (
                ValueError,
                OSError,
                OverflowError,
            ):
                return None

        text = str(
            value
        ).strip()

        return (
            text
            if text
            else None
        )

    @classmethod
    def _payload_as_of(
        cls,
        payload: Any,
    ) -> str | None:
        if not isinstance(
            payload,
            Mapping,
        ):
            return None

        return cls._normalize_timestamp(
            cls._first_value(
                payload,
                "as_of",
                "timestamp",
                "updated_at",
                "last_updated",
            )
        )

    @classmethod
    def _payload_provider(
        cls,
        payload: Any,
    ) -> str | None:
        if not isinstance(
            payload,
            Mapping,
        ):
            return None

        return cls._first_text(
            payload,
            "provider",
            "source",
            "broker",
        )

    @classmethod
    def _looks_like_contract(
        cls,
        value: Mapping[str, Any],
    ) -> bool:
        return bool(
            cls._first_value(
                value,
                *cls.SYMBOL_KEYS,
            )
            or cls._first_value(
                value,
                *cls.STRIKE_KEYS,
            )
            or cls._first_value(
                value,
                *cls.EXPIRATION_KEYS,
            )
        )

    @staticmethod
    def _object_to_mapping(
        value: Any,
    ) -> dict[str, Any]:
        if isinstance(
            value,
            Mapping,
        ):
            return dict(
                value
            )

        model_dump = getattr(
            value,
            "model_dump",
            None,
        )

        if callable(
            model_dump
        ):
            dumped = model_dump()

            if isinstance(
                dumped,
                Mapping,
            ):
                return dict(
                    dumped
                )

        dict_method = getattr(
            value,
            "dict",
            None,
        )

        if callable(
            dict_method
        ):
            dumped = dict_method()

            if isinstance(
                dumped,
                Mapping,
            ):
                return dict(
                    dumped
                )

        raw_dict = getattr(
            value,
            "__dict__",
            None,
        )

        if isinstance(
            raw_dict,
            Mapping,
        ):
            return {
                key: item
                for key, item in raw_dict.items()
                if not str(
                    key
                ).startswith(
                    "_"
                )
            }

        return {}

    @classmethod
    def _first_number(
        cls,
        source: Mapping[str, Any],
        *keys: str,
    ) -> float | None:
        for key in keys:
            if key not in source:
                continue

            number = cls._number(
                source.get(
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

    @classmethod
    def _first_bool(
        cls,
        source: Mapping[str, Any],
        *keys: str,
    ) -> bool | None:
        for key in keys:
            if key not in source:
                continue

            value = cls._coerce_bool(
                source.get(
                    key
                )
            )

            if value is not None:
                return value

        return None

    @staticmethod
    def _coerce_bool(
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
    def _first_value(
        source: Mapping[str, Any],
        *keys: str,
    ) -> Any:
        for key in keys:
            if key not in source:
                continue

            value = source.get(
                key
            )

            if value is not None:
                return value

        return None

    @staticmethod
    def _first_text(
        source: Mapping[str, Any],
        *keys: str,
    ) -> str | None:
        for key in keys:
            value = source.get(
                key
            )

            if value is None:
                continue

            text = str(
                value
            ).strip()

            if text:
                return text

        return None

    @staticmethod
    def _pop_first(
        source: dict[str, Any],
        *keys: str,
    ) -> Any:
        found = None
        has_found = False

        for key in keys:
            if key not in source:
                continue

            value = source.pop(
                key
            )

            if not has_found:
                found = value
                has_found = True

        return found

    @staticmethod
    def _unavailable(
        underlying: str,
    ) -> dict[str, Any]:
        return {
            "underlying": underlying,
            "available": False,
            "provider": "alpaca",
            "source": None,
            "method": None,
            "as_of": None,
            "contract_count": 0,
            "rejected_contract_count": 0,
            "filters": {},
            "contracts": [],
            "raw": None,
            "reason": (
                "Connected broker adapter does not expose an "
                "options-chain API"
            ),
        }


options_chain_service = OptionsChainService()


__all__ = [
    "OptionsChainService",
    "options_chain_service",
]