from __future__ import annotations

import asyncio
import inspect
import logging
import math
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence

from ..services.automation import automation_engine
from ..services.market_scanner import market_scanner
from ..services.universe import universe_service


logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

RUNTIME_STOPPED = "STOPPED"
RUNTIME_STARTING = "STARTING"
RUNTIME_RUNNING = "RUNNING"
RUNTIME_DRAINING = "DRAINING"
RUNTIME_BLOCKED = "BLOCKED"
RUNTIME_ERROR = "ERROR"

CANDIDATE_DISCOVERED = "DISCOVERED"
CANDIDATE_ANALYZING = "ANALYZING"
CANDIDATE_HOLD = "HOLD"
CANDIDATE_ACTIONABLE = "ACTIONABLE"
CANDIDATE_BLOCKED = "BLOCKED"
CANDIDATE_EXECUTING = "EXECUTING"
CANDIDATE_EXECUTED = "EXECUTED"
CANDIDATE_FAILED = "FAILED"
CANDIDATE_SKIPPED = "SKIPPED"

POSITION_OPEN = "OPEN"
POSITION_MONITORING = "MONITORING"
POSITION_EXIT_PENDING = "EXIT_PENDING"
POSITION_CLOSED = "CLOSED"
POSITION_ERROR = "ERROR"

ACTION_BUY = "BUY"
ACTION_SELL = "SELL"
ACTION_HOLD = "HOLD"

DEFAULT_SCAN_INTERVAL_SECONDS = 60.0
DEFAULT_MONITOR_INTERVAL_SECONDS = 5.0
DEFAULT_HEALTH_INTERVAL_SECONDS = 15.0
DEFAULT_UNIVERSE_REFRESH_SECONDS = 300.0
DEFAULT_CANDIDATE_LIMIT = 12
DEFAULT_MAX_CONCURRENT_ANALYSIS = 4
DEFAULT_MAX_CONCURRENT_EXECUTIONS = 1
DEFAULT_MAX_CONSECUTIVE_FAILURES = 8
DEFAULT_FAILURE_BACKOFF_SECONDS = 5.0
DEFAULT_MAX_FAILURE_BACKOFF_SECONDS = 120.0
DEFAULT_DECISION_HISTORY = 250
DEFAULT_EVENT_HISTORY = 500
DEFAULT_POSITION_HISTORY = 250
DEFAULT_CANDIDATE_HISTORY = 250
DEFAULT_HOLD_RECHECK_SECONDS = 15.0
DEFAULT_STALE_CANDIDATE_SECONDS = 300.0
DEFAULT_DRAIN_TIMEOUT_SECONDS = 30.0


# =============================================================================
# GENERAL HELPERS
# =============================================================================


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def utc_now() -> str:
    return utc_now_dt().isoformat()


def monotonic_now() -> float:
    return time.monotonic()


def normalize_asset_class(value: str | None) -> str:
    key = (value or "").strip().lower()

    aliases = {
        "stock": "stocks",
        "stocks": "stocks",
        "equity": "stocks",
        "equities": "stocks",
        "option": "options",
        "options": "options",
        "crypto": "crypto",
        "cryptocurrency": "crypto",
        "cryptocurrencies": "crypto",
        "etf": "etfs",
        "etfs": "etfs",
        "forex": "forex",
        "fx": "forex",
        "bond": "bonds",
        "bonds": "bonds",
        "fixed_income": "bonds",
        "fixed-income": "bonds",
    }

    return aliases.get(key, key)


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default

    try:
        result = float(value)
    except (TypeError, ValueError):
        return default

    if not math.isfinite(result):
        return default

    return result


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value).strip().lower()

    if text in {"true", "1", "yes", "y", "on", "enabled"}:
        return True

    if text in {"false", "0", "no", "n", "off", "disabled"}:
        return False

    return default


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def compact_error(exc: BaseException) -> str:
    name = exc.__class__.__name__
    message = str(exc).strip()

    if message:
        return f"{name}: {message}"

    return name


def first_present(
    source: Mapping[str, Any] | None,
    keys: Sequence[str],
    default: Any = None,
) -> Any:
    if not source:
        return default

    for key in keys:
        if key in source and source[key] is not None:
            return source[key]

    return default


def ensure_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return dict(value)

    if isinstance(value, Mapping):
        return dict(value.items())

    if hasattr(value, "model_dump"):
        try:
            result = value.model_dump()
            if isinstance(result, dict):
                return result
        except Exception:
            pass

    if hasattr(value, "dict"):
        try:
            result = value.dict()
            if isinstance(result, dict):
                return result
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

    return {"value": value}


def serialize_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Mapping):
        return {
            str(key): serialize_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set, deque)):
        return [serialize_value(item) for item in value]

    if hasattr(value, "model_dump"):
        try:
            return serialize_value(value.model_dump())
        except Exception:
            pass

    if hasattr(value, "dict"):
        try:
            return serialize_value(value.dict())
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return serialize_value(
                {
                    key: item
                    for key, item in vars(value).items()
                    if not key.startswith("_")
                }
            )
        except Exception:
            pass

    return str(value)


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value

    return value


async def call_maybe_async(
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)

    return await asyncio.to_thread(func, *args, **kwargs)


def method_accepts_keyword(
    func: Callable[..., Any],
    keyword: str,
) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False

    if keyword in signature.parameters:
        return True

    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


async def invoke_flexible(
    target: Any,
    method_names: Sequence[str],
    *,
    positional_variants: Sequence[tuple[Any, ...]] | None = None,
    keyword_variants: Sequence[dict[str, Any]] | None = None,
    required: bool = False,
) -> tuple[bool, Any, str | None]:
    positional_variants = positional_variants or [()]
    keyword_variants = keyword_variants or [{}]

    found_method = False
    last_type_error: str | None = None

    for method_name in method_names:
        method = getattr(target, method_name, None)

        if not callable(method):
            continue

        found_method = True

        for args in positional_variants:
            for kwargs in keyword_variants:
                try:
                    result = await call_maybe_async(
                        method,
                        *args,
                        **kwargs,
                    )

                    return True, result, method_name

                except TypeError as exc:
                    last_type_error = str(exc)
                    continue

    if required:
        if found_method and last_type_error:
            raise RuntimeError(
                f"Compatible method call not found for "
                f"{target.__class__.__name__}: {last_type_error}"
            )

        raise RuntimeError(
            f"Required method not available on "
            f"{target.__class__.__name__}: "
            f"{', '.join(method_names)}"
        )

    return False, None, None


# =============================================================================
# RUNTIME MODELS
# =============================================================================


@dataclass
class RuntimeEvent:
    event_id: str
    timestamp: str
    asset_class: str
    event_type: str
    severity: str = "INFO"
    symbol: str | None = None
    message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(asdict(self))


@dataclass
class CandidateRuntime:
    symbol: str
    asset_class: str
    state: str = CANDIDATE_DISCOVERED
    discovered_at: str = field(default_factory=utc_now)
    last_seen_at: str = field(default_factory=utc_now)
    last_analyzed_at: str | None = None
    next_analysis_at_monotonic: float = 0.0
    rank: int | None = None
    scanner_score: float | None = None
    decision: str = ACTION_HOLD
    confidence: float | None = None
    strategy: str | None = None
    pattern: str | None = None
    regime: str | None = None
    attempts: int = 0
    holds: int = 0
    executions: int = 0
    failures: int = 0
    last_error: str | None = None
    scanner_payload: dict[str, Any] = field(default_factory=dict)
    analysis_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(asdict(self))


@dataclass
class PositionRuntime:
    position_key: str
    symbol: str
    asset_class: str
    state: str = POSITION_OPEN
    opened_at: str | None = None
    last_seen_at: str = field(default_factory=utc_now)
    last_monitored_at: str | None = None
    quantity: float | None = None
    side: str | None = None
    entry_price: float | None = None
    current_price: float | None = None
    unrealized_pl: float | None = None
    unrealized_pl_pct: float | None = None
    strategy: str | None = None
    decision: str | None = None
    risk_state: str | None = None
    stop_price: float | None = None
    target_price: float | None = None
    monitor_cycles: int = 0
    failures: int = 0
    last_error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(asdict(self))


@dataclass
class DecisionRuntime:
    decision_id: str
    timestamp: str
    symbol: str
    asset_class: str
    action: str
    confidence: float | None = None
    strategy: str | None = None
    pattern: str | None = None
    regime: str | None = None
    automatic_execution_safe: bool | None = None
    executed: bool = False
    blocked: bool = False
    block_reason: str | None = None
    execution_result: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(asdict(self))


@dataclass
class RuntimeMetrics:
    scan_cycles: int = 0
    scan_failures: int = 0
    universe_refreshes: int = 0
    universe_failures: int = 0
    candidates_discovered: int = 0
    candidates_analyzed: int = 0
    candidate_failures: int = 0
    buy_decisions: int = 0
    sell_decisions: int = 0
    hold_decisions: int = 0
    execution_attempts: int = 0
    execution_successes: int = 0
    execution_failures: int = 0
    execution_blocks: int = 0
    position_monitor_cycles: int = 0
    position_monitor_failures: int = 0
    positions_seen: int = 0
    loop_failures: int = 0
    consecutive_failures: int = 0
    last_scan_duration_ms: float | None = None
    last_analysis_duration_ms: float | None = None
    last_execution_duration_ms: float | None = None
    last_monitor_duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(asdict(self))


@dataclass
class AssetRuntimeState:
    asset_class: str
    state: str = RUNTIME_STOPPED
    enabled: bool = False
    accepting_new_entries: bool = False
    started_at: str | None = None
    stopped_at: str | None = None
    draining_since: str | None = None
    last_scan_at: str | None = None
    last_analysis_at: str | None = None
    last_monitor_at: str | None = None
    last_health_at: str | None = None
    last_error: str | None = None
    blocked_reason: str | None = None
    runtime_id: str | None = None
    universe_size: int = 0
    candidate_count: int = 0
    active_position_count: int = 0
    current_cycle: int = 0

    def to_dict(self) -> dict[str, Any]:
        return serialize_value(asdict(self))


# =============================================================================
# BASE ASSET AUTOMATION
# =============================================================================


class BaseAssetAutomation:
    """
    Shared production runtime for PhoenixTrend asset automations.

    Responsibilities:
    - Capability gating.
    - Universe refresh.
    - Market scanning.
    - Candidate lifecycle.
    - Candidate ranking integration.
    - Decision Engine integration.
    - BUY / SELL / HOLD handling.
    - Automatic execution handoff.
    - Open-position monitoring.
    - Safe section draining.
    - Error isolation.
    - Retry/backoff.
    - Runtime telemetry.
    - Activity/audit publishing where the mature services expose hooks.

    Asset-specific runtimes override the narrow hooks rather than duplicating
    the complete orchestration.
    """

    asset_class = "stocks"

    scan_interval_seconds = DEFAULT_SCAN_INTERVAL_SECONDS
    monitor_interval_seconds = DEFAULT_MONITOR_INTERVAL_SECONDS
    health_interval_seconds = DEFAULT_HEALTH_INTERVAL_SECONDS
    universe_refresh_seconds = DEFAULT_UNIVERSE_REFRESH_SECONDS
    hold_recheck_seconds = DEFAULT_HOLD_RECHECK_SECONDS
    stale_candidate_seconds = DEFAULT_STALE_CANDIDATE_SECONDS
    drain_timeout_seconds = DEFAULT_DRAIN_TIMEOUT_SECONDS

    candidate_limit = DEFAULT_CANDIDATE_LIMIT
    max_concurrent_analysis = DEFAULT_MAX_CONCURRENT_ANALYSIS
    max_concurrent_executions = DEFAULT_MAX_CONCURRENT_EXECUTIONS

    max_consecutive_failures = DEFAULT_MAX_CONSECUTIVE_FAILURES
    failure_backoff_seconds = DEFAULT_FAILURE_BACKOFF_SECONDS
    max_failure_backoff_seconds = DEFAULT_MAX_FAILURE_BACKOFF_SECONDS

    allow_automatic_entries = True
    preserve_position_monitoring_when_disabled = True

    def __init__(self) -> None:
        self.asset_class = normalize_asset_class(self.asset_class)

        self.state = AssetRuntimeState(
            asset_class=self.asset_class,
        )

        self.metrics = RuntimeMetrics()

        self._lifecycle_lock = asyncio.Lock()
        self._candidate_lock = asyncio.Lock()
        self._position_lock = asyncio.Lock()

        self._analysis_semaphore = asyncio.Semaphore(
            max(1, int(self.max_concurrent_analysis))
        )

        self._execution_semaphore = asyncio.Semaphore(
            max(1, int(self.max_concurrent_executions))
        )

        self._stop_requested = asyncio.Event()
        self._entry_gate = asyncio.Event()

        self._main_task: asyncio.Task[Any] | None = None
        self._monitor_task: asyncio.Task[Any] | None = None
        self._health_task: asyncio.Task[Any] | None = None

        self._candidate_tasks: set[asyncio.Task[Any]] = set()

        self._universe: list[str] = []
        self._universe_snapshot: Any = None
        self._last_universe_refresh_monotonic = 0.0

        self._candidates: dict[str, CandidateRuntime] = {}
        self._positions: dict[str, PositionRuntime] = {}

        self._decision_history: deque[DecisionRuntime] = deque(
            maxlen=DEFAULT_DECISION_HISTORY
        )

        self._event_history: deque[RuntimeEvent] = deque(
            maxlen=DEFAULT_EVENT_HISTORY
        )

        self._candidate_history: deque[dict[str, Any]] = deque(
            maxlen=DEFAULT_CANDIDATE_HISTORY
        )

        self._position_history: deque[dict[str, Any]] = deque(
            maxlen=DEFAULT_POSITION_HISTORY
        )

        self._last_cycle_started_monotonic = 0.0
        self._last_cycle_finished_monotonic = 0.0

        self._last_monitor_started_monotonic = 0.0
        self._last_monitor_finished_monotonic = 0.0

        self._shutdown_complete = asyncio.Event()
        self._shutdown_complete.set()

    # =========================================================================
    # SERVICE RESOLUTION
    # =========================================================================

    @staticmethod
    def _resolve_service(
        module_name: str,
        attribute_names: Sequence[str],
    ) -> Any | None:
        # The production container starts Uvicorn as ``app.main:app`` with
        # /app on PYTHONPATH.  Older automation modules referenced services as
        # ``backend.app.*`` which does not exist in that runtime and silently
        # resolved every dependency to None.  Support both layouts so the same
        # package works in Docker and when imported from the repository root.
        module_candidates = [module_name]

        if module_name.startswith("backend."):
            module_candidates.append(module_name[len("backend."):])
        elif module_name.startswith("app."):
            module_candidates.append(f"backend.{module_name}")

        for candidate in module_candidates:
            try:
                module = __import__(
                    candidate,
                    fromlist=list(attribute_names),
                )
            except Exception:
                continue

            for attribute_name in attribute_names:
                service = getattr(
                    module,
                    attribute_name,
                    None,
                )

                if service is not None:
                    return service

        return None

    def _decision_service(self) -> Any | None:
        return self._resolve_service(
            "backend.app.services.decision_engine",
            (
                "decision_engine",
                "decision_engine_service",
                "engine",
            ),
        )

    def _automatic_service(self) -> Any | None:
        return self._resolve_service(
            "backend.app.engines.automatic_engine",
            (
                "automatic_engine",
                "automatic_trading_engine",
                "engine",
            ),
        )

    def _position_service(self) -> Any | None:
        return self._resolve_service(
            "backend.app.services.positions",
            (
                "position_service",
                "positions_service",
                "positions",
            ),
        )

    def _position_monitor_service(self) -> Any | None:
        return self._resolve_service(
            "backend.app.services.position_monitor",
            (
                "position_monitor",
                "position_monitor_service",
            ),
        )

    def _candidate_ranker_service(self) -> Any | None:
        return self._resolve_service(
            "backend.app.services.candidate_ranker",
            (
                "candidate_ranker",
                "candidate_ranker_service",
            ),
        )

    def _audit_service(self) -> Any | None:
        return self._resolve_service(
            "backend.app.services.audit",
            (
                "audit_service",
                "audit",
            ),
        )

    def _performance_service(self) -> Any | None:
        return self._resolve_service(
            "backend.app.services.performance",
            (
                "performance_service",
                "performance",
            ),
        )

    # =========================================================================
    # BASIC STATE
    # =========================================================================

    def is_running(self) -> bool:
        return bool(
            self._main_task
            and not self._main_task.done()
            and self.state.state
            in {
                RUNTIME_STARTING,
                RUNTIME_RUNNING,
                RUNTIME_DRAINING,
            }
        )

    def is_draining(self) -> bool:
        return self.state.state == RUNTIME_DRAINING

    def accepts_new_entries(self) -> bool:
        return bool(
            self.state.state == RUNTIME_RUNNING
            and self.state.accepting_new_entries
            and self._entry_gate.is_set()
            and not self._stop_requested.is_set()
        )

    def section_enabled(self) -> bool:
        try:
            return bool(
                automation_engine.section_enabled(
                    self.asset_class
                )
            )
        except Exception:
            return self.state.enabled

    def universe(self) -> list[str]:
        if self._universe:
            return list(self._universe)

        try:
            values = universe_service.symbols(
                self.asset_class
            )
        except Exception:
            return []

        return self._normalize_universe(values)

    def candidates(self) -> list[dict[str, Any]]:
        return [
            candidate.to_dict()
            for candidate in self._candidates.values()
        ]

    def positions(self) -> list[dict[str, Any]]:
        return [
            position.to_dict()
            for position in self._positions.values()
        ]

    def decisions(self) -> list[dict[str, Any]]:
        return [
            decision.to_dict()
            for decision in self._decision_history
        ]

    def events(self) -> list[dict[str, Any]]:
        return [
            event.to_dict()
            for event in self._event_history
        ]

    # =========================================================================
    # LIFECYCLE
    # =========================================================================

    async def start(self) -> dict[str, Any]:
        async with self._lifecycle_lock:
            if self.is_running():
                return self.status()

            self.state.state = RUNTIME_STARTING
            self.state.last_error = None
            self.state.blocked_reason = None
            self.state.stopped_at = None
            self.state.draining_since = None
            self.state.runtime_id = uuid.uuid4().hex
            self.state.enabled = True
            self.state.accepting_new_entries = False

            self._shutdown_complete.clear()
            self._stop_requested = asyncio.Event()
            self._entry_gate = asyncio.Event()

            capability = await self.capability_snapshot()

            if not capability["supported"]:
                reason = (
                    capability.get("reason")
                    or f"{self.asset_class} automation is unsupported"
                )

                self.state.state = RUNTIME_BLOCKED
                self.state.blocked_reason = reason
                self.state.last_error = reason
                self.state.enabled = False
                self.state.accepting_new_entries = False
                self._shutdown_complete.set()

                await self._emit_event(
                    "AUTOMATION_BLOCKED",
                    severity="WARNING",
                    message=reason,
                    data=capability,
                )

                return self.status()

            try:
                await self.refresh_universe(
                    force=True
                )
            except Exception as exc:
                self.metrics.universe_failures += 1

                message = compact_error(exc)

                self.state.state = RUNTIME_ERROR
                self.state.last_error = message
                self.state.enabled = False
                self.state.accepting_new_entries = False
                self._shutdown_complete.set()

                await self._emit_event(
                    "UNIVERSE_INITIALIZATION_FAILED",
                    severity="ERROR",
                    message=message,
                )

                return self.status()

            if not self._universe:
                reason = (
                    f"No tradable {self.asset_class} instruments "
                    f"are currently available"
                )

                self.state.state = RUNTIME_BLOCKED
                self.state.blocked_reason = reason
                self.state.last_error = reason
                self.state.enabled = False
                self.state.accepting_new_entries = False
                self._shutdown_complete.set()

                await self._emit_event(
                    "AUTOMATION_BLOCKED",
                    severity="WARNING",
                    message=reason,
                )

                return self.status()

            self.state.state = RUNTIME_RUNNING
            self.state.started_at = utc_now()
            self.state.enabled = True
            self.state.accepting_new_entries = True

            self._entry_gate.set()

            self._main_task = asyncio.create_task(
                self._run_loop(),
                name=(
                    f"phoenixtrend-"
                    f"{self.asset_class}-automation-main"
                ),
            )

            self._monitor_task = asyncio.create_task(
                self._position_monitor_loop(),
                name=(
                    f"phoenixtrend-"
                    f"{self.asset_class}-position-monitor"
                ),
            )

            self._health_task = asyncio.create_task(
                self._health_loop(),
                name=(
                    f"phoenixtrend-"
                    f"{self.asset_class}-health"
                ),
            )

            await self._emit_event(
                "AUTOMATION_STARTED",
                message=(
                    f"{self.asset_class} automation started"
                ),
                data={
                    "runtime_id": self.state.runtime_id,
                    "universe_size": len(self._universe),
                },
            )

            return self.status()

    async def stop(
        self,
        *,
        drain: bool = True,
        reason: str | None = None,
    ) -> dict[str, Any]:
        async with self._lifecycle_lock:
            if (
                self.state.state == RUNTIME_STOPPED
                and not self.is_running()
            ):
                return self.status()

            self.state.enabled = False
            self.state.accepting_new_entries = False

            self._entry_gate.clear()

            if drain:
                self.state.state = RUNTIME_DRAINING
                self.state.draining_since = utc_now()

                await self._emit_event(
                    "AUTOMATION_DRAINING",
                    message=(
                        reason
                        or (
                            f"{self.asset_class} automation "
                            f"is stopping new entries"
                        )
                    ),
                )

                await self._cancel_candidate_tasks()

                await self._stop_discovery_task()

                if self.preserve_position_monitoring_when_disabled:
                    await self._drain_open_positions(
                        timeout=self.drain_timeout_seconds
                    )

            self._stop_requested.set()

            await self._cancel_candidate_tasks()

            await self._cancel_task(
                self._main_task
            )

            await self._cancel_task(
                self._health_task
            )

            if not self._positions:
                await self._cancel_task(
                    self._monitor_task
                )

            elif not self.preserve_position_monitoring_when_disabled:
                await self._cancel_task(
                    self._monitor_task
                )

            else:
                await self._cancel_task(
                    self._monitor_task
                )

            self._main_task = None
            self._monitor_task = None
            self._health_task = None

            self.state.state = RUNTIME_STOPPED
            self.state.stopped_at = utc_now()
            self.state.draining_since = None
            self.state.accepting_new_entries = False

            self._shutdown_complete.set()

            await self._emit_event(
                "AUTOMATION_STOPPED",
                message=(
                    reason
                    or (
                        f"{self.asset_class} automation stopped"
                    )
                ),
            )

            return self.status()

    async def emergency_stop(
        self,
        reason: str = "Emergency stop requested",
    ) -> dict[str, Any]:
        self.state.accepting_new_entries = False
        self._entry_gate.clear()
        self._stop_requested.set()

        await self._emit_event(
            "AUTOMATION_EMERGENCY_STOP",
            severity="CRITICAL",
            message=reason,
        )

        async with self._lifecycle_lock:
            await self._cancel_candidate_tasks()

            await self._cancel_task(
                self._main_task
            )

            await self._cancel_task(
                self._monitor_task
            )

            await self._cancel_task(
                self._health_task
            )

            self._main_task = None
            self._monitor_task = None
            self._health_task = None

            self.state.state = RUNTIME_STOPPED
            self.state.enabled = False
            self.state.accepting_new_entries = False
            self.state.stopped_at = utc_now()
            self.state.last_error = reason

            self._shutdown_complete.set()

            return self.status()

    async def restart(self) -> dict[str, Any]:
        await self.stop(
            drain=True,
            reason="Automation restart requested",
        )

        return await self.start()

    async def wait_until_stopped(
        self,
        timeout: float | None = None,
    ) -> bool:
        try:
            if timeout is None:
                await self._shutdown_complete.wait()
            else:
                await asyncio.wait_for(
                    self._shutdown_complete.wait(),
                    timeout=timeout,
                )

            return True

        except asyncio.TimeoutError:
            return False

    # =========================================================================
    # CAPABILITIES
    # =========================================================================

    async def capability_snapshot(
        self,
    ) -> dict[str, Any]:
        try:
            snapshot = await asyncio.to_thread(
                universe_service.snapshot,
                self.asset_class,
            )
        except Exception as exc:
            return {
                "asset_class": self.asset_class,
                "supported": False,
                "reason": compact_error(exc),
            }

        payload = ensure_mapping(snapshot)

        supported = safe_bool(
            payload.get(
                "supported",
                getattr(
                    snapshot,
                    "supported",
                    False,
                ),
            ),
            default=False,
        )

        reason = payload.get(
            "reason",
            getattr(
                snapshot,
                "reason",
                None,
            ),
        )

        return {
            **serialize_value(payload),
            "asset_class": self.asset_class,
            "supported": supported,
            "reason": reason,
        }

    async def readiness_snapshot(
        self,
    ) -> dict[str, Any]:
        capability = await self.capability_snapshot()

        return {
            "asset_class": self.asset_class,
            "supported": capability["supported"],
            "reason": capability.get("reason"),
            "universe_size": len(self._universe),
            "runtime_state": self.state.state,
            "accepting_new_entries": (
                self.accepts_new_entries()
            ),
            "section_enabled": self.section_enabled(),
        }

    # =========================================================================
    # UNIVERSE
    # =========================================================================

    def _normalize_universe(
        self,
        values: Any,
    ) -> list[str]:
        if values is None:
            return []

        if isinstance(values, str):
            values = [values]

        normalized: list[str] = []
        seen: set[str] = set()

        for item in values:
            if isinstance(item, Mapping):
                symbol = normalize_symbol(
                    first_present(
                        item,
                        (
                            "symbol",
                            "ticker",
                            "code",
                            "asset",
                        ),
                    )
                )
            else:
                symbol = normalize_symbol(item)

            if not symbol:
                continue

            if symbol in seen:
                continue

            seen.add(symbol)
            normalized.append(symbol)

        return normalized

    async def refresh_universe(
        self,
        *,
        force: bool = False,
    ) -> list[str]:
        now = monotonic_now()

        if (
            not force
            and self._universe
            and (
                now
                - self._last_universe_refresh_monotonic
            )
            < self.universe_refresh_seconds
        ):
            return list(self._universe)

        try:
            snapshot = await asyncio.to_thread(
                universe_service.snapshot,
                self.asset_class,
            )

            payload = ensure_mapping(snapshot)

            supported = safe_bool(
                payload.get(
                    "supported",
                    getattr(
                        snapshot,
                        "supported",
                        False,
                    ),
                ),
                default=False,
            )

            if not supported:
                reason = (
                    payload.get("reason")
                    or getattr(
                        snapshot,
                        "reason",
                        None,
                    )
                    or (
                        f"{self.asset_class} universe "
                        f"is unsupported"
                    )
                )

                raise RuntimeError(reason)

            symbols = await asyncio.to_thread(
                universe_service.symbols,
                self.asset_class,
            )

            normalized = self._normalize_universe(
                symbols
            )

            normalized = await self.filter_universe(
                normalized
            )

            self._universe_snapshot = snapshot
            self._universe = normalized
            self._last_universe_refresh_monotonic = now

            self.state.universe_size = len(
                self._universe
            )

            self.metrics.universe_refreshes += 1

            await self._emit_event(
                "UNIVERSE_REFRESHED",
                message=(
                    f"{self.asset_class} universe refreshed"
                ),
                data={
                    "size": len(self._universe),
                },
            )

            return list(self._universe)

        except Exception:
            self.metrics.universe_failures += 1
            raise

    async def filter_universe(
        self,
        symbols: list[str],
    ) -> list[str]:
        return symbols

    # =========================================================================
    # SCANNING
    # =========================================================================

    async def scan_market(
        self,
    ) -> dict[str, Any]:
        symbols = await self.refresh_universe()

        if not symbols:
            return {
                "asset_class": self.asset_class,
                "candidates": [],
                "count": 0,
            }

        started = monotonic_now()

        try:
            result = await asyncio.to_thread(
                market_scanner.scan,
                self.asset_class,
                symbols=symbols,
                limit=self.candidate_limit,
            )

            payload = ensure_mapping(result)

            candidates = payload.get(
                "candidates",
                [],
            )

            if not isinstance(candidates, list):
                candidates = list(
                    candidates or []
                )

            candidates = await self.rank_candidates(
                candidates
            )

            payload["candidates"] = candidates[
                : self.candidate_limit
            ]

            payload["count"] = len(
                payload["candidates"]
            )

            payload["asset_class"] = self.asset_class

            self.metrics.scan_cycles += 1
            self.metrics.consecutive_failures = 0

            self.state.current_cycle += 1
            self.state.last_scan_at = utc_now()

            duration = (
                monotonic_now() - started
            ) * 1000.0

            self.metrics.last_scan_duration_ms = (
                duration
            )

            await self._ingest_candidates(
                payload["candidates"]
            )

            return payload

        except Exception:
            self.metrics.scan_failures += 1
            self.metrics.consecutive_failures += 1
            raise

    async def rank_candidates(
        self,
        candidates: list[Any],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []

        for index, item in enumerate(candidates):
            payload = ensure_mapping(item)

            symbol = normalize_symbol(
                first_present(
                    payload,
                    (
                        "symbol",
                        "ticker",
                        "code",
                    ),
                )
            )

            if not symbol:
                continue

            payload["symbol"] = symbol
            payload.setdefault(
                "asset_class",
                self.asset_class,
            )

            score = safe_float(
                first_present(
                    payload,
                    (
                        "score",
                        "rank_score",
                        "scanner_score",
                        "candidate_score",
                    ),
                )
            )

            if score is not None:
                payload["scanner_score"] = score

            payload.setdefault(
                "source_rank",
                index + 1,
            )

            normalized.append(payload)

        ranker = self._candidate_ranker_service()

        if ranker is not None and normalized:
            try:
                found, result, _ = await invoke_flexible(
                    ranker,
                    (
                        "rank",
                        "rank_candidates",
                        "score_candidates",
                    ),
                    positional_variants=[
                        (
                            self.asset_class,
                            normalized,
                        ),
                        (normalized,),
                    ],
                    keyword_variants=[
                        {},
                        {
                            "asset_class": (
                                self.asset_class
                            )
                        },
                    ],
                    required=False,
                )

                if found and result is not None:
                    ranked_payload = result

                    if isinstance(
                        ranked_payload,
                        Mapping,
                    ):
                        ranked_payload = (
                            ranked_payload.get(
                                "candidates",
                                ranked_payload.get(
                                    "ranked",
                                    [],
                                ),
                            )
                        )

                    if isinstance(
                        ranked_payload,
                        Iterable,
                    ) and not isinstance(
                        ranked_payload,
                        (str, bytes, Mapping),
                    ):
                        normalized = [
                            ensure_mapping(item)
                            for item in ranked_payload
                        ]

            except Exception as exc:
                await self._emit_event(
                    "CANDIDATE_RANKER_FAILED",
                    severity="WARNING",
                    message=compact_error(exc),
                )

        normalized.sort(
            key=lambda item: (
                safe_float(
                    first_present(
                        item,
                        (
                            "rank_score",
                            "score",
                            "scanner_score",
                            "candidate_score",
                        ),
                    ),
                    default=float("-inf"),
                )
                or float("-inf")
            ),
            reverse=True,
        )

        for rank, item in enumerate(
            normalized,
            start=1,
        ):
            item["rank"] = rank

        return normalized

    async def _ingest_candidates(
        self,
        candidates: list[dict[str, Any]],
    ) -> None:
        now_iso = utc_now()
        now_monotonic = monotonic_now()

        async with self._candidate_lock:
            for item in candidates:
                symbol = normalize_symbol(
                    item.get("symbol")
                )

                if not symbol:
                    continue

                candidate = self._candidates.get(
                    symbol
                )

                if candidate is None:
                    candidate = CandidateRuntime(
                        symbol=symbol,
                        asset_class=self.asset_class,
                    )

                    self._candidates[symbol] = (
                        candidate
                    )

                    self.metrics.candidates_discovered += 1

                    await self._emit_event(
                        "CANDIDATE_DISCOVERED",
                        symbol=symbol,
                        data=item,
                    )

                candidate.last_seen_at = now_iso
                candidate.rank = safe_int(
                    item.get("rank"),
                    default=0,
                ) or None

                candidate.scanner_score = safe_float(
                    first_present(
                        item,
                        (
                            "scanner_score",
                            "rank_score",
                            "score",
                        ),
                    )
                )

                candidate.scanner_payload = dict(
                    item
                )

                if (
                    candidate.next_analysis_at_monotonic
                    <= 0.0
                ):
                    candidate.next_analysis_at_monotonic = (
                        now_monotonic
                    )

            self.state.candidate_count = len(
                self._candidates
            )

    # =========================================================================
    # CANDIDATE ANALYSIS
    # =========================================================================

    async def analyze_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> DecisionRuntime:
        symbol = candidate.symbol

        candidate.state = CANDIDATE_ANALYZING
        candidate.attempts += 1
        candidate.last_analyzed_at = utc_now()

        started = monotonic_now()

        try:
            analysis = await self.run_decision_engine(
                symbol=symbol,
                candidate=candidate,
            )

            payload = ensure_mapping(
                analysis
            )

            action = self.extract_action(
                payload
            )

            confidence = self.extract_confidence(
                payload
            )

            strategy = self.extract_strategy(
                payload
            )

            pattern = self.extract_pattern(
                payload
            )

            regime = self.extract_regime(
                payload
            )

            automatic_execution_safe = (
                self.extract_automatic_execution_safe(
                    payload
                )
            )

            decision = DecisionRuntime(
                decision_id=uuid.uuid4().hex,
                timestamp=utc_now(),
                symbol=symbol,
                asset_class=self.asset_class,
                action=action,
                confidence=confidence,
                strategy=strategy,
                pattern=pattern,
                regime=regime,
                automatic_execution_safe=(
                    automatic_execution_safe
                ),
                analysis=serialize_value(payload),
            )

            candidate.analysis_payload = (
                serialize_value(payload)
            )

            candidate.decision = action
            candidate.confidence = confidence
            candidate.strategy = strategy
            candidate.pattern = pattern
            candidate.regime = regime
            candidate.last_error = None

            self.metrics.candidates_analyzed += 1
            self.metrics.consecutive_failures = 0

            if action == ACTION_BUY:
                self.metrics.buy_decisions += 1
                candidate.state = (
                    CANDIDATE_ACTIONABLE
                )

            elif action == ACTION_SELL:
                self.metrics.sell_decisions += 1
                candidate.state = (
                    CANDIDATE_ACTIONABLE
                )

            else:
                self.metrics.hold_decisions += 1
                candidate.state = CANDIDATE_HOLD
                candidate.holds += 1

                candidate.next_analysis_at_monotonic = (
                    monotonic_now()
                    + self.hold_recheck_seconds
                )

            self._decision_history.append(
                decision
            )

            self._candidate_history.append(
                candidate.to_dict()
            )

            self.state.last_analysis_at = utc_now()

            self.metrics.last_analysis_duration_ms = (
                (
                    monotonic_now()
                    - started
                )
                * 1000.0
            )

            await self._emit_event(
                "AUTOMATION_DECISION",
                symbol=symbol,
                message=(
                    f"{symbol}: {action}"
                ),
                data=decision.to_dict(),
            )

            return decision

        except Exception as exc:
            candidate.state = CANDIDATE_FAILED
            candidate.failures += 1
            candidate.last_error = compact_error(exc)

            candidate.next_analysis_at_monotonic = (
                monotonic_now()
                + self._failure_backoff_delay(
                    candidate.failures
                )
            )

            self.metrics.candidate_failures += 1
            self.metrics.consecutive_failures += 1

            await self._emit_event(
                "CANDIDATE_ANALYSIS_FAILED",
                severity="ERROR",
                symbol=symbol,
                message=candidate.last_error,
            )

            raise

    async def run_decision_engine(
        self,
        *,
        symbol: str,
        candidate: CandidateRuntime,
    ) -> Any:
        decision_service = self._decision_service()

        if decision_service is None:
            raise RuntimeError(
                "PhoenixTrend Decision Engine "
                "service is unavailable"
            )

        methods = (
            "analyze",
            "evaluate",
            "decide",
        )

        positional_variants = [
            (symbol,),
            (
                symbol,
                self.asset_class,
            ),
        ]

        keyword_variants = [
            {},
            {
                "force": False,
            },
            {
                "asset_class": (
                    self.asset_class
                ),
            },
            {
                "force": False,
                "asset_class": (
                    self.asset_class
                ),
            },
        ]

        found, result, _ = await invoke_flexible(
            decision_service,
            methods,
            positional_variants=(
                positional_variants
            ),
            keyword_variants=(
                keyword_variants
            ),
            required=True,
        )

        if not found:
            raise RuntimeError(
                "Decision Engine could not analyze "
                f"{symbol}"
            )

        return result

    def extract_action(
        self,
        payload: Mapping[str, Any],
    ) -> str:
        action = first_present(
            payload,
            (
                "action",
                "decision",
                "signal",
                "side",
                "recommendation",
            ),
            default=ACTION_HOLD,
        )

        if isinstance(action, Mapping):
            action = first_present(
                action,
                (
                    "action",
                    "signal",
                    "decision",
                ),
                default=ACTION_HOLD,
            )

        normalized = str(
            action or ACTION_HOLD
        ).strip().upper()

        aliases = {
            "LONG": ACTION_BUY,
            "ENTER_LONG": ACTION_BUY,
            "STRONG_BUY": ACTION_BUY,
            "SHORT": ACTION_SELL,
            "ENTER_SHORT": ACTION_SELL,
            "STRONG_SELL": ACTION_SELL,
            "NONE": ACTION_HOLD,
            "NO_TRADE": ACTION_HOLD,
            "WAIT": ACTION_HOLD,
            "NEUTRAL": ACTION_HOLD,
        }

        normalized = aliases.get(
            normalized,
            normalized,
        )

        if normalized not in {
            ACTION_BUY,
            ACTION_SELL,
            ACTION_HOLD,
        }:
            return ACTION_HOLD

        return normalized

    def extract_confidence(
        self,
        payload: Mapping[str, Any],
    ) -> float | None:
        confidence = safe_float(
            first_present(
                payload,
                (
                    "confidence",
                    "score",
                    "decision_confidence",
                    "strategy_confidence",
                ),
            )
        )

        if confidence is None:
            selected = payload.get(
                "selected_strategy"
            )

            if isinstance(selected, Mapping):
                confidence = safe_float(
                    first_present(
                        selected,
                        (
                            "confidence",
                            "score",
                        ),
                    )
                )

        return confidence

    def extract_strategy(
        self,
        payload: Mapping[str, Any],
    ) -> str | None:
        strategy = first_present(
            payload,
            (
                "strategy",
                "strategy_name",
                "selected_strategy_name",
            ),
        )

        if strategy is not None:
            return str(strategy)

        selected = payload.get(
            "selected_strategy"
        )

        if isinstance(selected, Mapping):
            value = first_present(
                selected,
                (
                    "name",
                    "strategy",
                    "strategy_name",
                ),
            )

            if value is not None:
                return str(value)

        return None

    def extract_pattern(
        self,
        payload: Mapping[str, Any],
    ) -> str | None:
        pattern = first_present(
            payload,
            (
                "pattern",
                "primary_pattern",
                "chart_pattern",
            ),
        )

        if pattern is not None:
            if isinstance(pattern, Mapping):
                pattern = first_present(
                    pattern,
                    (
                        "name",
                        "pattern",
                        "type",
                    ),
                )

            if pattern is not None:
                return str(pattern)

        patterns = payload.get("patterns")

        if isinstance(patterns, list) and patterns:
            first = patterns[0]

            if isinstance(first, Mapping):
                value = first_present(
                    first,
                    (
                        "name",
                        "pattern",
                        "type",
                    ),
                )

                if value is not None:
                    return str(value)

            return str(first)

        return None

    def extract_regime(
        self,
        payload: Mapping[str, Any],
    ) -> str | None:
        regime = first_present(
            payload,
            (
                "regime",
                "market_regime",
            ),
        )

        if isinstance(regime, Mapping):
            regime = first_present(
                regime,
                (
                    "name",
                    "regime",
                    "type",
                ),
            )

        if regime is None:
            return None

        return str(regime)

    def extract_automatic_execution_safe(
        self,
        payload: Mapping[str, Any],
    ) -> bool | None:
        value = first_present(
            payload,
            (
                "automatic_execution_safe",
                "execution_safe",
                "auto_execute_safe",
            ),
        )

        if value is None:
            context = payload.get("context")

            if isinstance(context, Mapping):
                value = first_present(
                    context,
                    (
                        "automatic_execution_safe",
                        "execution_safe",
                    ),
                )

        if value is None:
            return None

        return safe_bool(value)

    # =========================================================================
    # EXECUTION
    # =========================================================================

    async def handle_decision(
        self,
        candidate: CandidateRuntime,
        decision: DecisionRuntime,
    ) -> None:
        if decision.action == ACTION_HOLD:
            return

        if not self.allow_automatic_entries:
            decision.blocked = True
            decision.block_reason = (
                "Automatic entries are disabled "
                f"for {self.asset_class}"
            )

            candidate.state = CANDIDATE_BLOCKED

            self.metrics.execution_blocks += 1

            await self._emit_event(
                "AUTOMATION_EXECUTION_BLOCKED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=decision.block_reason,
                data=decision.to_dict(),
            )

            return

        if not self.accepts_new_entries():
            decision.blocked = True
            decision.block_reason = (
                f"{self.asset_class} automation "
                f"is not accepting new entries"
            )

            candidate.state = CANDIDATE_BLOCKED

            self.metrics.execution_blocks += 1

            await self._emit_event(
                "AUTOMATION_EXECUTION_BLOCKED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=decision.block_reason,
                data=decision.to_dict(),
            )

            return

        if decision.automatic_execution_safe is False:
            decision.blocked = True
            decision.block_reason = (
                "Decision Engine marked the "
                "market context unsafe for "
                "automatic execution"
            )

            candidate.state = CANDIDATE_BLOCKED

            self.metrics.execution_blocks += 1

            await self._emit_event(
                "AUTOMATION_EXECUTION_BLOCKED",
                severity="WARNING",
                symbol=candidate.symbol,
                message=decision.block_reason,
                data=decision.to_dict(),
            )

            return

        if await self.has_open_position(
            candidate.symbol
        ):
            decision.blocked = True
            decision.block_reason = (
                f"Open {self.asset_class} position "
                f"already exists for "
                f"{candidate.symbol}"
            )

            candidate.state = CANDIDATE_BLOCKED

            self.metrics.execution_blocks += 1

            await self._emit_event(
                "AUTOMATION_EXECUTION_BLOCKED",
                severity="INFO",
                symbol=candidate.symbol,
                message=decision.block_reason,
            )

            return

        await self.execute_decision(
            candidate=candidate,
            decision=decision,
        )

    async def execute_decision(
        self,
        *,
        candidate: CandidateRuntime,
        decision: DecisionRuntime,
    ) -> dict[str, Any]:
        automatic_service = self._automatic_service()

        if automatic_service is None:
            raise RuntimeError(
                "PhoenixTrend Automatic Engine "
                "is unavailable"
            )

        async with self._execution_semaphore:
            if not self.accepts_new_entries():
                decision.blocked = True
                decision.block_reason = (
                    "Automation stopped accepting "
                    "new entries before execution"
                )

                candidate.state = (
                    CANDIDATE_BLOCKED
                )

                self.metrics.execution_blocks += 1

                return {}

            candidate.state = (
                CANDIDATE_EXECUTING
            )

            self.metrics.execution_attempts += 1

            started = monotonic_now()

            analysis = decision.analysis

            methods = (
                "execute_decision",
                "execute_analysis",
                "process_decision",
                "process",
                "run",
                "execute",
            )

            positional_variants = [
                (
                    candidate.symbol,
                    analysis,
                ),
                (analysis,),
                (
                    candidate.symbol,
                    decision.action,
                ),
                (candidate.symbol,),
            ]

            keyword_variants = [
                {},
                {
                    "symbol": (
                        candidate.symbol
                    ),
                    "asset_class": (
                        self.asset_class
                    ),
                    "decision": analysis,
                },
                {
                    "symbol": (
                        candidate.symbol
                    ),
                    "asset_type": (
                        self.asset_class
                    ),
                    "analysis": analysis,
                },
            ]

            try:
                found, result, method_name = (
                    await invoke_flexible(
                        automatic_service,
                        methods,
                        positional_variants=(
                            positional_variants
                        ),
                        keyword_variants=(
                            keyword_variants
                        ),
                        required=True,
                    )
                )

                if not found:
                    raise RuntimeError(
                        "Automatic Engine execution "
                        "entry point was not found"
                    )

                payload = ensure_mapping(result)

                successful = self.execution_succeeded(
                    payload
                )

                blocked = self.execution_blocked(
                    payload
                )

                if blocked:
                    decision.blocked = True
                    decision.block_reason = (
                        self.execution_block_reason(
                            payload
                        )
                    )

                    candidate.state = (
                        CANDIDATE_BLOCKED
                    )

                    self.metrics.execution_blocks += 1

                elif successful:
                    decision.executed = True
                    candidate.state = (
                        CANDIDATE_EXECUTED
                    )

                    candidate.executions += 1

                    self.metrics.execution_successes += 1

                else:
                    candidate.state = (
                        CANDIDATE_FAILED
                    )

                    candidate.failures += 1

                    self.metrics.execution_failures += 1

                decision.execution_result = (
                    serialize_value(payload)
                )

                self.metrics.last_execution_duration_ms = (
                    (
                        monotonic_now()
                        - started
                    )
                    * 1000.0
                )

                await self._emit_event(
                    (
                        "AUTOMATION_EXECUTED"
                        if successful
                        else (
                            "AUTOMATION_EXECUTION_BLOCKED"
                            if blocked
                            else "AUTOMATION_EXECUTION_FAILED"
                        )
                    ),
                    severity=(
                        "INFO"
                        if successful
                        else "WARNING"
                    ),
                    symbol=candidate.symbol,
                    message=(
                        f"{candidate.symbol} "
                        f"{decision.action} "
                        f"via {method_name}"
                    ),
                    data=decision.to_dict(),
                )

                if successful:
                    await self.refresh_positions()

                return payload

            except Exception as exc:
                self.metrics.execution_failures += 1

                candidate.state = (
                    CANDIDATE_FAILED
                )

                candidate.failures += 1
                candidate.last_error = (
                    compact_error(exc)
                )

                await self._emit_event(
                    "AUTOMATION_EXECUTION_FAILED",
                    severity="ERROR",
                    symbol=candidate.symbol,
                    message=candidate.last_error,
                )

                raise

    def execution_succeeded(
        self,
        payload: Mapping[str, Any],
    ) -> bool:
        if not payload:
            return False

        explicit = first_present(
            payload,
            (
                "success",
                "executed",
                "submitted",
                "accepted",
            ),
        )

        if explicit is not None:
            return safe_bool(explicit)

        status = str(
            first_present(
                payload,
                (
                    "status",
                    "state",
                    "result",
                ),
                default="",
            )
        ).strip().upper()

        return status in {
            "SUCCESS",
            "EXECUTED",
            "SUBMITTED",
            "ACCEPTED",
            "FILLED",
            "PARTIALLY_FILLED",
            "PENDING",
            "NEW",
        }

    def execution_blocked(
        self,
        payload: Mapping[str, Any],
    ) -> bool:
        explicit = first_present(
            payload,
            (
                "blocked",
                "rejected",
            ),
        )

        if explicit is not None:
            return safe_bool(explicit)

        status = str(
            first_present(
                payload,
                (
                    "status",
                    "state",
                    "result",
                ),
                default="",
            )
        ).strip().upper()

        return status in {
            "BLOCKED",
            "REJECTED",
            "DENIED",
            "NO_TRADE",
        }

    def execution_block_reason(
        self,
        payload: Mapping[str, Any],
    ) -> str:
        reason = first_present(
            payload,
            (
                "reason",
                "message",
                "detail",
                "error",
            ),
            default="Execution blocked",
        )

        return str(reason)

    # =========================================================================
    # POSITION DISCOVERY / MONITORING
    # =========================================================================

    async def has_open_position(
        self,
        symbol: str,
    ) -> bool:
        normalized = normalize_symbol(symbol)

        for position in self._positions.values():
            if (
                position.symbol == normalized
                and position.state
                not in {
                    POSITION_CLOSED,
                }
            ):
                return True

        await self.refresh_positions()

        for position in self._positions.values():
            if (
                position.symbol == normalized
                and position.state
                not in {
                    POSITION_CLOSED,
                }
            ):
                return True

        return False

    async def fetch_open_positions(
        self,
    ) -> list[dict[str, Any]]:
        position_service = self._position_service()

        if position_service is None:
            return []

        found, result, _ = await invoke_flexible(
            position_service,
            (
                "open_positions",
                "list_open",
                "list_positions",
                "get_positions",
                "all",
            ),
            positional_variants=[
                (),
                (self.asset_class,),
            ],
            keyword_variants=[
                {},
                {
                    "asset_class": (
                        self.asset_class
                    )
                },
                {
                    "asset_type": (
                        self.asset_class
                    )
                },
            ],
            required=False,
        )

        if not found or result is None:
            return []

        if isinstance(result, Mapping):
            result = first_present(
                result,
                (
                    "positions",
                    "items",
                    "data",
                ),
                default=[],
            )

        if not isinstance(result, Iterable):
            return []

        positions: list[dict[str, Any]] = []

        for item in result:
            payload = ensure_mapping(item)

            symbol = normalize_symbol(
                first_present(
                    payload,
                    (
                        "symbol",
                        "ticker",
                    ),
                )
            )

            if not symbol:
                continue

            asset_class = normalize_asset_class(
                str(
                    first_present(
                        payload,
                        (
                            "asset_class",
                            "asset_type",
                            "type",
                        ),
                        default=self.asset_class,
                    )
                )
            )

            if (
                asset_class
                and asset_class
                != self.asset_class
            ):
                continue

            payload["symbol"] = symbol
            payload["asset_class"] = (
                self.asset_class
            )

            positions.append(payload)

        return positions

    async def refresh_positions(
        self,
    ) -> list[dict[str, Any]]:
        started = monotonic_now()

        try:
            raw_positions = (
                await self.fetch_open_positions()
            )

            seen: set[str] = set()

            async with self._position_lock:
                for payload in raw_positions:
                    position = (
                        self._position_from_payload(
                            payload
                        )
                    )

                    seen.add(
                        position.position_key
                    )

                    existing = self._positions.get(
                        position.position_key
                    )

                    if existing is None:
                        self._positions[
                            position.position_key
                        ] = position

                        self.metrics.positions_seen += 1

                        await self._emit_event(
                            "POSITION_DISCOVERED",
                            symbol=position.symbol,
                            data=position.to_dict(),
                        )

                    else:
                        self._merge_position(
                            existing,
                            position,
                        )

                stale_keys = [
                    key
                    for key in self._positions
                    if key not in seen
                ]

                for key in stale_keys:
                    closed = self._positions.pop(
                        key
                    )

                    closed.state = (
                        POSITION_CLOSED
                    )

                    closed.last_seen_at = utc_now()

                    self._position_history.append(
                        closed.to_dict()
                    )

                    await self._emit_event(
                        "POSITION_CLOSED",
                        symbol=closed.symbol,
                        data=closed.to_dict(),
                    )

                self.state.active_position_count = (
                    len(self._positions)
                )

            self.state.last_monitor_at = utc_now()

            self.metrics.position_monitor_cycles += 1

            self.metrics.last_monitor_duration_ms = (
                (
                    monotonic_now()
                    - started
                )
                * 1000.0
            )

            return self.positions()

        except Exception:
            self.metrics.position_monitor_failures += 1
            raise

    def _position_from_payload(
        self,
        payload: Mapping[str, Any],
    ) -> PositionRuntime:
        symbol = normalize_symbol(
            first_present(
                payload,
                (
                    "symbol",
                    "ticker",
                ),
            )
        )

        identifier = first_present(
            payload,
            (
                "id",
                "position_id",
                "broker_position_id",
            ),
        )

        position_key = str(
            identifier
            or (
                f"{self.asset_class}:"
                f"{symbol}"
            )
        )

        quantity = safe_float(
            first_present(
                payload,
                (
                    "qty",
                    "quantity",
                    "position_qty",
                ),
            )
        )

        side = first_present(
            payload,
            (
                "side",
                "position_side",
            ),
        )

        entry_price = safe_float(
            first_present(
                payload,
                (
                    "avg_entry_price",
                    "entry_price",
                    "average_entry_price",
                ),
            )
        )

        current_price = safe_float(
            first_present(
                payload,
                (
                    "current_price",
                    "market_price",
                    "price",
                ),
            )
        )

        unrealized_pl = safe_float(
            first_present(
                payload,
                (
                    "unrealized_pl",
                    "unrealized_pnl",
                    "pnl",
                ),
            )
        )

        unrealized_pl_pct = safe_float(
            first_present(
                payload,
                (
                    "unrealized_plpc",
                    "unrealized_pnl_pct",
                    "pnl_pct",
                ),
            )
        )

        stop_price = safe_float(
            first_present(
                payload,
                (
                    "stop_price",
                    "stop",
                    "stop_loss",
                ),
            )
        )

        target_price = safe_float(
            first_present(
                payload,
                (
                    "target_price",
                    "target",
                    "take_profit",
                ),
            )
        )

        strategy = first_present(
            payload,
            (
                "strategy",
                "strategy_name",
            ),
        )

        return PositionRuntime(
            position_key=position_key,
            symbol=symbol,
            asset_class=self.asset_class,
            state=POSITION_OPEN,
            opened_at=first_present(
                payload,
                (
                    "opened_at",
                    "created_at",
                    "timestamp",
                ),
            ),
            quantity=quantity,
            side=(
                str(side)
                if side is not None
                else None
            ),
            entry_price=entry_price,
            current_price=current_price,
            unrealized_pl=unrealized_pl,
            unrealized_pl_pct=(
                unrealized_pl_pct
            ),
            strategy=(
                str(strategy)
                if strategy is not None
                else None
            ),
            stop_price=stop_price,
            target_price=target_price,
            raw=serialize_value(payload),
        )

    def _merge_position(
        self,
        existing: PositionRuntime,
        incoming: PositionRuntime,
    ) -> None:
        existing.state = (
            incoming.state
            or existing.state
        )

        existing.last_seen_at = utc_now()

        existing.quantity = (
            incoming.quantity
            if incoming.quantity is not None
            else existing.quantity
        )

        existing.side = (
            incoming.side
            or existing.side
        )

        existing.entry_price = (
            incoming.entry_price
            if incoming.entry_price is not None
            else existing.entry_price
        )

        existing.current_price = (
            incoming.current_price
            if incoming.current_price is not None
            else existing.current_price
        )

        existing.unrealized_pl = (
            incoming.unrealized_pl
            if incoming.unrealized_pl is not None
            else existing.unrealized_pl
        )

        existing.unrealized_pl_pct = (
            incoming.unrealized_pl_pct
            if incoming.unrealized_pl_pct
            is not None
            else existing.unrealized_pl_pct
        )

        existing.strategy = (
            incoming.strategy
            or existing.strategy
        )

        existing.stop_price = (
            incoming.stop_price
            if incoming.stop_price is not None
            else existing.stop_price
        )

        existing.target_price = (
            incoming.target_price
            if incoming.target_price is not None
            else existing.target_price
        )

        existing.raw = incoming.raw

    async def monitor_position(
        self,
        position: PositionRuntime,
    ) -> None:
        monitor_service = (
            self._position_monitor_service()
        )

        if monitor_service is None:
            position.state = POSITION_MONITORING
            position.last_monitored_at = utc_now()
            position.monitor_cycles += 1
            return

        try:
            found, result, _ = await invoke_flexible(
                monitor_service,
                (
                    "monitor",
                    "evaluate",
                    "analyze_position",
                    "check",
                ),
                positional_variants=[
                    (position.raw,),
                    (
                        position.symbol,
                        position.raw,
                    ),
                    (position.symbol,),
                ],
                keyword_variants=[
                    {},
                    {
                        "asset_class": (
                            self.asset_class
                        )
                    },
                    {
                        "position": (
                            position.raw
                        ),
                        "asset_class": (
                            self.asset_class
                        ),
                    },
                ],
                required=False,
            )

            position.state = POSITION_MONITORING
            position.last_monitored_at = utc_now()
            position.monitor_cycles += 1
            position.last_error = None

            if found and result is not None:
                payload = ensure_mapping(
                    result
                )

                decision = first_present(
                    payload,
                    (
                        "decision",
                        "action",
                        "signal",
                    ),
                )

                if decision is not None:
                    position.decision = str(
                        decision
                    ).upper()

                risk_state = first_present(
                    payload,
                    (
                        "risk_state",
                        "risk",
                        "status",
                    ),
                )

                if isinstance(
                    risk_state,
                    Mapping,
                ):
                    risk_state = first_present(
                        risk_state,
                        (
                            "state",
                            "status",
                            "level",
                        ),
                    )

                if risk_state is not None:
                    position.risk_state = str(
                        risk_state
                    )

                stop_price = safe_float(
                    first_present(
                        payload,
                        (
                            "stop_price",
                            "stop",
                            "stop_loss",
                        ),
                    )
                )

                if stop_price is not None:
                    position.stop_price = (
                        stop_price
                    )

                target_price = safe_float(
                    first_present(
                        payload,
                        (
                            "target_price",
                            "target",
                            "take_profit",
                        ),
                    )
                )

                if target_price is not None:
                    position.target_price = (
                        target_price
                    )

        except Exception as exc:
            position.state = POSITION_ERROR
            position.failures += 1
            position.last_error = (
                compact_error(exc)
            )

            self.metrics.position_monitor_failures += 1

            await self._emit_event(
                "POSITION_MONITOR_FAILED",
                severity="ERROR",
                symbol=position.symbol,
                message=position.last_error,
            )

    async def _monitor_positions_once(
        self,
    ) -> None:
        await self.refresh_positions()

        if not self._positions:
            return

        tasks = [
            asyncio.create_task(
                self.monitor_position(position)
            )
            for position in list(
                self._positions.values()
            )
        ]

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

    # =========================================================================
    # MAIN LOOPS
    # =========================================================================

    async def _run_loop(self) -> None:
        await self._emit_event(
            "AUTOMATION_LOOP_STARTED",
            message=(
                f"{self.asset_class} discovery loop started"
            ),
        )

        try:
            while not self._stop_requested.is_set():
                if not self.section_enabled():
                    self.state.accepting_new_entries = (
                        False
                    )

                    self._entry_gate.clear()

                    self.state.state = (
                        RUNTIME_DRAINING
                    )

                    self.state.draining_since = (
                        self.state.draining_since
                        or utc_now()
                    )

                    await self._emit_event(
                        "AUTOMATION_SECTION_DISABLED",
                        severity="INFO",
                        message=(
                            f"{self.asset_class} section "
                            f"was disabled"
                        ),
                    )

                    return

                self.state.state = RUNTIME_RUNNING
                self.state.enabled = True
                self.state.accepting_new_entries = (
                    True
                )

                self._entry_gate.set()

                self._last_cycle_started_monotonic = (
                    monotonic_now()
                )

                try:
                    scan_result = (
                        await self.scan_market()
                    )

                    await self.process_scan_result(
                        scan_result
                    )

                    self.metrics.consecutive_failures = 0
                    self.state.last_error = None

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    self.metrics.loop_failures += 1
                    self.metrics.consecutive_failures += 1

                    self.state.last_error = (
                        compact_error(exc)
                    )

                    await self._emit_event(
                        "AUTOMATION_CYCLE_FAILED",
                        severity="ERROR",
                        message=self.state.last_error,
                    )

                    if (
                        self.metrics.consecutive_failures
                        >= self.max_consecutive_failures
                    ):
                        self.state.state = (
                            RUNTIME_ERROR
                        )

                        self.state.accepting_new_entries = (
                            False
                        )

                        self._entry_gate.clear()

                        await self._emit_event(
                            "AUTOMATION_RUNTIME_ERROR",
                            severity="CRITICAL",
                            message=(
                                "Maximum consecutive "
                                "automation failures "
                                "reached"
                            ),
                            data={
                                "failures": (
                                    self.metrics
                                    .consecutive_failures
                                )
                            },
                        )

                        return

                finally:
                    self._last_cycle_finished_monotonic = (
                        monotonic_now()
                    )

                delay = self._cycle_delay()

                try:
                    await asyncio.wait_for(
                        self._stop_requested.wait(),
                        timeout=delay,
                    )

                except asyncio.TimeoutError:
                    pass

        except asyncio.CancelledError:
            raise

        finally:
            self.state.accepting_new_entries = (
                False
            )

            self._entry_gate.clear()

            await self._emit_event(
                "AUTOMATION_LOOP_STOPPED",
                message=(
                    f"{self.asset_class} discovery loop stopped"
                ),
            )

    async def process_scan_result(
        self,
        scan_result: Mapping[str, Any],
    ) -> None:
        candidates = scan_result.get(
            "candidates",
            [],
        )

        if not candidates:
            await self._cleanup_stale_candidates()
            return

        now = monotonic_now()

        scheduled = 0

        for item in candidates:
            symbol = normalize_symbol(
                first_present(
                    item,
                    (
                        "symbol",
                        "ticker",
                    ),
                )
            )

            if not symbol:
                continue

            candidate = self._candidates.get(
                symbol
            )

            if candidate is None:
                continue

            if (
                candidate.next_analysis_at_monotonic
                > now
            ):
                continue

            if candidate.state in {
                CANDIDATE_ANALYZING,
                CANDIDATE_EXECUTING,
            }:
                continue

            task = asyncio.create_task(
                self._analyze_candidate_task(
                    candidate
                ),
                name=(
                    f"phoenixtrend-"
                    f"{self.asset_class}-"
                    f"candidate-{symbol}"
                ),
            )

            self._candidate_tasks.add(task)

            task.add_done_callback(
                self._candidate_task_done
            )

            scheduled += 1

            if (
                scheduled
                >= self.max_concurrent_analysis
            ):
                break

        await self._cleanup_stale_candidates()

    async def _analyze_candidate_task(
        self,
        candidate: CandidateRuntime,
    ) -> None:
        async with self._analysis_semaphore:
            if (
                self._stop_requested.is_set()
                or not self.accepts_new_entries()
            ):
                candidate.state = (
                    CANDIDATE_SKIPPED
                )
                return

            try:
                decision = (
                    await self.analyze_candidate(
                        candidate
                    )
                )

                await self.handle_decision(
                    candidate,
                    decision,
                )

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Candidate automation failed: "
                    "asset=%s symbol=%s",
                    self.asset_class,
                    candidate.symbol,
                )

    def _candidate_task_done(
        self,
        task: asyncio.Task[Any],
    ) -> None:
        self._candidate_tasks.discard(
            task
        )

        if task.cancelled():
            return

        try:
            task.result()
        except Exception:
            logger.exception(
                "Unhandled candidate task failure "
                "for %s",
                self.asset_class,
            )

    async def _position_monitor_loop(
        self,
    ) -> None:
        await self._emit_event(
            "POSITION_MONITOR_STARTED",
            message=(
                f"{self.asset_class} position monitor started"
            ),
        )

        try:
            while True:
                if (
                    self._stop_requested.is_set()
                    and not self._positions
                ):
                    return

                self._last_monitor_started_monotonic = (
                    monotonic_now()
                )

                try:
                    await self._monitor_positions_once()

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    self.metrics.position_monitor_failures += 1

                    await self._emit_event(
                        "POSITION_MONITOR_CYCLE_FAILED",
                        severity="ERROR",
                        message=compact_error(exc),
                    )

                finally:
                    self._last_monitor_finished_monotonic = (
                        monotonic_now()
                    )

                try:
                    await asyncio.wait_for(
                        self._stop_requested.wait(),
                        timeout=self.monitor_interval_seconds,
                    )

                    if not self._positions:
                        return

                except asyncio.TimeoutError:
                    pass

        except asyncio.CancelledError:
            raise

        finally:
            await self._emit_event(
                "POSITION_MONITOR_STOPPED",
                message=(
                    f"{self.asset_class} position monitor stopped"
                ),
            )

    async def _health_loop(self) -> None:
        try:
            while not self._stop_requested.is_set():
                self.state.last_health_at = utc_now()

                await self._emit_performance_snapshot()

                try:
                    await asyncio.wait_for(
                        self._stop_requested.wait(),
                        timeout=self.health_interval_seconds,
                    )
                except asyncio.TimeoutError:
                    pass

        except asyncio.CancelledError:
            raise

    # =========================================================================
    # DRAINING
    # =========================================================================

    async def _stop_discovery_task(
        self,
    ) -> None:
        if (
            self._main_task
            and not self._main_task.done()
            and self._main_task
            is not asyncio.current_task()
        ):
            await self._cancel_task(
                self._main_task
            )

            self._main_task = None

    async def _drain_open_positions(
        self,
        *,
        timeout: float,
    ) -> None:
        started = monotonic_now()

        try:
            await self.refresh_positions()
        except Exception as exc:
            await self._emit_event(
                "DRAIN_POSITION_REFRESH_FAILED",
                severity="WARNING",
                message=compact_error(exc),
            )

        while self._positions:
            if (
                monotonic_now() - started
                >= timeout
            ):
                await self._emit_event(
                    "AUTOMATION_DRAIN_TIMEOUT",
                    severity="WARNING",
                    message=(
                        f"{self.asset_class} runtime "
                        f"drain timeout reached with "
                        f"{len(self._positions)} "
                        f"open positions"
                    ),
                )

                return

            try:
                await self._monitor_positions_once()
            except Exception as exc:
                await self._emit_event(
                    "DRAIN_MONITOR_FAILED",
                    severity="ERROR",
                    message=compact_error(exc),
                )

            if not self._positions:
                return

            try:
                await asyncio.sleep(
                    min(
                        self.monitor_interval_seconds,
                        2.0,
                    )
                )
            except asyncio.CancelledError:
                raise

    # =========================================================================
    # HOUSEKEEPING
    # =========================================================================

    async def _cleanup_stale_candidates(
        self,
    ) -> None:
        if not self._candidates:
            return

        now = utc_now_dt()

        remove: list[str] = []

        for symbol, candidate in (
            self._candidates.items()
        ):
            if candidate.state in {
                CANDIDATE_ANALYZING,
                CANDIDATE_EXECUTING,
                CANDIDATE_EXECUTED,
            }:
                continue

            try:
                last_seen = datetime.fromisoformat(
                    candidate.last_seen_at
                )

                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(
                        tzinfo=timezone.utc
                    )

            except Exception:
                continue

            age = (
                now - last_seen
            ).total_seconds()

            if age >= self.stale_candidate_seconds:
                remove.append(symbol)

        if not remove:
            return

        async with self._candidate_lock:
            for symbol in remove:
                candidate = self._candidates.pop(
                    symbol,
                    None,
                )

                if candidate is not None:
                    self._candidate_history.append(
                        candidate.to_dict()
                    )

            self.state.candidate_count = len(
                self._candidates
            )

    async def _cancel_candidate_tasks(
        self,
    ) -> None:
        tasks = list(
            self._candidate_tasks
        )

        if not tasks:
            return

        for task in tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        self._candidate_tasks.clear()

    async def _cancel_task(
        self,
        task: asyncio.Task[Any] | None,
    ) -> None:
        if task is None:
            return

        if task.done():
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

            return

        if task is asyncio.current_task():
            return

        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    def _cycle_delay(self) -> float:
        failures = (
            self.metrics.consecutive_failures
        )

        if failures <= 0:
            return max(
                0.25,
                float(
                    self.scan_interval_seconds
                ),
            )

        backoff = (
            self.failure_backoff_seconds
            * (2 ** min(failures - 1, 6))
        )

        return min(
            max(
                float(
                    self.scan_interval_seconds
                ),
                backoff,
            ),
            self.max_failure_backoff_seconds,
        )

    def _failure_backoff_delay(
        self,
        failures: int,
    ) -> float:
        if failures <= 0:
            return self.failure_backoff_seconds

        delay = (
            self.failure_backoff_seconds
            * (2 ** min(failures - 1, 6))
        )

        return min(
            delay,
            self.max_failure_backoff_seconds,
        )

    # =========================================================================
    # EVENTS / AUDIT / PERFORMANCE
    # =========================================================================

    async def _emit_event(
        self,
        event_type: str,
        *,
        severity: str = "INFO",
        symbol: str | None = None,
        message: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> RuntimeEvent:
        event = RuntimeEvent(
            event_id=uuid.uuid4().hex,
            timestamp=utc_now(),
            asset_class=self.asset_class,
            event_type=event_type,
            severity=severity,
            symbol=(
                normalize_symbol(symbol)
                if symbol
                else None
            ),
            message=message,
            data=serialize_value(
                dict(data or {})
            ),
        )

        self._event_history.append(
            event
        )

        audit_service = self._audit_service()

        if audit_service is not None:
            try:
                await invoke_flexible(
                    audit_service,
                    (
                        "record",
                        "emit",
                        "log",
                        "write",
                        "add",
                    ),
                    positional_variants=[
                        (
                            event.event_type,
                            event.to_dict(),
                        ),
                        (event.to_dict(),),
                    ],
                    keyword_variants=[
                        {},
                        {
                            "event_type": (
                                event.event_type
                            ),
                            "payload": (
                                event.to_dict()
                            ),
                        },
                    ],
                    required=False,
                )
            except Exception:
                logger.exception(
                    "Audit event publication failed: "
                    "%s",
                    event.event_type,
                )

        return event

    async def _emit_performance_snapshot(
        self,
    ) -> None:
        performance_service = (
            self._performance_service()
        )

        if performance_service is None:
            return

        snapshot = {
            "asset_class": self.asset_class,
            "runtime": self.state.to_dict(),
            "metrics": self.metrics.to_dict(),
            "candidate_count": len(
                self._candidates
            ),
            "position_count": len(
                self._positions
            ),
            "timestamp": utc_now(),
        }

        try:
            await invoke_flexible(
                performance_service,
                (
                    "record_runtime",
                    "record_snapshot",
                    "update_runtime",
                    "ingest_runtime",
                ),
                positional_variants=[
                    (snapshot,),
                    (
                        self.asset_class,
                        snapshot,
                    ),
                ],
                keyword_variants=[
                    {},
                    {
                        "asset_class": (
                            self.asset_class
                        ),
                        "snapshot": snapshot,
                    },
                ],
                required=False,
            )
        except Exception:
            logger.exception(
                "Performance snapshot publication "
                "failed for %s",
                self.asset_class,
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
        self.state.enabled = (
            self.section_enabled()
        )

        self.state.universe_size = len(
            self._universe
        )

        self.state.candidate_count = len(
            self._candidates
        )

        self.state.active_position_count = len(
            self._positions
        )

        payload: dict[str, Any] = {
            **self.state.to_dict(),
            "runtime_id": self.state.runtime_id,
            "asset_class": self.asset_class,
            "section_enabled": (
                self.section_enabled()
            ),
            "accepting_new_entries": (
                self.accepts_new_entries()
            ),
            "is_running": self.is_running(),
            "is_draining": self.is_draining(),
            "universe": list(
                self._universe
            ),
            "universe_size": len(
                self._universe
            ),
            "candidate_count": len(
                self._candidates
            ),
            "active_position_count": len(
                self._positions
            ),
            "metrics": self.metrics.to_dict(),
            "task_state": {
                "main": self._task_status(
                    self._main_task
                ),
                "monitor": self._task_status(
                    self._monitor_task
                ),
                "health": self._task_status(
                    self._health_task
                ),
                "candidate_tasks": len(
                    self._candidate_tasks
                ),
            },
            "configuration": {
                "scan_interval_seconds": (
                    self.scan_interval_seconds
                ),
                "monitor_interval_seconds": (
                    self.monitor_interval_seconds
                ),
                "health_interval_seconds": (
                    self.health_interval_seconds
                ),
                "universe_refresh_seconds": (
                    self.universe_refresh_seconds
                ),
                "hold_recheck_seconds": (
                    self.hold_recheck_seconds
                ),
                "candidate_limit": (
                    self.candidate_limit
                ),
                "max_concurrent_analysis": (
                    self.max_concurrent_analysis
                ),
                "max_concurrent_executions": (
                    self.max_concurrent_executions
                ),
                "allow_automatic_entries": (
                    self.allow_automatic_entries
                ),
            },
        }

        if include_candidates:
            payload["candidates"] = (
                self.candidates()
            )

        if include_positions:
            payload["positions"] = (
                self.positions()
            )

        if include_decisions:
            payload["decisions"] = (
                self.decisions()
            )

        if include_events:
            payload["events"] = (
                self.events()
            )

        return serialize_value(payload)

    def _task_status(
        self,
        task: asyncio.Task[Any] | None,
    ) -> str:
        if task is None:
            return "NONE"

        if task.cancelled():
            return "CANCELLED"

        if task.done():
            try:
                exception = task.exception()
            except asyncio.CancelledError:
                return "CANCELLED"

            if exception is not None:
                return "FAILED"

            return "DONE"

        return "RUNNING"

    # =========================================================================
    # MANUAL CYCLE / DIAGNOSTICS
    # =========================================================================

    async def run_cycle_once(
        self,
        *,
        allow_execution: bool = False,
    ) -> dict[str, Any]:
        """
        Run one explicit diagnostic cycle.

        Execution is disabled by default so this method can be used by health
        checks and tests without accidentally placing an automatic trade.
        """

        original_entry_state = (
            self._entry_gate.is_set()
        )

        original_accepting = (
            self.state.accepting_new_entries
        )

        if not allow_execution:
            self._entry_gate.clear()
            self.state.accepting_new_entries = (
                False
            )

        try:
            scan_result = await self.scan_market()

            candidates = scan_result.get(
                "candidates",
                [],
            )

            results: list[dict[str, Any]] = []

            for item in candidates[
                : self.max_concurrent_analysis
            ]:
                symbol = normalize_symbol(
                    item.get("symbol")
                )

                candidate = self._candidates.get(
                    symbol
                )

                if candidate is None:
                    continue

                try:
                    decision = (
                        await self.analyze_candidate(
                            candidate
                        )
                    )

                    if allow_execution:
                        await self.handle_decision(
                            candidate,
                            decision,
                        )

                    results.append(
                        decision.to_dict()
                    )

                except Exception as exc:
                    results.append(
                        {
                            "symbol": symbol,
                            "error": (
                                compact_error(exc)
                            ),
                        }
                    )

            try:
                await self._monitor_positions_once()
            except Exception:
                pass

            return {
                "asset_class": self.asset_class,
                "scan": serialize_value(
                    scan_result
                ),
                "decisions": results,
                "status": self.status(
                    include_events=False
                ),
            }

        finally:
            self.state.accepting_new_entries = (
                original_accepting
            )

            if original_entry_state:
                self._entry_gate.set()
            else:
                self._entry_gate.clear()

    async def clear_runtime_history(
        self,
    ) -> None:
        self._decision_history.clear()
        self._event_history.clear()
        self._candidate_history.clear()
        self._position_history.clear()

    async def clear_candidates(
        self,
        *,
        preserve_actionable: bool = True,
    ) -> None:
        async with self._candidate_lock:
            if not preserve_actionable:
                self._candidates.clear()

            else:
                self._candidates = {
                    symbol: candidate
                    for symbol, candidate
                    in self._candidates.items()
                    if candidate.state
                    in {
                        CANDIDATE_ACTIONABLE,
                        CANDIDATE_EXECUTING,
                        CANDIDATE_EXECUTED,
                    }
                }

            self.state.candidate_count = len(
                self._candidates
            )

    # =========================================================================
    # ASSET OVERRIDE HOOKS
    # =========================================================================

    async def before_scan(
        self,
    ) -> None:
        """
        Asset runtimes may override this hook for real asset-specific
        preparation. The base implementation intentionally does nothing.
        """
        return None

    async def after_scan(
        self,
        result: Mapping[str, Any],
    ) -> None:
        """
        Asset runtimes may override this hook for asset-specific telemetry.
        """
        return None

    async def validate_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> tuple[bool, str | None]:
        """
        Asset runtimes may apply additional real-data eligibility checks.
        """
        if not candidate.symbol:
            return False, "Candidate has no symbol"

        return True, None

    async def prepare_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> CandidateRuntime:
        """
        Asset runtimes may enrich the candidate with provider-supported data.
        """
        return candidate

    async def prepare_execution(
        self,
        candidate: CandidateRuntime,
        decision: DecisionRuntime,
    ) -> tuple[CandidateRuntime, DecisionRuntime]:
        """
        Asset runtimes may transform a valid underlying decision into the
        correct executable instrument. Options automation, for example,
        should perform contract selection in its subclass rather than in this
        common runtime.
        """
        return candidate, decision

    # =========================================================================
    # EXTENDED CANDIDATE PIPELINE
    # =========================================================================

    async def process_candidate(
        self,
        candidate: CandidateRuntime,
    ) -> DecisionRuntime | None:
        valid, reason = (
            await self.validate_candidate(
                candidate
            )
        )

        if not valid:
            candidate.state = (
                CANDIDATE_SKIPPED
            )

            candidate.last_error = reason

            await self._emit_event(
                "CANDIDATE_SKIPPED",
                severity="INFO",
                symbol=candidate.symbol,
                message=reason,
            )

            return None

        candidate = await self.prepare_candidate(
            candidate
        )

        decision = await self.analyze_candidate(
            candidate
        )

        if decision.action != ACTION_HOLD:
            candidate, decision = (
                await self.prepare_execution(
                    candidate,
                    decision,
                )
            )

        await self.handle_decision(
            candidate,
            decision,
        )

        return decision

    # =========================================================================
    # RUNTIME HEALTH
    # =========================================================================

    def health(self) -> dict[str, Any]:
        main_alive = bool(
            self._main_task
            and not self._main_task.done()
        )

        monitor_alive = bool(
            self._monitor_task
            and not self._monitor_task.done()
        )

        health_alive = bool(
            self._health_task
            and not self._health_task.done()
        )

        healthy = True
        reasons: list[str] = []

        if (
            self.state.state
            == RUNTIME_RUNNING
            and not main_alive
        ):
            healthy = False
            reasons.append(
                "Discovery task is not running"
            )

        if (
            self.state.state
            in {
                RUNTIME_RUNNING,
                RUNTIME_DRAINING,
            }
            and not monitor_alive
            and self._positions
        ):
            healthy = False
            reasons.append(
                "Position monitor is not running"
            )

        if (
            self.state.state
            == RUNTIME_RUNNING
            and not health_alive
        ):
            healthy = False
            reasons.append(
                "Health task is not running"
            )

        if (
            self.metrics.consecutive_failures
            >= self.max_consecutive_failures
        ):
            healthy = False
            reasons.append(
                "Consecutive failure threshold reached"
            )

        return {
            "healthy": healthy,
            "asset_class": self.asset_class,
            "state": self.state.state,
            "reasons": reasons,
            "tasks": {
                "main": self._task_status(
                    self._main_task
                ),
                "monitor": self._task_status(
                    self._monitor_task
                ),
                "health": self._task_status(
                    self._health_task
                ),
            },
            "metrics": self.metrics.to_dict(),
            "last_error": self.state.last_error,
            "timestamp": utc_now(),
        }

    # =========================================================================
    # CONTEXT MANAGER SUPPORT
    # =========================================================================

    async def __aenter__(
        self,
    ) -> "BaseAssetAutomation":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc: Any,
        traceback: Any,
    ) -> None:
        await self.stop(
            drain=True,
            reason=(
                "Automation context closed"
                if exc is None
                else (
                    "Automation context closed "
                    f"after error: "
                    f"{compact_error(exc)}"
                )
            ),
        )