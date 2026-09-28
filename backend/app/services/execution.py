from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any

from sqlalchemy import select

from ..db import SessionLocal, TradeRecord
from ..domain import (
    AccountState,
    ExecutionMode,
    RiskStatus,
    TradeIntent,
)
from .audit import audit
from .market_safety import market_safety_service
from .risk import risk_engine


class ExecutionService:
    """
    PhoenixTrend final execution gateway.

    Flow:

        TradeIntent
            ↓
        Duplicate protection
            ↓
        Market Safety [required for AUTOMATIC]
            ↓
        Risk Engine
            ↓
        User approval [required for MANUAL / CONTROLLED]
            ↓
        Broker capability
            ↓
        Broker submission
            ↓
        Broker order
            ↓
        Persistence
            ↓
        Audit

    This service does NOT:
        - create strategies
        - generate market signals
        - select trades
        - fabricate broker orders
        - fabricate fill prices
        - fabricate realized P&L
        - silently fall back to simulated execution

    All real order submission must pass through this gateway.
    """

    def __init__(
        self,
        broker: Any | None = None,
    ) -> None:
        self.broker = broker

        self._submitted_intents: set[str] = set()
        self._submitting_intents: set[str] = set()
        self._lock = RLock()

        self.total_requests = 0
        self.total_submissions = 0
        self.total_failures = 0
        self.total_rejections = 0
        self.total_duplicates_blocked = 0

        self.last_intent_id: str | None = None
        self.last_symbol: str | None = None
        self.last_state: str | None = None
        self.last_error: str | None = None
        self.last_order: dict[str, Any] | None = None

    # ============================================================
    # BROKER
    # ============================================================

    def set_broker(
        self,
        broker: Any | None,
    ) -> None:
        self.broker = broker

    # ============================================================
    # PROCESS
    # ============================================================

    async def process(
        self,
        intent: TradeIntent,
        account: AccountState,
        automation_enabled: bool = True,
        user_approved: bool = False,
        market_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if intent is None:
            raise ValueError("Trade intent is required")

        if account is None:
            raise ValueError("Account state is required")

        intent_id = str(intent.intent_id or "").strip()

        if not intent_id:
            raise ValueError("Trade intent ID is required")

        self.total_requests += 1

        self.last_intent_id = intent_id
        self.last_symbol = str(intent.symbol or "").strip().upper()
        self.last_error = None
        self.last_order = None

        audit.log(
            "TRADE_INTENT",
            intent_id,
            intent.model_dump(mode="json"),
        )

        # ========================================================
        # DUPLICATE PROTECTION
        # ========================================================

        duplicate = self._duplicate_state(intent_id)

        if duplicate is not None:
            self.total_duplicates_blocked += 1
            self.last_state = "DUPLICATE_BLOCKED"
            self.last_error = duplicate

            audit.log(
                "DUPLICATE_EXECUTION_BLOCKED",
                intent_id,
                {"reason": duplicate},
            )

            return {
                "state": "DUPLICATE_BLOCKED",
                "error": duplicate,
            }

        # ========================================================
        # AUTOMATIC MARKET SAFETY
        # ========================================================

        market_safety: dict[str, Any] | None = None

        if intent.execution_mode == ExecutionMode.AUTOMATIC:
            if not automation_enabled:
                self.last_state = "AUTOMATION_DISABLED"
                self.last_error = "Automatic trading permission is disabled"

                audit.log(
                    "AUTOMATION_DISABLED",
                    intent_id,
                    {},
                )

                return {
                    "state": "AUTOMATION_DISABLED",
                    "error": self.last_error,
                }

            if market_data is None:
                reason = (
                    "Automatic execution requires current "
                    "real market data"
                )

                self.last_state = "MARKET_SAFETY_BLOCKED"
                self.last_error = reason

                market_safety = {
                    "safe": False,
                    "state": "BLOCKED",
                    "reasons": [reason],
                }

                audit.log(
                    "MARKET_SAFETY_BLOCKED",
                    intent_id,
                    {"reason": reason},
                )

                return {
                    "state": "MARKET_SAFETY_BLOCKED",
                    "market_safety": market_safety,
                    "error": reason,
                }

            market_safety = market_safety_service.validate(
                market_data,
                require_provider_approval=True,
            )

            audit.log(
                "MARKET_SAFETY",
                intent_id,
                market_safety,
            )

            if not market_safety.get("safe", False):
                reason = self._market_safety_error(
                    market_safety
                )

                self.last_state = "MARKET_SAFETY_BLOCKED"
                self.last_error = reason

                return {
                    "state": "MARKET_SAFETY_BLOCKED",
                    "market_safety": market_safety,
                    "error": reason,
                }

        # ========================================================
        # RISK
        # ========================================================

        decision = risk_engine.evaluate(
            intent,
            account,
            automation_enabled,
        )

        risk_view = decision.model_dump(mode="json")

        audit.log(
            "RISK_DECISION",
            intent_id,
            risk_view,
        )

        if decision.status == RiskStatus.REJECTED:
            self.total_rejections += 1

            reason = self._risk_error(risk_view)

            self.last_state = "REJECTED"
            self.last_error = reason

            return {
                "state": "REJECTED",
                "risk": risk_view,
                "market_safety": market_safety,
                "error": reason,
            }

        # ========================================================
        # MANUAL APPROVAL
        # ========================================================

        if (
            intent.execution_mode == ExecutionMode.MANUAL
            and not user_approved
        ):
            self.last_state = "AWAITING_USER_APPROVAL"

            return {
                "state": "AWAITING_USER_APPROVAL",
                "risk": risk_view,
                "market_safety": market_safety,
            }

        # ========================================================
        # CONTROLLED APPROVAL
        # ========================================================

        if (
            intent.execution_mode == ExecutionMode.CONTROLLED
            and not user_approved
        ):
            self.last_state = "AWAITING_APPROVAL"

            return {
                "state": "AWAITING_APPROVAL",
                "risk": risk_view,
                "market_safety": market_safety,
            }

        # ========================================================
        # BROKER REQUIRED
        # ========================================================

        if self.broker is None:
            return self._execution_failure(
                intent_id=intent_id,
                error="No broker configured",
                risk=risk_view,
                market_safety=market_safety,
            )

        # ========================================================
        # BROKER CAPABILITY
        # ========================================================

        capability_error = self._validate_broker_capability(
            intent
        )

        if capability_error:
            self.total_failures += 1
            self.last_state = "BROKER_CAPABILITY_BLOCKED"
            self.last_error = capability_error

            audit.log(
                "BROKER_CAPABILITY_BLOCKED",
                intent_id,
                {"error": capability_error},
            )

            return {
                "state": "BROKER_CAPABILITY_BLOCKED",
                "risk": risk_view,
                "market_safety": market_safety,
                "error": capability_error,
            }

        # ========================================================
        # RESERVE INTENT
        # ========================================================

        reservation_error = self._reserve_intent(
            intent_id
        )

        if reservation_error:
            self.total_duplicates_blocked += 1
            self.last_state = "DUPLICATE_BLOCKED"
            self.last_error = reservation_error

            audit.log(
                "DUPLICATE_EXECUTION_BLOCKED",
                intent_id,
                {"reason": reservation_error},
            )

            return {
                "state": "DUPLICATE_BLOCKED",
                "risk": risk_view,
                "market_safety": market_safety,
                "error": reservation_error,
            }

        # ========================================================
        # BROKER SUBMISSION
        # ========================================================

        try:
            self.total_submissions += 1

            audit.log(
                "BROKER_SUBMISSION_REQUESTED",
                intent_id,
                {
                    "symbol": intent.symbol,
                    "side": intent.side.value,
                    "qty": intent.qty,
                    "execution_mode": intent.execution_mode.value,
                    "strategy": intent.strategy,
                    "automation_id": intent.automation_id,
                    "asset_type": intent.asset_type.value,
                },
            )

            order = await self.broker.submit(intent)

        except Exception as exc:
            self._release_intent(intent_id)

            return self._execution_failure(
                intent_id=intent_id,
                error=str(exc),
                risk=risk_view,
                market_safety=market_safety,
            )

        # ========================================================
        # BROKER RESPONSE
        # ========================================================

        if order is None:
            self._release_intent(intent_id)

            return self._execution_failure(
                intent_id=intent_id,
                error="Broker returned no order",
                risk=risk_view,
                market_safety=market_safety,
            )

        order_view = self._order_view(order)

        if order_view is None:
            self._release_intent(intent_id)

            return self._execution_failure(
                intent_id=intent_id,
                error="Broker returned an unsupported order response",
                risk=risk_view,
                market_safety=market_safety,
            )

        order_status = self._order_status(
            order,
            order_view,
        )

        broker_order_id = self._broker_order_id(
            order_view
        )

        if not broker_order_id:
            self._release_intent(intent_id)

            return self._execution_failure(
                intent_id=intent_id,
                error=(
                    "Broker response does not contain "
                    "a broker order ID"
                ),
                risk=risk_view,
                market_safety=market_safety,
            )

        # ========================================================
        # MARK SUBMITTED
        # ========================================================

        self._mark_submitted(intent_id)

        self.last_state = order_status
        self.last_order = order_view
        self.last_error = None

        # ========================================================
        # PERSIST REAL BROKER SUBMISSION
        # ========================================================

        try:
            self._persist_trade_record(
                intent=intent,
                order_view=order_view,
                order_status=order_status,
            )

        except Exception as exc:
            self.total_failures += 1
            self.last_error = (
                "Broker order was submitted but local trade "
                f"persistence failed: {exc}"
            )

            audit.log(
                "TRADE_PERSISTENCE_FAILED",
                intent_id,
                {
                    "broker_order_id": broker_order_id,
                    "state": order_status,
                    "error": str(exc),
                },
            )

            return {
                "state": order_status,
                "risk": risk_view,
                "market_safety": market_safety,
                "order": order_view,
                "persistence": {
                    "ok": False,
                    "error": str(exc),
                },
            }

        # ========================================================
        # AUDIT
        # ========================================================

        audit.log(
            "BROKER_ORDER",
            intent_id,
            order_view,
        )

        audit.log(
            "EXECUTION_COMPLETED",
            intent_id,
            {
                "state": order_status,
                "symbol": intent.symbol,
                "side": intent.side.value,
                "qty": intent.qty,
                "strategy": intent.strategy,
                "automation_id": intent.automation_id,
                "asset_type": intent.asset_type.value,
                "broker_order_id": broker_order_id,
            },
        )

        return {
            "state": order_status,
            "risk": risk_view,
            "market_safety": market_safety,
            "order": order_view,
            "persistence": {
                "ok": True,
            },
        }

    # ============================================================
    # EXECUTION FAILURE
    # ============================================================

    def _execution_failure(
        self,
        *,
        intent_id: str,
        error: str,
        risk: dict[str, Any] | None,
        market_safety: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self.total_failures += 1
        self.last_state = "EXECUTION_FAILED"
        self.last_error = error

        audit.log(
            "EXECUTION_FAILED",
            intent_id,
            {"error": error},
        )

        return {
            "state": "EXECUTION_FAILED",
            "risk": risk,
            "market_safety": market_safety,
            "error": error,
        }

    # ============================================================
    # DUPLICATE STATE
    # ============================================================

    def _duplicate_state(
        self,
        intent_id: str,
    ) -> str | None:
        with self._lock:
            if intent_id in self._submitted_intents:
                return (
                    "Trade intent has already been submitted"
                )

            if intent_id in self._submitting_intents:
                return (
                    "Trade intent is already being submitted"
                )

        return None

    # ============================================================
    # RESERVE INTENT
    # ============================================================

    def _reserve_intent(
        self,
        intent_id: str,
    ) -> str | None:
        with self._lock:
            if intent_id in self._submitted_intents:
                return (
                    "Trade intent has already been submitted"
                )

            if intent_id in self._submitting_intents:
                return (
                    "Trade intent is already being submitted"
                )

            self._submitting_intents.add(intent_id)

        return None

    # ============================================================
    # RELEASE INTENT
    # ============================================================

    def _release_intent(
        self,
        intent_id: str,
    ) -> None:
        with self._lock:
            self._submitting_intents.discard(intent_id)

    # ============================================================
    # MARK SUBMITTED
    # ============================================================

    def _mark_submitted(
        self,
        intent_id: str,
    ) -> None:
        with self._lock:
            self._submitting_intents.discard(intent_id)
            self._submitted_intents.add(intent_id)

    # ============================================================
    # BROKER CAPABILITY
    # ============================================================

    def _validate_broker_capability(
        self,
        intent: TradeIntent,
    ) -> str | None:
        broker = self.broker

        if broker is None:
            return "No broker configured"

        is_connected = getattr(
            broker,
            "is_connected",
            None,
        )

        if callable(is_connected):
            try:
                connected = is_connected()

                if connected is False:
                    return "Broker is not connected"

            except Exception as exc:
                return (
                    "Unable to verify broker connection: "
                    f"{exc}"
                )

        supports_intent = getattr(
            broker,
            "supports_intent",
            None,
        )

        if callable(supports_intent):
            try:
                if not supports_intent(intent):
                    return (
                        "Broker does not support this trade intent"
                    )

            except Exception as exc:
                return (
                    "Unable to verify broker capability: "
                    f"{exc}"
                )

        supports_asset_type = getattr(
            broker,
            "supports_asset_type",
            None,
        )

        if callable(supports_asset_type):
            try:
                if not supports_asset_type(
                    intent.asset_type
                ):
                    asset_value = getattr(
                        intent.asset_type,
                        "value",
                        intent.asset_type,
                    )

                    return (
                        "Broker does not support asset type "
                        f"{asset_value}"
                    )

            except Exception as exc:
                return (
                    "Unable to verify broker asset capability: "
                    f"{exc}"
                )

        return None

    # ============================================================
    # ORDER VIEW
    # ============================================================

    @staticmethod
    def _order_view(
        order: Any,
    ) -> dict[str, Any] | None:
        try:
            value = order.model_dump(mode="json")

            if isinstance(value, dict):
                return value

        except AttributeError:
            pass

        if isinstance(order, dict):
            return dict(order)

        return None

    # ============================================================
    # BROKER ORDER ID
    # ============================================================

    @staticmethod
    def _broker_order_id(
        order_view: dict[str, Any],
    ) -> str | None:
        value = (
            order_view.get("order_id")
            or order_view.get("id")
        )

        if value is None:
            return None

        normalized = str(value).strip()

        return normalized or None

    # ============================================================
    # ORDER STATUS
    # ============================================================

    @staticmethod
    def _order_status(
        order: Any,
        order_view: dict[str, Any],
    ) -> str:
        raw_status = getattr(
            order,
            "status",
            None,
        )

        if raw_status is None:
            raw_status = order_view.get(
                "status"
            )

        if raw_status is None:
            return "SUBMITTED"

        value = getattr(
            raw_status,
            "value",
            raw_status,
        )

        normalized = str(value).strip()

        if not normalized:
            return "SUBMITTED"

        return normalized.upper()

    # ============================================================
    # MARKET SAFETY ERROR
    # ============================================================

    @staticmethod
    def _market_safety_error(
        market_safety: dict[str, Any],
    ) -> str:
        reasons = (
            market_safety.get("reasons")
            or []
        )

        if isinstance(reasons, list):
            clean = [
                str(reason)
                for reason in reasons
                if str(reason).strip()
            ]

            if clean:
                return "; ".join(clean)

        return (
            "Market safety rejected automatic execution"
        )

    # ============================================================
    # RISK ERROR
    # ============================================================

    @staticmethod
    def _risk_error(
        risk_view: dict[str, Any],
    ) -> str:
        reasons = (
            risk_view.get("reasons")
            or []
        )

        if isinstance(reasons, list):
            clean = [
                str(reason)
                for reason in reasons
                if str(reason).strip()
            ]

            if clean:
                return "; ".join(clean)

        return "Risk Engine rejected the trade intent"

    # ============================================================
    # TRADE PERSISTENCE
    # ============================================================

    @staticmethod
    def _persist_trade_record(
        *,
        intent: TradeIntent,
        order_view: dict[str, Any],
        order_status: str,
    ) -> None:
        now = datetime.now(timezone.utc)

        normalized_status = str(
            order_status or "SUBMITTED"
        ).strip().upper()

        broker_order_id = (
            ExecutionService._broker_order_id(
                order_view
            )
        )

        if not broker_order_id:
            raise RuntimeError(
                "Cannot persist trade without "
                "a broker order ID"
            )

        broker_name = str(
            order_view.get("broker")
            or ""
        ).strip() or None

        entry_price = None

        if normalized_status in {
            "FILLED",
            "PARTIALLY_FILLED",
        }:
            entry_price = (
                ExecutionService._broker_filled_price(
                    order_view
                )
            )

            if entry_price is None:
                entry_price = (
                    ExecutionService._safe_float(
                        order_view.get("price")
                    )
                )

        with SessionLocal() as session:
            record = session.scalar(
                select(
                    TradeRecord
                ).where(
                    TradeRecord.intent_id
                    == intent.intent_id
                )
            )

            if record is None:
                record = TradeRecord(
                    intent_id=intent.intent_id,
                    automation_id=intent.automation_id,
                    broker=broker_name,
                    broker_order_id=broker_order_id,
                    symbol=intent.symbol,
                    asset_type=intent.asset_type.value,
                    strategy=intent.strategy,
                    execution_mode=(
                        intent.execution_mode.value
                    ),
                    side=intent.side.value,
                    qty=float(intent.qty),
                    order_type=intent.order_type,
                    time_in_force=intent.time_in_force,
                    reference_price=float(
                        intent.reference_price
                    ),
                    entry_price=entry_price,
                    stop=intent.stop,
                    target=intent.target,
                    max_loss=intent.max_loss,
                    status=normalized_status,
                    opened_at=(
                        now
                        if entry_price is not None
                        else None
                    ),
                )

                session.add(record)

            else:
                if broker_name:
                    record.broker = broker_name

                record.broker_order_id = (
                    broker_order_id
                )

                record.status = normalized_status

                if entry_price is not None:
                    record.entry_price = entry_price

                    record.opened_at = (
                        record.opened_at
                        or now
                    )

                record.updated_at = now

            session.commit()

    # ============================================================
    # SAFE FLOAT
    # ============================================================

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        try:
            return float(value)

        except (TypeError, ValueError):
            return None

    # ============================================================
    # BROKER DATETIME
    # ============================================================

    @staticmethod
    def _parse_broker_datetime(
        value: Any,
    ) -> datetime | None:
        if value is None:
            return None

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(
                    tzinfo=timezone.utc
                )

            return value

        raw = str(value).strip()

        if not raw:
            return None

        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        try:
            parsed = datetime.fromisoformat(
                raw
            )

        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed

    # ============================================================
    # NORMALIZED BROKER STATUS
    # ============================================================

    @staticmethod
    def _normalized_broker_status(
        order: dict[str, Any],
    ) -> str:
        return str(
            order.get("status")
            or "UNKNOWN"
        ).strip().upper()

    # ============================================================
    # BROKER FILLED PRICE
    # ============================================================

    @classmethod
    def _broker_filled_price(
        cls,
        order: dict[str, Any],
    ) -> float | None:
        return cls._safe_float(
            order.get("filled_avg_price")
        )

    # ============================================================
    # BROKER FILLED QUANTITY
    # ============================================================

    @classmethod
    def _broker_filled_qty(
        cls,
        order: dict[str, Any],
    ) -> float | None:
        return cls._safe_float(
            order.get("filled_qty")
        )

    # ============================================================
    # TRADE RECORD VIEW
    # ============================================================

    @staticmethod
    def _trade_record_view(
        record: TradeRecord,
    ) -> dict[str, Any]:
        return {
            "id": record.id,
            "intent_id": record.intent_id,
            "automation_id": record.automation_id,
            "broker": record.broker,
            "broker_order_id": record.broker_order_id,
            "exit_broker_order_id": (
                record.exit_broker_order_id
            ),
            "symbol": record.symbol,
            "asset_type": record.asset_type,
            "strategy": record.strategy,
            "execution_mode": record.execution_mode,
            "side": record.side,
            "qty": record.qty,
            "entry_price": record.entry_price,
            "exit_price": record.exit_price,
            "pnl": record.pnl,
            "status": record.status,
            "opened_at": (
                record.opened_at.isoformat()
                if record.opened_at
                else None
            ),
            "closed_at": (
                record.closed_at.isoformat()
                if record.closed_at
                else None
            ),
            "updated_at": (
                record.updated_at.isoformat()
                if record.updated_at
                else None
            ),
        }

    # ============================================================
    # REQUIRE BROKER METHOD
    # ============================================================

    def _require_broker_method(
        self,
        method_name: str,
    ) -> Any:
        if self.broker is None:
            raise RuntimeError(
                "No broker configured for "
                "execution reconciliation."
            )

        method = getattr(
            self.broker,
            method_name,
            None,
        )

        if not callable(method):
            raise RuntimeError(
                "Configured broker does not support "
                f"{method_name}()."
            )

        return method

    # ============================================================
    # ENTRY RECONCILIATION
    # ============================================================

    def reconcile_trade(
        self,
        intent_id: str,
    ) -> dict[str, Any]:
        normalized_intent_id = str(
            intent_id
        ).strip()

        if not normalized_intent_id:
            raise ValueError(
                "Trade intent ID is required."
            )

        with SessionLocal() as session:
            record = session.scalar(
                select(
                    TradeRecord
                ).where(
                    TradeRecord.intent_id
                    == normalized_intent_id
                )
            )

            if record is None:
                raise ValueError(
                    "No persisted trade record "
                    "exists for intent "
                    f"'{normalized_intent_id}'."
                )

            broker_order_id = (
                str(
                    record.broker_order_id
                    or ""
                ).strip()
                or None
            )

        if broker_order_id:
            get_order = self._require_broker_method(
                "get_order"
            )

            broker_order = get_order(
                broker_order_id
            )

        else:
            get_by_client_order_id = (
                self._require_broker_method(
                    "get_order_by_client_order_id"
                )
            )

            broker_order = (
                get_by_client_order_id(
                    normalized_intent_id
                )
            )

        if not isinstance(
            broker_order,
            dict,
        ):
            raise RuntimeError(
                "Broker returned an invalid "
                "order during reconciliation."
            )

        broker_symbol = str(
            broker_order.get("symbol")
            or ""
        ).strip().upper()

        broker_side = str(
            broker_order.get("side")
            or ""
        ).strip().upper()

        broker_id = str(
            broker_order.get("id")
            or broker_order.get("order_id")
            or ""
        ).strip() or None

        status = self._normalized_broker_status(
            broker_order
        )

        filled_price = self._broker_filled_price(
            broker_order
        )

        filled_at = self._parse_broker_datetime(
            broker_order.get("filled_at")
        )

        now = datetime.now(timezone.utc)

        with SessionLocal() as session:
            record = session.scalar(
                select(
                    TradeRecord
                ).where(
                    TradeRecord.intent_id
                    == normalized_intent_id
                )
            )

            if record is None:
                raise ValueError(
                    "Trade record disappeared "
                    "during reconciliation."
                )

            expected_symbol = str(
                record.symbol
                or ""
            ).strip().upper()

            expected_side = str(
                record.side
                or ""
            ).strip().upper()

            if (
                broker_symbol
                and broker_symbol
                != expected_symbol
            ):
                raise RuntimeError(
                    "Broker entry order symbol "
                    "does not match the "
                    "persisted trade record."
                )

            if (
                broker_side
                and broker_side
                != expected_side
            ):
                raise RuntimeError(
                    "Broker entry order side "
                    "does not match the "
                    "persisted trade record."
                )

            if broker_id:
                record.broker_order_id = broker_id

            record.status = status

            if (
                status
                in {
                    "FILLED",
                    "PARTIALLY_FILLED",
                }
                and filled_price is not None
            ):
                record.entry_price = filled_price

                record.opened_at = (
                    record.opened_at
                    or filled_at
                    or now
                )

            record.updated_at = now

            session.commit()
            session.refresh(record)

            view = self._trade_record_view(
                record
            )

        audit.log(
            "TRADE_ENTRY_RECONCILED",
            normalized_intent_id,
            {
                "broker_order_id": (
                    broker_id
                    or broker_order_id
                ),
                "status": status,
                "filled_avg_price": filled_price,
            },
        )

        return view

    # ============================================================
    # RECONCILE OPEN TRADES
    # ============================================================

    def reconcile_open_trades(
        self,
    ) -> dict[str, Any]:
        with SessionLocal() as session:
            intent_ids = [
                str(intent_id)
                for intent_id
                in session.scalars(
                    select(
                        TradeRecord.intent_id
                    ).where(
                        TradeRecord.closed_at.is_(
                            None
                        ),
                        TradeRecord.intent_id.is_not(
                            None
                        ),
                    )
                ).all()
                if intent_id
            ]

        results: list[dict[str, Any]] = []

        for intent_id in intent_ids:
            try:
                results.append(
                    {
                        "intent_id": intent_id,
                        "ok": True,
                        "trade": self.reconcile_trade(
                            intent_id
                        ),
                    }
                )

            except Exception as exc:
                results.append(
                    {
                        "intent_id": intent_id,
                        "ok": False,
                        "error": str(exc),
                    }
                )

                audit.log(
                    "TRADE_ENTRY_RECONCILIATION_FAILED",
                    intent_id,
                    {
                        "error": str(exc),
                    },
                )

        successful = sum(
            1
            for item in results
            if item.get("ok") is True
        )

        return {
            "requested": len(intent_ids),
            "successful": successful,
            "failed": (
                len(results)
                - successful
            ),
            "results": results,
        }

    # ============================================================
    # EXIT RECONCILIATION
    # ============================================================

    def reconcile_exit_order(
        self,
        intent_id: str,
        exit_order_id: str,
    ) -> dict[str, Any]:
        normalized_intent_id = str(
            intent_id
        ).strip()

        normalized_exit_order_id = str(
            exit_order_id
        ).strip()

        if not normalized_intent_id:
            raise ValueError(
                "Trade intent ID is required."
            )

        if not normalized_exit_order_id:
            raise ValueError(
                "Exit broker order ID is required."
            )

        self.reconcile_trade(
            normalized_intent_id
        )

        get_order = self._require_broker_method(
            "get_order"
        )

        exit_order = get_order(
            normalized_exit_order_id
        )

        if not isinstance(
            exit_order,
            dict,
        ):
            raise RuntimeError(
                "Broker returned an invalid exit order."
            )

        exit_status = self._normalized_broker_status(
            exit_order
        )

        if exit_status != "FILLED":
            return {
                "state": "EXIT_NOT_FILLED",
                "intent_id": normalized_intent_id,
                "exit_order_id": (
                    normalized_exit_order_id
                ),
                "broker_status": exit_status,
            }

        exit_price = self._broker_filled_price(
            exit_order
        )

        if exit_price is None:
            raise RuntimeError(
                "Filled exit order does not contain "
                "broker filled_avg_price."
            )

        exit_filled_qty = self._broker_filled_qty(
            exit_order
        )

        if exit_filled_qty is None:
            raise RuntimeError(
                "Filled exit order does not contain "
                "broker filled_qty."
            )

        exit_filled_at = self._parse_broker_datetime(
            exit_order.get("filled_at")
        )

        if exit_filled_at is None:
            raise RuntimeError(
                "Filled exit order does not contain "
                "a valid broker filled_at timestamp."
            )

        exit_symbol = str(
            exit_order.get("symbol")
            or ""
        ).strip().upper()

        exit_side = str(
            exit_order.get("side")
            or ""
        ).strip().upper()

        actual_exit_order_id = str(
            exit_order.get("id")
            or exit_order.get("order_id")
            or normalized_exit_order_id
        ).strip()

        now = datetime.now(timezone.utc)

        with SessionLocal() as session:
            record = session.scalar(
                select(
                    TradeRecord
                ).where(
                    TradeRecord.intent_id
                    == normalized_intent_id
                )
            )

            if record is None:
                raise ValueError(
                    "No persisted trade record exists "
                    "for intent "
                    f"'{normalized_intent_id}'."
                )

            if record.closed_at is not None:
                if (
                    record.exit_broker_order_id
                    == actual_exit_order_id
                ):
                    return {
                        "state": "ALREADY_CLOSED",
                        "trade": (
                            self._trade_record_view(
                                record
                            )
                        ),
                    }

                raise RuntimeError(
                    "Trade is already closed by a "
                    "different broker exit order."
                )

            entry_price = self._safe_float(
                record.entry_price
            )

            if entry_price is None:
                raise RuntimeError(
                    "Cannot close trade because the "
                    "broker-confirmed entry fill price "
                    "is not available."
                )

            expected_symbol = str(
                record.symbol
                or ""
            ).strip().upper()

            entry_side = str(
                record.side
                or ""
            ).strip().upper()

            trade_qty = abs(
                float(record.qty)
            )

            if not exit_symbol:
                raise RuntimeError(
                    "Exit order does not contain a symbol."
                )

            if exit_symbol != expected_symbol:
                raise RuntimeError(
                    "Exit order symbol does not match "
                    "the persisted trade record."
                )

            expected_exit_side = (
                "SELL"
                if entry_side == "BUY"
                else (
                    "BUY"
                    if entry_side == "SELL"
                    else None
                )
            )

            if expected_exit_side is None:
                raise RuntimeError(
                    "Persisted trade has an "
                    "unsupported entry side."
                )

            if exit_side != expected_exit_side:
                raise RuntimeError(
                    "Exit order side is not opposite "
                    "the entry side."
                )

            if (
                exit_filled_qty
                + 1e-12
                < trade_qty
            ):
                return {
                    "state": "PARTIAL_EXIT",
                    "intent_id": normalized_intent_id,
                    "exit_order_id": (
                        actual_exit_order_id
                    ),
                    "trade_qty": trade_qty,
                    "filled_exit_qty": (
                        exit_filled_qty
                    ),
                }

            if entry_side == "BUY":
                pnl = (
                    exit_price
                    - entry_price
                ) * trade_qty

            else:
                pnl = (
                    entry_price
                    - exit_price
                ) * trade_qty

            record.exit_broker_order_id = (
                actual_exit_order_id
            )

            record.exit_price = exit_price
            record.pnl = float(pnl)
            record.closed_at = exit_filled_at
            record.status = "CLOSED"
            record.updated_at = now

            session.commit()
            session.refresh(record)

            view = self._trade_record_view(
                record
            )

        audit.log(
            "TRADE_EXIT_RECONCILED",
            normalized_intent_id,
            {
                "exit_broker_order_id": (
                    actual_exit_order_id
                ),
                "symbol": exit_symbol,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "qty": trade_qty,
                "pnl": pnl,
                "closed_at": (
                    exit_filled_at.isoformat()
                ),
            },
        )

        return {
            "state": "CLOSED",
            "trade": view,
        }

    # ============================================================
    # STATUS
    # ============================================================

    def status(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            submitted_count = len(
                self._submitted_intents
            )

            submitting_count = len(
                self._submitting_intents
            )

        broker_name = None

        if self.broker is not None:
            broker_name = (
                self.broker.__class__.__name__
            )

        return {
            "service": "execution",
            "broker_configured": (
                self.broker is not None
            ),
            "broker": broker_name,
            "submitted_intents": (
                submitted_count
            ),
            "submitting_intents": (
                submitting_count
            ),
            "total_requests": (
                self.total_requests
            ),
            "total_submissions": (
                self.total_submissions
            ),
            "total_failures": (
                self.total_failures
            ),
            "total_rejections": (
                self.total_rejections
            ),
            "total_duplicates_blocked": (
                self.total_duplicates_blocked
            ),
            "last_intent_id": (
                self.last_intent_id
            ),
            "last_symbol": (
                self.last_symbol
            ),
            "last_state": (
                self.last_state
            ),
            "last_error": (
                self.last_error
            ),
            "last_order": (
                self.last_order
            ),
        }


execution_service = ExecutionService()