# PhoenixTrend Strategy Audit

All strategy modules were parsed individually and exercised through the registry test suite.

| File | Strategy | Lines | Signal contract |
|---|---|---:|---|
| `adx_trend_strength.py` | ADX Trend Strength | 331 | yes |
| `atr_breakout.py` | ATR Breakout | 330 | yes |
| `atr_trailing_trend.py` | ATR Trailing Trend | 331 | yes |
| `bollinger_breakout.py` | Bollinger Breakout | 343 | yes |
| `bollinger_mean_reversion.py` | Bollinger Mean Reversion | 351 | yes |
| `breakout.py` | Breakout | 395 | yes |
| `cci_reversal.py` | CCI Reversal | 338 | yes |
| `cci_trend.py` | CCI Trend | 332 | yes |
| `donchian_breakout.py` | Donchian Breakout | 330 | yes |
| `ema_crossover.py` | EMA Crossover | 348 | yes |
| `gapgo.py` | GapAndGo | 416 | yes |
| `ichimoku_breakout.py` | Ichimoku Breakout | 333 | yes |
| `ichimoku_cloud_trend.py` | Ichimoku Cloud Trend | 332 | yes |
| `keltner_channel_breakout.py` | Keltner Channel Breakout | 330 | yes |
| `keltner_mean_reversion.py` | Keltner Mean Reversion | 334 | yes |
| `macd_momentum.py` | MACD Momentum | 348 | yes |
| `meanreversion.py` | MeanReversion | 389 | yes |
| `momentum.py` | Momentum | 400 | yes |
| `multi_factor_confluence.py` | Multi-Factor Confluence | 328 | yes |
| `opening_range_momentum.py` | Opening Range Momentum | 330 | yes |
| `orb.py` | ORB | 369 | yes |
| `parabolic_sar_trend.py` | Parabolic SAR Trend | 330 | yes |
| `pivot_point_reversal.py` | Pivot Point Reversal | 336 | yes |
| `price_channel_breakout.py` | Price Channel Breakout | 330 | yes |
| `pullback.py` | Pullback | 435 | yes |
| `regime_adaptive.py` | Regime Adaptive Strategy | 335 | yes |
| `relative_strength_rotation.py` | Relative Strength Rotation | 336 | yes |
| `roc_momentum.py` | ROC Momentum | 332 | yes |
| `rsi_reversal.py` | RSI Reversal | 350 | yes |
| `stochastic_momentum.py` | Stochastic Momentum | 332 | yes |
| `stochastic_reversal.py` | Stochastic Reversal | 336 | yes |
| `supertrend.py` | Supertrend | 330 | yes |
| `swingtrend.py` | SwingTrend | 373 | yes |
| `trendfollowing.py` | TrendFollowing | 389 | yes |
| `volume_breakout.py` | Volume Breakout | 330 | yes |
| `volume_weighted_momentum.py` | Volume-Weighted Momentum | 330 | yes |
| `vwap.py` | VWAP | 350 | yes |
| `vwap_deviation_reversion.py` | VWAP Deviation Reversion | 331 | yes |
| `williams_r_reversal.py` | Williams %R Reversal | 339 | yes |

Backend verification: Python compileall passed; pytest 9 passed. UI wiring verified by source references from Strategies.razor to PhoenixApi strategy methods and matching FastAPI routes.
