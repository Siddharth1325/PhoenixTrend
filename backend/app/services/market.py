from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from typing import Any

import httpx

from .indicators import ema, feature_snapshot


class MarketService:
    """
    PhoenixTrend independent market-data service.

    Yahoo Finance is currently used for:
        - market scanning
        - technical analysis
        - charts
        - strategy research
        - market intelligence

    Yahoo data is NOT currently considered sufficient for
    unattended automatic live execution.
    """

    CHART_URL = (
        "https://query1.finance.yahoo.com/"
        "v8/finance/chart/{symbol}"
    )

    QUOTE_SUMMARY_URL = (
        "https://query2.finance.yahoo.com/"
        "v10/finance/quoteSummary/{symbol}"
    )

    QUOTE_URL = (
        "https://query1.finance.yahoo.com/"
        "v7/finance/quote"
    )

    COOKIE_URL = "https://fc.yahoo.com"

    CRUMB_URL = (
        "https://query1.finance.yahoo.com/"
        "v1/test/getcrumb"
    )

    DEFAULT_INTRADAY_TIMEFRAME = "5M"
    DEFAULT_INTRADAY_RANGE = "5D"

    DEFAULT_HISTORY_TIMEFRAME = "1D"
    DEFAULT_HISTORY_RANGE = "1Y"

    CACHE_TTL_INTRADAY = 10
    CACHE_TTL_DAILY = 60

    # ========================================================
    # INITIALIZATION
    # ========================================================

    def __init__(self) -> None:
        self._cache: dict[
            tuple[str, str, str],
            tuple[float, Any],
        ] = {}

        self._fundamentals_cache: dict[
            str,
            tuple[float, dict[str, Any]],
        ] = {}

        self._lock = RLock()

    # ========================================================
    # SYMBOL NORMALIZATION
    # ========================================================

    @staticmethod
    def _symbol(
        symbol: str,
    ) -> str:
        normalized = (
            symbol
            .strip()
            .upper()
        )

        provider_map = {
            # Crypto
            "BTCUSD": "BTC-USD",
            "ETHUSD": "ETH-USD",
            "SOLUSD": "SOL-USD",
            "XRPUSD": "XRP-USD",
            "DOGEUSD": "DOGE-USD",
            "ADAUSD": "ADA-USD",
            "AVAXUSD": "AVAX-USD",

            # Friendly FX aliases
            "EURUSD": "EURUSD=X",
            "GBPUSD": "GBPUSD=X",
            "AUDUSD": "AUDUSD=X",
            "NZDUSD": "NZDUSD=X",
            "USDJPY": "JPY=X",
            "USDCAD": "CAD=X",
            "USDCHF": "CHF=X",

            # Friendly futures aliases
            "ES": "ES=F",
            "NQ": "NQ=F",
            "YM": "YM=F",
            "RTY": "RTY=F",

            # Friendly commodity aliases
            "GOLD": "GC=F",
            "SILVER": "SI=F",
            "OIL": "CL=F",
            "NATGAS": "NG=F",
            "COPPER": "HG=F",
        }

        return provider_map.get(
            normalized,
            normalized,
        )

    # ========================================================
    # ASSET TYPE
    # ========================================================

    @staticmethod
    def _asset_type(
        symbol: str,
    ) -> str:
        normalized = (
            symbol
            .strip()
            .upper()
        )

        crypto_symbols = {
            "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD",
            "DOGEUSD", "ADAUSD", "AVAXUSD",
        }

        etf_symbols = {
            "SPY", "QQQ", "VOO", "IWM", "DIA",
            "XLK", "XLF", "XLE", "TLT", "IEF", "SHY",
        }

        commodity_symbols = {
            "GC=F", "SI=F", "CL=F", "NG=F", "HG=F",
            "GOLD", "SILVER", "OIL", "NATGAS", "COPPER",
        }

        bond_symbols = {
            "^TNX", "^FVX", "^TYX", "TLT", "IEF", "SHY",
        }

        if normalized.endswith("-USD") or normalized in crypto_symbols:
            return "crypto"

        if normalized.endswith("=X") or normalized in {
            "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD",
            "USDJPY", "USDCAD", "USDCHF",
        }:
            return "forex"

        if normalized in commodity_symbols:
            return "commodity"

        if normalized.endswith("=F") or normalized in {
            "ES", "NQ", "YM", "RTY",
        }:
            return "future"

        if normalized in bond_symbols:
            return "bond"

        if normalized in etf_symbols:
            return "etf"

        return "equity"

    # ========================================================
    # RANGE NORMALIZATION
    # ========================================================

    @staticmethod
    def _range(
        value: str,
    ) -> str:
        mapping = {
            "1D": "1d",
            "5D": "5d",
            "1M": "1mo",
            "3M": "3mo",
            "6M": "6mo",
            "YTD": "ytd",
            "1Y": "1y",
            "2Y": "2y",
            "5Y": "5y",
            "MAX": "max",
        }

        key = (
            value
            .strip()
            .upper()
        )

        return mapping.get(
            key,
            value,
        )

    # ========================================================
    # INTERVAL NORMALIZATION
    # ========================================================

    @staticmethod
    def _interval(
        value: str,
    ) -> str:
        mapping = {
            "1M": "1m",
            "2M": "2m",
            "5M": "5m",
            "15M": "15m",
            "30M": "30m",
            "60M": "60m",
            "1H": "60m",
            "4H": "60m",
            "1D": "1d",
            "1W": "1wk",
            "1MO": "1mo",
        }

        key = (
            value
            .strip()
            .upper()
        )

        return mapping.get(
            key,
            value,
        )

    # ========================================================
    # YAHOO CHART REQUEST
    # ========================================================

    def _chart(
        self,
        symbol: str,
        range_: str,
        interval: str,
        ttl: int = 10,
    ) -> dict[str, Any]:
        provider_symbol = self._symbol(
            symbol
        )

        key = (
            provider_symbol,
            range_,
            interval,
        )

        now = monotonic()

        with self._lock:
            cached = self._cache.get(
                key
            )

            if (
                cached is not None
                and now - cached[0] <= ttl
            ):
                return cached[1]

        try:
            with httpx.Client(
                timeout=8.0,
                headers={
                    "User-Agent": "Mozilla/5.0"
                },
            ) as client:
                response = client.get(
                    self.CHART_URL.format(
                        symbol=provider_symbol
                    ),
                    params={
                        "range": range_,
                        "interval": interval,
                        "includePrePost": "false",
                        "events": "div,splits",
                    },
                )

                response.raise_for_status()
                payload = response.json()

        except httpx.HTTPError as exc:
            raise RuntimeError(
                "Yahoo market-data request "
                f"failed for {symbol}: {exc}"
            ) from exc

        chart = (
            payload.get("chart")
            or {}
        )

        error = chart.get("error")

        if error:
            raise RuntimeError(
                "Yahoo market-data error "
                f"for {symbol}: {error}"
            )

        results = (
            chart.get("result")
            or []
        )

        if not results:
            raise RuntimeError(
                "No market data returned "
                f"for {symbol}"
            )

        result = results[0]

        with self._lock:
            self._cache[key] = (
                now,
                result,
            )

        return result

    # ========================================================
    # FUNDAMENTAL METADATA
    # ========================================================

    @staticmethod
    def _raw_number(value: Any) -> float | None:
        if isinstance(value, dict):
            value = value.get("raw")

        try:
            if value is None:
                return None

            number = float(value)

            return None if number != number else number

        except (TypeError, ValueError):
            return None

    def _fundamentals(
        self,
        symbol: str,
        ttl: int = 300,
    ) -> dict[str, Any]:
        """
        Fetch equity/ETF fundamentals from Yahoo's crumb-gated
        quote endpoints.

        Yahoo's chart endpoint works without authentication, but
        v7 quote / v10 quoteSummary can require a session cookie
        plus crumb. We bootstrap both here and keep failures
        optional so quotes/charts never break.
        """

        asset_type = self._asset_type(symbol)

        if asset_type not in {
            "equity",
            "etf",
        }:
            return {}

        provider_symbol = self._symbol(symbol)
        now = monotonic()

        with self._lock:
            cached = self._fundamentals_cache.get(
                provider_symbol
            )

            if (
                cached is not None
                and now - cached[0] <= ttl
            ):
                return cached[1]

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }

        metadata: dict[str, Any] = {}

        try:
            with httpx.Client(
                timeout=10.0,
                headers=headers,
                follow_redirects=True,
            ) as client:
                # Bootstrap Yahoo session cookie.
                try:
                    client.get(
                        self.COOKIE_URL
                    )
                except httpx.HTTPError:
                    pass

                crumb_response = client.get(
                    self.CRUMB_URL
                )

                crumb_response.raise_for_status()

                crumb = (
                    crumb_response.text
                    .strip()
                )

                if (
                    not crumb
                    or crumb.startswith("<")
                    or "Unauthorized" in crumb
                ):
                    raise RuntimeError(
                        "Yahoo returned an invalid crumb"
                    )

                quote_response = client.get(
                    self.QUOTE_URL,
                    params={
                        "symbols": provider_symbol,
                        "crumb": crumb,
                        "region": "US",
                        "lang": "en-US",
                    },
                )

                quote_response.raise_for_status()

                quote_payload = quote_response.json()

                quote_root = (
                    quote_payload.get(
                        "quoteResponse"
                    )
                    or {}
                )

                quote_results = (
                    quote_root.get("result")
                    or []
                )

                if quote_results:
                    quote = (
                        quote_results[0]
                        or {}
                    )

                    trailing_pe = self._raw_number(
                        quote.get("trailingPE")
                    )

                    forward_pe = self._raw_number(
                        quote.get("forwardPE")
                    )

                    metadata = {
                        "market_cap": self._raw_number(
                            quote.get("marketCap")
                        ),
                        "pe_ratio": trailing_pe,
                        "trailing_pe": trailing_pe,
                        "forward_pe": forward_pe,
                        "fifty_two_week_high": self._raw_number(
                            quote.get("fiftyTwoWeekHigh")
                        ),
                        "fifty_two_week_low": self._raw_number(
                            quote.get("fiftyTwoWeekLow")
                        ),
                        "regular_market_volume": self._raw_number(
                            quote.get("regularMarketVolume")
                        ),
                        "fundamentals_source": "yahoo-finance-v7",
                    }

                needs_summary = (
                    not metadata
                    or metadata.get("market_cap") is None
                    or metadata.get("pe_ratio") is None
                )

                if needs_summary:
                    summary_response = client.get(
                        self.QUOTE_SUMMARY_URL.format(
                            symbol=provider_symbol
                        ),
                        params={
                            "modules": (
                                "price,summaryDetail,"
                                "defaultKeyStatistics,"
                                "financialData"
                            ),
                            "crumb": crumb,
                            "region": "US",
                            "lang": "en-US",
                            "formatted": "false",
                        },
                    )

                    summary_response.raise_for_status()
                    summary_payload = summary_response.json()

                    root = (
                        summary_payload.get(
                            "quoteSummary"
                        )
                        or {}
                    )

                    results = (
                        root.get("result")
                        or []
                    )

                    if results:
                        result = (
                            results[0]
                            or {}
                        )

                        price = (
                            result.get("price")
                            or {}
                        )

                        summary = (
                            result.get("summaryDetail")
                            or {}
                        )

                        stats = (
                            result.get(
                                "defaultKeyStatistics"
                            )
                            or {}
                        )

                        market_cap = (
                            self._raw_number(
                                price.get("marketCap")
                            )
                            or self._raw_number(
                                summary.get("marketCap")
                            )
                        )

                        trailing_pe = self._raw_number(
                            summary.get("trailingPE")
                        )

                        if trailing_pe is None:
                            trailing_pe = self._raw_number(
                                stats.get("trailingPE")
                            )

                        forward_pe = self._raw_number(
                            summary.get("forwardPE")
                        )

                        if forward_pe is None:
                            forward_pe = self._raw_number(
                                stats.get("forwardPE")
                            )

                        metadata.setdefault(
                            "market_cap",
                            market_cap,
                        )

                        if metadata.get("market_cap") is None:
                            metadata["market_cap"] = market_cap

                        if metadata.get("pe_ratio") is None:
                            metadata["pe_ratio"] = trailing_pe

                        if metadata.get("trailing_pe") is None:
                            metadata["trailing_pe"] = trailing_pe

                        if metadata.get("forward_pe") is None:
                            metadata["forward_pe"] = forward_pe

                        if metadata.get("fifty_two_week_high") is None:
                            metadata["fifty_two_week_high"] = self._raw_number(
                                summary.get("fiftyTwoWeekHigh")
                            )

                        if metadata.get("fifty_two_week_low") is None:
                            metadata["fifty_two_week_low"] = self._raw_number(
                                summary.get("fiftyTwoWeekLow")
                            )

                        if metadata.get("regular_market_volume") is None:
                            metadata["regular_market_volume"] = self._raw_number(
                                price.get("regularMarketVolume")
                            )

                        metadata[
                            "fundamentals_source"
                        ] = "yahoo-finance-authenticated"

        except (
            httpx.HTTPError,
            ValueError,
            RuntimeError,
        ):
            # Fundamentals are enrichment only.
            return {}

        if not metadata:
            return {}

        with self._lock:
            self._fundamentals_cache[
                provider_symbol
            ] = (
                now,
                metadata,
            )

        return metadata

    # ========================================================
    # BAR DATA
    # ========================================================

    def bars(
        self,
        symbol: str,
        range_: str = "3M",
        timeframe: str = "1D",
    ) -> list[dict[str, Any]]:
        requested_timeframe = timeframe.strip().upper()

        normalized_range = self._range(
            range_
        )

        normalized_interval = self._interval(
            timeframe
        )

        ttl = (
            self.CACHE_TTL_INTRADAY
            if normalized_interval in {
                "1m",
                "2m",
                "5m",
                "15m",
                "30m",
                "60m",
            }
            else self.CACHE_TTL_DAILY
        )

        result = self._chart(
            symbol=symbol,
            range_=normalized_range,
            interval=normalized_interval,
            ttl=ttl,
        )

        timestamps = (
            result.get("timestamp")
            or []
        )

        indicators = (
            result.get("indicators")
            or {}
        )

        quotes = (
            indicators.get("quote")
            or [{}]
        )

        quote = quotes[0]

        output: list[
            dict[str, Any]
        ] = []

        for index, raw_timestamp in enumerate(timestamps):
            def value(
                key: str,
            ) -> Any:
                values = (
                    quote.get(key)
                    or []
                )

                if index >= len(values):
                    return None

                return values[index]

            open_value = value("open")
            high_value = value("high")
            low_value = value("low")
            close_value = value("close")
            volume_value = value("volume")

            # Never fabricate an OHLC candle.
            if (
                open_value is None
                or high_value is None
                or low_value is None
                or close_value is None
            ):
                continue

            timestamp = datetime.fromtimestamp(
                int(raw_timestamp),
                tz=timezone.utc,
            )

            normalized_volume = (
                float(volume_value)
                if volume_value is not None
                else None
            )

            output.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "time": int(raw_timestamp),
                    "open": float(open_value),
                    "high": float(high_value),
                    "low": float(low_value),
                    "close": float(close_value),
                    "volume": normalized_volume,
                    "timeframe": requested_timeframe,
                }
            )

        if not output:
            raise RuntimeError(
                "No usable OHLCV bars "
                f"returned for {symbol}"
            )

        if requested_timeframe == "4H":
            output = self._aggregate_four_hour_bars(
                output
            )

        return output

    # ========================================================
    # 4-HOUR BARS
    # ========================================================

    @staticmethod
    def _aggregate_four_hour_bars(
        bars: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Build 4-hour candles from genuine Yahoo 60-minute candles.

        No prices are interpolated or generated.
        """

        if not bars:
            return []

        grouped: dict[
            tuple[int, int, int, int],
            list[dict[str, Any]],
        ] = {}

        for bar in bars:
            raw_time = bar.get("time")

            if raw_time is None:
                continue

            timestamp = datetime.fromtimestamp(
                int(raw_time),
                tz=timezone.utc,
            )

            four_hour_bucket = (
                timestamp.hour // 4
            ) * 4

            key = (
                timestamp.year,
                timestamp.month,
                timestamp.day,
                four_hour_bucket,
            )

            grouped.setdefault(
                key,
                [],
            ).append(bar)

        output: list[dict[str, Any]] = []

        for group in grouped.values():
            group.sort(
                key=lambda item: int(item["time"])
            )

            first = group[0]
            last = group[-1]

            volumes = [
                float(item["volume"])
                for item in group
                if item.get("volume") is not None
            ]

            output.append(
                {
                    "timestamp": first["timestamp"],
                    "time": int(first["time"]),
                    "open": float(first["open"]),
                    "high": max(
                        float(item["high"])
                        for item in group
                    ),
                    "low": min(
                        float(item["low"])
                        for item in group
                    ),
                    "close": float(last["close"]),
                    "volume": (
                        sum(volumes)
                        if volumes
                        else None
                    ),
                    "timeframe": "4H",
                }
            )

        output.sort(
            key=lambda item: int(item["time"])
        )

        return output

    # ========================================================
    # LATEST CHART CANDLE
    # ========================================================

    def latest_bar(
        self,
        symbol: str,
        timeframe: str = "1M",
    ) -> dict[str, Any]:
        """
        Return the latest genuine provider-backed candle.

        Yahoo is currently polled. This is not an exchange-native
        tick stream.
        """

        requested_timeframe = (
            timeframe
            .strip()
            .upper()
        )

        range_by_timeframe = {
            "1M": "1D",
            "2M": "5D",
            "5M": "5D",
            "15M": "5D",
            "30M": "1M",
            "60M": "1M",
            "1H": "1M",
            "4H": "1M",
            "1D": "1M",
            "1W": "1Y",
            "1MO": "5Y",
        }

        range_ = range_by_timeframe.get(
            requested_timeframe,
            "5D",
        )

        bars = self.bars(
            symbol,
            range_,
            requested_timeframe,
        )

        if not bars:
            raise RuntimeError(
                "No latest candle available "
                f"for {symbol}"
            )

        latest = dict(
            bars[-1]
        )

        latest.update(
            {
                "symbol": symbol.strip().upper(),
                "source": "yahoo-finance",
                "provider_mode": "polled",
                "real_time_stream": False,
                "simulated": False,
                "automatic_execution_safe": False,
            }
        )

        return latest

    # ========================================================
    # SUPPORT / RESISTANCE
    # ========================================================

    def support_resistance(
        self,
        symbol: str,
        range_: str = "6M",
        timeframe: str = "1D",
        lookback: int = 120,
    ) -> dict[str, Any]:
        """
        Calculate technical support and resistance from genuine
        provider-backed OHLC candles.

        These levels are technical calculations, not guaranteed
        future prices or trade recommendations.
        """

        bars = self.bars(
            symbol,
            range_,
            timeframe,
        )

        safe_lookback = max(
            10,
            min(
                int(lookback),
                1000,
            ),
        )

        sample = bars[
            -safe_lookback:
        ]

        if len(sample) < 5:
            raise RuntimeError(
                "Insufficient bars for "
                f"support/resistance: {symbol}"
            )

        latest_close = float(
            sample[-1]["close"]
        )

        swing_lows: list[float] = []
        swing_highs: list[float] = []

        for index in range(
            2,
            len(sample) - 2,
        ):
            current_low = float(
                sample[index]["low"]
            )

            current_high = float(
                sample[index]["high"]
            )

            surrounding_lows = [
                float(sample[index - 2]["low"]),
                float(sample[index - 1]["low"]),
                float(sample[index + 1]["low"]),
                float(sample[index + 2]["low"]),
            ]

            surrounding_highs = [
                float(sample[index - 2]["high"]),
                float(sample[index - 1]["high"]),
                float(sample[index + 1]["high"]),
                float(sample[index + 2]["high"]),
            ]

            if current_low <= min(
                surrounding_lows
            ):
                swing_lows.append(
                    current_low
                )

            if current_high >= max(
                surrounding_highs
            ):
                swing_highs.append(
                    current_high
                )

        supports = sorted(
            {
                round(value, 8)
                for value in swing_lows
                if value < latest_close
            },
            reverse=True,
        )[:3]

        resistances = sorted(
            {
                round(value, 8)
                for value in swing_highs
                if value > latest_close
            }
        )[:3]

        if not supports:
            supports = [
                round(
                    min(
                        float(bar["low"])
                        for bar in sample
                    ),
                    8,
                )
            ]

        if not resistances:
            resistances = [
                round(
                    max(
                        float(bar["high"])
                        for bar in sample
                    ),
                    8,
                )
            ]

        return {
            "symbol": symbol.strip().upper(),
            "range": range_.upper(),
            "timeframe": timeframe.upper(),
            "latest_close": latest_close,
            "support": supports,
            "resistance": resistances,
            "lookback_bars": len(sample),
            "method": "five-bar-swing-pivots",
            "source": "yahoo-finance",
            "simulated": False,
            "trade_recommendation": False,
        }

    # ========================================================
    # CORPORATE CHART EVENTS
    # ========================================================

    def corporate_events(
        self,
        symbol: str,
        range_: str = "5Y",
    ) -> dict[str, Any]:
        """
        Return provider-confirmed dividend and split events.

        No future news or unscheduled event is fabricated.
        """

        result = self._chart(
            symbol=symbol,
            range_=self._range(
                range_
            ),
            interval="1d",
            ttl=self.CACHE_TTL_DAILY,
        )

        raw_events = (
            result.get("events")
            or {}
        )

        events: list[
            dict[str, Any]
        ] = []

        for (
            event_type,
            collection,
        ) in raw_events.items():
            if not isinstance(
                collection,
                dict,
            ):
                continue

            for raw_event in collection.values():
                if not isinstance(
                    raw_event,
                    dict,
                ):
                    continue

                raw_timestamp = raw_event.get(
                    "date"
                )

                if raw_timestamp is None:
                    continue

                timestamp = int(
                    raw_timestamp
                )

                event: dict[str, Any] = {
                    "type": event_type,
                    "time": timestamp,
                    "timestamp": datetime.fromtimestamp(
                        timestamp,
                        tz=timezone.utc,
                    ).isoformat(),
                    "source": "yahoo-finance",
                }

                if event_type == "dividends":
                    event["amount"] = (
                        raw_event.get("amount")
                    )

                if event_type == "splits":
                    event["numerator"] = (
                        raw_event.get("numerator")
                    )

                    event["denominator"] = (
                        raw_event.get("denominator")
                    )

                    event["split_ratio"] = (
                        raw_event.get("splitRatio")
                    )

                events.append(
                    event
                )

        events.sort(
            key=lambda event: event["time"]
        )

        return {
            "symbol": symbol.strip().upper(),
            "range": range_.upper(),
            "events": events,
            "source": "yahoo-finance",
            "simulated": False,
        }

    # ========================================================
    # CURRENT QUOTE
    # ========================================================

    def quote(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        result = self._chart(
            symbol=symbol,
            range_="1d",
            interval="1m",
            ttl=5,
        )

        meta = (
            result.get("meta")
            or {}
        )

        price = meta.get(
            "regularMarketPrice"
        )

        if price is None:
            indicators = (
                result.get("indicators")
                or {}
            )

            quote = (
                indicators.get("quote")
                or [{}]
            )[0]

            closes = (
                quote.get("close")
                or []
            )

            price = next(
                (
                    value
                    for value in reversed(closes)
                    if value is not None
                ),
                None,
            )

        if price is None:
            raise RuntimeError(
                "No current price available "
                f"for {symbol}"
            )

        price_value = float(
            price
        )

        previous_close = meta.get(
            "chartPreviousClose"
        )

        if previous_close is None:
            previous_close = meta.get(
                "previousClose"
            )

        previous_close_value: float | None = None
        change_value: float | None = None
        change_percent_value: float | None = None

        try:
            if previous_close is not None:
                candidate = float(
                    previous_close
                )

                if candidate > 0:
                    previous_close_value = candidate

                    change_value = (
                        price_value
                        - previous_close_value
                    )

                    change_percent_value = (
                        change_value
                        / previous_close_value
                        * 100.0
                    )

        except (
            TypeError,
            ValueError,
        ):
            previous_close_value = None
            change_value = None
            change_percent_value = None

        market_time = meta.get(
            "regularMarketTime"
        )

        if market_time:
            as_of = (
                datetime.fromtimestamp(
                    int(market_time),
                    tz=timezone.utc,
                )
                .isoformat()
            )

        else:
            timestamps = (
                result.get("timestamp")
                or []
            )

            if not timestamps:
                raise RuntimeError(
                    "Yahoo quote has no "
                    "provider timestamp "
                    f"for {symbol}"
                )

            as_of = (
                datetime.fromtimestamp(
                    int(timestamps[-1]),
                    tz=timezone.utc,
                )
                .isoformat()
            )

        fundamentals = self._fundamentals(
            symbol
        )

        return {
            "symbol": symbol.strip().upper(),
            "asset_type": self._asset_type(symbol),
            "price": price_value,
            "previous_close": previous_close_value,
            "change": change_value,
            "change_percent": change_percent_value,
            "currency": meta.get(
                "currency",
                "USD",
            ),
            "exchange": meta.get(
                "exchangeName"
            ),
            "market_state": meta.get(
                "marketState"
            ),
            "as_of": as_of,
            "market_cap": fundamentals.get(
                "market_cap"
            ),
            "pe_ratio": fundamentals.get(
                "pe_ratio"
            ),
            "trailing_pe": fundamentals.get(
                "trailing_pe"
            ),
            "forward_pe": fundamentals.get(
                "forward_pe"
            ),
            "fifty_two_week_high": fundamentals.get(
                "fifty_two_week_high"
            ),
            "fifty_two_week_low": fundamentals.get(
                "fifty_two_week_low"
            ),
            "regular_market_volume": fundamentals.get(
                "regular_market_volume"
            ),
            "source": "yahoo-finance",
            "provider_mode": "polled",
            "real_time_stream": False,
            "simulated": False,
            "automatic_execution_safe": False,
        }

    # ========================================================
    # VOLUME REFERENCE
    # ========================================================

    @staticmethod
    def _volume_reference(
        bars: list[dict[str, Any]],
    ) -> tuple[
        float | None,
        str | None,
        bool,
    ]:
        """
        Find the most recent usable positive-volume bar.

        Returns:
            volume
            timestamp
            fallback_used

        We never invent or estimate volume.
        """

        if not bars:
            return (
                None,
                None,
                False,
            )

        latest = bars[-1]

        latest_volume = latest.get(
            "volume"
        )

        try:
            if (
                latest_volume is not None
                and float(latest_volume) > 0
            ):
                return (
                    float(latest_volume),
                    latest.get("timestamp"),
                    False,
                )

        except (
            TypeError,
            ValueError,
        ):
            pass

        for bar in reversed(
            bars[:-1]
        ):
            raw_volume = bar.get(
                "volume"
            )

            try:
                if (
                    raw_volume is not None
                    and float(raw_volume) > 0
                ):
                    return (
                        float(raw_volume),
                        bar.get("timestamp"),
                        True,
                    )

            except (
                TypeError,
                ValueError,
            ):
                continue

        return (
            None,
            None,
            True,
        )

    # ========================================================
    # MARKET CONTEXT
    # ========================================================

    def context(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        normalized_symbol = (
            symbol
            .strip()
            .upper()
        )

        if not normalized_symbol:
            raise ValueError(
                "Symbol is required"
            )

        intraday_bars = self.bars(
            normalized_symbol,
            self.DEFAULT_INTRADAY_RANGE,
            self.DEFAULT_INTRADAY_TIMEFRAME,
        )

        if len(intraday_bars) < 50:
            raise RuntimeError(
                "Insufficient intraday data "
                f"for {normalized_symbol}: "
                "requires at least 50 bars, "
                f"received {len(intraday_bars)}"
            )

        features = feature_snapshot(
            intraday_bars
        )

        latest_bar_timestamp = (
            intraday_bars[-1]
            .get("timestamp")
        )

        if not latest_bar_timestamp:
            raise RuntimeError(
                "Latest market bar has no "
                "timestamp for "
                f"{normalized_symbol}"
            )

        (
            reference_volume,
            volume_as_of,
            volume_fallback_used,
        ) = self._volume_reference(
            intraday_bars
        )

        raw_latest_volume = (
            intraday_bars[-1]
            .get("volume")
        )

        latest_volume_usable = False

        try:
            latest_volume_usable = (
                raw_latest_volume is not None
                and float(raw_latest_volume) > 0
            )

        except (
            TypeError,
            ValueError,
        ):
            latest_volume_usable = False

        if (
            not latest_volume_usable
            and reference_volume is not None
        ):
            features["volume"] = (
                reference_volume
            )

            average_volume = features.get(
                "average_volume"
            )

            try:
                average_volume_value = float(
                    average_volume
                )

                if average_volume_value > 0:
                    features["volume_ratio"] = (
                        reference_volume
                        / average_volume_value
                    )
                else:
                    features["volume_ratio"] = None

            except (
                TypeError,
                ValueError,
            ):
                features["volume_ratio"] = None

        daily_bars = self.bars(
            normalized_symbol,
            self.DEFAULT_HISTORY_RANGE,
            self.DEFAULT_HISTORY_TIMEFRAME,
        )

        daily_closes = [
            float(
                bar["close"]
            )
            for bar in daily_bars
            if bar.get("close") is not None
        ]

        features["daily_ema50"] = (
            ema(
                daily_closes,
                50,
            )
            if len(daily_closes) >= 50
            else None
        )

        features["daily_ema200"] = (
            ema(
                daily_closes,
                200,
            )
            if len(daily_closes) >= 200
            else None
        )

        fundamentals = self._fundamentals(
            normalized_symbol
        )

        return {
            "symbol": normalized_symbol,
            "asset_type": self._asset_type(
                normalized_symbol
            ),
            **features,
            "market_cap": fundamentals.get(
                "market_cap"
            ),
            "pe_ratio": fundamentals.get(
                "pe_ratio"
            ),
            "trailing_pe": fundamentals.get(
                "trailing_pe"
            ),
            "forward_pe": fundamentals.get(
                "forward_pe"
            ),
            "fifty_two_week_high": fundamentals.get(
                "fifty_two_week_high"
            ),
            "fifty_two_week_low": fundamentals.get(
                "fifty_two_week_low"
            ),
            "regular_market_volume": fundamentals.get(
                "regular_market_volume"
            ),
            "volume_as_of": volume_as_of,
            "volume_fallback_used": volume_fallback_used,
            "bars": intraday_bars[-200:],
            "timeframe": self.DEFAULT_INTRADAY_TIMEFRAME,
            "history_timeframe": self.DEFAULT_HISTORY_TIMEFRAME,
            "as_of": latest_bar_timestamp,
            "source": "yahoo-finance",
            "sources": [
                "yahoo-finance"
            ],
            "source_count": 1,
            "simulated": False,
            "provider_healthy": True,
            "provider_mode": "polled",
            "real_time_stream": False,

            # Yahoo remains scanning/intelligence data only.
            "automatic_execution_safe": False,
        }

    # ========================================================
    # STATUS
    # ========================================================

    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "provider": "yahoo-finance",
            "provider_mode": "polled",
            "real_time_stream": False,
            "intraday_timeframe": self.DEFAULT_INTRADAY_TIMEFRAME,
            "supports_five_year_history": True,
            "supports_latest_candle": True,
            "supports_corporate_events": True,
            "simulated": False,
            "automatic_execution_safe": False,
            "cache": "enabled",
        }


market_service = MarketService()