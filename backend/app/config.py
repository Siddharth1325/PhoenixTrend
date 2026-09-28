from __future__ import annotations

from typing import Literal

from pydantic import (
    Field,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    """
    PhoenixTrend application configuration.

    Environment variables override these defaults.

    Important safety rules:
        - live market data does NOT enable live order execution
        - execution_env="live" alone does NOT enable live trading
        - allow_live_trading must also be explicitly enabled
        - production must not run with debug enabled
        - risk limits must always be finite and valid
        - confidence/edge values must remain within valid ranges
        - malformed safety configuration fails during application startup
          instead of silently weakening runtime protection
    """

    # ========================================================
    # APPLICATION
    # ========================================================

    app_name: str = "PhoenixTrend API"

    app_env: Literal[
        "development",
        "test",
        "production",
    ] = "development"

    debug: bool = False

    # ========================================================
    # DATABASE
    # ========================================================

    database_url: str = "sqlite:///./phoenixtrend.db"

    redis_url: str | None = None

    # ========================================================
    # EXECUTION
    # ========================================================

    execution_env: Literal[
        "paper",
        "live",
    ] = "paper"

    # This is the explicit server-side live-order permission.
    #
    # execution_env="live" does not bypass this control.
    allow_live_trading: bool = False

    # Global automation permission.
    #
    # Individual asset automation switches remain independent.
    automation_enabled: bool = True

    # ========================================================
    # RISK LIMITS
    # ========================================================

    risk_max_daily_loss: float = Field(
        default=500.0,
        gt=0.0,
    )

    risk_max_weekly_loss: float = Field(
        default=1500.0,
        gt=0.0,
    )

    risk_max_position_value: float = Field(
        default=2500.0,
        gt=0.0,
    )

    risk_max_positions: int = Field(
        default=4,
        ge=1,
    )

    # ========================================================
    # DECISION ENGINE
    # ========================================================

    # Minimum score required before PhoenixTrend considers
    # an actionable BUY / SELL decision.
    decision_min_confidence: float = Field(
        default=0.58,
        ge=0.0,
        le=1.0,
    )

    # Short cache prevents recalculating indicators and
    # patterns repeatedly while the UI is refreshing.
    decision_cache_seconds: int = Field(
        default=15,
        ge=0,
    )

    # Minimum difference between BUY and SELL score before
    # PhoenixTrend commits to a direction.
    decision_min_edge: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
    )

    # Maximum number of strategies evaluated in detail
    # after the first fast-ranking pass.
    decision_top_strategies: int = Field(
        default=5,
        ge=1,
    )

    # If no existing strategy is strong enough, allow
    # PhoenixTrend to build an Adaptive Composite strategy.
    adaptive_strategy_enabled: bool = True

    adaptive_strategy_min_confidence: float = Field(
        default=0.62,
        ge=0.0,
        le=1.0,
    )

    # ========================================================
    # MARKET DATA SAFETY
    # ========================================================

    market_data_max_age_seconds: int = Field(
        default=120,
        ge=1,
    )

    market_data_require_provider_approval: bool = True

    # ========================================================
    # LIVE MARKET DATA
    # ========================================================

    # Enables PhoenixTrend's provider-backed LIVE chart mode.
    #
    # This setting does not authorize live orders.
    live_market_data_enabled: bool = True

    # Alpaca market-data feed.
    #
    # IEX is the conservative default because SIP availability
    # depends on the connected Alpaca account's entitlement.
    alpaca_market_data_feed: Literal[
        "iex",
        "sip",
    ] = "iex"

    # If Alpaca streaming is unavailable, PhoenixTrend may use
    # the existing Yahoo provider polling path.
    #
    # Callers must preserve the real source and must not label
    # provider polling as a live broker stream.
    live_chart_fallback_to_yahoo: bool = True

    # ========================================================
    # API
    # ========================================================

    api_host: str = "0.0.0.0"

    api_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
    )

    # ========================================================
    # STRING VALIDATION
    # ========================================================

    @field_validator(
        "app_name",
        mode="before",
    )
    @classmethod
    def _validate_app_name(
        cls,
        value: object,
    ) -> str:
        if value is None:
            raise ValueError(
                "app_name cannot be empty."
            )

        normalized = str(value).strip()

        if not normalized:
            raise ValueError(
                "app_name cannot be empty."
            )

        return normalized

    @field_validator(
        "database_url",
        mode="before",
    )
    @classmethod
    def _validate_database_url(
        cls,
        value: object,
    ) -> str:
        if value is None:
            raise ValueError(
                "database_url cannot be empty."
            )

        normalized = str(value).strip()

        if not normalized:
            raise ValueError(
                "database_url cannot be empty."
            )

        return normalized

    @field_validator(
        "redis_url",
        mode="before",
    )
    @classmethod
    def _normalize_redis_url(
        cls,
        value: object,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip()

        if not normalized:
            return None

        return normalized

    @field_validator(
        "api_host",
        mode="before",
    )
    @classmethod
    def _validate_api_host(
        cls,
        value: object,
    ) -> str:
        if value is None:
            raise ValueError(
                "api_host cannot be empty."
            )

        normalized = str(value).strip()

        if not normalized:
            raise ValueError(
                "api_host cannot be empty."
            )

        return normalized

    # ========================================================
    # CROSS-FIELD SAFETY VALIDATION
    # ========================================================

    @model_validator(
        mode="after",
    )
    def _validate_runtime_safety(
        self,
    ) -> "Settings":
        if (
            self.app_env == "production"
            and self.debug
        ):
            raise ValueError(
                "debug must be disabled in production."
            )

        if (
            self.risk_max_weekly_loss
            < self.risk_max_daily_loss
        ):
            raise ValueError(
                "risk_max_weekly_loss must be greater than "
                "or equal to risk_max_daily_loss."
            )

        if (
            self.adaptive_strategy_enabled
            and self.adaptive_strategy_min_confidence
            < self.decision_min_confidence
        ):
            raise ValueError(
                "adaptive_strategy_min_confidence must be "
                "greater than or equal to "
                "decision_min_confidence."
            )

        return self

    # ========================================================
    # DERIVED EXECUTION STATE
    # ========================================================

    @property
    def live_execution_requested(
        self,
    ) -> bool:
        """
        Whether the configured execution environment points at
        live execution.

        This does not itself authorize live trading.
        """

        return self.execution_env == "live"

    @property
    def live_trading_enabled(
        self,
    ) -> bool:
        """
        Effective PhoenixTrend live-order permission.

        Both controls must explicitly permit live execution.
        """

        return (
            self.execution_env == "live"
            and self.allow_live_trading
        )

    @property
    def paper_trading_enabled(
        self,
    ) -> bool:
        return self.execution_env == "paper"

    # ========================================================
    # CONFIGURATION SUMMARY
    # ========================================================

    def public_runtime_configuration(
        self,
    ) -> dict[str, object]:
        """
        Return non-secret runtime configuration suitable for
        diagnostics/status endpoints.

        Broker credentials are intentionally not part of Settings
        and therefore cannot be exposed here.
        """

        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "debug": self.debug,
            "execution_env": self.execution_env,
            "allow_live_trading": self.allow_live_trading,
            "live_trading_enabled": self.live_trading_enabled,
            "automation_enabled": self.automation_enabled,
            "risk": {
                "max_daily_loss": self.risk_max_daily_loss,
                "max_weekly_loss": self.risk_max_weekly_loss,
                "max_position_value": self.risk_max_position_value,
                "max_positions": self.risk_max_positions,
            },
            "decision_engine": {
                "minimum_confidence": self.decision_min_confidence,
                "cache_seconds": self.decision_cache_seconds,
                "minimum_edge": self.decision_min_edge,
                "top_strategies": self.decision_top_strategies,
                "adaptive_strategy_enabled": (
                    self.adaptive_strategy_enabled
                ),
                "adaptive_strategy_min_confidence": (
                    self.adaptive_strategy_min_confidence
                ),
            },
            "market_data": {
                "max_age_seconds": (
                    self.market_data_max_age_seconds
                ),
                "require_provider_approval": (
                    self.market_data_require_provider_approval
                ),
                "live_market_data_enabled": (
                    self.live_market_data_enabled
                ),
                "alpaca_feed": (
                    self.alpaca_market_data_feed
                ),
                "fallback_to_yahoo": (
                    self.live_chart_fallback_to_yahoo
                ),
            },
            "api": {
                "host": self.api_host,
                "port": self.api_port,
            },
            "redis_configured": (
                self.redis_url is not None
            ),
        }

    # ========================================================
    # PYDANTIC SETTINGS
    # ========================================================

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        validate_default=True,
    )


settings = Settings()


__all__ = [
    "Settings",
    "settings",
]