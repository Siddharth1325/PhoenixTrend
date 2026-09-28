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
# FOREX CONSTANTS
# =============================================================================

FOREX_ASSET_CLASS = "forex"

DEFAULT_FOREX_SCAN_INTERVAL_SECONDS = 30.0
DEFAULT_FOREX_MONITOR_INTERVAL_SECONDS = 3.0
DEFAULT_FOREX_UNIVERSE_REFRESH_SECONDS = 300.0
DEFAULT_FOREX_CANDIDATE_LIMIT = 16

DEFAULT_HOLD_RECHECK_SECONDS = 10.0
DEFAULT_STALE_CANDIDATE_SECONDS = 180.0

DEFAULT_MAX_SPREAD_PCT = 1.0
DEFAULT_MAX_SPREAD_PIPS = 10.0
DEFAULT_MIN_PRICE = 0.000001
DEFAULT_MIN_LIQUIDITY_SCORE = 0.0

DEFAULT_MAX_POSITION_FRACTION = 0.10
DEFAULT_MAX_FOREX_EXPOSURE_FRACTION = 0.30

DEFAULT_MIN_LOT_SIZE = 0.0

FOREX_CAPABILITY_KEYS = (
    "forex",
    "fx",
    "currencies",
    "currency",
    "foreign_exchange",
    "foreign-exchange",
)

FOREX_MARKET_DATA_CAPABILITY_KEYS = (
    "forex_market_data",
    "fx_market_data",
    "currency_market_data",
    "forex_quotes",
    "fx_quotes",
)

FOREX_ORDER_CAPABILITY_KEYS = (
    "forex_orders",
    "forex_trading",
    "fx_orders",
    "fx_trading",
    "currency_orders",
    "currency_trading",
)

FOREX_SYMBOL_KEYS = (
    "symbol",
    "pair",
    "ticker",
    "instrument",
    "market",
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
    "mid_price",
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

OPEN_KEYS = (
    "open",
    "day_open",
    "session_open",
)

HIGH_KEYS = (
    "high",
    "day_high",
    "session_high",
)

LOW_KEYS = (
    "low",
    "day_low",
    "session_low",
)

PREVIOUS_CLOSE_KEYS = (
    "previous_close",
    "prev_close",
    "prior_close",
)

CHANGE_KEYS = (
    "change_pct",
    "percent_change",
    "price_change_pct",
    "day_change_pct",
)

VOLUME_KEYS = (
    "volume",
    "tick_volume",
    "day_volume",
)

LIQUIDITY_KEYS = (
    "liquidity",
    "liquidity_score",
)

BASE_CURRENCY_KEYS = (
    "base_currency",
    "base",
    "base_asset",
)

QUOTE_CURRENCY_KEYS = (
    "quote_currency",
    "quote",
    "quote_asset",
    "counter_currency",
)

PIP_SIZE_KEYS = (
    "pip_size",
    "pip",
)

PIP_VALUE_KEYS = (
    "pip_value",
)

LOT_SIZE_KEYS = (
    "lot_size",
    "contract_size",
)

MIN_ORDER_KEYS = (
    "min_order_size",
    "minimum_order",
    "minimum_quantity",
    "min_qty",
    "minimum_units",
)

QTY_INCREMENT_KEYS = (
    "quantity_increment",
    "qty_increment",
    "step_size",
    "lot_increment",
)

PRICE_INCREMENT_KEYS = (
    "price_increment",
    "tick_size",
    "minimum_price_increment",
)

TRADABLE_KEYS = (
    "tradable",
    "is_tradable",
    "tradeable",
)

BUYABLE_KEYS = (
    "buyable",
    "can_buy",
)

SELLABLE_KEYS = (
    "sellable",
    "can_sell",
)

SHORTABLE_KEYS = (
    "shortable",
    "can_short",
)

MARGINABLE_KEYS = (
    "marginable",
    "margin_eligible",
)

LEVERAGE_KEYS = (
    "leverage",
    "max_leverage",
)

SOURCE_KEYS = (
    "source",
    "provider",
    "feed",
    "data_source",
)

AS_OF_KEYS = (
    "as_of",
    "timestamp",
    "updated_at",
    "time",
)

COMMON_CURRENCIES = {
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CHF",
    "CAD",
    "AUD",
    "NZD",
    "CNY",
    "CNH",
    "HKD",
    "SGD",
    "NOK",
    "SEK",
    "DKK",
    "MXN",
    "ZAR",
    "TRY",
    "PLN",
    "CZK",
    "HUF",
    "INR",
    "BRL",
    "KRW",
}


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


def _normalize_currency(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().upper()

    if not text:
        return None

    return text


def _normalize_pair(symbol: str) -> str:
    text = str(symbol or "").strip().upper()

    if not text:
        return ""

    for separator in (
        "/",
        "-",
        "_",
        ":",
        ".",
    ):
        text = text.replace(separator, "")

    return text


def _split_forex_pair(
    symbol: str,
) -> tuple[str | None, str | None]:
    text = str(symbol or "").strip().upper()

    if not text:
        return None, None

    for separator in (
        "/",
        "-",
        "_",
        ":",
    ):
        if separator in text:
            parts = [
                part.strip()
                for part in text.split(separator)
                if part.strip()
            ]

            if len(parts) >= 2:
                return (
                    parts[0],
                    parts[1],
                )

    compact = _normalize_pair(text)

    if len(compact) == 6:
        return (
            compact[:3],
            compact[3:],
        )

    return None, None


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


def _spread_pct(
    bid: float | None,
    ask: float | None,
) -> float | None:
    midpoint = _mid_price(
        bid,
        ask,
    )

    if midpoint is None:
        return None

    return (
        (ask - bid)
        / midpoint
        * 100.0
    )


def _default_pip_size(
    quote_currency: str | None,
) -> float | None:
    if not quote_currency:
        return None

    if quote_currency.upper() == "JPY":
        return 0.01

    return 0.0001


def _spread_pips(
    bid: float | None,
    ask: float | None,
    pip_size: float | None,
) -> float | None:
    if (
        bid is None
        or ask is None
        or pip_size is None
        or pip_size <= 0.0
    ):
        return None

    if bid <= 0.0 or ask <= 0.0:
        return None

    if ask < bid:
        return None

    return (
        ask - bid
    ) / pip_size


# =============================================================================
# FOREX DOMAIN MODELS
# =============================================================================


@dataclass
class ForexInstrumentSnapshot:
    symbol: str

    base_currency: str | None = None
    quote_currency: str | None = None

    price: float | None = None
    bid: float | None = None
    ask: float | None = None

    spread_pct: float | None = None
    spread_pips: float | None = None

    pip_size: float | None = None
    pip_value: float | None = None

    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    previous_close: float | None = None
    change_pct: float | None = None

    volume: float | None = None
    liquidity_score: float | None = None

    lot_size: float | None = None
    minimum_order: float | None = None
    quantity_increment: float | None = None
    price_increment: float | None = None

    leverage: float | None = None

    tradable: bool | None = None
    buyable: bool | None = None
    sellable: bool | None = None
    shortable: bool | None = None
    marginable: bool | None = None

    source: str | None = None
    as_of: str | None = None

    raw: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            {
                "symbol": self.symbol,
                "base_currency": self.base_currency,
                "quote_currency": self.quote_currency,
                "price": self.price,
                "bid": self.bid,
                "ask": self.ask,
                "spread_pct": self.spread_pct,
                "spread_pips": self.spread_pips,
                "pip_size": self.pip_size,
                "pip_value": self.pip_value,
                "open_price": self.open_price,
                "high_price": self.high_price,
                "low_price": self.low_price,
                "previous_close": self.previous_close,
                "change_pct": self.change_pct,
                "volume": self.volume,
                "liquidity_score": self.liquidity_score,
                "lot_size": self.lot_size,
                "minimum_order": self.minimum_order,
                "quantity_increment": self.quantity_increment,
                "price_increment": self.price_increment,
                "leverage": self.leverage,
                "tradable": self.tradable,
                "buyable": self.buyable,
                "sellable": self.sellable,
                "shortable": self.shortable,
                "marginable": self.marginable,
                "source": self.source,
                "as_of": self.as_of,
                "raw": self.raw,
            }
        )


@dataclass
class ForexValidationResult:
    valid: bool

    reason: str | None = None

    warnings: list[str] = field(
        default_factory=list
    )

    snapshot: ForexInstrumentSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            {
                "valid": self.valid,
                "reason": self.reason,
                "warnings": list(
                    self.warnings
                ),
                "snapshot": (
                    self.snapshot.to_dict()
                    if self.snapshot
                    is not None
                    else None
                ),
            }
        )


@dataclass
class ForexRuntimeMetrics:
    capability_checks: int = 0
    capability_blocks: int = 0

    metadata_requests: int = 0
    metadata_failures: int = 0

    quote_requests: int = 0
    quote_failures: int = 0

    validations: int = 0
    validation_failures: int = 0

    invalid_pair_blocks: int = 0
    price_blocks: int = 0
    spread_blocks: int = 0
    liquidity_blocks: int = 0
    tradability_blocks: int = 0

    buy_blocks: int = 0
    sell_blocks: int = 0
    short_blocks: int = 0

    execution_blocks: int = 0

    position_quote_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            self.__dict__
        )


# =============================================================================
# FOREX AUTOMATION
# =============================================================================


class ForexAutomation(BaseAssetAutomation):
    """
    PhoenixTrend foreign-exchange automation runtime.

    The shared BaseAssetAutomation owns the common intelligence pipeline.
    This runtime adds forex-specific capability gating, pair validation,
    quote/spread/pip validation, execution constraints and live position
    enrichment.

    Forex remains unavailable when the configured broker or market-data
    provider does not expose the required forex capabilities. The runtime
    never manufactures currency pairs, quotes, liquidity, pip values,
    leverage or execution support.
    """

    asset_class = FOREX_ASSET_CLASS

    scan_interval_seconds = (
        DEFAULT_FOREX_SCAN_INTERVAL_SECONDS
    )

    monitor_interval_seconds = (
        DEFAULT_FOREX_MONITOR_INTERVAL_SECONDS
    )

    universe_refresh_seconds = (
        DEFAULT_FOREX_UNIVERSE_REFRESH_SECONDS
    )

    candidate_limit = (
        DEFAULT_FOREX_CANDIDATE_LIMIT
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

    max_bid_ask_spread_pips = (
        DEFAULT_MAX_SPREAD_PIPS
    )

    minimum_price = (
        DEFAULT_MIN_PRICE
    )

    minimum_liquidity_score = (
        DEFAULT_MIN_LIQUIDITY_SCORE
    )

    minimum_lot_size = (
        DEFAULT_MIN_LOT_SIZE
    )

    maximum_position_fraction = (
        DEFAULT_MAX_POSITION_FRACTION
    )

    maximum_forex_exposure_fraction = (
        DEFAULT_MAX_FOREX_EXPOSURE_FRACTION
    )

    require_real_market_data = True
    require_execution_capability = True
    require_tradable_flag = True

    allow_automatic_entries = True

    preserve_position_monitoring_when_disabled = True

    def __init__(self) -> None:
        super().__init__()

        self.forex_metrics = (
            ForexRuntimeMetrics()
        )

        self._instrument_cache: dict[
            str,
            ForexInstrumentSnapshot,
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

    def _broker_service(
        self,
    ) -> Any | None:
        return self._resolve_service(
            "backend.app.broker",
            (
                "alpaca_broker",
                "broker",
                "broker_service",
                "broker_client",
            ),
        )

    def _market_service(
        self,
    ) -> Any | None:
        return self._resolve_service(
            "backend.app.services.market",
            (
                "market_service",
                "market",
            ),
        )

    def _live_market_service(
        self,
    ) -> Any | None:
        return self._resolve_service(
            "backend.app.services.live_market",
            (
                "live_market_service",
                "live_market",
            ),
        )

    # =========================================================================
    # CAPABILITY GATING
    # =========================================================================

    async def capability_snapshot(
        self,
    ) -> dict[str, Any]:
        self.forex_metrics.capability_checks += 1

        base = (
            await super().capability_snapshot()
        )

        if not base.get(
            "supported",
            False,
        ):
            self.forex_metrics.capability_blocks += 1

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
                        "advertise forex support"
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

        general_forex_support = (
            self._capability_value(
                broker_capabilities,
                FOREX_CAPABILITY_KEYS,
            )
        )

        market_data_supported = (
            self._capability_value(
                broker_capabilities,
                FOREX_MARKET_DATA_CAPABILITY_KEYS,
            )
        )

        execution_supported = (
            self._capability_value(
                broker_capabilities,
                FOREX_ORDER_CAPABILITY_KEYS,
            )
        )

        if market_data_supported is None:
            market_data_supported = (
                general_forex_support
            )

        if execution_supported is None:
            execution_supported = (
                general_forex_support
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
                "expose forex market data"
            )

        elif (
            self.require_execution_capability
            and not execution_supported
        ):
            supported = False

            reason = (
                "Configured broker does not "
                "support forex order execution"
            )

        if not supported:
            self.forex_metrics.capability_blocks += 1

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
            "general_forex_support": (
                general_forex_support
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

                return _mapping(
                    result
                )

            except Exception as exc:
                logger.debug(
                    "Forex capability call failed "
                    "using %s: %s",
                    method_name,
                    exc,
                )

        raw = getattr(
            broker,
            "capabilities",
            None,
        )

        if isinstance(
            raw,
            Mapping,
        ):
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

            value = normalized[
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

            return safe_bool(
                value
            )

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

                return safe_bool(
                    value
                )

        return None

    # =========================================================================
    # UNIVERSE
    # =========================================================================

    async def filter_universe(
        self,
        symbols: list[str],
    ) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for raw_symbol in symbols:
            symbol = normalize_symbol(
                raw_symbol
            )

            if not symbol:
                continue

            base, quote = (
                _split_forex_pair(
                    symbol
                )
            )

            if (
                base is None
                or quote is None
            ):
                continue

            if base == quote:
                continue

            canonical = (
                f"{base}/{quote}"
            )

            if canonical in seen:
                continue

            seen.add(
                canonical
            )

            result.append(
                canonical
            )

        return result

    # =========================================================================
    # PROVIDER INVOCATION
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

            if not callable(
                method
            ):
                continue

            variants = [
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

            for args, kwargs in variants:
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
                        "Forex service call "
                        "%s.%s failed for %s: %s",
                        service.__class__.__name__,
                        method_name,
                        symbol,
                        exc,
                    )

                    break

        return None

    # =========================================================================
    # METADATA
    # =========================================================================

    async def _fetch_forex_metadata(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        self.forex_metrics.metadata_requests += 1

        broker = (
            self._broker_service()
        )

        if broker is not None:
            result = (
                await self._try_service_methods(
                    broker,
                    (
                        "get_forex_instrument",
                        "forex_instrument",
                        "get_fx_instrument",
                        "fx_instrument",
                        "get_currency_pair",
                        "currency_pair",
                        "get_asset",
                        "asset",
                        "instrument",
                    ),
                    symbol,
                    asset_class=self.asset_class,
                )
            )

            if result is not None:
                return _mapping(
                    result
                )

        market = (
            self._market_service()
        )

        if market is not None:
            result = (
                await self._try_service_methods(
                    market,
                    (
                        "forex_metadata",
                        "fx_metadata",
                        "currency_pair",
                        "instrument",
                        "asset",
                    ),
                    symbol,
                    asset_class=self.asset_class,
                )
            )

            if result is not None:
                return _mapping(
                    result
                )

        self.forex_metrics.metadata_failures += 1

        return {}

    # =========================================================================
    # QUOTES
    # =========================================================================

    async def _fetch_forex_quote(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        self.forex_metrics.quote_requests += 1

        live_market = (
            self._live_market_service()
        )

        if live_market is not None:
            result = (
                await self._try_service_methods(
                    live_market,
                    (
                        "forex_snapshot",
                        "fx_snapshot",
                        "forex_quote",
                        "fx_quote",
                        "latest_quote",
                        "quote",
                        "get_quote",
                    ),
                    symbol,
                    asset_class=self.asset_class,
                )
            )

            if result is not None:
                payload = _mapping(
                    result
                )

                if payload:
                    return payload

        market = (
            self._market_service()
        )

        if market is not None:
            result = (
                await self._try_service_methods(
                    market,
                    (
                        "forex_snapshot",
                        "fx_snapshot",
                        "forex_quote",
                        "fx_quote",
                        "latest_quote",
                        "quote",
                        "get_quote",
                    ),
                    symbol,
                    asset_class=self.asset_class,
                )
            )

            if result is not None:
                payload = _mapping(
                    result
                )

                if payload:
                    return payload

        broker = (
            self._broker_service()
        )

        if broker is not None:
            result = (
                await self._try_service_methods(
                    broker,
                    (
                        "get_forex_quote",
                        "forex_quote",
                        "get_fx_quote",
                        "fx_quote",
                        "get_quote",
                        "quote",
                    ),
                    symbol,
                    asset_class=self.asset_class,
                )
            )

            if result is not None:
                payload = _mapping(
                    result
                )

                if payload:
                    return payload

        self.forex_metrics.quote_failures += 1

        return {}

    # =========================================================================
    # SNAPSHOT
    # =========================================================================

    async def instrument_snapshot(
        self,
        symbol: str,
        *,
        force: bool = False,
    ) -> ForexInstrumentSnapshot:
        symbol = normalize_symbol(
            symbol
        )

        if not symbol:
            raise ValueError(
                "Forex symbol is required"
            )

        base_from_symbol, quote_from_symbol = (
            _split_forex_pair(
                symbol
            )
        )

        if (
            base_from_symbol is None
            or quote_from_symbol is None
        ):
            raise ValueError(
                f"Invalid forex pair: {symbol}"
            )

        canonical_symbol = (
            f"{base_from_symbol}/{quote_from_symbol}"
        )

        if not force:
            cached = (
                self._instrument_cache.get(
                    canonical_symbol
                )
            )

            if cached is not None:
                return cached

        metadata_task = asyncio.create_task(
            self._fetch_forex_metadata(
                canonical_symbol
            )
        )

        quote_task = asyncio.create_task(
            self._fetch_forex_quote(
                canonical_symbol
            )
        )

        metadata, quote = (
            await asyncio.gather(
                metadata_task,
                quote_task,
            )
        )

        combined: dict[str, Any] = {}

        combined.update(
            metadata
        )

        combined.update(
            quote
        )

        snapshot = (
            self._build_snapshot(
                canonical_symbol,
                combined,
                metadata=metadata,
                quote=quote,
            )
        )

        async with self._instrument_cache_lock:
            self._instrument_cache[
                canonical_symbol
            ] = snapshot

        return snapshot

    def _build_snapshot(
        self,
        symbol: str,
        payload: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any],
        quote: Mapping[str, Any],
    ) -> ForexInstrumentSnapshot:
        parsed_base, parsed_quote = (
            _split_forex_pair(
                symbol
            )
        )

        explicit_base = (
            _normalize_currency(
                _first(
                    payload,
                    BASE_CURRENCY_KEYS,
                )
            )
        )

        explicit_quote = (
            _normalize_currency(
                _first(
                    payload,
                    QUOTE_CURRENCY_KEYS,
                )
            )
        )

        base_currency = (
            explicit_base
            or parsed_base
        )

        quote_currency = (
            explicit_quote
            or parsed_quote
        )

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

        pip_size = safe_float(
            _first(
                payload,
                PIP_SIZE_KEYS,
            )
        )

        if pip_size is None:
            pip_size = (
                _default_pip_size(
                    quote_currency
                )
            )

        tradable_raw = (
            _first(
                payload,
                TRADABLE_KEYS,
            )
        )

        buyable_raw = (
            _first(
                payload,
                BUYABLE_KEYS,
            )
        )

        sellable_raw = (
            _first(
                payload,
                SELLABLE_KEYS,
            )
        )

        shortable_raw = (
            _first(
                payload,
                SHORTABLE_KEYS,
            )
        )

        marginable_raw = (
            _first(
                payload,
                MARGINABLE_KEYS,
            )
        )

        source = _first(
            payload,
            SOURCE_KEYS,
        )

        as_of = _first(
            payload,
            AS_OF_KEYS,
        )

        return ForexInstrumentSnapshot(
            symbol=symbol,
            base_currency=base_currency,
            quote_currency=quote_currency,
            price=price,
            bid=bid,
            ask=ask,
            spread_pct=_spread_pct(
                bid,
                ask,
            ),
            spread_pips=_spread_pips(
                bid,
                ask,
                pip_size,
            ),
            pip_size=pip_size,
            pip_value=safe_float(
                _first(
                    payload,
                    PIP_VALUE_KEYS,
                )
            ),
            open_price=safe_float(
                _first(
                    payload,
                    OPEN_KEYS,
                )
            ),
            high_price=safe_float(
                _first(
                    payload,
                    HIGH_KEYS,
                )
            ),
            low_price=safe_float(
                _first(
                    payload,
                    LOW_KEYS,
                )
            ),
            previous_close=safe_float(
                _first(
                    payload,
                    PREVIOUS_CLOSE_KEYS,
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
            liquidity_score=safe_float(
                _first(
                    payload,
                    LIQUIDITY_KEYS,
                )
            ),
            lot_size=safe_float(
                _first(
                    payload,
                    LOT_SIZE_KEYS,
                )
            ),
            minimum_order=safe_float(
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
            leverage=safe_float(
                _first(
                    payload,
                    LEVERAGE_KEYS,
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
            marginable=(
                safe_bool(
                    marginable_raw
                )
                if marginable_raw
                is not None
                else None
            ),
            source=(
                str(source)
                if source is not None
                else None
            ),
            as_of=(
                str(as_of)
                if as_of is not None
                else None
            ),
            raw={
                "metadata": (
                    serialize_value(
                        metadata
                    )
                ),
                "quote": (
                    serialize_value(
                        quote
                    )
                ),
            },
        )

    # =========================================================================
    # VALIDATION
    # =========================================================================

    async def validate_forex_instrument(
        self,
        symbol: str,
    ) -> ForexValidationResult:
        self.forex_metrics.validations += 1

        base, quote = (
            _split_forex_pair(
                symbol
            )
        )

        if (
            base is None
            or quote is None
            or base == quote
        ):
            self.forex_metrics.invalid_pair_blocks += 1
            self.forex_metrics.validation_failures += 1

            return ForexValidationResult(
                valid=False,
                reason=(
                    "Invalid forex currency pair"
                ),
            )

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
            self.forex_metrics.price_blocks += 1
            self.forex_metrics.validation_failures += 1

            return ForexValidationResult(
                valid=False,
                reason=(
                    "No real forex price or "
                    "quote is available"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.price is not None
            and snapshot.price
            < self.minimum_price
        ):
            self.forex_metrics.price_blocks += 1
            self.forex_metrics.validation_failures += 1

            return ForexValidationResult(
                valid=False,
                reason=(
                    "Forex price is below the "
                    "configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            self.forex_metrics.spread_blocks += 1
            self.forex_metrics.validation_failures += 1

            return ForexValidationResult(
                valid=False,
                reason=(
                    "Forex bid/ask spread exceeds "
                    f"{self.max_bid_ask_spread_pct:.4f}%"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.spread_pips is not None
            and snapshot.spread_pips
            > self.max_bid_ask_spread_pips
        ):
            self.forex_metrics.spread_blocks += 1
            self.forex_metrics.validation_failures += 1

            return ForexValidationResult(
                valid=False,
                reason=(
                    "Forex spread exceeds "
                    f"{self.max_bid_ask_spread_pips:.4f} pips"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.liquidity_score is not None
            and snapshot.liquidity_score
            < self.minimum_liquidity_score
        ):
            self.forex_metrics.liquidity_blocks += 1
            self.forex_metrics.validation_failures += 1

            return ForexValidationResult(
                valid=False,
                reason=(
                    "Forex liquidity score is below "
                    "the configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            self.require_tradable_flag
            and snapshot.tradable is False
        ):
            self.forex_metrics.tradability_blocks += 1
            self.forex_metrics.validation_failures += 1

            return ForexValidationResult(
                valid=False,
                reason=(
                    "Broker marks this forex pair "
                    "as non-tradable"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.lot_size is not None
            and snapshot.lot_size
            < self.minimum_lot_size
        ):
            self.forex_metrics.validation_failures += 1

            return ForexValidationResult(
                valid=False,
                reason=(
                    "Forex lot size is below the "
                    "configured minimum"
                ),
                snapshot=snapshot,
            )

        if snapshot.tradable is None:
            warnings.append(
                "Provider did not return an "
                "explicit tradable flag"
            )

        if snapshot.bid is None:
            warnings.append(
                "Forex bid is unavailable"
            )

        if snapshot.ask is None:
            warnings.append(
                "Forex ask is unavailable"
            )

        if snapshot.spread_pips is None:
            warnings.append(
                "Forex spread in pips is unavailable"
            )

        if snapshot.pip_value is None:
            warnings.append(
                "Provider did not return pip value"
            )

        if snapshot.liquidity_score is None:
            warnings.append(
                "Forex liquidity score is unavailable"
            )

        return ForexValidationResult(
            valid=True,
            warnings=warnings,
            snapshot=snapshot,
        )

    async def validate_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> tuple[
        bool,
        str | None,
    ]:
        valid, reason = (
            await super().validate_candidate(
                candidate
            )
        )

        if not valid:
            self.forex_metrics.validation_failures += 1

            return (
                valid,
                reason,
            )

        capability = (
            await self.capability_snapshot()
        )

        if not capability.get(
            "supported",
            False,
        ):
            self.forex_metrics.validation_failures += 1

            return (
                False,
                capability.get(
                    "reason"
                )
                or (
                    "Forex automation capability "
                    "is unavailable"
                ),
            )

        try:
            validation = (
                await self.validate_forex_instrument(
                    candidate.symbol
                )
            )

        except Exception as exc:
            self.forex_metrics.validation_failures += 1

            return (
                False,
                f"Forex validation failed: {exc}",
            )

        if not validation.valid:
            return (
                False,
                validation.reason,
            )

        if validation.snapshot is not None:
            candidate.scanner_payload[
                "forex"
            ] = (
                validation.snapshot.to_dict()
            )

        if validation.warnings:
            candidate.scanner_payload[
                "forex_warnings"
            ] = list(
                validation.warnings
            )

        return (
            True,
            None,
        )

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

        base, quote = (
            _split_forex_pair(
                candidate.symbol
            )
        )

        if (
            base is None
            or quote is None
        ):
            candidate.state = (
                CANDIDATE_BLOCKED
            )

            return candidate

        canonical = (
            f"{base}/{quote}"
        )

        snapshot = (
            self._instrument_cache.get(
                canonical
            )
        )

        if snapshot is None:
            snapshot = (
                await self.instrument_snapshot(
                    canonical,
                    force=True,
                )
            )

        candidate.scanner_payload[
            "asset_class"
        ] = self.asset_class

        candidate.scanner_payload[
            "instrument_type"
        ] = "forex"

        candidate.scanner_payload[
            "symbol"
        ] = canonical

        candidate.scanner_payload[
            "forex"
        ] = snapshot.to_dict()

        self._merge_forex_fields(
            candidate.scanner_payload,
            snapshot,
        )

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
                capability.get(
                    "reason"
                )
                or (
                    "Forex capability "
                    "is unavailable"
                )
            )

    async def after_scan(
        self,
        result: Mapping[str, Any],
    ) -> None:
        candidates = (
            result.get(
                "candidates",
                [],
            )
        )

        await self._emit_event(
            "FOREX_SCAN_COMPLETED",
            message=(
                "Forex scan completed"
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
                    len(
                        self.universe()
                    )
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

        candidates = (
            result.get(
                "candidates",
                [],
            )
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
                        ForexValidationResult
                    ],
                ]
            ] = []

            for raw_candidate in candidates:
                payload = _mapping(
                    raw_candidate
                )

                raw_symbol = (
                    _first(
                        payload,
                        FOREX_SYMBOL_KEYS,
                    )
                )

                symbol = (
                    normalize_symbol(
                        raw_symbol
                    )
                )

                if not symbol:
                    continue

                base, quote = (
                    _split_forex_pair(
                        symbol
                    )
                )

                if (
                    base is None
                    or quote is None
                ):
                    continue

                canonical = (
                    f"{base}/{quote}"
                )

                task = (
                    asyncio.create_task(
                        self.validate_forex_instrument(
                            canonical
                        )
                    )
                )

                validation_tasks.append(
                    (
                        payload,
                        task,
                    )
                )

            for payload, task in validation_tasks:
                raw_symbol = (
                    _first(
                        payload,
                        FOREX_SYMBOL_KEYS,
                    )
                )

                symbol = (
                    normalize_symbol(
                        raw_symbol
                    )
                )

                base, quote = (
                    _split_forex_pair(
                        symbol
                    )
                )

                if (
                    base is None
                    or quote is None
                ):
                    continue

                canonical = (
                    f"{base}/{quote}"
                )

                try:
                    validation = (
                        await task
                    )

                except Exception as exc:
                    logger.debug(
                        "Forex scan validation "
                        "failed for %s: %s",
                        canonical,
                        exc,
                    )

                    continue

                if not validation.valid:
                    continue

                payload[
                    "symbol"
                ] = canonical

                payload[
                    "asset_class"
                ] = self.asset_class

                payload[
                    "instrument_type"
                ] = "forex"

                snapshot = (
                    validation.snapshot
                )

                if snapshot is not None:
                    payload[
                        "forex"
                    ] = snapshot.to_dict()

                    self._merge_forex_fields(
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

        result = dict(
            result
        )

        result[
            "candidates"
        ] = validated[
            : self.candidate_limit
        ]

        result[
            "count"
        ] = len(
            result[
                "candidates"
            ]
        )

        result[
            "asset_class"
        ] = self.asset_class

        result[
            "instrument_type"
        ] = "forex"

        await self.after_scan(
            result
        )

        return result

    def _merge_forex_fields(
        self,
        payload: dict[str, Any],
        snapshot: ForexInstrumentSnapshot,
    ) -> None:
        payload.setdefault(
            "base_currency",
            snapshot.base_currency,
        )

        payload.setdefault(
            "quote_currency",
            snapshot.quote_currency,
        )

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

        if snapshot.spread_pips is not None:
            payload.setdefault(
                "spread_pips",
                snapshot.spread_pips,
            )

        if snapshot.pip_size is not None:
            payload.setdefault(
                "pip_size",
                snapshot.pip_size,
            )

        if snapshot.pip_value is not None:
            payload.setdefault(
                "pip_value",
                snapshot.pip_value,
            )

        if snapshot.volume is not None:
            payload.setdefault(
                "volume",
                snapshot.volume,
            )

        if snapshot.change_pct is not None:
            payload.setdefault(
                "change_pct",
                snapshot.change_pct,
            )

        if snapshot.liquidity_score is not None:
            payload.setdefault(
                "liquidity_score",
                snapshot.liquidity_score,
            )

        if snapshot.leverage is not None:
            payload.setdefault(
                "leverage",
                snapshot.leverage,
            )

    # =========================================================================
    # EXECUTION VALIDATION
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
            self.forex_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Configured broker does not "
                "support forex execution"
            )

            return (
                candidate,
                decision,
            )

        base, quote = (
            _split_forex_pair(
                candidate.symbol
            )
        )

        if (
            base is None
            or quote is None
        ):
            self.forex_metrics.invalid_pair_blocks += 1
            self.forex_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Invalid forex currency pair"
            )

            return (
                candidate,
                decision,
            )

        canonical = (
            f"{base}/{quote}"
        )

        snapshot = (
            self._instrument_cache.get(
                canonical
            )
        )

        if snapshot is None:
            snapshot = (
                await self.instrument_snapshot(
                    canonical,
                    force=True,
                )
            )

        if snapshot.tradable is False:
            self.forex_metrics.tradability_blocks += 1
            self.forex_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Broker marks the selected "
                "forex pair as non-tradable"
            )

            return (
                candidate,
                decision,
            )

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            self.forex_metrics.spread_blocks += 1
            self.forex_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Current forex spread exceeds "
                "the configured percentage threshold"
            )

            return (
                candidate,
                decision,
            )

        if (
            snapshot.spread_pips is not None
            and snapshot.spread_pips
            > self.max_bid_ask_spread_pips
        ):
            self.forex_metrics.spread_blocks += 1
            self.forex_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Current forex spread exceeds "
                "the configured pip threshold"
            )

            return (
                candidate,
                decision,
            )

        if (
            decision.action == ACTION_BUY
            and snapshot.buyable is False
        ):
            self.forex_metrics.buy_blocks += 1
            self.forex_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Broker does not allow BUY "
                f"orders for {canonical}"
            )

            return (
                candidate,
                decision,
            )

        if (
            decision.action == ACTION_SELL
        ):
            can_sell = (
                await self._can_sell_forex(
                    canonical,
                    snapshot,
                )
            )

            if not can_sell:
                self.forex_metrics.sell_blocks += 1
                self.forex_metrics.short_blocks += 1
                self.forex_metrics.execution_blocks += 1

                candidate.state = (
                    CANDIDATE_BLOCKED
                )

                decision.blocked = True

                decision.block_reason = (
                    "SELL decision cannot be executed "
                    "because no owned/open forex "
                    "position was confirmed and the "
                    "broker did not confirm short-side "
                    "execution support"
                )

                return (
                    candidate,
                    decision,
                )

        decision.analysis.setdefault(
            "forex",
            snapshot.to_dict(),
        )

        decision.analysis[
            "asset_class"
        ] = self.asset_class

        decision.analysis[
            "instrument_type"
        ] = "forex"

        decision.analysis[
            "execution_constraints"
        ] = {
            "base_currency": (
                snapshot.base_currency
            ),
            "quote_currency": (
                snapshot.quote_currency
            ),
            "pip_size": (
                snapshot.pip_size
            ),
            "pip_value": (
                snapshot.pip_value
            ),
            "lot_size": (
                snapshot.lot_size
            ),
            "minimum_order": (
                snapshot.minimum_order
            ),
            "quantity_increment": (
                snapshot.quantity_increment
            ),
            "price_increment": (
                snapshot.price_increment
            ),
            "spread_pct": (
                snapshot.spread_pct
            ),
            "spread_pips": (
                snapshot.spread_pips
            ),
            "leverage": (
                snapshot.leverage
            ),
            "marginable": (
                snapshot.marginable
            ),
            "maximum_position_fraction": (
                self.maximum_position_fraction
            ),
            "maximum_forex_exposure_fraction": (
                self.maximum_forex_exposure_fraction
            ),
        }

        return (
            candidate,
            decision,
        )

    async def _can_sell_forex(
        self,
        symbol: str,
        snapshot: ForexInstrumentSnapshot,
    ) -> bool:
        if await self.has_open_position(
            symbol
        ):
            return True

        if snapshot.sellable is False:
            return False

        return (
            snapshot.shortable is True
        )

    # =========================================================================
    # DECISION HANDLING
    # =========================================================================

    async def handle_decision(
        self,
        candidate: CandidateRuntime,
        decision: DecisionRuntime,
    ) -> None:
        if decision.blocked:
            self.metrics.execution_blocks += 1

            await self._emit_event(
                "FOREX_EXECUTION_BLOCKED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    decision.block_reason
                    or (
                        "Forex execution blocked"
                    )
                ),
                data=(
                    decision.to_dict()
                ),
            )

            return

        if (
            decision.action
            == ACTION_HOLD
        ):
            await self._emit_event(
                "FOREX_HOLD",
                symbol=candidate.symbol,
                message=(
                    f"{candidate.symbol} remains "
                    "under forex monitoring"
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
                "FOREX_DECISION_SKIPPED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    "Unsupported forex decision "
                    f"{decision.action}"
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

        raw_symbol = (
            getattr(
                position,
                "symbol",
                None,
            )
        )

        symbol = normalize_symbol(
            raw_symbol
        )

        if not symbol:
            return

        base, quote = (
            _split_forex_pair(
                symbol
            )
        )

        if (
            base is None
            or quote is None
        ):
            await self._emit_event(
                "FOREX_POSITION_INVALID_PAIR",
                severity="WARNING",
                symbol=symbol,
                message=(
                    "Position contains an invalid "
                    "forex currency pair"
                ),
            )

            return

        canonical = (
            f"{base}/{quote}"
        )

        try:
            snapshot = (
                await self.instrument_snapshot(
                    canonical,
                    force=True,
                )
            )

        except Exception as exc:
            self.forex_metrics.position_quote_failures += 1

            await self._emit_event(
                "FOREX_POSITION_QUOTE_FAILED",
                severity="WARNING",
                symbol=canonical,
                message=str(
                    exc
                ),
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

                price_delta = (
                    snapshot.price
                    - entry_price
                )

                pnl = (
                    price_delta
                    * quantity
                    * direction
                )

                pnl_pct = (
                    price_delta
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

                if (
                    snapshot.pip_size
                    is not None
                    and snapshot.pip_size
                    > 0.0
                ):
                    pip_change = (
                        price_delta
                        / snapshot.pip_size
                        * direction
                    )

                    raw = _mapping(
                        getattr(
                            position,
                            "raw",
                            {},
                        )
                    )

                    raw[
                        "unrealized_pips"
                    ] = pip_change

                    position.raw = raw

        position.raw = {
            **_mapping(
                getattr(
                    position,
                    "raw",
                    {},
                )
            ),
            "forex": (
                snapshot.to_dict()
            ),
        }

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            await self._emit_event(
                "FOREX_SPREAD_WARNING",
                severity="WARNING",
                symbol=canonical,
                message=(
                    f"{canonical} spread exceeds "
                    "the configured percentage threshold"
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

        if (
            snapshot.spread_pips is not None
            and snapshot.spread_pips
            > self.max_bid_ask_spread_pips
        ):
            await self._emit_event(
                "FOREX_PIP_SPREAD_WARNING",
                severity="WARNING",
                symbol=canonical,
                message=(
                    f"{canonical} spread exceeds "
                    "the configured pip threshold"
                ),
                data={
                    "spread_pips": (
                        snapshot.spread_pips
                    ),
                    "threshold": (
                        self.max_bid_ask_spread_pips
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
        payload = (
            super().status(
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
        )

        payload[
            "forex_runtime"
        ] = {
            "metrics": (
                self.forex_metrics.to_dict()
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
                "max_bid_ask_spread_pips": (
                    self.max_bid_ask_spread_pips
                ),
                "minimum_price": (
                    self.minimum_price
                ),
                "minimum_liquidity_score": (
                    self.minimum_liquidity_score
                ),
                "minimum_lot_size": (
                    self.minimum_lot_size
                ),
                "maximum_position_fraction": (
                    self.maximum_position_fraction
                ),
                "maximum_forex_exposure_fraction": (
                    self.maximum_forex_exposure_fraction
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

        raw_universe = (
            self.universe()
        )

        universe = (
            await self.filter_universe(
                raw_universe
            )
        )

        sample_validation: list[
            dict[str, Any]
        ] = []

        for symbol in universe[:5]:
            try:
                validation = (
                    await self.validate_forex_instrument(
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
                        "reason": str(
                            exc
                        ),
                    }
                )

        return {
            "asset_class": (
                self.asset_class
            ),
            "capability": (
                capability
            ),
            "universe_size": (
                len(
                    universe
                )
            ),
            "sample_validation": (
                sample_validation
            ),
            "status": (
                self.status(
                    include_candidates=False,
                    include_positions=False,
                    include_decisions=False,
                    include_events=False,
                )
            ),
            "timestamp": (
                _utc_now()
            ),
        }

    async def clear_instrument_cache(
        self,
    ) -> None:
        async with self._instrument_cache_lock:
            self._instrument_cache.clear()


# =============================================================================
# SINGLETON
# =============================================================================


forex_automation = ForexAutomation()