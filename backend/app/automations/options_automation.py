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
    safe_int,
    serialize_value,
)
from ..services.options_chain import options_chain_service
from ..services.options_scanner import options_scanner


logger = logging.getLogger(__name__)


# =============================================================================
# OPTIONS CONSTANTS
# =============================================================================

OPTIONS_ASSET_CLASS = "options"

DEFAULT_OPTIONS_SCAN_INTERVAL_SECONDS = 45.0
DEFAULT_OPTIONS_MONITOR_INTERVAL_SECONDS = 3.0
DEFAULT_OPTIONS_UNIVERSE_REFRESH_SECONDS = 600.0

DEFAULT_UNDERLYING_CANDIDATE_LIMIT = 10
DEFAULT_CHAIN_UNDERLYING_LIMIT = 5
DEFAULT_CONTRACT_CANDIDATE_LIMIT = 20

DEFAULT_MAX_SPREAD_PCT = 25.0
DEFAULT_MIN_BID = 0.0
DEFAULT_MIN_MARK = 0.01
DEFAULT_MIN_VOLUME = 0
DEFAULT_MIN_OPEN_INTEREST = 0

DEFAULT_MIN_DAYS_TO_EXPIRATION = 0
DEFAULT_MAX_DAYS_TO_EXPIRATION = 365

DEFAULT_MIN_DELTA_ABS = 0.0
DEFAULT_MAX_DELTA_ABS = 1.0

DEFAULT_MAX_POSITION_FRACTION = 0.05
DEFAULT_MAX_OPTIONS_EXPOSURE_FRACTION = 0.20

DEFAULT_HOLD_RECHECK_SECONDS = 10.0
DEFAULT_STALE_CANDIDATE_SECONDS = 180.0

OPTION_MULTIPLIER_DEFAULT = 100.0

OPTION_TYPE_CALL = "CALL"
OPTION_TYPE_PUT = "PUT"

OPTIONS_CAPABILITY_KEYS = (
    "options",
    "option",
    "equity_options",
    "listed_options",
)

OPTIONS_MARKET_DATA_CAPABILITY_KEYS = (
    "options_market_data",
    "option_market_data",
    "options_quotes",
    "options_chain",
    "option_chain",
)

OPTIONS_ORDER_CAPABILITY_KEYS = (
    "options_orders",
    "options_trading",
    "option_orders",
    "option_trading",
)

UNDERLYING_SYMBOL_KEYS = (
    "underlying",
    "underlying_symbol",
    "root_symbol",
    "root",
    "symbol",
)

CONTRACT_SYMBOL_KEYS = (
    "contract_symbol",
    "option_symbol",
    "occ_symbol",
    "symbol",
)

OPTION_TYPE_KEYS = (
    "option_type",
    "type",
    "right",
    "put_call",
    "call_put",
)

STRIKE_KEYS = (
    "strike",
    "strike_price",
)

EXPIRATION_KEYS = (
    "expiration",
    "expiration_date",
    "expiry",
    "expiry_date",
)

DTE_KEYS = (
    "days_to_expiration",
    "dte",
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

LAST_KEYS = (
    "last",
    "last_price",
    "price",
)

MARK_KEYS = (
    "mark",
    "mark_price",
    "mid",
    "mid_price",
)

VOLUME_KEYS = (
    "volume",
    "contract_volume",
)

OPEN_INTEREST_KEYS = (
    "open_interest",
    "oi",
)

IV_KEYS = (
    "implied_volatility",
    "iv",
)

DELTA_KEYS = (
    "delta",
)

GAMMA_KEYS = (
    "gamma",
)

THETA_KEYS = (
    "theta",
)

VEGA_KEYS = (
    "vega",
)

RHO_KEYS = (
    "rho",
)

UNDERLYING_PRICE_KEYS = (
    "underlying_price",
    "stock_price",
    "spot",
    "spot_price",
)

MULTIPLIER_KEYS = (
    "multiplier",
    "contract_multiplier",
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

CLOSE_ONLY_KEYS = (
    "close_only",
    "closing_only",
)

SOURCE_KEYS = (
    "source",
    "provider",
    "feed",
)

AS_OF_KEYS = (
    "as_of",
    "timestamp",
    "updated_at",
    "time",
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


def _normalize_option_type(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().upper()

    if text in {
        "C",
        "CALL",
        "CALLS",
    }:
        return OPTION_TYPE_CALL

    if text in {
        "P",
        "PUT",
        "PUTS",
    }:
        return OPTION_TYPE_PUT

    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip()

        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            result = datetime.fromisoformat(text)
        except ValueError:
            try:
                result = datetime.strptime(
                    text[:10],
                    "%Y-%m-%d",
                )
            except ValueError:
                return None

    if result.tzinfo is None:
        result = result.replace(
            tzinfo=timezone.utc
        )

    return result.astimezone(
        timezone.utc
    )


def _days_to_expiration(
    expiration: Any,
) -> int | None:
    parsed = _parse_datetime(
        expiration
    )

    if parsed is None:
        return None

    now = datetime.now(
        timezone.utc
    )

    seconds = (
        parsed - now
    ).total_seconds()

    return max(
        0,
        int(
            seconds // 86400
        ),
    )


def _mid_price(
    bid: float | None,
    ask: float | None,
) -> float | None:
    if (
        bid is None
        or ask is None
        or bid < 0.0
        or ask <= 0.0
        or ask < bid
    ):
        return None

    return (
        bid + ask
    ) / 2.0


def _spread_pct(
    bid: float | None,
    ask: float | None,
    mark: float | None = None,
) -> float | None:
    if (
        bid is None
        or ask is None
        or bid < 0.0
        or ask <= 0.0
        or ask < bid
    ):
        return None

    denominator = (
        mark
        if mark is not None
        and mark > 0.0
        else _mid_price(
            bid,
            ask,
        )
    )

    if (
        denominator is None
        or denominator <= 0.0
    ):
        return None

    return (
        (ask - bid)
        / denominator
        * 100.0
    )


# =============================================================================
# OPTIONS DOMAIN MODELS
# =============================================================================


@dataclass
class OptionContractSnapshot:
    symbol: str
    underlying: str

    option_type: str | None = None

    strike: float | None = None
    expiration: str | None = None
    days_to_expiration: int | None = None

    underlying_price: float | None = None

    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    mark: float | None = None
    spread_pct: float | None = None

    volume: int | None = None
    open_interest: int | None = None

    implied_volatility: float | None = None

    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None

    multiplier: float | None = None

    tradable: bool | None = None
    buyable: bool | None = None
    sellable: bool | None = None
    close_only: bool | None = None

    source: str | None = None
    as_of: str | None = None

    raw: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            {
                "symbol": self.symbol,
                "underlying": self.underlying,
                "option_type": self.option_type,
                "strike": self.strike,
                "expiration": self.expiration,
                "days_to_expiration": self.days_to_expiration,
                "underlying_price": self.underlying_price,
                "bid": self.bid,
                "ask": self.ask,
                "last": self.last,
                "mark": self.mark,
                "spread_pct": self.spread_pct,
                "volume": self.volume,
                "open_interest": self.open_interest,
                "implied_volatility": self.implied_volatility,
                "delta": self.delta,
                "gamma": self.gamma,
                "theta": self.theta,
                "vega": self.vega,
                "rho": self.rho,
                "multiplier": self.multiplier,
                "tradable": self.tradable,
                "buyable": self.buyable,
                "sellable": self.sellable,
                "close_only": self.close_only,
                "source": self.source,
                "as_of": self.as_of,
                "raw": self.raw,
            }
        )


@dataclass
class OptionValidationResult:
    valid: bool

    reason: str | None = None

    warnings: list[str] = field(
        default_factory=list
    )

    snapshot: OptionContractSnapshot | None = None

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
class OptionsRuntimeMetrics:
    capability_checks: int = 0
    capability_blocks: int = 0

    underlying_scans: int = 0
    underlying_candidates: int = 0

    chain_requests: int = 0
    chain_failures: int = 0
    empty_chains: int = 0

    contract_scans: int = 0
    contracts_received: int = 0
    contracts_validated: int = 0
    contracts_rejected: int = 0

    invalid_contract_blocks: int = 0
    expired_contract_blocks: int = 0
    spread_blocks: int = 0
    liquidity_blocks: int = 0
    tradability_blocks: int = 0

    buy_blocks: int = 0
    sell_blocks: int = 0

    execution_blocks: int = 0

    position_quote_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(
            self.__dict__
        )


# =============================================================================
# OPTIONS AUTOMATION
# =============================================================================


class OptionsAutomation(BaseAssetAutomation):
    """
    PhoenixTrend options automation runtime.

    Pipeline:

        Stock/ETF underlying universe
        -> underlying market scanner
        -> underlying candidate ranking
        -> underlying technical intelligence
        -> directional BUY / SELL / HOLD context
        -> real option-chain request
        -> contract scanner
        -> contract liquidity / expiration / spread validation
        -> contract candidate analysis
        -> safety
        -> risk
        -> execution
        -> position monitoring

    Option chains, strikes, expirations, quotes, Greeks, open interest,
    volume and broker capabilities are never fabricated by this runtime.
    """

    asset_class = OPTIONS_ASSET_CLASS

    scan_interval_seconds = (
        DEFAULT_OPTIONS_SCAN_INTERVAL_SECONDS
    )

    monitor_interval_seconds = (
        DEFAULT_OPTIONS_MONITOR_INTERVAL_SECONDS
    )

    universe_refresh_seconds = (
        DEFAULT_OPTIONS_UNIVERSE_REFRESH_SECONDS
    )

    candidate_limit = (
        DEFAULT_UNDERLYING_CANDIDATE_LIMIT
    )

    chain_underlying_limit = (
        DEFAULT_CHAIN_UNDERLYING_LIMIT
    )

    contract_candidate_limit = (
        DEFAULT_CONTRACT_CANDIDATE_LIMIT
    )

    hold_recheck_seconds = (
        DEFAULT_HOLD_RECHECK_SECONDS
    )

    stale_candidate_seconds = (
        DEFAULT_STALE_CANDIDATE_SECONDS
    )

    max_concurrent_analysis = 4
    max_concurrent_executions = 1

    max_bid_ask_spread_pct = (
        DEFAULT_MAX_SPREAD_PCT
    )

    minimum_bid = (
        DEFAULT_MIN_BID
    )

    minimum_mark = (
        DEFAULT_MIN_MARK
    )

    minimum_volume = (
        DEFAULT_MIN_VOLUME
    )

    minimum_open_interest = (
        DEFAULT_MIN_OPEN_INTEREST
    )

    minimum_days_to_expiration = (
        DEFAULT_MIN_DAYS_TO_EXPIRATION
    )

    maximum_days_to_expiration = (
        DEFAULT_MAX_DAYS_TO_EXPIRATION
    )

    minimum_absolute_delta = (
        DEFAULT_MIN_DELTA_ABS
    )

    maximum_absolute_delta = (
        DEFAULT_MAX_DELTA_ABS
    )

    maximum_position_fraction = (
        DEFAULT_MAX_POSITION_FRACTION
    )

    maximum_options_exposure_fraction = (
        DEFAULT_MAX_OPTIONS_EXPOSURE_FRACTION
    )

    require_real_chain = True
    require_real_quote = True
    require_execution_capability = True
    require_tradable_flag = True

    allow_automatic_entries = True

    preserve_position_monitoring_when_disabled = True

    def __init__(self) -> None:
        super().__init__()

        self.options_metrics = (
            OptionsRuntimeMetrics()
        )

        self._contract_cache: dict[
            str,
            OptionContractSnapshot,
        ] = {}

        self._contract_cache_lock = (
            asyncio.Lock()
        )

        self._chain_cache: dict[
            str,
            Any,
        ] = {}

        self._chain_cache_lock = (
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

    # =========================================================================
    # CAPABILITIES
    # =========================================================================

    async def capability_snapshot(
        self,
    ) -> dict[str, Any]:
        self.options_metrics.capability_checks += 1

        base = (
            await super().capability_snapshot()
        )

        if not base.get(
            "supported",
            False,
        ):
            self.options_metrics.capability_blocks += 1

            result = {
                **base,
                "asset_class": self.asset_class,
                "supported": False,
                "chain_supported": False,
                "execution_supported": False,
                "reason": (
                    base.get("reason")
                    or (
                        "Configured provider does not "
                        "advertise options support"
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

        general_options_support = (
            self._capability_value(
                broker_capabilities,
                OPTIONS_CAPABILITY_KEYS,
            )
        )

        chain_supported = (
            self._capability_value(
                broker_capabilities,
                OPTIONS_MARKET_DATA_CAPABILITY_KEYS,
            )
        )

        execution_supported = (
            self._capability_value(
                broker_capabilities,
                OPTIONS_ORDER_CAPABILITY_KEYS,
            )
        )

        if chain_supported is None:
            chain_supported = (
                general_options_support
            )

        if execution_supported is None:
            execution_supported = (
                general_options_support
            )

        if chain_supported is None:
            chain_supported = True

        if execution_supported is None:
            execution_supported = False

        supported = bool(
            base.get(
                "supported",
                False,
            )
            and chain_supported
        )

        reason: str | None = None

        if not chain_supported:
            supported = False

            reason = (
                "Configured provider does not "
                "support real options-chain data"
            )

        elif (
            self.require_execution_capability
            and not execution_supported
        ):
            supported = False

            reason = (
                "Configured broker does not "
                "support options order execution"
            )

        if not supported:
            self.options_metrics.capability_blocks += 1

        result = {
            **base,
            "asset_class": self.asset_class,
            "supported": supported,
            "chain_supported": bool(
                chain_supported
            ),
            "execution_supported": bool(
                execution_supported
            ),
            "general_options_support": (
                general_options_support
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

            if not callable(
                method
            ):
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
                    "Options capability call failed "
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
            return dict(
                raw
            )

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
    # OPTIONS CHAIN
    # =========================================================================

    async def _request_chain(
        self,
        underlying: str,
        *,
        force: bool = False,
    ) -> Any:
        underlying = normalize_symbol(
            underlying
        )

        if not underlying:
            raise ValueError(
                "Underlying symbol is required"
            )

        if not force:
            cached = (
                self._chain_cache.get(
                    underlying
                )
            )

            if cached is not None:
                return cached

        self.options_metrics.chain_requests += 1

        try:
            chain_method = getattr(
                options_chain_service,
                "chain",
                None,
            )

            if not callable(
                chain_method
            ):
                raise RuntimeError(
                    "Options chain service does not "
                    "expose chain()"
                )

            if asyncio.iscoroutinefunction(
                chain_method
            ):
                chain = await chain_method(
                    underlying
                )
            else:
                chain = (
                    await asyncio.to_thread(
                        chain_method,
                        underlying,
                    )
                )

        except Exception:
            self.options_metrics.chain_failures += 1
            raise

        if chain is None:
            self.options_metrics.empty_chains += 1

            if self.require_real_chain:
                raise RuntimeError(
                    f"No options chain returned for {underlying}"
                )

        async with self._chain_cache_lock:
            self._chain_cache[
                underlying
            ] = chain

        return chain

    async def _scan_chain(
        self,
        underlying: str,
        chain: Any,
    ) -> dict[str, Any]:
        self.options_metrics.contract_scans += 1

        scanner_method = getattr(
            options_scanner,
            "scan",
            None,
        )

        if not callable(
            scanner_method
        ):
            raise RuntimeError(
                "Options scanner does not expose scan()"
            )

        if asyncio.iscoroutinefunction(
            scanner_method
        ):
            result = await scanner_method(
                underlying,
                chain,
            )
        else:
            result = (
                await asyncio.to_thread(
                    scanner_method,
                    underlying,
                    chain,
                )
            )

        return _mapping(
            result
        )

    # =========================================================================
    # CONTRACT ENRICHMENT
    # =========================================================================

    async def enrich_contracts(
        self,
        underlying_candidates: list[
            dict[str, Any]
        ],
    ) -> list[dict[str, Any]]:
        contracts: list[
            dict[str, Any]
        ] = []

        selected_underlyings = (
            underlying_candidates[
                : self.chain_underlying_limit
            ]
        )

        for candidate in selected_underlyings:
            underlying = normalize_symbol(
                _first(
                    candidate,
                    UNDERLYING_SYMBOL_KEYS,
                )
            )

            if not underlying:
                continue

            try:
                chain = (
                    await self._request_chain(
                        underlying,
                        force=True,
                    )
                )

                scan_result = (
                    await self._scan_chain(
                        underlying,
                        chain,
                    )
                )

            except Exception as exc:
                logger.warning(
                    "Options chain processing failed "
                    "for %s: %s",
                    underlying,
                    exc,
                )

                await self._emit_event(
                    "OPTIONS_CHAIN_FAILED",
                    severity="WARNING",
                    symbol=underlying,
                    message=str(
                        exc
                    ),
                )

                continue

            raw_contracts = (
                scan_result.get(
                    "contracts",
                    [],
                )
            )

            if not isinstance(
                raw_contracts,
                list,
            ):
                continue

            self.options_metrics.contracts_received += (
                len(
                    raw_contracts
                )
            )

            for raw_contract in raw_contracts:
                payload = _mapping(
                    raw_contract
                )

                validation = (
                    self._validate_contract_payload(
                        underlying,
                        payload,
                    )
                )

                if not validation.valid:
                    self.options_metrics.contracts_rejected += 1

                    continue

                self.options_metrics.contracts_validated += 1

                snapshot = (
                    validation.snapshot
                )

                if snapshot is None:
                    continue

                contract_payload = dict(
                    payload
                )

                contract_payload[
                    "symbol"
                ] = snapshot.symbol

                contract_payload[
                    "contract_symbol"
                ] = snapshot.symbol

                contract_payload[
                    "underlying"
                ] = snapshot.underlying

                contract_payload[
                    "asset_class"
                ] = self.asset_class

                contract_payload[
                    "instrument_type"
                ] = "option"

                contract_payload[
                    "option"
                ] = snapshot.to_dict()

                contract_payload[
                    "underlying_candidate"
                ] = serialize_value(
                    candidate
                )

                if validation.warnings:
                    contract_payload[
                        "warnings"
                    ] = list(
                        validation.warnings
                    )

                contracts.append(
                    contract_payload
                )

                self._contract_cache[
                    snapshot.symbol
                ] = snapshot

        contracts.sort(
            key=self._contract_rank_key,
            reverse=True,
        )

        return contracts[
            : self.contract_candidate_limit
        ]

    def _contract_rank_key(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[
        float,
        float,
        float,
        float,
    ]:
        option = _mapping(
            payload.get(
                "option"
            )
        )

        volume = safe_float(
            option.get(
                "volume"
            )
        ) or 0.0

        open_interest = safe_float(
            option.get(
                "open_interest"
            )
        ) or 0.0

        spread = safe_float(
            option.get(
                "spread_pct"
            )
        )

        delta = safe_float(
            option.get(
                "delta"
            )
        )

        spread_score = (
            -spread
            if spread is not None
            else -1_000_000.0
        )

        delta_score = (
            -abs(
                abs(delta) - 0.50
            )
            if delta is not None
            else -1.0
        )

        return (
            open_interest,
            volume,
            spread_score,
            delta_score,
        )

    # =========================================================================
    # CONTRACT VALIDATION
    # =========================================================================

    def _validate_contract_payload(
        self,
        underlying: str,
        payload: Mapping[str, Any],
    ) -> OptionValidationResult:
        contract_symbol = normalize_symbol(
            _first(
                payload,
                CONTRACT_SYMBOL_KEYS,
            )
        )

        if not contract_symbol:
            self.options_metrics.invalid_contract_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Option contract symbol is missing"
                ),
            )

        option_type = (
            _normalize_option_type(
                _first(
                    payload,
                    OPTION_TYPE_KEYS,
                )
            )
        )

        strike = safe_float(
            _first(
                payload,
                STRIKE_KEYS,
            )
        )

        expiration_raw = _first(
            payload,
            EXPIRATION_KEYS,
        )

        expiration = (
            str(
                expiration_raw
            )
            if expiration_raw is not None
            else None
        )

        dte = safe_int(
            _first(
                payload,
                DTE_KEYS,
            )
        )

        if dte is None:
            dte = (
                _days_to_expiration(
                    expiration
                )
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

        last = safe_float(
            _first(
                payload,
                LAST_KEYS,
            )
        )

        mark = safe_float(
            _first(
                payload,
                MARK_KEYS,
            )
        )

        if mark is None:
            mark = _mid_price(
                bid,
                ask,
            )

        spread_pct = (
            _spread_pct(
                bid,
                ask,
                mark,
            )
        )

        volume = safe_int(
            _first(
                payload,
                VOLUME_KEYS,
            )
        )

        open_interest = safe_int(
            _first(
                payload,
                OPEN_INTEREST_KEYS,
            )
        )

        delta = safe_float(
            _first(
                payload,
                DELTA_KEYS,
            )
        )

        tradable_raw = _first(
            payload,
            TRADABLE_KEYS,
        )

        buyable_raw = _first(
            payload,
            BUYABLE_KEYS,
        )

        sellable_raw = _first(
            payload,
            SELLABLE_KEYS,
        )

        close_only_raw = _first(
            payload,
            CLOSE_ONLY_KEYS,
        )

        snapshot = OptionContractSnapshot(
            symbol=contract_symbol,
            underlying=normalize_symbol(
                underlying
            ),
            option_type=option_type,
            strike=strike,
            expiration=expiration,
            days_to_expiration=dte,
            underlying_price=safe_float(
                _first(
                    payload,
                    UNDERLYING_PRICE_KEYS,
                )
            ),
            bid=bid,
            ask=ask,
            last=last,
            mark=mark,
            spread_pct=spread_pct,
            volume=volume,
            open_interest=open_interest,
            implied_volatility=safe_float(
                _first(
                    payload,
                    IV_KEYS,
                )
            ),
            delta=delta,
            gamma=safe_float(
                _first(
                    payload,
                    GAMMA_KEYS,
                )
            ),
            theta=safe_float(
                _first(
                    payload,
                    THETA_KEYS,
                )
            ),
            vega=safe_float(
                _first(
                    payload,
                    VEGA_KEYS,
                )
            ),
            rho=safe_float(
                _first(
                    payload,
                    RHO_KEYS,
                )
            ),
            multiplier=(
                safe_float(
                    _first(
                        payload,
                        MULTIPLIER_KEYS,
                    )
                )
            ),
            tradable=(
                safe_bool(
                    tradable_raw
                )
                if tradable_raw is not None
                else None
            ),
            buyable=(
                safe_bool(
                    buyable_raw
                )
                if buyable_raw is not None
                else None
            ),
            sellable=(
                safe_bool(
                    sellable_raw
                )
                if sellable_raw is not None
                else None
            ),
            close_only=(
                safe_bool(
                    close_only_raw
                )
                if close_only_raw is not None
                else None
            ),
            source=(
                str(
                    _first(
                        payload,
                        SOURCE_KEYS,
                    )
                )
                if _first(
                    payload,
                    SOURCE_KEYS,
                )
                is not None
                else None
            ),
            as_of=(
                str(
                    _first(
                        payload,
                        AS_OF_KEYS,
                    )
                )
                if _first(
                    payload,
                    AS_OF_KEYS,
                )
                is not None
                else None
            ),
            raw=serialize_value(
                dict(
                    payload
                )
            ),
        )

        warnings: list[str] = []

        if option_type not in {
            OPTION_TYPE_CALL,
            OPTION_TYPE_PUT,
        }:
            self.options_metrics.invalid_contract_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Option contract type is missing "
                    "or unsupported"
                ),
                snapshot=snapshot,
            )

        if (
            strike is None
            or strike <= 0.0
        ):
            self.options_metrics.invalid_contract_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Option strike is missing or invalid"
                ),
                snapshot=snapshot,
            )

        if expiration is None:
            self.options_metrics.invalid_contract_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Option expiration is missing"
                ),
                snapshot=snapshot,
            )

        if dte is None:
            self.options_metrics.invalid_contract_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Option expiration could not be parsed"
                ),
                snapshot=snapshot,
            )

        if (
            dte < self.minimum_days_to_expiration
            or dte > self.maximum_days_to_expiration
        ):
            self.options_metrics.expired_contract_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Option expiration is outside the "
                    "configured DTE range"
                ),
                snapshot=snapshot,
            )

        if (
            self.require_real_quote
            and mark is None
            and last is None
            and bid is None
            and ask is None
        ):
            self.options_metrics.invalid_contract_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "No real option quote is available"
                ),
                snapshot=snapshot,
            )

        if (
            mark is not None
            and mark < self.minimum_mark
        ):
            self.options_metrics.invalid_contract_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Option mark is below the "
                    "configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            bid is not None
            and bid < self.minimum_bid
        ):
            self.options_metrics.invalid_contract_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Option bid is below the "
                    "configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            spread_pct is not None
            and spread_pct
            > self.max_bid_ask_spread_pct
        ):
            self.options_metrics.spread_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Option bid/ask spread exceeds "
                    f"{self.max_bid_ask_spread_pct:.4f}%"
                ),
                snapshot=snapshot,
            )

        if (
            volume is not None
            and volume < self.minimum_volume
        ):
            self.options_metrics.liquidity_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Option volume is below the "
                    "configured minimum"
                ),
                snapshot=snapshot,
            )

        if (
            open_interest is not None
            and open_interest
            < self.minimum_open_interest
        ):
            self.options_metrics.liquidity_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Option open interest is below "
                    "the configured minimum"
                ),
                snapshot=snapshot,
            )

        if delta is not None:
            absolute_delta = abs(
                delta
            )

            if (
                absolute_delta
                < self.minimum_absolute_delta
                or absolute_delta
                > self.maximum_absolute_delta
            ):
                self.options_metrics.invalid_contract_blocks += 1

                return OptionValidationResult(
                    valid=False,
                    reason=(
                        "Option delta is outside the "
                        "configured range"
                    ),
                    snapshot=snapshot,
                )

        if (
            self.require_tradable_flag
            and snapshot.tradable is False
        ):
            self.options_metrics.tradability_blocks += 1

            return OptionValidationResult(
                valid=False,
                reason=(
                    "Broker marks this option contract "
                    "as non-tradable"
                ),
                snapshot=snapshot,
            )

        if snapshot.tradable is None:
            warnings.append(
                "Provider did not return an explicit "
                "option tradable flag"
            )

        if volume is None:
            warnings.append(
                "Option volume is unavailable"
            )

        if open_interest is None:
            warnings.append(
                "Option open interest is unavailable"
            )

        if spread_pct is None:
            warnings.append(
                "Option bid/ask spread is unavailable"
            )

        if snapshot.implied_volatility is None:
            warnings.append(
                "Option implied volatility is unavailable"
            )

        if snapshot.delta is None:
            warnings.append(
                "Option delta is unavailable"
            )

        if snapshot.multiplier is None:
            warnings.append(
                "Option multiplier is unavailable"
            )

        return OptionValidationResult(
            valid=True,
            warnings=warnings,
            snapshot=snapshot,
        )

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
                    "Options capability is unavailable"
                )
            )

    async def after_scan(
        self,
        result: Mapping[str, Any],
    ) -> None:
        contracts = (
            result.get(
                "candidates",
                [],
            )
        )

        await self._emit_event(
            "OPTIONS_SCAN_COMPLETED",
            message=(
                "Options scan completed"
            ),
            data={
                "contract_candidate_count": (
                    len(contracts)
                    if isinstance(
                        contracts,
                        list,
                    )
                    else 0
                ),
                "underlying_candidate_count": (
                    self.options_metrics.underlying_candidates
                ),
                "chain_requests": (
                    self.options_metrics.chain_requests
                ),
            },
        )

    async def scan_market(
        self,
    ) -> dict[str, Any]:
        await self.before_scan()

        self.options_metrics.underlying_scans += 1

        underlying_result = (
            await super().scan_market()
        )

        underlying_candidates = (
            underlying_result.get(
                "candidates",
                [],
            )
        )

        if not isinstance(
            underlying_candidates,
            list,
        ):
            underlying_candidates = []

        self.options_metrics.underlying_candidates += (
            len(
                underlying_candidates
            )
        )

        contracts = (
            await self.enrich_contracts(
                [
                    _mapping(
                        candidate
                    )
                    for candidate
                    in underlying_candidates
                ]
            )
        )

        result = dict(
            underlying_result
        )

        result[
            "underlying_candidates"
        ] = serialize_value(
            underlying_candidates
        )

        result[
            "candidates"
        ] = contracts

        result[
            "contracts"
        ] = contracts

        result[
            "count"
        ] = len(
            contracts
        )

        result[
            "asset_class"
        ] = self.asset_class

        result[
            "instrument_type"
        ] = "option"

        await self.after_scan(
            result
        )

        return result

    # =========================================================================
    # CANDIDATE VALIDATION
    # =========================================================================

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
            return (
                False,
                capability.get(
                    "reason"
                )
                or (
                    "Options automation capability "
                    "is unavailable"
                ),
            )

        payload = (
            candidate.scanner_payload
        )

        underlying = normalize_symbol(
            _first(
                payload,
                UNDERLYING_SYMBOL_KEYS,
            )
        )

        contract_symbol = normalize_symbol(
            _first(
                payload,
                CONTRACT_SYMBOL_KEYS,
            )
        )

        option_payload = _mapping(
            payload.get(
                "option"
            )
        )

        if option_payload:
            merged_payload = {
                **payload,
                **option_payload,
            }
        else:
            merged_payload = dict(
                payload
            )

        if not underlying:
            underlying = normalize_symbol(
                _first(
                    merged_payload,
                    (
                        "underlying",
                        "underlying_symbol",
                    ),
                )
            )

        if not underlying:
            return (
                False,
                "Option underlying symbol is missing",
            )

        if not contract_symbol:
            contract_symbol = normalize_symbol(
                _first(
                    merged_payload,
                    CONTRACT_SYMBOL_KEYS,
                )
            )

        if not contract_symbol:
            return (
                False,
                "Option contract symbol is missing",
            )

        validation = (
            self._validate_contract_payload(
                underlying,
                {
                    **merged_payload,
                    "symbol": contract_symbol,
                },
            )
        )

        if not validation.valid:
            return (
                False,
                validation.reason,
            )

        if validation.snapshot is not None:
            candidate.scanner_payload[
                "option"
            ] = (
                validation.snapshot.to_dict()
            )

            self._contract_cache[
                validation.snapshot.symbol
            ] = validation.snapshot

        if validation.warnings:
            candidate.scanner_payload[
                "option_warnings"
            ] = list(
                validation.warnings
            )

        return (
            True,
            None,
        )

    # =========================================================================
    # CANDIDATE PREPARATION
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

        payload = (
            candidate.scanner_payload
        )

        option_payload = _mapping(
            payload.get(
                "option"
            )
        )

        contract_symbol = normalize_symbol(
            _first(
                option_payload,
                CONTRACT_SYMBOL_KEYS,
            )
            or _first(
                payload,
                CONTRACT_SYMBOL_KEYS,
            )
            or candidate.symbol
        )

        underlying = normalize_symbol(
            _first(
                option_payload,
                (
                    "underlying",
                    "underlying_symbol",
                ),
            )
            or _first(
                payload,
                (
                    "underlying",
                    "underlying_symbol",
                ),
            )
        )

        if not contract_symbol:
            candidate.state = (
                CANDIDATE_BLOCKED
            )

            return candidate

        snapshot = (
            self._contract_cache.get(
                contract_symbol
            )
        )

        if snapshot is None:
            validation = (
                self._validate_contract_payload(
                    underlying,
                    {
                        **payload,
                        **option_payload,
                        "symbol": contract_symbol,
                    },
                )
            )

            if (
                not validation.valid
                or validation.snapshot is None
            ):
                candidate.state = (
                    CANDIDATE_BLOCKED
                )

                return candidate

            snapshot = (
                validation.snapshot
            )

            self._contract_cache[
                snapshot.symbol
            ] = snapshot

        candidate.scanner_payload[
            "asset_class"
        ] = self.asset_class

        candidate.scanner_payload[
            "instrument_type"
        ] = "option"

        candidate.scanner_payload[
            "contract_symbol"
        ] = snapshot.symbol

        candidate.scanner_payload[
            "underlying"
        ] = snapshot.underlying

        candidate.scanner_payload[
            "option"
        ] = snapshot.to_dict()

        return candidate

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
            self.options_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Configured broker does not "
                "support options execution"
            )

            return (
                candidate,
                decision,
            )

        payload = (
            candidate.scanner_payload
        )

        option_payload = _mapping(
            payload.get(
                "option"
            )
        )

        contract_symbol = normalize_symbol(
            _first(
                option_payload,
                CONTRACT_SYMBOL_KEYS,
            )
            or _first(
                payload,
                CONTRACT_SYMBOL_KEYS,
            )
            or candidate.symbol
        )

        snapshot = (
            self._contract_cache.get(
                contract_symbol
            )
        )

        if snapshot is None:
            underlying = normalize_symbol(
                _first(
                    option_payload,
                    (
                        "underlying",
                        "underlying_symbol",
                    ),
                )
                or _first(
                    payload,
                    (
                        "underlying",
                        "underlying_symbol",
                    ),
                )
            )

            validation = (
                self._validate_contract_payload(
                    underlying,
                    {
                        **payload,
                        **option_payload,
                        "symbol": contract_symbol,
                    },
                )
            )

            if (
                not validation.valid
                or validation.snapshot is None
            ):
                self.options_metrics.execution_blocks += 1

                candidate.state = (
                    CANDIDATE_BLOCKED
                )

                decision.blocked = True

                decision.block_reason = (
                    validation.reason
                    or (
                        "Option contract failed "
                        "execution validation"
                    )
                )

                return (
                    candidate,
                    decision,
                )

            snapshot = (
                validation.snapshot
            )

            self._contract_cache[
                snapshot.symbol
            ] = snapshot

        if snapshot.tradable is False:
            self.options_metrics.tradability_blocks += 1
            self.options_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Broker marks the selected option "
                "contract as non-tradable"
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
            self.options_metrics.spread_blocks += 1
            self.options_metrics.execution_blocks += 1

            candidate.state = (
                CANDIDATE_BLOCKED
            )

            decision.blocked = True

            decision.block_reason = (
                "Current option spread exceeds "
                "the configured execution threshold"
            )

            return (
                candidate,
                decision,
            )

        if (
            decision.action == ACTION_BUY
        ):
            if snapshot.close_only is True:
                self.options_metrics.buy_blocks += 1
                self.options_metrics.execution_blocks += 1

                candidate.state = (
                    CANDIDATE_BLOCKED
                )

                decision.blocked = True

                decision.block_reason = (
                    "Option contract is close-only"
                )

                return (
                    candidate,
                    decision,
                )

            if snapshot.buyable is False:
                self.options_metrics.buy_blocks += 1
                self.options_metrics.execution_blocks += 1

                candidate.state = (
                    CANDIDATE_BLOCKED
                )

                decision.blocked = True

                decision.block_reason = (
                    "Broker does not allow purchases "
                    f"of {snapshot.symbol}"
                )

                return (
                    candidate,
                    decision,
                )

        if (
            decision.action == ACTION_SELL
        ):
            can_sell = (
                await self._can_sell_option(
                    snapshot
                )
            )

            if not can_sell:
                self.options_metrics.sell_blocks += 1
                self.options_metrics.execution_blocks += 1

                candidate.state = (
                    CANDIDATE_BLOCKED
                )

                decision.blocked = True

                decision.block_reason = (
                    "SELL decision cannot open an "
                    "unverified naked short option. "
                    "No existing long contract position "
                    "was confirmed."
                )

                return (
                    candidate,
                    decision,
                )

        multiplier = (
            snapshot.multiplier
            if snapshot.multiplier is not None
            else OPTION_MULTIPLIER_DEFAULT
        )

        decision.analysis.setdefault(
            "option",
            snapshot.to_dict(),
        )

        decision.analysis[
            "asset_class"
        ] = self.asset_class

        decision.analysis[
            "instrument_type"
        ] = "option"

        decision.analysis[
            "execution_constraints"
        ] = {
            "contract_symbol": (
                snapshot.symbol
            ),
            "underlying": (
                snapshot.underlying
            ),
            "option_type": (
                snapshot.option_type
            ),
            "strike": (
                snapshot.strike
            ),
            "expiration": (
                snapshot.expiration
            ),
            "days_to_expiration": (
                snapshot.days_to_expiration
            ),
            "multiplier": (
                multiplier
            ),
            "bid": (
                snapshot.bid
            ),
            "ask": (
                snapshot.ask
            ),
            "mark": (
                snapshot.mark
            ),
            "spread_pct": (
                snapshot.spread_pct
            ),
            "volume": (
                snapshot.volume
            ),
            "open_interest": (
                snapshot.open_interest
            ),
            "maximum_position_fraction": (
                self.maximum_position_fraction
            ),
            "maximum_options_exposure_fraction": (
                self.maximum_options_exposure_fraction
            ),
        }

        return (
            candidate,
            decision,
        )

    async def _can_sell_option(
        self,
        snapshot: OptionContractSnapshot,
    ) -> bool:
        if await self.has_open_position(
            snapshot.symbol
        ):
            return True

        return False

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
                "OPTIONS_EXECUTION_BLOCKED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    decision.block_reason
                    or (
                        "Options execution blocked"
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
                "OPTIONS_HOLD",
                symbol=candidate.symbol,
                message=(
                    f"{candidate.symbol} remains "
                    "under options monitoring"
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
                "OPTIONS_DECISION_SKIPPED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=(
                    "Unsupported options decision "
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

    async def _refresh_position_contract(
        self,
        position: Any,
    ) -> OptionContractSnapshot | None:
        contract_symbol = normalize_symbol(
            getattr(
                position,
                "symbol",
                None,
            )
        )

        raw = _mapping(
            getattr(
                position,
                "raw",
                {},
            )
        )

        option_raw = _mapping(
            raw.get(
                "option"
            )
        )

        underlying = normalize_symbol(
            _first(
                option_raw,
                (
                    "underlying",
                    "underlying_symbol",
                ),
            )
            or _first(
                raw,
                (
                    "underlying",
                    "underlying_symbol",
                ),
            )
        )

        if not contract_symbol:
            return None

        if not underlying:
            cached = (
                self._contract_cache.get(
                    contract_symbol
                )
            )

            if cached is not None:
                underlying = (
                    cached.underlying
                )

        if not underlying:
            return (
                self._contract_cache.get(
                    contract_symbol
                )
            )

        try:
            chain = (
                await self._request_chain(
                    underlying,
                    force=True,
                )
            )

            scan_result = (
                await self._scan_chain(
                    underlying,
                    chain,
                )
            )

        except Exception:
            self.options_metrics.position_quote_failures += 1
            return None

        contracts = (
            scan_result.get(
                "contracts",
                [],
            )
        )

        if not isinstance(
            contracts,
            list,
        ):
            return None

        for raw_contract in contracts:
            payload = _mapping(
                raw_contract
            )

            symbol = normalize_symbol(
                _first(
                    payload,
                    CONTRACT_SYMBOL_KEYS,
                )
            )

            if symbol != contract_symbol:
                continue

            validation = (
                self._validate_contract_payload(
                    underlying,
                    payload,
                )
            )

            if validation.snapshot is None:
                return None

            snapshot = (
                validation.snapshot
            )

            async with self._contract_cache_lock:
                self._contract_cache[
                    snapshot.symbol
                ] = snapshot

            return snapshot

        return None

    async def monitor_position(
        self,
        position: Any,
    ) -> None:
        await super().monitor_position(
            position
        )

        contract_symbol = normalize_symbol(
            getattr(
                position,
                "symbol",
                None,
            )
        )

        if not contract_symbol:
            return

        snapshot = (
            await self._refresh_position_contract(
                position
            )
        )

        if snapshot is None:
            await self._emit_event(
                "OPTION_POSITION_QUOTE_FAILED",
                severity="WARNING",
                symbol=contract_symbol,
                message=(
                    "Unable to refresh real option "
                    "contract data"
                ),
            )

            return

        current_price = (
            snapshot.mark
            if snapshot.mark is not None
            else snapshot.last
        )

        if current_price is None:
            current_price = _mid_price(
                snapshot.bid,
                snapshot.ask,
            )

        if current_price is not None:
            position.current_price = (
                current_price
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

            multiplier = (
                snapshot.multiplier
                if snapshot.multiplier is not None
                else OPTION_MULTIPLIER_DEFAULT
            )

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
                    current_price
                    - entry_price
                )

                pnl = (
                    price_delta
                    * quantity
                    * multiplier
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

        position.raw = {
            **_mapping(
                getattr(
                    position,
                    "raw",
                    {},
                )
            ),
            "option": (
                snapshot.to_dict()
            ),
        }

        if (
            snapshot.spread_pct is not None
            and snapshot.spread_pct
            > self.max_bid_ask_spread_pct
        ):
            await self._emit_event(
                "OPTION_SPREAD_WARNING",
                severity="WARNING",
                symbol=contract_symbol,
                message=(
                    f"{contract_symbol} spread exceeds "
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

        if (
            snapshot.days_to_expiration
            is not None
            and snapshot.days_to_expiration
            <= 1
        ):
            await self._emit_event(
                "OPTION_EXPIRATION_WARNING",
                severity="WARNING",
                symbol=contract_symbol,
                message=(
                    f"{contract_symbol} is near expiration"
                ),
                data={
                    "expiration": (
                        snapshot.expiration
                    ),
                    "days_to_expiration": (
                        snapshot.days_to_expiration
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
            "options_runtime"
        ] = {
            "metrics": (
                self.options_metrics.to_dict()
            ),
            "capability": (
                serialize_value(
                    self._capability_cache
                )
            ),
            "capability_checked_at": (
                self._capability_checked_at
            ),
            "cached_contracts": (
                len(
                    self._contract_cache
                )
            ),
            "cached_chains": (
                len(
                    self._chain_cache
                )
            ),
            "configuration": {
                "underlying_candidate_limit": (
                    self.candidate_limit
                ),
                "chain_underlying_limit": (
                    self.chain_underlying_limit
                ),
                "contract_candidate_limit": (
                    self.contract_candidate_limit
                ),
                "max_bid_ask_spread_pct": (
                    self.max_bid_ask_spread_pct
                ),
                "minimum_bid": (
                    self.minimum_bid
                ),
                "minimum_mark": (
                    self.minimum_mark
                ),
                "minimum_volume": (
                    self.minimum_volume
                ),
                "minimum_open_interest": (
                    self.minimum_open_interest
                ),
                "minimum_days_to_expiration": (
                    self.minimum_days_to_expiration
                ),
                "maximum_days_to_expiration": (
                    self.maximum_days_to_expiration
                ),
                "minimum_absolute_delta": (
                    self.minimum_absolute_delta
                ),
                "maximum_absolute_delta": (
                    self.maximum_absolute_delta
                ),
                "maximum_position_fraction": (
                    self.maximum_position_fraction
                ),
                "maximum_options_exposure_fraction": (
                    self.maximum_options_exposure_fraction
                ),
                "require_real_chain": (
                    self.require_real_chain
                ),
                "require_real_quote": (
                    self.require_real_quote
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

        universe = (
            self.universe()
        )

        samples: list[
            dict[str, Any]
        ] = []

        for underlying in universe[
            : min(
                3,
                self.chain_underlying_limit,
            )
        ]:
            underlying = normalize_symbol(
                underlying
            )

            if not underlying:
                continue

            sample: dict[str, Any] = {
                "underlying": underlying,
            }

            try:
                chain = (
                    await self._request_chain(
                        underlying,
                        force=True,
                    )
                )

                scan_result = (
                    await self._scan_chain(
                        underlying,
                        chain,
                    )
                )

                contracts = (
                    scan_result.get(
                        "contracts",
                        [],
                    )
                )

                sample[
                    "chain_available"
                ] = chain is not None

                sample[
                    "scanner_contract_count"
                ] = (
                    len(contracts)
                    if isinstance(
                        contracts,
                        list,
                    )
                    else 0
                )

                validated = 0

                if isinstance(
                    contracts,
                    list,
                ):
                    for contract in contracts[
                        :10
                    ]:
                        validation = (
                            self._validate_contract_payload(
                                underlying,
                                _mapping(
                                    contract
                                ),
                            )
                        )

                        if validation.valid:
                            validated += 1

                sample[
                    "validated_sample_contracts"
                ] = validated

            except Exception as exc:
                sample[
                    "chain_available"
                ] = False

                sample[
                    "error"
                ] = str(
                    exc
                )

            samples.append(
                sample
            )

        return {
            "asset_class": (
                self.asset_class
            ),
            "capability": (
                capability
            ),
            "underlying_universe_size": (
                len(
                    universe
                )
            ),
            "samples": (
                samples
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

    async def clear_contract_cache(
        self,
    ) -> None:
        async with self._contract_cache_lock:
            self._contract_cache.clear()

        async with self._chain_cache_lock:
            self._chain_cache.clear()


# =============================================================================
# SINGLETON
# =============================================================================


options_automation = OptionsAutomation()