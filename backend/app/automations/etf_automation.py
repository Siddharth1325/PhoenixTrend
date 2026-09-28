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
# ETF CONSTANTS
# =============================================================================

ETF_ASSET_CLASS = "etfs"

DEFAULT_ETF_SCAN_INTERVAL_SECONDS = 45.0
DEFAULT_ETF_MONITOR_INTERVAL_SECONDS = 5.0
DEFAULT_ETF_UNIVERSE_REFRESH_SECONDS = 600.0
DEFAULT_ETF_CANDIDATE_LIMIT = 16

DEFAULT_MAX_SPREAD_PCT = 1.50
DEFAULT_MIN_PRICE = 0.01
DEFAULT_MAX_PRICE = 1_000_000.0
DEFAULT_MIN_AVERAGE_VOLUME = 0.0
DEFAULT_MIN_DOLLAR_VOLUME = 0.0
DEFAULT_MIN_LIQUIDITY_SCORE = 0.0

DEFAULT_MAX_POSITION_FRACTION = 0.20
DEFAULT_MAX_ETF_EXPOSURE_FRACTION = 0.60

DEFAULT_HOLD_RECHECK_SECONDS = 20.0
DEFAULT_STALE_CANDIDATE_SECONDS = 600.0

ETF_CAPABILITY_KEYS = (
    "etf",
    "etfs",
    "fund",
    "funds",
    "equity",
    "equities",
    "stocks",
)

ETF_MARKET_DATA_CAPABILITY_KEYS = (
    "etf_market_data",
    "fund_market_data",
    "equity_market_data",
    "stock_market_data",
    "market_data",
)

ETF_ORDER_CAPABILITY_KEYS = (
    "etf_orders",
    "etf_trading",
    "fund_orders",
    "equity_orders",
    "stock_orders",
    "equity_trading",
)

ETF_SYMBOL_KEYS = (
    "symbol",
    "ticker",
    "code",
    "asset",
    "instrument",
)

ETF_PRICE_KEYS = (
    "price",
    "last",
    "last_price",
    "current_price",
    "market_price",
    "mark",
    "mid",
)

ETF_BID_KEYS = (
    "bid",
    "bid_price",
    "best_bid",
)

ETF_ASK_KEYS = (
    "ask",
    "ask_price",
    "best_ask",
)

ETF_VOLUME_KEYS = (
    "volume",
    "daily_volume",
    "day_volume",
)

ETF_AVERAGE_VOLUME_KEYS = (
    "average_volume",
    "avg_volume",
    "average_daily_volume",
    "avg_daily_volume",
)

ETF_DOLLAR_VOLUME_KEYS = (
    "dollar_volume",
    "notional_volume",
    "average_dollar_volume",
)

ETF_CHANGE_KEYS = (
    "change_pct",
    "percent_change",
    "price_change_pct",
    "day_change_pct",
)

ETF_OPEN_KEYS = (
    "open",
    "day_open",
)

ETF_HIGH_KEYS = (
    "high",
    "day_high",
)

ETF_LOW_KEYS = (
    "low",
    "day_low",
)

ETF_PREVIOUS_CLOSE_KEYS = (
    "previous_close",
    "prev_close",
    "prior_close",
)

ETF_LIQUIDITY_KEYS = (
    "liquidity",
    "liquidity_score",
)

ETF_NAV_KEYS = (
    "nav",
    "net_asset_value",
    "indicative_nav",
)

ETF_PREMIUM_DISCOUNT_KEYS = (
    "premium_discount_pct",
    "premium_discount",
    "nav_premium_discount",
)

ETF_EXPENSE_RATIO_KEYS = (
    "expense_ratio",
    "expense_ratio_pct",
)

ETF_AUM_KEYS = (
    "aum",
    "assets_under_management",
    "net_assets",
)

ETF_CATEGORY_KEYS = (
    "category",
    "fund_category",
    "asset_category",
    "classification",
)

ETF_PROVIDER_KEYS = (
    "provider",
    "fund_family",
    "issuer",
    "sponsor",
)

ETF_INCEPTION_KEYS = (
    "inception_date",
    "inception",
    "launch_date",
)

ETF_LEVERAGED_KEYS = (
    "leveraged",
    "is_leveraged",
)

ETF_INVERSE_KEYS = (
    "inverse",
    "is_inverse",
)

ETF_TRADABLE_KEYS = (
    "tradable",
    "is_tradable",
    "tradeable",
)

ETF_SHORTABLE_KEYS = (
    "shortable",
    "is_shortable",
)

ETF_FRACTIONABLE_KEYS = (
    "fractionable",
    "fractional",
    "supports_fractional",
)

ETF_MARGINABLE_KEYS = (
    "marginable",
    "margin_eligible",
)

ETF_MIN_ORDER_KEYS = (
    "min_order_size",
    "minimum_order",
    "minimum_quantity",
    "min_qty",
)

ETF_QTY_INCREMENT_KEYS = (
    "quantity_increment",
    "qty_increment",
    "lot_size",
    "step_size",
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


def _premium_discount_pct(
    price: float | None,
    nav: float | None,
) -> float | None:
    if price is None or nav is None:
        return None

    if nav <= 0.0:
        return None

    return ((price - nav) / nav) * 100.0


# =============================================================================
# ETF DOMAIN MODELS
# =============================================================================


@dataclass
class EtfInstrumentSnapshot:
    symbol: str

    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread_pct: float | None = None

    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    previous_close: float | None = None
    change_pct: float | None = None

    volume: float | None = None
    average_volume: float | None = None
    dollar_volume: float | None = None
    liquidity_score: float | None = None

    nav: float | None = None
    premium_discount_pct: float | None = None
    expense_ratio: float | None = None
    assets_under_management: float | None = None

    category: str | None = None
    provider: str | None = None
    inception_date: str | None = None

    leveraged: bool | None = None
    inverse: bool | None = None

    tradable: bool | None = None
    shortable: bool | None = None
    fractionable: bool | None = None
    marginable: bool | None = None

    minimum_order: float | None = None
    quantity_increment: float | None = None

    source: str | None = None
    as_of: str | None = None

    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            {
                "symbol": self.symbol,
                "price": self.price,
                "bid": self.bid,
                "ask": self.ask,
                "spread_pct": self.spread_pct,
                "open_price": self.open_price,
                "high_price": self.high_price,
                "low_price": self.low_price,
                "previous_close": self.previous_close,
                "change_pct": self.change_pct,
                "volume": self.volume,
                "average_volume": self.average_volume,
                "dollar_volume": self.dollar_volume,
                "liquidity_score": self.liquidity_score,
                "nav": self.nav,
                "premium_discount_pct": self.premium_discount_pct,
                "expense_ratio": self.expense_ratio,
                "assets_under_management": self.assets_under_management,
                "category": self.category,
                "provider": self.provider,
                "inception_date": self.inception_date,
                "leveraged": self.leveraged,
                "inverse": self.inverse,
                "tradable": self.tradable,
                "shortable": self.shortable,
                "fractionable": self.fractionable,
                "marginable": self.marginable,
                "minimum_order": self.minimum_order,
                "quantity_increment": self.quantity_increment,
                "source": self.source,
                "as_of": self.as_of,
                "raw": self.raw,
            }
        )


@dataclass
class EtfValidationResult:
    valid: bool
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    snapshot: EtfInstrumentSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            {
                "valid": self.valid,
                "reason": self.reason,
                "warnings": list(self.warnings),
                "snapshot": (
                    self.snapshot.to_dict()
                    if self.snapshot is not None
                    else None
                ),
            }
        )


@dataclass
class EtfRuntimeMetrics:
    capability_checks: int = 0
    capability_blocks: int = 0

    metadata_requests: int = 0
    metadata_failures: int = 0

    quote_requests: int = 0
    quote_failures: int = 0

    validations: int = 0
    validation_failures: int = 0

    price_blocks: int = 0
    spread_blocks: int = 0
    liquidity_blocks: int = 0
    tradability_blocks: int = 0

    buy_blocks: int = 0
    sell_blocks: int = 0
    short_blocks: int = 0

    execution_blocks: int = 0

    leveraged_candidates: int = 0
    inverse_candidates: int = 0

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(self.__dict__)


# =============================================================================
# ETF AUTOMATION
# =============================================================================


class EtfAutomation(BaseAssetAutomation):
    """
    PhoenixTrend ETF automation runtime.

    BaseAssetAutomation owns the common automation lifecycle and shared
    intelligence pipeline. This class provides ETF-specific:

    - capability gating;
    - ETF-only universe enforcement;
    - instrument metadata validation;
    - quote/spread/liquidity checks;
    - NAV and premium/discount context;
    - leveraged/inverse ETF metadata;
    - broker tradability validation;
    - short-sale validation;
    - execution constraints;
    - live ETF position enrichment.

    No ETF price, NAV, liquidity, volume or broker capability is fabricated.
    Missing provider data remains missing and is surfaced through warnings.
    """

    asset_class = ETF_ASSET_CLASS

    scan_interval_seconds = DEFAULT_ETF_SCAN_INTERVAL_SECONDS
    monitor_interval_seconds = DEFAULT_ETF_MONITOR_INTERVAL_SECONDS
    universe_refresh_seconds = DEFAULT_ETF_UNIVERSE_REFRESH_SECONDS
    candidate_limit = DEFAULT_ETF_CANDIDATE_LIMIT

    hold_recheck_seconds = DEFAULT_HOLD_RECHECK_SECONDS
    stale_candidate_seconds = DEFAULT_STALE_CANDIDATE_SECONDS

    max_concurrent_analysis = 5
    max_concurrent_executions = 1

    max_bid_ask_spread_pct = DEFAULT_MAX_SPREAD_PCT

    minimum_price = DEFAULT_MIN_PRICE
    maximum_price = DEFAULT_MAX_PRICE

    minimum_average_volume = DEFAULT_MIN_AVERAGE_VOLUME
    minimum_dollar_volume = DEFAULT_MIN_DOLLAR_VOLUME
    minimum_liquidity_score = DEFAULT_MIN_LIQUIDITY_SCORE

    maximum_position_fraction = DEFAULT_MAX_POSITION_FRACTION
    maximum_etf_exposure_fraction = DEFAULT_MAX_ETF_EXPOSURE_FRACTION

    require_real_market_data = True
    require_tradable_flag = True
    require_execution_capability = True

    allow_automatic_entries = True
    preserve_position_monitoring_when_disabled = True

    def __init__(self) -> None:
        super().__init__()

        self.etf_metrics = EtfRuntimeMetrics()

        self._instrument_cache: dict[
            str,
            EtfInstrumentSnapshot,
        ] = {}

        self._instrument_cache_lock = asyncio.Lock()

        self._capability_cache: dict[str, Any] | None = None
        self._capability_checked_at: str | None = None

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
    # CAPABILITY GATING
    # =========================================================================

    async def capability_snapshot(self) -> dict[str, Any]:
        self.etf_metrics.capability_checks += 1

        base = await super().capability_snapshot()

        if not base.get("supported", False):
            self.etf_metrics.capability_blocks += 1

            result = {
                **base,
                "asset_class": self.asset_class,
                "supported": False,
                "market_data_supported": False,
                "execution_supported": False,
                "reason": (
                    base.get("reason")
                    or "Configured provider does not advertise ETF support"
                ),
                "checked_at": _utc_now(),
            }

            self._capability_cache = result
            self._capability_checked_at = result["checked_at"]

            return result

        broker_capabilities = await self._broker_capabilities()

        general_etf_support = self._capability_value(
            broker_capabilities,
            ETF_CAPABILITY_KEYS,
        )

        market_data_supported = self._capability_value(
            broker_capabilities,
            ETF_MARKET_DATA_CAPABILITY_KEYS,
        )

        execution_supported = self._capability_value(
            broker_capabilities,
            ETF_ORDER_CAPABILITY_KEYS,
        )

        if market_data_supported is None:
            market_data_supported = general_etf_support

        if execution_supported is None:
            execution_supported = general_etf_support

        if market_data_supported is None:
            market_data_supported = bool(
                base.get("supported", False)
            )

        if execution_supported is None:
            execution_supported = False

        supported = bool(
            base.get("supported", False)
            and market_data_supported
        )

        reason: str | None = None

        if not market_data_supported:
            supported = False
            reason = (
                "Configured provider does not expose ETF market data"
            )

        elif (
            self.require_execution_capability
            and not execution_supported
        ):
            supported = False
            reason = (
                "Configured broker does not support ETF order execution"
            )

        if not supported:
            self.etf_metrics.capability_blocks += 1

        result = {
            **base,
            "asset_class": self.asset_class,
            "supported": supported,
            "market_data_supported": bool(market_data_supported),
            "execution_supported": bool(execution_supported),
            "general_etf_support": general_etf_support,
            "reason": reason,
            "checked_at": _utc_now(),
        }

        self._capability_cache = result
        self._capability_checked_at = result["checked_at"]

        return result

    async def _broker_capabilities(self) -> dict[str, Any]:
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
                if asyncio.iscoroutinefunction(method):
                    result = await method()
                else:
                    result = await asyncio.to_thread(method)

                return _mapping(result)

            except Exception as exc:
                logger.debug(
                    "ETF capability call failed using %s: %s",
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
            for key, value in capabilities.items()
        }

        for key in keys:
            lookup = str(key).strip().lower()

            if lookup not in normalized:
                continue

            value = normalized[lookup]

            if isinstance(value, Mapping):
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
                    return safe_bool(nested)

            return safe_bool(value)

        assets = normalized.get("assets")

        if isinstance(assets, Mapping):
            normalized_assets = {
                str(key).strip().lower(): value
                for key, value in assets.items()
            }

            for key in keys:
                lookup = str(key).strip().lower()

                if lookup not in normalized_assets:
                    continue

                value = normalized_assets[lookup]

                if isinstance(value, Mapping):
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
                        return safe_bool(nested)

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
        The universe service remains authoritative.

        Only symbols returned by the ETF universe are retained. This method
        does not substitute a stock watchlist or manufacture ETF symbols.
        """

        result: list[str] = []
        seen: set[str] = set()

        for raw_symbol in symbols:
            symbol = normalize_symbol(raw_symbol)

            if not symbol:
                continue

            if symbol in seen:
                continue

            seen.add(symbol)
            result.append(symbol)

        return result

    # =========================================================================
    # SERVICE INVOCATION
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
                    if asyncio.iscoroutinefunction(method):
                        result = await method(
                            *args,
                            **kwargs,
                        )
                    else:
                        result = await asyncio.to_thread(
                            method,
                            *args,
                            **kwargs,
                        )

                    if result is not None:
                        return result

                except TypeError:
                    continue

                except Exception as exc:
                    logger.debug(
                        "ETF service call %s.%s failed for %s: %s",
                        service.__class__.__name__,
                        method_name,
                        symbol,
                        exc,
                    )
                    break

        return None

    # =========================================================================
    # ETF METADATA / QUOTES
    # =========================================================================

    async def _fetch_etf_metadata(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        self.etf_metrics.metadata_requests += 1

        broker = self._broker_service()

        if broker is not None:
            result = await self._try_service_methods(
                broker,
                (
                    "get_etf",
                    "etf",
                    "get_fund",
                    "fund",
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
                    "etf_metadata",
                    "fund_metadata",
                    "instrument",
                    "asset",
                    "security",
                ),
                symbol,
                asset_class=self.asset_class,
            )

            if result is not None:
                return _mapping(result)

        self.etf_metrics.metadata_failures += 1

        return {}

    async def _fetch_etf_quote(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        self.etf_metrics.quote_requests += 1

        live_market = self._live_market_service()

        if live_market is not None:
            result = await self._try_service_methods(
                live_market,
                (
                    "etf_snapshot",
                    "snapshot",
                    "latest_quote",
                    "quote",
                    "get_quote",
                ),
                symbol,
                asset_class=self.asset_class,
            )

            if result is not None:
                payload = _mapping(result)

                if payload:
                    return payload

        market = self._market_service()

        if market is not None:
            result = await self._try_service_methods(
                market,
                (
                    "etf_snapshot",
                    "snapshot",
                    "latest_quote",
                    "quote",
                    "get_quote",
                ),
                symbol,
                asset_class=self.asset_class,
            )

            if result is not None:
                payload = _mapping(result)

                if payload:
                    return payload

        broker = self._broker_service()

        if broker is not None:
            result = await self._try_service_methods(
                broker,
                (
                    "get_etf_quote",
                    "etf_quote",
                    "get_quote",
                    "quote",
                ),
                symbol,
                asset_class=self.asset_class,
            )

            if result is not None:
                payload = _mapping(result)

                if payload:
                    return payload

        self.etf_metrics.quote_failures += 1

        return {}

    # =========================================================================
    # SNAPSHOT
    # =========================================================================

    async def instrument_snapshot(
        self,
        symbol: str,
        *,
        force: bool = False,
    ) -> EtfInstrumentSnapshot:
        symbol = normalize_symbol(symbol)

        if not symbol:
            raise ValueError(
                "ETF symbol is required"
            )

        if not force:
            cached = self._instrument_cache.get(symbol)

            if cached is not None:
                return cached

        metadata_task = asyncio.create_task(
            self._fetch_etf_metadata(symbol)
        )

        quote_task = asyncio.create_task(
            self._fetch_etf_quote(symbol)
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
            self._instrument_cache[symbol] = snapshot

        return snapshot

    def _build_snapshot(
        self,
        symbol: str,
        payload: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any],
        quote: Mapping[str, Any],
    ) -> EtfInstrumentSnapshot:
        bid = safe_float(
            _first(
                payload,
                ETF_BID_KEYS,
            )
        )

        ask = safe_float(
            _first(
                payload,
                ETF_ASK_KEYS,
            )
        )

        price = safe_float(
            _first(
                payload,
                ETF_PRICE_KEYS,
            )
        )

        if price is None:
            price = _mid_price(
                bid,
                ask,
            )

        nav = safe_float(
            _first(
                payload,
                ETF_NAV_KEYS,
            )
        )

        premium_discount = safe_float(
            _first(
                payload,
                ETF_PREMIUM_DISCOUNT_KEYS,
            )
        )

        if premium_discount is None:
            premium_discount = _premium_discount_pct(
                price,
                nav,
            )

        volume = safe_float(
            _first(
                payload,
                ETF_VOLUME_KEYS,
            )
        )

        average_volume = safe_float(
            _first(
                payload,
                ETF_AVERAGE_VOLUME_KEYS,
            )
        )

        dollar_volume = safe_float(
            _first(
                payload,
                ETF_DOLLAR_VOLUME_KEYS,
            )
        )

        if (
            dollar_volume is None
            and price is not None
            and volume is not None
        ):
            dollar_volume = price * volume

        tradable_raw = _first(
            payload,
            ETF_TRADABLE_KEYS,
        )

        shortable_raw = _first(
            payload,
            ETF_SHORTABLE_KEYS,
        )

        fractionable_raw = _first(
            payload,
            ETF_FRACTIONABLE_KEYS,
        )

        marginable_raw = _first(
            payload,
            ETF_MARGINABLE_KEYS,
        )

        leveraged_raw = _first(
            payload,
            ETF_LEVERAGED_KEYS,
        )

        inverse_raw = _first(
            payload,
            ETF_INVERSE_KEYS,
        )

        provider = _first(
            payload,
            ETF_PROVIDER_KEYS,
        )

        category = _first(
            payload,
            ETF_CATEGORY_KEYS,
        )

        inception = _first(
            payload,
            ETF_INCEPTION_KEYS,
        )

        source = _first(
            payload,
            (
                "source",
                "feed",
                "data_source",
            ),
        )

        as_of = _first(
            payload,
            (
                "as_of",
                "timestamp",
                "updated_at",
                "time",
            ),
        )

        return EtfInstrumentSnapshot(
            symbol=symbol,
            price=price,
            bid=bid,
            ask=ask,
            spread_pct=_spread_pct(
                bid,
                ask,
            ),
            open_price=safe_float(
                _first(
                    payload,
                    ETF_OPEN_KEYS,
                )
            ),
            high_price=safe_float(
                _first(
                    payload,
                    ETF_HIGH_KEYS,
                )
            ),
            low_price=safe_float(
                _first(
                    payload,
                    ETF_LOW_KEYS,
                )
            ),
            previous_close=safe_float(
                _first(
                    payload,
                    ETF_PREVIOUS_CLOSE_KEYS,
                )
            ),
            change_pct=safe_float(
                _first(
                    payload,
                    ETF_CHANGE_KEYS,
                )
            ),
            volume=volume,
            average_volume=average_volume,
            dollar_volume=dollar_volume,
            liquidity_score=safe_float(
                _first(
                    payload,
                    ETF_LIQUIDITY_KEYS,
                )
            ),
            nav=nav,
            premium_discount_pct=premium_discount,
            expense_ratio=safe_float(
                _first(
                    payload,
                    ETF_EXPENSE_RATIO_KEYS,
                )
            ),
            assets_under_management=safe_float(
                _first(
                    payload,
                    ETF_AUM_KEYS,
                )
            ),
            category=(
                str(category)
                if category is not None
                else None
            ),
            provider=(
                str(provider)
                if provider is not None
                else None
            ),
            inception_date=(
                str(inception)
                if inception is not None
                else None
            ),
            leveraged=(
                safe_bool(leveraged_raw)
                if leveraged_raw is not None
                else None
            ),
            inverse=(
                safe_bool(inverse_raw)
                if inverse_raw is not None
                else None
            ),
            tradable=(
                safe_bool(tradable_raw)
                if tradable_raw is not None
                else None
            ),
            shortable=(
                safe_bool(shortable_raw)
                if shortable_raw is not None
                else None
            ),
            fractionable=(
                safe_bool(fractionable_raw)
                if fractionable_raw is not None
                else None
            ),
            marginable=(
                safe_bool(marginable_raw)
                if marginable_raw is not None
                else None
            ),
            minimum_order=safe_float(
                _first(
                    payload,
                    ETF_MIN_ORDER_KEYS,
                )
            ),
            quantity_increment=safe_float(
                _first(
                    payload,
                    ETF_QTY_INCREMENT_KEYS,
                )
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
                "metadata": serialize_value(metadata),
                "quote": serialize_value(quote),
            },
        )

    # =========================================================================
    # VALIDATION
    # =========================================================================

    async def validate_etf_instrument(
        self,
        symbol: str,
    ) -> EtfValidationResult:
        snapshot = await self.instrument_snapshot(
            symbol,
            force=True,
        )

        warnings: list[str] = []

        if (
            self.require_real_market_data
            and snapshot.price is None
            and snapshot.bid is None
            and snapshot.ask is None
        ):
            self.etf_metrics.price_blocks += 1

            return EtfValidationResult(
                valid=False,
                reason=(
                    "No real ETF price or quote is available"
                ),
                snapshot=snapshot,
            )

        if snapshot.price is not None:
            if (
                snapshot.price < self.minimum_price
                or snapshot.price > self.maximum_price
            ):
                self.etf_metrics.price_blocks += 1

                return EtfValidationResult(
                    valid=False,
                    reason=(
                        "ETF price is outside the configured valid range"
                    ),
                    snapshot=snapshot,
                )

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            self.etf_metrics.spread_blocks += 1

            return EtfValidationResult(
                valid=False,
                reason=(
                    "ETF bid/ask spread exceeds "
                    f"{self.max_bid_ask_spread_pct:.4f}%"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.average_volume is not None
            and snapshot.average_volume
            < self.minimum_average_volume
        ):
            self.etf_metrics.liquidity_blocks += 1

            return EtfValidationResult(
                valid=False,
                reason=(
                    "ETF average volume is below the configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.dollar_volume is not None
            and snapshot.dollar_volume
            < self.minimum_dollar_volume
        ):
            self.etf_metrics.liquidity_blocks += 1

            return EtfValidationResult(
                valid=False,
                reason=(
                    "ETF dollar volume is below the configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.liquidity_score is not None
            and snapshot.liquidity_score
            < self.minimum_liquidity_score
        ):
            self.etf_metrics.liquidity_blocks += 1

            return EtfValidationResult(
                valid=False,
                reason=(
                    "ETF liquidity score is below the configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            self.require_tradable_flag
            and snapshot.tradable is False
        ):
            self.etf_metrics.tradability_blocks += 1

            return EtfValidationResult(
                valid=False,
                reason=(
                    "Broker marks this ETF as non-tradable"
                ),
                snapshot=snapshot,
            )

        if (
            self.require_tradable_flag
            and snapshot.tradable is None
        ):
            warnings.append(
                "Provider did not return an explicit tradable flag"
            )

        if snapshot.leveraged is True:
            self.etf_metrics.leveraged_candidates += 1

            warnings.append(
                "Leveraged ETF: risk engine must apply the configured "
                "position and exposure limits"
            )

        if snapshot.inverse is True:
            self.etf_metrics.inverse_candidates += 1

            warnings.append(
                "Inverse ETF: strategy direction must be interpreted "
                "against the ETF itself, not its tracked benchmark"
            )

        if snapshot.nav is None:
            warnings.append(
                "ETF NAV is unavailable"
            )

        if snapshot.average_volume is None:
            warnings.append(
                "ETF average volume is unavailable"
            )

        if snapshot.spread_pct is None:
            warnings.append(
                "ETF bid/ask spread is unavailable"
            )

        return EtfValidationResult(
            valid=True,
            warnings=warnings,
            snapshot=snapshot,
        )

    async def validate_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> tuple[bool, str | None]:
        self.etf_metrics.validations += 1

        valid, reason = await super().validate_candidate(
            candidate
        )

        if not valid:
            self.etf_metrics.validation_failures += 1
            return valid, reason

        capability = await self.capability_snapshot()

        if not capability.get("supported", False):
            self.etf_metrics.validation_failures += 1

            return (
                False,
                capability.get("reason")
                or "ETF automation capability is unavailable",
            )

        try:
            validation = await self.validate_etf_instrument(
                candidate.symbol
            )

        except Exception as exc:
            self.etf_metrics.validation_failures += 1

            return (
                False,
                f"ETF validation failed: {exc}",
            )

        if not validation.valid:
            self.etf_metrics.validation_failures += 1

            return (
                False,
                validation.reason,
            )

        if validation.snapshot is not None:
            candidate.scanner_payload[
                "etf"
            ] = validation.snapshot.to_dict()

        if validation.warnings:
            candidate.scanner_payload[
                "etf_warnings"
            ] = list(validation.warnings)

        return True, None

    # =========================================================================
    # CANDIDATE ENRICHMENT
    # =========================================================================

    async def prepare_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> CandidateRuntime:
        candidate = await super().prepare_candidate(
            candidate
        )

        snapshot = self._instrument_cache.get(
            candidate.symbol
        )

        if snapshot is None:
            snapshot = await self.instrument_snapshot(
                candidate.symbol,
                force=True,
            )

        candidate.scanner_payload[
            "asset_class"
        ] = self.asset_class

        candidate.scanner_payload[
            "instrument_type"
        ] = "etf"

        candidate.scanner_payload[
            "etf"
        ] = snapshot.to_dict()

        self._merge_etf_fields(
            candidate.scanner_payload,
            snapshot,
        )

        return candidate

    # =========================================================================
    # SCANNING
    # =========================================================================

    async def before_scan(self) -> None:
        capability = await self.capability_snapshot()

        if not capability.get("supported", False):
            raise RuntimeError(
                capability.get("reason")
                or "ETF capability is unavailable"
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
            "ETF_SCAN_COMPLETED",
            message="ETF scan completed",
            data={
                "candidate_count": (
                    len(candidates)
                    if isinstance(candidates, list)
                    else 0
                ),
                "universe_size": len(self.universe()),
            },
        )

    async def scan_market(self) -> dict[str, Any]:
        await self.before_scan()

        result = await super().scan_market()

        candidates = result.get(
            "candidates",
            [],
        )

        validated: list[dict[str, Any]] = []

        if isinstance(candidates, list):
            validation_tasks: list[
                tuple[
                    dict[str, Any],
                    asyncio.Task[EtfValidationResult],
                ]
            ] = []

            for raw_candidate in candidates:
                payload = _mapping(raw_candidate)

                symbol = normalize_symbol(
                    _first(
                        payload,
                        ETF_SYMBOL_KEYS,
                    )
                )

                if not symbol:
                    continue

                task = asyncio.create_task(
                    self.validate_etf_instrument(
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
                        ETF_SYMBOL_KEYS,
                    )
                )

                try:
                    validation = await task

                except Exception as exc:
                    logger.debug(
                        "ETF scan validation failed for %s: %s",
                        symbol,
                        exc,
                    )
                    continue

                if not validation.valid:
                    continue

                payload["symbol"] = symbol
                payload["asset_class"] = self.asset_class
                payload["instrument_type"] = "etf"

                snapshot = validation.snapshot

                if snapshot is not None:
                    payload["etf"] = snapshot.to_dict()

                    self._merge_etf_fields(
                        payload,
                        snapshot,
                    )

                if validation.warnings:
                    payload["warnings"] = list(
                        validation.warnings
                    )

                validated.append(payload)

        result = dict(result)

        result["candidates"] = validated[
            : self.candidate_limit
        ]

        result["count"] = len(
            result["candidates"]
        )

        result["asset_class"] = self.asset_class
        result["instrument_type"] = "etf"

        await self.after_scan(result)

        return result

    def _merge_etf_fields(
        self,
        payload: dict[str, Any],
        snapshot: EtfInstrumentSnapshot,
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

        if snapshot.average_volume is not None:
            payload.setdefault(
                "average_volume",
                snapshot.average_volume,
            )

        if snapshot.dollar_volume is not None:
            payload.setdefault(
                "dollar_volume",
                snapshot.dollar_volume,
            )

        if snapshot.change_pct is not None:
            payload.setdefault(
                "change_pct",
                snapshot.change_pct,
            )

        if snapshot.nav is not None:
            payload.setdefault(
                "nav",
                snapshot.nav,
            )

        if snapshot.premium_discount_pct is not None:
            payload.setdefault(
                "premium_discount_pct",
                snapshot.premium_discount_pct,
            )

        if snapshot.expense_ratio is not None:
            payload.setdefault(
                "expense_ratio",
                snapshot.expense_ratio,
            )

        if snapshot.assets_under_management is not None:
            payload.setdefault(
                "assets_under_management",
                snapshot.assets_under_management,
            )

        if snapshot.category is not None:
            payload.setdefault(
                "category",
                snapshot.category,
            )

        if snapshot.provider is not None:
            payload.setdefault(
                "provider",
                snapshot.provider,
            )

        if snapshot.leveraged is not None:
            payload.setdefault(
                "leveraged",
                snapshot.leveraged,
            )

        if snapshot.inverse is not None:
            payload.setdefault(
                "inverse",
                snapshot.inverse,
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
        candidate, decision = await super().prepare_execution(
            candidate,
            decision,
        )

        capability = await self.capability_snapshot()

        if not capability.get(
            "execution_supported",
            False,
        ):
            self.etf_metrics.execution_blocks += 1

            candidate.state = CANDIDATE_BLOCKED

            decision.blocked = True
            decision.block_reason = (
                "Configured broker does not support ETF execution"
            )

            return candidate, decision

        snapshot = self._instrument_cache.get(
            candidate.symbol
        )

        if snapshot is None:
            snapshot = await self.instrument_snapshot(
                candidate.symbol,
                force=True,
            )

        if snapshot.tradable is False:
            self.etf_metrics.tradability_blocks += 1
            self.etf_metrics.execution_blocks += 1

            candidate.state = CANDIDATE_BLOCKED

            decision.blocked = True
            decision.block_reason = (
                "Broker marks the selected ETF as non-tradable"
            )

            return candidate, decision

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            self.etf_metrics.spread_blocks += 1
            self.etf_metrics.execution_blocks += 1

            candidate.state = CANDIDATE_BLOCKED

            decision.blocked = True
            decision.block_reason = (
                "Current ETF spread exceeds the configured execution threshold"
            )

            return candidate, decision

        if decision.action == ACTION_SELL:
            can_sell = await self._can_sell_etf(
                candidate.symbol,
                snapshot,
            )

            if not can_sell:
                self.etf_metrics.sell_blocks += 1
                self.etf_metrics.short_blocks += 1
                self.etf_metrics.execution_blocks += 1

                candidate.state = CANDIDATE_BLOCKED

                decision.blocked = True
                decision.block_reason = (
                    "SELL decision cannot be executed because no owned "
                    "position was confirmed and the broker did not confirm "
                    "ETF shortability"
                )

                return candidate, decision

        decision.analysis.setdefault(
            "etf",
            snapshot.to_dict(),
        )

        decision.analysis[
            "asset_class"
        ] = self.asset_class

        decision.analysis[
            "instrument_type"
        ] = "etf"

        decision.analysis[
            "execution_constraints"
        ] = {
            "minimum_order": snapshot.minimum_order,
            "quantity_increment": snapshot.quantity_increment,
            "fractionable": snapshot.fractionable,
            "marginable": snapshot.marginable,
            "shortable": snapshot.shortable,
            "spread_pct": snapshot.spread_pct,
            "leveraged": snapshot.leveraged,
            "inverse": snapshot.inverse,
            "maximum_position_fraction": (
                self.maximum_position_fraction
            ),
            "maximum_etf_exposure_fraction": (
                self.maximum_etf_exposure_fraction
            ),
        }

        return candidate, decision

    async def _can_sell_etf(
        self,
        symbol: str,
        snapshot: EtfInstrumentSnapshot,
    ) -> bool:
        if await self.has_open_position(symbol):
            return True

        return snapshot.shortable is True

    async def handle_decision(
        self,
        candidate: CandidateRuntime,
        decision: DecisionRuntime,
    ) -> None:
        if decision.blocked:
            self.metrics.execution_blocks += 1

            await self._emit_event(
                "ETF_EXECUTION_BLOCKED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    decision.block_reason
                    or "ETF execution blocked"
                ),
                data=decision.to_dict(),
            )

            return

        if decision.action == ACTION_HOLD:
            await self._emit_event(
                "ETF_HOLD",
                symbol=candidate.symbol,
                message=(
                    f"{candidate.symbol} remains under ETF monitoring"
                ),
                data={
                    "confidence": decision.confidence,
                    "strategy": decision.strategy,
                    "pattern": decision.pattern,
                    "regime": decision.regime,
                },
            )

            return

        if decision.action not in {
            ACTION_BUY,
            ACTION_SELL,
        }:
            candidate.state = CANDIDATE_SKIPPED

            await self._emit_event(
                "ETF_DECISION_SKIPPED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    f"Unsupported ETF decision {decision.action}"
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
            snapshot = await self.instrument_snapshot(
                symbol,
                force=True,
            )

        except Exception as exc:
            await self._emit_event(
                "ETF_POSITION_QUOTE_FAILED",
                severity="WARNING",
                symbol=symbol,
                message=str(exc),
            )

            return

        if snapshot.price is not None:
            position.current_price = snapshot.price

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
                    if side in {
                        "SHORT",
                        "SELL",
                    }
                    else 1.0
                )

                pnl = (
                    snapshot.price - entry_price
                ) * quantity * direction

                pnl_pct = (
                    (
                        snapshot.price - entry_price
                    )
                    / entry_price
                    * 100.0
                    * direction
                )

                position.unrealized_pl = pnl
                position.unrealized_pl_pct = pnl_pct

        position.raw = {
            **_mapping(
                getattr(
                    position,
                    "raw",
                    {},
                )
            ),
            "etf": snapshot.to_dict(),
        }

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            await self._emit_event(
                "ETF_SPREAD_WARNING",
                severity="WARNING",
                symbol=symbol,
                message=(
                    f"{symbol} spread exceeds the configured threshold"
                ),
                data={
                    "spread_pct": snapshot.spread_pct,
                    "threshold": self.max_bid_ask_spread_pct,
                },
            )

        if snapshot.leveraged is True:
            await self._emit_event(
                "ETF_LEVERAGED_POSITION",
                severity="INFO",
                symbol=symbol,
                message=(
                    f"{symbol} is a leveraged ETF position"
                ),
            )

        if snapshot.inverse is True:
            await self._emit_event(
                "ETF_INVERSE_POSITION",
                severity="INFO",
                symbol=symbol,
                message=(
                    f"{symbol} is an inverse ETF position"
                ),
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
            include_candidates=include_candidates,
            include_positions=include_positions,
            include_decisions=include_decisions,
            include_events=include_events,
        )

        payload["etf_runtime"] = {
            "metrics": self.etf_metrics.to_dict(),
            "capability": serialize_value(
                self._capability_cache
            ),
            "capability_checked_at": (
                self._capability_checked_at
            ),
            "cached_instruments": len(
                self._instrument_cache
            ),
            "configuration": {
                "max_bid_ask_spread_pct": (
                    self.max_bid_ask_spread_pct
                ),
                "minimum_price": self.minimum_price,
                "maximum_price": self.maximum_price,
                "minimum_average_volume": (
                    self.minimum_average_volume
                ),
                "minimum_dollar_volume": (
                    self.minimum_dollar_volume
                ),
                "minimum_liquidity_score": (
                    self.minimum_liquidity_score
                ),
                "maximum_position_fraction": (
                    self.maximum_position_fraction
                ),
                "maximum_etf_exposure_fraction": (
                    self.maximum_etf_exposure_fraction
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
        capability = await self.capability_snapshot()

        universe = self.universe()

        sample_validation: list[
            dict[str, Any]
        ] = []

        for symbol in universe[:5]:
            try:
                validation = await self.validate_etf_instrument(
                    symbol
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
            "asset_class": self.asset_class,
            "capability": capability,
            "universe_size": len(universe),
            "sample_validation": sample_validation,
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


etf_automation = EtfAutomation()