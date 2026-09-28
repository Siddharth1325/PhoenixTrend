from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from typing import Any


def _values(
    bars: list[dict[str, Any]],
    key: str,
) -> list[float]:
    values: list[float] = []

    for bar in bars:
        value = bar.get(key)
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue

    return values


def _float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _timestamp(
    bar: dict[str, Any],
) -> datetime | None:
    raw = (
        bar.get("timestamp")
        or bar.get("datetime")
        or bar.get("time")
        or bar.get("date")
    )

    if raw is None:
        return None

    if isinstance(raw, datetime):
        return raw

    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(
                float(raw),
                tz=timezone.utc,
            )
        except (ValueError, OSError, OverflowError):
            return None

    try:
        return datetime.fromisoformat(
            str(raw).replace("Z", "+00:00")
        )
    except ValueError:
        return None


def ema(
    values: list[float],
    period: int,
) -> float:
    if period <= 0:
        raise ValueError("EMA period must be positive")

    if len(values) < period:
        raise ValueError(
            f"EMA{period} requires at least {period} values; "
            f"received {len(values)}"
        )

    sample = values[-period:]
    multiplier = 2.0 / (period + 1.0)
    result = sample[0]

    for value in sample[1:]:
        result = (
            value * multiplier
            + result * (1.0 - multiplier)
        )

    return result


def sma(
    values: list[float],
    period: int,
) -> float:
    if not values:
        raise ValueError("SMA requires values")
    if period <= 0:
        raise ValueError("SMA period must be positive")

    effective_period = min(period, len(values))
    sample = values[-effective_period:]
    return sum(sample) / len(sample)


def rsi(
    values: list[float],
    period: int = 14,
) -> float:
    if len(values) < 2:
        return 50.0

    changes = [
        current - previous
        for previous, current in zip(values[:-1], values[1:])
    ][-period:]

    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    count = max(len(changes), 1)
    avg_gain = sum(gains) / count
    avg_loss = sum(losses) / count

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    relative_strength = avg_gain / avg_loss

    return 100.0 - (
        100.0 / (1.0 + relative_strength)
    )


def atr(
    bars: list[dict[str, Any]],
    period: int = 14,
) -> float:
    if len(bars) < 2:
        return 0.0

    true_ranges: list[float] = []

    for previous, current in zip(bars[:-1], bars[1:]):
        high = _float(current.get("high"))
        low = _float(current.get("low"))
        previous_close = _float(previous.get("close"))

        if high <= 0 or low <= 0 or previous_close <= 0:
            continue

        true_ranges.append(
            max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        )

    if not true_ranges:
        return 0.0

    return sma(true_ranges, period)


def _ema_series(
    values: list[float],
    period: int,
) -> list[float]:
    if not values:
        return []

    multiplier = 2.0 / (period + 1.0)
    current = values[0]
    result = [current]

    for value in values[1:]:
        current = (
            value * multiplier
            + current * (1.0 - multiplier)
        )
        result.append(current)

    return result


def macd(
    values: list[float],
) -> tuple[float, float, float]:
    if len(values) < 2:
        return 0.0, 0.0, 0.0

    fast = _ema_series(values, 12)
    slow = _ema_series(values, 26)

    line_series = [
        fast_value - slow_value
        for fast_value, slow_value in zip(fast, slow)
    ]

    signal_series = _ema_series(line_series, 9)

    line = line_series[-1]
    signal = signal_series[-1]

    return line, signal, line - signal


def bollinger(
    values: list[float],
    period: int = 20,
    deviations: float = 2.0,
) -> tuple[float, float, float]:
    if not values:
        raise ValueError("Bollinger Bands require values")

    effective_period = min(period, len(values))
    sample = values[-effective_period:]

    middle = sum(sample) / len(sample)

    variance = (
        sum((value - middle) ** 2 for value in sample)
        / len(sample)
    )

    standard_deviation = sqrt(variance)

    return (
        middle - deviations * standard_deviation,
        middle,
        middle + deviations * standard_deviation,
    )


def current_session_bars(
    bars: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not bars:
        return []

    latest_timestamp = _timestamp(bars[-1])

    if latest_timestamp is None:
        return bars

    session_date = latest_timestamp.date()

    session = [
        bar
        for bar in bars
        if (
            (timestamp := _timestamp(bar)) is not None
            and timestamp.date() == session_date
        )
    ]

    return session if session else bars


def previous_session_bars(
    bars: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not bars:
        return []

    latest_timestamp = _timestamp(bars[-1])

    if latest_timestamp is None:
        return []

    current_date = latest_timestamp.date()

    previous_dates = sorted(
        {
            timestamp.date()
            for bar in bars
            if (
                (timestamp := _timestamp(bar)) is not None
                and timestamp.date() < current_date
            )
        }
    )

    if not previous_dates:
        return []

    previous_date = previous_dates[-1]

    return [
        bar
        for bar in bars
        if (
            (timestamp := _timestamp(bar)) is not None
            and timestamp.date() == previous_date
        )
    ]


def true_vwap(
    bars: list[dict[str, Any]],
) -> float:
    if not bars:
        raise ValueError("VWAP requires bars")

    price_volume = 0.0
    total_volume = 0.0

    for bar in bars:
        high = _float(bar.get("high"))
        low = _float(bar.get("low"))
        close = _float(bar.get("close"))
        volume = _float(bar.get("volume"))

        if high <= 0 or low <= 0 or close <= 0 or volume <= 0:
            continue

        typical_price = (high + low + close) / 3.0
        price_volume += typical_price * volume
        total_volume += volume

    if total_volume <= 0:
        return _float(bars[-1].get("close"))

    return price_volume / total_volume


def opening_range(
    session_bars: list[dict[str, Any]],
    bars_count: int = 6,
) -> tuple[float | None, float | None]:
    if len(session_bars) < bars_count:
        return None, None

    sample = session_bars[:bars_count]
    highs = _values(sample, "high")
    lows = _values(sample, "low")

    if not highs or not lows:
        return None, None

    return max(highs), min(lows)


def reference_levels(
    session_bars: list[dict[str, Any]],
) -> tuple[float, float]:
    if len(session_bars) < 2:
        return 0.0, 0.0

    completed = session_bars[:-1]
    highs = _values(completed, "high")
    lows = _values(completed, "low")

    if not highs or not lows:
        return 0.0, 0.0

    return max(highs), min(lows)


def trend_strength(
    price: float,
    ema20_value: float,
    ema50_value: float,
    atr_value: float,
) -> float:
    if price <= 0 or atr_value <= 0:
        return 0.0

    ema_separation = (
        abs(ema20_value - ema50_value)
        / atr_value
    )

    price_separation = (
        abs(price - ema20_value)
        / atr_value
    )

    score = (
        ema_separation * 0.60
        + price_separation * 0.40
    )

    return max(0.0, min(score / 3.0, 1.0))




def advanced_indicators(bars: list[dict[str, Any]]) -> dict[str, float | None]:
    """Calculate advanced indicators from the supplied real OHLCV bars.

    The function is deliberately pure: it never fetches prices and never
    synthesizes missing bars. If history is insufficient, unavailable values
    remain absent rather than being fabricated.
    """
    closes = _values(bars, "close")
    highs = _values(bars, "high")
    lows = _values(bars, "low")

    if len(closes) < 20 or len(highs) < 20 or len(lows) < 20:
        return {}

    def prior_high(period: int) -> float | None:
        sample = highs[-(period + 1):-1]
        return max(sample) if sample else None

    def prior_low(period: int) -> float | None:
        sample = lows[-(period + 1):-1]
        return min(sample) if sample else None

    def rolling_midpoint(period: int) -> float | None:
        if len(highs) < period or len(lows) < period:
            return None
        return (max(highs[-period:]) + min(lows[-period:])) / 2.0

    atr_value = atr(bars, 14)
    keltner_middle = ema(closes, 20)
    keltner_upper = keltner_middle + 2.0 * atr_value
    keltner_lower = keltner_middle - 2.0 * atr_value

    donchian_high = prior_high(20)
    donchian_low = prior_low(20)

    high14 = max(highs[-14:])
    low14 = min(lows[-14:])
    range14 = max(high14 - low14, 1e-12)
    stochastic_k = (closes[-1] - low14) / range14 * 100.0

    stochastic_samples: list[float] = []
    for end in range(len(closes) - 2, len(closes) + 1):
        start = max(0, end - 14)
        sample_high = max(highs[start:end])
        sample_low = min(lows[start:end])
        sample_range = max(sample_high - sample_low, 1e-12)
        stochastic_samples.append(
            (closes[end - 1] - sample_low) / sample_range * 100.0
        )
    stochastic_d = sum(stochastic_samples) / len(stochastic_samples)
    williams_r = -100.0 * (high14 - closes[-1]) / range14

    roc_value = None
    if len(closes) >= 13 and closes[-13] > 0:
        roc_value = ((closes[-1] / closes[-13]) - 1.0) * 100.0

    typical_prices = [
        (
            _float(bar.get("high"))
            + _float(bar.get("low"))
            + _float(bar.get("close"))
        ) / 3.0
        for bar in bars[-20:]
    ]
    typical_average = sum(typical_prices) / len(typical_prices)
    mean_deviation = sum(
        abs(value - typical_average)
        for value in typical_prices
    ) / len(typical_prices)
    cci_value = (
        (typical_prices[-1] - typical_average)
        / (0.015 * mean_deviation)
        if mean_deviation > 0
        else 0.0
    )

    # Wilder-style DMI/ADX. We calculate a full DX sequence and average the
    # latest 14 values instead of treating the latest DX as ADX.
    true_ranges: list[float] = []
    plus_moves: list[float] = []
    minus_moves: list[float] = []
    for previous, current in zip(bars[:-1], bars[1:]):
        current_high = _float(current.get("high"))
        current_low = _float(current.get("low"))
        previous_high = _float(previous.get("high"))
        previous_low = _float(previous.get("low"))
        previous_close = _float(previous.get("close"))

        up_move = current_high - previous_high
        down_move = previous_low - current_low
        plus_moves.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_moves.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        true_ranges.append(
            max(
                current_high - current_low,
                abs(current_high - previous_close),
                abs(current_low - previous_close),
            )
        )

    dx_values: list[float] = []
    plus_di = 0.0
    minus_di = 0.0
    period = 14
    for index in range(period - 1, len(true_ranges)):
        tr_sum = sum(true_ranges[index - period + 1:index + 1])
        if tr_sum <= 0:
            continue
        plus_sum = sum(plus_moves[index - period + 1:index + 1])
        minus_sum = sum(minus_moves[index - period + 1:index + 1])
        plus_di = 100.0 * plus_sum / tr_sum
        minus_di = 100.0 * minus_sum / tr_sum
        denominator = plus_di + minus_di
        if denominator > 0:
            dx_values.append(100.0 * abs(plus_di - minus_di) / denominator)
    adx_value = (
        sum(dx_values[-period:]) / min(period, len(dx_values))
        if dx_values
        else 0.0
    )

    conversion = rolling_midpoint(9)
    base = rolling_midpoint(26)
    span_a = (
        (conversion + base) / 2.0
        if conversion is not None and base is not None
        else None
    )
    span_b = rolling_midpoint(52)

    # Supertrend using ATR(10), multiplier 3, with band carry-forward.
    supertrend_value: float | None = None
    if len(bars) >= 11:
        multiplier = 3.0
        previous_upper: float | None = None
        previous_lower: float | None = None
        previous_supertrend: float | None = None

        for index in range(10, len(bars)):
            window = bars[:index + 1]
            current_atr = atr(window, 10)
            high = _float(bars[index].get("high"))
            low = _float(bars[index].get("low"))
            close = _float(bars[index].get("close"))
            previous_close = _float(bars[index - 1].get("close"))
            midpoint = (high + low) / 2.0
            basic_upper = midpoint + multiplier * current_atr
            basic_lower = midpoint - multiplier * current_atr

            final_upper = basic_upper
            final_lower = basic_lower
            if previous_upper is not None and previous_close <= previous_upper:
                final_upper = min(basic_upper, previous_upper)
            if previous_lower is not None and previous_close >= previous_lower:
                final_lower = max(basic_lower, previous_lower)

            if previous_supertrend is None:
                current_supertrend = final_lower if close >= midpoint else final_upper
            elif previous_supertrend == previous_upper:
                current_supertrend = final_upper if close <= final_upper else final_lower
            else:
                current_supertrend = final_lower if close >= final_lower else final_upper

            previous_upper = final_upper
            previous_lower = final_lower
            previous_supertrend = current_supertrend

        supertrend_value = previous_supertrend

    # Standard iterative Parabolic SAR with acceleration-factor progression.
    psar_value: float | None = None
    if len(bars) >= 3:
        bullish = closes[1] >= closes[0]
        acceleration = 0.02
        acceleration_step = 0.02
        acceleration_max = 0.20
        extreme = highs[0] if bullish else lows[0]
        psar_value = lows[0] if bullish else highs[0]

        for index in range(1, len(bars)):
            psar_value = psar_value + acceleration * (extreme - psar_value)

            if bullish:
                psar_value = min(psar_value, lows[index - 1])
                if index > 1:
                    psar_value = min(psar_value, lows[index - 2])
                if lows[index] < psar_value:
                    bullish = False
                    psar_value = extreme
                    extreme = lows[index]
                    acceleration = acceleration_step
                elif highs[index] > extreme:
                    extreme = highs[index]
                    acceleration = min(acceleration + acceleration_step, acceleration_max)
            else:
                psar_value = max(psar_value, highs[index - 1])
                if index > 1:
                    psar_value = max(psar_value, highs[index - 2])
                if highs[index] > psar_value:
                    bullish = True
                    psar_value = extreme
                    extreme = highs[index]
                    acceleration = acceleration_step
                elif lows[index] < extreme:
                    extreme = lows[index]
                    acceleration = min(acceleration + acceleration_step, acceleration_max)

    return {
        "sma20": sma(closes, 20),
        "sma50": sma(closes, 50),
        "adx": adx_value,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "stochastic_k": stochastic_k,
        "stochastic_d": stochastic_d,
        "cci": cci_value,
        "williams_r": williams_r,
        "roc": roc_value,
        "donchian_high": donchian_high,
        "donchian_low": donchian_low,
        "keltner_middle": keltner_middle,
        "keltner_upper": keltner_upper,
        "keltner_lower": keltner_lower,
        "ichimoku_conversion": conversion,
        "ichimoku_base": base,
        "ichimoku_span_a": span_a,
        "ichimoku_span_b": span_b,
        "supertrend": supertrend_value,
        "psar": psar_value,
    }

def feature_snapshot(
    bars: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(bars) < 50:
        raise ValueError(
            "At least 50 bars are required for the strategy feature snapshot"
        )

    closes = _values(bars, "close")

    if len(closes) < 50:
        raise ValueError(
            "At least 50 valid close values are required"
        )

    session_bars = current_session_bars(bars)
    previous_bars = previous_session_bars(bars)

    price = closes[-1]

    ema9_value = ema(closes, 9)
    ema20_value = ema(closes, 20)
    ema50_value = ema(closes, 50)
    ema200_value = ema(closes, 200) if len(closes) >= 200 else None

    rsi_value = rsi(closes, 14)
    atr_value = atr(bars, 14)
    atr_pct = atr_value / price if price > 0 else 0.0

    macd_value, macd_signal_value, macd_histogram = macd(closes)

    bb_lower, bb_middle, bb_upper = bollinger(
        closes,
        20,
        2.0,
    )

    vwap_value = true_vwap(session_bars)

    opening_range_high, opening_range_low = opening_range(
        session_bars
    )

    day_high, day_low = reference_levels(session_bars)

    current_volume = _float(
        session_bars[-1].get("volume")
        if session_bars
        else 0.0
    )

    historical_session_volumes = [
        _float(bar.get("volume"))
        for bar in session_bars[:-1]
        if _float(bar.get("volume")) > 0
    ]

    if historical_session_volumes:
        average_volume = (
            sum(historical_session_volumes)
            / len(historical_session_volumes)
        )
    else:
        all_volumes = [
            _float(bar.get("volume"))
            for bar in bars[-20:-1]
            if _float(bar.get("volume")) > 0
        ]

        average_volume = (
            sum(all_volumes) / len(all_volumes)
            if all_volumes
            else 0.0
        )

    volume_ratio = (
        current_volume / average_volume
        if average_volume > 0
        else 1.0
    )

    open_price = None

    if session_bars:
        open_price = _float(session_bars[0].get("open"))
        if open_price <= 0:
            open_price = None

    previous_close = None

    if previous_bars:
        previous_close = _float(previous_bars[-1].get("close"))
        if previous_close <= 0:
            previous_close = None

    strength = trend_strength(
        price,
        ema20_value,
        ema50_value,
        atr_value,
    )

    if price > ema20_value > ema50_value:
        market_regime = "BULLISH"
    elif price < ema20_value < ema50_value:
        market_regime = "BEARISH"
    else:
        market_regime = "NEUTRAL"

    advanced = advanced_indicators(bars)

    return {
        "price": price,
        "open_price": open_price,
        "previous_close": previous_close,
        "ema9": ema9_value,
        "ema20": ema20_value,
        "ema50": ema50_value,
        "ema200": ema200_value,
        "vwap": vwap_value,
        "rsi": rsi_value,
        "macd": macd_value,
        "macd_signal": macd_signal_value,
        "macd_histogram": macd_histogram,
        "atr": atr_value,
        "atr_pct": atr_pct,
        "bb_lower": bb_lower,
        "bb_middle": bb_middle,
        "bb_upper": bb_upper,
        "volume": current_volume,
        "average_volume": average_volume,
        "volume_ratio": volume_ratio,
        "day_high": day_high,
        "day_low": day_low,
        "opening_range_high": opening_range_high,
        "opening_range_low": opening_range_low,
        "market_regime": market_regime,
        "trend_strength": strength,
        **advanced,
    }
