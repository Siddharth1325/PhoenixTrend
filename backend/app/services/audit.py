from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import json
import logging
import math
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from ..db import AuditEvent, SessionLocal


logger = logging.getLogger(__name__)


class AuditService:
    """
    PhoenixTrend persistent audit service.

    This service is the shared, non-authoritative audit sink for security,
    trading, automation, risk, broker, account and runtime events.

    Audit logging NEVER:

        - approves a trade
        - blocks a trade by itself
        - changes a TradeIntent
        - changes a RiskEngine decision
        - changes a Market Safety decision
        - submits an order
        - retries an order
        - fabricates execution state
        - exposes secrets intentionally

    The caller remains authoritative for business logic.

    Audit persistence is intentionally non-fatal. A database failure is
    logged through Python logging and returns False to the caller instead
    of crashing an otherwise valid trading workflow.

    Sensitive fields are recursively redacted before persistence.
    """

    # =====================================================================
    # EVENT TYPES
    # =====================================================================

    TRADE_INTENT = "TRADE_INTENT"

    MARKET_SAFETY = "MARKET_SAFETY"
    MARKET_SAFETY_BLOCKED = "MARKET_SAFETY_BLOCKED"

    RISK_DECISION = "RISK_DECISION"
    RISK_BLOCKED = "RISK_BLOCKED"

    BROKER_CAPABILITY = "BROKER_CAPABILITY"
    BROKER_CAPABILITY_BLOCKED = "BROKER_CAPABILITY_BLOCKED"

    BROKER_ORDER = "BROKER_ORDER"
    BROKER_ORDER_FILLED = "BROKER_ORDER_FILLED"
    BROKER_ORDER_REJECTED = "BROKER_ORDER_REJECTED"
    BROKER_ORDER_CANCELLED = "BROKER_ORDER_CANCELLED"

    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    DUPLICATE_EXECUTION_BLOCKED = "DUPLICATE_EXECUTION_BLOCKED"

    POSITION_OPENED = "POSITION_OPENED"
    POSITION_UPDATED = "POSITION_UPDATED"
    POSITION_CLOSED = "POSITION_CLOSED"

    AUTOMATION_ENABLED = "AUTOMATION_ENABLED"
    AUTOMATION_DISABLED = "AUTOMATION_DISABLED"
    AUTOMATION_STARTED = "AUTOMATION_STARTED"
    AUTOMATION_STOPPED = "AUTOMATION_STOPPED"
    AUTOMATION_PAUSED = "AUTOMATION_PAUSED"
    AUTOMATION_RESUMED = "AUTOMATION_RESUMED"
    AUTOMATION_RUNTIME_FAILURE = "AUTOMATION_RUNTIME_FAILURE"

    EMERGENCY_STOP = "EMERGENCY_STOP"

    MANUAL_TRADE_ANALYSIS = "MANUAL_TRADE_ANALYSIS"
    MANUAL_TRADE_CONFIRMATION = "MANUAL_TRADE_CONFIRMATION"
    MANUAL_TRADE_REJECTED = "MANUAL_TRADE_REJECTED"

    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"

    BROKER_CONNECTED = "BROKER_CONNECTED"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    BROKER_CONNECTION_FAILED = "BROKER_CONNECTION_FAILED"

    SETTINGS_UPDATED = "SETTINGS_UPDATED"

    # =====================================================================
    # LIMITS
    # =====================================================================

    MAX_EVENT_TYPE_LENGTH = 128
    MAX_ENTITY_ID_LENGTH = 512

    MAX_DETAIL_DEPTH = 12
    MAX_COLLECTION_ITEMS = 500
    MAX_STRING_LENGTH = 16_384

    DEFAULT_RECENT_LIMIT = 100
    MAX_RECENT_LIMIT = 1000

    REDACTED = "[REDACTED]"

    # =====================================================================
    # SENSITIVE FIELD PROTECTION
    # =====================================================================

    _SENSITIVE_EXACT_KEYS = frozenset(
        {
            "password",
            "passwd",
            "passphrase",
            "pwd",
            "secret",
            "secret_key",
            "client_secret",
            "api_secret",
            "api_key",
            "apikey",
            "access_key",
            "access_key_id",
            "secret_access_key",
            "private_key",
            "privatekey",
            "authorization",
            "proxy_authorization",
            "cookie",
            "set_cookie",
            "session_cookie",
            "session_token",
            "access_token",
            "refresh_token",
            "id_token",
            "bearer_token",
            "jwt",
            "token",
            "credential",
            "credentials",
            "broker_credentials",
            "data_provider_credentials",
            "oauth_token",
            "oauth_secret",
        }
    )

    _SENSITIVE_KEY_FRAGMENTS = (
        "password",
        "passwd",
        "passphrase",
        "secret",
        "private_key",
        "authorization",
        "access_token",
        "refresh_token",
        "session_token",
        "bearer_token",
        "api_key",
        "apikey",
        "credential",
    )

    _BEARER_PATTERN = re.compile(
        r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]+=*"
    )

    _BASIC_PATTERN = re.compile(
        r"(?i)\bbasic\s+[A-Za-z0-9+/]+=*"
    )

    _SECRET_ASSIGNMENT_PATTERN = re.compile(
        r"(?i)"
        r"\b("
        r"password|passwd|passphrase|"
        r"secret|client_secret|api_secret|"
        r"api_key|apikey|access_token|"
        r"refresh_token|session_token|"
        r"bearer_token|authorization"
        r")"
        r"\s*[:=]\s*"
        r"([^\s,;]+)"
    )

    # =====================================================================
    # PRIMARY LOG METHOD
    # =====================================================================

    def log(
        self,
        event_type: str,
        entity_id: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        """
        Persist one audit event.

        Returns:

            True
                The audit event was committed successfully.

            False
                The event was invalid or persistence failed.

        Audit failure is intentionally non-fatal to the caller.
        """

        normalized_event_type = self._normalize_event_type(
            event_type
        )

        if normalized_event_type is None:
            logger.error(
                "Audit event rejected: invalid or missing event_type"
            )
            return False

        normalized_entity_id = self._normalize_entity_id(
            entity_id
        )

        normalized_detail = self._normalize_detail(
            detail
        )

        payload = self._serialize(
            normalized_detail
        )

        session = SessionLocal()

        try:
            event = AuditEvent(
                event_type=normalized_event_type,
                entity_id=normalized_entity_id,
                detail=payload,
            )

            session.add(
                event
            )

            session.commit()

            return True

        except Exception:
            try:
                session.rollback()
            except Exception:
                logger.exception(
                    "Audit session rollback failed"
                )

            logger.exception(
                "Failed to persist audit event %s for %s",
                normalized_event_type,
                normalized_entity_id,
            )

            return False

        finally:
            try:
                session.close()
            except Exception:
                logger.exception(
                    "Audit session close failed"
                )

    # =====================================================================
    # CONVENIENCE EVENT HELPERS
    # =====================================================================

    def trade_intent(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.TRADE_INTENT,
            entity_id,
            detail,
        )

    def market_safety(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
        *,
        blocked: bool = False,
    ) -> bool:
        return self.log(
            (
                self.MARKET_SAFETY_BLOCKED
                if blocked
                else self.MARKET_SAFETY
            ),
            entity_id,
            detail,
        )

    def risk_decision(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
        *,
        blocked: bool = False,
    ) -> bool:
        return self.log(
            (
                self.RISK_BLOCKED
                if blocked
                else self.RISK_DECISION
            ),
            entity_id,
            detail,
        )

    def broker_capability(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
        *,
        blocked: bool = False,
    ) -> bool:
        return self.log(
            (
                self.BROKER_CAPABILITY_BLOCKED
                if blocked
                else self.BROKER_CAPABILITY
            ),
            entity_id,
            detail,
        )

    def broker_order(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.BROKER_ORDER,
            entity_id,
            detail,
        )

    def execution_started(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.EXECUTION_STARTED,
            entity_id,
            detail,
        )

    def execution_completed(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.EXECUTION_COMPLETED,
            entity_id,
            detail,
        )

    def execution_failed(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.EXECUTION_FAILED,
            entity_id,
            detail,
        )

    def duplicate_execution_blocked(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.DUPLICATE_EXECUTION_BLOCKED,
            entity_id,
            detail,
        )

    def position_opened(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.POSITION_OPENED,
            entity_id,
            detail,
        )

    def position_updated(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.POSITION_UPDATED,
            entity_id,
            detail,
        )

    def position_closed(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.POSITION_CLOSED,
            entity_id,
            detail,
        )

    def automation_enabled(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.AUTOMATION_ENABLED,
            entity_id,
            detail,
        )

    def automation_disabled(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.AUTOMATION_DISABLED,
            entity_id,
            detail,
        )

    def automation_started(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.AUTOMATION_STARTED,
            entity_id,
            detail,
        )

    def automation_stopped(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.AUTOMATION_STOPPED,
            entity_id,
            detail,
        )

    def automation_paused(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.AUTOMATION_PAUSED,
            entity_id,
            detail,
        )

    def automation_resumed(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.AUTOMATION_RESUMED,
            entity_id,
            detail,
        )

    def automation_runtime_failure(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.AUTOMATION_RUNTIME_FAILURE,
            entity_id,
            detail,
        )

    def emergency_stop(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.EMERGENCY_STOP,
            entity_id,
            detail,
        )

    def manual_trade_analysis(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.MANUAL_TRADE_ANALYSIS,
            entity_id,
            detail,
        )

    def manual_trade_confirmation(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.MANUAL_TRADE_CONFIRMATION,
            entity_id,
            detail,
        )

    def manual_trade_rejected(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.MANUAL_TRADE_REJECTED,
            entity_id,
            detail,
        )

    def login(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.LOGIN,
            entity_id,
            detail,
        )

    def login_failed(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.LOGIN_FAILED,
            entity_id,
            detail,
        )

    def logout(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.LOGOUT,
            entity_id,
            detail,
        )

    def broker_connected(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.BROKER_CONNECTED,
            entity_id,
            detail,
        )

    def broker_disconnected(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.BROKER_DISCONNECTED,
            entity_id,
            detail,
        )

    def broker_connection_failed(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.BROKER_CONNECTION_FAILED,
            entity_id,
            detail,
        )

    def settings_updated(
        self,
        entity_id: str | None,
        detail: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.log(
            self.SETTINGS_UPDATED,
            entity_id,
            detail,
        )

    # =====================================================================
    # READ API
    # =====================================================================

    def recent(
        self,
        limit: int = DEFAULT_RECENT_LIMIT,
        *,
        event_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return recent persisted audit events.

        Filtering is exact after normalization.
        """

        try:
            safe_limit = int(
                limit
            )
        except (
            TypeError,
            ValueError,
        ):
            safe_limit = self.DEFAULT_RECENT_LIMIT

        safe_limit = max(
            1,
            min(
                safe_limit,
                self.MAX_RECENT_LIMIT,
            ),
        )

        normalized_event_type = None

        if event_type is not None:
            normalized_event_type = (
                self._normalize_event_type(
                    event_type
                )
            )

            if normalized_event_type is None:
                return []

        normalized_entity_id = None

        if entity_id is not None:
            normalized_entity_id = (
                self._normalize_entity_id(
                    entity_id
                )
            )

        session = SessionLocal()

        try:
            statement = select(
                AuditEvent
            )

            if normalized_event_type is not None:
                statement = statement.where(
                    AuditEvent.event_type
                    == normalized_event_type
                )

            if entity_id is not None:
                statement = statement.where(
                    AuditEvent.entity_id
                    == normalized_entity_id
                )

            created_at = getattr(
                AuditEvent,
                "created_at",
                None,
            )

            if created_at is not None:
                statement = statement.order_by(
                    created_at.desc()
                )

            else:
                event_id = getattr(
                    AuditEvent,
                    "id",
                    None,
                )

                if event_id is not None:
                    statement = statement.order_by(
                        event_id.desc()
                    )

            statement = statement.limit(
                safe_limit
            )

            rows = list(
                session.scalars(
                    statement
                ).all()
            )

            return [
                self._event_view(
                    row
                )
                for row in rows
            ]

        except Exception:
            logger.exception(
                "Failed to read audit events"
            )

            return []

        finally:
            try:
                session.close()
            except Exception:
                logger.exception(
                    "Audit read session close failed"
                )

    def for_entity(
        self,
        entity_id: str,
        *,
        limit: int = DEFAULT_RECENT_LIMIT,
    ) -> list[dict[str, Any]]:
        return self.recent(
            limit=limit,
            entity_id=entity_id,
        )

    def by_type(
        self,
        event_type: str,
        *,
        limit: int = DEFAULT_RECENT_LIMIT,
    ) -> list[dict[str, Any]]:
        return self.recent(
            limit=limit,
            event_type=event_type,
        )

    # =====================================================================
    # NORMALIZATION
    # =====================================================================

    def _normalize_event_type(
        self,
        event_type: Any,
    ) -> str | None:
        if event_type is None:
            return None

        normalized = str(
            event_type
        ).strip().upper()

        normalized = re.sub(
            r"[^A-Z0-9_]+",
            "_",
            normalized,
        )

        normalized = re.sub(
            r"_+",
            "_",
            normalized,
        ).strip(
            "_"
        )

        if not normalized:
            return None

        if len(
            normalized
        ) > self.MAX_EVENT_TYPE_LENGTH:
            normalized = normalized[
                :self.MAX_EVENT_TYPE_LENGTH
            ]

        return normalized

    def _normalize_entity_id(
        self,
        entity_id: Any,
    ) -> str | None:
        if entity_id is None:
            return None

        normalized = str(
            entity_id
        ).strip()

        if not normalized:
            return None

        if len(
            normalized
        ) > self.MAX_ENTITY_ID_LENGTH:
            normalized = normalized[
                :self.MAX_ENTITY_ID_LENGTH
            ]

        return normalized

    # =====================================================================
    # DETAIL NORMALIZATION
    # =====================================================================

    def _normalize_detail(
        self,
        detail: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if detail is None:
            return {}

        if not isinstance(
            detail,
            Mapping,
        ):
            return {
                "detail": self._safe_value(
                    detail,
                    key=None,
                    depth=0,
                )
            }

        result = self._safe_value(
            detail,
            key=None,
            depth=0,
        )

        if isinstance(
            result,
            dict,
        ):
            return result

        return {
            "detail": result,
        }

    def _safe_value(
        self,
        value: Any,
        *,
        key: str | None,
        depth: int,
    ) -> Any:
        if (
            key is not None
            and self._is_sensitive_key(
                key
            )
        ):
            return self.REDACTED

        if depth >= self.MAX_DETAIL_DEPTH:
            return "[MAX_DEPTH]"

        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            enum.Enum,
        ):
            return self._safe_value(
                value.value,
                key=key,
                depth=depth + 1,
            )

        if isinstance(
            value,
            Decimal,
        ):
            if not value.is_finite():
                return str(
                    value
                )

            return float(
                value
            )

        if isinstance(
            value,
            float,
        ):
            if not math.isfinite(
                value
            ):
                return str(
                    value
                )

            return value

        if isinstance(
            value,
            int,
        ):
            return value

        if isinstance(
            value,
            str,
        ):
            return self._sanitize_string(
                value
            )

        if isinstance(
            value,
            (
                dt.datetime,
                dt.date,
                dt.time,
            ),
        ):
            return value.isoformat()

        if dataclasses.is_dataclass(
            value
        ):
            try:
                value = dataclasses.asdict(
                    value
                )
            except Exception:
                return self._sanitize_string(
                    str(
                        value
                    )
                )

        if isinstance(
            value,
            Mapping,
        ):
            output: dict[
                str,
                Any,
            ] = {}

            for index, (
                raw_key,
                raw_value,
            ) in enumerate(
                value.items()
            ):
                if index >= self.MAX_COLLECTION_ITEMS:
                    output[
                        "_truncated"
                    ] = True
                    break

                normalized_key = str(
                    raw_key
                )

                output[
                    normalized_key
                ] = self._safe_value(
                    raw_value,
                    key=normalized_key,
                    depth=depth + 1,
                )

            return output

        if isinstance(
            value,
            (
                bytes,
                bytearray,
                memoryview,
            ),
        ):
            return (
                f"[BINARY:{len(value)} bytes]"
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
            output_list: list[
                Any
            ] = []

            for index, item in enumerate(
                value
            ):
                if index >= self.MAX_COLLECTION_ITEMS:
                    output_list.append(
                        "[TRUNCATED]"
                    )
                    break

                output_list.append(
                    self._safe_value(
                        item,
                        key=None,
                        depth=depth + 1,
                    )
                )

            return output_list

        if isinstance(
            value,
            (
                set,
                frozenset,
            ),
        ):
            output_set: list[
                Any
            ] = []

            for index, item in enumerate(
                value
            ):
                if index >= self.MAX_COLLECTION_ITEMS:
                    output_set.append(
                        "[TRUNCATED]"
                    )
                    break

                output_set.append(
                    self._safe_value(
                        item,
                        key=None,
                        depth=depth + 1,
                    )
                )

            return output_set

        if hasattr(
            value,
            "model_dump",
        ):
            try:
                dumped = value.model_dump()

                return self._safe_value(
                    dumped,
                    key=key,
                    depth=depth + 1,
                )

            except Exception:
                pass

        if hasattr(
            value,
            "dict",
        ):
            try:
                dumped = value.dict()

                return self._safe_value(
                    dumped,
                    key=key,
                    depth=depth + 1,
                )

            except Exception:
                pass

        return self._sanitize_string(
            str(
                value
            )
        )

    # =====================================================================
    # SECRET REDACTION
    # =====================================================================

    @classmethod
    def _is_sensitive_key(
        cls,
        key: str,
    ) -> bool:
        normalized = (
            str(
                key
            )
            .strip()
            .lower()
            .replace(
                "-",
                "_",
            )
            .replace(
                " ",
                "_",
            )
        )

        if normalized in cls._SENSITIVE_EXACT_KEYS:
            return True

        return any(
            fragment in normalized
            for fragment in cls._SENSITIVE_KEY_FRAGMENTS
        )

    def _sanitize_string(
        self,
        value: str,
    ) -> str:
        sanitized = str(
            value
        )

        sanitized = self._BEARER_PATTERN.sub(
            "Bearer [REDACTED]",
            sanitized,
        )

        sanitized = self._BASIC_PATTERN.sub(
            "Basic [REDACTED]",
            sanitized,
        )

        sanitized = self._SECRET_ASSIGNMENT_PATTERN.sub(
            lambda match: (
                f"{match.group(1)}={self.REDACTED}"
            ),
            sanitized,
        )

        if len(
            sanitized
        ) > self.MAX_STRING_LENGTH:
            sanitized = (
                sanitized[
                    :self.MAX_STRING_LENGTH
                ]
                + "[TRUNCATED]"
            )

        return sanitized

    # =====================================================================
    # SERIALIZATION
    # =====================================================================

    def _serialize(
        self,
        detail: Mapping[str, Any],
    ) -> str:
        try:
            return json.dumps(
                detail,
                default=self._json_default,
                separators=(
                    ",",
                    ":",
                ),
                ensure_ascii=False,
                allow_nan=False,
            )

        except Exception as exc:
            logger.exception(
                "Failed to serialize audit detail"
            )

            fallback = {
                "serialization_error": True,
                "error_type": (
                    exc.__class__.__name__
                ),
            }

            try:
                return json.dumps(
                    fallback,
                    separators=(
                        ",",
                        ":",
                    ),
                    ensure_ascii=False,
                    allow_nan=False,
                )

            except Exception:
                return (
                    '{"serialization_error":true}'
                )

    def _json_default(
        self,
        value: Any,
    ) -> Any:
        return self._safe_value(
            value,
            key=None,
            depth=0,
        )

    # =====================================================================
    # DESERIALIZATION
    # =====================================================================

    @staticmethod
    def _deserialize(
        payload: Any,
    ) -> Any:
        if payload is None:
            return {}

        if isinstance(
            payload,
            (
                dict,
                list,
            ),
        ):
            return payload

        if not isinstance(
            payload,
            str,
        ):
            return payload

        try:
            return json.loads(
                payload
            )

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return {
                "raw": payload,
            }

    # =====================================================================
    # EVENT VIEW
    # =====================================================================

    def _event_view(
        self,
        event: AuditEvent,
    ) -> dict[str, Any]:
        created_at = getattr(
            event,
            "created_at",
            None,
        )

        updated_at = getattr(
            event,
            "updated_at",
            None,
        )

        return {
            "id": getattr(
                event,
                "id",
                None,
            ),
            "event_type": getattr(
                event,
                "event_type",
                None,
            ),
            "entity_id": getattr(
                event,
                "entity_id",
                None,
            ),
            "detail": self._deserialize(
                getattr(
                    event,
                    "detail",
                    None,
                )
            ),
            "created_at": (
                created_at.isoformat()
                if created_at is not None
                and hasattr(
                    created_at,
                    "isoformat",
                )
                else (
                    str(
                        created_at
                    )
                    if created_at is not None
                    else None
                )
            ),
            "updated_at": (
                updated_at.isoformat()
                if updated_at is not None
                and hasattr(
                    updated_at,
                    "isoformat",
                )
                else (
                    str(
                        updated_at
                    )
                    if updated_at is not None
                    else None
                )
            ),
        }


audit = AuditService()
audit_service = audit


__all__ = [
    "AuditService",
    "audit",
    "audit_service",
]