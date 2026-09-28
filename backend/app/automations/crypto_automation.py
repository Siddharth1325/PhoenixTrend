from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .base_automation import (
    ACTION_BUY,
    ACTION_HOLD,
    ACTION_SELL,
    CANDIDATE_BLOCKED,
    CANDIDATE_SKIPPED,
    BaseAssetAutomation,
    CandidateRuntime,
    DecisionRuntime,
    normalize_symbol,
    safe_bool,
    safe_float,
    serialize_value,
)


logger = logging.getLogger(__name__)


# =============================================================================
# CRYPTO CONSTANTS
# =============================================================================

CRYPTO_ASSET_CLASS = "crypto"

DEFAULT_CRYPTO_SCAN_INTERVAL_SECONDS = 20.0
DEFAULT_CRYPTO_MONITOR_INTERVAL_SECONDS = 3.0
DEFAULT_CRYPTO_UNIVERSE_REFRESH_SECONDS = 300.0
DEFAULT_CRYPTO_CANDIDATE_LIMIT = 16

DEFAULT_MAX_SPREAD_PCT = 2.0
DEFAULT_MIN_PRICE = 0.00000001
DEFAULT_MIN_QUOTE_VOLUME = 0.0
DEFAULT_MIN_LIQUIDITY_SCORE = 0.0

DEFAULT_MAX_POSITION_FRACTION = 0.15
DEFAULT_MAX_CRYPTO_EXPOSURE_FRACTION = 0.35

DEFAULT_HOLD_RECHECK_SECONDS = 10.0
DEFAULT_STALE_CANDIDATE_SECONDS = 180.0

STABLECOINS = {
    "USDT",
    "USDC",
    "DAI",
    "FDUSD",
    "TUSD",
    "USDP",
    "PYUSD",
    "GUSD",
}

COMMON_QUOTE_ASSETS = (
    "USD",
    "USDT",
    "USDC",
    "BTC",
    "ETH",
    "EUR",
    "GBP",
)

CRYPTO_SYMBOL_KEYS = (
    "symbol",
    "ticker",
    "pair",
    "market",
    "instrument",
    "asset",
)

PRICE_KEYS = (
    "price",
    "last",
    "last_price",
    "current_price",
    "market_price",
    "mark",
    "mark_price",
    "mid",
)

BID_KEYS = (
    "bid",
    "bid_price",
    "best_bid",
)

ASK_KEYS = (
    "ask",
    "ask_price",
    "best_ask",
)

VOLUME_KEYS = (
    "volume",
    "base_volume",
    "volume_24h",
    "daily_volume",
)

QUOTE_VOLUME_KEYS = (
    "quote_volume",
    "quote_volume_24h",
    "notional_volume",
    "dollar_volume",
    "volume_usd",
)

CHANGE_KEYS = (
    "change_pct",
    "percent_change",
    "price_change_pct",
    "change_24h_pct",
    "percent_change_24h",
)

HIGH_KEYS = (
    "high",
    "high_24h",
    "day_high",
)

LOW_KEYS = (
    "low",
    "low_24h",
    "day_low",
)

OPEN_KEYS = (
    "open",
    "open_24h",
    "day_open",
)

LIQUIDITY_KEYS = (
    "liquidity",
    "liquidity_score",
)

BASE_ASSET_KEYS = (
    "base_asset",
    "base",
    "base_currency",
    "base_symbol",
)

QUOTE_ASSET_KEYS = (
    "quote_asset",
    "quote",
    "quote_currency",
    "quote_symbol",
)

MIN_ORDER_KEYS = (
    "min_order_size",
    "minimum_order",
    "min_qty",
    "minimum_quantity",
)

QTY_INCREMENT_KEYS = (
    "qty_increment",
    "quantity_increment",
    "step_size",
    "lot_size",
)

PRICE_INCREMENT_KEYS = (
    "price_increment",
    "tick_size",
    "minimum_price_increment",
)

CRYPTO_CAPABILITY_KEYS = (
    "crypto",
    "cryptocurrency",
    "digital_assets",
    "digital-assets",
)

CRYPTO_MARKET_DATA_CAPABILITY_KEYS = (
    "crypto_market_data",
    "crypto_quotes",
    "digital_asset_market_data",
)

CRYPTO_ORDER_CAPABILITY_KEYS = (
    "crypto_orders",
    "crypto_trading",
    "digital_asset_orders",
)


# =============================================================================
# HELPERS
# =============================================================================


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return dict(value)

    if isinstance(value, Mapping):
        return dict(value.items())

    if hasattr(value, "model_dump"):
        try:
            result = value.model_dump()
            if isinstance(result, Mapping):
                return dict(result)
        except Exception:
            pass

    if hasattr(value, "dict"):
        try:
            result = value.dict()
            if isinstance(result, Mapping):
                return dict(result)
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        except Exception:
            pass

    return {}


def _first(
    payload: Mapping[str, Any] | None,
    keys: Iterable[str],
    default: Any = None,
) -> Any:
    if not payload:
        return default

    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]

    return default


def _spread_pct(
    bid: float | None,
    ask: float | None,
) -> float | None:
    if bid is None or ask is None:
        return None

    if bid <= 0.0 or ask <= 0.0:
        return None

    if ask < bid:
        return None

    midpoint = (bid + ask) / 2.0

    if midpoint <= 0.0:
        return None

    return ((ask - bid) / midpoint) * 100.0


def _mid_price(
    bid: float | None,
    ask: float | None,
) -> float | None:
    if bid is None or ask is None:
        return None

    if bid <= 0.0 or ask <= 0.0:
        return None

    if ask < bid:
        return None

    return (bid + ask) / 2.0


def _normalize_asset_code(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().upper()

    if not text:
        return None

    return text


def _split_crypto_symbol(
    symbol: str,
) -> tuple[str | None, str | None]:
    normalized = str(symbol or "").strip().upper()

    if not normalized:
        return None, None

    for separator in (
        "/",
        "-",
        "_",
        ":",
    ):
        if separator in normalized:
            parts = [
                part
                for part in normalized.split(separator)
                if part
            ]

            if len(parts) >= 2:
                return parts[0], parts[1]

    for quote in sorted(
        COMMON_QUOTE_ASSETS,
        key=len,
        reverse=True,
    ):
        if (
            normalized.endswith(quote)
            and len(normalized) > len(quote)
        ):
            base = normalized[
                : -len(quote)
            ]

            if base:
                return base, quote

    return normalized, None


# =============================================================================
# CRYPTO MODELS
# =============================================================================


@dataclass
class CryptoInstrumentSnapshot:
    symbol: str

    base_asset: str | None = None
    quote_asset: str | None = None

    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread_pct: float | None = None

    open_24h: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    change_pct: float | None = None

    volume: float | None = None
    quote_volume: float | None = None
    liquidity_score: float | None = None

    min_order_size: float | None = None
    quantity_increment: float | None = None
    price_increment: float | None = None

    tradable: bool | None = None
    buyable: bool | None = None
    sellable: bool | None = None
    shortable: bool | None = None

    source: str | None = None
    as_of: str | None = None

    raw: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            {
                "symbol": self.symbol,
                "base_asset": self.base_asset,
                "quote_asset": self.quote_asset,
                "price": self.price,
                "bid": self.bid,
                "ask": self.ask,
                "spread_pct": self.spread_pct,
                "open_24h": self.open_24h,
                "high_24h": self.high_24h,
                "low_24h": self.low_24h,
                "change_pct": self.change_pct,
                "volume": self.volume,
                "quote_volume": self.quote_volume,
                "liquidity_score": self.liquidity_score,
                "min_order_size": self.min_order_size,
                "quantity_increment": self.quantity_increment,
                "price_increment": self.price_increment,
                "tradable": self.tradable,
                "buyable": self.buyable,
                "sellable": self.sellable,
                "shortable": self.shortable,
                "source": self.source,
                "as_of": self.as_of,
                "raw": self.raw,
            }
        )


@dataclass
class CryptoValidationResult:
    valid: bool
    reason: str | None = None
    warnings: list[str] = field(
        default_factory=list
    )
    snapshot: CryptoInstrumentSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            {
                "valid": self.valid,
                "reason": self.reason,
                "warnings": self.warnings,
                "snapshot": (
                    self.snapshot.to_dict()
                    if self.snapshot
                    else None
                ),
            }
        )


@dataclass
class CryptoRuntimeMetrics:
    capability_checks: int = 0
    capability_blocks: int = 0

    metadata_requests: int = 0
    metadata_failures: int = 0

    quote_requests: int = 0
    quote_failures: int = 0

    validations: int = 0
    validation_failures: int = 0

    spread_blocks: int = 0
    price_blocks: int = 0
    liquidity_blocks: int = 0
    tradability_blocks: int = 0
    buy_blocks: int = 0
    sell_blocks: int = 0
    short_blocks: int = 0

    execution_blocks: int = 0

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            self.__dict__
        )


# =============================================================================
# CRYPTO AUTOMATION
# =============================================================================


class CryptoAutomation(BaseAssetAutomation):
    """
    PhoenixTrend cryptocurrency automation runtime.

    The shared BaseAssetAutomation owns the common automation lifecycle:

        universe
        -> scanner
        -> candidate ranking
        -> Decision Engine
        -> BUY / SELL / HOLD
        -> safety
        -> risk
        -> execution
        -> position monitoring

    This class supplies crypto-specific capability validation, instrument
    metadata, quote validation, liquidity/spread checks, pair handling,
    execution constraints and continuous crypto position monitoring.

    It does not create synthetic crypto prices, volume, liquidity or broker
    capabilities when a provider does not return them.
    """

    asset_class = CRYPTO_ASSET_CLASS

    scan_interval_seconds = (
        DEFAULT_CRYPTO_SCAN_INTERVAL_SECONDS
    )

    monitor_interval_seconds = (
        DEFAULT_CRYPTO_MONITOR_INTERVAL_SECONDS
    )

    universe_refresh_seconds = (
        DEFAULT_CRYPTO_UNIVERSE_REFRESH_SECONDS
    )

    candidate_limit = (
        DEFAULT_CRYPTO_CANDIDATE_LIMIT
    )

    hold_recheck_seconds = (
        DEFAULT_HOLD_RECHECK_SECONDS
    )

    stale_candidate_seconds = (
        DEFAULT_STALE_CANDIDATE_SECONDS
    )

    max_concurrent_analysis = 5
    max_concurrent_executions = 1

    max_bid_ask_spread_pct = (
        DEFAULT_MAX_SPREAD_PCT
    )

    minimum_price = DEFAULT_MIN_PRICE

    minimum_quote_volume = (
        DEFAULT_MIN_QUOTE_VOLUME
    )

    minimum_liquidity_score = (
        DEFAULT_MIN_LIQUIDITY_SCORE
    )

    maximum_position_fraction = (
        DEFAULT_MAX_POSITION_FRACTION
    )

    maximum_crypto_exposure_fraction = (
        DEFAULT_MAX_CRYPTO_EXPOSURE_FRACTION
    )

    require_real_market_data = True
    require_execution_capability = True
    require_tradable_flag = True

    allow_automatic_entries = True

    preserve_position_monitoring_when_disabled = True

    def __init__(self) -> None:
        super().__init__()

        self.crypto_metrics = (
            CryptoRuntimeMetrics()
        )

        self._instrument_cache: dict[
            str,
            CryptoInstrumentSnapshot,
        ] = {}

        self._instrument_cache_lock = (
            asyncio.Lock()
        )

        self._capability_cache: (
            dict[str, Any] | None
        ) = None

        self._capability_checked_at: (
            str | None
        ) = None

    # =========================================================================
    # SERVICES
    # =========================================================================

    def _broker_service(self) -> Any | None:
        return self._resolve_service(
            "backend.app.broker",
            (
                "alpaca_broker",
                "broker",
                "broker_service",
                "broker_client",
            ),
        )

    def _market_service(self) -> Any | None:
        return self._resolve_service(
            "backend.app.services.market",
            (
                "market_service",
                "market",
            ),
        )

    def _live_market_service(self) -> Any | None:
        return self._resolve_service(
            "backend.app.services.live_market",
            (
                "live_market_service",
                "live_market",
            ),
        )

    # =========================================================================
    # CAPABILITIES
    # =========================================================================

    async def capability_snapshot(
        self,
    ) -> dict[str, Any]:
        self.crypto_metrics.capability_checks += 1

        base = (
            await super().capability_snapshot()
        )

        if not base.get(
            "supported",
            False,
        ):
            self.crypto_metrics.capability_blocks += 1

            result = {
                **base,
                "asset_class": self.asset_class,
                "supported": False,
                "market_data_supported": False,
                "execution_supported": False,
                "reason": (
                    base.get("reason")
                    or (
                        "Configured provider does not "
                        "advertise cryptocurrency support"
                    )
                ),
                "checked_at": _utc_now(),
            }

            self._capability_cache = result
            self._capability_checked_at = (
                result["checked_at"]
            )

            return result

        broker_capabilities = (
            await self._broker_capabilities()
        )

        general_crypto = (
            self._capability_value(
                broker_capabilities,
                CRYPTO_CAPABILITY_KEYS,
            )
        )

        market_data_supported = (
            self._capability_value(
                broker_capabilities,
                CRYPTO_MARKET_DATA_CAPABILITY_KEYS,
            )
        )

        execution_supported = (
            self._capability_value(
                broker_capabilities,
                CRYPTO_ORDER_CAPABILITY_KEYS,
            )
        )

        if market_data_supported is None:
            market_data_supported = (
                general_crypto
            )

        if execution_supported is None:
            execution_supported = (
                general_crypto
            )

        if market_data_supported is None:
            market_data_supported = bool(
                base.get(
                    "supported",
                    False,
                )
            )

        if execution_supported is None:
            execution_supported = False

        supported = bool(
            base.get(
                "supported",
                False,
            )
            and market_data_supported
        )

        reason: str | None = None

        if not market_data_supported:
            supported = False

            reason = (
                "Configured provider does not "
                "expose cryptocurrency market data"
            )

        elif (
            self.require_execution_capability
            and not execution_supported
        ):
            supported = False

            reason = (
                "Configured broker does not "
                "support cryptocurrency order execution"
            )

        if not supported:
            self.crypto_metrics.capability_blocks += 1

        result = {
            **base,
            "asset_class": self.asset_class,
            "supported": supported,
            "market_data_supported": bool(
                market_data_supported
            ),
            "execution_supported": bool(
                execution_supported
            ),
            "general_crypto_support": (
                general_crypto
            ),
            "reason": reason,
            "checked_at": _utc_now(),
        }

        self._capability_cache = result
        self._capability_checked_at = (
            result["checked_at"]
        )

        return result

    async def _broker_capabilities(
        self,
    ) -> dict[str, Any]:
        broker = self._broker_service()

        if broker is None:
            return {}

        for method_name in (
            "capabilities",
            "get_capabilities",
            "trading_capabilities",
            "broker_capabilities",
        ):
            method = getattr(
                broker,
                method_name,
                None,
            )

            if not callable(method):
                continue

            try:
                if asyncio.iscoroutinefunction(
                    method
                ):
                    result = await method()
                else:
                    result = (
                        await asyncio.to_thread(
                            method
                        )
                    )

                return _mapping(result)

            except Exception as exc:
                logger.debug(
                    "Crypto capability call failed "
                    "using %s: %s",
                    method_name,
                    exc,
                )

        raw = getattr(
            broker,
            "capabilities",
            None,
        )

        if isinstance(raw, Mapping):
            return dict(raw)

        return {}

    def _capability_value(
        self,
        capabilities: Mapping[str, Any],
        keys: Iterable[str],
    ) -> bool | None:
        if not capabilities:
            return None

        normalized = {
            str(key).strip().lower(): value
            for key, value
            in capabilities.items()
        }

        for key in keys:
            lookup = str(
                key
            ).strip().lower()

            if lookup not in normalized:
                continue

            value = normalized[lookup]

            if isinstance(
                value,
                Mapping,
            ):
                nested = _first(
                    value,
                    (
                        "supported",
                        "enabled",
                        "available",
                        "tradable",
                    ),
                )

                if nested is not None:
                    return safe_bool(
                        nested
                    )

            return safe_bool(value)

        assets = normalized.get(
            "assets"
        )

        if isinstance(
            assets,
            Mapping,
        ):
            normalized_assets = {
                str(key).strip().lower(): value
                for key, value
                in assets.items()
            }

            for key in keys:
                lookup = str(
                    key
                ).strip().lower()

                if lookup not in normalized_assets:
                    continue

                value = normalized_assets[
                    lookup
                ]

                if isinstance(
                    value,
                    Mapping,
                ):
                    nested = _first(
                        value,
                        (
                            "supported",
                            "enabled",
                            "available",
                            "tradable",
                        ),
                    )

                    if nested is not None:
                        return safe_bool(
                            nested
                        )

                return safe_bool(value)

        return None

    # =========================================================================
    # UNIVERSE
    # =========================================================================

    async def filter_universe(
        self,
        symbols: list[str],
    ) -> list[str]:
        """
        Keep only provider-returned crypto instruments.

        No stock ticker fallback is introduced here. The universe service must
        supply the actual tradable crypto universe.
        """

        result: list[str] = []
        seen: set[str] = set()

        for raw_symbol in symbols:
            symbol = normalize_symbol(
                raw_symbol
            )

            if not symbol:
                continue

            if symbol in seen:
                continue

            seen.add(symbol)
            result.append(symbol)

        return result

    # =========================================================================
    # PROVIDER CALLS
    # =========================================================================

    async def _try_service_methods(
        self,
        service: Any,
        method_names: Iterable[str],
        symbol: str,
        **extra: Any,
    ) -> Any | None:
        for method_name in method_names:
            method = getattr(
                service,
                method_name,
                None,
            )

            if not callable(method):
                continue

            call_variants = [
                (
                    (symbol,),
                    {},
                ),
                (
                    (symbol,),
                    extra,
                ),
                (
                    (),
                    {
                        "symbol": symbol,
                        **extra,
                    },
                ),
            ]

            for args, kwargs in call_variants:
                try:
                    if asyncio.iscoroutinefunction(
                        method
                    ):
                        result = await method(
                            *args,
                            **kwargs,
                        )
                    else:
                        result = (
                            await asyncio.to_thread(
                                method,
                                *args,
                                **kwargs,
                            )
                        )

                    if result is not None:
                        return result

                except TypeError:
                    continue

                except Exception as exc:
                    logger.debug(
                        "Crypto service call "
                        "%s.%s failed for %s: %s",
                        service.__class__.__name__,
                        method_name,
                        symbol,
                        exc,
                    )

                    break

        return None

    async def _fetch_crypto_metadata(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        self.crypto_metrics.metadata_requests += 1

        broker = self._broker_service()

        if broker is not None:
            result = await self._try_service_methods(
                broker,
                (
                    "get_crypto_asset",
                    "crypto_asset",
                    "get_asset",
                    "asset",
                    "instrument",
                ),
                symbol,
                asset_class=self.asset_class,
            )

            if result is not None:
                return _mapping(result)

        market = self._market_service()

        if market is not None:
            result = await self._try_service_methods(
                market,
                (
                    "crypto_metadata",
                    "instrument",
                    "asset",
                    "security",
                ),
                symbol,
                asset_class=self.asset_class,
            )

            if result is not None:
                return _mapping(result)

        self.crypto_metrics.metadata_failures += 1

        return {}

    async def _fetch_crypto_quote(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        self.crypto_metrics.quote_requests += 1

        live_market = (
            self._live_market_service()
        )

        if live_market is not None:
            result = await self._try_service_methods(
                live_market,
                (
                    "crypto_snapshot",
                    "snapshot",
                    "crypto_quote",
                    "latest_quote",
                    "quote",
                    "get_quote",
                ),
                symbol,
                asset_class=self.asset_class,
            )

            if result is not None:
                payload = _mapping(
                    result
                )

                if payload:
                    return payload

        market = self._market_service()

        if market is not None:
            result = await self._try_service_methods(
                market,
                (
                    "crypto_snapshot",
                    "snapshot",
                    "crypto_quote",
                    "latest_quote",
                    "quote",
                    "get_quote",
                ),
                symbol,
                asset_class=self.asset_class,
            )

            if result is not None:
                payload = _mapping(
                    result
                )

                if payload:
                    return payload

        broker = self._broker_service()

        if broker is not None:
            result = await self._try_service_methods(
                broker,
                (
                    "get_crypto_quote",
                    "crypto_quote",
                    "get_quote",
                    "quote",
                ),
                symbol,
                asset_class=self.asset_class,
            )

            if result is not None:
                payload = _mapping(
                    result
                )

                if payload:
                    return payload

        self.crypto_metrics.quote_failures += 1

        return {}

    # =========================================================================
    # INSTRUMENT SNAPSHOT
    # =========================================================================

    async def instrument_snapshot(
        self,
        symbol: str,
        *,
        force: bool = False,
    ) -> CryptoInstrumentSnapshot:
        symbol = normalize_symbol(
            symbol
        )

        if not symbol:
            raise ValueError(
                "Crypto symbol is required"
            )

        if not force:
            cached = self._instrument_cache.get(
                symbol
            )

            if cached is not None:
                return cached

        metadata_task = asyncio.create_task(
            self._fetch_crypto_metadata(
                symbol
            )
        )

        quote_task = asyncio.create_task(
            self._fetch_crypto_quote(
                symbol
            )
        )

        metadata, quote = await asyncio.gather(
            metadata_task,
            quote_task,
        )

        combined: dict[str, Any] = {}

        combined.update(metadata)
        combined.update(quote)

        snapshot = self._build_snapshot(
            symbol,
            combined,
            metadata=metadata,
            quote=quote,
        )

        async with self._instrument_cache_lock:
            self._instrument_cache[
                symbol
            ] = snapshot

        return snapshot

    def _build_snapshot(
        self,
        symbol: str,
        payload: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any],
        quote: Mapping[str, Any],
    ) -> CryptoInstrumentSnapshot:
        bid = safe_float(
            _first(
                payload,
                BID_KEYS,
            )
        )

        ask = safe_float(
            _first(
                payload,
                ASK_KEYS,
            )
        )

        price = safe_float(
            _first(
                payload,
                PRICE_KEYS,
            )
        )

        if price is None:
            price = _mid_price(
                bid,
                ask,
            )

        explicit_base = (
            _normalize_asset_code(
                _first(
                    payload,
                    BASE_ASSET_KEYS,
                )
            )
        )

        explicit_quote = (
            _normalize_asset_code(
                _first(
                    payload,
                    QUOTE_ASSET_KEYS,
                )
            )
        )

        parsed_base, parsed_quote = (
            _split_crypto_symbol(
                symbol
            )
        )

        base_asset = (
            explicit_base
            or parsed_base
        )

        quote_asset = (
            explicit_quote
            or parsed_quote
        )

        tradable_raw = _first(
            payload,
            (
                "tradable",
                "is_tradable",
                "tradeable",
            ),
        )

        buyable_raw = _first(
            payload,
            (
                "buyable",
                "can_buy",
            ),
        )

        sellable_raw = _first(
            payload,
            (
                "sellable",
                "can_sell",
            ),
        )

        shortable_raw = _first(
            payload,
            (
                "shortable",
                "can_short",
            ),
        )

        return CryptoInstrumentSnapshot(
            symbol=symbol,
            base_asset=base_asset,
            quote_asset=quote_asset,
            price=price,
            bid=bid,
            ask=ask,
            spread_pct=_spread_pct(
                bid,
                ask,
            ),
            open_24h=safe_float(
                _first(
                    payload,
                    OPEN_KEYS,
                )
            ),
            high_24h=safe_float(
                _first(
                    payload,
                    HIGH_KEYS,
                )
            ),
            low_24h=safe_float(
                _first(
                    payload,
                    LOW_KEYS,
                )
            ),
            change_pct=safe_float(
                _first(
                    payload,
                    CHANGE_KEYS,
                )
            ),
            volume=safe_float(
                _first(
                    payload,
                    VOLUME_KEYS,
                )
            ),
            quote_volume=safe_float(
                _first(
                    payload,
                    QUOTE_VOLUME_KEYS,
                )
            ),
            liquidity_score=safe_float(
                _first(
                    payload,
                    LIQUIDITY_KEYS,
                )
            ),
            min_order_size=safe_float(
                _first(
                    payload,
                    MIN_ORDER_KEYS,
                )
            ),
            quantity_increment=safe_float(
                _first(
                    payload,
                    QTY_INCREMENT_KEYS,
                )
            ),
            price_increment=safe_float(
                _first(
                    payload,
                    PRICE_INCREMENT_KEYS,
                )
            ),
            tradable=(
                safe_bool(
                    tradable_raw
                )
                if tradable_raw
                is not None
                else None
            ),
            buyable=(
                safe_bool(
                    buyable_raw
                )
                if buyable_raw
                is not None
                else None
            ),
            sellable=(
                safe_bool(
                    sellable_raw
                )
                if sellable_raw
                is not None
                else None
            ),
            shortable=(
                safe_bool(
                    shortable_raw
                )
                if shortable_raw
                is not None
                else None
            ),
            source=(
                str(
                    _first(
                        payload,
                        (
                            "source",
                            "provider",
                            "feed",
                        ),
                    )
                )
                if _first(
                    payload,
                    (
                        "source",
                        "provider",
                        "feed",
                    ),
                )
                is not None
                else None
            ),
            as_of=(
                str(
                    _first(
                        payload,
                        (
                            "as_of",
                            "timestamp",
                            "updated_at",
                            "time",
                        ),
                    )
                )
                if _first(
                    payload,
                    (
                        "as_of",
                        "timestamp",
                        "updated_at",
                        "time",
                    ),
                )
                is not None
                else None
            ),
            raw={
                "metadata": serialize_value(
                    metadata
                ),
                "quote": serialize_value(
                    quote
                ),
            },
        )

    # =========================================================================
    # VALIDATION
    # =========================================================================

    async def validate_crypto_instrument(
        self,
        symbol: str,
    ) -> CryptoValidationResult:
        snapshot = (
            await self.instrument_snapshot(
                symbol,
                force=True,
            )
        )

        warnings: list[str] = []

        if (
            self.require_real_market_data
            and snapshot.price is None
            and snapshot.bid is None
            and snapshot.ask is None
        ):
            self.crypto_metrics.price_blocks += 1

            return CryptoValidationResult(
                valid=False,
                reason=(
                    "No real cryptocurrency price "
                    "or quote is available"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.price is not None
            and snapshot.price
            < self.minimum_price
        ):
            self.crypto_metrics.price_blocks += 1

            return CryptoValidationResult(
                valid=False,
                reason=(
                    "Crypto price is below the "
                    "configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            self.crypto_metrics.spread_blocks += 1

            return CryptoValidationResult(
                valid=False,
                reason=(
                    "Crypto bid/ask spread exceeds "
                    f"{self.max_bid_ask_spread_pct:.4f}%"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.quote_volume is not None
            and snapshot.quote_volume
            < self.minimum_quote_volume
        ):
            self.crypto_metrics.liquidity_blocks += 1

            return CryptoValidationResult(
                valid=False,
                reason=(
                    "Crypto quote volume is below "
                    "the configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.liquidity_score is not None
            and snapshot.liquidity_score
            < self.minimum_liquidity_score
        ):
            self.crypto_metrics.liquidity_blocks += 1

            return CryptoValidationResult(
                valid=False,
                reason=(
                    "Crypto liquidity score is "
                    "below the configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            self.require_tradable_flag
            and snapshot.tradable is False
        ):
            self.crypto_metrics.tradability_blocks += 1

            return CryptoValidationResult(
                valid=False,
                reason=(
                    "Broker marks this cryptocurrency "
                    "instrument as non-tradable"
                ),
                snapshot=snapshot,
            )

        if (
            self.require_tradable_flag
            and snapshot.tradable is None
        ):
            warnings.append(
                "Provider did not return an "
                "explicit tradable flag"
            )

        if snapshot.quote_asset is None:
            warnings.append(
                "Quote asset is unavailable"
            )

        if snapshot.volume is None:
            warnings.append(
                "Base volume is unavailable"
            )

        if snapshot.quote_volume is None:
            warnings.append(
                "Quote volume is unavailable"
            )

        if snapshot.spread_pct is None:
            warnings.append(
                "Bid/ask spread is unavailable"
            )

        return CryptoValidationResult(
            valid=True,
            warnings=warnings,
            snapshot=snapshot,
        )

    async def validate_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> tuple[bool, str | None]:
        self.crypto_metrics.validations += 1

        valid, reason = (
            await super().validate_candidate(
                candidate
            )
        )

        if not valid:
            self.crypto_metrics.validation_failures += 1

            return valid, reason

        capability = (
            await self.capability_snapshot()
        )

        if not capability.get(
            "supported",
            False,
        ):
            self.crypto_metrics.validation_failures += 1

            return (
                False,
                capability.get("reason")
                or (
                    "Cryptocurrency automation "
                    "capability is unavailable"
                ),
            )

        try:
            validation = (
                await self.validate_crypto_instrument(
                    candidate.symbol
                )
            )

        except Exception as exc:
            self.crypto_metrics.validation_failures += 1

            return (
                False,
                f"Crypto validation failed: {exc}",
            )

        if not validation.valid:
            self.crypto_metrics.validation_failures += 1

            return (
                False,
                validation.reason,
            )

        if validation.snapshot is not None:
            candidate.scanner_payload[
                "crypto"
            ] = validation.snapshot.to_dict()

        if validation.warnings:
            candidate.scanner_payload[
                "crypto_warnings"
            ] = list(
                validation.warnings
            )

        return True, None

    # =========================================================================
    # CANDIDATE ENRICHMENT
    # =========================================================================

    async def prepare_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> CandidateRuntime:
        candidate = (
            await super().prepare_candidate(
                candidate
            )
        )

        snapshot = (
            self._instrument_cache.get(
                candidate.symbol
            )
        )

        if snapshot is None:
            snapshot = (
                await self.instrument_snapshot(
                    candidate.symbol,
                    force=True,
                )
            )

        candidate.scanner_payload[
            "asset_class"
        ] = self.asset_class

        candidate.scanner_payload[
            "instrument_type"
        ] = "crypto"

        candidate.scanner_payload[
            "crypto"
        ] = snapshot.to_dict()

        if snapshot.price is not None:
            candidate.scanner_payload[
                "price"
            ] = snapshot.price

        if snapshot.bid is not None:
            candidate.scanner_payload[
                "bid"
            ] = snapshot.bid

        if snapshot.ask is not None:
            candidate.scanner_payload[
                "ask"
            ] = snapshot.ask

        if snapshot.spread_pct is not None:
            candidate.scanner_payload[
                "spread_pct"
            ] = snapshot.spread_pct

        if snapshot.volume is not None:
            candidate.scanner_payload[
                "volume"
            ] = snapshot.volume

        if snapshot.quote_volume is not None:
            candidate.scanner_payload[
                "quote_volume"
            ] = snapshot.quote_volume

        if snapshot.change_pct is not None:
            candidate.scanner_payload[
                "change_pct"
            ] = snapshot.change_pct

        return candidate

    # =========================================================================
    # SCANNING
    # =========================================================================

    async def before_scan(
        self,
    ) -> None:
        capability = (
            await self.capability_snapshot()
        )

        if not capability.get(
            "supported",
            False,
        ):
            raise RuntimeError(
                capability.get("reason")
                or (
                    "Cryptocurrency capability "
                    "is unavailable"
                )
            )

    async def after_scan(
        self,
        result: Mapping[str, Any],
    ) -> None:
        candidates = result.get(
            "candidates",
            [],
        )

        await self._emit_event(
            "CRYPTO_SCAN_COMPLETED",
            message=(
                "Cryptocurrency scan completed"
            ),
            data={
                "candidate_count": (
                    len(candidates)
                    if isinstance(
                        candidates,
                        list,
                    )
                    else 0
                ),
                "universe_size": (
                    len(self.universe())
                ),
            },
        )

    async def scan_market(
        self,
    ) -> dict[str, Any]:
        await self.before_scan()

        result = (
            await super().scan_market()
        )

        candidates = result.get(
            "candidates",
            [],
        )

        validated: list[
            dict[str, Any]
        ] = []

        if isinstance(
            candidates,
            list,
        ):
            validation_tasks: list[
                tuple[
                    dict[str, Any],
                    asyncio.Task[
                        CryptoValidationResult
                    ],
                ]
            ] = []

            for raw_candidate in candidates:
                payload = _mapping(
                    raw_candidate
                )

                symbol = normalize_symbol(
                    _first(
                        payload,
                        CRYPTO_SYMBOL_KEYS,
                    )
                )

                if not symbol:
                    continue

                task = asyncio.create_task(
                    self.validate_crypto_instrument(
                        symbol
                    )
                )

                validation_tasks.append(
                    (
                        payload,
                        task,
                    )
                )

            for payload, task in validation_tasks:
                symbol = normalize_symbol(
                    _first(
                        payload,
                        CRYPTO_SYMBOL_KEYS,
                    )
                )

                try:
                    validation = await task
                except Exception as exc:
                    logger.debug(
                        "Crypto scan validation "
                        "failed for %s: %s",
                        symbol,
                        exc,
                    )

                    continue

                if not validation.valid:
                    continue

                payload["symbol"] = symbol
                payload["asset_class"] = (
                    self.asset_class
                )
                payload["instrument_type"] = (
                    "crypto"
                )

                snapshot = (
                    validation.snapshot
                )

                if snapshot is not None:
                    payload["crypto"] = (
                        snapshot.to_dict()
                    )

                    self._merge_crypto_fields(
                        payload,
                        snapshot,
                    )

                if validation.warnings:
                    payload[
                        "warnings"
                    ] = list(
                        validation.warnings
                    )

                validated.append(
                    payload
                )

        result = dict(result)

        result["candidates"] = (
            validated[
                : self.candidate_limit
            ]
        )

        result["count"] = len(
            result["candidates"]
        )

        result["asset_class"] = (
            self.asset_class
        )

        result["instrument_type"] = (
            "crypto"
        )

        await self.after_scan(
            result
        )

        return result

    def _merge_crypto_fields(
        self,
        payload: dict[str, Any],
        snapshot: CryptoInstrumentSnapshot,
    ) -> None:
        if snapshot.price is not None:
            payload.setdefault(
                "price",
                snapshot.price,
            )

        if snapshot.bid is not None:
            payload.setdefault(
                "bid",
                snapshot.bid,
            )

        if snapshot.ask is not None:
            payload.setdefault(
                "ask",
                snapshot.ask,
            )

        if snapshot.spread_pct is not None:
            payload.setdefault(
                "spread_pct",
                snapshot.spread_pct,
            )

        if snapshot.volume is not None:
            payload.setdefault(
                "volume",
                snapshot.volume,
            )

        if snapshot.quote_volume is not None:
            payload.setdefault(
                "quote_volume",
                snapshot.quote_volume,
            )

        if snapshot.change_pct is not None:
            payload.setdefault(
                "change_pct",
                snapshot.change_pct,
            )

        if snapshot.high_24h is not None:
            payload.setdefault(
                "high_24h",
                snapshot.high_24h,
            )

        if snapshot.low_24h is not None:
            payload.setdefault(
                "low_24h",
                snapshot.low_24h,
            )

        if snapshot.base_asset is not None:
            payload.setdefault(
                "base_asset",
                snapshot.base_asset,
            )

        if snapshot.quote_asset is not None:
            payload.setdefault(
                "quote_asset",
                snapshot.quote_asset,
            )

    # =========================================================================
    # EXECUTION
    # =========================================================================

    async def prepare_execution(
        self,
        candidate: CandidateRuntime,
        decision: DecisionRuntime,
    ) -> tuple[
        CandidateRuntime,
        DecisionRuntime,
    ]:
        candidate, decision = (
            await super().prepare_execution(
                candidate,
                decision,
            )
        )

        capability = (
            await self.capability_snapshot()
        )

        if not capability.get(
            "execution_supported",
            False,
        ):
            self.crypto_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Configured broker does not "
                "support cryptocurrency execution"
            )

            return candidate, decision

        snapshot = (
            self._instrument_cache.get(
                candidate.symbol
            )
        )

        if snapshot is None:
            snapshot = (
                await self.instrument_snapshot(
                    candidate.symbol,
                    force=True,
                )
            )

        if snapshot.tradable is False:
            self.crypto_metrics.tradability_blocks += 1
            self.crypto_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Broker marks the selected crypto "
                "instrument as non-tradable"
            )

            return candidate, decision

        if (
            decision.action == ACTION_BUY
            and snapshot.buyable is False
        ):
            self.crypto_metrics.buy_blocks += 1
            self.crypto_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Broker does not allow purchases "
                f"of {candidate.symbol}"
            )

            return candidate, decision

        if decision.action == ACTION_SELL:
            can_sell = (
                await self._can_sell_crypto(
                    candidate.symbol,
                    snapshot,
                )
            )

            if not can_sell:
                self.crypto_metrics.sell_blocks += 1
                self.crypto_metrics.execution_blocks += 1

                candidate.state = (
                    CANDIDATE_BLOCKED
                )

                decision.blocked = True

                decision.block_reason = (
                    "SELL decision cannot be "
                    "executed because no owned "
                    "position was confirmed and "
                    "the broker did not confirm "
                    "crypto short selling"
                )

                return candidate, decision

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            self.crypto_metrics.spread_blocks += 1
            self.crypto_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Current cryptocurrency spread "
                "exceeds the configured execution "
                "threshold"
            )

            return candidate, decision

        decision.analysis.setdefault(
            "crypto",
            snapshot.to_dict(),
        )

        decision.analysis[
            "asset_class"
        ] = self.asset_class

        decision.analysis[
            "instrument_type"
        ] = "crypto"

        decision.analysis[
            "execution_constraints"
        ] = {
            "min_order_size": (
                snapshot.min_order_size
            ),
            "quantity_increment": (
                snapshot.quantity_increment
            ),
            "price_increment": (
                snapshot.price_increment
            ),
            "base_asset": (
                snapshot.base_asset
            ),
            "quote_asset": (
                snapshot.quote_asset
            ),
            "spread_pct": (
                snapshot.spread_pct
            ),
        }

        return candidate, decision

    async def _can_sell_crypto(
        self,
        symbol: str,
        snapshot: CryptoInstrumentSnapshot,
    ) -> bool:
        if await self.has_open_position(
            symbol
        ):
            return True

        if snapshot.sellable is False:
            return False

        return snapshot.shortable is True

    async def handle_decision(
        self,
        candidate: CandidateRuntime,
        decision: DecisionRuntime,
    ) -> None:
        if decision.blocked:
            self.metrics.execution_blocks += 1

            await self._emit_event(
                "CRYPTO_EXECUTION_BLOCKED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    decision.block_reason
                    or (
                        "Cryptocurrency execution "
                        "blocked"
                    )
                ),
                data=decision.to_dict(),
            )

            return

        if decision.action == ACTION_HOLD:
            await self._emit_event(
                "CRYPTO_HOLD",
                symbol=candidate.symbol,
                message=(
                    f"{candidate.symbol} remains "
                    "under crypto monitoring"
                ),
                data={
                    "confidence": (
                        decision.confidence
                    ),
                    "strategy": (
                        decision.strategy
                    ),
                    "pattern": (
                        decision.pattern
                    ),
                    "regime": (
                        decision.regime
                    ),
                },
            )

            return

        if decision.action not in {
            ACTION_BUY,
            ACTION_SELL,
        }:
            candidate.state = (
                CANDIDATE_SKIPPED
            )

            await self._emit_event(
                "CRYPTO_DECISION_SKIPPED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    "Unsupported cryptocurrency "
                    f"decision {decision.action}"
                ),
            )

            return

        await super().handle_decision(
            candidate,
            decision,
        )

    # =========================================================================
    # POSITION MONITORING
    # =========================================================================

    async def monitor_position(
        self,
        position: Any,
    ) -> None:
        await super().monitor_position(
            position
        )

        symbol = normalize_symbol(
            getattr(
                position,
                "symbol",
                None,
            )
        )

        if not symbol:
            return

        try:
            snapshot = (
                await self.instrument_snapshot(
                    symbol,
                    force=True,
                )
            )

        except Exception as exc:
            await self._emit_event(
                "CRYPTO_POSITION_QUOTE_FAILED",
                severity="WARNING",
                symbol=symbol,
                message=str(exc),
            )

            return

        if snapshot.price is not None:
            position.current_price = (
                snapshot.price
            )

            quantity = safe_float(
                getattr(
                    position,
                    "quantity",
                    None,
                )
            )

            entry_price = safe_float(
                getattr(
                    position,
                    "entry_price",
                    None,
                )
            )

            side = str(
                getattr(
                    position,
                    "side",
                    "",
                )
                or ""
            ).strip().upper()

            if (
                quantity is not None
                and entry_price is not None
                and entry_price > 0.0
            ):
                direction = (
                    -1.0
                    if side
                    in {
                        "SHORT",
                        "SELL",
                    }
                    else 1.0
                )

                pnl = (
                    snapshot.price
                    - entry_price
                ) * quantity * direction

                pnl_pct = (
                    (
                        snapshot.price
                        - entry_price
                    )
                    / entry_price
                    * 100.0
                    * direction
                )

                position.unrealized_pl = (
                    pnl
                )

                position.unrealized_pl_pct = (
                    pnl_pct
                )

        position.raw = {
            **_mapping(
                getattr(
                    position,
                    "raw",
                    {},
                )
            ),
            "crypto": (
                snapshot.to_dict()
            ),
        }

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            await self._emit_event(
                "CRYPTO_SPREAD_WARNING",
                severity="WARNING",
                symbol=symbol,
                message=(
                    f"{symbol} spread exceeds "
                    "the configured threshold"
                ),
                data={
                    "spread_pct": (
                        snapshot.spread_pct
                    ),
                    "threshold": (
                        self.max_bid_ask_spread_pct
                    ),
                },
            )

    # =========================================================================
    # STATUS
    # =========================================================================

    def status(
        self,
        *,
        include_candidates: bool = True,
        include_positions: bool = True,
        include_decisions: bool = True,
        include_events: bool = False,
    ) -> dict[str, Any]:
        payload = super().status(
            include_candidates=(
                include_candidates
            ),
            include_positions=(
                include_positions
            ),
            include_decisions=(
                include_decisions
            ),
            include_events=(
                include_events
            ),
        )

        payload["crypto_runtime"] = {
            "metrics": (
                self.crypto_metrics.to_dict()
            ),
            "capability": (
                serialize_value(
                    self._capability_cache
                )
            ),
            "capability_checked_at": (
                self._capability_checked_at
            ),
            "cached_instruments": (
                len(
                    self._instrument_cache
                )
            ),
            "configuration": {
                "max_bid_ask_spread_pct": (
                    self.max_bid_ask_spread_pct
                ),
                "minimum_price": (
                    self.minimum_price
                ),
                "minimum_quote_volume": (
                    self.minimum_quote_volume
                ),
                "minimum_liquidity_score": (
                    self.minimum_liquidity_score
                ),
                "maximum_position_fraction": (
                    self.maximum_position_fraction
                ),
                "maximum_crypto_exposure_fraction": (
                    self.maximum_crypto_exposure_fraction
                ),
                "require_real_market_data": (
                    self.require_real_market_data
                ),
                "require_execution_capability": (
                    self.require_execution_capability
                ),
                "require_tradable_flag": (
                    self.require_tradable_flag
                ),
            },
        }

        return payload

    # =========================================================================
    # DIAGNOSTICS
    # =========================================================================

    async def diagnostics(
        self,
    ) -> dict[str, Any]:
        capability = (
            await self.capability_snapshot()
        )

        universe = self.universe()

        sample_validation: list[
            dict[str, Any]
        ] = []

        for symbol in universe[:5]:
            try:
                validation = (
                    await self.validate_crypto_instrument(
                        symbol
                    )
                )

                sample_validation.append(
                    {
                        "symbol": symbol,
                        **validation.to_dict(),
                    }
                )

            except Exception as exc:
                sample_validation.append(
                    {
                        "symbol": symbol,
                        "valid": False,
                        "reason": str(exc),
                    }
                )

        return {
            "asset_class": (
                self.asset_class
            ),
            "capability": capability,
            "universe_size": (
                len(universe)
            ),
            "sample_validation": (
                sample_validation
            ),
            "status": self.status(
                include_candidates=False,
                include_positions=False,
                include_decisions=False,
                include_events=False,
            ),
            "timestamp": _utc_now(),
        }

    async def clear_instrument_cache(
        self,
    ) -> None:
        async with self._instrument_cache_lock:
            self._instrument_cache.clear()


# =============================================================================
# SINGLETON
# =============================================================================


crypto_automation = CryptoAutomation()