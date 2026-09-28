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
from .strategy_picker import StrategyPicker


class ManualEngine:
    """
    PhoenixTrend Manual Trading Engine.

    Manual trading uses the same shared intelligence and controlled execution
    path as automation, but the user remains the execution authority.

    Analysis flow
    -------------
        User selects symbol
            ↓
        DecisionEngine
            ↓
        Patterns / indicators / regime / all registered strategies
            ↓
        Strategy selection
            ↓
        BUY / SELL / HOLD analysis
            ↓
        Manual candidate
            ↓
        User explicitly decides whether to trade

    Execution flow
    --------------
        Manual candidate
            ↓
        Explicit user confirmation
            ↓
        Fresh real market snapshot
            ↓
        Market Safety
            ↓
        TradeIntent(MANUAL)
            ↓
        ExecutionService
            ↓
        Safety / Risk / Broker capability
            ↓
        Broker

    This engine never auto-submits an order.
    """

    engine_type = "manual"

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
        "OPTION": AssetType.OPTION,
        "OPTIONS": AssetType.OPTION,
        "CRYPTO": AssetType.CRYPTO,
        "CRYPTOCURRENCY": AssetType.CRYPTO,
        "CRYPTOCURRENCIES": AssetType.CRYPTO,
        "FOREX": AssetType.FOREX,
        "FX": AssetType.FOREX,
        "COMMODITY": AssetType.COMMODITY,
        "COMMODITIES": AssetType.COMMODITY,
    }

    _PRICE_KEYS = (
        "price",
        "last",
        "last_price",
        "current_price",
        "market_price",
        "mark",
        "mark_price",
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

    _SOURCE_KEYS = (
        "source",
        "provider",
        "data_provider",
        "feed",
    )

    _CANDIDATE_ID_KEYS = (
        "candidate_id",
        "id",
    )

    def __init__(
        self,
        strategy_picker: StrategyPicker | None = None,
        decision_service: Any | None = None,
        execution_engine: Any | None = None,
        market_safety: Any | None = None,
    ) -> None:
        self.strategy_picker = (
            strategy_picker
            or StrategyPicker()
        )

        self.decision_service = (
            decision_service
            or decision_engine
        )

        self.execution_engine = (
            execution_engine
            or execution_service
        )

        self.market_safety = (
            market_safety
            or market_safety_service
        )

        self.analysis_count = 0
        self.candidates_created = 0
        self.orders_prepared = 0
        self.executions_requested = 0

        self.no_trade_count = 0
        self.confirmation_blocks = 0
        self.market_safety_blocks = 0
        self.execution_errors = 0

        self.last_symbol: str | None = None
        self.last_strategy: str | None = None
        self.last_signal: str | None = None
        self.last_status: str | None = None
        self.last_reason: str | None = None
        self.last_candidate_id: str | None = None
        self.last_execution_state: str | None = None
        self.last_processed_at: str | None = None

    # =========================================================================
    # ANALYSIS
    # =========================================================================

    async def analyze(
        self,
        *,
        symbol: str,
        strategy_name: str | None = None,
        market_data: dict[str, Any] | None = None,
        strategy_config: dict[str, Any] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Analyze a symbol without submitting an order.

        DecisionEngine is the intelligence authority. ManualEngine does not
        rebuild a separate indicator/pattern/strategy pipeline.

        A manually selected strategy may be used to choose one of the
        DecisionEngine evaluations, but ManualEngine does not fabricate a
        signal when that strategy returned HOLD.
        """
        normalized_symbol = self._normalize_symbol(
            symbol
        )

        self.analysis_count += 1
        self.last_symbol = normalized_symbol
        self.last_processed_at = self._utc_now()
        self.last_reason = None
        self.last_execution_state = None

        decision = await self._call_decision_analyze(
            normalized_symbol,
            force=force,
        )

        if not isinstance(
            decision,
            dict,
        ):
            raise RuntimeError(
                "Decision Engine returned an invalid response"
            )

        decision_market = self._mapping(
            decision.get(
                "market"
            )
        )

        supplied_market = self._mapping(
            market_data
        )

        analysis_market = self._merge_analysis_market(
            decision_market,
            supplied_market,
        )

        asset_type = self._resolve_asset_type(
            analysis_market,
            decision,
        )

        selected: dict[str, Any] | None = None
        requested_strategy: str | None = None

        if strategy_name:
            requested_strategy = self._resolve_strategy(
                strategy_name
            )

            selected = self._find_strategy(
                decision,
                requested_strategy,
            )

            if selected is None:
                self.no_trade_count += 1

                candidate = self._build_candidate(
                    symbol=normalized_symbol,
                    asset_type=asset_type,
                    signal="HOLD",
                    confidence=0.0,
                    strategy=requested_strategy,
                    stop=None,
                    target=None,
                    rationale=[
                        (
                            "Requested strategy was not returned "
                            "by Decision Engine"
                        )
                    ],
                    decision=decision,
                    selected=None,
                    market=analysis_market,
                    strategy_config=strategy_config,
                    executable=False,
                    status="NO_TRADE",
                )

                self._remember_candidate(
                    candidate
                )

                return candidate

        else:
            raw_selected = decision.get(
                "selected"
            )

            if isinstance(
                raw_selected,
                Mapping,
            ):
                selected = dict(
                    raw_selected
                )

        decision_action = self._normalize_signal(
            decision.get(
                "action"
            )
        )

        if selected is not None:
            selected_signal = self._normalize_signal(
                selected.get(
                    "signal"
                )
            )

            strategy = str(
                selected.get(
                    "strategy"
                )
                or requested_strategy
                or decision.get(
                    "strategy"
                )
                or "Unknown"
            ).strip()

            confidence = self._optional_float(
                selected.get(
                    "confidence"
                )
            )

            if confidence is None:
                confidence = self._optional_float(
                    selected.get(
                        "score"
                    )
                )

            if confidence is None:
                confidence = self._optional_float(
                    decision.get(
                        "confidence"
                    )
                )

            if confidence is None:
                confidence = 0.0

            stop = self._optional_float(
                selected.get(
                    "stop"
                )
            )

            target = self._optional_float(
                selected.get(
                    "target"
                )
            )

            rationale = self._normalize_rationale(
                selected.get(
                    "rationale"
                )
                or selected.get(
                    "reasons"
                )
                or decision.get(
                    "rationale"
                )
                or decision.get(
                    "reasons"
                )
            )

        else:
            selected_signal = decision_action

            strategy = str(
                requested_strategy
                or decision.get(
                    "strategy"
                )
                or "Decision Engine"
            ).strip()

            confidence = self._optional_float(
                decision.get(
                    "confidence"
                )
            )

            if confidence is None:
                confidence = 0.0

            stop = self._optional_float(
                decision.get(
                    "stop"
                )
            )

            target = self._optional_float(
                decision.get(
                    "target"
                )
            )

            rationale = self._normalize_rationale(
                decision.get(
                    "rationale"
                )
                or decision.get(
                    "reasons"
                )
            )

        if (
            requested_strategy is None
            and decision_action in self._ACTIONABLE_SIGNALS
            and selected is not None
            and selected_signal != decision_action
        ):
            selected_signal = "HOLD"

            rationale.append(
                (
                    "Selected strategy signal does not match "
                    "the Decision Engine final action"
                )
            )

        executable = (
            selected_signal
            in self._ACTIONABLE_SIGNALS
        )

        if not executable:
            self.no_trade_count += 1

        status = (
            "AWAITING_USER_DECISION"
            if executable
            else "NO_TRADE"
        )

        candidate = self._build_candidate(
            symbol=normalized_symbol,
            asset_type=asset_type,
            signal=selected_signal,
            confidence=confidence,
            strategy=strategy,
            stop=stop,
            target=target,
            rationale=rationale,
            decision=decision,
            selected=selected,
            market=analysis_market,
            strategy_config=strategy_config,
            executable=executable,
            status=status,
        )

        self._remember_candidate(
            candidate
        )

        return candidate

    # =========================================================================
    # PREPARE ORDER
    # =========================================================================

    def prepare_order(
        self,
        candidate: dict[str, Any],
        quantity: float,
        *,
        reference_market: dict[str, Any] | None = None,
    ) -> TradeIntent:
        """
        Convert a previously analyzed candidate into a MANUAL TradeIntent.

        This method does not submit anything.

        Explicit user approval is still required by execute().
        """
        if not isinstance(
            candidate,
            dict,
        ):
            raise ValueError(
                "Candidate is required"
            )

        if not candidate.get(
            "executable",
            False,
        ):
            raise ValueError(
                "Candidate is not executable"
            )

        if candidate.get(
            "auto_execute"
        ):
            raise ValueError(
                "Manual candidates cannot enable auto execution"
            )

        if not candidate.get(
            "requires_user_confirmation",
            True,
        ):
            raise ValueError(
                "Manual candidate must require user confirmation"
            )

        signal = self._normalize_signal(
            candidate.get(
                "signal"
            )
        )

        if signal not in self._ACTIONABLE_SIGNALS:
            raise ValueError(
                (
                    "Candidate does not contain an "
                    "actionable BUY/SELL signal"
                )
            )

        symbol = self._normalize_symbol(
            candidate.get(
                "symbol"
            )
        )

        quantity_value = self._normalize_quantity(
            quantity
        )

        candidate_asset_type = self._asset_type_from_value(
            candidate.get(
                "asset_type"
            )
        )

        candidate_price = self._optional_float(
            candidate.get(
                "reference_price"
            )
        )

        if reference_market:
            market = self._mapping(
                reference_market
            )

            market_symbol = str(
                market.get(
                    "symbol"
                )
                or symbol
            ).strip().upper()

            if market_symbol != symbol:
                raise ValueError(
                    (
                        "Reference market symbol does not "
                        "match candidate symbol"
                    )
                )

            raw_market_asset = (
                market.get(
                    "asset_type"
                )
                or market.get(
                    "asset_class"
                )
            )

            if raw_market_asset is not None:
                market_asset_type = self._asset_type_from_value(
                    raw_market_asset
                )

                if market_asset_type != candidate_asset_type:
                    raise ValueError(
                        (
                            "Reference market asset type does not "
                            "match candidate asset type"
                        )
                    )

            live_price = self._market_price(
                market
            )

            if (
                live_price is not None
                and live_price > 0
            ):
                candidate_price = live_price

        if (
            candidate_price is None
            or candidate_price <= 0
        ):
            raise ValueError(
                "Candidate has an invalid reference price"
            )

        strategy = str(
            candidate.get(
                "strategy"
            )
            or ""
        ).strip()

        if not strategy:
            raise ValueError(
                "Candidate strategy is missing"
            )

        intent = TradeIntent(
            intent_id=(
                "ti_"
                + uuid4().hex[:12]
            ),
            symbol=symbol,
            asset_type=candidate_asset_type,
            side=Side(
                signal
            ),
            qty=quantity_value,
            reference_price=candidate_price,
            strategy=strategy,
            execution_mode=ExecutionMode.MANUAL,
            stop=self._optional_float(
                candidate.get(
                    "stop"
                )
            ),
            target=self._optional_float(
                candidate.get(
                    "target"
                )
            ),
        )

        self.orders_prepared += 1

        return intent

    # =========================================================================
    # EXECUTE
    # =========================================================================

    async def execute(
        self,
        *,
        candidate: dict[str, Any],
        quantity: float,
        account: AccountState,
        user_approved: bool,
        market_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a manual candidate only after explicit user confirmation.

        The backend enforces user_approved=True. UI confirmation alone is not
        sufficient.

        The resulting TradeIntent is always MANUAL and is routed through the
        shared ExecutionService.
        """
        if not user_approved:
            self.confirmation_blocks += 1
            self.last_status = "AWAITING_USER_CONFIRMATION"
            self.last_reason = (
                "Explicit user confirmation is required"
            )

            return {
                "engine": self.engine_type,
                "status": "AWAITING_USER_CONFIRMATION",
                "executed": False,
                "reason": (
                    "Explicit user confirmation is required"
                ),
                "candidate_id": candidate.get(
                    "candidate_id"
                )
                if isinstance(
                    candidate,
                    dict,
                )
                else None,
            }

        if account is None:
            raise ValueError(
                "Account state is required"
            )

        if not isinstance(
            candidate,
            dict,
        ):
            raise ValueError(
                "Candidate is required"
            )

        if not candidate.get(
            "executable",
            False,
        ):
            raise ValueError(
                "Candidate is not executable"
            )

        signal = self._normalize_signal(
            candidate.get(
                "signal"
            )
        )

        if signal not in self._ACTIONABLE_SIGNALS:
            raise ValueError(
                "Candidate is not BUY or SELL"
            )

        symbol = self._normalize_symbol(
            candidate.get(
                "symbol"
            )
        )

        candidate_asset_type = self._asset_type_from_value(
            candidate.get(
                "asset_type"
            )
        )

        execution_market = self._validate_execution_market(
            symbol=symbol,
            expected_asset_type=candidate_asset_type,
            market_data=market_data,
            candidate=candidate,
        )

        if execution_market is None:
            self.last_status = "BLOCKED_MARKET_DATA"
            self.last_reason = (
                "A valid current market snapshot is required "
                "before manual execution"
            )

            return {
                "engine": self.engine_type,
                "symbol": symbol,
                "status": "BLOCKED_MARKET_DATA",
                "executed": False,
                "reason": self.last_reason,
                "candidate_id": candidate.get(
                    "candidate_id"
                ),
            }

        safety = await self._call_market_safety(
            execution_market
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
            self.market_safety_blocks += 1

            reason = (
                self._extract_reason(
                    safety
                )
                or (
                    "Market Safety rejected the "
                    "manual execution snapshot"
                )
            )

            self.last_status = "BLOCKED_MARKET_SAFETY"
            self.last_reason = reason

            return {
                "engine": self.engine_type,
                "symbol": symbol,
                "status": "BLOCKED_MARKET_SAFETY",
                "executed": False,
                "reason": reason,
                "candidate_id": candidate.get(
                    "candidate_id"
                ),
                "market_safety": safety,
            }

        intent = self.prepare_order(
            candidate,
            quantity,
            reference_market=execution_market,
        )

        if intent.execution_mode != ExecutionMode.MANUAL:
            raise RuntimeError(
                "ManualEngine produced a non-manual TradeIntent"
            )

        self.executions_requested += 1

        try:
            result = await self._call_execution_process(
                intent=intent,
                account=account,
                user_approved=True,
                market_data=execution_market,
            )

        except Exception as exc:
            self.execution_errors += 1
            self.last_status = "EXECUTION_ERROR"
            self.last_execution_state = "EXECUTION_ERROR"
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
                "state"
            )
            or result.get(
                "status"
            )
            or "UNKNOWN"
        ).strip().upper()

        if not execution_state:
            execution_state = "UNKNOWN"

        self.last_status = execution_state
        self.last_execution_state = execution_state
        self.last_reason = self._extract_reason(
            result
        )
        self.last_processed_at = self._utc_now()

        return {
            "engine": self.engine_type,
            "symbol": symbol,
            "status": execution_state,
            "executed": True,
            "candidate_id": candidate.get(
                "candidate_id"
            ),
            "intent": self._intent_dump(
                intent
            ),
            "market_safety": safety,
            "execution": result,
        }

    # =========================================================================
    # ANALYZE + EXECUTE
    # =========================================================================

    async def process(
        self,
        *,
        symbol: str,
        quantity: float,
        account: AccountState,
        user_approved: bool,
        strategy_name: str | None = None,
        market_data: dict[str, Any] | None = None,
        strategy_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Convenience path for a manual trade request.

        Analysis occurs first. Even when DecisionEngine returns BUY/SELL,
        execution is impossible unless user_approved=True.
        """
        candidate = await self.analyze(
            symbol=symbol,
            strategy_name=strategy_name,
            market_data=market_data,
            strategy_config=strategy_config,
            force=True,
        )

        if not candidate.get(
            "executable",
            False,
        ):
            return {
                "engine": self.engine_type,
                "symbol": candidate.get(
                    "symbol"
                ),
                "status": "NO_TRADE",
                "executed": False,
                "candidate": candidate,
            }

        if not user_approved:
            self.confirmation_blocks += 1
            self.last_status = "AWAITING_USER_CONFIRMATION"
            self.last_reason = (
                "Explicit user confirmation is required"
            )

            return {
                "engine": self.engine_type,
                "symbol": candidate.get(
                    "symbol"
                ),
                "status": "AWAITING_USER_CONFIRMATION",
                "executed": False,
                "candidate": candidate,
            }

        result = await self.execute(
            candidate=candidate,
            quantity=quantity,
            account=account,
            user_approved=True,
            market_data=market_data,
        )

        result[
            "candidate"
        ] = candidate

        return result

    # =========================================================================
    # DECISION ENGINE
    # =========================================================================

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

    # =========================================================================
    # MARKET SAFETY
    # =========================================================================

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
                require_provider_approval=False,
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

    # =========================================================================
    # EXECUTION SERVICE
    # =========================================================================

    async def _call_execution_process(
        self,
        *,
        intent: TradeIntent,
        account: AccountState,
        user_approved: bool,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:
        if not user_approved:
            raise RuntimeError(
                "Manual execution requires explicit user approval"
            )

        if intent.execution_mode != ExecutionMode.MANUAL:
            raise RuntimeError(
                "ManualEngine may submit only MANUAL TradeIntent objects"
            )

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
            automation_enabled=False,
            user_approved=True,
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

    # =========================================================================
    # EXECUTION MARKET VALIDATION
    # =========================================================================

    def _validate_execution_market(
        self,
        *,
        symbol: str,
        expected_asset_type: AssetType,
        market_data: dict[str, Any] | None,
        candidate: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Manual trading does not require unattended-execution eligibility, but
        it still requires a current, non-simulated market snapshot before an
        order is sent to ExecutionService.

        Simulated analysis may be displayed in Manual Trade, but it cannot be
        silently converted into a live broker order.
        """
        market = self._mapping(
            market_data
        )

        if not market:
            candidate_market = self._mapping(
                candidate.get(
                    "market"
                )
            )

            market = candidate_market

        if not market:
            return None

        market_symbol = str(
            market.get(
                "symbol"
            )
            or symbol
        ).strip().upper()

        if market_symbol != symbol:
            return None

        raw_asset_type = (
            market.get(
                "asset_type"
            )
            or market.get(
                "asset_class"
            )
        )

        if raw_asset_type is not None:
            try:
                market_asset_type = self._asset_type_from_value(
                    raw_asset_type
                )
            except RuntimeError:
                return None

            if market_asset_type != expected_asset_type:
                return None

        simulated = self._optional_bool(
            market.get(
                "simulated"
            )
        )

        if simulated is True:
            return None

        price = self._market_price(
            market
        )

        if (
            price is None
            or price <= 0
        ):
            return None

        timestamp = self._market_timestamp(
            market
        )

        if timestamp is None:
            return None

        source = self._first_text(
            market,
            self._SOURCE_KEYS,
        )

        if not source:
            return None

        normalized = dict(
            market
        )

        normalized[
            "symbol"
        ] = symbol

        normalized[
            "asset_type"
        ] = self._asset_type_value(
            expected_asset_type
        )

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
            "source"
        ] = source

        normalized[
            "simulated"
        ] = False

        normalized[
            "manual_execution"
        ] = True

        normalized[
            "user_confirmation_required"
        ] = True

        normalized[
            "user_approved"
        ] = True

        return normalized

    # =========================================================================
    # CANDIDATE
    # =========================================================================

    def _build_candidate(
        self,
        *,
        symbol: str,
        asset_type: AssetType,
        signal: str,
        confidence: float,
        strategy: str,
        stop: float | None,
        target: float | None,
        rationale: list[str],
        decision: dict[str, Any],
        selected: dict[str, Any] | None,
        market: dict[str, Any],
        strategy_config: dict[str, Any] | None,
        executable: bool,
        status: str,
    ) -> dict[str, Any]:
        reference_price = self._market_price(
            market
        )

        if reference_price is None:
            reference_price = self._optional_float(
                decision.get(
                    "reference_price"
                )
            )

        patterns = (
            decision.get(
                "patterns"
            )
            or decision.get(
                "chart_patterns"
            )
            or market.get(
                "patterns"
            )
            or []
        )

        support = (
            decision.get(
                "support"
            )
            or market.get(
                "support"
            )
        )

        resistance = (
            decision.get(
                "resistance"
            )
            or market.get(
                "resistance"
            )
        )

        regime = (
            decision.get(
                "regime"
            )
            or market.get(
                "market_regime"
            )
            or market.get(
                "regime"
            )
        )

        candidate_id = (
            "mc_"
            + uuid4().hex[:12]
        )

        self.candidates_created += 1

        return {
            "candidate_id": candidate_id,
            "engine": self.engine_type,
            "symbol": symbol,
            "asset_type": self._asset_type_value(
                asset_type
            ),
            "strategy": strategy,
            "signal": signal,
            "action": signal,
            "confidence": float(
                confidence
            ),
            "reference_price": reference_price,
            "stop": stop,
            "target": target,
            "rationale": rationale,
            "patterns": patterns,
            "support": support,
            "resistance": resistance,
            "regime": regime,
            "selected": selected,
            "decision": decision,
            "market": market,
            "strategy_config": (
                dict(
                    strategy_config
                )
                if isinstance(
                    strategy_config,
                    dict,
                )
                else None
            ),
            "executable": bool(
                executable
            ),
            "requires_user_confirmation": True,
            "user_approved": False,
            "auto_execute": False,
            "execution_mode": self._execution_mode_value(
                ExecutionMode.MANUAL
            ),
            "status": status,
            "created_at": self._utc_now(),
        }

    def _remember_candidate(
        self,
        candidate: dict[str, Any],
    ) -> None:
        self.last_candidate_id = str(
            candidate.get(
                "candidate_id"
            )
            or ""
        ) or None

        self.last_symbol = str(
            candidate.get(
                "symbol"
            )
            or ""
        ) or None

        self.last_strategy = str(
            candidate.get(
                "strategy"
            )
            or ""
        ) or None

        self.last_signal = self._normalize_signal(
            candidate.get(
                "signal"
            )
        )

        self.last_status = str(
            candidate.get(
                "status"
            )
            or ""
        ) or None

        self.last_reason = None

    # =========================================================================
    # MARKET MERGE
    # =========================================================================

    def _merge_analysis_market(
        self,
        decision_market: dict[str, Any],
        supplied_market: dict[str, Any],
    ) -> dict[str, Any]:
        """
        DecisionEngine market context remains authoritative for analysis.

        User/API supplied market data may enrich the response but cannot erase
        DecisionEngine fields with None.
        """
        merged = dict(
            decision_market
        )

        for key, value in supplied_market.items():
            if value is not None:
                merged[
                    key
                ] = value

        return merged

    # =========================================================================
    # STRATEGY
    # =========================================================================

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

        resolver = getattr(
            self.strategy_picker,
            "resolve_name",
            None,
        )

        if callable(
            resolver
        ):
            return str(
                resolver(
                    normalized
                )
            )

        picker = getattr(
            self.strategy_picker,
            "pick",
            None,
        )

        if callable(
            picker
        ):
            try:
                strategy = picker(
                    normalized,
                    None,
                )
            except TypeError:
                strategy = picker(
                    normalized
                )

            strategy_name = getattr(
                strategy,
                "name",
                None,
            )

            if strategy_name:
                return str(
                    strategy_name
                )

        raise RuntimeError(
            "Strategy Picker cannot resolve strategy names"
        )

    @staticmethod
    def _find_strategy(
        decision: dict[str, Any],
        strategy_name: str,
    ) -> dict[str, Any] | None:
        wanted = str(
            strategy_name
        ).strip().lower()

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

        for evaluation in evaluations:
            if not isinstance(
                evaluation,
                Mapping,
            ):
                continue

            name = str(
                evaluation.get(
                    "strategy"
                )
                or evaluation.get(
                    "name"
                )
                or ""
            ).strip().lower()

            if name == wanted:
                return dict(
                    evaluation
                )

        return None

    # =========================================================================
    # ASSET TYPE
    # =========================================================================

    @classmethod
    def _resolve_asset_type(
        cls,
        market: dict[str, Any],
        decision: dict[str, Any],
    ) -> AssetType:
        raw = (
            market.get(
                "asset_type"
            )
            or market.get(
                "asset_class"
            )
            or decision.get(
                "asset_type"
            )
            or decision.get(
                "asset_class"
            )
        )

        if raw is None:
            raise RuntimeError(
                (
                    "Decision Engine did not identify "
                    "the instrument asset type"
                )
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

        if raw is None:
            raise RuntimeError(
                "Asset type is required"
            )

        normalized = str(
            raw
        ).strip().upper()

        if not normalized:
            raise RuntimeError(
                "Asset type is required"
            )

        alias = cls._ASSET_ALIASES.get(
            normalized
        )

        if alias is not None:
            return alias

        for item in AssetType:
            value = str(
                getattr(
                    item,
                    "value",
                    item,
                )
            ).strip().upper()

            name = str(
                getattr(
                    item,
                    "name",
                    "",
                )
            ).strip().upper()

            if normalized in {
                value,
                name,
            }:
                return item

        raise RuntimeError(
            (
                "Unsupported or unknown asset type: "
                f"{raw}"
            )
        )

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

    # =========================================================================
    # MARKET PRICE
    # =========================================================================

    @classmethod
    def _market_price(
        cls,
        market: Mapping[str, Any],
    ) -> float | None:
        for key in cls._PRICE_KEYS:
            value = cls._optional_float(
                market.get(
                    key
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
            value = cls._optional_float(
                market.get(
                    key
                )
            )

            if (
                value is not None
                and value > 0
            ):
                bid = value
                break

        for key in cls._ASK_KEYS:
            value = cls._optional_float(
                market.get(
                    key
                )
            )

            if (
                value is not None
                and value > 0
            ):
                ask = value
                break

        if (
            bid is not None
            and ask is not None
            and ask >= bid
        ):
            return (
                bid + ask
            ) / 2.0

        candle = market.get(
            "candle"
        )

        if isinstance(
            candle,
            Mapping,
        ):
            close = cls._optional_float(
                candle.get(
                    "close"
                )
            )

            if (
                close is not None
                and close > 0
            ):
                return close

        return None

    @classmethod
    def _market_timestamp(
        cls,
        market: Mapping[str, Any],
    ) -> Any:
        for key in cls._TIMESTAMP_KEYS:
            value = market.get(
                key
            )

            if value is not None:
                return value

        candle = market.get(
            "candle"
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
                value = candle.get(
                    key
                )

                if value is not None:
                    return value

        return None

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> str:
        normalized = str(
            symbol
            or ""
        ).strip().upper()

        if not normalized:
            raise ValueError(
                "Symbol is required"
            )

        return normalized

    @staticmethod
    def _normalize_quantity(
        quantity: Any,
    ) -> float:
        try:
            value = float(
                quantity
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Quantity must be a number"
            ) from exc

        if value <= 0:
            raise ValueError(
                "Quantity must be greater than zero"
            )

        return value

    @staticmethod
    def _normalize_signal(
        value: Any,
    ) -> str:
        normalized = str(
            value
            or ""
        ).strip().upper()

        if normalized == "LONG":
            return "BUY"

        if normalized == "SHORT":
            return "SELL"

        if normalized in ManualEngine._HOLD_SIGNALS:
            return "HOLD"

        return normalized

    @staticmethod
    def _normalize_rationale(
        value: Any,
    ) -> list[str]:
        if value is None:
            return []

        if isinstance(
            value,
            str,
        ):
            text = value.strip()

            return (
                [text]
                if text
                else []
            )

        if isinstance(
            value,
            (list, tuple, set),
        ):
            result: list[str] = []

            for item in value:
                text = str(
                    item
                ).strip()

                if text:
                    result.append(
                        text
                    )

            return result

        if isinstance(
            value,
            Mapping,
        ):
            return [
                str(
                    dict(
                        value
                    )
                )
            ]

        text = str(
            value
        ).strip()

        return (
            [text]
            if text
            else []
        )

    @staticmethod
    def _mapping(
        value: Any,
    ) -> dict[str, Any]:
        if value is None:
            return {}

        if isinstance(
            value,
            dict,
        ):
            return dict(
                value
            )

        if isinstance(
            value,
            Mapping,
        ):
            return dict(
                value.items()
            )

        if hasattr(
            value,
            "model_dump",
        ):
            try:
                result = value.model_dump()

                if isinstance(
                    result,
                    Mapping,
                ):
                    return dict(
                        result
                    )

            except Exception:
                pass

        if hasattr(
            value,
            "dict",
        ):
            try:
                result = value.dict()

                if isinstance(
                    result,
                    Mapping,
                ):
                    return dict(
                        result
                    )

            except Exception:
                pass

        return {}

    @staticmethod
    def _optional_float(
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

    @staticmethod
    def _first_text(
        payload: Mapping[str, Any],
        keys: tuple[str, ...],
    ) -> str | None:
        for key in keys:
            value = payload.get(
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
            value = payload.get(
                key
            )

            if value is None:
                continue

            text = str(
                value
            ).strip()

            if text:
                return text

        reasons = payload.get(
            "reasons"
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
    def _execution_mode_value(
        execution_mode: ExecutionMode,
    ) -> str:
        value = getattr(
            execution_mode,
            "value",
            None,
        )

        if value is not None:
            return str(
                value
            )

        return str(
            execution_mode
        )

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
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    # =========================================================================
    # STATUS
    # =========================================================================

    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "engine": self.engine_type,
            "automatic_execution": False,
            "manual_execution": True,
            "user_confirmation_required": True,
            "backend_confirmation_enforced": True,
            "decision_engine_required": True,
            "market_safety_required": True,
            "execution_service_required": True,
            "risk_pipeline_required": True,
            "analysis_count": self.analysis_count,
            "candidates_created": self.candidates_created,
            "orders_prepared": self.orders_prepared,
            "executions_requested": self.executions_requested,
            "no_trade_count": self.no_trade_count,
            "confirmation_blocks": self.confirmation_blocks,
            "market_safety_blocks": self.market_safety_blocks,
            "execution_errors": self.execution_errors,
            "last_symbol": self.last_symbol,
            "last_strategy": self.last_strategy,
            "last_signal": self.last_signal,
            "last_status": self.last_status,
            "last_reason": self.last_reason,
            "last_candidate_id": self.last_candidate_id,
            "last_execution_state": self.last_execution_state,
            "last_processed_at": self.last_processed_at,
        }


manual_engine = ManualEngine()