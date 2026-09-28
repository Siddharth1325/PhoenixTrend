from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from ..domain import (
    AccountState,
    AssetType,
    ExecutionMode,
    Side,
    TradeIntent,
)
from ..services.decision_engine import decision_engine
from ..services.execution import execution_service
from ..services.market_safety import market_safety_service


class AutomaticEngine:
    """
    PhoenixTrend Automatic Trading Engine.

    Responsibilities
    ----------------
    - Own automatic-engine runtime state.
    - Analyze opportunities through the shared DecisionEngine.
    - Honor pinned or automatically selected strategies.
    - Require actionable BUY / SELL decisions.
    - Require genuine live execution-market data.
    - Enforce Market Safety before creating an intent.
    - Create AUTOMATIC TradeIntent objects.
    - Route every approved intent through ExecutionService.
    - Never bypass the shared Risk / Safety / Broker execution path.
    - Never talk directly to a broker.
    - Never fabricate prices, positions, P&L, market data or fills.
    - Remain asset-aware instead of assuming every instrument is equity.
    - Revalidate engine state immediately before execution.

    Execution path
    --------------
        DecisionEngine
            ↓
        Live execution-market validation
            ↓
        Market Safety
            ↓
        Strategy selection
            ↓
        AutomaticEngine creates TradeIntent
            ↓
        ExecutionService
            ↓
        Market Safety re-check
            ↓
        Risk
            ↓
        Broker capability
            ↓
        Broker
    """

    engine_type = "automatic"

    _ACTIONABLE_SIGNALS = {
        "BUY",
        "SELL",
    }

    _HOLD_SIGNALS = {
        "",
        "HOLD",
        "WAIT",
        "NONE",
        "NO_TRADE",
        "NO TRADE",
        "NEUTRAL",
    }

    _ASSET_ALIASES = {
        "STOCK": AssetType.EQUITY,
        "STOCKS": AssetType.EQUITY,
        "EQUITY": AssetType.EQUITY,
        "EQUITIES": AssetType.EQUITY,
        "ETF": AssetType.ETF,
        "ETFS": AssetType.ETF,
        "CRYPTO": AssetType.CRYPTO,
        "CRYPTOCURRENCY": AssetType.CRYPTO,
        "CRYPTOCURRENCIES": AssetType.CRYPTO,
        "OPTION": AssetType.OPTION,
        "OPTIONS": AssetType.OPTION,
        "FOREX": AssetType.FOREX,
        "FX": AssetType.FOREX,
        "COMMODITY": AssetType.COMMODITY,
        "COMMODITIES": AssetType.COMMODITY,
    }

    _STREAM_MODE_VALUES = {
        "stream",
        "streaming",
        "websocket",
        "ws",
        "realtime",
        "real-time",
        "real_time",
        "live",
    }

    _REALTIME_FLAG_KEYS = (
        "real_time_stream",
        "realtime",
        "real_time",
        "live",
        "is_live",
    )

    _PRICE_KEYS = (
        "price",
        "last",
        "last_price",
        "mark",
        "mark_price",
        "current_price",
        "market_price",
    )

    _BID_KEYS = (
        "bid",
        "bid_price",
        "best_bid",
    )

    _ASK_KEYS = (
        "ask",
        "ask_price",
        "best_ask",
    )

    _TIMESTAMP_KEYS = (
        "timestamp",
        "as_of",
        "updated_at",
        "time",
        "event_time",
    )

    _PROVIDER_KEYS = (
        "provider",
        "source",
        "data_provider",
    )

    _PROVIDER_MODE_KEYS = (
        "provider_mode",
        "mode",
        "feed_mode",
        "transport",
    )

    def __init__(
        self,
        strategy_picker: Any | None = None,
        execution_engine: Any | None = None,
        market_safety: Any | None = None,
        decision_service: Any | None = None,
    ) -> None:
        self.strategy_picker = strategy_picker

        self.execution_engine = (
            execution_engine
            or execution_service
        )

        self.market_safety = (
            market_safety
            or market_safety_service
        )

        self.decision_service = (
            decision_service
            or decision_engine
        )

        self.enabled = False
        self.emergency_stop = False
        self.new_entries_paused = False

        self.selected_strategy: str | None = None
        self.auto_select_strategy = True

        self.processed_opportunities = 0
        self.trade_intents_created = 0
        self.executions_requested = 0

        self.blocked_live_market = 0
        self.blocked_market_safety = 0
        self.blocked_engine_state = 0
        self.no_trade_decisions = 0
        self.execution_errors = 0

        self.last_symbol: str | None = None
        self.last_status: str | None = None
        self.last_strategy: str | None = None
        self.last_action: str | None = None
        self.last_execution_state: str | None = None
        self.last_reason: str | None = None
        self.last_processed_at: str | None = None
        self.last_execution_provider: str | None = None
        self.last_asset_type: str | None = None

    # ======================================================================
    # START
    # ======================================================================

    def start(
        self,
        strategy_name: str | None = None,
        auto_select: bool = True,
    ) -> dict[str, Any]:
        if self.emergency_stop:
            raise RuntimeError(
                "Emergency Stop is active"
            )

        self.auto_select_strategy = bool(
            auto_select
        )

        if strategy_name:
            self.selected_strategy = (
                self._resolve_strategy(
                    strategy_name
                )
            )

            self.auto_select_strategy = False

        elif not self.auto_select_strategy:
            if not self.selected_strategy:
                raise ValueError(
                    "A strategy must be selected when "
                    "automatic strategy selection is disabled"
                )

        self.enabled = True
        self.new_entries_paused = False
        self.last_status = "RUNNING"
        self.last_reason = None

        return self.status()

    # ======================================================================
    # STOP
    # ======================================================================

    def stop(
        self,
    ) -> dict[str, Any]:
        """
        Stop creation of new automatic entries.

        Position monitoring and exit/risk management belong to the shared
        position-monitoring/runtime services. This method intentionally does
        not close positions and does not disable those services.
        """
        self.enabled = False
        self.new_entries_paused = True
        self.last_status = "STOPPED"
        self.last_reason = (
            "New automatic entries are disabled"
        )

        return self.status()

    # ======================================================================
    # STRATEGY SELECTION
    # ======================================================================

    def select_strategy(
        self,
        name: str,
    ) -> dict[str, Any]:
        self.selected_strategy = (
            self._resolve_strategy(
                name
            )
        )

        self.auto_select_strategy = False

        return self.status()

    def enable_auto_strategy_selection(
        self,
    ) -> dict[str, Any]:
        self.auto_select_strategy = True
        self.selected_strategy = None

        return self.status()

    # ======================================================================
    # PAUSE / RESUME
    # ======================================================================

    def pause_new_entries(
        self,
    ) -> dict[str, Any]:
        self.new_entries_paused = True
        self.last_status = "PAUSED"
        self.last_reason = (
            "New automatic entries are paused"
        )

        return self.status()

    def resume_new_entries(
        self,
    ) -> dict[str, Any]:
        if self.emergency_stop:
            raise RuntimeError(
                "Cannot resume while Emergency Stop is active"
            )

        if not self.enabled:
            raise RuntimeError(
                "Automatic Engine is disabled"
            )

        self.new_entries_paused = False
        self.last_status = "RUNNING"
        self.last_reason = None

        return self.status()

    # ======================================================================
    # EMERGENCY STOP
    # ======================================================================

    def activate_emergency_stop(
        self,
    ) -> dict[str, Any]:
        self.emergency_stop = True
        self.enabled = False
        self.new_entries_paused = True
        self.last_status = "EMERGENCY_STOP"
        self.last_reason = (
            "Emergency Stop is active"
        )

        return self.status()

    def clear_emergency_stop(
        self,
    ) -> dict[str, Any]:
        # Clearing Emergency Stop must never restart automatic trading.
        self.emergency_stop = False
        self.enabled = False
        self.new_entries_paused = True
        self.last_status = "STOPPED"
        self.last_reason = (
            "Emergency Stop cleared; automatic trading remains stopped"
        )

        return self.status()

    # ======================================================================
    # ANALYZE
    # ======================================================================

    async def analyze(
        self,
        *,
        symbol: str,
        market_data: Any = None,
        strategy_name: str | None = None,
        strategy_config: Any = None,
    ) -> dict[str, Any]:
        """
        Preview analysis only.

        This method never creates or submits an order.

        DecisionEngine remains the authority for normalized market context,
        strategy evaluation and final BUY / SELL / HOLD analysis.
        """
        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )

        decision = await self._call_decision_analyze(
            normalized_symbol,
            force=False,
        )

        requested_strategy = None

        if strategy_name:
            canonical = (
                self._resolve_strategy(
                    strategy_name
                )
            )

            requested_strategy = (
                self._find_strategy(
                    decision,
                    canonical,
                )
            )

        return {
            **decision,
            "engine": self.engine_type,
            "requested_strategy": requested_strategy,
            "requested_strategy_name": strategy_name,
            "strategy_config_supplied": (
                strategy_config is not None
            ),
            "market_data_supplied": (
                market_data is not None
            ),
            "preview_only": True,
        }

    # ======================================================================
    # PROCESS
    # ======================================================================

    async def process(
        self,
        *,
        symbol: str,
        market_data: Any = None,
        quantity: float,
        account: AccountState,
        strategy_name: str | None = None,
        strategy_config: Any = None,
        automation_enabled: bool = True,
        automation_id: str | None = None,
        asset_class: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze one automatic-trading opportunity and submit an order only
        when the complete PhoenixTrend execution pipeline approves it.

        This method never bypasses:
            - DecisionEngine
            - live execution-market validation
            - Market Safety
            - ExecutionService
            - Risk
            - broker capability checks
        """
        try:
            self._ready()
        except Exception:
            self.blocked_engine_state += 1
            raise

        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )

        normalized_quantity = (
            self._normalize_quantity(
                quantity
            )
        )

        if account is None:
            raise ValueError(
                "Account state is required"
            )

        self.processed_opportunities += 1

        self.last_symbol = normalized_symbol
        self.last_action = None
        self.last_strategy = None
        self.last_execution_state = None
        self.last_reason = None
        self.last_processed_at = (
            self._utc_now()
        )
        self.last_execution_provider = None
        self.last_asset_type = None

        # ==================================================================
        # DECISION
        # ==================================================================

        decision = await self._call_decision_analyze(
            normalized_symbol,
            force=True,
        )

        if not isinstance(
            decision,
            dict,
        ):
            return self._result(
                symbol=normalized_symbol,
                status="NO_DECISION",
                reason=(
                    "Decision Engine did not return "
                    "a valid decision payload"
                ),
                execution=None,
            )

        analysis_market = (
            decision.get("market")
            or {}
        )

        if (
            not isinstance(
                analysis_market,
                dict,
            )
            or not analysis_market
        ):
            return self._result(
                symbol=normalized_symbol,
                status="NO_MARKET_DATA",
                reason=(
                    "Decision Engine did not return "
                    "a normalized market snapshot"
                ),
                decision=decision,
                execution=None,
            )

        # ==================================================================
        # ASSET TYPE
        # ==================================================================

        resolved_asset_type = (
            self._resolve_requested_asset_type(
                analysis_market,
                asset_class,
            )
        )

        self.last_asset_type = (
            self._asset_type_value(
                resolved_asset_type
            )
        )

        # ==================================================================
        # LIVE EXECUTION MARKET
        # ==================================================================

        live_market = (
            self._validate_live_market(
                normalized_symbol,
                market_data,
                expected_asset_type=resolved_asset_type,
            )
        )

        if live_market is None:
            self.blocked_live_market += 1

            return self._result(
                symbol=normalized_symbol,
                status="BLOCKED_LIVE_MARKET_DATA",
                reason=(
                    "Automatic execution requires a genuine "
                    "real-time provider snapshot for the same "
                    "symbol and asset class"
                ),
                decision=decision,
                execution=None,
            )

        decision_market = (
            self._merge_execution_market(
                analysis_market,
                live_market,
                expected_asset_type=resolved_asset_type,
            )
        )

        self.last_execution_provider = str(
            decision_market.get(
                "execution_provider"
            )
            or decision_market.get(
                "provider"
            )
            or ""
        ).strip() or None

        # ==================================================================
        # MARKET SAFETY
        # ==================================================================

        safety = await self._call_market_safety(
            decision_market
        )

        if (
            not isinstance(
                safety,
                dict,
            )
            or not safety.get(
                "safe",
                False,
            )
        ):
            self.blocked_market_safety += 1

            return self._result(
                symbol=normalized_symbol,
                status="BLOCKED_MARKET_SAFETY",
                reason=(
                    self._extract_reason(
                        safety
                    )
                    or (
                        "Market Safety rejected "
                        "the execution snapshot"
                    )
                ),
                decision=decision,
                market_safety=safety,
                execution=None,
            )

        # ==================================================================
        # CHOOSE STRATEGY
        # ==================================================================

        requested_strategy = strategy_name

        if (
            requested_strategy is None
            and not self.auto_select_strategy
        ):
            requested_strategy = (
                self.selected_strategy
            )

        chosen: dict[str, Any] | None = None

        # ------------------------------------------------------------------
        # PINNED STRATEGY
        # ------------------------------------------------------------------

        if requested_strategy:
            canonical = (
                self._resolve_strategy(
                    requested_strategy
                )
            )

            candidate = (
                self._find_strategy(
                    decision,
                    canonical,
                )
            )

            if candidate is None:
                self.no_trade_decisions += 1

                return self._result(
                    symbol=normalized_symbol,
                    status="NO_TRADE",
                    reason=(
                        "Requested strategy was not returned "
                        "by Decision Engine"
                    ),
                    requested_strategy=canonical,
                    decision=decision,
                    market_safety=safety,
                    execution=None,
                )

            candidate_signal = (
                self._normalize_signal(
                    candidate.get(
                        "signal"
                    )
                )
            )

            if (
                candidate_signal
                not in self._ACTIONABLE_SIGNALS
            ):
                self.no_trade_decisions += 1

                return self._result(
                    symbol=normalized_symbol,
                    status="NO_TRADE",
                    reason=(
                        "Pinned strategy is not actionable"
                    ),
                    requested_strategy=canonical,
                    decision=decision,
                    market_safety=safety,
                    execution=None,
                )

            chosen = candidate

        # ------------------------------------------------------------------
        # AUTOMATIC STRATEGY SELECTION
        # ------------------------------------------------------------------

        else:
            decision_action = (
                self._normalize_signal(
                    decision.get(
                        "action"
                    )
                )
            )

            if (
                decision_action
                not in self._ACTIONABLE_SIGNALS
            ):
                self.no_trade_decisions += 1

                return self._result(
                    symbol=normalized_symbol,
                    status="NO_TRADE",
                    reason=(
                        "Decision Engine returned HOLD"
                    ),
                    decision=decision,
                    market_safety=safety,
                    execution=None,
                )

            selected = (
                decision.get(
                    "selected"
                )
            )

            if not isinstance(
                selected,
                dict,
            ):
                self.no_trade_decisions += 1

                return self._result(
                    symbol=normalized_symbol,
                    status="NO_TRADE",
                    reason=(
                        "Decision Engine did not select "
                        "an actionable strategy"
                    ),
                    decision=decision,
                    market_safety=safety,
                    execution=None,
                )

            chosen = selected

        # ==================================================================
        # VALIDATE CHOSEN SIGNAL
        # ==================================================================

        if chosen is None:
            self.no_trade_decisions += 1

            return self._result(
                symbol=normalized_symbol,
                status="NO_TRADE",
                reason=(
                    "No strategy was selected"
                ),
                decision=decision,
                market_safety=safety,
                execution=None,
            )

        chosen_signal = (
            self._normalize_signal(
                chosen.get(
                    "signal"
                )
            )
        )

        if (
            chosen_signal
            not in self._ACTIONABLE_SIGNALS
        ):
            self.no_trade_decisions += 1

            return self._result(
                symbol=normalized_symbol,
                status="NO_TRADE",
                reason=(
                    "Selected strategy signal "
                    "is not BUY or SELL"
                ),
                decision=decision,
                market_safety=safety,
                execution=None,
            )

        decision_action = (
            self._normalize_signal(
                decision.get(
                    "action"
                )
            )
        )

        if (
            not requested_strategy
            and decision_action
            in self._ACTIONABLE_SIGNALS
            and chosen_signal
            != decision_action
        ):
            self.no_trade_decisions += 1

            return self._result(
                symbol=normalized_symbol,
                status="NO_TRADE",
                reason=(
                    "Selected strategy signal does not "
                    "match Decision Engine action"
                ),
                decision=decision,
                market_safety=safety,
                execution=None,
            )

        chosen_strategy = str(
            chosen.get(
                "strategy",
                "Unknown",
            )
        ).strip()

        if not chosen_strategy:
            chosen_strategy = "Unknown"

        self.last_action = chosen_signal
        self.last_strategy = chosen_strategy

        # ==================================================================
        # RECHECK ENGINE STATE
        # ==================================================================

        try:
            self._ready()
        except Exception:
            self.blocked_engine_state += 1
            raise

        # ==================================================================
        # RECHECK LIVE EXECUTION SNAPSHOT
        # ==================================================================

        revalidated_live_market = (
            self._validate_live_market(
                normalized_symbol,
                market_data,
                expected_asset_type=resolved_asset_type,
            )
        )

        if revalidated_live_market is None:
            self.blocked_live_market += 1

            return self._result(
                symbol=normalized_symbol,
                status="BLOCKED_LIVE_MARKET_DATA",
                reason=(
                    "Live execution snapshot failed "
                    "revalidation before intent creation"
                ),
                decision=decision,
                market_safety=safety,
                execution=None,
            )

        decision_market = (
            self._merge_execution_market(
                analysis_market,
                revalidated_live_market,
                expected_asset_type=resolved_asset_type,
            )
        )

        # ==================================================================
        # MARKET SAFETY RECHECK BEFORE INTENT
        # ==================================================================

        safety = await self._call_market_safety(
            decision_market
        )

        if (
            not isinstance(
                safety,
                dict,
            )
            or not safety.get(
                "safe",
                False,
            )
        ):
            self.blocked_market_safety += 1

            return self._result(
                symbol=normalized_symbol,
                status="BLOCKED_MARKET_SAFETY",
                reason=(
                    self._extract_reason(
                        safety
                    )
                    or (
                        "Market Safety rejected the "
                        "final execution snapshot"
                    )
                ),
                decision=decision,
                market_safety=safety,
                execution=None,
            )

        # ==================================================================
        # REFERENCE PRICE
        # ==================================================================

        reference_price = (
            self._reference_price(
                decision_market
            )
        )

        # ==================================================================
        # TRADE INTENT
        # ==================================================================

        intent = TradeIntent(
            intent_id=(
                "ti_"
                + uuid4().hex[:12]
            ),
            symbol=normalized_symbol,
            asset_type=resolved_asset_type,
            side=Side(
                chosen_signal
            ),
            qty=normalized_quantity,
            reference_price=reference_price,
            strategy=chosen_strategy,
            automation_id=automation_id,
            execution_mode=(
                ExecutionMode.AUTOMATIC
            ),
            stop=(
                self._optional_number(
                    chosen.get(
                        "stop"
                    )
                )
            ),
            target=(
                self._optional_number(
                    chosen.get(
                        "target"
                    )
                )
            ),
        )

        self.trade_intents_created += 1

        # ==================================================================
        # FINAL STATE CHECK
        # ==================================================================

        try:
            self._ready()
        except Exception:
            self.blocked_engine_state += 1
            raise

        if not bool(
            automation_enabled
        ):
            return self._result(
                symbol=normalized_symbol,
                status="BLOCKED_AUTOMATION_DISABLED",
                reason=(
                    "The owning automation is disabled"
                ),
                decision=decision,
                market_safety=safety,
                requested_strategy=(
                    requested_strategy
                ),
                intent=(
                    self._intent_dump(
                        intent
                    )
                ),
                execution=None,
            )

        # ==================================================================
        # EXECUTION
        # ==================================================================

        self.executions_requested += 1

        try:
            result = (
                await self._call_execution_process(
                    intent=intent,
                    account=account,
                    automation_enabled=True,
                    user_approved=False,
                    market_data=decision_market,
                )
            )

        except Exception as exc:
            self.execution_errors += 1

            self.last_execution_state = (
                "EXECUTION_ERROR"
            )

            self.last_status = (
                "EXECUTION_ERROR"
            )

            self.last_reason = str(
                exc
            )

            raise

        if not isinstance(
            result,
            dict,
        ):
            result = {
                "state": "UNKNOWN",
                "result": result,
            }

        execution_state = str(
            result.get(
                "state",
                "UNKNOWN",
            )
        ).strip().upper()

        if not execution_state:
            execution_state = "UNKNOWN"

        self.last_execution_state = (
            execution_state
        )

        self.last_status = (
            execution_state
        )

        return self._result(
            symbol=normalized_symbol,
            status=execution_state,
            decision=decision,
            market_safety=safety,
            requested_strategy=(
                requested_strategy
            ),
            intent=(
                self._intent_dump(
                    intent
                )
            ),
            execution=result,
            strategy_config_supplied=(
                strategy_config is not None
            ),
            market_data_supplied=(
                market_data is not None
            ),
        )

    # ======================================================================
    # DECISION SERVICE INVOCATION
    # ======================================================================

    async def _call_decision_analyze(
        self,
        symbol: str,
        *,
        force: bool,
    ) -> dict[str, Any]:
        method = getattr(
            self.decision_service,
            "analyze",
            None,
        )

        if not callable(
            method
        ):
            raise RuntimeError(
                "Decision Engine analyze() is unavailable"
            )

        try:
            result = method(
                symbol,
                force=force,
            )
        except TypeError:
            result = method(
                symbol
            )

        if inspect.isawaitable(
            result
        ):
            result = await result

        if not isinstance(
            result,
            dict,
        ):
            raise RuntimeError(
                "Decision Engine returned an invalid response"
            )

        return result

    # ======================================================================
    # MARKET SAFETY INVOCATION
    # ======================================================================

    async def _call_market_safety(
        self,
        market: dict[str, Any],
    ) -> dict[str, Any]:
        method = getattr(
            self.market_safety,
            "validate",
            None,
        )

        if not callable(
            method
        ):
            raise RuntimeError(
                "Market Safety validate() is unavailable"
            )

        try:
            result = method(
                market,
                require_provider_approval=True,
            )
        except TypeError:
            result = method(
                market
            )

        if inspect.isawaitable(
            result
        ):
            result = await result

        if isinstance(
            result,
            dict,
        ):
            return result

        if isinstance(
            result,
            bool,
        ):
            return {
                "safe": result,
            }

        raise RuntimeError(
            "Market Safety returned an invalid response"
        )

    # ======================================================================
    # EXECUTION SERVICE INVOCATION
    # ======================================================================

    async def _call_execution_process(
        self,
        *,
        intent: TradeIntent,
        account: AccountState,
        automation_enabled: bool,
        user_approved: bool,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:
        method = getattr(
            self.execution_engine,
            "process",
            None,
        )

        if not callable(
            method
        ):
            raise RuntimeError(
                "ExecutionService process() is unavailable"
            )

        result = method(
            intent=intent,
            account=account,
            automation_enabled=automation_enabled,
            user_approved=user_approved,
            market_data=market_data,
        )

        if inspect.isawaitable(
            result
        ):
            result = await result

        if isinstance(
            result,
            dict,
        ):
            return result

        return {
            "state": "UNKNOWN",
            "result": result,
        }

    # ======================================================================
    # LIVE EXECUTION MARKET
    # ======================================================================

    @classmethod
    def _validate_live_market(
        cls,
        symbol: str,
        market_data: Any,
        *,
        expected_asset_type: AssetType | None = None,
    ) -> dict[str, Any] | None:
        """
        Validate a real execution-market snapshot.

        This intentionally does NOT hardcode Alpaca. The configured broker /
        data-provider pipeline determines the provider. AutomaticEngine only
        requires that the supplied snapshot explicitly identifies itself as
        genuine, real-time, non-simulated market data for the same instrument.

        Provider-specific entitlement, feed and broker-capability validation
        remains inside the provider / ExecutionService layers.
        """
        if not isinstance(
            market_data,
            dict,
        ):
            return None

        live_symbol = str(
            market_data.get(
                "symbol"
            )
            or ""
        ).strip().upper()

        if live_symbol != symbol:
            return None

        provider = (
            cls._first_text(
                market_data,
                cls._PROVIDER_KEYS,
            )
        )

        if not provider:
            return None

        provider_mode = (
            cls._first_text(
                market_data,
                cls._PROVIDER_MODE_KEYS,
            )
        )

        realtime_flag = (
            cls._first_bool(
                market_data,
                cls._REALTIME_FLAG_KEYS,
            )
        )

        simulated = (
            cls._optional_bool(
                market_data.get(
                    "simulated"
                )
            )
        )

        if simulated is not False:
            return None

        if realtime_flag is not True:
            if (
                provider_mode is None
                or provider_mode.lower()
                not in cls._STREAM_MODE_VALUES
            ):
                return None

        if (
            provider_mode is not None
            and provider_mode.lower()
            not in cls._STREAM_MODE_VALUES
            and realtime_flag is not True
        ):
            return None

        price = (
            cls._market_price(
                market_data
            )
        )

        if (
            price is None
            or price <= 0
        ):
            return None

        timestamp = (
            cls._market_timestamp(
                market_data
            )
        )

        if timestamp is None:
            return None

        if expected_asset_type is not None:
            raw_asset = (
                market_data.get(
                    "asset_type"
                )
                or market_data.get(
                    "asset_class"
                )
                or market_data.get(
                    "type"
                )
            )

            if raw_asset is not None:
                try:
                    actual_asset_type = (
                        cls._asset_type_from_value(
                            raw_asset
                        )
                    )
                except RuntimeError:
                    return None

                if (
                    actual_asset_type
                    != expected_asset_type
                ):
                    return None

        normalized = dict(
            market_data
        )

        normalized[
            "symbol"
        ] = symbol

        normalized[
            "price"
        ] = price

        normalized[
            "timestamp"
        ] = timestamp

        normalized[
            "as_of"
        ] = timestamp

        normalized[
            "provider"
        ] = provider

        normalized[
            "execution_provider"
        ] = provider

        normalized[
            "provider_mode"
        ] = (
            provider_mode
            or "realtime"
        )

        normalized[
            "real_time_stream"
        ] = True

        normalized[
            "simulated"
        ] = False

        normalized[
            "automatic_execution_safe"
        ] = True

        return normalized

    @classmethod
    def _merge_execution_market(
        cls,
        analysis_market: dict[str, Any],
        live_market: dict[str, Any],
        *,
        expected_asset_type: AssetType | None = None,
    ) -> dict[str, Any]:
        """
        Merge DecisionEngine analysis context with the validated live
        execution snapshot.

        Analysis indicators/patterns/regime remain intact. Execution-critical
        quote fields are replaced by the validated live snapshot.
        """
        merged = dict(
            analysis_market
        )

        analysis_source = (
            analysis_market.get(
                "source"
            )
            or analysis_market.get(
                "provider"
            )
        )

        provider = str(
            live_market.get(
                "execution_provider"
            )
            or live_market.get(
                "provider"
            )
            or live_market.get(
                "source"
            )
            or ""
        ).strip()

        if not provider:
            raise RuntimeError(
                "Live execution market does not identify its provider"
            )

        live_price = (
            cls._reference_price(
                live_market
            )
        )

        live_timestamp = (
            cls._market_timestamp(
                live_market
            )
        )

        if live_timestamp is None:
            raise RuntimeError(
                "Live execution market does not contain a timestamp"
            )

        merged[
            "analysis_source"
        ] = analysis_source

        merged[
            "execution_source"
        ] = provider

        merged[
            "execution_provider"
        ] = provider

        merged[
            "execution_feed"
        ] = (
            live_market.get(
                "feed"
            )
        )

        merged[
            "price"
        ] = live_price

        merged[
            "timestamp"
        ] = live_timestamp

        merged[
            "as_of"
        ] = live_timestamp

        merged[
            "source"
        ] = provider

        merged[
            "provider"
        ] = provider

        merged[
            "provider_mode"
        ] = (
            live_market.get(
                "provider_mode"
            )
            or "realtime"
        )

        merged[
            "real_time_stream"
        ] = True

        merged[
            "simulated"
        ] = False

        merged[
            "automatic_execution_safe"
        ] = True

        for key in (
            "bid",
            "bid_price",
            "ask",
            "ask_price",
            "spread",
            "spread_pct",
            "volume",
            "quote_volume",
            "last",
            "last_price",
            "mark",
            "mark_price",
            "open_interest",
            "implied_volatility",
            "delta",
            "gamma",
            "theta",
            "vega",
            "rho",
        ):
            if (
                key in live_market
                and live_market[
                    key
                ] is not None
            ):
                merged[
                    key
                ] = live_market[
                    key
                ]

        candle = (
            live_market.get(
                "candle"
            )
        )

        if isinstance(
            candle,
            dict,
        ):
            merged[
                "live_candle"
            ] = dict(
                candle
            )

        if expected_asset_type is not None:
            merged[
                "asset_type"
            ] = (
                cls._asset_type_value(
                    expected_asset_type
                )
            )

            if not merged.get(
                "asset_class"
            ):
                merged[
                    "asset_class"
                ] = (
                    cls._asset_type_value(
                        expected_asset_type
                    )
                )

        resolved = (
            cls._resolve_asset_type(
                merged
            )
        )

        if (
            expected_asset_type is not None
            and resolved
            != expected_asset_type
        ):
            raise RuntimeError(
                "Live execution market asset type does "
                "not match Decision Engine asset type"
            )

        return merged

    # ======================================================================
    # RESULT
    # ======================================================================

    def _result(
        self,
        *,
        symbol: str,
        status: str,
        decision: dict[str, Any] | None = None,
        market_safety: dict[str, Any] | None = None,
        execution: Any = None,
        reason: str | None = None,
        requested_strategy: str | None = None,
        intent: dict[str, Any] | None = None,
        strategy_config_supplied: bool | None = None,
        market_data_supplied: bool | None = None,
    ) -> dict[str, Any]:
        self.last_symbol = symbol
        self.last_status = status
        self.last_reason = reason

        result: dict[str, Any] = {
            "engine": self.engine_type,
            "symbol": symbol,
            "status": status,
            "decision": decision,
            "market_safety": market_safety,
            "execution": execution,
        }

        if reason is not None:
            result[
                "reason"
            ] = reason

        if requested_strategy is not None:
            result[
                "requested_strategy"
            ] = requested_strategy

        if intent is not None:
            result[
                "intent"
            ] = intent

        if strategy_config_supplied is not None:
            result[
                "strategy_config_supplied"
            ] = (
                strategy_config_supplied
            )

        if market_data_supplied is not None:
            result[
                "market_data_supplied"
            ] = (
                market_data_supplied
            )

        return result

    # ======================================================================
    # FIND STRATEGY
    # ======================================================================

    @staticmethod
    def _find_strategy(
        decision: dict[str, Any],
        strategy_name: str,
    ) -> dict[str, Any] | None:
        wanted = (
            strategy_name
            .strip()
            .lower()
        )

        if not wanted:
            return None

        evaluations = (
            decision.get(
                "evaluations"
            )
            or decision.get(
                "strategy_evaluations"
            )
            or []
        )

        if not isinstance(
            evaluations,
            list,
        ):
            return None

        return next(
            (
                evaluation
                for evaluation
                in evaluations
                if (
                    isinstance(
                        evaluation,
                        dict,
                    )
                    and str(
                        evaluation.get(
                            "strategy",
                            "",
                        )
                    )
                    .strip()
                    .lower()
                    == wanted
                )
            ),
            None,
        )

    # ======================================================================
    # STRATEGY RESOLUTION
    # ======================================================================

    def _resolve_strategy(
        self,
        name: str,
    ) -> str:
        normalized = str(
            name
        ).strip()

        if not normalized:
            raise ValueError(
                "Strategy name is required"
            )

        if self.strategy_picker is None:
            raise RuntimeError(
                "Strategy Picker is not configured"
            )

        resolver = getattr(
            self.strategy_picker,
            "resolve_name",
            None,
        )

        if not callable(
            resolver
        ):
            raise RuntimeError(
                "Strategy Picker resolve_name() is unavailable"
            )

        return resolver(
            normalized
        )

    # ======================================================================
    # NORMALIZATION
    # ======================================================================

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        normalized = str(
            symbol
        ).strip().upper()

        if not normalized:
            raise ValueError(
                "Symbol is required"
            )

        return normalized

    @staticmethod
    def _normalize_quantity(
        quantity: float,
    ) -> float:
        try:
            normalized = float(
                quantity
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Quantity must be a number"
            ) from exc

        if normalized <= 0:
            raise ValueError(
                "Quantity must be greater than zero"
            )

        return normalized

    @staticmethod
    def _normalize_signal(
        value: Any,
    ) -> str:
        if value is None:
            return "HOLD"

        normalized = str(
            value
        ).strip().upper()

        if normalized in {
            "LONG",
        }:
            return "BUY"

        if normalized in {
            "SHORT",
        }:
            return "SELL"

        if not normalized:
            return "HOLD"

        return normalized

    # ======================================================================
    # ASSET TYPE
    # ======================================================================

    @classmethod
    def _resolve_requested_asset_type(
        cls,
        market: dict[str, Any],
        requested_asset_class: str | None,
    ) -> AssetType:
        market_type = (
            cls._resolve_asset_type(
                market
            )
        )

        if not requested_asset_class:
            return market_type

        requested = (
            cls._asset_type_from_value(
                requested_asset_class
            )
        )

        if requested != market_type:
            raise RuntimeError(
                "Requested asset class does not match "
                "Decision Engine market snapshot"
            )

        return market_type

    @classmethod
    def _resolve_asset_type(
        cls,
        market: dict[str, Any],
    ) -> AssetType:
        """
        Resolve PhoenixTrend asset type from the normalized market snapshot.

        Unknown instruments are never silently classified as EQUITY.
        """
        raw = (
            market.get(
                "asset_type"
            )
            or market.get(
                "asset_class"
            )
            or market.get(
                "type"
            )
        )

        if raw is None:
            raise RuntimeError(
                "Decision market snapshot does not contain asset_type"
            )

        return cls._asset_type_from_value(
            raw
        )

    @classmethod
    def _asset_type_from_value(
        cls,
        raw: Any,
    ) -> AssetType:
        if isinstance(
            raw,
            AssetType,
        ):
            return raw

        normalized = str(
            raw
        ).strip().upper()

        asset_type = (
            cls._ASSET_ALIASES.get(
                normalized
            )
        )

        if asset_type is None:
            for candidate in AssetType:
                candidate_value = str(
                    getattr(
                        candidate,
                        "value",
                        candidate,
                    )
                ).strip().upper()

                candidate_name = str(
                    getattr(
                        candidate,
                        "name",
                        "",
                    )
                ).strip().upper()

                if normalized in {
                    candidate_value,
                    candidate_name,
                }:
                    return candidate

            raise RuntimeError(
                "Unsupported or unknown asset type "
                f"from market snapshot: {raw}"
            )

        return asset_type

    @staticmethod
    def _asset_type_value(
        asset_type: AssetType,
    ) -> str:
        value = getattr(
            asset_type,
            "value",
            None,
        )

        if value is not None:
            return str(
                value
            )

        return str(
            asset_type
        )

    # ======================================================================
    # REFERENCE PRICE
    # ======================================================================

    @classmethod
    def _reference_price(
        cls,
        market: dict[str, Any],
    ) -> float:
        price = (
            cls._market_price(
                market
            )
        )

        if (
            price is None
            or price <= 0
        ):
            raise RuntimeError(
                "Decision market snapshot "
                "does not contain a valid price"
            )

        return price

    @classmethod
    def _market_price(
        cls,
        market: Mapping[str, Any],
    ) -> float | None:
        for key in cls._PRICE_KEYS:
            value = (
                cls._optional_number(
                    market.get(
                        key
                    )
                )
            )

            if (
                value is not None
                and value > 0
            ):
                return value

        bid = None
        ask = None

        for key in cls._BID_KEYS:
            bid = (
                cls._optional_number(
                    market.get(
                        key
                    )
                )
            )

            if (
                bid is not None
                and bid > 0
            ):
                break

        for key in cls._ASK_KEYS:
            ask = (
                cls._optional_number(
                    market.get(
                        key
                    )
                )
            )

            if (
                ask is not None
                and ask > 0
            ):
                break

        if (
            bid is not None
            and ask is not None
            and bid > 0
            and ask > 0
            and ask >= bid
        ):
            return (
                bid + ask
            ) / 2.0

        candle = (
            market.get(
                "candle"
            )
        )

        if isinstance(
            candle,
            Mapping,
        ):
            close = (
                cls._optional_number(
                    candle.get(
                        "close"
                    )
                )
            )

            if (
                close is not None
                and close > 0
            ):
                return close

        return None

    # ======================================================================
    # TIMESTAMP
    # ======================================================================

    @classmethod
    def _market_timestamp(
        cls,
        market: Mapping[str, Any],
    ) -> Any:
        for key in cls._TIMESTAMP_KEYS:
            value = (
                market.get(
                    key
                )
            )

            if value is not None:
                return value

        candle = (
            market.get(
                "candle"
            )
        )

        if isinstance(
            candle,
            Mapping,
        ):
            for key in (
                "timestamp",
                "time",
                "as_of",
            ):
                value = (
                    candle.get(
                        key
                    )
                )

                if value is not None:
                    return value

        return None

    # ======================================================================
    # GENERIC HELPERS
    # ======================================================================

    @staticmethod
    def _optional_number(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        try:
            return float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _optional_bool(
        value: Any,
    ) -> bool | None:
        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            (int, float),
        ):
            return bool(
                value
            )

        normalized = str(
            value
        ).strip().lower()

        if normalized in {
            "true",
            "1",
            "yes",
            "y",
            "on",
            "enabled",
            "live",
        }:
            return True

        if normalized in {
            "false",
            "0",
            "no",
            "n",
            "off",
            "disabled",
            "simulated",
        }:
            return False

        return None

    @classmethod
    def _first_bool(
        cls,
        payload: Mapping[str, Any],
        keys: tuple[str, ...],
    ) -> bool | None:
        for key in keys:
            if key not in payload:
                continue

            value = (
                cls._optional_bool(
                    payload.get(
                        key
                    )
                )
            )

            if value is not None:
                return value

        return None

    @staticmethod
    def _first_text(
        payload: Mapping[str, Any],
        keys: tuple[str, ...],
    ) -> str | None:
        for key in keys:
            value = (
                payload.get(
                    key
                )
            )

            if value is None:
                continue

            normalized = str(
                value
            ).strip()

            if normalized:
                return normalized

        return None

    @staticmethod
    def _extract_reason(
        payload: Any,
    ) -> str | None:
        if not isinstance(
            payload,
            Mapping,
        ):
            return None

        for key in (
            "reason",
            "message",
            "detail",
            "error",
        ):
            value = (
                payload.get(
                    key
                )
            )

            if value is not None:
                text = str(
                    value
                ).strip()

                if text:
                    return text

        reasons = (
            payload.get(
                "reasons"
            )
        )

        if isinstance(
            reasons,
            list,
        ):
            normalized = [
                str(
                    item
                ).strip()
                for item in reasons
                if str(
                    item
                ).strip()
            ]

            if normalized:
                return "; ".join(
                    normalized
                )

        return None

    @staticmethod
    def _intent_dump(
        intent: TradeIntent,
    ) -> dict[str, Any]:
        if hasattr(
            intent,
            "model_dump",
        ):
            try:
                return intent.model_dump(
                    mode="json"
                )
            except TypeError:
                return intent.model_dump()

        if hasattr(
            intent,
            "dict",
        ):
            return intent.dict()

        if hasattr(
            intent,
            "__dict__",
        ):
            return {
                key: value
                for key, value
                in vars(
                    intent
                ).items()
                if not key.startswith(
                    "_"
                )
            }

        raise RuntimeError(
            "TradeIntent cannot be serialized"
        )

    @staticmethod
    def _utc_now(
    ) -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    # ======================================================================
    # READY
    # ======================================================================

    def _ready(
        self,
    ) -> None:
        if self.emergency_stop:
            raise RuntimeError(
                "Emergency Stop is active"
            )

        if not self.enabled:
            raise RuntimeError(
                "Automatic Engine is disabled"
            )

        if self.new_entries_paused:
            raise RuntimeError(
                "New automatic entries are paused"
            )

    # ======================================================================
    # STATUS
    # ======================================================================

    def status(
        self,
    ) -> dict[str, Any]:
        if self.emergency_stop:
            state = "EMERGENCY_STOP"

        elif not self.enabled:
            state = "STOPPED"

        elif self.new_entries_paused:
            state = "PAUSED"

        else:
            state = "RUNNING"

        return {
            "engine": self.engine_type,
            "state": state,
            "enabled": self.enabled,
            "emergency_stop": (
                self.emergency_stop
            ),
            "new_entries_paused": (
                self.new_entries_paused
            ),
            "selected_strategy": (
                self.selected_strategy
            ),
            "auto_select_strategy": (
                self.auto_select_strategy
            ),
            "automatic_execution": True,
            "market_safety_required": True,
            "decision_engine_required": True,
            "execution_service_required": True,
            "live_market_required": True,
            "provider_agnostic_live_validation": True,
            "processed_opportunities": (
                self.processed_opportunities
            ),
            "trade_intents_created": (
                self.trade_intents_created
            ),
            "executions_requested": (
                self.executions_requested
            ),
            "blocked_live_market": (
                self.blocked_live_market
            ),
            "blocked_market_safety": (
                self.blocked_market_safety
            ),
            "blocked_engine_state": (
                self.blocked_engine_state
            ),
            "no_trade_decisions": (
                self.no_trade_decisions
            ),
            "execution_errors": (
                self.execution_errors
            ),
            "last_symbol": (
                self.last_symbol
            ),
            "last_status": (
                self.last_status
            ),
            "last_strategy": (
                self.last_strategy
            ),
            "last_action": (
                self.last_action
            ),
            "last_execution_state": (
                self.last_execution_state
            ),
            "last_reason": (
                self.last_reason
            ),
            "last_processed_at": (
                self.last_processed_at
            ),
            "last_execution_provider": (
                self.last_execution_provider
            ),
            "last_asset_type": (
                self.last_asset_type
            ),
        }


automatic_engine = AutomaticEngine()