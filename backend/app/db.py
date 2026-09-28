from __future__ import annotations

from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

from .config import settings


# ============================================================
# HELPERS
# ============================================================


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# BASE
# ============================================================


class Base(DeclarativeBase):
    pass


# ============================================================
# USER ACCOUNTS
# ============================================================


class UserAccount(Base):
    """
    PhoenixTrend application user.

    Passwords are never stored directly. password_hash contains
    only the password hash produced by AuthService.

    UserAccount is the ownership root for user-scoped
    PhoenixTrend data.
    """

    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )

    username: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        index=True,
        nullable=False,
    )

    display_name: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
        default="",
    )

    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


# ============================================================
# AUTH SESSIONS
# ============================================================


class AuthSession(Base):
    """
    Opaque bearer-token session.

    Only the SHA-256 token digest is persisted.

    Sessions are explicitly owned by a UserAccount.
    """

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "user_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )


# ============================================================
# AUDIT EVENTS
# ============================================================


class AuditEvent(Base):
    """
    Immutable-style PhoenixTrend activity/audit event.

    AuditEvent records genuine PhoenixTrend activity such as:

        login
        logout
        broker connection changes
        analysis
        pattern detection
        strategy selection
        automation ON/OFF
        emergency stop
        trade intent
        market-safety decision
        risk decision
        manual confirmation
        broker submission
        order result
        fill/rejection
        position close
        runtime failure

    Audit records are user-scoped.

    detail is serialized text produced by AuditService. Secrets,
    bearer tokens and broker credentials must never be written
    into this table.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "user_accounts.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    entity_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    detail: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )


# ============================================================
# TRADE RECORDS
# ============================================================


class TradeRecord(Base):
    """
    Persistent PhoenixTrend trade/execution record.

    A TradeRecord represents one genuine trade lifecycle:

        strategy signal
            ->
        trade intent
            ->
        market safety
            ->
        risk authorization
            ->
        broker entry order
            ->
        broker entry fill
            ->
        open position
            ->
        broker exit order
            ->
        broker exit fill
            ->
        realized P&L

    IMPORTANT:

    broker_order_id stores the ENTRY broker order ID.

    exit_broker_order_id stores the EXIT broker order ID.

    entry_price and exit_price must come from genuine broker
    execution/fill information.

    pnl must only be populated after a genuine closing
    execution has been confirmed.

    Analysis that does not result in an actual broker trade
    belongs in AuditEvent instead.

    Every trade belongs to one authenticated PhoenixTrend user.
    """

    __tablename__ = "trade_records"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # --------------------------------------------------------
    # OWNERSHIP
    # --------------------------------------------------------

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "user_accounts.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # --------------------------------------------------------
    # PHOENIXTREND IDS
    # --------------------------------------------------------

    intent_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        index=True,
    )

    automation_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    # --------------------------------------------------------
    # BROKER
    # --------------------------------------------------------

    broker: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    # Genuine entry broker order ID.
    broker_order_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    # Genuine broker order that closes this trade.
    exit_broker_order_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    # --------------------------------------------------------
    # INSTRUMENT
    # --------------------------------------------------------

    symbol: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    asset_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="EQUITY",
        index=True,
    )

    # --------------------------------------------------------
    # STRATEGY / ENGINE
    # --------------------------------------------------------

    strategy: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    execution_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="CONTROLLED",
        index=True,
    )

    # --------------------------------------------------------
    # ORDER
    # --------------------------------------------------------

    side: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
    )

    qty: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    order_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="market",
    )

    time_in_force: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="day",
    )

    reference_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Genuine broker entry fill price.
    entry_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Genuine broker exit fill price.
    exit_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # --------------------------------------------------------
    # RISK / EXIT LEVELS
    # --------------------------------------------------------

    stop: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    target: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    max_loss: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # --------------------------------------------------------
    # PERFORMANCE
    # --------------------------------------------------------

    # Realized P&L only.
    pnl: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="CREATED",
        index=True,
    )

    # --------------------------------------------------------
    # TIMESTAMPS
    # --------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )


# ============================================================
# AUTOMATION DEFINITIONS
# ============================================================


class AutomationRecord(Base):
    """
    Persistent PhoenixTrend automatic-trading definition.

    This table stores user configuration only.

    Runtime state is intentionally not persisted as "running"
    because a process restart must never cause PhoenixTrend to
    pretend an automatic engine is still alive.

    enabled represents configuration permission for new
    discovery/entries. Turning it OFF must not be interpreted
    by runtime code as permission to abandon already-open
    positions. Existing positions continue through the shared
    monitoring/risk/exit pipeline.

    No prices, fills, P&L, opportunities or generated trading
    activity are fabricated by this model.
    """

    __tablename__ = "automation_records"

    id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    # --------------------------------------------------------
    # OWNERSHIP
    # --------------------------------------------------------

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "user_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    strategy: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    # JSON list of configured symbols.
    symbols: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="AUTOMATIC",
        index=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    # When True, no new entries may be created while position
    # monitoring and exits remain active.
    entries_paused: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    auto_select_strategy: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    # --------------------------------------------------------
    # ASSET / STYLE
    # --------------------------------------------------------

    asset_class: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="stocks",
        index=True,
    )

    trading_style: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="intraday",
        index=True,
    )

    # --------------------------------------------------------
    # CAPITAL / RISK CONFIGURATION
    # --------------------------------------------------------

    max_position_value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    capital_allocation: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    max_daily_loss: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    max_open_positions: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    allow_long: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    allow_short: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Asset/strategy-specific configuration as JSON text.
    configuration: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


# ============================================================
# AUTOMATION ASSET CONFIGURATION
# ============================================================


class AutomationAssetConfiguration(Base):
    """
    Persistent configuration for an automatic-trading asset
    section.

    Examples:

        stocks
        options
        crypto
        etfs
        forex
        bonds

    Configuration is isolated per PhoenixTrend user.

    The model stores configuration only. It does not imply that
    the currently connected broker supports the asset class.
    Broker capability must be checked at runtime before enabling
    or starting new discovery/entries.

    OFF means:
        - stop new discovery/entries for this asset section
        - do not abandon existing positions
        - continue monitoring/risk/exit handling until positions
          are safely drained
    """

    __tablename__ = "automation_asset_configurations"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "asset_class",
            name="uq_automation_asset_configuration_user_asset",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "user_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    asset_class: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    trading_style: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="intraday",
        index=True,
    )

    symbols: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    strategy: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    auto_select_strategy: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    max_position_value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    capital_allocation: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    max_daily_loss: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    max_open_positions: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    allow_long: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    allow_short: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    configuration: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


# ============================================================
# STRATEGY CONFIGURATION
# ============================================================


class StrategyConfiguration(Base):
    """
    Persistent configuration for a registered PhoenixTrend
    strategy.

    Strategy settings are isolated per user.

    This table stores configuration only.

    It does NOT:
        - place trades
        - bypass StrategyRegistry validation
        - bypass StrategySelector
        - bypass DecisionEngine
        - bypass MarketSafety
        - bypass RiskEngine
        - bypass ExecutionService

    Configuration is stored as JSON text because each strategy
    can expose a different configuration schema.

    StrategyRegistry remains responsible for validating whether
    a configuration field is supported by the implementation.
    """

    __tablename__ = "strategy_configurations"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "strategy_name",
            name="uq_strategy_configuration_user_name",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "user_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    strategy_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    configuration: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


# ============================================================
# CUSTOM STRATEGIES
# ============================================================


class CustomStrategy(Base):
    """
    User-created strategy preset backed by a registered
    PhoenixTrend strategy implementation.

    Names are unique within one user account rather than
    globally across every PhoenixTrend account.
    """

    __tablename__ = "custom_strategies"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "name",
            name="uq_custom_strategy_user_name",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "user_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    base_strategy: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    configuration: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


# ============================================================
# DATABASE ENGINE
# ============================================================


connect_args = (
    {
        "check_same_thread": False,
    }
    if settings.database_url.startswith(
        "sqlite"
    )
    else {}
)


engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)


# ============================================================
# SESSION FACTORY
# ============================================================


SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


# ============================================================
# SQLITE IDENTIFIER SAFETY
# ============================================================


def _sqlite_identifier(
    value: str,
) -> str:
    """
    Validate identifiers used by compatibility migration SQL.

    Table/index/column identifiers in this module are internal
    constants, but validation prevents accidental unsafe future
    use of these helpers.
    """

    text = str(value or "").strip()

    if not text:
        raise ValueError(
            "SQLite identifier cannot be empty."
        )

    if not all(
        character.isalnum()
        or character == "_"
        for character in text
    ):
        raise ValueError(
            f"Unsafe SQLite identifier: {text!r}"
        )

    return text


# ============================================================
# SQLITE MIGRATION HELPERS
# ============================================================


def _sqlite_columns(
    table_name: str,
) -> set[str]:
    if engine.dialect.name != "sqlite":
        return set()

    table = _sqlite_identifier(
        table_name
    )

    with engine.begin() as connection:
        rows = connection.exec_driver_sql(
            f"PRAGMA table_info({table})"
        ).fetchall()

    return {
        str(row[1])
        for row in rows
    }


def _sqlite_indexes(
    table_name: str,
) -> dict[str, dict[str, object]]:
    if engine.dialect.name != "sqlite":
        return {}

    table = _sqlite_identifier(
        table_name
    )

    with engine.begin() as connection:
        rows = connection.exec_driver_sql(
            f"PRAGMA index_list({table})"
        ).fetchall()

        output: dict[
            str,
            dict[str, object],
        ] = {}

        for row in rows:
            index_name = str(
                row[1]
            )

            safe_index = _sqlite_identifier(
                index_name
            )

            info_rows = connection.exec_driver_sql(
                f"PRAGMA index_info({safe_index})"
            ).fetchall()

            output[index_name] = {
                "unique": bool(
                    row[2]
                ),
                "columns": [
                    str(info[2])
                    for info in info_rows
                ],
            }

    return output


def _sqlite_add_column(
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    if engine.dialect.name != "sqlite":
        return

    table = _sqlite_identifier(
        table_name
    )

    column = _sqlite_identifier(
        column_name
    )

    existing_columns = _sqlite_columns(
        table
    )

    if not existing_columns:
        return

    if column in existing_columns:
        return

    allowed_definitions = {
        "INTEGER",
        "INTEGER NULL",
        "VARCHAR(128)",
        "VARCHAR(64)",
        "VARCHAR(32)",
        "FLOAT",
        "DATETIME",
        "TEXT",
        "TEXT NOT NULL DEFAULT '[]'",
        "TEXT NOT NULL DEFAULT '{}'",
        "VARCHAR(32) NOT NULL DEFAULT 'AUTOMATIC'",
        "VARCHAR(32) NOT NULL DEFAULT 'stocks'",
        "VARCHAR(32) NOT NULL DEFAULT 'intraday'",
        "BOOLEAN NOT NULL DEFAULT 0",
        "BOOLEAN NOT NULL DEFAULT 1",
    }

    normalized_definition = str(
        definition
    ).strip()

    if normalized_definition not in allowed_definitions:
        raise ValueError(
            "Unsupported SQLite migration column definition: "
            f"{normalized_definition}"
        )

    with engine.begin() as connection:
        connection.exec_driver_sql(
            (
                f"ALTER TABLE {table} "
                f"ADD COLUMN {column} "
                f"{normalized_definition}"
            )
        )


def _sqlite_create_index(
    index_name: str,
    table_name: str,
    columns: str,
    *,
    unique: bool = False,
) -> None:
    if engine.dialect.name != "sqlite":
        return

    index = _sqlite_identifier(
        index_name
    )

    table = _sqlite_identifier(
        table_name
    )

    column_names = [
        _sqlite_identifier(
            item.strip()
        )
        for item in str(
            columns
        ).split(",")
        if item.strip()
    ]

    if not column_names:
        raise ValueError(
            "SQLite index must contain at least one column."
        )

    column_sql = ", ".join(
        column_names
    )

    unique_sql = (
        "UNIQUE "
        if unique
        else ""
    )

    with engine.begin() as connection:
        connection.exec_driver_sql(
            (
                f"CREATE {unique_sql}INDEX IF NOT EXISTS "
                f"{index} "
                f"ON {table} ({column_sql})"
            )
        )


def _sqlite_drop_index(
    index_name: str,
) -> None:
    if engine.dialect.name != "sqlite":
        return

    index = _sqlite_identifier(
        index_name
    )

    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"DROP INDEX IF EXISTS {index}"
        )


# ============================================================
# USER / AUTH MIGRATIONS
# ============================================================


def _ensure_auth_columns() -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(
        engine
    )

    if inspector.has_table(
        "auth_sessions"
    ):
        _sqlite_create_index(
            "ix_auth_sessions_user_id",
            "auth_sessions",
            "user_id",
        )

        _sqlite_create_index(
            "ix_auth_sessions_expires_at",
            "auth_sessions",
            "expires_at",
        )

        _sqlite_create_index(
            "ix_auth_sessions_revoked",
            "auth_sessions",
            "revoked",
        )

    if inspector.has_table(
        "user_accounts"
    ):
        _sqlite_create_index(
            "ix_user_accounts_is_active",
            "user_accounts",
            "is_active",
        )

        _sqlite_create_index(
            "ix_user_accounts_created_at",
            "user_accounts",
            "created_at",
        )


# ============================================================
# AUDIT EVENT MIGRATIONS
# ============================================================


def _ensure_audit_event_columns() -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(
        engine
    )

    if not inspector.has_table(
        "audit_events"
    ):
        return

    _sqlite_add_column(
        "audit_events",
        "user_id",
        "INTEGER",
    )

    _sqlite_create_index(
        "ix_audit_events_user_id",
        "audit_events",
        "user_id",
    )


# ============================================================
# TRADE RECORD MIGRATIONS
# ============================================================


def _ensure_trade_record_columns() -> None:
    """
    Apply compatibility migrations for existing SQLite
    trade_records tables.

    No market values, fill values, P&L or broker state are
    fabricated.

    Existing rows receive NULL for newly introduced ownership
    columns. Ownership must never be guessed during migration.
    """

    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(
        engine
    )

    if not inspector.has_table(
        "trade_records"
    ):
        return

    _sqlite_add_column(
        "trade_records",
        "user_id",
        "INTEGER",
    )

    _sqlite_add_column(
        "trade_records",
        "exit_broker_order_id",
        "VARCHAR(128)",
    )

    _sqlite_create_index(
        "ix_trade_records_user_id",
        "trade_records",
        "user_id",
    )

    _sqlite_create_index(
        "ix_trade_records_exit_broker_order_id",
        "trade_records",
        "exit_broker_order_id",
    )

    _sqlite_create_index(
        "ix_trade_records_opened_at",
        "trade_records",
        "opened_at",
    )

    _sqlite_create_index(
        "ix_trade_records_closed_at",
        "trade_records",
        "closed_at",
    )


# ============================================================
# AUTOMATION RECORD MIGRATIONS
# ============================================================


def _ensure_automation_record_columns() -> None:
    """
    Compatibility migration for automation_records.

    New installations receive the complete table from
    create_all().

    Existing SQLite installations receive missing configuration
    and ownership columns only.

    Existing rows are not assigned to an arbitrary user.
    user_id remains NULL until ownership is established by
    application-level migration/account reconciliation.

    Runtime activity is never fabricated.
    """

    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(
        engine
    )

    if not inspector.has_table(
        "automation_records"
    ):
        return

    columns = (
        (
            "user_id",
            "INTEGER",
        ),
        (
            "strategy",
            "VARCHAR(128)",
        ),
        (
            "symbols",
            "TEXT NOT NULL DEFAULT '[]'",
        ),
        (
            "mode",
            "VARCHAR(32) NOT NULL DEFAULT 'AUTOMATIC'",
        ),
        (
            "enabled",
            "BOOLEAN NOT NULL DEFAULT 0",
        ),
        (
            "entries_paused",
            "BOOLEAN NOT NULL DEFAULT 0",
        ),
        (
            "auto_select_strategy",
            "BOOLEAN NOT NULL DEFAULT 1",
        ),
        (
            "asset_class",
            "VARCHAR(32) NOT NULL DEFAULT 'stocks'",
        ),
        (
            "trading_style",
            "VARCHAR(32) NOT NULL DEFAULT 'intraday'",
        ),
        (
            "max_position_value",
            "FLOAT",
        ),
        (
            "capital_allocation",
            "FLOAT",
        ),
        (
            "max_daily_loss",
            "FLOAT",
        ),
        (
            "max_open_positions",
            "INTEGER",
        ),
        (
            "allow_long",
            "BOOLEAN NOT NULL DEFAULT 1",
        ),
        (
            "allow_short",
            "BOOLEAN NOT NULL DEFAULT 0",
        ),
        (
            "configuration",
            "TEXT NOT NULL DEFAULT '{}'",
        ),
        (
            "created_at",
            "DATETIME",
        ),
        (
            "updated_at",
            "DATETIME",
        ),
    )

    for column_name, definition in columns:
        _sqlite_add_column(
            "automation_records",
            column_name,
            definition,
        )

    _sqlite_create_index(
        "ix_automation_records_user_id",
        "automation_records",
        "user_id",
    )

    _sqlite_create_index(
        "ix_automation_records_name",
        "automation_records",
        "name",
    )

    _sqlite_create_index(
        "ix_automation_records_strategy",
        "automation_records",
        "strategy",
    )

    _sqlite_create_index(
        "ix_automation_records_mode",
        "automation_records",
        "mode",
    )

    _sqlite_create_index(
        "ix_automation_records_enabled",
        "automation_records",
        "enabled",
    )

    _sqlite_create_index(
        "ix_automation_records_entries_paused",
        "automation_records",
        "entries_paused",
    )

    _sqlite_create_index(
        "ix_automation_records_asset_class",
        "automation_records",
        "asset_class",
    )

    _sqlite_create_index(
        "ix_automation_records_trading_style",
        "automation_records",
        "trading_style",
    )

    _sqlite_create_index(
        "ix_automation_records_created_at",
        "automation_records",
        "created_at",
    )


# ============================================================
# AUTOMATION ASSET CONFIGURATION MIGRATIONS
# ============================================================


def _ensure_automation_asset_configuration_columns() -> None:
    """
    Add user ownership and current automation configuration
    columns to existing SQLite databases.

    The historical global unique index on asset_class is removed
    when present because configuration is now isolated by:

        user_id + asset_class

    Existing rows retain NULL user_id. Ownership is never
    guessed.
    """

    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(
        engine
    )

    if not inspector.has_table(
        "automation_asset_configurations"
    ):
        return

    columns = (
        (
            "user_id",
            "INTEGER",
        ),
        (
            "enabled",
            "BOOLEAN NOT NULL DEFAULT 0",
        ),
        (
            "trading_style",
            "VARCHAR(32) NOT NULL DEFAULT 'intraday'",
        ),
        (
            "symbols",
            "TEXT NOT NULL DEFAULT '[]'",
        ),
        (
            "strategy",
            "VARCHAR(128)",
        ),
        (
            "auto_select_strategy",
            "BOOLEAN NOT NULL DEFAULT 1",
        ),
        (
            "max_position_value",
            "FLOAT",
        ),
        (
            "capital_allocation",
            "FLOAT",
        ),
        (
            "max_daily_loss",
            "FLOAT",
        ),
        (
            "max_open_positions",
            "INTEGER",
        ),
        (
            "allow_long",
            "BOOLEAN NOT NULL DEFAULT 1",
        ),
        (
            "allow_short",
            "BOOLEAN NOT NULL DEFAULT 0",
        ),
        (
            "configuration",
            "TEXT NOT NULL DEFAULT '{}'",
        ),
        (
            "created_at",
            "DATETIME",
        ),
        (
            "updated_at",
            "DATETIME",
        ),
    )

    for column_name, definition in columns:
        _sqlite_add_column(
            "automation_asset_configurations",
            column_name,
            definition,
        )

    indexes = _sqlite_indexes(
        "automation_asset_configurations"
    )

    for index_name, metadata in indexes.items():
        columns_value = metadata.get(
            "columns"
        )

        unique_value = metadata.get(
            "unique"
        )

        if (
            unique_value is True
            and columns_value
            == ["asset_class"]
            and not index_name.startswith(
                "sqlite_autoindex_"
            )
        ):
            _sqlite_drop_index(
                index_name
            )

    _sqlite_create_index(
        "ix_automation_asset_configurations_user_id",
        "automation_asset_configurations",
        "user_id",
    )

    _sqlite_create_index(
        "ix_automation_asset_configurations_asset_class",
        "automation_asset_configurations",
        "asset_class",
    )

    _sqlite_create_index(
        "ix_automation_asset_configurations_enabled",
        "automation_asset_configurations",
        "enabled",
    )

    _sqlite_create_index(
        "ix_automation_asset_configurations_trading_style",
        "automation_asset_configurations",
        "trading_style",
    )

    # SQLite permits multiple NULL values in a unique index.
    # This preserves legacy unowned rows without assigning them
    # to an arbitrary account.
    _sqlite_create_index(
        "uq_automation_asset_configuration_user_asset",
        "automation_asset_configurations",
        "user_id, asset_class",
        unique=True,
    )


# ============================================================
# STRATEGY CONFIGURATION MIGRATIONS
# ============================================================


def _ensure_strategy_configuration_columns() -> None:
    """
    Convert strategy configuration ownership from global to
    per-user configuration without fabricating ownership.

    Existing rows remain user_id=NULL until explicitly migrated.
    """

    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(
        engine
    )

    if not inspector.has_table(
        "strategy_configurations"
    ):
        return

    _sqlite_add_column(
        "strategy_configurations",
        "user_id",
        "INTEGER",
    )

    indexes = _sqlite_indexes(
        "strategy_configurations"
    )

    for index_name, metadata in indexes.items():
        columns_value = metadata.get(
            "columns"
        )

        unique_value = metadata.get(
            "unique"
        )

        if (
            unique_value is True
            and columns_value
            == ["strategy_name"]
            and not index_name.startswith(
                "sqlite_autoindex_"
            )
        ):
            _sqlite_drop_index(
                index_name
            )

    _sqlite_create_index(
        "ix_strategy_configurations_user_id",
        "strategy_configurations",
        "user_id",
    )

    _sqlite_create_index(
        "ix_strategy_configurations_strategy_name",
        "strategy_configurations",
        "strategy_name",
    )

    _sqlite_create_index(
        "uq_strategy_configuration_user_name",
        "strategy_configurations",
        "user_id, strategy_name",
        unique=True,
    )


# ============================================================
# CUSTOM STRATEGY MIGRATIONS
# ============================================================


def _ensure_custom_strategy_columns() -> None:
    """
    Convert custom strategy ownership from global to per-user.

    Existing custom strategies are not automatically assigned
    to an arbitrary user.
    """

    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(
        engine
    )

    if not inspector.has_table(
        "custom_strategies"
    ):
        return

    _sqlite_add_column(
        "custom_strategies",
        "user_id",
        "INTEGER",
    )

    indexes = _sqlite_indexes(
        "custom_strategies"
    )

    for index_name, metadata in indexes.items():
        columns_value = metadata.get(
            "columns"
        )

        unique_value = metadata.get(
            "unique"
        )

        if (
            unique_value is True
            and columns_value
            == ["name"]
            and not index_name.startswith(
                "sqlite_autoindex_"
            )
        ):
            _sqlite_drop_index(
                index_name
            )

    _sqlite_create_index(
        "ix_custom_strategies_user_id",
        "custom_strategies",
        "user_id",
    )

    _sqlite_create_index(
        "ix_custom_strategies_name",
        "custom_strategies",
        "name",
    )

    _sqlite_create_index(
        "uq_custom_strategy_user_name",
        "custom_strategies",
        "user_id, name",
        unique=True,
    )


# ============================================================
# SQLITE LEGACY UNIQUE-CONSTRAINT WARNING
# ============================================================


def _sqlite_validate_legacy_uniqueness() -> None:
    """
    Detect legacy SQLite autoindexes that cannot safely be
    removed with DROP INDEX.

    SQLite automatically creates sqlite_autoindex_* indexes for
    table-level UNIQUE constraints. Those indexes cannot be
    dropped directly.

    We deliberately do not rebuild tables automatically here
    because doing so during application startup could destroy or
    incorrectly reassign existing user data.

    Application queries must use user_id once account isolation
    is enabled. A formal schema migration should rebuild legacy
    tables if they were originally created with global UNIQUE
    constraints.
    """

    if engine.dialect.name != "sqlite":
        return

    tables = (
        (
            "automation_asset_configurations",
            ["asset_class"],
        ),
        (
            "strategy_configurations",
            ["strategy_name"],
        ),
        (
            "custom_strategies",
            ["name"],
        ),
    )

    for table_name, legacy_columns in tables:
        inspector = inspect(
            engine
        )

        if not inspector.has_table(
            table_name
        ):
            continue

        indexes = _sqlite_indexes(
            table_name
        )

        for index_name, metadata in indexes.items():
            if not index_name.startswith(
                "sqlite_autoindex_"
            ):
                continue

            if (
                metadata.get(
                    "unique"
                )
                is True
                and metadata.get(
                    "columns"
                )
                == legacy_columns
            ):
                # No mutation is performed. Rebuilding an
                # existing table automatically at startup would
                # be unsafe. This condition can be inspected by
                # migration tooling and resolved explicitly.
                break


# ============================================================
# INITIALIZATION
# ============================================================


def init_db() -> None:
    """
    Initialize the PhoenixTrend database.

    New databases receive the complete current schema.

    Existing SQLite databases are preserved and receive only
    explicitly defined compatibility migrations.

    Ownership is never guessed.

    No migration creates fake:
        - users
        - trades
        - fills
        - prices
        - P&L
        - runtime activity
        - broker state
        - strategy results
        - market data
    """

    Base.metadata.create_all(
        bind=engine
    )

    _ensure_auth_columns()
    _ensure_audit_event_columns()
    _ensure_trade_record_columns()
    _ensure_automation_record_columns()
    _ensure_automation_asset_configuration_columns()
    _ensure_strategy_configuration_columns()
    _ensure_custom_strategy_columns()
    _sqlite_validate_legacy_uniqueness()


# ============================================================
# FASTAPI DB DEPENDENCY
# ============================================================


def get_db() -> Generator[
    Session,
    None,
    None,
]:
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# ============================================================
# EXPORTS
# ============================================================


__all__ = [
    "AuditEvent",
    "AuthSession",
    "AutomationAssetConfiguration",
    "AutomationRecord",
    "Base",
    "CustomStrategy",
    "SessionLocal",
    "StrategyConfiguration",
    "TradeRecord",
    "UserAccount",
    "engine",
    "get_db",
    "init_db",
    "utc_now",
]