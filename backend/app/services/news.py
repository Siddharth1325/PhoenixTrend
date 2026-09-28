from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from typing import Any

import httpx


class NewsService:
    """
    PhoenixTrend market-news service.

    Current provider:
        Yahoo Finance search/news endpoint

    Responsibilities:
        - fetch real published articles
        - normalize article metadata
        - preserve publisher/image/url information
        - provide stock-specific news for UI/intelligence

    NewsService does NOT:
        - fabricate articles
        - fabricate images
        - generate trading signals
        - place orders
    """

    URL = (
        "https://query1.finance.yahoo.com/"
        "v1/finance/search"
    )

    CACHE_TTL_SECONDS = 45

    MAX_LIMIT = 50


    def __init__(self) -> None:

        self._cache: dict[
            str,
            tuple[
                float,
                list[dict[str, Any]],
            ],
        ] = {}

        self._lock = RLock()


    # ========================================================
    # SYMBOL NEWS
    # ========================================================

    def for_symbol(
        self,
        symbol: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:

        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )


        safe_limit = max(
            1,
            min(
                int(limit),
                self.MAX_LIMIT,
            ),
        )


        cache_key = (
            f"{normalized_symbol}:{safe_limit}"
        )


        cached = self._get_cache(
            cache_key
        )


        if cached is not None:

            return cached


        try:

            with httpx.Client(
                timeout=8.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(PhoenixTrend)"
                    )
                },
            ) as client:

                response = client.get(
                    self.URL,
                    params={
                        "q": (
                            normalized_symbol
                        ),
                        "quotesCount": 1,
                        "newsCount": (
                            safe_limit
                        ),
                    },
                )


                response.raise_for_status()

                payload = (
                    response.json()
                )


        except (
            httpx.HTTPError,
            ValueError,
        ):

            # News should fail gracefully.
            #
            # A news-provider failure must not break the
            # trading system or cause fabricated fallback
            # articles.

            return []


        output: list[
            dict[str, Any]
        ] = []

        seen_urls: set[str] = set()


        for item in (
            payload.get(
                "news"
            )
            or []
        ):

            article = (
                self._normalize_article(
                    normalized_symbol,
                    item,
                )
            )


            if article is None:

                continue


            article_url = str(
                article[
                    "article_url"
                ]
            )


            if article_url in seen_urls:

                continue


            seen_urls.add(
                article_url
            )


            output.append(
                article
            )


            if len(output) >= safe_limit:

                break


        # Always deliver newest stories first. Yahoo normally returns
        # recent stories first, but PhoenixTrend does not rely on provider
        # ordering.
        output.sort(
            key=lambda article: (
                article.get("published_at") or ""
            ),
            reverse=True,
        )

        self._set_cache(
            cache_key,
            output,
        )


        return output


    # ========================================================
    # ARTICLE NORMALIZATION
    # ========================================================

    def _normalize_article(
        self,
        symbol: str,
        item: dict[str, Any],
    ) -> dict[str, Any] | None:

        url = (
            item.get(
                "link"
            )
            or item.get(
                "url"
            )
        )


        headline = (
            item.get(
                "title"
            )
        )


        if not url or not headline:

            return None


        published_at = (
            self._published_at(
                item.get(
                    "providerPublishTime"
                )
            )
        )


        return {
            "symbol": (
                symbol
            ),

            "headline": str(
                headline
            ).strip(),

            # Yahoo's search payload does not always provide
            # a proper article summary. Do not invent one.
            "summary": (
                item.get(
                    "summary"
                )
            ),

            "image_url": (
                self._image_url(
                    item
                )
            ),

            "publisher": (
                item.get(
                    "publisher"
                )
            ),

            "published_at": (
                published_at
            ),

            "article_url": (
                str(
                    url
                )
            ),

            # These fields are intentionally empty until
            # PhoenixTrend derives or receives real values.
            "topics": [],

            "sentiment": None,

            "hot_score": None,

            "source": (
                "yahoo-finance"
            ),

            "simulated": (
                False
            ),
        }


    # ========================================================
    # IMAGE
    # ========================================================

    @staticmethod
    def _image_url(
        item: dict[str, Any],
    ) -> str | None:

        thumbnail = (
            item.get(
                "thumbnail"
            )
            or {}
        )


        resolutions = (
            thumbnail.get(
                "resolutions"
            )
            or []
        )


        valid = [
            resolution
            for resolution
            in resolutions
            if resolution.get(
                "url"
            )
        ]


        if not valid:

            return None


        best = max(
            valid,
            key=lambda resolution: (
                resolution.get(
                    "width",
                    0,
                )
                or 0
            ),
        )


        return best.get(
            "url"
        )


    # ========================================================
    # TIMESTAMP
    # ========================================================

    @staticmethod
    def _published_at(
        timestamp: Any,
    ) -> str | None:

        if timestamp is None:

            return None


        try:

            return (
                datetime.fromtimestamp(
                    float(
                        timestamp
                    ),
                    tz=timezone.utc,
                )
                .isoformat()
            )


        except (
            TypeError,
            ValueError,
            OSError,
        ):

            return None


    # ========================================================
    # SYMBOL
    # ========================================================

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:

        normalized = (
            str(
                symbol
            )
            .strip()
            .upper()
        )


        if not normalized:

            raise ValueError(
                "Symbol is required"
            )


        return normalized


    # ========================================================
    # CACHE
    # ========================================================

    def _get_cache(
        self,
        key: str,
    ) -> list[dict[str, Any]] | None:

        now = monotonic()


        with self._lock:

            cached = (
                self._cache.get(
                    key
                )
            )


            if cached is None:

                return None


            created_at, data = cached


            if (
                now - created_at
                > self.CACHE_TTL_SECONDS
            ):

                self._cache.pop(
                    key,
                    None,
                )

                return None


            return [
                dict(
                    article
                )
                for article
                in data
            ]


    def _set_cache(
        self,
        key: str,
        data: list[dict[str, Any]],
    ) -> None:

        with self._lock:

            self._cache[
                key
            ] = (
                monotonic(),
                [
                    dict(
                        article
                    )
                    for article
                    in data
                ],
            )


    # ========================================================
    # STATUS
    # ========================================================

    def status(
        self,
    ) -> dict[str, Any]:

        return {
            "provider": (
                "yahoo-finance"
            ),

            "simulated": (
                False
            ),

            "supports_images": (
                True
            ),

            "supports_symbol_news": (
                True
            ),

            "direct_trade_signal": (
                False
            ),
        }


news_service = NewsService()