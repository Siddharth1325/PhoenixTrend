from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx
import websockets

from ..broker import alpaca_broker


# ============================================================
# LIVE MARKET DATA MODELS
# ============================================================


@dataclass
class LiveMarketCredentials:
    key: str
    secret: str


@dataclass
class LiveTrade:
    symbol: str
    time: int
    timestamp: str
    price: float
    size: float
    trade_id: int | str | None = None
    exchange: str | None = None


@dataclass
class LiveCandle:
    symbol: str
    timeframe: str
    time: int
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int
    vwap: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "time": self.time,
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "trade_count": self.trade_count,
            "vwap": self.vwap,
            "source": "alpaca-market-data",
            "provider": "alpaca",
            "provider_mode": "stream",
            "real_time_stream": True,
            "simulated": False,
        }


# ============================================================
# LIVE MARKET DATA SERVICE
# ============================================================


class LiveMarketService:
    """
    PhoenixTrend live market-data service.

    Responsibilities:

    - Connect to genuine Alpaca market-data WebSockets.
    - Route each supported asset class to its correct provider stream.
    - Authenticate using the already connected Alpaca account.
    - Subscribe to genuine provider trade events.
    - Build active candles only from genuine trade prices/sizes.
    - Push genuine candle changes to PhoenixTrend.
    - Never generate or interpolate fake prices.
    - Never expose Alpaca credentials to the browser.

    Supported live routing:

        stocks -> Alpaca IEX/SIP stock stream
        etfs   -> Alpaca IEX/SIP stock stream
        crypto -> Alpaca US crypto stream

    Options, Forex and Bonds are intentionally NOT silently routed
    through the stock stream. Their live-data implementation must be
    explicitly supported before automatic execution can use them.

    Historical chart data remains the responsibility of market.py.

    Broker execution remains the responsibility of broker.py.
    """

    # --------------------------------------------------------
    # STOCK / ETF STREAMS
    # --------------------------------------------------------

    ALPACA_IEX_STREAM_URL = (
        "wss://stream.data.alpaca.markets/v2/iex"
    )

    ALPACA_SIP_STREAM_URL = (
        "wss://stream.data.alpaca.markets/v2/sip"
    )

    # --------------------------------------------------------
    # CRYPTO STREAM
    # --------------------------------------------------------

    ALPACA_CRYPTO_STREAM_URL = (
        "wss://stream.data.alpaca.markets/v1beta3/crypto/us"
    )

    # --------------------------------------------------------
    # REST MARKET DATA
    # --------------------------------------------------------

    ALPACA_DATA_BASE_URL = (
        "https://data.alpaca.markets"
    )

    SUPPORTED_TIMEFRAMES = {
        "1M",
        "5M",
        "15M",
        "30M",
        "1H",
    }

    EQUITY_ASSET_CLASSES = {
        "stocks",
        "etfs",
    }

    CRYPTO_ASSET_CLASSES = {
        "crypto",
    }

    UNSUPPORTED_LIVE_ASSET_CLASSES = {
        "options",
        "forex",
        "bonds",
    }

    def __init__(self) -> None:
        self._default_feed = "iex"

    # ========================================================
    # STATUS
    # ========================================================

    def status(self) -> dict[str, Any]:
        broker_status = alpaca_broker.status()

        return {
            "provider": "alpaca",
            "service": "live-market-data",
            "broker_connected": bool(
                broker_status.get("connected")
            ),
            "feed": self._default_feed,
            "provider_mode": "stream",
            "real_time_stream": True,
            "simulated": False,
            "supported_asset_classes": [
                "stocks",
                "etfs",
                "crypto",
            ],
            "streams": {
                "stocks": {
                    "available": True,
                    "feeds": [
                        "iex",
                        "sip",
                    ],
                },
                "etfs": {
                    "available": True,
                    "feeds": [
                        "iex",
                        "sip",
                    ],
                },
                "crypto": {
                    "available": True,
                    "feed": "crypto",
                },
                "options": {
                    "available": False,
                },
                "forex": {
                    "available": False,
                },
                "bonds": {
                    "available": False,
                },
            },
        }

    # ========================================================
    # ASSET NORMALIZATION
    # ========================================================

    @staticmethod
    def normalize_asset_class(
        asset_class: str | None,
    ) -> str:
        normalized = (
            asset_class
            or "stocks"
        ).strip().lower()

        normalized = (
            normalized
            .replace("-", "_")
            .replace(" ", "_")
        )

        aliases = {
            "stock": "stocks",
            "equity": "stocks",
            "equities": "stocks",

            "etf": "etfs",

            "option": "options",

            "cryptocurrency": "crypto",
            "cryptocurrencies": "crypto",

            "fx": "forex",

            "bond": "bonds",
            "fixed_income": "bonds",
            "fixedincome": "bonds",
        }

        return aliases.get(
            normalized,
            normalized,
        )

    # ========================================================
    # SYMBOL NORMALIZATION
    # ========================================================

    @classmethod
    def normalize_symbol(
        cls,
        symbol: str,
        asset_class: str | None = None,
    ) -> str:
        normalized = (
            symbol
            .strip()
            .upper()
        )

        if not normalized:
            raise ValueError(
                "Symbol is required."
            )

        asset = cls.normalize_asset_class(
            asset_class
        )

        if asset == "crypto":
            return cls.normalize_crypto_symbol(
                normalized
            )

        return normalized

    @staticmethod
    def normalize_crypto_symbol(
        symbol: str,
    ) -> str:
        """
        Normalize crypto symbols into Alpaca pair format.

        Examples:

            BTCUSD  -> BTC/USD
            BTC-USD -> BTC/USD
            BTC_USD -> BTC/USD
            BTC/USD -> BTC/USD

        No fake quote currency is added for unknown symbols.
        """

        normalized = (
            symbol
            .strip()
            .upper()
            .replace("-", "/")
            .replace("_", "/")
            .replace(" ", "")
        )

        if not normalized:
            raise ValueError(
                "Crypto symbol is required."
            )

        if "/" in normalized:
            parts = [
                part
                for part in normalized.split("/")
                if part
            ]

            if len(parts) != 2:
                raise ValueError(
                    f"Invalid crypto pair: {symbol}"
                )

            return (
                f"{parts[0]}/{parts[1]}"
            )

        quote_currencies = (
            "USDT",
            "USDC",
            "USD",
            "BTC",
            "ETH",
        )

        for quote in quote_currencies:
            if (
                normalized.endswith(quote)
                and len(normalized) > len(quote)
            ):
                base = normalized[
                    :-len(quote)
                ]

                return (
                    f"{base}/{quote}"
                )

        raise ValueError(
            "Crypto symbols must be supplied as a pair, "
            "for example BTC/USD or ETH/USD."
        )

    # ========================================================
    # TIMEFRAME NORMALIZATION
    # ========================================================

    @classmethod
    def normalize_timeframe(
        cls,
        timeframe: str,
    ) -> str:
        normalized = (
            timeframe
            .strip()
            .upper()
        )

        aliases = {
            "1MIN": "1M",
            "1MINUTE": "1M",

            "5MIN": "5M",
            "5MINUTE": "5M",

            "15MIN": "15M",
            "15MINUTE": "15M",

            "30MIN": "30M",
            "30MINUTE": "30M",

            "60M": "1H",
            "60MIN": "1H",
            "1HR": "1H",
            "1HOUR": "1H",
        }

        normalized = aliases.get(
            normalized,
            normalized,
        )

        if (
            normalized
            not in cls.SUPPORTED_TIMEFRAMES
        ):
            raise ValueError(
                "LIVE mode supports "
                "1m, 5m, 15m, 30m and 1h."
            )

        return normalized

    # ========================================================
    # FEED NORMALIZATION
    # ========================================================

    @classmethod
    def normalize_feed(
        cls,
        feed: str | None,
        asset_class: str | None = None,
    ) -> str:
        asset = cls.normalize_asset_class(
            asset_class
        )

        if asset == "crypto":
            return "crypto"

        if asset in cls.EQUITY_ASSET_CLASSES:
            normalized = (
                feed
                or "iex"
            ).strip().lower()

            if normalized not in {
                "iex",
                "sip",
            }:
                raise ValueError(
                    "Alpaca stock/ETF market-data feed must "
                    "be 'iex' or 'sip'."
                )

            return normalized

        if (
            asset
            in cls.UNSUPPORTED_LIVE_ASSET_CLASSES
        ):
            raise RuntimeError(
                f"PhoenixTrend live market-data routing "
                f"is not configured for asset class "
                f"'{asset}'."
            )

        raise RuntimeError(
            f"Unsupported live market-data asset class: "
            f"{asset}"
        )

    # ========================================================
    # BROKER CREDENTIALS
    # ========================================================

    @staticmethod
    def _credentials() -> LiveMarketCredentials:
        getter = getattr(
            alpaca_broker,
            "market_data_credentials",
            None,
        )

        if getter is None:
            raise RuntimeError(
                "Alpaca live market data is not configured."
            )

        raw = getter()

        if not isinstance(
            raw,
            dict,
        ):
            raise RuntimeError(
                "Invalid Alpaca market-data credentials."
            )

        key = str(
            raw.get("key")
            or ""
        ).strip()

        secret = str(
            raw.get("secret")
            or ""
        ).strip()

        if not key or not secret:
            raise RuntimeError(
                "Connect Alpaca before starting LIVE mode."
            )

        return LiveMarketCredentials(
            key=key,
            secret=secret,
        )

    # ========================================================
    # STREAM URL
    # ========================================================

    @classmethod
    def stream_url(
        cls,
        feed: str | None = None,
        asset_class: str | None = None,
    ) -> str:
        asset = cls.normalize_asset_class(
            asset_class
        )

        normalized_feed = cls.normalize_feed(
            feed,
            asset,
        )

        if asset == "crypto":
            return (
                cls.ALPACA_CRYPTO_STREAM_URL
            )

        if asset in cls.EQUITY_ASSET_CLASSES:
            if normalized_feed == "sip":
                return (
                    cls.ALPACA_SIP_STREAM_URL
                )

            return (
                cls.ALPACA_IEX_STREAM_URL
            )

        raise RuntimeError(
            f"No live stream URL is configured "
            f"for asset class '{asset}'."
        )

    # ========================================================
    # AUTHENTICATION MESSAGE
    # ========================================================

    @staticmethod
    def auth_message(
        credentials: LiveMarketCredentials,
    ) -> dict[str, Any]:
        return {
            "action": "auth",
            "key": credentials.key,
            "secret": credentials.secret,
        }

    # ========================================================
    # SUBSCRIPTION MESSAGE
    # ========================================================

    @staticmethod
    def subscription_message(
        symbol: str,
    ) -> dict[str, Any]:
        """
        Subscribe to genuine Alpaca trade events.

        Stock, ETF and crypto Alpaca streams use trade
        subscriptions to drive PhoenixTrend live candles.
        """

        return {
            "action": "subscribe",
            "trades": [
                symbol,
            ],
        }

    # ========================================================
    # JSON MESSAGE PARSING
    # ========================================================

    @staticmethod
    def _parse_messages(
        raw_message: str | bytes,
    ) -> list[dict[str, Any]]:
        if isinstance(
            raw_message,
            bytes,
        ):
            raw_message = (
                raw_message.decode(
                    "utf-8"
                )
            )

        payload = json.loads(
            raw_message
        )

        if isinstance(
            payload,
            list,
        ):
            return [
                item
                for item in payload
                if isinstance(
                    item,
                    dict,
                )
            ]

        if isinstance(
            payload,
            dict,
        ):
            return [
                payload
            ]

        return []

    # ========================================================
    # TIMESTAMP PARSING
    # ========================================================

    @staticmethod
    def _parse_timestamp(
        value: Any,
    ) -> datetime:
        if value is None:
            raise ValueError(
                "Live market event has no timestamp."
            )

        if isinstance(
            value,
            datetime,
        ):
            timestamp = value

        else:
            text = str(
                value
            ).strip()

            if text.endswith("Z"):
                text = (
                    text[:-1]
                    + "+00:00"
                )

            timestamp = (
                datetime.fromisoformat(
                    text
                )
            )

        if timestamp.tzinfo is None:
            timestamp = (
                timestamp.replace(
                    tzinfo=timezone.utc
                )
            )

        return timestamp.astimezone(
            timezone.utc
        )

    # ========================================================
    # TRADE NORMALIZATION
    # ========================================================

    @classmethod
    def _normalize_trade(
        cls,
        message: dict[str, Any],
        expected_symbol: str,
    ) -> LiveTrade | None:
        event_type = str(
            message.get("T")
            or ""
        ).strip().lower()

        if event_type != "t":
            return None

        symbol = str(
            message.get("S")
            or ""
        ).strip().upper()

        if (
            symbol
            != expected_symbol
        ):
            return None

        raw_price = (
            message.get("p")
        )

        raw_size = (
            message.get("s")
        )

        raw_timestamp = (
            message.get("t")
        )

        if (
            raw_price is None
            or raw_size is None
            or raw_timestamp is None
        ):
            return None

        try:
            price = float(
                raw_price
            )

            size = float(
                raw_size
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

        if (
            price <= 0
            or size <= 0
        ):
            return None

        timestamp = (
            cls._parse_timestamp(
                raw_timestamp
            )
        )

        trade_id = (
            message.get("i")
        )

        exchange = (
            str(
                message.get("x")
            )
            if message.get("x") is not None
            else None
        )

        return LiveTrade(
            symbol=symbol,
            time=int(
                timestamp.timestamp()
            ),
            timestamp=(
                timestamp.isoformat()
            ),
            price=price,
            size=size,
            trade_id=trade_id,
            exchange=exchange,
        )

    # ========================================================
    # TIMEFRAME BUCKETS
    # ========================================================

    @staticmethod
    def _bucket_seconds(
        timeframe: str,
    ) -> int:
        mapping = {
            "1M": 60,
            "5M": 5 * 60,
            "15M": 15 * 60,
            "30M": 30 * 60,
            "1H": 60 * 60,
        }

        return mapping[
            timeframe
        ]

    @classmethod
    def _bucket_start(
        cls,
        raw_time: int,
        timeframe: str,
    ) -> int:
        seconds = (
            cls._bucket_seconds(
                timeframe
            )
        )

        return (
            int(raw_time)
            // seconds
            * seconds
        )

    # ========================================================
    # LIVE CANDLE BUILDER
    # ========================================================

    @classmethod
    def _apply_trade(
        cls,
        current: LiveCandle | None,
        trade: LiveTrade,
        timeframe: str,
    ) -> LiveCandle:
        """
        Build/update the active candle using genuine trades only.

        Open:
            first genuine trade in the interval

        High:
            highest genuine trade price

        Low:
            lowest genuine trade price

        Close:
            latest genuine trade price

        Volume:
            sum of genuine reported trade sizes

        VWAP:
            volume-weighted average of genuine trades
        """

        bucket = (
            cls._bucket_start(
                trade.time,
                timeframe,
            )
        )

        bucket_timestamp = (
            datetime.fromtimestamp(
                bucket,
                tz=timezone.utc,
            ).isoformat()
        )

        if (
            current is None
            or current.time != bucket
        ):
            return LiveCandle(
                symbol=trade.symbol,
                timeframe=timeframe,
                time=bucket,
                timestamp=bucket_timestamp,
                open=trade.price,
                high=trade.price,
                low=trade.price,
                close=trade.price,
                volume=trade.size,
                trade_count=1,
                vwap=trade.price,
            )

        previous_volume = (
            current.volume
        )

        new_volume = (
            previous_volume
            + trade.size
        )

        vwap: float | None

        if (
            current.vwap is None
            or new_volume <= 0
        ):
            vwap = None

        else:
            vwap = (
                (
                    current.vwap
                    * previous_volume
                )
                + (
                    trade.price
                    * trade.size
                )
            ) / new_volume

        return LiveCandle(
            symbol=current.symbol,
            timeframe=timeframe,
            time=current.time,
            timestamp=current.timestamp,
            open=current.open,
            high=max(
                current.high,
                trade.price,
            ),
            low=min(
                current.low,
                trade.price,
            ),
            close=trade.price,
            volume=new_volume,
            trade_count=(
                current.trade_count
                + 1
            ),
            vwap=vwap,
        )

    # ========================================================
    # AUTH RESPONSE VALIDATION
    # ========================================================

    @staticmethod
    def _validate_auth_messages(
        messages: list[dict[str, Any]],
    ) -> bool:
        for message in messages:
            event_type = str(
                message.get("T")
                or ""
            ).lower()

            message_text = str(
                message.get("msg")
                or ""
            ).lower()

            if (
                event_type == "success"
                and message_text == "authenticated"
            ):
                return True

            if event_type == "error":
                code = (
                    message.get(
                        "code"
                    )
                )

                raise RuntimeError(
                    "Alpaca market-data authentication "
                    f"failed: {code} "
                    f"{message.get('msg') or ''}"
                )

        return False

    # ========================================================
    # SUBSCRIPTION RESPONSE VALIDATION
    # ========================================================

    @staticmethod
    def _validate_subscription_messages(
        messages: list[dict[str, Any]],
        symbol: str,
    ) -> bool:
        for message in messages:
            event_type = str(
                message.get("T")
                or ""
            ).lower()

            if event_type == "error":
                code = (
                    message.get(
                        "code"
                    )
                )

                raise RuntimeError(
                    "Alpaca market-data subscription "
                    f"failed: {code} "
                    f"{message.get('msg') or ''}"
                )

            if (
                event_type
                != "subscription"
            ):
                continue

            trades = (
                message.get("trades")
                or []
            )

            subscribed = {
                str(item).upper()
                for item in trades
            }

            if (
                symbol
                in subscribed
            ):
                return True

        return False

    # ========================================================
    # AUTHENTICATE STREAM
    # ========================================================

    async def _authenticate_stream(
        self,
        websocket: Any,
        credentials: LiveMarketCredentials,
    ) -> None:
        await websocket.send(
            json.dumps(
                self.auth_message(
                    credentials
                )
            )
        )

        for _ in range(5):
            raw_message = (
                await asyncio.wait_for(
                    websocket.recv(),
                    timeout=10,
                )
            )

            messages = (
                self._parse_messages(
                    raw_message
                )
            )

            if (
                self._validate_auth_messages(
                    messages
                )
            ):
                return

        raise RuntimeError(
            "Alpaca market-data stream did not "
            "confirm authentication."
        )

    # ========================================================
    # SUBSCRIBE STREAM
    # ========================================================

    async def _subscribe_stream(
        self,
        websocket: Any,
        symbol: str,
    ) -> None:
        await websocket.send(
            json.dumps(
                self.subscription_message(
                    symbol
                )
            )
        )

        for _ in range(5):
            raw_message = (
                await asyncio.wait_for(
                    websocket.recv(),
                    timeout=10,
                )
            )

            messages = (
                self._parse_messages(
                    raw_message
                )
            )

            if (
                self._validate_subscription_messages(
                    messages,
                    symbol,
                )
            ):
                return

        raise RuntimeError(
            "Alpaca market-data stream did not "
            "confirm the trade subscription."
        )

    # ========================================================
    # STREAM LIVE CANDLES
    # ========================================================

    async def stream_candles(
        self,
        symbol: str,
        timeframe: str = "1M",
        feed: str | None = None,
        asset_class: str = "stocks",
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Yield genuine Alpaca trade-driven candle updates.

        Routing:

            stocks -> IEX/SIP
            etfs   -> IEX/SIP
            crypto -> Alpaca crypto US stream

        Unsupported asset classes are explicitly rejected.

        Every candle mutation originates from a real provider
        trade event.

        No random values.
        No interpolation.
        No artificial candle movement.
        """

        normalized_asset = (
            self.normalize_asset_class(
                asset_class
            )
        )

        normalized_symbol = (
            self.normalize_symbol(
                symbol,
                normalized_asset,
            )
        )

        normalized_timeframe = (
            self.normalize_timeframe(
                timeframe
            )
        )

        normalized_feed = (
            self.normalize_feed(
                feed,
                normalized_asset,
            )
        )

        credentials = (
            self._credentials()
        )

        stream_url = (
            self.stream_url(
                normalized_feed,
                normalized_asset,
            )
        )

        current_candle: (
            LiveCandle | None
        ) = None

        async with websockets.connect(
            stream_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
            max_size=2 * 1024 * 1024,
        ) as websocket:

            await self._authenticate_stream(
                websocket,
                credentials,
            )

            await self._subscribe_stream(
                websocket,
                normalized_symbol,
            )

            yield {
                "type": "live_status",
                "symbol": normalized_symbol,
                "asset_class": normalized_asset,
                "timeframe": normalized_timeframe,
                "provider": "alpaca",
                "provider_mode": "stream",
                "feed": normalized_feed,
                "stream_url_type": (
                    "crypto"
                    if normalized_asset == "crypto"
                    else "equity"
                ),
                "real_time_stream": True,
                "simulated": False,
                "status": "connected",
            }

            while True:
                raw_message = (
                    await websocket.recv()
                )

                messages = (
                    self._parse_messages(
                        raw_message
                    )
                )

                for message in messages:
                    event_type = str(
                        message.get("T")
                        or ""
                    ).lower()

                    if (
                        event_type
                        == "error"
                    ):
                        raise RuntimeError(
                            "Alpaca market-data stream error: "
                            f"{message.get('code')} "
                            f"{message.get('msg') or ''}"
                        )

                    trade = (
                        self._normalize_trade(
                            message,
                            normalized_symbol,
                        )
                    )

                    if trade is None:
                        continue

                    current_candle = (
                        self._apply_trade(
                            current_candle,
                            trade,
                            normalized_timeframe,
                        )
                    )

                    candle_payload = (
                        current_candle.as_dict()
                    )

                    candle_payload[
                        "asset_class"
                    ] = normalized_asset

                    candle_payload[
                        "feed"
                    ] = normalized_feed

                    yield {
                        "type": "candle",
                        "symbol": normalized_symbol,
                        "asset_class": normalized_asset,
                        "timeframe": normalized_timeframe,
                        "provider": "alpaca",
                        "provider_mode": "stream",
                        "feed": normalized_feed,
                        "real_time_stream": True,
                        "simulated": False,
                        "candle": candle_payload,
                    }

    # ========================================================
    # MARKET-DATA ENTITLEMENT CHECK
    # ========================================================

    async def check_feed(
        self,
        feed: str | None = None,
        asset_class: str = "stocks",
    ) -> dict[str, Any]:
        """
        Verify that the configured Alpaca credentials can access
        the requested asset-class market-data source.

        Availability is never inferred solely from broker
        connectivity.
        """

        normalized_asset = (
            self.normalize_asset_class(
                asset_class
            )
        )

        try:
            normalized_feed = (
                self.normalize_feed(
                    feed,
                    normalized_asset,
                )
            )

        except (
            ValueError,
            RuntimeError,
        ) as exc:
            return {
                "available": False,
                "provider": "alpaca",
                "asset_class": normalized_asset,
                "feed": None,
                "real_time_stream": False,
                "simulated": False,
                "message": str(exc),
            }

        credentials = (
            self._credentials()
        )

        headers = {
            "APCA-API-KEY-ID":
                credentials.key,

            "APCA-API-SECRET-KEY":
                credentials.secret,
        }

        if (
            normalized_asset
            in self.EQUITY_ASSET_CLASSES
        ):
            url = (
                f"{self.ALPACA_DATA_BASE_URL}"
                "/v2/stocks/snapshots"
            )

            params = {
                "symbols": "AAPL",
                "feed": normalized_feed,
            }

        elif (
            normalized_asset
            == "crypto"
        ):
            url = (
                f"{self.ALPACA_DATA_BASE_URL}"
                "/v1beta3/crypto/us/latest/trades"
            )

            params = {
                "symbols": "BTC/USD",
            }

        else:
            return {
                "available": False,
                "provider": "alpaca",
                "asset_class": normalized_asset,
                "feed": normalized_feed,
                "real_time_stream": False,
                "simulated": False,
                "message": (
                    "Live market-data entitlement check "
                    "is not configured for this asset class."
                ),
            }

        try:
            async with httpx.AsyncClient(
                timeout=10,
            ) as client:

                response = (
                    await client.get(
                        url,
                        headers=headers,
                        params=params,
                    )
                )

                response.raise_for_status()

        except httpx.HTTPStatusError as exc:
            return {
                "available": False,
                "provider": "alpaca",
                "asset_class": normalized_asset,
                "feed": normalized_feed,
                "real_time_stream": False,
                "simulated": False,
                "status_code":
                    exc.response.status_code,
                "message":
                    exc.response.text
                    or str(exc),
            }

        except httpx.HTTPError as exc:
            return {
                "available": False,
                "provider": "alpaca",
                "asset_class": normalized_asset,
                "feed": normalized_feed,
                "real_time_stream": False,
                "simulated": False,
                "message": str(exc),
            }

        return {
            "available": True,
            "provider": "alpaca",
            "asset_class": normalized_asset,
            "feed": normalized_feed,
            "real_time_stream": True,
            "simulated": False,
        }


# ============================================================
# SINGLETON
# ============================================================


live_market_service = LiveMarketService()