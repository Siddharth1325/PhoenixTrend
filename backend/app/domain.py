from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ============================================================
# HELPERS
# ============================================================


def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _finite_float(
    value: Any,
    *,
    field_name: str,
    allow_none: bool = False,
    positive: bool = False,
    non_negative: bool = False,
) -> float | None:
    if value is None:
        if allow_none:
            return None

        raise ValueError(
            f"{field_name} is required"
        )

    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            f"{field_name} must be numeric"
        )

    try:
        number = float(
            value
        )

    except (
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise ValueError(
            f"{field_name} must be numeric"
        ) from exc

    if not isfinite(
        number
    ):
        raise ValueError(
            f"{field_name} must be finite"
        )

    if (
        positive
        and number <= 0
    ):
        raise ValueError(
            f"{field_name} must be greater than zero"
        )

    if (
        non_negative
        and number < 0
    ):
        raise ValueError(
            f"{field_name} cannot be negative"
        )

    return number


def _clean_required_text(
    value: Any,
    *,
    field_name: str,
    max_length: int | None = None,
) -> str:
    if value is None:
        raise ValueError(
            f"{field_name} is required"
        )

    text = str(
        value
    ).strip()

    if not text:
        raise ValueError(
            f"{field_name} is required"
        )

    if (
        max_length is not None
        and len(
            text
        ) > max_length
    ):
        raise ValueError(
            f"{field_name} is too long"
        )

    return text


def _clean_optional_text(
    value: Any,
    *,
    max_length: int | None = None,
) -> str | None:
    if value is None:
        return None

    text = str(
        value
    ).strip()

    if not text:
        return None

    if (
        max_length is not None
        and len(
            text
        ) > max_length
    ):
        raise ValueError(
            "value is too long"
        )

    return text


def _normalize_symbol(
    value: Any,
) -> str:
    symbol = _clean_required_text(
        value,
        field_name="symbol",
        max_length=128,
    ).upper()

    if any(
        character.isspace()
        for character in symbol
    ):
        raise ValueError(
            "symbol cannot contain whitespace"
        )

    return symbol


def _normalize_currency(
    value: Any,
    *,
    field_name: str,
) -> str:
    currency = _clean_required_text(
        value,
        field_name=field_name,
        max_length=16,
    ).upper()

    return currency


# ============================================================
# ENUMS
# ============================================================


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExecutionMode(
    str,
    Enum,
):
    MANUAL = "MANUAL"
    CONTROLLED = "CONTROLLED"
    AUTOMATIC = "AUTOMATIC"


class RiskStatus(
    str,
    Enum,
):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AssetType(
    str,
    Enum,
):
    EQUITY = "EQUITY"
    ETF = "ETF"
    OPTION = "OPTION"
    CRYPTO = "CRYPTO"
    FOREX = "FOREX"
    BOND = "BOND"
    COMMODITY = "COMMODITY"


# ============================================================
# INSTRUMENT MODEL
# ============================================================


class Instrument(
    BaseModel
):
    """
    Normalized PhoenixTrend tradable instrument.

    Instrument contains identity and instrument metadata only.

    It does not imply:
        - broker support
        - broker entitlement
        - tradability
        - liquidity
        - market-data availability
        - execution authorization
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    symbol: str
    asset_type: AssetType

    venue: str | None = None

    currency: str | None = None

    # --------------------------------------------------------
    # OPTIONS
    # --------------------------------------------------------

    underlying: str | None = None

    expiration: str | None = None

    strike: float | None = None

    option_type: Literal[
        "CALL",
        "PUT",
    ] | None = None

    multiplier: float | None = None

    # --------------------------------------------------------
    # FX / CRYPTO PAIRS
    # --------------------------------------------------------

    base_currency: str | None = None

    quote_currency: str | None = None

    # --------------------------------------------------------
    # GENERIC PROVIDER METADATA
    # --------------------------------------------------------

    metadata: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict
    )

    @field_validator(
        "symbol",
        mode="before",
    )
    @classmethod
    def _validate_symbol(
        cls,
        value: Any,
    ) -> str:
        return _normalize_symbol(
            value
        )

    @field_validator(
        "venue",
        "underlying",
        "expiration",
        mode="before",
    )
    @classmethod
    def _normalize_optional_strings(
        cls,
        value: Any,
    ) -> str | None:
        return _clean_optional_text(
            value,
            max_length=128,
        )

    @field_validator(
        "currency",
        "base_currency",
        "quote_currency",
        mode="before",
    )
    @classmethod
    def _normalize_currency_fields(
        cls,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        text = str(
            value
        ).strip()

        if not text:
            return None

        return _normalize_currency(
            text,
            field_name="currency",
        )

    @field_validator(
        "strike",
        "multiplier",
        mode="before",
    )
    @classmethod
    def _validate_positive_optional_number(
        cls,
        value: Any,
        info,
    ) -> float | None:
        return _finite_float(
            value,
            field_name=(
                info.field_name
            ),
            allow_none=True,
            positive=True,
        )

    @model_validator(
        mode="after",
    )
    def _validate_asset_metadata(
        self,
    ) -> "Instrument":
        if (
            self.asset_type
            == AssetType.OPTION
        ):
            if not self.underlying:
                raise ValueError(
                    "Option instrument requires underlying"
                )

            if not self.expiration:
                raise ValueError(
                    "Option instrument requires expiration"
                )

            if self.strike is None:
                raise ValueError(
                    "Option instrument requires strike"
                )

            if self.option_type is None:
                raise ValueError(
                    "Option instrument requires option_type"
                )

        if (
            self.asset_type
            == AssetType.FOREX
        ):
            if not self.base_currency:
                raise ValueError(
                    "Forex instrument requires base_currency"
                )

            if not self.quote_currency:
                raise ValueError(
                    "Forex instrument requires quote_currency"
                )

        return self


# ============================================================
# STRATEGY SIGNAL
# ============================================================


class Signal(
    BaseModel
):
    """
    Genuine strategy output.

    Signal is analysis only.

    It does not authorize execution.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    symbol: str

    side: Side

    strategy: str

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    rationale: list[
        str
    ] = Field(
        default_factory=list
    )

    stop: float | None = None

    target: float | None = None

    generated_at: datetime = Field(
        default_factory=utc_now
    )

    @field_validator(
        "symbol",
        mode="before",
    )
    @classmethod
    def _validate_symbol(
        cls,
        value: Any,
    ) -> str:
        return _normalize_symbol(
            value
        )

    @field_validator(
        "strategy",
        mode="before",
    )
    @classmethod
    def _validate_strategy(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="strategy",
            max_length=128,
        )

    @field_validator(
        "confidence",
        mode="before",
    )
    @classmethod
    def _validate_confidence(
        cls,
        value: Any,
    ) -> float:
        result = _finite_float(
            value,
            field_name="confidence",
        )

        assert result is not None

        return result

    @field_validator(
        "stop",
        "target",
        mode="before",
    )
    @classmethod
    def _validate_optional_price(
        cls,
        value: Any,
        info,
    ) -> float | None:
        return _finite_float(
            value,
            field_name=(
                info.field_name
            ),
            allow_none=True,
            positive=True,
        )

    @field_validator(
        "rationale",
        mode="before",
    )
    @classmethod
    def _normalize_rationale(
        cls,
        value: Any,
    ) -> list[str]:
        if value is None:
            return []

        if isinstance(
            value,
            str,
        ):
            clean = value.strip()

            return (
                [clean]
                if clean
                else []
            )

        if not isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            raise ValueError(
                "rationale must be a list of strings"
            )

        output: list[
            str
        ] = []

        for item in value:
            text = str(
                item
            ).strip()

            if text:
                output.append(
                    text
                )

        return output

    @field_validator(
        "generated_at",
    )
    @classmethod
    def _validate_generated_at(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                "generated_at must contain timezone information"
            )

        return value


# ============================================================
# TRADE INTENT
# ============================================================


class TradeIntent(
    BaseModel
):
    """
    Standard trade request shared by PhoenixTrend engines.

    Typical execution path:

        analysis
            ->
        strategy
            ->
        DecisionEngine
            ->
        TradeIntent
            ->
        MarketSafety
            ->
        RiskEngine
            ->
        broker capability
            ->
        ExecutionService
            ->
        broker

    TradeIntent itself does not represent authorization.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    intent_id: str

    symbol: str

    asset_type: AssetType = (
        AssetType.EQUITY
    )

    instrument: Instrument | None = None

    side: Side

    qty: float = Field(
        gt=0,
    )

    reference_price: float = Field(
        gt=0,
    )

    strategy: str

    automation_id: str | None = None

    execution_mode: ExecutionMode = (
        ExecutionMode.CONTROLLED
    )

    # --------------------------------------------------------
    # POSITION EFFECT
    # --------------------------------------------------------

    # True means the order must only reduce/close an existing
    # position and must not create or enlarge exposure.
    #
    # Enforcement belongs to ExecutionService/broker adapter.
    reduce_only: bool = False

    # Explicit semantic description for risk/execution.
    position_effect: Literal[
        "AUTO",
        "OPEN",
        "INCREASE",
        "REDUCE",
        "CLOSE",
    ] = "AUTO"

    # --------------------------------------------------------
    # RISK CONTROLS
    # --------------------------------------------------------

    stop: float | None = None

    target: float | None = None

    max_loss: float | None = None

    # --------------------------------------------------------
    # BROKER ORDER CONFIGURATION
    # --------------------------------------------------------

    order_type: Literal[
        "market",
        "limit",
        "stop",
        "stop_limit",
    ] = "market"

    time_in_force: str = "day"

    limit_price: float | None = None

    stop_price: float | None = None

    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    metadata: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict
    )

    @field_validator(
        "intent_id",
        mode="before",
    )
    @classmethod
    def _validate_intent_id(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="intent_id",
            max_length=128,
        )

    @field_validator(
        "symbol",
        mode="before",
    )
    @classmethod
    def _validate_symbol(
        cls,
        value: Any,
    ) -> str:
        return _normalize_symbol(
            value
        )

    @field_validator(
        "strategy",
        mode="before",
    )
    @classmethod
    def _validate_strategy(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="strategy",
            max_length=128,
        )

    @field_validator(
        "automation_id",
        mode="before",
    )
    @classmethod
    def _validate_automation_id(
        cls,
        value: Any,
    ) -> str | None:
        return _clean_optional_text(
            value,
            max_length=128,
        )

    @field_validator(
        "qty",
        "reference_price",
        mode="before",
    )
    @classmethod
    def _validate_required_positive_numbers(
        cls,
        value: Any,
        info,
    ) -> float:
        result = _finite_float(
            value,
            field_name=(
                info.field_name
            ),
            positive=True,
        )

        assert result is not None

        return result

    @field_validator(
        "stop",
        "target",
        "limit_price",
        "stop_price",
        mode="before",
    )
    @classmethod
    def _validate_optional_prices(
        cls,
        value: Any,
        info,
    ) -> float | None:
        return _finite_float(
            value,
            field_name=(
                info.field_name
            ),
            allow_none=True,
            positive=True,
        )

    @field_validator(
        "max_loss",
        mode="before",
    )
    @classmethod
    def _validate_max_loss(
        cls,
        value: Any,
    ) -> float | None:
        return _finite_float(
            value,
            field_name="max_loss",
            allow_none=True,
            positive=True,
        )

    @field_validator(
        "time_in_force",
        mode="before",
    )
    @classmethod
    def _validate_time_in_force(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="time_in_force",
            max_length=32,
        ).lower()

    @model_validator(
        mode="after",
    )
    def validate_intent(
        self,
    ) -> "TradeIntent":
        # ----------------------------------------------------
        # INSTRUMENT CONSISTENCY
        # ----------------------------------------------------

        if self.instrument is not None:
            if (
                self.instrument.symbol
                != self.symbol
            ):
                raise ValueError(
                    "instrument.symbol must match TradeIntent.symbol"
                )

            if (
                self.instrument.asset_type
                != self.asset_type
            ):
                raise ValueError(
                    "instrument.asset_type must match TradeIntent.asset_type"
                )

        # ----------------------------------------------------
        # ORDER CONFIGURATION
        # ----------------------------------------------------

        if (
            self.order_type
            in {
                "limit",
                "stop_limit",
            }
            and self.limit_price
            is None
        ):
            raise ValueError(
                f"{self.order_type} order requires limit_price"
            )

        if (
            self.order_type
            in {
                "stop",
                "stop_limit",
            }
            and self.stop_price
            is None
        ):
            raise ValueError(
                f"{self.order_type} order requires stop_price"
            )

        # ----------------------------------------------------
        # OPTION CONTRACT QUANTITY
        # ----------------------------------------------------

        if (
            self.asset_type
            == AssetType.OPTION
            and not float(
                self.qty
            ).is_integer()
        ):
            raise ValueError(
                "Option quantity must be a whole number of contracts"
            )

        # ----------------------------------------------------
        # REDUCE-ONLY SEMANTICS
        # ----------------------------------------------------

        if (
            self.reduce_only
            and self.position_effect
            in {
                "OPEN",
                "INCREASE",
            }
        ):
            raise ValueError(
                "reduce_only intent cannot OPEN or INCREASE a position"
            )

        if (
            self.position_effect
            in {
                "REDUCE",
                "CLOSE",
            }
            and not self.reduce_only
        ):
            self.reduce_only = True

        return self


# ============================================================
# ACCOUNT STATE
# ============================================================


class AccountState(
    BaseModel
):
    """
    Account/risk values observed from the connected broker or
    authoritative portfolio subsystem.

    Missing values remain None.

    Zero is valid only when the provider actually reports zero.

    This prevents unavailable data from becoming fabricated:
        buying_power=0
        P&L=0
        positions=0
        exposure=0
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    buying_power: float | None = None

    daily_pnl: float | None = None

    weekly_pnl: float | None = None

    open_positions: int | None = None

    gross_exposure: float | None = None

    equity: float | None = None

    cash: float | None = None

    portfolio_value: float | None = None

    account_status: str | None = None

    trading_blocked: bool | None = None

    account_blocked: bool | None = None

    trade_suspended_by_user: bool | None = None

    source: str | None = None

    observed_at: datetime | None = None

    @field_validator(
        "buying_power",
        "gross_exposure",
        "equity",
        "cash",
        "portfolio_value",
        mode="before",
    )
    @classmethod
    def _validate_non_negative_values(
        cls,
        value: Any,
        info,
    ) -> float | None:
        return _finite_float(
            value,
            field_name=(
                info.field_name
            ),
            allow_none=True,
            non_negative=True,
        )

    @field_validator(
        "daily_pnl",
        "weekly_pnl",
        mode="before",
    )
    @classmethod
    def _validate_pnl(
        cls,
        value: Any,
        info,
    ) -> float | None:
        return _finite_float(
            value,
            field_name=(
                info.field_name
            ),
            allow_none=True,
        )

    @field_validator(
        "open_positions",
        mode="before",
    )
    @classmethod
    def _validate_open_positions(
        cls,
        value: Any,
    ) -> int | None:
        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "open_positions must be an integer"
            )

        try:
            number = int(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ValueError(
                "open_positions must be an integer"
            ) from exc

        if number < 0:
            raise ValueError(
                "open_positions cannot be negative"
            )

        return number

    @field_validator(
        "account_status",
        "source",
        mode="before",
    )
    @classmethod
    def _validate_optional_text(
        cls,
        value: Any,
    ) -> str | None:
        return _clean_optional_text(
            value,
            max_length=128,
        )

    @field_validator(
        "observed_at",
    )
    @classmethod
    def _validate_observed_at(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            raise ValueError(
                "observed_at must contain timezone information"
            )

        return value


# ============================================================
# RISK DECISION
# ============================================================


class RiskDecision(
    BaseModel
):
    """
    Result of the PhoenixTrend risk stage.

    approved_qty / approved_notional remain optional unless the
    decision is actually APPROVED.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    status: RiskStatus

    reasons: list[
        str
    ] = Field(
        default_factory=list
    )

    approved_qty: float | None = None

    approved_notional: float | None = None

    @field_validator(
        "approved_qty",
        "approved_notional",
        mode="before",
    )
    @classmethod
    def _validate_approved_values(
        cls,
        value: Any,
        info,
    ) -> float | None:
        return _finite_float(
            value,
            field_name=(
                info.field_name
            ),
            allow_none=True,
            non_negative=True,
        )

    @field_validator(
        "reasons",
        mode="before",
    )
    @classmethod
    def _validate_reasons(
        cls,
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

        if not isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            raise ValueError(
                "reasons must be a list"
            )

        return [
            text
            for text in (
                str(
                    item
                ).strip()
                for item in value
            )
            if text
        ]

    @model_validator(
        mode="after",
    )
    def _validate_decision(
        self,
    ) -> "RiskDecision":
        if (
            self.status
            == RiskStatus.APPROVED
        ):
            if (
                self.approved_qty
                is None
                or self.approved_qty
                <= 0
            ):
                raise ValueError(
                    "Approved risk decision requires approved_qty > 0"
                )

            if (
                self.approved_notional
                is None
                or self.approved_notional
                <= 0
            ):
                raise ValueError(
                    "Approved risk decision requires approved_notional > 0"
                )

        return self

    @property
    def approved(
        self,
    ) -> bool:
        return (
            self.status
            == RiskStatus.APPROVED
        )


# ============================================================
# BROKER ORDER
# ============================================================


class Order(
    BaseModel
):
    """
    Normalized broker order.

    reference_price is PhoenixTrend's decision/reference price.

    filled_avg_price is populated only when the broker reports
    a genuine fill price.

    price remains as a compatibility field for existing callers,
    but it must not be interpreted as proof of fill unless the
    broker order status/fill data confirms execution.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    order_id: str

    intent_id: str

    symbol: str

    asset_type: AssetType = (
        AssetType.EQUITY
    )

    side: Side

    qty: float

    price: float | None = None

    reference_price: float | None = None

    filled_avg_price: float | None = None

    filled_qty: float | None = None

    status: str

    broker: str

    submitted_at: datetime | None = None

    filled_at: datetime | None = None

    @field_validator(
        "order_id",
        mode="before",
    )
    @classmethod
    def _validate_order_id(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="order_id",
            max_length=128,
        )

    @field_validator(
        "intent_id",
        mode="before",
    )
    @classmethod
    def _validate_intent_id(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="intent_id",
            max_length=128,
        )

    @field_validator(
        "symbol",
        mode="before",
    )
    @classmethod
    def _validate_symbol(
        cls,
        value: Any,
    ) -> str:
        return _normalize_symbol(
            value
        )

    @field_validator(
        "qty",
        mode="before",
    )
    @classmethod
    def _validate_qty(
        cls,
        value: Any,
    ) -> float:
        result = _finite_float(
            value,
            field_name="qty",
            positive=True,
        )

        assert result is not None

        return result

    @field_validator(
        "price",
        "reference_price",
        "filled_avg_price",
        mode="before",
    )
    @classmethod
    def _validate_prices(
        cls,
        value: Any,
        info,
    ) -> float | None:
        return _finite_float(
            value,
            field_name=(
                info.field_name
            ),
            allow_none=True,
            positive=True,
        )

    @field_validator(
        "filled_qty",
        mode="before",
    )
    @classmethod
    def _validate_filled_qty(
        cls,
        value: Any,
    ) -> float | None:
        return _finite_float(
            value,
            field_name="filled_qty",
            allow_none=True,
            non_negative=True,
        )

    @field_validator(
        "status",
        "broker",
        mode="before",
    )
    @classmethod
    def _validate_required_strings(
        cls,
        value: Any,
        info,
    ) -> str:
        return _clean_required_text(
            value,
            field_name=(
                info.field_name
            ),
            max_length=128,
        )

    @field_validator(
        "submitted_at",
        "filled_at",
    )
    @classmethod
    def _validate_order_timestamps(
        cls,
        value: datetime | None,
        info,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            raise ValueError(
                f"{info.field_name} must contain timezone information"
            )

        return value


# ============================================================
# POSITION
# ============================================================


class Position(
    BaseModel
):
    """
    Normalized broker/portfolio position.

    Position quantity is positive magnitude.

    side identifies whether the position is LONG or SHORT when
    that information is known.

    Existing callers that do not yet provide side remain
    compatible because side is optional.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    position_id: str

    symbol: str

    asset_type: AssetType = (
        AssetType.EQUITY
    )

    qty: float

    side: Literal[
        "LONG",
        "SHORT",
    ] | None = None

    avg_entry: float

    current_price: float

    strategy: str

    execution_mode: ExecutionMode

    stop: float | None = None

    target: float | None = None

    trailing_pct: float | None = None

    highest_price: float | None = None

    lowest_price: float | None = None

    opened_at: datetime | None = None

    metadata: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict
    )

    @field_validator(
        "position_id",
        mode="before",
    )
    @classmethod
    def _validate_position_id(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="position_id",
            max_length=128,
        )

    @field_validator(
        "symbol",
        mode="before",
    )
    @classmethod
    def _validate_symbol(
        cls,
        value: Any,
    ) -> str:
        return _normalize_symbol(
            value
        )

    @field_validator(
        "strategy",
        mode="before",
    )
    @classmethod
    def _validate_strategy(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="strategy",
            max_length=128,
        )

    @field_validator(
        "qty",
        "avg_entry",
        "current_price",
        mode="before",
    )
    @classmethod
    def _validate_required_positive_values(
        cls,
        value: Any,
        info,
    ) -> float:
        result = _finite_float(
            value,
            field_name=(
                info.field_name
            ),
            positive=True,
        )

        assert result is not None

        return result

    @field_validator(
        "stop",
        "target",
        "highest_price",
        "lowest_price",
        mode="before",
    )
    @classmethod
    def _validate_optional_positive_values(
        cls,
        value: Any,
        info,
    ) -> float | None:
        return _finite_float(
            value,
            field_name=(
                info.field_name
            ),
            allow_none=True,
            positive=True,
        )

    @field_validator(
        "trailing_pct",
        mode="before",
    )
    @classmethod
    def _validate_trailing_pct(
        cls,
        value: Any,
    ) -> float | None:
        result = _finite_float(
            value,
            field_name="trailing_pct",
            allow_none=True,
            positive=True,
        )

        if result is None:
            return None

        if result >= 100:
            raise ValueError(
                "trailing_pct must be less than 100"
            )

        return result

    @field_validator(
        "opened_at",
    )
    @classmethod
    def _validate_opened_at(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            raise ValueError(
                "opened_at must contain timezone information"
            )

        return value


# ============================================================
# BROKER REQUESTS
# ============================================================


class AlpacaConnectRequest(
    BaseModel
):
    """
    Credentials are accepted by the broker connection endpoint
    and must never be logged, persisted, or placed into audit
    detail.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    api_key: str

    secret_key: str

    paper: bool = True

    @field_validator(
        "api_key",
        mode="before",
    )
    @classmethod
    def _validate_api_key(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="api_key",
            max_length=512,
        )

    @field_validator(
        "secret_key",
        mode="before",
    )
    @classmethod
    def _validate_secret_key(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="secret_key",
            max_length=512,
        )


# ============================================================
# MANUAL ORDER REQUEST
# ============================================================


class ManualOrderRequest(
    BaseModel
):
    """
    User-controlled order request.

    This request is not sent directly to a broker.

    ManualEngine / ExecutionService must still construct a
    TradeIntent and pass the order through the same:

        market safety
        risk
        capability
        execution
        persistence
        audit

    pipeline used by automation.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    symbol: str

    asset_type: AssetType = (
        AssetType.EQUITY
    )

    qty: float = Field(
        gt=0,
    )

    side: Literal[
        "buy",
        "sell",
    ]

    order_type: Literal[
        "market",
        "limit",
        "stop",
        "stop_limit",
    ] = "market"

    time_in_force: str = "day"

    limit_price: float | None = None

    stop_price: float | None = None

    reduce_only: bool = False

    # --------------------------------------------------------
    # OPTIONS
    # --------------------------------------------------------

    underlying: str | None = None

    expiration: str | None = None

    strike: float | None = None

    option_type: Literal[
        "CALL",
        "PUT",
    ] | None = None

    multiplier: float | None = None

    # --------------------------------------------------------
    # FX / CRYPTO
    # --------------------------------------------------------

    base_currency: str | None = None

    quote_currency: str | None = None

    @field_validator(
        "symbol",
        mode="before",
    )
    @classmethod
    def _validate_symbol(
        cls,
        value: Any,
    ) -> str:
        return _normalize_symbol(
            value
        )

    @field_validator(
        "qty",
        mode="before",
    )
    @classmethod
    def _validate_qty(
        cls,
        value: Any,
    ) -> float:
        result = _finite_float(
            value,
            field_name="qty",
            positive=True,
        )

        assert result is not None

        return result

    @field_validator(
        "limit_price",
        "stop_price",
        "strike",
        "multiplier",
        mode="before",
    )
    @classmethod
    def _validate_optional_positive_values(
        cls,
        value: Any,
        info,
    ) -> float | None:
        return _finite_float(
            value,
            field_name=(
                info.field_name
            ),
            allow_none=True,
            positive=True,
        )

    @field_validator(
        "time_in_force",
        mode="before",
    )
    @classmethod
    def _validate_tif(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="time_in_force",
            max_length=32,
        ).lower()

    @field_validator(
        "underlying",
        "expiration",
        mode="before",
    )
    @classmethod
    def _validate_optional_strings(
        cls,
        value: Any,
    ) -> str | None:
        return _clean_optional_text(
            value,
            max_length=128,
        )

    @field_validator(
        "base_currency",
        "quote_currency",
        mode="before",
    )
    @classmethod
    def _validate_pair_currency(
        cls,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        text = str(
            value
        ).strip()

        if not text:
            return None

        return _normalize_currency(
            text,
            field_name="currency",
        )

    @model_validator(
        mode="after",
    )
    def _validate_order_request(
        self,
    ) -> "ManualOrderRequest":
        if (
            self.order_type
            in {
                "limit",
                "stop_limit",
            }
            and self.limit_price
            is None
        ):
            raise ValueError(
                f"{self.order_type} order requires limit_price"
            )

        if (
            self.order_type
            in {
                "stop",
                "stop_limit",
            }
            and self.stop_price
            is None
        ):
            raise ValueError(
                f"{self.order_type} order requires stop_price"
            )

        if (
            self.asset_type
            == AssetType.OPTION
        ):
            if not float(
                self.qty
            ).is_integer():
                raise ValueError(
                    "Option quantity must be a whole number of contracts"
                )

            if not self.underlying:
                raise ValueError(
                    "Option order requires underlying"
                )

            if not self.expiration:
                raise ValueError(
                    "Option order requires expiration"
                )

            if self.strike is None:
                raise ValueError(
                    "Option order requires strike"
                )

            if self.option_type is None:
                raise ValueError(
                    "Option order requires option_type"
                )

        if (
            self.asset_type
            == AssetType.FOREX
        ):
            if not self.base_currency:
                raise ValueError(
                    "Forex order requires base_currency"
                )

            if not self.quote_currency:
                raise ValueError(
                    "Forex order requires quote_currency"
                )

        return self


# ============================================================
# ENGINE MODE REQUEST
# ============================================================


class EngineModeRequest(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
    )

    mode: Literal[
        "manual",
        "automatic",
    ]


# ============================================================
# AUTOMATION ASSET REQUEST
# ============================================================


class AutomationAssetStateRequest(
    BaseModel
):
    """
    Enable/disable one independent PhoenixTrend automation
    asset section.

    enabled=False means no new discovery/entries.

    It must not be interpreted as permission to abandon active
    position monitoring or risk exits.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    asset_class: Literal[
        "stocks",
        "options",
        "crypto",
        "etfs",
        "forex",
        "bonds",
    ]

    enabled: bool


# ============================================================
# MANUAL CONFIRMATION
# ============================================================


class ManualTradeConfirmation(
    BaseModel
):
    """
    Explicit user confirmation attached to a manually initiated
    execution request.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    intent_id: str

    confirmed: bool

    confirmed_at: datetime = Field(
        default_factory=utc_now
    )

    @field_validator(
        "intent_id",
        mode="before",
    )
    @classmethod
    def _validate_intent_id(
        cls,
        value: Any,
    ) -> str:
        return _clean_required_text(
            value,
            field_name="intent_id",
            max_length=128,
        )

    @field_validator(
        "confirmed_at",
    )
    @classmethod
    def _validate_confirmed_at(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                "confirmed_at must contain timezone information"
            )

        return value


# ============================================================
# EXPORTS
# ============================================================


__all__ = [
    "AccountState",
    "AlpacaConnectRequest",
    "AssetType",
    "AutomationAssetStateRequest",
    "EngineModeRequest",
    "ExecutionMode",
    "Instrument",
    "ManualOrderRequest",
    "ManualTradeConfirmation",
    "Order",
    "Position",
    "RiskDecision",
    "RiskStatus",
    "Side",
    "Signal",
    "TradeIntent",
    "utc_now",
]