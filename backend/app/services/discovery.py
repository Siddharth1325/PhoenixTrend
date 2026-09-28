from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from math import isfinite
from threading import RLock
from time import monotonic
from typing import Any, Iterable, Mapping, Sequence

from .candidate_ranker import candidate_ranker
from .decision_engine import decision_engine
from .market import market_service


class DiscoveryService:
    """
    PhoenixTrend read-only discovery and market-scanner service.

    Responsibilities
    ----------------
    * Build or accept a symbol universe.
    * Retrieve real provider-backed market context.
    * Run PhoenixTrend DecisionEngine analysis.
    * Normalize scanner output without inventing missing market values.
    * Rank candidates through the shared CandidateRanker.
    * Surface provider/data failures explicitly.
    * Keep unsupported data products clearly unavailable.
    * Never place orders or authorize execution.

    Discovery is intentionally separate from execution.

    A BUY/SELL result returned by this service is an analytical decision only.
    Automatic execution must still pass the normal PhoenixTrend safety, risk,
    broker-capability and execution pipeline.

    No missing price, volume, spread, liquidity, P&L, pattern, strategy,
    confidence, options-flow, earnings date, IPO date, or other observation is
    fabricated by this service.
    """

    MAX_SCAN_SYMBOLS = 250
    DEFAULT_RESULT_LIMIT = 50
    MAX_RESULT_LIMIT = 250
    DEFAULT_WORKERS = 8
    MAX_WORKERS = 16

    ACTION_BUY = "BUY"
    ACTION_SELL = "SELL"
    ACTION_HOLD = "HOLD"

    STATUS_OK = "ok"
    STATUS_ERROR = "error"
    STATUS_UNAVAILABLE = "unavailable"

    # -------------------------------------------------------------------------
    # These are discovery seed universes only.
    #
    # They are NOT claims that these symbols are currently the best movers,
    # unusual-volume names, earnings names, option-flow leaders, etc.
    #
    # When a broker/provider-backed universe is supplied by the caller, that
    # universe takes precedence.
    # -------------------------------------------------------------------------

    CATEGORY_UNIVERSES: dict[str, list[str]] = {
        "prebuilt": [
            "NVDA",
            "AAPL",
            "MSFT",
            "AMZN",
            "META",
            "GOOGL",
            "TSLA",
            "AMD",
            "AVGO",
            "NFLX",
            "JPM",
            "XOM",
        ],
        "ai": [
            "NVDA",
            "AAPL",
            "MSFT",
            "AMZN",
            "META",
            "GOOGL",
            "TSLA",
            "AMD",
            "AVGO",
            "NFLX",
            "JPM",
            "XOM",
        ],
        "options-flow": [
            "NVDA",
            "AAPL",
            "MSFT",
            "TSLA",
            "AMD",
            "AMZN",
            "META",
            "GOOGL",
            "NFLX",
            "SPY",
            "QQQ",
            "IWM",
        ],
        "unusual-activity": [
            "NVDA",
            "TSLA",
            "AMD",
            "PLTR",
            "SOFI",
            "AAPL",
            "AMZN",
            "META",
            "NFLX",
            "COIN",
            "MSTR",
            "AVGO",
        ],
        "earnings": [
            "AAPL",
            "MSFT",
            "NVDA",
            "AMZN",
            "META",
            "GOOGL",
            "TSLA",
            "NFLX",
            "AMD",
            "AVGO",
            "JPM",
            "XOM",
        ],
        "ipo": [
            "RDDT",
            "ARM",
            "CAVA",
            "BIRK",
            "CART",
            "KVYO",
        ],
        "sectors": [
            "XLK",
            "XLF",
            "XLE",
            "XLV",
            "XLY",
            "XLI",
            "XLP",
            "XLU",
            "XLRE",
            "XLB",
            "XLC",
        ],
        "etfs": [
            "SPY",
            "QQQ",
            "IWM",
            "DIA",
            "VTI",
            "VOO",
            "ARKK",
            "SMH",
            "XLF",
            "XLE",
            "XLV",
            "GLD",
        ],
        "crypto": [
            "BTC-USD",
            "ETH-USD",
            "SOL-USD",
            "XRP-USD",
            "DOGE-USD",
            "ADA-USD",
        ],
    }

    CATEGORY_META: dict[str, dict[str, Any]] = {
        "prebuilt": {
            "title": "Pre-Built Scanners",
            "mode": "decision_engine",
            "asset_class": "stocks",
            "supported": True,
            "note": (
                "PhoenixTrend analysis over the configured discovery universe. "
                "Returned market observations come from the connected market "
                "and DecisionEngine pipeline."
            ),
        },
        "ai": {
            "title": "AI Scan (NETRA)",
            "mode": "decision_engine",
            "asset_class": "stocks",
            "supported": True,
            "note": (
                "PhoenixTrend DecisionEngine analysis ranked using confirmed "
                "decision and market fields."
            ),
        },
        "options-flow": {
            "title": "Options Flow",
            "mode": "options_candidates",
            "asset_class": "options",
            "supported": False,
            "note": (
                "Dedicated options-flow/tape data is not connected to this "
                "service. PhoenixTrend will not fabricate options-flow events."
            ),
        },
        "unusual-activity": {
            "title": "Unusual Activity",
            "mode": "unusual_volume",
            "asset_class": "stocks",
            "supported": True,
            "note": (
                "Provider-backed unusual-volume observations only. Dedicated "
                "options-flow and block-trade tape events are not fabricated."
            ),
        },
        "earnings": {
            "title": "Earnings",
            "mode": "earnings_watch",
            "asset_class": "stocks",
            "supported": True,
            "note": (
                "DecisionEngine analysis over the configured earnings-watch "
                "universe. Earnings dates are shown only when supplied by a "
                "connected provider."
            ),
        },
        "ipo": {
            "title": "IPO",
            "mode": "ipo_watch",
            "asset_class": "stocks",
            "supported": True,
            "note": (
                "DecisionEngine analysis over the configured recent-listing "
                "watch universe. Listing dates are not fabricated."
            ),
        },
        "sectors": {
            "title": "Sectors",
            "mode": "sector_etfs",
            "asset_class": "etfs",
            "supported": True,
            "note": (
                "Sector analysis represented through configured sector ETFs "
                "using real market and DecisionEngine data."
            ),
        },
        "etfs": {
            "title": "ETFs",
            "mode": "etf_scan",
            "asset_class": "etfs",
            "supported": True,
            "note": (
                "PhoenixTrend analysis of the configured ETF universe using "
                "the connected market pipeline."
            ),
        },
        "crypto": {
            "title": "Crypto",
            "mode": "crypto_scan",
            "asset_class": "crypto",
            "supported": True,
            "note": (
                "PhoenixTrend analysis of configured crypto symbols using "
                "provider-backed market data."
            ),
        },
    }

    CATEGORY_ALIASES: dict[str, str] = {
        "ai-scan-netra": "ai",
        "netra": "ai",
        "ai-scan": "ai",
        "options": "options-flow",
        "option-flow": "options-flow",
        "optionsflow": "options-flow",
        "unusual": "unusual-activity",
        "activity": "unusual-activity",
        "sector": "sectors",
        "sector-etfs": "sectors",
        "etf": "etfs",
        "cryptocurrency": "crypto",
        "cryptocurrencies": "crypto",
    }

    def __init__(self) -> None:
        self._lock = RLock()

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def scan(
        self,
        symbols: list[str],
        *,
        limit: int | None = None,
        workers: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Analyze and rank a supplied symbol universe.

        The universe is bounded by MAX_SCAN_SYMBOLS. Ranking is delegated to the
        shared CandidateRanker so discovery and automation can use the same
        candidate-ranking semantics.
        """

        normalized_symbols = self._normalize_symbols(symbols)[
            : self.MAX_SCAN_SYMBOLS
        ]

        if not normalized_symbols:
            return []

        safe_workers = self._normalize_workers(
            workers,
            len(normalized_symbols),
        )

        results: list[dict[str, Any]] = []

        if safe_workers <= 1:
            for symbol in normalized_symbols:
                results.append(
                    self._scan_symbol(symbol)
                )
        else:
            with ThreadPoolExecutor(
                max_workers=safe_workers,
                thread_name_prefix="phoenix-discovery",
            ) as executor:
                futures = {
                    executor.submit(
                        self._scan_symbol,
                        symbol,
                    ): symbol
                    for symbol in normalized_symbols
                }

                for future in as_completed(futures):
                    symbol = futures[future]

                    try:
                        result = future.result()
                    except Exception as exc:
                        result = self._error_result(
                            symbol,
                            exc,
                        )

                    results.append(result)

        ordered = self._rank(results)

        if limit is not None:
            safe_limit = self._normalize_limit(
                limit,
                maximum=self.MAX_RESULT_LIMIT,
                minimum=0,
            )
            ordered = ordered[:safe_limit]

        return ordered

    def scan_category(
        self,
        category: str,
        symbols: list[str] | None = None,
        *,
        limit: int | None = None,
        workers: int | None = None,
    ) -> dict[str, Any]:
        """
        Scan one discovery category.

        Caller-supplied symbols take precedence over the configured seed
        universe. Unsupported data products fail closed rather than being
        represented by synthetic observations.
        """

        normalized_category = self._normalize_category(
            category
        )

        meta = dict(
            self.CATEGORY_META[
                normalized_category
            ]
        )

        universe = (
            self._normalize_symbols(symbols)
            if symbols
            else list(
                self.CATEGORY_UNIVERSES[
                    normalized_category
                ]
            )
        )

        universe = universe[
            : self.MAX_SCAN_SYMBOLS
        ]

        if not bool(
            meta.get(
                "supported",
                True,
            )
        ):
            return {
                "category": normalized_category,
                **meta,
                "symbols": universe,
                "results": [],
                "status": self.STATUS_UNAVAILABLE,
                "result_count": 0,
                "error_count": 0,
            }

        if normalized_category == "unusual-activity":
            unusual = self.unusual_activity(
                symbols=universe,
                limit=(
                    limit
                    if limit is not None
                    else self.DEFAULT_RESULT_LIMIT
                ),
            )

            return {
                "category": normalized_category,
                **meta,
                "symbols": universe,
                "results": unusual.get(
                    "events",
                    [],
                ),
                "events": unusual.get(
                    "events",
                    [],
                ),
                "errors": unusual.get(
                    "errors",
                    [],
                ),
                "status": self.STATUS_OK,
                "result_count": len(
                    unusual.get(
                        "events",
                        [],
                    )
                ),
                "error_count": len(
                    unusual.get(
                        "errors",
                        [],
                    )
                ),
                "minimum_ratio": unusual.get(
                    "minimum_ratio"
                ),
                "source": unusual.get(
                    "source"
                ),
                "simulated": False,
            }

        results = self.scan(
            universe,
            limit=limit,
            workers=workers,
        )

        return {
            "category": normalized_category,
            **meta,
            "symbols": universe,
            "results": results,
            "status": self.STATUS_OK,
            "result_count": len(results),
            "error_count": sum(
                1
                for item in results
                if item.get("status")
                != self.STATUS_OK
            ),
        }

    def unusual_activity(
        self,
        symbols: list[str] | None = None,
        min_ratio: float = 1.5,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Return provider-backed unusual-volume events.

        This method does not claim to provide options flow, dark-pool flow,
        block trades, sweeps, tape prints, or institutional order flow.
        """

        universe = (
            self._normalize_symbols(symbols)
            if symbols
            else list(
                self.CATEGORY_UNIVERSES[
                    "unusual-activity"
                ]
            )
        )[
            : self.MAX_SCAN_SYMBOLS
        ]

        safe_ratio = self._positive_number(
            min_ratio
        )

        if safe_ratio is None:
            raise ValueError(
                "min_ratio must be a finite non-negative number"
            )

        safe_limit = self._normalize_limit(
            limit,
            maximum=100,
            minimum=1,
        )

        events: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        observed_sources: set[str] = set()

        for symbol in universe:
            try:
                market = market_service.context(
                    symbol
                )

                if not isinstance(
                    market,
                    Mapping,
                ):
                    raise RuntimeError(
                        "Market provider returned an invalid context payload"
                    )

                market_dict = dict(
                    market
                )

                ratio = self._first_number(
                    market_dict,
                    "volume_ratio",
                    "relative_volume",
                    "relative_volume_ratio",
                )

                volume = self._first_number(
                    market_dict,
                    "volume",
                    "regular_market_volume",
                )

                average_volume = self._first_number(
                    market_dict,
                    "average_volume",
                    "avg_volume",
                    "average_daily_volume",
                )

                if (
                    ratio is None
                    and volume is not None
                    and average_volume is not None
                    and average_volume > 0
                ):
                    ratio = (
                        volume
                        / average_volume
                    )

                as_of = self._first_value(
                    market_dict,
                    "volume_as_of",
                    "as_of",
                    "timestamp",
                    "market_timestamp",
                )

                source = self._first_text(
                    market_dict,
                    "source",
                    "provider",
                    "market_provider",
                )

                if source:
                    observed_sources.add(
                        source
                    )

                if ratio is None:
                    continue

                if ratio < safe_ratio:
                    continue

                # An unusual-volume event without an observation timestamp is
                # not surfaced as current provider-backed activity.
                if not as_of:
                    continue

                event: dict[str, Any] = {
                    "time": str(as_of),
                    "symbol": symbol,
                    "type": "Volume",
                    "details": (
                        f"{ratio:.2f}x average volume"
                    ),
                    "volume_ratio": ratio,
                    "volume": volume,
                    "average_volume": average_volume,
                    "source": source,
                    "simulated": False,
                    "automatic_execution_safe": False,
                    "status": self.STATUS_OK,
                }

                price = self._first_number(
                    market_dict,
                    "price",
                    "regular_market_price",
                    "close",
                    "last",
                )

                if price is not None:
                    event["price"] = price

                change_percent = self._extract_change_percent(
                    market_dict
                )

                if change_percent is not None:
                    event[
                        "change_percent"
                    ] = change_percent

                events.append(
                    event
                )

            except Exception as exc:
                errors.append(
                    {
                        "symbol": symbol,
                        "error": self._safe_error(
                            exc
                        ),
                    }
                )

        events.sort(
            key=lambda item: (
                -self._sortable_number(
                    item.get(
                        "volume_ratio"
                    )
                ),
                str(
                    item.get(
                        "symbol"
                    )
                    or ""
                ),
            )
        )

        source: str | list[str] | None

        if not observed_sources:
            source = None
        elif len(observed_sources) == 1:
            source = next(
                iter(
                    observed_sources
                )
            )
        else:
            source = sorted(
                observed_sources
            )

        return {
            "type": "unusual-volume",
            "note": (
                "Provider-backed unusual-volume observations only. "
                "Options-flow, block-trade and dark-pool events are not shown "
                "without a dedicated connected data source."
            ),
            "minimum_ratio": safe_ratio,
            "source": source,
            "simulated": False,
            "events": events[
                :safe_limit
            ],
            "errors": errors,
        }

    def evaluate(
        self,
        symbol: str,
        strategy_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Return the DecisionEngine analysis for one symbol.

        When strategy_name is supplied, the requested strategy evaluation is
        extracted from the DecisionEngine evaluation collection. The service
        does not synthesize a strategy result when that strategy was not
        evaluated.
        """

        normalized_symbol = self._normalize_symbol(
            symbol
        )

        if not normalized_symbol:
            raise ValueError(
                "symbol is required"
            )

        decision = decision_engine.analyze(
            normalized_symbol
        )

        if not isinstance(
            decision,
            Mapping,
        ):
            raise RuntimeError(
                "DecisionEngine returned an invalid payload"
            )

        decision_dict = dict(
            decision
        )

        if not strategy_name:
            return decision_dict

        requested = str(
            strategy_name
        ).strip()

        if not requested:
            return decision_dict

        requested_key = requested.lower()

        evaluations = decision_dict.get(
            "evaluations"
        )

        if not isinstance(
            evaluations,
            list,
        ):
            evaluations = []

        evaluation = next(
            (
                item
                for item in evaluations
                if (
                    isinstance(
                        item,
                        Mapping,
                    )
                    and str(
                        item.get(
                            "strategy",
                            ""
                        )
                    )
                    .strip()
                    .lower()
                    == requested_key
                )
            ),
            None,
        )

        return {
            "symbol": normalized_symbol,
            "requested_strategy": requested,
            "found": evaluation is not None,
            "evaluation": (
                dict(
                    evaluation
                )
                if isinstance(
                    evaluation,
                    Mapping,
                )
                else None
            ),
            "decision": decision_dict,
        }

    def categories(
        self,
    ) -> list[dict[str, Any]]:
        """
        Return discovery-category capabilities without performing a scan.
        """

        output: list[dict[str, Any]] = []

        for category in self.CATEGORY_UNIVERSES:
            meta = dict(
                self.CATEGORY_META[
                    category
                ]
            )

            output.append(
                {
                    "category": category,
                    **meta,
                    "configured_symbols": len(
                        self.CATEGORY_UNIVERSES[
                            category
                        ]
                    ),
                }
            )

        return output

    def category_status(
        self,
        category: str,
    ) -> dict[str, Any]:
        normalized = self._normalize_category(
            category
        )

        return {
            "category": normalized,
            **dict(
                self.CATEGORY_META[
                    normalized
                ]
            ),
            "configured_symbols": list(
                self.CATEGORY_UNIVERSES[
                    normalized
                ]
            ),
        }

    # =========================================================================
    # SYMBOL SCANNING
    # =========================================================================

    def _scan_symbol(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        started = monotonic()

        try:
            decision = decision_engine.analyze(
                symbol
            )

            if not isinstance(
                decision,
                Mapping,
            ):
                raise RuntimeError(
                    "DecisionEngine returned an invalid payload"
                )

            decision_dict = dict(
                decision
            )

            selected = self._mapping(
                decision_dict.get(
                    "selected"
                )
            )

            selection = self._mapping(
                decision_dict.get(
                    "selection"
                )
            )

            market = self._mapping(
                decision_dict.get(
                    "market"
                )
            )

            patterns = self._list(
                decision_dict.get(
                    "patterns"
                )
            )

            confidence = self._extract_confidence(
                decision_dict,
                selected,
                selection,
            )

            strategy = self._first_nonempty(
                decision_dict.get(
                    "strategy"
                ),
                selected.get(
                    "strategy"
                ),
                selected.get(
                    "name"
                ),
                selection.get(
                    "selected_strategy"
                ),
                selection.get(
                    "strategy"
                ),
            )

            action = self._normalize_action(
                self._first_nonempty(
                    decision_dict.get(
                        "action"
                    ),
                    decision_dict.get(
                        "decision"
                    ),
                    selected.get(
                        "action"
                    ),
                    selected.get(
                        "signal"
                    ),
                    self.ACTION_HOLD,
                )
            )

            price = self._first_number(
                market,
                "price",
                "regular_market_price",
                "close",
                "last",
                "last_price",
            )

            previous_close = self._first_number(
                market,
                "previous_close",
                "regular_market_previous_close",
                "prev_close",
            )

            change_percent = self._extract_change_percent(
                market
            )

            if (
                change_percent is None
                and price is not None
                and previous_close is not None
                and previous_close != 0
            ):
                change_percent = (
                    (
                        price
                        - previous_close
                    )
                    / previous_close
                ) * 100.0

            volume = self._first_number(
                market,
                "volume",
                "regular_market_volume",
            )

            average_volume = self._first_number(
                market,
                "average_volume",
                "avg_volume",
                "average_daily_volume",
            )

            volume_ratio = self._first_number(
                market,
                "volume_ratio",
                "relative_volume",
                "relative_volume_ratio",
            )

            if (
                volume_ratio is None
                and volume is not None
                and average_volume is not None
                and average_volume > 0
            ):
                volume_ratio = (
                    volume
                    / average_volume
                )

            bid = self._first_number(
                market,
                "bid",
                "bid_price",
            )

            ask = self._first_number(
                market,
                "ask",
                "ask_price",
            )

            spread = self._first_number(
                market,
                "spread",
            )

            spread_percent = self._first_number(
                market,
                "spread_percent",
                "spread_pct",
            )

            if (
                spread is None
                and bid is not None
                and ask is not None
                and ask >= bid
            ):
                spread = (
                    ask
                    - bid
                )

            if (
                spread_percent is None
                and spread is not None
                and bid is not None
                and ask is not None
            ):
                midpoint = (
                    bid
                    + ask
                ) / 2.0

                if midpoint > 0:
                    spread_percent = (
                        spread
                        / midpoint
                    ) * 100.0

            pattern_name = self._first_pattern_name(
                patterns
            )

            automatic_execution_safe = self._extract_execution_safety(
                decision_dict,
                market,
            )

            source = self._first_text(
                market,
                "source",
                "provider",
                "market_provider",
            )

            as_of = self._first_value(
                market,
                "as_of",
                "timestamp",
                "market_timestamp",
                "quote_timestamp",
                "bar_timestamp",
            )

            result: dict[str, Any] = {
                "symbol": self._normalize_symbol(
                    decision_dict.get(
                        "symbol",
                        symbol,
                    )
                )
                or symbol,
                "action": action,
                "signal": action,
                "strategy": (
                    str(strategy)
                    if strategy is not None
                    else None
                ),
                "confidence": confidence,
                "score": confidence,
                "price": price,
                "previous_close": previous_close,
                "change_percent": change_percent,
                "volume": volume,
                "average_volume": average_volume,
                "volume_ratio": volume_ratio,
                "bid": bid,
                "ask": ask,
                "spread": spread,
                "spread_percent": spread_percent,
                "pattern": pattern_name,
                "selected": selected or None,
                "patterns": patterns,
                "market": market or None,
                "automatic_execution_safe": automatic_execution_safe,
                "source": source,
                "as_of": (
                    str(as_of)
                    if as_of is not None
                    else None
                ),
                "status": self.STATUS_OK,
                "scan_duration_ms": round(
                    (
                        monotonic()
                        - started
                    )
                    * 1000.0,
                    3,
                ),
            }

            regime = self._first_nonempty(
                decision_dict.get(
                    "regime"
                ),
                market.get(
                    "regime"
                ),
                market.get(
                    "market_regime"
                ),
            )

            if regime is not None:
                result[
                    "regime"
                ] = regime

            selector = decision_dict.get(
                "selection"
            )

            if isinstance(
                selector,
                Mapping,
            ):
                result[
                    "selection"
                ] = dict(
                    selector
                )

            evaluations = decision_dict.get(
                "evaluations"
            )

            if isinstance(
                evaluations,
                list,
            ):
                result[
                    "evaluation_count"
                ] = len(
                    evaluations
                )

            return result

        except Exception as exc:
            return self._error_result(
                symbol,
                exc,
                started=started,
            )

    def _error_result(
        self,
        symbol: str,
        exc: Exception,
        *,
        started: float | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "symbol": self._normalize_symbol(
                symbol
            )
            or str(
                symbol
            ),
            "action": self.ACTION_HOLD,
            "signal": self.ACTION_HOLD,
            "strategy": None,
            "confidence": 0.0,
            "score": 0.0,
            "price": None,
            "previous_close": None,
            "change_percent": None,
            "volume": None,
            "average_volume": None,
            "volume_ratio": None,
            "bid": None,
            "ask": None,
            "spread": None,
            "spread_percent": None,
            "pattern": None,
            "selected": None,
            "patterns": [],
            "market": None,
            "automatic_execution_safe": False,
            "source": None,
            "as_of": None,
            "status": self.STATUS_ERROR,
            "error": self._safe_error(
                exc
            ),
        }

        if started is not None:
            result[
                "scan_duration_ms"
            ] = round(
                (
                    monotonic()
                    - started
                )
                * 1000.0,
                3,
            )

        return result

    # =========================================================================
    # RANKING
    # =========================================================================

    def _rank(
        self,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Rank successful candidates with CandidateRanker and append failed
        symbols after successful observations.

        CandidateRanker is the canonical shared ranking implementation.
        """

        successful = [
            item
            for item in results
            if item.get(
                "status"
            )
            == self.STATUS_OK
        ]

        failed = [
            item
            for item in results
            if item.get(
                "status"
            )
            != self.STATUS_OK
        ]

        ranked: list[
            dict[
                str,
                Any,
            ]
        ]

        try:
            ranked = candidate_ranker.rank(
                successful
            )
        except Exception:
            # Discovery remains readable even if the optional ranking layer
            # fails. This fallback ranks only from already-confirmed fields and
            # never fabricates observations.
            ranked = self._fallback_rank(
                successful
            )

        failed.sort(
            key=lambda item: str(
                item.get(
                    "symbol"
                )
                or ""
            )
        )

        return (
            ranked
            + failed
        )

    def _fallback_rank(
        self,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ordered = sorted(
            results,
            key=lambda item: (
                -(
                    1
                    if self._normalize_action(
                        item.get(
                            "action"
                        )
                    )
                    in {
                        self.ACTION_BUY,
                        self.ACTION_SELL,
                    }
                    else 0
                ),
                -self._sortable_number(
                    item.get(
                        "confidence"
                    )
                ),
                str(
                    item.get(
                        "symbol"
                    )
                    or ""
                ),
            ),
        )

        output: list[
            dict[
                str,
                Any,
            ]
        ] = []

        for index, item in enumerate(
            ordered,
            start=1,
        ):
            copied = dict(
                item
            )
            copied[
                "rank"
            ] = index
            copied[
                "rank_score"
            ] = self._sortable_number(
                copied.get(
                    "confidence"
                )
            )
            copied[
                "ranking_reasons"
            ] = [
                "DecisionEngine confidence",
                (
                    "Actionable DecisionEngine signal"
                    if self._normalize_action(
                        copied.get(
                            "action"
                        )
                    )
                    in {
                        self.ACTION_BUY,
                        self.ACTION_SELL,
                    }
                    else "Non-actionable HOLD decision"
                ),
            ]

            output.append(
                copied
            )

        return output

    # =========================================================================
    # NORMALIZATION
    # =========================================================================

    def _normalize_category(
        self,
        category: str,
    ) -> str:
        normalized = (
            str(
                category
                or ""
            )
            .strip()
            .lower()
            .replace(
                "_",
                "-",
            )
            .replace(
                " ",
                "-",
            )
        )

        while "--" in normalized:
            normalized = normalized.replace(
                "--",
                "-",
            )

        normalized = self.CATEGORY_ALIASES.get(
            normalized,
            normalized,
        )

        if normalized not in self.CATEGORY_UNIVERSES:
            raise ValueError(
                f"Unknown discovery category: {category}"
            )

        return normalized

    @classmethod
    def _normalize_symbols(
        cls,
        symbols: Iterable[Any],
    ) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()

        for raw in symbols:
            symbol = cls._normalize_symbol(
                raw
            )

            if not symbol:
                continue

            if symbol in seen:
                continue

            seen.add(
                symbol
            )
            output.append(
                symbol
            )

            if len(
                output
            ) >= cls.MAX_SCAN_SYMBOLS:
                break

        return output

    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> str:
        if symbol is None:
            return ""

        value = str(
            symbol
        ).strip().upper()

        if not value:
            return ""

        if len(
            value
        ) > 64:
            return ""

        allowed = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-/_:"
        )

        if any(
            character not in allowed
            for character in value
        ):
            return ""

        return value

    @classmethod
    def _normalize_action(
        cls,
        value: Any,
    ) -> str:
        action = str(
            value
            or cls.ACTION_HOLD
        ).strip().upper()

        if action in {
            cls.ACTION_BUY,
            cls.ACTION_SELL,
            cls.ACTION_HOLD,
        }:
            return action

        return cls.ACTION_HOLD

    @classmethod
    def _normalize_workers(
        cls,
        workers: int | None,
        symbol_count: int,
    ) -> int:
        if symbol_count <= 1:
            return 1

        if workers is None:
            workers = cls.DEFAULT_WORKERS

        try:
            value = int(
                workers
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            value = cls.DEFAULT_WORKERS

        value = max(
            1,
            min(
                value,
                cls.MAX_WORKERS,
                symbol_count,
            ),
        )

        return value

    @staticmethod
    def _normalize_limit(
        value: Any,
        *,
        maximum: int,
        minimum: int,
    ) -> int:
        try:
            parsed = int(
                value
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            parsed = minimum

        return max(
            minimum,
            min(
                parsed,
                maximum,
            ),
        )

    # =========================================================================
    # DECISION FIELD EXTRACTION
    # =========================================================================

    @classmethod
    def _extract_confidence(
        cls,
        decision: Mapping[str, Any],
        selected: Mapping[str, Any],
        selection: Mapping[str, Any],
    ) -> float:
        candidates = (
            selected.get(
                "confidence"
            ),
            decision.get(
                "confidence"
            ),
            selection.get(
                "confidence"
            ),
            selection.get(
                "base_confidence"
            ),
            selected.get(
                "score"
            ),
        )

        for value in candidates:
            number = cls._number(
                value
            )

            if number is None:
                continue

            if number > 1.0 and number <= 100.0:
                number = (
                    number
                    / 100.0
                )

            return max(
                0.0,
                min(
                    number,
                    1.0,
                ),
            )

        return 0.0

    @classmethod
    def _extract_execution_safety(
        cls,
        decision: Mapping[str, Any],
        market: Mapping[str, Any],
    ) -> bool:
        decision_value = decision.get(
            "automatic_execution_safe"
        )

        if isinstance(
            decision_value,
            bool,
        ):
            return decision_value

        market_value = market.get(
            "automatic_execution_safe"
        )

        if isinstance(
            market_value,
            bool,
        ):
            return market_value

        # Missing safety confirmation is always fail-closed.
        return False

    @classmethod
    def _extract_change_percent(
        cls,
        market: Mapping[str, Any],
    ) -> float | None:
        direct = cls._first_number(
            market,
            "change_percent",
            "change_pct",
            "regular_market_change_percent",
            "percent_change",
        )

        if direct is not None:
            return direct

        price = cls._first_number(
            market,
            "price",
            "regular_market_price",
            "close",
            "last",
            "last_price",
        )

        previous_close = cls._first_number(
            market,
            "previous_close",
            "regular_market_previous_close",
            "prev_close",
        )

        if (
            price is None
            or previous_close is None
            or previous_close == 0
        ):
            return None

        return (
            (
                price
                - previous_close
            )
            / previous_close
        ) * 100.0

    @staticmethod
    def _first_pattern_name(
        patterns: Sequence[Any],
    ) -> str | None:
        for item in patterns:
            if isinstance(
                item,
                Mapping,
            ):
                value = (
                    item.get(
                        "name"
                    )
                    or item.get(
                        "label"
                    )
                    or item.get(
                        "pattern"
                    )
                    or item.get(
                        "type"
                    )
                )

                if value:
                    return str(
                        value
                    )

            elif item:
                return str(
                    item
                )

        return None

    # =========================================================================
    # GENERIC VALUE HELPERS
    # =========================================================================

    @staticmethod
    def _mapping(
        value: Any,
    ) -> dict[str, Any]:
        if isinstance(
            value,
            Mapping,
        ):
            return dict(
                value
            )

        return {}

    @staticmethod
    def _list(
        value: Any,
    ) -> list[Any]:
        if isinstance(
            value,
            list,
        ):
            return list(
                value
            )

        if isinstance(
            value,
            tuple,
        ):
            return list(
                value
            )

        return []

    @classmethod
    def _first_number(
        cls,
        source: Mapping[str, Any],
        *keys: str,
    ) -> float | None:
        for key in keys:
            if key not in source:
                continue

            value = cls._number(
                source.get(
                    key
                )
            )

            if value is not None:
                return value

        return None

    @staticmethod
    def _first_value(
        source: Mapping[str, Any],
        *keys: str,
    ) -> Any:
        for key in keys:
            if key not in source:
                continue

            value = source.get(
                key
            )

            if value is not None:
                return value

        return None

    @staticmethod
    def _first_text(
        source: Mapping[str, Any],
        *keys: str,
    ) -> str | None:
        for key in keys:
            value = source.get(
                key
            )

            if value is None:
                continue

            text = str(
                value
            ).strip()

            if text:
                return text

        return None

    @staticmethod
    def _first_nonempty(
        *values: Any,
    ) -> Any:
        for value in values:
            if value is None:
                continue

            if isinstance(
                value,
                str,
            ):
                if value.strip():
                    return value.strip()

                continue

            return value

        return None

    @staticmethod
    def _number(
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
            number = float(
                value
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if not isfinite(
            number
        ):
            return None

        return number

    @classmethod
    def _positive_number(
        cls,
        value: Any,
    ) -> float | None:
        number = cls._number(
            value
        )

        if number is None:
            return None

        if number < 0:
            return None

        return number

    @classmethod
    def _sortable_number(
        cls,
        value: Any,
    ) -> float:
        number = cls._number(
            value
        )

        return (
            number
            if number is not None
            else 0.0
        )

    @staticmethod
    def _safe_error(
        exc: Exception,
    ) -> str:
        """
        Produce a bounded error message suitable for scanner responses.

        Exception text is intentionally bounded so a provider cannot flood an
        API response with an unexpectedly large error payload.
        """

        message = str(
            exc
        ).strip()

        if not message:
            message = exc.__class__.__name__

        if len(
            message
        ) > 500:
            message = (
                message[
                    :497
                ]
                + "..."
            )

        return message


discovery_service = DiscoveryService()


__all__ = [
    "DiscoveryService",
    "discovery_service",
]