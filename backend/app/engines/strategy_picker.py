from __future__ import annotations

from typing import Any

from ..strategies.base import Strategy
from ..strategies.registry import StrategyRegistry


class StrategyPicker:
    """
    PhoenixTrend explicit strategy picker.

    Used when a user or automation explicitly chooses a
    registered strategy.

    Responsibilities:

    - list registered strategies
    - validate strategy names
    - resolve aliases/names
    - create fresh strategy instances
    - apply persisted strategy configuration
    - expose strategy metadata

    StrategyPicker does NOT:

    - analyze market conditions
    - rank strategies
    - select the best market strategy
    - generate adaptive strategies
    - execute trades

    Automatic market-based ranking belongs to
    StrategySelector.
    """

    def __init__(
        self,
        registry: StrategyRegistry | None = None,
    ) -> None:
        self._registry = (
            registry
            or StrategyRegistry()
        )

    # ========================================================
    # MANAGEMENT SERVICE
    # ========================================================

    @staticmethod
    def _management():
        """
        Import lazily to avoid a circular import between the
        strategy-management service and StrategyPicker.
        """

        from ..services.strategy_management import (
            strategy_management_service,
        )

        return strategy_management_service

    # ========================================================
    # AVAILABLE
    # ========================================================

    def available_strategies(
        self,
        enabled_only: bool = False,
    ) -> list[str]:
        strategies = self._management().all_names()

        if not enabled_only:
            return strategies

        management = self._management()

        return [
            strategy_name
            for strategy_name in strategies
            if management.enabled_for(
                strategy_name
            )
        ]

    # ========================================================
    # EXISTS
    # ========================================================

    def exists(
        self,
        strategy_name: str,
    ) -> bool:
        if not strategy_name:
            return False

        return self._registry.exists(strategy_name) or self._management().custom_get(strategy_name) is not None

    # ========================================================
    # RESOLVE NAME
    # ========================================================

    def resolve_name(
        self,
        strategy_name: str,
    ) -> str:
        if not strategy_name:
            raise ValueError(
                "Strategy name is required"
            )

        if self._registry.exists(strategy_name):
            return self._registry.resolve_name(strategy_name)
        custom = self._management().custom_get(strategy_name)
        if custom is not None:
            return custom["name"]
        raise ValueError(f"Unknown strategy '{strategy_name}'.")

    # ========================================================
    # ENABLED
    # ========================================================

    def is_enabled(
        self,
        strategy_name: str,
    ) -> bool:
        canonical_name = (
            self.resolve_name(
                strategy_name
            )
        )

        return self._management().enabled_for(
            canonical_name
        )

    # ========================================================
    # CONFIGURATION
    # ========================================================

    def configuration(
        self,
        strategy_name: str,
    ) -> dict[str, Any]:
        canonical_name = (
            self.resolve_name(
                strategy_name
            )
        )

        management = self._management()
        custom = management.custom_get(canonical_name)
        if custom is not None:
            return dict(custom.get("configuration") or {})

        return management.configuration_for(canonical_name)

    # ========================================================
    # PICK
    # ========================================================

    def pick(
        self,
        strategy_name: str,
        config: dict[str, Any] | None = None,
        require_enabled: bool = False,
    ) -> Strategy:
        """
        Create a fresh strategy instance.

        Persisted strategy configuration is loaded first.

        Optional runtime configuration is then applied on top,
        so an explicit runtime override takes precedence.

        StrategyRegistry remains the authoritative factory and
        validates every configuration field.

        require_enabled should be True when the caller is
        attempting to use a strategy for an enabled/automatic
        workflow.
        """

        canonical_name = (
            self.resolve_name(
                strategy_name
            )
        )

        management = self._management()

        if (
            require_enabled
            and not management.enabled_for(
                canonical_name
            )
        ):
            raise ValueError(
                f"Strategy '{canonical_name}' is disabled."
            )

        if self._registry.exists(canonical_name):
            effective_config = management.effective_configuration(canonical_name, config)
            return self._registry.create(canonical_name, **effective_config)

        strategy = management.create_instance(canonical_name)
        for key, value in (config or {}).items():
            if not hasattr(strategy, key):
                raise ValueError(f"Strategy '{canonical_name}' does not support configuration field '{key}'.")
            setattr(strategy, key, value)
        return strategy

    # ========================================================
    # DESCRIBE
    # ========================================================

    def describe(
        self,
        strategy_name: str,
    ) -> dict[str, Any]:
        canonical_name = (
            self.resolve_name(
                strategy_name
            )
        )

        management = self._management()

        custom = management.custom_get(canonical_name)
        if custom is not None:
            return {
                **custom,
                "description": custom.get("summary")
                or (
                    f"Custom strategy based on "
                    f"{custom.get('base_strategy')}"
                ),
                "engine_support": [
                    "manual",
                    "automatic",
                ],
                "registered": True,
            }

        strategy = self.pick(
            canonical_name
        )

        registry_description = (
            self._registry.describe(
                canonical_name
            )
        )

        return {
            **registry_description,
            "name": strategy.name,
            "description": (
                registry_description.get(
                    "summary"
                )
                or (
                    f"{strategy.name} systematic "
                    "PhoenixTrend strategy."
                )
            ),
            "engine_support": [
                "manual",
                "automatic",
            ],
            "registered": True,
            "enabled": (
                management.enabled_for(
                    canonical_name
                )
            ),
            "configuration": (
                management.configuration_for(
                    canonical_name
                )
            ),
        }

    # ========================================================
    # CATALOG
    # ========================================================

    def catalog(
        self,
    ) -> list[dict[str, Any]]:
        return [
            self.describe(
                strategy_name
            )
            for strategy_name
            in self.available_strategies()
        ]