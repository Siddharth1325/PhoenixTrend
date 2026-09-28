from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any

import httpx

from .domain import (
    AssetType,
    Order,
    TradeIntent,
)


# ============================================================
# CREDENTIALS
# ============================================================


@dataclass(frozen=True)
class BrokerCredentials:
    """
    Alpaca credentials are kept in memory only.

    They are supplied by the PhoenixTrend UI and are never
    written to the database by this broker.
    """

    key: str
    secret: str
    paper: bool = True


# ============================================================
# ALPACA BROKER
# ============================================================


class AlpacaBroker:
    """
    PhoenixTrend Alpaca execution adapter.

    Responsibilities:
        - connect / disconnect
        - expose broker connection state
        - expose broker capabilities
        - retrieve account information
        - retrieve positions
        - retrieve broker asset metadata
        - validate supported PhoenixTrend trade intents
        - submit approved orders
        - retrieve order status
        - retrieve orders by PhoenixTrend intent ID
        - cancel orders
        - cancel all open orders
        - preserve PhoenixTrend intent IDs as client_order_id

    This adapter does NOT:
        - generate signals
        - select strategies
        - perform risk decisions
        - fabricate fills
        - fabricate prices
        - silently simulate unsupported assets

    PhoenixTrend supports more asset classes at the domain level
    than this particular broker adapter necessarily supports.
    """

    PAPER_BASE_URL = "https://paper-api.alpaca.markets"
    LIVE_BASE_URL = "https://api.alpaca.markets"

    SUPPORTED_ASSET_TYPES = {
        AssetType.EQUITY,
        AssetType.ETF,
        AssetType.CRYPTO,
        AssetType.OPTION,
    }

    UNSUPPORTED_ASSET_TYPES = {
        AssetType.FOREX,
        AssetType.COMMODITY,
    }

    SUPPORTED_ORDER_TYPES = {
        "market",
        "limit",
        "stop",
        "stop_limit",
    }

    def __init__(self) -> None:
        self._lock = RLock()
        self._creds: BrokerCredentials | None = None

    # ============================================================
    # CONNECTION HELPERS
    # ============================================================

    @staticmethod
    def _base(paper: bool) -> str:
        if paper:
            return AlpacaBroker.PAPER_BASE_URL

        return AlpacaBroker.LIVE_BASE_URL

    @staticmethod
    def _headers(
        credentials: BrokerCredentials,
    ) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": credentials.key,
            "APCA-API-SECRET-KEY": credentials.secret,
        }

    # ============================================================
    # CONNECT
    # ============================================================

    def connect(
        self,
        key: str,
        secret: str,
        paper: bool = True,
    ) -> dict[str, Any]:
        key = str(key).strip()
        secret = str(secret).strip()

        if not key or not secret:
            raise ValueError(
                "API key and secret are required."
            )

        credentials = BrokerCredentials(
            key=key,
            secret=secret,
            paper=bool(paper),
        )

        base_url = self._base(
            credentials.paper
        )

        headers = self._headers(
            credentials
        )

        try:
            with httpx.Client(
                timeout=12,
            ) as client:
                response = client.get(
                    f"{base_url}/v2/account",
                    headers=headers,
                )

                response.raise_for_status()
                account = response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    "Alpaca connection failed",
                    exc,
                )
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Unable to reach Alpaca: {exc}"
            ) from exc

        if not isinstance(
            account,
            dict,
        ):
            raise RuntimeError(
                "Alpaca returned an invalid account response."
            )

        # Credentials are stored only after Alpaca validates them.
        with self._lock:
            self._creds = credentials

        return {
            "connected": True,
            "paper": credentials.paper,
            "broker": "alpaca",
            "capabilities": self.capabilities(),
            "account": {
                "status": account.get(
                    "status"
                ),
                "currency": account.get(
                    "currency"
                ),
                "cash": account.get(
                    "cash"
                ),
                "buying_power": account.get(
                    "buying_power"
                ),
                "portfolio_value": account.get(
                    "portfolio_value"
                ),
                "equity": account.get(
                    "equity"
                ),
                "last_equity": account.get(
                    "last_equity"
                ),
                "trading_blocked": account.get(
                    "trading_blocked"
                ),
                "account_blocked": account.get(
                    "account_blocked"
                ),
                "trade_suspended_by_user": account.get(
                    "trade_suspended_by_user"
                ),
            },
        }

    # ============================================================
    # DISCONNECT
    # ============================================================

    def disconnect(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            self._creds = None

        return {
            "connected": False,
            "paper": None,
            "broker": "alpaca",
            "capabilities": self.capabilities(),
        }

    # ============================================================
    # CONNECTION STATE
    # ============================================================

    def is_connected(
        self,
    ) -> bool:
        with self._lock:
            return self._creds is not None

    # ============================================================
    # CAPABILITIES
    # ============================================================

    def capabilities(
        self,
    ) -> dict[str, dict[str, Any]]:
        connected = self.is_connected()

        capabilities: dict[
            str,
            dict[str, Any],
        ] = {}

        asset_aliases = {
            AssetType.EQUITY: "stocks",
            AssetType.ETF: "etfs",
            AssetType.CRYPTO: "crypto",
            AssetType.OPTION: "options",
            AssetType.FOREX: "forex",
            AssetType.COMMODITY: "commodities",
        }

        for asset_type, name in asset_aliases.items():
            supported = (
                asset_type
                in self.SUPPORTED_ASSET_TYPES
            )

            capabilities[name] = {
                "asset_type": asset_type.value,
                "supported": supported,
                "connected": connected,
                "available": (
                    supported
                    and connected
                ),
                "automatic_trading": supported,
                "manual_trading": supported,
                "order_types": (
                    sorted(
                        self.SUPPORTED_ORDER_TYPES
                    )
                    if supported
                    else []
                ),
                "reason": (
                    None
                    if supported
                    else (
                        "Asset class is not supported "
                        "by the Alpaca broker adapter."
                    )
                ),
            }

        return capabilities

    # ============================================================
    # STATUS
    # ============================================================

    def status(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            credentials = self._creds

        return {
            "connected": (
                credentials is not None
            ),
            "paper": (
                credentials.paper
                if credentials
                else None
            ),
            "broker": "alpaca",
            "credentials_persisted": False,
            "supported_asset_types": [
                asset_type.value
                for asset_type
                in sorted(
                    self.SUPPORTED_ASSET_TYPES,
                    key=lambda item: item.value,
                )
            ],
            "unsupported_asset_types": [
                asset_type.value
                for asset_type
                in sorted(
                    self.UNSUPPORTED_ASSET_TYPES,
                    key=lambda item: item.value,
                )
            ],
            "supported_order_types": sorted(
                self.SUPPORTED_ORDER_TYPES
            ),
            "capabilities": self.capabilities(),
        }

    # ============================================================
    # MARKET DATA AUTH
    # ============================================================

    def market_data_credentials(
        self,
    ) -> dict[str, str]:
        """
        Return validated Alpaca credentials for internal
        PhoenixTrend market-data services.

        Credentials remain server-side only and must never be
        exposed through a public API endpoint or browser response.
        """

        with self._lock:
            credentials = self._creds

        if credentials is None:
            raise RuntimeError(
                "Alpaca is not connected."
            )

        return {
            "key": credentials.key,
            "secret": credentials.secret,
        }

    # ============================================================
    # AUTH
    # ============================================================

    def _auth(
        self,
    ) -> tuple[
        BrokerCredentials,
        str,
        dict[str, str],
    ]:
        with self._lock:
            credentials = self._creds

        if credentials is None:
            raise RuntimeError(
                "Alpaca is not connected."
            )

        return (
            credentials,
            self._base(
                credentials.paper
            ),
            self._headers(
                credentials
            ),
        )

    # ============================================================
    # ACCOUNT
    # ============================================================

    def account(
        self,
    ) -> dict[str, Any]:
        _, base_url, headers = (
            self._auth()
        )

        try:
            with httpx.Client(
                timeout=12,
            ) as client:
                response = client.get(
                    f"{base_url}/v2/account",
                    headers=headers,
                )

                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    "Unable to retrieve Alpaca account",
                    exc,
                )
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Unable to reach Alpaca: {exc}"
            ) from exc

        if not isinstance(
            data,
            dict,
        ):
            raise RuntimeError(
                "Alpaca returned an invalid account response."
            )

        return data

    # ============================================================
    # PORTFOLIO HISTORY
    # ============================================================

    def portfolio_history(
        self,
        *,
        period: str = "1M",
        timeframe: str = "1D",
    ) -> dict[str, Any]:
        """Return Alpaca's real account portfolio history.

        This is used for account P&L/risk metrics.  Values are never
        fabricated; callers must handle an unavailable history response.
        """
        _, base_url, headers = self._auth()

        try:
            with httpx.Client(timeout=12) as client:
                response = client.get(
                    f"{base_url}/v2/account/portfolio/history",
                    headers=headers,
                    params={
                        "period": str(period),
                        "timeframe": str(timeframe),
                        "extended_hours": "true",
                    },
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    "Unable to retrieve Alpaca portfolio history", exc
                )
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Unable to reach Alpaca: {exc}") from exc

        if not isinstance(data, dict):
            raise RuntimeError(
                "Alpaca returned an invalid portfolio history response."
            )

        return data

    # ============================================================
    # POSITIONS
    # ============================================================

    def positions(
        self,
    ) -> list[dict[str, Any]]:
        _, base_url, headers = (
            self._auth()
        )

        try:
            with httpx.Client(
                timeout=12,
            ) as client:
                response = client.get(
                    f"{base_url}/v2/positions",
                    headers=headers,
                )

                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    "Unable to retrieve Alpaca positions",
                    exc,
                )
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Unable to reach Alpaca: {exc}"
            ) from exc

        if not isinstance(
            data,
            list,
        ):
            raise RuntimeError(
                "Alpaca returned an invalid positions response."
            )

        return data

    # ============================================================
    # ASSET
    # ============================================================

    def get_asset(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Ask Alpaca for the broker's actual metadata for a symbol.

        This is useful for determining whether a symbol is active,
        tradable and fractionable rather than guessing locally.
        """

        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )

        _, base_url, headers = (
            self._auth()
        )

        try:
            with httpx.Client(
                timeout=12,
            ) as client:
                response = client.get(
                    (
                        f"{base_url}/v2/assets/"
                        f"{normalized_symbol}"
                    ),
                    headers=headers,
                )

                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    (
                        "Unable to retrieve "
                        f"Alpaca asset {normalized_symbol}"
                    ),
                    exc,
                )
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Unable to reach Alpaca: {exc}"
            ) from exc

        if not isinstance(
            data,
            dict,
        ):
            raise RuntimeError(
                "Alpaca returned an invalid asset response."
            )

        return data

    # ============================================================
    # ASSET TYPE CAPABILITY
    # ============================================================

    def supports_asset_type(
        self,
        asset_type: AssetType,
    ) -> bool:
        try:
            if isinstance(
                asset_type,
                AssetType,
            ):
                normalized = asset_type

            else:
                raw = str(
                    asset_type
                ).strip()

                normalized = None

                for candidate in AssetType:
                    if (
                        raw.upper()
                        == candidate.name.upper()
                        or raw.upper()
                        == str(
                            candidate.value
                        ).upper()
                    ):
                        normalized = candidate
                        break

                if normalized is None:
                    return False

        except (
            TypeError,
            ValueError,
        ):
            return False

        return (
            normalized
            in self.SUPPORTED_ASSET_TYPES
        )

    # ============================================================
    # INTENT CAPABILITY
    # ============================================================

    def supports_intent(
        self,
        intent: TradeIntent,
    ) -> bool:
        try:
            self._validate_intent(
                intent
            )

            return True

        except (
            TypeError,
            ValueError,
        ):
            return False

    # ============================================================
    # INTENT VALIDATION
    # ============================================================

    def _validate_intent(
        self,
        intent: TradeIntent,
    ) -> None:
        if intent is None:
            raise ValueError(
                "Trade intent is required."
            )

        if not self.supports_asset_type(
            intent.asset_type
        ):
            raise ValueError(
                (
                    "Alpaca broker adapter does not "
                    "support PhoenixTrend asset type "
                    f"{intent.asset_type.value}."
                )
            )

        symbol = self._normalize_symbol(
            intent.symbol
        )

        if not symbol:
            raise ValueError(
                "Order symbol is required."
            )

        try:
            qty = float(
                intent.qty
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Order quantity must be numeric."
            ) from exc

        if qty <= 0:
            raise ValueError(
                "Order quantity must be greater than zero."
            )

        if (
            intent.asset_type
            == AssetType.OPTION
            and not qty.is_integer()
        ):
            raise ValueError(
                "Option quantity must be a whole number of contracts."
            )

        order_type = str(
            intent.order_type
        ).strip().lower()

        if (
            order_type
            not in self.SUPPORTED_ORDER_TYPES
        ):
            raise ValueError(
                (
                    "Unsupported order type: "
                    f"{order_type}"
                )
            )

        if (
            order_type
            in {
                "limit",
                "stop_limit",
            }
            and intent.limit_price is None
        ):
            raise ValueError(
                (
                    f"{order_type} order requires "
                    "limit_price."
                )
            )

        if (
            order_type
            in {
                "stop",
                "stop_limit",
            }
            and intent.stop_price is None
        ):
            raise ValueError(
                (
                    f"{order_type} order requires "
                    "stop_price."
                )
            )

        if (
            intent.limit_price is not None
            and float(
                intent.limit_price
            ) <= 0
        ):
            raise ValueError(
                "limit_price must be greater than zero."
            )

        if (
            intent.stop_price is not None
            and float(
                intent.stop_price
            ) <= 0
        ):
            raise ValueError(
                "stop_price must be greater than zero."
            )

        time_in_force = str(
            intent.time_in_force
        ).strip().lower()

        if not time_in_force:
            raise ValueError(
                "time_in_force is required."
            )

        # Do not silently rewrite TIF here.
        #
        # Different asset classes can have different broker rules.
        # If PhoenixTrend supplies an invalid combination, Alpaca
        # must reject it rather than PhoenixTrend pretending it
        # executed something else.

        if (
            intent.instrument is not None
            and intent.instrument.symbol.upper()
            != intent.symbol.upper()
        ):
            raise ValueError(
                (
                    "TradeIntent instrument symbol "
                    "does not match intent symbol."
                )
            )

        if (
            intent.instrument is not None
            and intent.instrument.asset_type
            != intent.asset_type
        ):
            raise ValueError(
                (
                    "TradeIntent instrument asset type "
                    "does not match intent asset type."
                )
            )

    # ============================================================
    # RAW ORDER SUBMISSION
    # ============================================================

    def order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
        limit_price: float | None = None,
        stop_price: float | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Lower-level order helper.

        PhoenixTrend automatic execution should normally use
        submit(TradeIntent), because that preserves intent metadata
        and the execution pipeline.
        """

        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )

        normalized_qty = (
            self._normalize_qty(
                qty
            )
        )

        normalized_side = (
            str(
                side
            )
            .strip()
            .lower()
        )

        if normalized_side not in {
            "buy",
            "sell",
        }:
            raise ValueError(
                "Order side must be buy or sell."
            )

        normalized_order_type = (
            str(
                order_type
            )
            .strip()
            .lower()
        )

        if (
            normalized_order_type
            not in self.SUPPORTED_ORDER_TYPES
        ):
            raise ValueError(
                (
                    "Unsupported order type: "
                    f"{normalized_order_type}"
                )
            )

        normalized_tif = (
            str(
                time_in_force
            )
            .strip()
            .lower()
        )

        if not normalized_tif:
            raise ValueError(
                "time_in_force is required."
            )

        if (
            normalized_order_type
            in {
                "limit",
                "stop_limit",
            }
            and limit_price is None
        ):
            raise ValueError(
                (
                    f"{normalized_order_type} "
                    "order requires limit_price."
                )
            )

        if (
            normalized_order_type
            in {
                "stop",
                "stop_limit",
            }
            and stop_price is None
        ):
            raise ValueError(
                (
                    f"{normalized_order_type} "
                    "order requires stop_price."
                )
            )

        _, base_url, headers = (
            self._auth()
        )

        payload: dict[str, Any] = {
            "symbol": normalized_symbol,
            "qty": self._decimal_string(
                normalized_qty
            ),
            "side": normalized_side,
            "type": normalized_order_type,
            "time_in_force": normalized_tif,
        }

        if limit_price is not None:
            payload["limit_price"] = (
                self._decimal_string(
                    limit_price
                )
            )

        if stop_price is not None:
            payload["stop_price"] = (
                self._decimal_string(
                    stop_price
                )
            )

        if client_order_id:
            payload["client_order_id"] = (
                str(
                    client_order_id
                ).strip()[:48]
            )

        try:
            with httpx.Client(
                timeout=12,
            ) as client:
                response = client.post(
                    f"{base_url}/v2/orders",
                    headers=headers,
                    json=payload,
                )

                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    "Alpaca rejected the order",
                    exc,
                )
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Unable to reach Alpaca: {exc}"
            ) from exc

        if not isinstance(
            data,
            dict,
        ):
            raise RuntimeError(
                "Alpaca returned an invalid order response."
            )

        return data

    # ============================================================
    # PHOENIXTREND TRADEINTENT SUBMISSION
    # ============================================================

    async def submit(
        self,
        intent: TradeIntent,
    ) -> Order:
        """
        Submit an already risk-approved TradeIntent.

        This method does not perform PhoenixTrend risk approval.
        ExecutionService must perform that before calling submit().

        The PhoenixTrend intent ID is sent as Alpaca's
        client_order_id so broker orders remain traceable back to
        the exact PhoenixTrend decision that created them.
        """

        self._validate_intent(
            intent
        )

        _, base_url, headers = (
            self._auth()
        )

        payload = self._intent_payload(
            intent
        )

        try:
            async with httpx.AsyncClient(
                timeout=12,
            ) as client:
                response = await client.post(
                    f"{base_url}/v2/orders",
                    headers=headers,
                    json=payload,
                )

                response.raise_for_status()
                raw = response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    "Alpaca rejected the order",
                    exc,
                )
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Unable to reach Alpaca: {exc}"
            ) from exc

        if not isinstance(
            raw,
            dict,
        ):
            raise RuntimeError(
                "Alpaca returned an invalid order response."
            )

        return self._order_from_response(
            intent,
            raw,
        )

    # ============================================================
    # INTENT PAYLOAD
    # ============================================================

    def _intent_payload(
        self,
        intent: TradeIntent,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": self._normalize_symbol(
                intent.symbol
            ),
            "qty": self._decimal_string(
                intent.qty
            ),
            "side": (
                intent.side.value.lower()
            ),
            "type": (
                str(
                    intent.order_type
                )
                .strip()
                .lower()
            ),
            "time_in_force": (
                str(
                    intent.time_in_force
                )
                .strip()
                .lower()
            ),
            "client_order_id": (
                str(
                    intent.intent_id
                ).strip()[:48]
            ),
        }

        if intent.limit_price is not None:
            payload["limit_price"] = (
                self._decimal_string(
                    intent.limit_price
                )
            )

        if intent.stop_price is not None:
            payload["stop_price"] = (
                self._decimal_string(
                    intent.stop_price
                )
            )

        return payload

    # ============================================================
    # NORMALIZE BROKER ORDER
    # ============================================================

    def _order_from_response(
        self,
        intent: TradeIntent,
        raw: dict[str, Any],
    ) -> Order:
        filled_price = (
            self._optional_float(
                raw.get(
                    "filled_avg_price"
                )
            )
        )

        # If Alpaca has not filled the order yet, this is NOT a
        # fabricated fill price.
        #
        # Order.price remains the PhoenixTrend reference price used
        # when the intent was created. Order.status tells callers
        # whether the broker has actually filled the order.

        price = (
            filled_price
            if filled_price is not None
            else float(
                intent.reference_price
            )
        )

        order_id = str(
            raw.get(
                "id"
            )
            or raw.get(
                "client_order_id"
            )
            or intent.intent_id
        )

        status = str(
            raw.get(
                "status"
            )
            or "NEW"
        ).upper()

        return Order(
            order_id=order_id,
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            asset_type=intent.asset_type,
            side=intent.side,
            qty=intent.qty,
            price=price,
            status=status,
            broker=self._broker_name(),
        )

    # ============================================================
    # BROKER NAME
    # ============================================================

    def _broker_name(
        self,
    ) -> str:
        with self._lock:
            credentials = self._creds

        if credentials is None:
            return "alpaca"

        if credentials.paper:
            return "alpaca-paper"

        return "alpaca-live"

    # ============================================================
    # ORDER STATUS
    # ============================================================

    def get_order(
        self,
        order_id: str,
    ) -> dict[str, Any]:
        normalized_order_id = str(
            order_id
        ).strip()

        if not normalized_order_id:
            raise ValueError(
                "Order ID is required."
            )

        _, base_url, headers = (
            self._auth()
        )

        try:
            with httpx.Client(
                timeout=12,
            ) as client:
                response = client.get(
                    (
                        f"{base_url}/v2/orders/"
                        f"{normalized_order_id}"
                    ),
                    headers=headers,
                )

                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    "Unable to retrieve Alpaca order",
                    exc,
                )
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Unable to reach Alpaca: {exc}"
            ) from exc

        if not isinstance(
            data,
            dict,
        ):
            raise RuntimeError(
                "Alpaca returned an invalid order response."
            )

        return data

    # ============================================================
    # ORDER BY CLIENT ORDER ID
    # ============================================================

    def get_order_by_client_order_id(
        self,
        client_order_id: str,
    ) -> dict[str, Any]:
        """
        Resolve a broker order using the PhoenixTrend intent ID.

        This is important when a network error happens after Alpaca
        accepted an order but before PhoenixTrend received the HTTP
        response.
        """

        normalized = str(
            client_order_id
        ).strip()[:48]

        if not normalized:
            raise ValueError(
                "Client order ID is required."
            )

        _, base_url, headers = (
            self._auth()
        )

        try:
            with httpx.Client(
                timeout=12,
            ) as client:
                response = client.get(
                    f"{base_url}/v2/orders:by_client_order_id",
                    headers=headers,
                    params={
                        "client_order_id": normalized
                    },
                )

                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    (
                        "Unable to retrieve Alpaca "
                        "order by client order ID"
                    ),
                    exc,
                )
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Unable to reach Alpaca: {exc}"
            ) from exc

        if not isinstance(
            data,
            dict,
        ):
            raise RuntimeError(
                "Alpaca returned an invalid order response."
            )

        return data

    # ============================================================
    # CANCEL ORDER
    # ============================================================

    def cancel_order(
        self,
        order_id: str,
    ) -> dict[str, Any]:
        normalized_order_id = str(
            order_id
        ).strip()

        if not normalized_order_id:
            raise ValueError(
                "Order ID is required."
            )

        _, base_url, headers = (
            self._auth()
        )

        try:
            with httpx.Client(
                timeout=12,
            ) as client:
                response = client.delete(
                    (
                        f"{base_url}/v2/orders/"
                        f"{normalized_order_id}"
                    ),
                    headers=headers,
                )

                response.raise_for_status()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    "Unable to cancel Alpaca order",
                    exc,
                )
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Unable to reach Alpaca: {exc}"
            ) from exc

        return {
            "order_id": normalized_order_id,
            "cancel_requested": True,
        }

    # ============================================================
    # CANCEL ALL ORDERS
    # ============================================================

    def cancel_all_orders(
        self,
    ) -> dict[str, Any]:
        """
        Request cancellation of all open Alpaca orders.

        This is useful for the PhoenixTrend emergency-stop workflow.
        It does not claim that every order was cancelled until the
        broker confirms its own resulting order states.
        """

        _, base_url, headers = (
            self._auth()
        )

        try:
            with httpx.Client(
                timeout=12,
            ) as client:
                response = client.delete(
                    f"{base_url}/v2/orders",
                    headers=headers,
                )

                response.raise_for_status()

                if response.content:
                    data = response.json()
                else:
                    data = []

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    "Unable to cancel Alpaca orders",
                    exc,
                )
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Unable to reach Alpaca: {exc}"
            ) from exc

        return {
            "cancel_requested": True,
            "broker_response": data,
        }

    # ============================================================
    # OPEN ORDERS
    # ============================================================

    def open_orders(
        self,
    ) -> list[dict[str, Any]]:
        _, base_url, headers = (
            self._auth()
        )

        try:
            with httpx.Client(
                timeout=12,
            ) as client:
                response = client.get(
                    f"{base_url}/v2/orders",
                    headers=headers,
                    params={
                        "status": "open",
                        "direction": "desc",
                    },
                )

                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                self._format_http_error(
                    "Unable to retrieve Alpaca open orders",
                    exc,
                )
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Unable to reach Alpaca: {exc}"
            ) from exc

        if not isinstance(
            data,
            list,
        ):
            raise RuntimeError(
                "Alpaca returned an invalid orders response."
            )

        return data

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        normalized = str(
            symbol
        ).strip().upper()

        if not normalized:
            raise ValueError(
                "Symbol is required."
            )

        return normalized

    @staticmethod
    def _normalize_qty(
        qty: float,
    ) -> float:
        try:
            normalized = float(
                qty
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Order quantity must be numeric."
            ) from exc

        if normalized <= 0:
            raise ValueError(
                "Order quantity must be greater than zero."
            )

        return normalized

    @staticmethod
    def _decimal_string(
        value: Any,
    ) -> str:
        try:
            number = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                f"Invalid numeric value: {value}"
            ) from exc

        if number <= 0:
            raise ValueError(
                "Numeric order values must be greater than zero."
            )

        return format(
            number,
            ".12g",
        )

    @staticmethod
    def _optional_float(
        value: Any,
    ) -> float | None:
        if value in {
            None,
            "",
        }:
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

    # ============================================================
    # ERROR NORMALIZATION
    # ============================================================

    @staticmethod
    def _format_http_error(
        prefix: str,
        exc: httpx.HTTPStatusError,
    ) -> str:
        response = exc.response

        try:
            payload = response.json()

            if isinstance(
                payload,
                dict,
            ):
                message = (
                    payload.get(
                        "message"
                    )
                    or payload.get(
                        "error"
                    )
                    or payload.get(
                        "code"
                    )
                    or str(
                        payload
                    )
                )

            else:
                message = str(
                    payload
                )

        except Exception:
            message = (
                response.text
                or str(
                    exc
                )
            )

        return (
            f"{prefix}: "
            f"HTTP {response.status_code} - "
            f"{message}"
        )


# ============================================================
# SINGLETON
# ============================================================


alpaca_broker = AlpacaBroker()