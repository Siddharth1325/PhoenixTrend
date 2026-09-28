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
# BOND / FIXED-INCOME CONSTANTS
# =============================================================================

BOND_ASSET_CLASS = "bonds"

BOND_TYPE_TREASURY = "TREASURY"
BOND_TYPE_GOVERNMENT = "GOVERNMENT"
BOND_TYPE_MUNICIPAL = "MUNICIPAL"
BOND_TYPE_CORPORATE = "CORPORATE"
BOND_TYPE_AGENCY = "AGENCY"
BOND_TYPE_SOVEREIGN = "SOVEREIGN"
BOND_TYPE_UNKNOWN = "UNKNOWN"

SUPPORTED_BOND_TYPES = {
    BOND_TYPE_TREASURY,
    BOND_TYPE_GOVERNMENT,
    BOND_TYPE_MUNICIPAL,
    BOND_TYPE_CORPORATE,
    BOND_TYPE_AGENCY,
    BOND_TYPE_SOVEREIGN,
    BOND_TYPE_UNKNOWN,
}

DEFAULT_BOND_SCAN_INTERVAL_SECONDS = 120.0
DEFAULT_BOND_MONITOR_INTERVAL_SECONDS = 15.0
DEFAULT_BOND_UNIVERSE_REFRESH_SECONDS = 900.0
DEFAULT_BOND_CANDIDATE_LIMIT = 12

DEFAULT_MAX_BID_ASK_SPREAD_PCT = 2.50
DEFAULT_MIN_PRICE = 0.01
DEFAULT_MAX_PRICE = 1_000_000.0

DEFAULT_MIN_YIELD_PCT = -25.0
DEFAULT_MAX_YIELD_PCT = 100.0

DEFAULT_MIN_DURATION = 0.0
DEFAULT_MAX_DURATION = 100.0

DEFAULT_MIN_DAYS_TO_MATURITY = 1

DEFAULT_MIN_LIQUIDITY_SCORE = 0.0

DEFAULT_MAX_BOND_POSITION_FRACTION = 0.20
DEFAULT_MAX_ISSUER_EXPOSURE_FRACTION = 0.20

EXECUTION_CAPABILITY_KEYS = (
    "bonds",
    "bond",
    "fixed_income",
    "fixed-income",
    "fixedincome",
)

MARKET_DATA_CAPABILITY_KEYS = (
    "bond_market_data",
    "fixed_income_market_data",
    "fixed-income-market-data",
    "bonds_market_data",
    "bond_quotes",
)

ORDER_CAPABILITY_KEYS = (
    "bond_orders",
    "fixed_income_orders",
    "fixed-income-orders",
    "bonds_trading",
)

BOND_SYMBOL_KEYS = (
    "symbol",
    "ticker",
    "cusip",
    "isin",
    "security_id",
    "instrument_id",
    "asset_id",
)

BOND_PRICE_KEYS = (
    "price",
    "current_price",
    "market_price",
    "last_price",
    "last",
    "mark",
    "mid",
    "clean_price",
    "dirty_price",
)

BOND_BID_KEYS = (
    "bid",
    "bid_price",
    "best_bid",
)

BOND_ASK_KEYS = (
    "ask",
    "ask_price",
    "best_ask",
)

BOND_YIELD_KEYS = (
    "yield",
    "yield_pct",
    "yield_percent",
    "yield_to_maturity",
    "ytm",
    "yield_to_worst",
    "ytw",
)

BOND_COUPON_KEYS = (
    "coupon",
    "coupon_rate",
    "coupon_pct",
    "coupon_percent",
)

BOND_DURATION_KEYS = (
    "duration",
    "modified_duration",
    "effective_duration",
)

BOND_VOLUME_KEYS = (
    "volume",
    "trade_volume",
    "daily_volume",
)

BOND_LIQUIDITY_KEYS = (
    "liquidity",
    "liquidity_score",
    "marketability_score",
)

BOND_MATURITY_KEYS = (
    "maturity",
    "maturity_date",
    "matures_at",
)

BOND_ISSUER_KEYS = (
    "issuer",
    "issuer_name",
    "company",
    "government",
)

BOND_TYPE_KEYS = (
    "bond_type",
    "security_type",
    "instrument_type",
    "type",
    "category",
)

BOND_CREDIT_RATING_KEYS = (
    "credit_rating",
    "rating",
    "composite_rating",
)

BOND_CALLABLE_KEYS = (
    "callable",
    "is_callable",
)

BOND_CURRENCY_KEYS = (
    "currency",
    "currency_code",
)

BOND_FACE_VALUE_KEYS = (
    "face_value",
    "par_value",
    "principal",
)

BOND_MIN_ORDER_KEYS = (
    "minimum_order",
    "minimum_quantity",
    "min_qty",
    "min_order_quantity",
)

BOND_INCREMENT_KEYS = (
    "quantity_increment",
    "order_increment",
    "increment",
    "lot_size",
)


# =============================================================================
# HELPERS
# =============================================================================


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _normalize_bond_type(value: Any) -> str:
    text = str(value or "").strip().upper()

    aliases = {
        "US_TREASURY": BOND_TYPE_TREASURY,
        "U.S. TREASURY": BOND_TYPE_TREASURY,
        "TREASURIES": BOND_TYPE_TREASURY,
        "TREASURY": BOND_TYPE_TREASURY,
        "GOV": BOND_TYPE_GOVERNMENT,
        "GOVERNMENT": BOND_TYPE_GOVERNMENT,
        "GOVERNMENT_BOND": BOND_TYPE_GOVERNMENT,
        "MUNI": BOND_TYPE_MUNICIPAL,
        "MUNICIPAL": BOND_TYPE_MUNICIPAL,
        "MUNICIPAL_BOND": BOND_TYPE_MUNICIPAL,
        "CORP": BOND_TYPE_CORPORATE,
        "CORPORATE": BOND_TYPE_CORPORATE,
        "CORPORATE_BOND": BOND_TYPE_CORPORATE,
        "AGENCY": BOND_TYPE_AGENCY,
        "AGENCY_BOND": BOND_TYPE_AGENCY,
        "SOVEREIGN": BOND_TYPE_SOVEREIGN,
        "SOVEREIGN_BOND": BOND_TYPE_SOVEREIGN,
    }

    normalized = aliases.get(text, text)

    if normalized not in SUPPORTED_BOND_TYPES:
        return BOND_TYPE_UNKNOWN

    return normalized


def _parse_iso_date(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        result = value

        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)

        return result

    text = str(value).strip()

    if not text:
        return None

    candidates = [
        text,
        text.replace("Z", "+00:00"),
    ]

    for candidate in candidates:
        try:
            result = datetime.fromisoformat(candidate)

            if result.tzinfo is None:
                result = result.replace(tzinfo=timezone.utc)

            return result
        except ValueError:
            continue

    for format_string in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%Y%m%d",
    ):
        try:
            result = datetime.strptime(
                text,
                format_string,
            )

            return result.replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue

    return None


def _days_to_maturity(value: Any) -> int | None:
    maturity = _parse_iso_date(value)

    if maturity is None:
        return None

    delta = maturity - datetime.now(timezone.utc)

    return max(
        0,
        int(delta.total_seconds() // 86400),
    )


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
    if (
        bid is None
        or ask is None
        or bid <= 0.0
        or ask <= 0.0
        or ask < bid
    ):
        return None

    return (bid + ask) / 2.0


# =============================================================================
# BOND DOMAIN STATE
# =============================================================================


@dataclass
class BondInstrumentSnapshot:
    symbol: str
    issuer: str | None = None
    bond_type: str = BOND_TYPE_UNKNOWN
    currency: str | None = None

    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread_pct: float | None = None

    yield_pct: float | None = None
    coupon_pct: float | None = None

    maturity_date: str | None = None
    days_to_maturity: int | None = None

    duration: float | None = None
    credit_rating: str | None = None

    volume: float | None = None
    liquidity_score: float | None = None

    callable: bool | None = None
    face_value: float | None = None
    minimum_order: float | None = None
    quantity_increment: float | None = None

    tradable: bool | None = None
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
                "issuer": self.issuer,
                "bond_type": self.bond_type,
                "currency": self.currency,
                "price": self.price,
                "bid": self.bid,
                "ask": self.ask,
                "spread_pct": self.spread_pct,
                "yield_pct": self.yield_pct,
                "coupon_pct": self.coupon_pct,
                "maturity_date": self.maturity_date,
                "days_to_maturity": (
                    self.days_to_maturity
                ),
                "duration": self.duration,
                "credit_rating": (
                    self.credit_rating
                ),
                "volume": self.volume,
                "liquidity_score": (
                    self.liquidity_score
                ),
                "callable": self.callable,
                "face_value": self.face_value,
                "minimum_order": self.minimum_order,
                "quantity_increment": (
                    self.quantity_increment
                ),
                "tradable": self.tradable,
                "shortable": self.shortable,
                "source": self.source,
                "as_of": self.as_of,
                "raw": self.raw,
            }
        )


@dataclass
class BondValidationResult:
    valid: bool
    reason: str | None = None
    warnings: list[str] = field(
        default_factory=list
    )
    snapshot: BondInstrumentSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "warnings": list(self.warnings),
            "snapshot": (
                self.snapshot.to_dict()
                if self.snapshot
                else None
            ),
        }


@dataclass
class BondRuntimeMetrics:
    capability_checks: int = 0
    capability_blocks: int = 0
    metadata_requests: int = 0
    metadata_failures: int = 0
    quote_requests: int = 0
    quote_failures: int = 0
    candidate_validations: int = 0
    candidate_rejections: int = 0
    spread_rejections: int = 0
    maturity_rejections: int = 0
    price_rejections: int = 0
    tradability_rejections: int = 0
    execution_blocks: int = 0
    short_sale_blocks: int = 0

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            self.__dict__
        )


# =============================================================================
# BOND AUTOMATION
# =============================================================================


class BondAutomation(BaseAssetAutomation):
    """
    PhoenixTrend fixed-income automation runtime.

    This runtime deliberately remains capability-gated.

    It never:
    - invents bond instruments;
    - fabricates yields;
    - fabricates coupons;
    - fabricates maturities;
    - assumes a stock broker supports fixed income;
    - converts an equity symbol into a fake bond;
    - creates a synthetic bond quote when the provider returns no quote;
    - submits an order when fixed-income execution capability is unavailable.

    When the configured broker/data provider exposes genuine fixed-income
    functionality, this class validates the returned instruments and delegates
    shared market intelligence, safety, risk and execution to PhoenixTrend's
    mature services through BaseAssetAutomation.
    """

    asset_class = BOND_ASSET_CLASS

    scan_interval_seconds = (
        DEFAULT_BOND_SCAN_INTERVAL_SECONDS
    )

    monitor_interval_seconds = (
        DEFAULT_BOND_MONITOR_INTERVAL_SECONDS
    )

    universe_refresh_seconds = (
        DEFAULT_BOND_UNIVERSE_REFRESH_SECONDS
    )

    candidate_limit = (
        DEFAULT_BOND_CANDIDATE_LIMIT
    )

    max_concurrent_analysis = 3
    max_concurrent_executions = 1

    hold_recheck_seconds = 30.0
    stale_candidate_seconds = 900.0
    drain_timeout_seconds = 45.0

    max_bid_ask_spread_pct = (
        DEFAULT_MAX_BID_ASK_SPREAD_PCT
    )

    minimum_price = DEFAULT_MIN_PRICE
    maximum_price = DEFAULT_MAX_PRICE

    minimum_yield_pct = DEFAULT_MIN_YIELD_PCT
    maximum_yield_pct = DEFAULT_MAX_YIELD_PCT

    minimum_duration = DEFAULT_MIN_DURATION
    maximum_duration = DEFAULT_MAX_DURATION

    minimum_days_to_maturity = (
        DEFAULT_MIN_DAYS_TO_MATURITY
    )

    minimum_liquidity_score = (
        DEFAULT_MIN_LIQUIDITY_SCORE
    )

    maximum_position_fraction = (
        DEFAULT_MAX_BOND_POSITION_FRACTION
    )

    maximum_issuer_exposure_fraction = (
        DEFAULT_MAX_ISSUER_EXPOSURE_FRACTION
    )

    require_tradable_flag = True

    require_real_market_data = True

    require_execution_capability = True

    allow_automatic_entries = True

    preserve_position_monitoring_when_disabled = True

    def __init__(self) -> None:
        super().__init__()

        self.bond_metrics = BondRuntimeMetrics()

        self._instrument_cache: dict[
            str,
            BondInstrumentSnapshot,
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
    # SERVICE RESOLUTION
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

    def _risk_service(self) -> Any | None:
        return self._resolve_service(
            "backend.app.services.risk",
            (
                "risk_service",
                "risk",
            ),
        )

    # =========================================================================
    # CAPABILITY GATING
    # =========================================================================

    async def capability_snapshot(
        self,
    ) -> dict[str, Any]:
        self.bond_metrics.capability_checks += 1

        base_capability = (
            await super().capability_snapshot()
        )

        if not base_capability.get(
            "supported",
            False,
        ):
            self.bond_metrics.capability_blocks += 1

            result = {
                **base_capability,
                "asset_class": self.asset_class,
                "supported": False,
                "market_data_supported": False,
                "execution_supported": False,
                "reason": (
                    base_capability.get("reason")
                    or (
                        "Configured provider does not "
                        "advertise bond support"
                    )
                ),
            }

            self._capability_cache = result
            self._capability_checked_at = (
                _utc_now()
            )

            return result

        broker_capability = (
            await self._broker_capabilities()
        )

        market_data_supported = (
            self._capability_value(
                broker_capability,
                MARKET_DATA_CAPABILITY_KEYS,
            )
        )

        execution_supported = (
            self._capability_value(
                broker_capability,
                ORDER_CAPABILITY_KEYS,
            )
        )

        general_bond_support = (
            self._capability_value(
                broker_capability,
                EXECUTION_CAPABILITY_KEYS,
            )
        )

        if market_data_supported is None:
            market_data_supported = (
                general_bond_support
            )

        if execution_supported is None:
            execution_supported = (
                general_bond_support
            )

        if market_data_supported is None:
            market_data_supported = bool(
                base_capability.get(
                    "supported",
                    False,
                )
            )

        if execution_supported is None:
            execution_supported = False

        supported = bool(
            base_capability.get(
                "supported",
                False,
            )
            and market_data_supported
        )

        reason: str | None = None

        if not market_data_supported:
            supported = False
            reason = (
                "The configured provider does not "
                "expose fixed-income market data"
            )

        elif (
            self.require_execution_capability
            and not execution_supported
        ):
            supported = False
            reason = (
                "The configured broker does not "
                "support fixed-income order execution"
            )

        result = {
            **base_capability,
            "asset_class": self.asset_class,
            "supported": supported,
            "market_data_supported": bool(
                market_data_supported
            ),
            "execution_supported": bool(
                execution_supported
            ),
            "general_bond_support": (
                general_bond_support
            ),
            "reason": reason,
            "checked_at": _utc_now(),
        }

        if not supported:
            self.bond_metrics.capability_blocks += 1

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

        method_names = (
            "capabilities",
            "get_capabilities",
            "trading_capabilities",
            "broker_capabilities",
        )

        for method_name in method_names:
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
                    result = await asyncio.to_thread(
                        method
                    )

                return _mapping(result)

            except Exception as exc:
                logger.warning(
                    "Bond capability request failed "
                    "using %s: %s",
                    method_name,
                    exc,
                )

        capabilities = getattr(
            broker,
            "capabilities",
            None,
        )

        if isinstance(
            capabilities,
            Mapping,
        ):
            return dict(capabilities)

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
            normalized_key = (
                str(key).strip().lower()
            )

            if normalized_key not in normalized:
                continue

            value = normalized[
                normalized_key
            ]

            if isinstance(value, Mapping):
                for nested_key in (
                    "supported",
                    "enabled",
                    "available",
                    "tradable",
                ):
                    if nested_key in value:
                        return safe_bool(
                            value[nested_key]
                        )

            return safe_bool(value)

        assets = normalized.get(
            "assets"
        )

        if isinstance(assets, Mapping):
            for key in keys:
                if key in assets:
                    value = assets[key]

                    if isinstance(
                        value,
                        Mapping,
                    ):
                        return safe_bool(
                            _first(
                                value,
                                (
                                    "supported",
                                    "enabled",
                                    "available",
                                    "tradable",
                                ),
                                False,
                            )
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
        The universe service is authoritative.

        This method only normalizes and deduplicates provider-returned
        identifiers. It does not manufacture CUSIPs, ISINs or ticker symbols.
        """

        normalized: list[str] = []
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
            normalized.append(symbol)

        return normalized

    # =========================================================================
    # PROVIDER DATA
    # =========================================================================

    async def _fetch_bond_metadata(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        self.bond_metrics.metadata_requests += 1

        symbol = normalize_symbol(symbol)

        broker = self._broker_service()

        if broker is not None:
            result = await self._try_service_methods(
                broker,
                (
                    "get_bond",
                    "bond",
                    "get_fixed_income_asset",
                    "get_asset",
                    "asset",
                ),
                symbol,
            )

            if result is not None:
                return _mapping(result)

        market = self._market_service()

        if market is not None:
            result = await self._try_service_methods(
                market,
                (
                    "bond_metadata",
                    "instrument",
                    "asset",
                    "security",
                ),
                symbol,
            )

            if result is not None:
                return _mapping(result)

        self.bond_metrics.metadata_failures += 1

        return {}

    async def _fetch_bond_quote(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        self.bond_metrics.quote_requests += 1

        symbol = normalize_symbol(symbol)

        live_market = (
            self._live_market_service()
        )

        if live_market is not None:
            result = await self._try_service_methods(
                live_market,
                (
                    "snapshot",
                    "quote",
                    "latest_quote",
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
                    "snapshot",
                    "quote",
                    "latest_quote",
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
                    "get_bond_quote",
                    "bond_quote",
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

        self.bond_metrics.quote_failures += 1

        return {}

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

            calls = [
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

            for args, kwargs in calls:
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
                        "Bond service call %s.%s "
                        "failed for %s: %s",
                        service.__class__.__name__,
                        method_name,
                        symbol,
                        exc,
                    )

                    break

        return None

    # =========================================================================
    # SNAPSHOT CONSTRUCTION
    # =========================================================================

    async def instrument_snapshot(
        self,
        symbol: str,
        *,
        force: bool = False,
    ) -> BondInstrumentSnapshot:
        symbol = normalize_symbol(symbol)

        if not symbol:
            raise ValueError(
                "Bond instrument identifier is required"
            )

        if not force:
            cached = self._instrument_cache.get(
                symbol
            )

            if cached is not None:
                return cached

        metadata_task = asyncio.create_task(
            self._fetch_bond_metadata(
                symbol
            )
        )

        quote_task = asyncio.create_task(
            self._fetch_bond_quote(
                symbol
            )
        )

        metadata, quote = await asyncio.gather(
            metadata_task,
            quote_task,
        )

        merged: dict[str, Any] = {}

        merged.update(metadata)
        merged.update(quote)

        snapshot = self._build_snapshot(
            symbol,
            merged,
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
    ) -> BondInstrumentSnapshot:
        bid = safe_float(
            _first(
                payload,
                BOND_BID_KEYS,
            )
        )

        ask = safe_float(
            _first(
                payload,
                BOND_ASK_KEYS,
            )
        )

        price = safe_float(
            _first(
                payload,
                BOND_PRICE_KEYS,
            )
        )

        if price is None:
            price = _mid_price(
                bid,
                ask,
            )

        yield_pct = safe_float(
            _first(
                payload,
                BOND_YIELD_KEYS,
            )
        )

        coupon_pct = safe_float(
            _first(
                payload,
                BOND_COUPON_KEYS,
            )
        )

        duration = safe_float(
            _first(
                payload,
                BOND_DURATION_KEYS,
            )
        )

        maturity = _first(
            payload,
            BOND_MATURITY_KEYS,
        )

        issuer = _first(
            payload,
            BOND_ISSUER_KEYS,
        )

        bond_type = _normalize_bond_type(
            _first(
                payload,
                BOND_TYPE_KEYS,
            )
        )

        credit_rating = _first(
            payload,
            BOND_CREDIT_RATING_KEYS,
        )

        volume = safe_float(
            _first(
                payload,
                BOND_VOLUME_KEYS,
            )
        )

        liquidity_score = safe_float(
            _first(
                payload,
                BOND_LIQUIDITY_KEYS,
            )
        )

        callable_value = _first(
            payload,
            BOND_CALLABLE_KEYS,
        )

        callable_flag = (
            safe_bool(callable_value)
            if callable_value is not None
            else None
        )

        tradable_value = _first(
            payload,
            (
                "tradable",
                "is_tradable",
                "tradeable",
            ),
        )

        tradable = (
            safe_bool(tradable_value)
            if tradable_value is not None
            else None
        )

        shortable_value = _first(
            payload,
            (
                "shortable",
                "is_shortable",
            ),
        )

        shortable = (
            safe_bool(shortable_value)
            if shortable_value is not None
            else None
        )

        source = _first(
            payload,
            (
                "source",
                "provider",
                "feed",
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

        return BondInstrumentSnapshot(
            symbol=symbol,
            issuer=(
                str(issuer)
                if issuer is not None
                else None
            ),
            bond_type=bond_type,
            currency=(
                str(
                    _first(
                        payload,
                        BOND_CURRENCY_KEYS,
                    )
                )
                if _first(
                    payload,
                    BOND_CURRENCY_KEYS,
                )
                is not None
                else None
            ),
            price=price,
            bid=bid,
            ask=ask,
            spread_pct=_spread_pct(
                bid,
                ask,
            ),
            yield_pct=yield_pct,
            coupon_pct=coupon_pct,
            maturity_date=(
                str(maturity)
                if maturity is not None
                else None
            ),
            days_to_maturity=(
                _days_to_maturity(
                    maturity
                )
            ),
            duration=duration,
            credit_rating=(
                str(credit_rating)
                if credit_rating is not None
                else None
            ),
            volume=volume,
            liquidity_score=(
                liquidity_score
            ),
            callable=callable_flag,
            face_value=safe_float(
                _first(
                    payload,
                    BOND_FACE_VALUE_KEYS,
                )
            ),
            minimum_order=safe_float(
                _first(
                    payload,
                    BOND_MIN_ORDER_KEYS,
                )
            ),
            quantity_increment=safe_float(
                _first(
                    payload,
                    BOND_INCREMENT_KEYS,
                )
            ),
            tradable=tradable,
            shortable=shortable,
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
                "metadata": serialize_value(
                    metadata
                ),
                "quote": serialize_value(
                    quote
                ),
            },
        )

    # =========================================================================
    # CANDIDATE VALIDATION
    # =========================================================================

    async def validate_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> tuple[bool, str | None]:
        self.bond_metrics.candidate_validations += 1

        base_valid, base_reason = (
            await super().validate_candidate(
                candidate
            )
        )

        if not base_valid:
            self.bond_metrics.candidate_rejections += 1

            return (
                False,
                base_reason,
            )

        capability = (
            await self.capability_snapshot()
        )

        if not capability.get(
            "supported",
            False,
        ):
            self.bond_metrics.candidate_rejections += 1

            return (
                False,
                capability.get("reason")
                or (
                    "Fixed-income capability "
                    "is unavailable"
                ),
            )

        try:
            validation = (
                await self.validate_bond_instrument(
                    candidate.symbol
                )
            )

        except Exception as exc:
            self.bond_metrics.candidate_rejections += 1

            return (
                False,
                f"Bond validation failed: {exc}",
            )

        if not validation.valid:
            self.bond_metrics.candidate_rejections += 1

            return (
                False,
                validation.reason,
            )

        if validation.snapshot is not None:
            candidate.scanner_payload[
                "bond"
            ] = validation.snapshot.to_dict()

            if validation.warnings:
                candidate.scanner_payload[
                    "bond_warnings"
                ] = list(
                    validation.warnings
                )

        return True, None

    async def validate_bond_instrument(
        self,
        symbol: str,
    ) -> BondValidationResult:
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
            self.bond_metrics.price_rejections += 1

            return BondValidationResult(
                valid=False,
                reason=(
                    "No real fixed-income price or "
                    "quote is available"
                ),
                snapshot=snapshot,
            )

        if snapshot.price is not None:
            if (
                snapshot.price
                < self.minimum_price
                or snapshot.price
                > self.maximum_price
            ):
                self.bond_metrics.price_rejections += 1

                return BondValidationResult(
                    valid=False,
                    reason=(
                        "Bond price is outside the "
                        "configured valid range"
                    ),
                    snapshot=snapshot,
                )

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            self.bond_metrics.spread_rejections += 1

            return BondValidationResult(
                valid=False,
                reason=(
                    "Bond bid/ask spread exceeds "
                    f"{self.max_bid_ask_spread_pct:.2f}%"
                ),
                snapshot=snapshot,
            )

        if (
            snapshot.days_to_maturity is not None
            and snapshot.days_to_maturity
            < self.minimum_days_to_maturity
        ):
            self.bond_metrics.maturity_rejections += 1

            return BondValidationResult(
                valid=False,
                reason=(
                    "Bond has reached or is too "
                    "close to maturity"
                ),
                snapshot=snapshot,
            )

        if snapshot.yield_pct is not None:
            if (
                snapshot.yield_pct
                < self.minimum_yield_pct
                or snapshot.yield_pct
                > self.maximum_yield_pct
            ):
                return BondValidationResult(
                    valid=False,
                    reason=(
                        "Reported bond yield is "
                        "outside configured validation "
                        "bounds"
                    ),
                    snapshot=snapshot,
                )

        if snapshot.duration is not None:
            if (
                snapshot.duration
                < self.minimum_duration
                or snapshot.duration
                > self.maximum_duration
            ):
                return BondValidationResult(
                    valid=False,
                    reason=(
                        "Reported duration is outside "
                        "configured validation bounds"
                    ),
                    snapshot=snapshot,
                )

        if (
            snapshot.liquidity_score is not None
            and snapshot.liquidity_score
            < self.minimum_liquidity_score
        ):
            return BondValidationResult(
                valid=False,
                reason=(
                    "Bond liquidity score is below "
                    "the configured minimum"
                ),
                snapshot=snapshot,
            )

        if self.require_tradable_flag:
            if snapshot.tradable is False:
                self.bond_metrics.tradability_rejections += 1

                return BondValidationResult(
                    valid=False,
                    reason=(
                        "Broker marks this bond as "
                        "not tradable"
                    ),
                    snapshot=snapshot,
                )

            if snapshot.tradable is None:
                warnings.append(
                    "Provider did not return an "
                    "explicit tradable flag"
                )

        if snapshot.credit_rating is None:
            warnings.append(
                "Credit rating is unavailable"
            )

        if snapshot.duration is None:
            warnings.append(
                "Duration is unavailable"
            )

        if snapshot.yield_pct is None:
            warnings.append(
                "Yield is unavailable"
            )

        if snapshot.maturity_date is None:
            warnings.append(
                "Maturity date is unavailable"
            )

        return BondValidationResult(
            valid=True,
            warnings=warnings,
            snapshot=snapshot,
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

        snapshot = (
            self._instrument_cache.get(
                candidate.symbol
            )
        )

        if snapshot is None:
            snapshot = await self.instrument_snapshot(
                candidate.symbol,
                force=True,
            )

        bond_payload = snapshot.to_dict()

        candidate.scanner_payload[
            "bond"
        ] = bond_payload

        candidate.scanner_payload[
            "asset_class"
        ] = self.asset_class

        candidate.scanner_payload[
            "instrument_type"
        ] = "fixed_income"

        if snapshot.spread_pct is not None:
            candidate.scanner_payload[
                "spread_pct"
            ] = snapshot.spread_pct

        if snapshot.yield_pct is not None:
            candidate.scanner_payload[
                "yield_pct"
            ] = snapshot.yield_pct

        if snapshot.duration is not None:
            candidate.scanner_payload[
                "duration"
            ] = snapshot.duration

        if (
            snapshot.days_to_maturity
            is not None
        ):
            candidate.scanner_payload[
                "days_to_maturity"
            ] = snapshot.days_to_maturity

        return candidate

    # =========================================================================
    # EXECUTION PREPARATION
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
            self.bond_metrics.execution_blocks += 1

            candidate.state = CANDIDATE_BLOCKED

            decision.blocked = True
            decision.block_reason = (
                "Configured broker does not "
                "support fixed-income execution"
            )

            return candidate, decision

        snapshot = (
            self._instrument_cache.get(
                candidate.symbol
            )
        )

        if snapshot is None:
            snapshot = await self.instrument_snapshot(
                candidate.symbol,
                force=True,
            )

        if snapshot.tradable is False:
            self.bond_metrics.execution_blocks += 1

            candidate.state = CANDIDATE_BLOCKED

            decision.blocked = True
            decision.block_reason = (
                "Broker marks the selected bond "
                "as non-tradable"
            )

            return candidate, decision

        if (
            decision.action == ACTION_SELL
            and not await self._can_sell_bond(
                candidate.symbol,
                snapshot,
            )
        ):
            self.bond_metrics.short_sale_blocks += 1
            self.bond_metrics.execution_blocks += 1

            candidate.state = CANDIDATE_BLOCKED

            decision.blocked = True

            decision.block_reason = (
                "SELL decision cannot be executed "
                "because no owned position was "
                "confirmed and the provider did not "
                "confirm fixed-income shortability"
            )

            return candidate, decision

        decision.analysis.setdefault(
            "bond",
            snapshot.to_dict(),
        )

        decision.analysis[
            "asset_class"
        ] = self.asset_class

        decision.analysis[
            "instrument_type"
        ] = "fixed_income"

        decision.analysis[
            "execution_constraints"
        ] = {
            "minimum_order": (
                snapshot.minimum_order
            ),
            "quantity_increment": (
                snapshot.quantity_increment
            ),
            "face_value": (
                snapshot.face_value
            ),
            "currency": snapshot.currency,
            "spread_pct": (
                snapshot.spread_pct
            ),
        }

        return candidate, decision

    async def _can_sell_bond(
        self,
        symbol: str,
        snapshot: BondInstrumentSnapshot,
    ) -> bool:
        if await self.has_open_position(
            symbol
        ):
            return True

        return snapshot.shortable is True

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
                "BOND_EXECUTION_BLOCKED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    decision.block_reason
                    or "Bond execution blocked"
                ),
                data=decision.to_dict(),
            )

            return

        if decision.action == ACTION_HOLD:
            await self._emit_event(
                "BOND_HOLD",
                symbol=candidate.symbol,
                message=(
                    f"{candidate.symbol} remains "
                    "under fixed-income monitoring"
                ),
                data={
                    "confidence": (
                        decision.confidence
                    ),
                    "strategy": (
                        decision.strategy
                    ),
                },
            )

            return

        if decision.action not in {
            ACTION_BUY,
            ACTION_SELL,
        }:
            candidate.state = CANDIDATE_SKIPPED

            await self._emit_event(
                "BOND_DECISION_SKIPPED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    "Unsupported bond decision "
                    f"{decision.action}"
                ),
            )

            return

        await super().handle_decision(
            candidate,
            decision,
        )

    # =========================================================================
    # BOND-SPECIFIC SCANNER HOOKS
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
                    "Bond automation capability "
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
            "BOND_SCAN_COMPLETED",
            message=(
                "Fixed-income scan completed"
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

        result = await super().scan_market()

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
            for candidate_payload in candidates:
                payload = _mapping(
                    candidate_payload
                )

                symbol = normalize_symbol(
                    _first(
                        payload,
                        BOND_SYMBOL_KEYS,
                    )
                )

                if not symbol:
                    continue

                try:
                    validation = (
                        await self.validate_bond_instrument(
                            symbol
                        )
                    )

                except Exception as exc:
                    logger.warning(
                        "Bond scan validation "
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

                if validation.snapshot:
                    payload["bond"] = (
                        validation.snapshot.to_dict()
                    )

                    self._merge_bond_ranking_fields(
                        payload,
                        validation.snapshot,
                    )

                if validation.warnings:
                    payload["warnings"] = list(
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
            "fixed_income"
        )

        await self.after_scan(
            result
        )

        return result

    def _merge_bond_ranking_fields(
        self,
        payload: dict[str, Any],
        snapshot: BondInstrumentSnapshot,
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

        if snapshot.yield_pct is not None:
            payload.setdefault(
                "yield_pct",
                snapshot.yield_pct,
            )

        if snapshot.coupon_pct is not None:
            payload.setdefault(
                "coupon_pct",
                snapshot.coupon_pct,
            )

        if snapshot.duration is not None:
            payload.setdefault(
                "duration",
                snapshot.duration,
            )

        if snapshot.volume is not None:
            payload.setdefault(
                "volume",
                snapshot.volume,
            )

        if snapshot.liquidity_score is not None:
            payload.setdefault(
                "liquidity_score",
                snapshot.liquidity_score,
            )

        if snapshot.days_to_maturity is not None:
            payload.setdefault(
                "days_to_maturity",
                snapshot.days_to_maturity,
            )

        if snapshot.credit_rating is not None:
            payload.setdefault(
                "credit_rating",
                snapshot.credit_rating,
            )

        if snapshot.issuer is not None:
            payload.setdefault(
                "issuer",
                snapshot.issuer,
            )

        payload.setdefault(
            "bond_type",
            snapshot.bond_type,
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
                "BOND_POSITION_QUOTE_FAILED",
                severity="WARNING",
                symbol=symbol,
                message=str(exc),
            )

            return

        if snapshot.price is not None:
            position.current_price = (
                snapshot.price
            )

        position.raw = {
            **_mapping(
                getattr(
                    position,
                    "raw",
                    {},
                )
            ),
            "bond": snapshot.to_dict(),
        }

        if (
            snapshot.days_to_maturity
            is not None
            and snapshot.days_to_maturity
            <= self.minimum_days_to_maturity
        ):
            await self._emit_event(
                "BOND_MATURITY_WARNING",
                severity="WARNING",
                symbol=symbol,
                message=(
                    f"{symbol} is approaching "
                    "maturity"
                ),
                data={
                    "days_to_maturity": (
                        snapshot.days_to_maturity
                    ),
                    "maturity_date": (
                        snapshot.maturity_date
                    ),
                },
            )

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            await self._emit_event(
                "BOND_SPREAD_WARNING",
                severity="WARNING",
                symbol=symbol,
                message=(
                    f"{symbol} bid/ask spread "
                    "exceeds configured threshold"
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
    # STATUS / DIAGNOSTICS
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

        payload["bond_runtime"] = {
            "metrics": (
                self.bond_metrics.to_dict()
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
                "maximum_price": (
                    self.maximum_price
                ),
                "minimum_yield_pct": (
                    self.minimum_yield_pct
                ),
                "maximum_yield_pct": (
                    self.maximum_yield_pct
                ),
                "minimum_duration": (
                    self.minimum_duration
                ),
                "maximum_duration": (
                    self.maximum_duration
                ),
                "minimum_days_to_maturity": (
                    self.minimum_days_to_maturity
                ),
                "minimum_liquidity_score": (
                    self.minimum_liquidity_score
                ),
                "maximum_position_fraction": (
                    self.maximum_position_fraction
                ),
                "maximum_issuer_exposure_fraction": (
                    self.maximum_issuer_exposure_fraction
                ),
                "require_real_market_data": (
                    self.require_real_market_data
                ),
                "require_execution_capability": (
                    self.require_execution_capability
                ),
            },
        }

        return payload

    async def diagnostics(
        self,
    ) -> dict[str, Any]:
        capability = (
            await self.capability_snapshot()
        )

        universe = self.universe()

        samples: list[
            dict[str, Any]
        ] = []

        for symbol in universe[:3]:
            try:
                validation = (
                    await self.validate_bond_instrument(
                        symbol
                    )
                )

                samples.append(
                    {
                        "symbol": symbol,
                        **validation.to_dict(),
                    }
                )

            except Exception as exc:
                samples.append(
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
            "sample_validation": samples,
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


bond_automation = BondAutomation()
