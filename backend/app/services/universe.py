from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from threading import RLock
from time import monotonic
from typing import Any, Iterable, Mapping, Sequence

from ..broker import alpaca_broker
from .discovery import discovery_service


@dataclass(frozen=True)
class UniverseSnapshot:
    asset_class: str
    symbols: tuple[str, ...]
    source: str
    broker_connected: bool
    supported: bool
    reason: str | None = None
    validated: bool = False
    validation_attempted: bool = False
    rejected_symbols: tuple[str, ...] = ()
    provider: str | None = None

    def dump(self) -> dict[str, Any]:
        return {
            "asset_class": self.asset_class,
            "symbols": list(self.symbols),
            "count": len(self.symbols),
            "source": self.source,
            "broker_connected": self.broker_connected,
            "supported": self.supported,
            "reason": self.reason,
            "validated": self.validated,
            "validation_attempted": self.validation_attempted,
            "rejected_symbols": list(self.rejected_symbols),
            "rejected_count": len(self.rejected_symbols),
            "provider": self.provider,
        }


@dataclass(frozen=True)
class AssetValidation:
    symbol: str
    valid: bool
    tradable: bool | None
    asset_class: str | None
    status: str | None
    reason: str | None = None

    def dump(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "valid": self.valid,
            "tradable": self.tradable,
            "asset_class": self.asset_class,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: float
    snapshot: UniverseSnapshot


class UniverseService:
    """
    PhoenixTrend automation universe resolver.

    Responsibilities:
        - normalize PhoenixTrend asset-class names
        - obtain genuine broker/provider asset universes when the connected
          broker adapter exposes a list-assets or equivalent capability
        - preserve configured discovery universes as explicit seed universes
          when dynamic enumeration is unavailable
        - validate configured symbols against the broker when requested
        - exclude explicitly non-tradable or inactive assets
        - preserve capability/unavailability state instead of inventing support
        - keep Forex/Bonds unavailable unless the broker explicitly reports
          support or exposes genuine assets for those classes
        - deduplicate and normalize provider symbols
        - cache expensive universe enumeration briefly without fabricating data

    This service does NOT:
        - rank candidates
        - calculate scanner metrics
        - call DecisionEngine for every symbol
        - invent broker capabilities
        - invent market symbols
        - invent tradability
        - treat a failed provider request as an empty successful universe

    Automation discovery should use:

        UniverseService
            -> MarketScanner
            -> CandidateRanker
            -> DecisionEngine

    Broad universe resolution belongs here. Candidate analysis does not.
    """

    ASSET_CLASSES = frozenset(
        {
            "stocks",
            "options",
            "crypto",
            "etfs",
            "forex",
            "bonds",
        }
    )

    _MAP = {
        "stocks": "prebuilt",
        "options": "options-flow",
        "crypto": "crypto",
        "etfs": "etfs",
    }

    _ALIASES = {
        "stock": "stocks",
        "stocks": "stocks",
        "equity": "stocks",
        "equities": "stocks",
        "share": "stocks",
        "shares": "stocks",

        "option": "options",
        "options": "options",

        "crypto": "crypto",
        "cryptocurrency": "crypto",
        "cryptocurrencies": "crypto",
        "digital_asset": "crypto",
        "digital_assets": "crypto",

        "etf": "etfs",
        "etfs": "etfs",
        "exchange_traded_fund": "etfs",
        "exchange_traded_funds": "etfs",

        "fx": "forex",
        "forex": "forex",
        "foreign_exchange": "forex",

        "bond": "bonds",
        "bonds": "bonds",
        "fixed_income": "bonds",
        "fixedincome": "bonds",
    }

    _BROKER_ASSET_CLASS_ALIASES = {
        "us_equity": "stocks",
        "equity": "stocks",
        "stock": "stocks",
        "stocks": "stocks",

        "option": "options",
        "options": "options",

        "crypto": "crypto",
        "cryptocurrency": "crypto",

        "etf": "etfs",
        "etfs": "etfs",

        "forex": "forex",
        "fx": "forex",

        "bond": "bonds",
        "bonds": "bonds",
        "fixed_income": "bonds",
    }

    _ENUMERATION_METHODS = (
        "list_assets",
        "assets",
        "get_assets",
        "tradable_assets",
        "list_tradable_assets",
    )

    _ASSET_LOOKUP_METHODS = (
        "get_asset",
        "asset",
        "lookup_asset",
    )

    _SYMBOL_KEYS = (
        "symbol",
        "ticker",
        "code",
        "asset_symbol",
    )

    _ASSET_CLASS_KEYS = (
        "asset_class",
        "class",
        "asset_type",
        "type",
    )

    _STATUS_KEYS = (
        "status",
        "state",
    )

    _TRADABLE_KEYS = (
        "tradable",
        "is_tradable",
    )

    _ACTIVE_STATUS = frozenset(
        {
            "active",
            "tradable",
            "enabled",
        }
    )

    _INACTIVE_STATUS = frozenset(
        {
            "inactive",
            "disabled",
            "delisted",
            "halted",
            "suspended",
        }
    )

    CACHE_TTL_SECONDS = 30.0

    def __init__(self) -> None:
        self._lock = RLock()
        self._cache: dict[
            tuple[str, bool, bool],
            _CacheEntry,
        ] = {}

    # ============================================================
    # ASSET CLASS
    # ============================================================

    def normalize_asset_class(
        self,
        value: str,
    ) -> str:
        normalized = (
            str(value or "")
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

        normalized = self._ALIASES.get(
            normalized,
            normalized,
        )

        if normalized not in self.ASSET_CLASSES:
            raise ValueError(
                f"Unsupported asset class: {value}"
            )

        return normalized

    # ============================================================
    # SYMBOL NORMALIZATION
    # ============================================================

    @staticmethod
    def normalize_symbol(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        text = str(
            value
        ).strip().upper()

        if not text:
            return None

        if len(text) > 64:
            return None

        if any(
            character.isspace()
            for character in text
        ):
            return None

        return text

    # ============================================================
    # DEDUPE
    # ============================================================

    @classmethod
    def _dedupe(
        cls,
        symbols: Iterable[str],
    ) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()

        for symbol in symbols:
            item = cls.normalize_symbol(
                symbol
            )

            if (
                item is None
                or item in seen
            ):
                continue

            seen.add(
                item
            )

            output.append(
                item
            )

        return output

    def dedupe(
        self,
        symbols: Iterable[str],
    ) -> list[str]:
        return self._dedupe(
            symbols
        )

    # ============================================================
    # CONFIGURED UNIVERSE
    # ============================================================

    def configured(
        self,
        asset_class: str,
    ) -> list[str]:
        asset = self.normalize_asset_class(
            asset_class
        )

        category = self._MAP.get(
            asset
        )

        if category is None:
            return []

        universes = getattr(
            discovery_service,
            "CATEGORY_UNIVERSES",
            None,
        )

        if not isinstance(
            universes,
            Mapping,
        ):
            return []

        raw = universes.get(
            category
        )

        if raw is None:
            return []

        if isinstance(
            raw,
            str,
        ):
            return self._dedupe(
                [raw]
            )

        if not isinstance(
            raw,
            Iterable,
        ):
            return []

        return self._dedupe(
            raw
        )

    # ============================================================
    # CAPABILITIES
    # ============================================================

    def capability(
        self,
        asset_class: str,
    ) -> dict[str, Any]:
        asset = self.normalize_asset_class(
            asset_class
        )

        connected = self._broker_connected()

        capabilities = self._broker_capabilities()

        capability = (
            capabilities.get(asset)
            if isinstance(
                capabilities,
                Mapping,
            )
            else None
        )

        explicit = isinstance(
            capability,
            Mapping,
        )

        supported: bool | None = None
        reason: str | None = None
        provider: str | None = None

        if explicit:
            supported = self._strict_bool(
                capability.get(
                    "supported"
                )
            )

            reason = self._text(
                capability.get(
                    "reason"
                )
            )

            provider = self._text(
                capability.get(
                    "provider"
                )
            )

        if provider is None:
            provider = self._provider_name(
                capabilities
            )

        enumerator = self._asset_enumerator()

        configured = self.configured(
            asset
        )

        if supported is None:
            if asset in {
                "forex",
                "bonds",
            }:
                supported = False

                if reason is None:
                    reason = (
                        "Broker capability for this asset class "
                        "has not been explicitly confirmed."
                    )

            elif configured:
                supported = True

            elif enumerator is not None:
                supported = True

            else:
                supported = False

                if reason is None:
                    reason = (
                        "No configured universe or broker asset "
                        "enumeration capability is available."
                    )

        return {
            "asset_class": asset,
            "supported": supported,
            "reason": reason,
            "broker_connected": connected,
            "provider": provider,
            "capability_explicit": explicit,
            "dynamic_enumeration_available": (
                enumerator is not None
            ),
            "configured_symbol_count": len(
                configured
            ),
        }

    # ============================================================
    # SNAPSHOT
    # ============================================================

    def snapshot(
        self,
        asset_class: str,
        *,
        validate_with_broker: bool = False,
        prefer_broker_universe: bool = True,
        use_cache: bool = True,
    ) -> UniverseSnapshot:
        asset = self.normalize_asset_class(
            asset_class
        )

        cache_key = (
            asset,
            bool(validate_with_broker),
            bool(prefer_broker_universe),
        )

        if use_cache:
            cached = self._cache_get(
                cache_key
            )

            if cached is not None:
                return cached

        capability = self.capability(
            asset
        )

        connected = bool(
            capability[
                "broker_connected"
            ]
        )

        supported = bool(
            capability[
                "supported"
            ]
        )

        provider = self._text(
            capability.get(
                "provider"
            )
        )

        capability_reason = self._text(
            capability.get(
                "reason"
            )
        )

        if not supported:
            snapshot = UniverseSnapshot(
                asset_class=asset,
                symbols=(),
                source="unavailable",
                broker_connected=connected,
                supported=False,
                reason=capability_reason
                or (
                    "Asset class is not supported "
                    "by the current broker/provider."
                ),
                validated=False,
                validation_attempted=False,
                rejected_symbols=(),
                provider=provider,
            )

            self._cache_put(
                cache_key,
                snapshot,
            )

            return snapshot

        configured_symbols = self.configured(
            asset
        )

        dynamic_symbols: list[str] = []
        dynamic_attempted = False
        dynamic_error: str | None = None

        if (
            prefer_broker_universe
            and connected
        ):
            (
                dynamic_symbols,
                dynamic_attempted,
                dynamic_error,
            ) = self._broker_universe(
                asset
            )

        if dynamic_symbols:
            symbols = dynamic_symbols
            source = (
                "broker_asset_universe"
            )

        elif configured_symbols:
            symbols = configured_symbols
            source = (
                "configured_discovery_universe"
            )

        else:
            symbols = []

            if dynamic_attempted:
                source = (
                    "broker_asset_universe"
                )
            else:
                source = "unavailable"

        validation_attempted = False
        validated = False
        rejected: list[str] = []

        if (
            validate_with_broker
            and symbols
        ):
            if not connected:
                validation_reason = (
                    "Broker validation was requested "
                    "but the broker is not connected."
                )

                snapshot = UniverseSnapshot(
                    asset_class=asset,
                    symbols=tuple(
                        symbols
                    ),
                    source=source,
                    broker_connected=False,
                    supported=True,
                    reason=validation_reason,
                    validated=False,
                    validation_attempted=False,
                    rejected_symbols=(),
                    provider=provider,
                )

                self._cache_put(
                    cache_key,
                    snapshot,
                )

                return snapshot

            validation_attempted = True

            valid_symbols: list[str] = []

            for symbol in symbols:
                result = self.validate_symbol(
                    asset,
                    symbol,
                )

                if result.valid:
                    valid_symbols.append(
                        symbol
                    )
                else:
                    rejected.append(
                        symbol
                    )

            symbols = valid_symbols
            validated = True

        reason: str | None = None

        if not symbols:
            if dynamic_error:
                reason = dynamic_error

            elif (
                dynamic_attempted
                and not configured_symbols
            ):
                reason = (
                    "Broker asset enumeration returned "
                    "no eligible symbols."
                )

            elif not configured_symbols:
                reason = (
                    "No configured or broker-provided "
                    "symbols are available."
                )

            elif (
                validation_attempted
                and rejected
            ):
                reason = (
                    "All candidate symbols were rejected "
                    "during broker validation."
                )

        elif (
            dynamic_error
            and source
            == "configured_discovery_universe"
        ):
            reason = (
                "Broker universe enumeration was unavailable; "
                "using the configured discovery universe."
            )

        snapshot = UniverseSnapshot(
            asset_class=asset,
            symbols=tuple(
                self._dedupe(
                    symbols
                )
            ),
            source=source,
            broker_connected=connected,
            supported=True,
            reason=reason,
            validated=validated,
            validation_attempted=(
                validation_attempted
            ),
            rejected_symbols=tuple(
                self._dedupe(
                    rejected
                )
            ),
            provider=provider,
        )

        self._cache_put(
            cache_key,
            snapshot,
        )

        return snapshot

    # ============================================================
    # SYMBOLS
    # ============================================================

    def symbols(
        self,
        asset_class: str,
        *,
        limit: int | None = None,
        validate_with_broker: bool = False,
        prefer_broker_universe: bool = True,
    ) -> list[str]:
        snapshot = self.snapshot(
            asset_class,
            validate_with_broker=(
                validate_with_broker
            ),
            prefer_broker_universe=(
                prefer_broker_universe
            ),
        )

        values = list(
            snapshot.symbols
        )

        normalized_limit = self._limit(
            limit
        )

        if normalized_limit is not None:
            values = values[
                :normalized_limit
            ]

        return values

    # ============================================================
    # VALIDATE SYMBOL
    # ============================================================

    def validate_symbol(
        self,
        asset_class: str,
        symbol: str,
    ) -> AssetValidation:
        asset = self.normalize_asset_class(
            asset_class
        )

        normalized_symbol = (
            self.normalize_symbol(
                symbol
            )
        )

        if normalized_symbol is None:
            return AssetValidation(
                symbol=str(
                    symbol or ""
                ),
                valid=False,
                tradable=None,
                asset_class=None,
                status=None,
                reason="Invalid symbol",
            )

        if not self._broker_connected():
            return AssetValidation(
                symbol=normalized_symbol,
                valid=False,
                tradable=None,
                asset_class=None,
                status=None,
                reason=(
                    "Broker is not connected"
                ),
            )

        lookup = self._asset_lookup()

        if lookup is None:
            return AssetValidation(
                symbol=normalized_symbol,
                valid=False,
                tradable=None,
                asset_class=None,
                status=None,
                reason=(
                    "Broker adapter does not expose "
                    "an asset lookup capability"
                ),
            )

        try:
            payload = lookup(
                normalized_symbol
            )

        except Exception as exc:
            return AssetValidation(
                symbol=normalized_symbol,
                valid=False,
                tradable=None,
                asset_class=None,
                status=None,
                reason=self._safe_error(
                    exc,
                    fallback=(
                        "Broker asset lookup failed"
                    ),
                ),
            )

        asset_payload = self._mapping(
            payload
        )

        if asset_payload is None:
            return AssetValidation(
                symbol=normalized_symbol,
                valid=False,
                tradable=None,
                asset_class=None,
                status=None,
                reason=(
                    "Broker returned an invalid asset payload"
                ),
            )

        broker_symbol = (
            self.normalize_symbol(
                self._first(
                    asset_payload,
                    *self._SYMBOL_KEYS,
                )
            )
            or normalized_symbol
        )

        broker_asset_class = (
            self._normalize_broker_asset_class(
                self._first(
                    asset_payload,
                    *self._ASSET_CLASS_KEYS,
                )
            )
        )

        tradable = self._strict_bool(
            self._first(
                asset_payload,
                *self._TRADABLE_KEYS,
            )
        )

        status = self._text(
            self._first(
                asset_payload,
                *self._STATUS_KEYS,
            )
        )

        status_normalized = (
            status.casefold()
            if status
            else None
        )

        if tradable is False:
            return AssetValidation(
                symbol=broker_symbol,
                valid=False,
                tradable=False,
                asset_class=(
                    broker_asset_class
                ),
                status=status,
                reason=(
                    "Broker reports asset as non-tradable"
                ),
            )

        if (
            status_normalized
            in self._INACTIVE_STATUS
        ):
            return AssetValidation(
                symbol=broker_symbol,
                valid=False,
                tradable=tradable,
                asset_class=(
                    broker_asset_class
                ),
                status=status,
                reason=(
                    "Broker reports asset as inactive"
                ),
            )

        if (
            broker_asset_class
            is not None
            and not self._asset_class_matches(
                requested=asset,
                broker_asset_class=(
                    broker_asset_class
                ),
                payload=asset_payload,
            )
        ):
            return AssetValidation(
                symbol=broker_symbol,
                valid=False,
                tradable=tradable,
                asset_class=(
                    broker_asset_class
                ),
                status=status,
                reason=(
                    "Broker asset class does not match "
                    "the requested universe"
                ),
            )

        if tradable is None:
            return AssetValidation(
                symbol=broker_symbol,
                valid=False,
                tradable=None,
                asset_class=(
                    broker_asset_class
                ),
                status=status,
                reason=(
                    "Broker asset payload does not confirm tradability"
                ),
            )

        return AssetValidation(
            symbol=broker_symbol,
            valid=True,
            tradable=True,
            asset_class=(
                broker_asset_class
            ),
            status=status,
            reason=None,
        )

    # ============================================================
    # BROKER UNIVERSE
    # ============================================================

    def _broker_universe(
        self,
        asset_class: str,
    ) -> tuple[
        list[str],
        bool,
        str | None,
    ]:
        enumerator = self._asset_enumerator()

        if enumerator is None:
            return (
                [],
                False,
                None,
            )

        payload: Any = None

        try:
            payload = self._call_asset_enumerator(
                enumerator,
                asset_class,
            )

        except Exception as exc:
            return (
                [],
                True,
                self._safe_error(
                    exc,
                    fallback=(
                        "Broker asset enumeration failed"
                    ),
                ),
            )

        assets = self._extract_assets(
            payload
        )

        if assets is None:
            return (
                [],
                True,
                (
                    "Broker returned an unsupported "
                    "asset-universe payload."
                ),
            )

        symbols: list[str] = []

        for item in assets:
            mapping = self._mapping(
                item
            )

            if mapping is None:
                continue

            symbol = self.normalize_symbol(
                self._first(
                    mapping,
                    *self._SYMBOL_KEYS,
                )
            )

            if symbol is None:
                continue

            broker_asset_class = (
                self._normalize_broker_asset_class(
                    self._first(
                        mapping,
                        *self._ASSET_CLASS_KEYS,
                    )
                )
            )

            if (
                broker_asset_class
                is not None
                and not self._asset_class_matches(
                    requested=asset_class,
                    broker_asset_class=(
                        broker_asset_class
                    ),
                    payload=mapping,
                )
            ):
                continue

            tradable = self._strict_bool(
                self._first(
                    mapping,
                    *self._TRADABLE_KEYS,
                )
            )

            if tradable is False:
                continue

            status = self._text(
                self._first(
                    mapping,
                    *self._STATUS_KEYS,
                )
            )

            if (
                status is not None
                and status.casefold()
                in self._INACTIVE_STATUS
            ):
                continue

            if tradable is not True:
                continue

            symbols.append(
                symbol
            )

        return (
            self._dedupe(
                symbols
            ),
            True,
            None,
        )

    # ============================================================
    # BROKER ENUMERATOR CALL
    # ============================================================

    def _call_asset_enumerator(
        self,
        enumerator: Any,
        asset_class: str,
    ) -> Any:
        """
        Invoke a broker enumeration method conservatively.

        We do not assume that every adapter accepts the same keyword
        arguments. The first call uses no guessed provider-specific filters.

        Filtering is performed locally against returned asset metadata.
        """

        return enumerator()

    # ============================================================
    # EXTRACT ASSETS
    # ============================================================

    def _extract_assets(
        self,
        payload: Any,
    ) -> list[Any] | None:
        if payload is None:
            return None

        if isinstance(
            payload,
            Mapping,
        ):
            for key in (
                "assets",
                "data",
                "results",
                "items",
            ):
                value = payload.get(
                    key
                )

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

            if self._first(
                payload,
                *self._SYMBOL_KEYS,
            ) is not None:
                return [
                    payload
                ]

            return []

        if isinstance(
            payload,
            Sequence,
        ) and not isinstance(
            payload,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            return list(
                payload
            )

        try:
            values = list(
                payload
            )

        except TypeError:
            return None

        return values

    # ============================================================
    # ASSET CLASS MATCH
    # ============================================================

    def _asset_class_matches(
        self,
        *,
        requested: str,
        broker_asset_class: str,
        payload: Mapping[str, Any],
    ) -> bool:
        if requested == broker_asset_class:
            return True

        if requested in {
            "stocks",
            "etfs",
        } and broker_asset_class == "stocks":
            return self._equity_subtype_matches(
                requested=requested,
                payload=payload,
            )

        return False

    def _equity_subtype_matches(
        self,
        *,
        requested: str,
        payload: Mapping[str, Any],
    ) -> bool:
        subtype = self._text(
            self._first(
                payload,
                "asset_type",
                "security_type",
                "type",
                "category",
            )
        )

        if subtype is None:
            # Many equity APIs expose ETFs under the same "us_equity"
            # asset class without a reliable subtype. In that case we
            # cannot prove an ETF classification from the broker payload.
            return requested == "stocks"

        normalized = (
            subtype
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

        etf_markers = {
            "etf",
            "exchange_traded_fund",
            "exchange_traded_product",
            "fund",
        }

        if requested == "etfs":
            return normalized in (
                etf_markers
            )

        if requested == "stocks":
            return normalized not in (
                etf_markers
            )

        return False

    # ============================================================
    # BROKER ASSET CLASS
    # ============================================================

    def _normalize_broker_asset_class(
        self,
        value: Any,
    ) -> str | None:
        text = self._text(
            value
        )

        if text is None:
            return None

        normalized = (
            text
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

        return (
            self._BROKER_ASSET_CLASS_ALIASES.get(
                normalized,
                normalized,
            )
        )

    # ============================================================
    # BROKER CONNECTION
    # ============================================================

    @staticmethod
    def _broker_connected() -> bool:
        method = getattr(
            alpaca_broker,
            "is_connected",
            None,
        )

        if not callable(
            method
        ):
            return False

        try:
            result = method()

        except Exception:
            return False

        return result is True

    # ============================================================
    # BROKER CAPABILITIES
    # ============================================================

    @staticmethod
    def _broker_capabilities() -> dict[str, Any]:
        method = getattr(
            alpaca_broker,
            "capabilities",
            None,
        )

        if not callable(
            method
        ):
            return {}

        try:
            result = method()

        except Exception:
            return {}

        if isinstance(
            result,
            Mapping,
        ):
            return dict(
                result
            )

        return {}

    # ============================================================
    # PROVIDER NAME
    # ============================================================

    @staticmethod
    def _provider_name(
        capabilities: Mapping[str, Any],
    ) -> str | None:
        for key in (
            "provider",
            "broker",
            "name",
        ):
            value = capabilities.get(
                key
            )

            text = UniverseService._text(
                value
            )

            if text:
                return text

        broker_name = getattr(
            alpaca_broker,
            "name",
            None,
        )

        return UniverseService._text(
            broker_name
        )

    # ============================================================
    # ENUMERATOR
    # ============================================================

    @classmethod
    def _asset_enumerator(
        cls,
    ) -> Any | None:
        for method_name in (
            cls._ENUMERATION_METHODS
        ):
            method = getattr(
                alpaca_broker,
                method_name,
                None,
            )

            if callable(
                method
            ):
                return method

        return None

    # ============================================================
    # ASSET LOOKUP
    # ============================================================

    @classmethod
    def _asset_lookup(
        cls,
    ) -> Any | None:
        for method_name in (
            cls._ASSET_LOOKUP_METHODS
        ):
            method = getattr(
                alpaca_broker,
                method_name,
                None,
            )

            if callable(
                method
            ):
                return method

        return None

    # ============================================================
    # CACHE
    # ============================================================

    def _cache_get(
        self,
        key: tuple[
            str,
            bool,
            bool,
        ],
    ) -> UniverseSnapshot | None:
        now = monotonic()

        with self._lock:
            entry = self._cache.get(
                key
            )

            if entry is None:
                return None

            if (
                entry.expires_at
                <= now
            ):
                self._cache.pop(
                    key,
                    None,
                )

                return None

            return entry.snapshot

    def _cache_put(
        self,
        key: tuple[
            str,
            bool,
            bool,
        ],
        snapshot: UniverseSnapshot,
    ) -> None:
        ttl = self._number(
            self.CACHE_TTL_SECONDS
        )

        if (
            ttl is None
            or ttl <= 0
        ):
            return

        entry = _CacheEntry(
            expires_at=(
                monotonic()
                + ttl
            ),
            snapshot=snapshot,
        )

        with self._lock:
            self._cache[
                key
            ] = entry

    def clear_cache(
        self,
        asset_class: str | None = None,
    ) -> None:
        with self._lock:
            if asset_class is None:
                self._cache.clear()
                return

            asset = (
                self.normalize_asset_class(
                    asset_class
                )
            )

            keys = [
                key
                for key
                in self._cache
                if key[0]
                == asset
            ]

            for key in keys:
                self._cache.pop(
                    key,
                    None,
                )

    # ============================================================
    # STATUS
    # ============================================================

    def status(
        self,
    ) -> dict[str, Any]:
        assets: dict[
            str,
            dict[str, Any],
        ] = {}

        for asset_class in sorted(
            self.ASSET_CLASSES
        ):
            assets[
                asset_class
            ] = self.capability(
                asset_class
            )

        return {
            "broker_connected": (
                self._broker_connected()
            ),
            "dynamic_enumeration_available": (
                self._asset_enumerator()
                is not None
            ),
            "asset_lookup_available": (
                self._asset_lookup()
                is not None
            ),
            "assets": assets,
        }

    # ============================================================
    # PAYLOAD HELPERS
    # ============================================================

    @staticmethod
    def _mapping(
        value: Any,
    ) -> dict[str, Any] | None:
        if value is None:
            return None

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
            try:
                result = model_dump()

            except Exception:
                result = None

            if isinstance(
                result,
                Mapping,
            ):
                return dict(
                    result
                )

        to_dict = getattr(
            value,
            "to_dict",
            None,
        )

        if callable(
            to_dict
        ):
            try:
                result = to_dict()

            except Exception:
                result = None

            if isinstance(
                result,
                Mapping,
            ):
                return dict(
                    result
                )

        raw = getattr(
            value,
            "__dict__",
            None,
        )

        if isinstance(
            raw,
            Mapping,
        ):
            return {
                key: item
                for key, item
                in raw.items()
                if not str(
                    key
                ).startswith(
                    "_"
                )
            }

        return None

    @staticmethod
    def _first(
        mapping: Mapping[str, Any],
        *keys: str,
    ) -> Any:
        for key in keys:
            if key not in mapping:
                continue

            value = mapping.get(
                key
            )

            if value is not None:
                return value

        return None

    # ============================================================
    # BOOLEAN
    # ============================================================

    @staticmethod
    def _strict_bool(
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
                value.strip().lower()
            )

            if normalized in {
                "true",
                "1",
                "yes",
                "on",
                "enabled",
                "supported",
                "tradable",
                "active",
            }:
                return True

            if normalized in {
                "false",
                "0",
                "no",
                "off",
                "disabled",
                "unsupported",
                "non_tradable",
                "inactive",
            }:
                return False

        return None

    # ============================================================
    # TEXT
    # ============================================================

    @staticmethod
    def _text(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        text = str(
            value
        ).strip()

        if not text:
            return None

        return text

    # ============================================================
    # NUMBER
    # ============================================================

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
            parsed = float(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if not isfinite(
            parsed
        ):
            return None

        return parsed

    # ============================================================
    # LIMIT
    # ============================================================

    @staticmethod
    def _limit(
        value: Any,
    ) -> int | None:
        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "limit must be an integer"
            )

        try:
            parsed = int(
                value
            )

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

        return parsed

    # ============================================================
    # SAFE ERROR
    # ============================================================

    @staticmethod
    def _safe_error(
        exc: Exception,
        *,
        fallback: str,
    ) -> str:
        """
        Do not expose provider response bodies, credentials, URLs containing
        query secrets, or arbitrary exception internals through universe API
        responses.
        """

        name = (
            exc.__class__.__name__
        )

        if not name:
            return fallback

        return (
            f"{fallback} ({name})"
        )


universe_service = UniverseService()


__all__ = [
    "AssetValidation",
    "UniverseService",
    "UniverseSnapshot",
    "universe_service",
]