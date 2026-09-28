from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from ..db import CustomStrategy, SessionLocal, StrategyConfiguration
from ..strategies.registry import StrategyRegistry


class StrategyManagementService:
    """
    Persistent PhoenixTrend strategy-management service.

    Responsibilities:

    - resolve registered strategy names
    - expose strategy management state
    - persist strategy configuration
    - persist strategy enabled/disabled state
    - validate configuration through StrategyRegistry
    - provide stored configuration to StrategyPicker

    This service does NOT:

    - rank strategies
    - generate signals
    - execute orders
    - start automations
    - bypass market safety
    - bypass the risk engine
    """

    def __init__(
        self,
        registry: StrategyRegistry | None = None,
    ) -> None:
        self._registry = registry or StrategyRegistry()

    # ========================================================
    # HELPERS
    # ========================================================

    def _canonical_name(
        self,
        strategy_name: str,
    ) -> str:
        return self._registry.resolve_name(
            strategy_name
        )

    @staticmethod
    def _decode_configuration(
        raw: str | None,
    ) -> dict[str, Any]:
        if not raw:
            return {}

        try:
            value = json.loads(raw)
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return {}

        if not isinstance(value, dict):
            return {}

        return value

    @staticmethod
    def _encode_configuration(
        configuration: dict[str, Any],
    ) -> str:
        try:
            return json.dumps(
                configuration,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Strategy configuration must contain "
                "JSON-compatible values."
            ) from exc

    def _find_row(
        self,
        session,
        canonical_name: str,
    ) -> StrategyConfiguration | None:
        return session.scalar(
            select(StrategyConfiguration).where(
                StrategyConfiguration.strategy_name
                == canonical_name
            )
        )

    def _get_or_create_row(
        self,
        session,
        canonical_name: str,
    ) -> StrategyConfiguration:
        row = self._find_row(
            session,
            canonical_name,
        )

        if row is not None:
            return row

        row = StrategyConfiguration(
            strategy_name=canonical_name,
            enabled=True,
            configuration="{}",
        )

        session.add(row)
        session.flush()

        return row

    # ========================================================
    # CONFIGURATION VALIDATION
    # ========================================================

    def validate_configuration(
        self,
        strategy_name: str,
        configuration: dict[str, Any] | None,
    ) -> dict[str, Any]:
        canonical_name = self._canonical_name(
            strategy_name
        )

        config = dict(
            configuration or {}
        )

        self._registry.create(
            canonical_name,
            **config,
        )

        return config

    # ========================================================
    # STORED CONFIGURATION
    # ========================================================

    def configuration_for(
        self,
        strategy_name: str,
    ) -> dict[str, Any]:
        canonical_name = self._canonical_name(
            strategy_name
        )

        with SessionLocal() as session:
            row = self._find_row(
                session,
                canonical_name,
            )

            if row is None:
                return {}

            return self._decode_configuration(
                row.configuration
            )

    # ========================================================
    # ENABLED STATE
    # ========================================================

    def is_enabled(
        self,
        strategy_name: str,
    ) -> bool:
        canonical_name = self._canonical_name(
            strategy_name
        )

        with SessionLocal() as session:
            row = self._find_row(
                session,
                canonical_name,
            )

            if row is None:
                return True

            return bool(
                row.enabled
            )

    # ========================================================
    # GET
    # ========================================================

    def get(
        self,
        strategy_name: str,
    ) -> dict[str, Any]:
        canonical_name = self._canonical_name(
            strategy_name
        )

        registry_description = (
            self._registry.describe(
                canonical_name
            )
        )

        with SessionLocal() as session:
            row = self._find_row(
                session,
                canonical_name,
            )

            if row is None:
                return {
                    **registry_description,
                    "enabled": True,
                    "configuration": {},
                    "configuration_persisted": False,
                    "created_at": None,
                    "updated_at": None,
                }

            return {
                **registry_description,
                "enabled": bool(
                    row.enabled
                ),
                "configuration": (
                    self._decode_configuration(
                        row.configuration
                    )
                ),
                "configuration_persisted": True,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    # ========================================================
    # LIST
    # ========================================================

    def list(
        self,
    ) -> list[dict[str, Any]]:
        return [
            self.get(strategy_name)
            for strategy_name
            in self._registry.list_strategies()
        ]

    # ========================================================
    # ENABLE
    # ========================================================

    def enable(
        self,
        strategy_name: str,
    ) -> dict[str, Any]:
        canonical_name = self._canonical_name(
            strategy_name
        )

        with SessionLocal() as session:
            row = self._get_or_create_row(
                session,
                canonical_name,
            )

            row.enabled = True

            session.commit()
            session.refresh(row)

        return self.get(
            canonical_name
        )

    # ========================================================
    # DISABLE
    # ========================================================

    def disable(
        self,
        strategy_name: str,
    ) -> dict[str, Any]:
        canonical_name = self._canonical_name(
            strategy_name
        )

        with SessionLocal() as session:
            row = self._get_or_create_row(
                session,
                canonical_name,
            )

            row.enabled = False

            session.commit()
            session.refresh(row)

        return self.get(
            canonical_name
        )

    # ========================================================
    # UPDATE CONFIGURATION
    # ========================================================

    def update_configuration(
        self,
        strategy_name: str,
        configuration: dict[str, Any],
        replace: bool = False,
    ) -> dict[str, Any]:
        canonical_name = self._canonical_name(
            strategy_name
        )

        if not isinstance(
            configuration,
            dict,
        ):
            raise ValueError(
                "Strategy configuration must be an object."
            )

        with SessionLocal() as session:
            row = self._get_or_create_row(
                session,
                canonical_name,
            )

            current = self._decode_configuration(
                row.configuration
            )

            if replace:
                merged = dict(
                    configuration
                )
            else:
                merged = {
                    **current,
                    **configuration,
                }

            validated = (
                self.validate_configuration(
                    canonical_name,
                    merged,
                )
            )

            row.configuration = (
                self._encode_configuration(
                    validated
                )
            )

            session.commit()
            session.refresh(row)

        return self.get(
            canonical_name
        )

    # ========================================================
    # RESET CONFIGURATION
    # ========================================================

    def reset_configuration(
        self,
        strategy_name: str,
    ) -> dict[str, Any]:
        canonical_name = self._canonical_name(
            strategy_name
        )

        with SessionLocal() as session:
            row = self._get_or_create_row(
                session,
                canonical_name,
            )

            row.configuration = "{}"

            session.commit()
            session.refresh(row)

        return self.get(
            canonical_name
        )

    # ========================================================
    # EFFECTIVE CONFIGURATION
    # ========================================================

    def effective_configuration(
        self,
        strategy_name: str,
        runtime_configuration: (
            dict[str, Any] | None
        ) = None,
    ) -> dict[str, Any]:
        """
        Merge persisted strategy configuration with an optional
        runtime override.

        Runtime configuration wins when the same field exists in
        both places.

        The final result is validated through StrategyRegistry.
        """

        canonical_name = self._canonical_name(
            strategy_name
        )

        persisted = self.configuration_for(
            canonical_name
        )

        effective = {
            **persisted,
            **(runtime_configuration or {}),
        }

        return self.validate_configuration(
            canonical_name,
            effective,
        )


    # ========================================================
    # CUSTOM STRATEGIES
    # ========================================================

    def _custom_row(self, session, name: str) -> CustomStrategy | None:
        wanted = (name or "").strip().lower()
        return session.scalar(select(CustomStrategy).where(CustomStrategy.name.ilike(wanted)))

    def custom_list(self) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = list(session.scalars(select(CustomStrategy).order_by(CustomStrategy.name)).all())
            return [self._custom_payload(row) for row in rows]

    def _custom_payload(self, row: CustomStrategy) -> dict[str, Any]:
        base = self._registry.describe(row.base_strategy)
        return {
            "name": row.name,
            "class": "CustomStrategyPreset",
            "module": "phoenixtrend.custom",
            "base_strategy": row.base_strategy,
            "custom": True,
            "enabled": bool(row.enabled),
            "configuration": self._decode_configuration(row.configuration),
            "default_configuration": base.get("default_configuration", {}),
            "editing_supported": True,
            "configuration_editable": True,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def create_custom(self, name: str, base_strategy: str, configuration: dict[str, Any] | None = None) -> dict[str, Any]:
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("Custom strategy name is required.")
        if self._registry.exists(clean_name):
            raise ValueError("Custom strategy name conflicts with a built-in strategy.")
        canonical = self._registry.resolve_name(base_strategy)
        config = self.validate_configuration(canonical, configuration or {})
        with SessionLocal() as session:
            existing = session.scalar(select(CustomStrategy).where(CustomStrategy.name == clean_name))
            if existing is not None:
                raise ValueError(f"Custom strategy '{clean_name}' already exists.")
            row = CustomStrategy(name=clean_name, base_strategy=canonical, enabled=True, configuration=self._encode_configuration(config))
            session.add(row); session.commit(); session.refresh(row)
            return self._custom_payload(row)

    def delete_custom(self, name: str) -> None:
        with SessionLocal() as session:
            row = session.scalar(select(CustomStrategy).where(CustomStrategy.name == name))
            if row is None:
                raise ValueError(f"Unknown custom strategy '{name}'.")
            session.delete(row); session.commit()

    def custom_get(self, name: str) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = session.scalar(select(CustomStrategy).where(CustomStrategy.name == name))
            return self._custom_payload(row) if row else None

    def set_custom_enabled(self, name: str, enabled: bool) -> dict[str, Any]:
        with SessionLocal() as session:
            row = session.scalar(select(CustomStrategy).where(CustomStrategy.name == name))
            if row is None:
                raise ValueError(f"Unknown custom strategy '{name}'.")
            row.enabled = enabled; session.commit(); session.refresh(row)
            return self._custom_payload(row)

    def update_custom_configuration(self, name: str, configuration: dict[str, Any]) -> dict[str, Any]:
        with SessionLocal() as session:
            row = session.scalar(select(CustomStrategy).where(CustomStrategy.name == name))
            if row is None:
                raise ValueError(f"Unknown custom strategy '{name}'.")
            current = self._decode_configuration(row.configuration)
            merged = {**current, **configuration}
            validated = self.validate_configuration(row.base_strategy, merged)
            row.configuration = self._encode_configuration(validated)
            session.commit(); session.refresh(row)
            return self._custom_payload(row)

    def reset_custom_configuration(self, name: str) -> dict[str, Any]:
        with SessionLocal() as session:
            row = session.scalar(select(CustomStrategy).where(CustomStrategy.name == name))
            if row is None:
                raise ValueError(f"Unknown custom strategy '{name}'.")
            row.configuration = "{}"
            session.commit(); session.refresh(row)
            return self._custom_payload(row)

    def create_instance(self, name: str):
        if self._registry.exists(name):
            config = self.configuration_for(name)
            return self._registry.create(name, **config)
        custom = self.custom_get(name)
        if custom is None:
            raise ValueError(f"Unknown strategy '{name}'.")
        strategy = self._registry.create(custom["base_strategy"], **custom["configuration"])
        strategy.name = custom["name"]
        return strategy

    def all_names(self) -> list[str]:
        return self._registry.list_strategies() + [item["name"] for item in self.custom_list()]

    def enabled_for(self, name: str) -> bool:
        if self._registry.exists(name):
            return self.is_enabled(name)
        custom = self.custom_get(name)
        return bool(custom and custom["enabled"])


strategy_management_service = (
    StrategyManagementService()
)