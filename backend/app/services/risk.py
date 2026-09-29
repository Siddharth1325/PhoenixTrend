from __future__ import annotations

from math import isfinite
from typing import Any

from ..config import settings
from ..domain import (
    AccountState,
    AssetType,
    ExecutionMode,
    RiskDecision,
    RiskStatus,
    Side,
    TradeIntent,
)


class RiskEngine:
    """
    PhoenixTrend account/trade risk gate.

    Risk answers:

        "Is this TradeIntent allowed to proceed?"

    Risk does NOT:
        - generate market signals
        - select strategies
        - validate market-data freshness
        - submit orders
        - talk directly to brokers
        - fabricate account values
        - fabricate option multipliers
        - assume missing P&L/exposure values are zero

    Market Safety must run separately for unattended automatic execution.

    Execution remains responsible for:
        - broker capability validation
        - order-type capability validation
        - broker submission
        - persistence
        - reconciliation
        - audit/activity events
    """

    MIN_RISK_REWARD = 1.0

    # ============================================================
    # AUTOMATION SAFETY OVERRIDES
    # ============================================================

    @staticmethod
    def _strictest_positive(
        *values: Any,
    ) -> float | None:
        parsed: list[float] = []

        for value in values:
            if value is None:
                continue

            try:
                number = float(value)
            except (TypeError, ValueError):
                continue

            if isfinite(number) and number > 0:
                parsed.append(number)

        return min(parsed) if parsed else None

    @staticmethod
    def _strictest_positive_int(
        *values: Any,
    ) -> int | None:
        parsed: list[int] = []

        for value in values:
            if value is None:
                continue

            try:
                number = int(value)
            except (TypeError, ValueError):
                continue

            if number > 0:
                parsed.append(number)

        return min(parsed) if parsed else None

    @staticmethod
    def _automation_safety_limits(
        asset_type: AssetType,
    ) -> dict[str, Any]:
        sections = {
            AssetType.EQUITY: "stocks",
            AssetType.ETF: "etfs",
            AssetType.OPTION: "options",
            AssetType.CRYPTO: "crypto",
            AssetType.FOREX: "forex",
            AssetType.BOND: "bonds",
        }

        section = sections.get(asset_type)

        if section is None:
            return {}

        try:
            from .automation import automation_engine

            configuration = (
                automation_engine
                .section_configuration(
                    section
                )
            )
        except Exception:
            return {}

        if not configuration.get(
            "configured"
        ):
            return {}

        return configuration

    # ============================================================
    # PUBLIC EVALUATION
    # ============================================================

    def evaluate(
        self,
        intent: TradeIntent,
        account: AccountState,
        automation_enabled: bool = True,
    ) -> RiskDecision:
        reasons: list[str] = []

        if intent is None:
            return self._reject(
                "Trade intent is required"
            )

        if account is None:
            return self._reject(
                "Account state is required"
            )

        # ========================================================
        # EXECUTION MODE
        # ========================================================

        execution_mode = getattr(
            intent,
            "execution_mode",
            None,
        )

        if execution_mode is None:
            reasons.append(
                "Trade intent execution mode is required"
            )

        # ========================================================
        # SIDE
        # ========================================================

        side = getattr(
            intent,
            "side",
            None,
        )

        if side not in {
            Side.BUY,
            Side.SELL,
        }:
            reasons.append(
                "Trade intent side must be BUY or SELL"
            )

        # ========================================================
        # BASIC INTENT VALUES
        # ========================================================

        qty = self._required_positive_number(
            getattr(
                intent,
                "qty",
                None,
            ),
            "Order quantity",
            reasons,
        )

        reference_price = (
            self._required_positive_number(
                getattr(
                    intent,
                    "reference_price",
                    None,
                ),
                "Reference price",
                reasons,
            )
        )

        notional: float | None = None

        if (
            qty is not None
            and reference_price is not None
        ):
            notional = (
                qty
                * reference_price
            )

            if not isfinite(notional):
                reasons.append(
                    "Order notional is not finite"
                )

                notional = None

            elif notional <= 0:
                reasons.append(
                    "Order notional must be greater than zero"
                )

                notional = None

        # ========================================================
        # AUTOMATION PERMISSION
        # ========================================================

        if (
            execution_mode
            == ExecutionMode.AUTOMATIC
            and not automation_enabled
        ):
            reasons.append(
                "Automatic trading permission is disabled"
            )

        # ========================================================
        # ASSET TYPE
        # ========================================================

        asset_type = self._asset_type(
            getattr(
                intent,
                "asset_type",
                None,
            )
        )

        if asset_type is None:
            reasons.append(
                "Trade intent contains an unsupported or unknown asset type"
            )

        automation_limits: dict[str, Any] = {}

        if (
            execution_mode
            == ExecutionMode.AUTOMATIC
            and asset_type is not None
        ):
            automation_limits = (
                self._automation_safety_limits(
                    asset_type
                )
            )

        # ========================================================
        # GLOBAL / AUTOMATION POSITION LIMIT
        # ========================================================

        global_max_position_value = (
            self._strictest_positive(
                self._positive_setting(
                    "risk_max_position_value"
                ),
                automation_limits.get(
                    "max_position_value"
                ),
            )
        )

        if (
            notional is not None
            and global_max_position_value
            is not None
            and notional
            > global_max_position_value
        ):
            reasons.append(
                (
                    f"Position value {notional:.2f} "
                    f"exceeds "
                    f"{global_max_position_value:.2f}"
                )
            )

        # ========================================================
        # ACCOUNT BUYING POWER
        # ========================================================

        buying_power = (
            self._required_nonnegative_account_number(
                account,
                "buying_power",
                "Account buying power",
                reasons,
            )
        )

        if (
            notional is not None
            and buying_power is not None
            and notional > buying_power
        ):
            reasons.append(
                (
                    "Insufficient buying power "
                    f"(required {notional:.2f}, "
                    f"available {buying_power:.2f})"
                )
            )

        # ========================================================
        # OPEN POSITIONS
        # ========================================================

        open_positions = (
            self._required_nonnegative_account_integer(
                account,
                "open_positions",
                "Account open-position count",
                reasons,
            )
        )

        max_positions = (
            self._strictest_positive_int(
                self._positive_int_setting(
                    "risk_max_positions"
                ),
                automation_limits.get(
                    "max_open_positions"
                ),
            )
        )

        if (
            max_positions is not None
            and open_positions is not None
            and open_positions
            >= max_positions
        ):
            reasons.append(
                "Maximum simultaneous positions reached"
            )

        # ========================================================
        # DAILY LOSS
        # ========================================================

        max_daily_loss = (
            self._strictest_positive(
                self._positive_setting(
                    "risk_max_daily_loss"
                ),
                automation_limits.get(
                    "max_daily_loss"
                ),
            )
        )

        daily_pnl: float | None = None

        if max_daily_loss is not None:
            daily_pnl = (
                self._required_account_number(
                    account,
                    "daily_pnl",
                    "Account daily P&L",
                    reasons,
                )
            )

            if (
                daily_pnl is not None
                and daily_pnl
                <= -abs(max_daily_loss)
            ):
                reasons.append(
                    "Maximum daily loss reached"
                )

        # ========================================================
        # WEEKLY LOSS
        # ========================================================

        max_weekly_loss = (
            self._positive_setting(
                "risk_max_weekly_loss"
            )
        )

        weekly_pnl: float | None = None

        if max_weekly_loss is not None:
            weekly_pnl = (
                self._required_account_number(
                    account,
                    "weekly_pnl",
                    "Account weekly P&L",
                    reasons,
                )
            )

            if (
                weekly_pnl is not None
                and weekly_pnl
                <= -abs(max_weekly_loss)
            ):
                reasons.append(
                    "Maximum weekly loss reached"
                )

        # ========================================================
        # GROSS EXPOSURE
        # ========================================================

        max_gross_exposure = (
            self._strictest_positive(
                self._positive_setting(
                    "risk_max_gross_exposure"
                ),
                automation_limits.get(
                    "capital_allocation"
                ),
            )
        )

        gross_exposure: float | None = None

        if max_gross_exposure is not None:
            gross_exposure = (
                self._required_nonnegative_account_number(
                    account,
                    "gross_exposure",
                    "Account gross exposure",
                    reasons,
                )
            )

            if (
                gross_exposure is not None
                and notional is not None
                and (
                    gross_exposure
                    + notional
                )
                > max_gross_exposure
            ):
                reasons.append(
                    (
                        "Maximum gross exposure would be exceeded "
                        f"(current {gross_exposure:.2f}, "
                        f"new {notional:.2f}, "
                        f"limit {max_gross_exposure:.2f})"
                    )
                )

        # ========================================================
        # STOP / TARGET
        # ========================================================

        stop = self._optional_number(
            getattr(
                intent,
                "stop",
                None,
            )
        )

        target = self._optional_number(
            getattr(
                intent,
                "target",
                None,
            )
        )

        if (
            getattr(
                intent,
                "stop",
                None,
            )
            is not None
            and stop is None
        ):
            reasons.append(
                "Stop price must be a finite numeric value"
            )

        if (
            getattr(
                intent,
                "target",
                None,
            )
            is not None
            and target is None
        ):
            reasons.append(
                "Target price must be a finite numeric value"
            )

        stop_risk_per_unit: float | None = None
        target_reward_per_unit: float | None = None

        if (
            stop is not None
            and reference_price is not None
        ):
            if stop <= 0:
                reasons.append(
                    "Stop price must be greater than zero"
                )

            elif (
                side == Side.BUY
                and stop >= reference_price
            ):
                reasons.append(
                    "Long stop must be below entry"
                )

            elif (
                side == Side.SELL
                and stop <= reference_price
            ):
                reasons.append(
                    "Short stop must be above entry"
                )

            elif side in {
                Side.BUY,
                Side.SELL,
            }:
                stop_risk_per_unit = abs(
                    reference_price
                    - stop
                )

        if (
            target is not None
            and reference_price is not None
        ):
            if target <= 0:
                reasons.append(
                    "Target price must be greater than zero"
                )

            elif (
                side == Side.BUY
                and target <= reference_price
            ):
                reasons.append(
                    "Long target must be above entry"
                )

            elif (
                side == Side.SELL
                and target >= reference_price
            ):
                reasons.append(
                    "Short target must be below entry"
                )

            elif side in {
                Side.BUY,
                Side.SELL,
            }:
                target_reward_per_unit = abs(
                    target
                    - reference_price
                )

        # ========================================================
        # ESTIMATED LOSS
        # ========================================================

        estimated_loss: float | None = None

        if (
            stop_risk_per_unit is not None
            and stop_risk_per_unit > 0
            and qty is not None
        ):
            estimated_loss = (
                stop_risk_per_unit
                * qty
            )

            if not isfinite(
                estimated_loss
            ):
                reasons.append(
                    "Estimated stop loss is not finite"
                )

                estimated_loss = None

        raw_max_loss = getattr(
            intent,
            "max_loss",
            None,
        )

        max_loss = self._optional_number(
            raw_max_loss
        )

        if (
            raw_max_loss is not None
            and max_loss is None
        ):
            reasons.append(
                "Intent max loss must be a finite numeric value"
            )

        elif (
            max_loss is not None
            and max_loss <= 0
        ):
            reasons.append(
                "Intent max loss must be greater than zero"
            )

        elif (
            max_loss is not None
            and estimated_loss is not None
            and estimated_loss > max_loss
        ):
            reasons.append(
                (
                    "Estimated stop loss "
                    f"{estimated_loss:.2f} "
                    "exceeds intent max loss "
                    f"{max_loss:.2f}"
                )
            )

        # ========================================================
        # RISK / REWARD
        # ========================================================

        risk_reward: float | None = None

        if (
            stop_risk_per_unit is not None
            and stop_risk_per_unit > 0
            and target_reward_per_unit
            is not None
        ):
            risk_reward = (
                target_reward_per_unit
                / stop_risk_per_unit
            )

            if not isfinite(
                risk_reward
            ):
                reasons.append(
                    "Risk/reward ratio is not finite"
                )

                risk_reward = None

            elif (
                risk_reward
                < self.MIN_RISK_REWARD
            ):
                reasons.append(
                    (
                        "Risk/reward ratio is below "
                        f"{self.MIN_RISK_REWARD:.2f}"
                    )
                )

        # ========================================================
        # ASSET-SPECIFIC VALIDATION
        # ========================================================

        if (
            asset_type is not None
            and qty is not None
            and notional is not None
            and reference_price is not None
        ):
            self._validate_asset(
                intent=intent,
                asset_type=asset_type,
                qty=qty,
                notional=notional,
                reference_price=reference_price,
                reasons=reasons,
            )

        # ========================================================
        # AUTOMATIC EXECUTION VALIDATION
        # ========================================================

        if (
            execution_mode
            == ExecutionMode.AUTOMATIC
        ):
            self._validate_automatic(
                intent=intent,
                asset_type=asset_type,
                reasons=reasons,
            )

        # ========================================================
        # REJECT
        # ========================================================

        if reasons:
            return RiskDecision(
                status=RiskStatus.REJECTED,
                reasons=self._deduplicate(
                    reasons
                ),
            )

        # ========================================================
        # APPROVE
        # ========================================================

        if (
            qty is None
            or notional is None
        ):
            return self._reject(
                "Risk evaluation could not establish approved quantity and notional"
            )

        return RiskDecision(
            status=RiskStatus.APPROVED,
            approved_qty=qty,
            approved_notional=notional,
        )

    # ============================================================
    # ASSET VALIDATION
    # ============================================================

    def _validate_asset(
        self,
        *,
        intent: TradeIntent,
        asset_type: AssetType,
        qty: float,
        notional: float,
        reference_price: float,
        reasons: list[str],
    ) -> None:
        if asset_type == AssetType.EQUITY:
            self._validate_equity(
                intent=intent,
                qty=qty,
                notional=notional,
                reasons=reasons,
            )
            return

        if asset_type == AssetType.ETF:
            self._validate_etf(
                intent=intent,
                qty=qty,
                notional=notional,
                reasons=reasons,
            )
            return

        if asset_type == AssetType.CRYPTO:
            self._validate_crypto(
                intent=intent,
                qty=qty,
                notional=notional,
                reasons=reasons,
            )
            return

        if asset_type == AssetType.OPTION:
            self._validate_option(
                intent=intent,
                qty=qty,
                notional=notional,
                reference_price=reference_price,
                reasons=reasons,
            )
            return

        if asset_type == AssetType.FOREX:
            self._validate_forex(
                intent=intent,
                qty=qty,
                notional=notional,
                reasons=reasons,
            )
            return

        if self._is_asset(
            asset_type,
            "BOND",
            "BONDS",
            "FIXED_INCOME",
            "FIXED-INCOME",
        ):
            self._validate_bond(
                intent=intent,
                qty=qty,
                notional=notional,
                reasons=reasons,
            )
            return

        if asset_type == AssetType.COMMODITY:
            self._validate_commodity(
                intent=intent,
                qty=qty,
                notional=notional,
                reasons=reasons,
            )
            return

        reasons.append(
            (
                "Risk Engine does not support asset type "
                f"{self._asset_name(asset_type)}"
            )
        )

    # ============================================================
    # EQUITY
    # ============================================================

    def _validate_equity(
        self,
        *,
        intent: TradeIntent,
        qty: float,
        notional: float,
        reasons: list[str],
    ) -> None:
        if qty <= 0:
            reasons.append(
                "Equity quantity must be greater than zero"
            )

        limit = self._positive_setting(
            "risk_max_equity_position_value"
        )

        if (
            limit is not None
            and notional > limit
        ):
            reasons.append(
                (
                    "Equity position value "
                    f"{notional:.2f} exceeds "
                    f"{limit:.2f}"
                )
            )

    # ============================================================
    # ETF
    # ============================================================

    def _validate_etf(
        self,
        *,
        intent: TradeIntent,
        qty: float,
        notional: float,
        reasons: list[str],
    ) -> None:
        if qty <= 0:
            reasons.append(
                "ETF quantity must be greater than zero"
            )

        limit = self._positive_setting(
            "risk_max_etf_position_value"
        )

        if (
            limit is not None
            and notional > limit
        ):
            reasons.append(
                (
                    "ETF position value "
                    f"{notional:.2f} exceeds "
                    f"{limit:.2f}"
                )
            )

    # ============================================================
    # CRYPTO
    # ============================================================

    def _validate_crypto(
        self,
        *,
        intent: TradeIntent,
        qty: float,
        notional: float,
        reasons: list[str],
    ) -> None:
        if qty <= 0:
            reasons.append(
                "Crypto quantity must be greater than zero"
            )

        limit = self._positive_setting(
            "risk_max_crypto_position_value"
        )

        if (
            limit is not None
            and notional > limit
        ):
            reasons.append(
                (
                    "Crypto position value "
                    f"{notional:.2f} exceeds "
                    f"{limit:.2f}"
                )
            )

        block_short = self._boolean_setting(
            "risk_block_crypto_short_sales",
            default=True,
        )

        if (
            getattr(
                intent,
                "side",
                None,
            )
            == Side.SELL
            and block_short
            and self._intent_opens_short(
                intent
            )
        ):
            reasons.append(
                "Crypto short entries are disabled by risk policy"
            )

    # ============================================================
    # OPTIONS
    # ============================================================

    def _validate_option(
        self,
        *,
        intent: TradeIntent,
        qty: float,
        notional: float,
        reference_price: float,
        reasons: list[str],
    ) -> None:
        if qty <= 0:
            reasons.append(
                "Option contract quantity must be greater than zero"
            )

        if not self._is_whole_number(
            qty
        ):
            reasons.append(
                "Option quantity must be a whole number of contracts"
            )

        multiplier = self._option_multiplier(
            intent
        )

        if multiplier is None:
            reasons.append(
                "Option contract multiplier is required"
            )
            return

        if multiplier <= 0:
            reasons.append(
                "Option contract multiplier must be greater than zero"
            )
            return

        premium_exposure = (
            qty
            * reference_price
            * multiplier
        )

        if not isfinite(
            premium_exposure
        ):
            reasons.append(
                "Option premium exposure is not finite"
            )
            return

        max_option_exposure = (
            self._positive_setting(
                "risk_max_option_position_value"
            )
        )

        if (
            max_option_exposure is not None
            and premium_exposure
            > max_option_exposure
        ):
            reasons.append(
                (
                    "Option premium exposure "
                    f"{premium_exposure:.2f} exceeds "
                    f"{max_option_exposure:.2f}"
                )
            )

        max_contracts = (
            self._positive_int_setting(
                "risk_max_option_contracts"
            )
        )

        if (
            max_contracts is not None
            and qty > max_contracts
        ):
            reasons.append(
                (
                    "Option contract quantity "
                    f"{qty:.0f} exceeds "
                    f"{max_contracts}"
                )
            )

        block_naked = self._boolean_setting(
            "risk_block_naked_option_sales",
            default=True,
        )

        if (
            getattr(
                intent,
                "side",
                None,
            )
            == Side.SELL
            and block_naked
            and self._intent_opens_short(
                intent
            )
            and not self._intent_is_covered(
                intent
            )
        ):
            reasons.append(
                "Naked option selling is disabled by risk policy"
            )

    # ============================================================
    # FOREX
    # ============================================================

    def _validate_forex(
        self,
        *,
        intent: TradeIntent,
        qty: float,
        notional: float,
        reasons: list[str],
    ) -> None:
        if qty <= 0:
            reasons.append(
                "Forex quantity must be greater than zero"
            )

        if not self._boolean_setting(
            "risk_enable_forex",
            default=False,
        ):
            reasons.append(
                "Forex trading is not enabled by risk policy"
            )

        limit = self._positive_setting(
            "risk_max_forex_position_value"
        )

        if (
            limit is not None
            and notional > limit
        ):
            reasons.append(
                (
                    "Forex position value "
                    f"{notional:.2f} exceeds "
                    f"{limit:.2f}"
                )
            )

    # ============================================================
    # BONDS / FIXED INCOME
    # ============================================================

    def _validate_bond(
        self,
        *,
        intent: TradeIntent,
        qty: float,
        notional: float,
        reasons: list[str],
    ) -> None:
        if qty <= 0:
            reasons.append(
                "Fixed-income quantity must be greater than zero"
            )

        if not self._boolean_setting(
            "risk_enable_bonds",
            default=False,
        ):
            reasons.append(
                "Bond/fixed-income trading is not enabled by risk policy"
            )

        limit = self._positive_setting(
            "risk_max_bond_position_value"
        )

        if (
            limit is not None
            and notional > limit
        ):
            reasons.append(
                (
                    "Fixed-income position value "
                    f"{notional:.2f} exceeds "
                    f"{limit:.2f}"
                )
            )

    # ============================================================
    # COMMODITY
    # ============================================================

    def _validate_commodity(
        self,
        *,
        intent: TradeIntent,
        qty: float,
        notional: float,
        reasons: list[str],
    ) -> None:
        if qty <= 0:
            reasons.append(
                "Commodity quantity must be greater than zero"
            )

        if not self._boolean_setting(
            "risk_enable_commodities",
            default=False,
        ):
            reasons.append(
                "Commodity trading is not enabled by risk policy"
            )

        limit = self._positive_setting(
            "risk_max_commodity_position_value"
        )

        if (
            limit is not None
            and notional > limit
        ):
            reasons.append(
                (
                    "Commodity position value "
                    f"{notional:.2f} exceeds "
                    f"{limit:.2f}"
                )
            )

    # ============================================================
    # AUTOMATIC EXECUTION
    # ============================================================

    def _validate_automatic(
        self,
        *,
        intent: TradeIntent,
        asset_type: AssetType | None,
        reasons: list[str],
    ) -> None:
        automation_id = str(
            getattr(
                intent,
                "automation_id",
                "",
            )
            or ""
        ).strip()

        if not automation_id:
            reasons.append(
                "Automatic TradeIntent requires an automation ID"
            )

        strategy = str(
            getattr(
                intent,
                "strategy",
                "",
            )
            or ""
        ).strip()

        if not strategy:
            reasons.append(
                "Automatic TradeIntent requires a strategy"
            )

        if asset_type is None:
            return

        if (
            asset_type == AssetType.FOREX
            and not self._boolean_setting(
                "risk_enable_automatic_forex",
                default=False,
            )
        ):
            reasons.append(
                "Automatic forex trading is not enabled by risk policy"
            )

        if (
            self._is_asset(
                asset_type,
                "BOND",
                "BONDS",
                "FIXED_INCOME",
                "FIXED-INCOME",
            )
            and not self._boolean_setting(
                "risk_enable_automatic_bonds",
                default=False,
            )
        ):
            reasons.append(
                "Automatic bond/fixed-income trading is not enabled by risk policy"
            )

        if (
            asset_type
            == AssetType.COMMODITY
            and not self._boolean_setting(
                "risk_enable_automatic_commodities",
                default=False,
            )
        ):
            reasons.append(
                "Automatic commodity trading is not enabled by risk policy"
            )

    # ============================================================
    # INTENT METADATA
    # ============================================================

    @classmethod
    def _intent_opens_short(
        cls,
        intent: TradeIntent,
    ) -> bool:
        value = cls._intent_boolean(
            intent,
            (
                "opens_short",
                "open_short",
                "is_short_entry",
            ),
        )

        return value is True

    @classmethod
    def _intent_is_covered(
        cls,
        intent: TradeIntent,
    ) -> bool:
        value = cls._intent_boolean(
            intent,
            (
                "covered",
                "is_covered",
            ),
        )

        return value is True

    @staticmethod
    def _intent_boolean(
        intent: TradeIntent,
        keys: tuple[str, ...],
    ) -> bool | None:
        for key in keys:
            value = getattr(
                intent,
                key,
                None,
            )

            if isinstance(
                value,
                bool,
            ):
                return value

        metadata = getattr(
            intent,
            "metadata",
            None,
        )

        if isinstance(
            metadata,
            dict,
        ):
            for key in keys:
                value = metadata.get(
                    key
                )

                if isinstance(
                    value,
                    bool,
                ):
                    return value

        return None

    # ============================================================
    # OPTION MULTIPLIER
    # ============================================================

    @staticmethod
    def _option_multiplier(
        intent: TradeIntent,
    ) -> float | None:
        """
        Return only a multiplier explicitly supplied by the normalized
        TradeIntent or its broker/provider metadata.

        The Risk Engine intentionally does NOT assume 100 because contract
        multipliers can differ and fabricated exposure is unsafe.
        """

        values = (
            getattr(
                intent,
                "contract_multiplier",
                None,
            ),
            getattr(
                intent,
                "multiplier",
                None,
            ),
        )

        for value in values:
            parsed = RiskEngine._optional_number(
                value
            )

            if (
                parsed is not None
                and parsed > 0
            ):
                return parsed

        metadata = getattr(
            intent,
            "metadata",
            None,
        )

        if isinstance(
            metadata,
            dict,
        ):
            for key in (
                "contract_multiplier",
                "multiplier",
            ):
                parsed = (
                    RiskEngine._optional_number(
                        metadata.get(
                            key
                        )
                    )
                )

                if (
                    parsed is not None
                    and parsed > 0
                ):
                    return parsed

        return None

    # ============================================================
    # ASSET TYPE
    # ============================================================

    @staticmethod
    def _asset_type(
        value: Any,
    ) -> AssetType | None:
        if isinstance(
            value,
            AssetType,
        ):
            return value

        if value is None:
            return None

        normalized = str(
            value
        ).strip().upper()

        if not normalized:
            return None

        aliases = {
            "STOCK": "EQUITY",
            "STOCKS": "EQUITY",
            "EQUITIES": "EQUITY",
            "ETFS": "ETF",
            "CRYPTOCURRENCY": "CRYPTO",
            "CRYPTOCURRENCIES": "CRYPTO",
            "OPTIONS": "OPTION",
            "FX": "FOREX",
            "COMMODITIES": "COMMODITY",
        }

        normalized = aliases.get(
            normalized,
            normalized,
        )

        for asset_type in AssetType:
            enum_name = str(
                getattr(
                    asset_type,
                    "name",
                    "",
                )
            ).strip().upper()

            enum_value = str(
                getattr(
                    asset_type,
                    "value",
                    "",
                )
            ).strip().upper()

            if normalized in {
                enum_name,
                enum_value,
            }:
                return asset_type

        return None

    @staticmethod
    def _asset_name(
        asset_type: Any,
    ) -> str:
        value = getattr(
            asset_type,
            "value",
            asset_type,
        )

        return str(
            value
        )

    @classmethod
    def _is_asset(
        cls,
        asset_type: Any,
        *names: str,
    ) -> bool:
        current = (
            cls._asset_name(
                asset_type
            )
            .strip()
            .upper()
        )

        enum_name = str(
            getattr(
                asset_type,
                "name",
                "",
            )
        ).strip().upper()

        wanted = {
            str(
                name
            ).strip().upper()
            for name in names
        }

        return (
            current in wanted
            or enum_name in wanted
        )

    # ============================================================
    # SETTINGS
    # ============================================================

    @staticmethod
    def _setting(
        name: str,
        default: Any = None,
    ) -> Any:
        return getattr(
            settings,
            name,
            default,
        )

    @classmethod
    def _positive_setting(
        cls,
        name: str,
    ) -> float | None:
        raw = cls._setting(
            name,
            None,
        )

        if raw is None:
            return None

        value = cls._optional_number(
            raw
        )

        if (
            value is None
            or value <= 0
        ):
            return None

        return value

    @classmethod
    def _positive_int_setting(
        cls,
        name: str,
    ) -> int | None:
        raw = cls._setting(
            name,
            None,
        )

        if raw is None:
            return None

        if isinstance(
            raw,
            bool,
        ):
            return None

        try:
            number = float(
                raw
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if (
            not isfinite(number)
            or number <= 0
            or not number.is_integer()
        ):
            return None

        return int(
            number
        )

    @classmethod
    def _boolean_setting(
        cls,
        name: str,
        *,
        default: bool,
    ) -> bool:
        value = cls._setting(
            name,
            default,
        )

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            int,
        ) and value in {
            0,
            1,
        }:
            return bool(
                value
            )

        if isinstance(
            value,
            str,
        ):
            normalized = (
                value.strip().lower()
            )

            if normalized in {
                "true",
                "1",
                "yes",
                "on",
                "enabled",
            }:
                return True

            if normalized in {
                "false",
                "0",
                "no",
                "off",
                "disabled",
            }:
                return False

        return default

    # ============================================================
    # ACCOUNT VALUE HELPERS
    # ============================================================

    @classmethod
    def _required_account_number(
        cls,
        account: AccountState,
        attribute: str,
        label: str,
        reasons: list[str],
    ) -> float | None:
        raw = getattr(
            account,
            attribute,
            None,
        )

        value = cls._optional_number(
            raw
        )

        if value is None:
            reasons.append(
                f"{label} is required and must be finite"
            )

            return None

        return value

    @classmethod
    def _required_nonnegative_account_number(
        cls,
        account: AccountState,
        attribute: str,
        label: str,
        reasons: list[str],
    ) -> float | None:
        value = (
            cls._required_account_number(
                account,
                attribute,
                label,
                reasons,
            )
        )

        if value is None:
            return None

        if value < 0:
            reasons.append(
                f"{label} cannot be negative"
            )

            return None

        return value

    @classmethod
    def _required_nonnegative_account_integer(
        cls,
        account: AccountState,
        attribute: str,
        label: str,
        reasons: list[str],
    ) -> int | None:
        raw = getattr(
            account,
            attribute,
            None,
        )

        if isinstance(
            raw,
            bool,
        ):
            reasons.append(
                f"{label} must be a non-negative integer"
            )

            return None

        number = cls._optional_number(
            raw
        )

        if (
            number is None
            or number < 0
            or not number.is_integer()
        ):
            reasons.append(
                f"{label} must be a non-negative integer"
            )

            return None

        return int(
            number
        )

    # ============================================================
    # NUMBER HELPERS
    # ============================================================

    @staticmethod
    def _optional_number(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return None

        try:
            parsed = float(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if not isfinite(
            parsed
        ):
            return None

        return parsed

    @classmethod
    def _required_positive_number(
        cls,
        value: Any,
        label: str,
        reasons: list[str],
    ) -> float | None:
        parsed = cls._optional_number(
            value
        )

        if parsed is None:
            reasons.append(
                f"{label} is required and must be finite"
            )

            return None

        if parsed <= 0:
            reasons.append(
                f"{label} must be greater than zero"
            )

            return None

        return parsed

    # ============================================================
    # BACKWARD-COMPATIBLE FLOAT HELPERS
    # ============================================================

    @classmethod
    def _float(
        cls,
        value: Any,
        default: float = 0.0,
    ) -> float:
        parsed = cls._optional_number(
            value
        )

        if parsed is None:
            return default

        return parsed

    @classmethod
    def _optional_float(
        cls,
        value: Any,
    ) -> float | None:
        return cls._optional_number(
            value
        )

    @staticmethod
    def _int(
        value: Any,
        default: int = 0,
    ) -> int:
        if value is None:
            return default

        if isinstance(
            value,
            bool,
        ):
            return default

        try:
            parsed = float(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return default

        if (
            not isfinite(parsed)
            or not parsed.is_integer()
        ):
            return default

        return int(
            parsed
        )

    # ============================================================
    # WHOLE NUMBER
    # ============================================================

    @staticmethod
    def _is_whole_number(
        value: float,
    ) -> bool:
        if isinstance(
            value,
            bool,
        ):
            return False

        try:
            parsed = float(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return False

        return (
            isfinite(parsed)
            and parsed.is_integer()
        )

    # ============================================================
    # REJECTION
    # ============================================================

    @staticmethod
    def _reject(
        *reasons: str,
    ) -> RiskDecision:
        clean = [
            str(reason).strip()
            for reason in reasons
            if str(reason).strip()
        ]

        return RiskDecision(
            status=RiskStatus.REJECTED,
            reasons=clean,
        )

    # ============================================================
    # DEDUPLICATE
    # ============================================================

    @staticmethod
    def _deduplicate(
        values: list[str],
    ) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()

        for value in values:
            normalized = str(
                value
            ).strip()

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(
                normalized
            )

            output.append(
                normalized
            )

        return output

    validate = evaluate


risk_engine = RiskEngine()


__all__ = [
    "RiskEngine",
    "risk_engine",
]