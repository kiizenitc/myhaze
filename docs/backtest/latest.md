# MYHaze backtest

Trained on days up to 2026-09-30; tested on later days. Bands are the official API bands of each day's average PM2.5. Target for tomorrow: ≥90% correct band and ≥90% of unhealthy-or-worse days caught.

| Lead | Method | Days | Correct band | Unhealthy+ caught | False alarms | Avg miss (µg/m³) | In 80% range |
|---|---|---|---|---|---|---|---|
| Tomorrow | model (shipped) | 930 | 71.2% | 81.0% | 6.5% | 7.87 | 74.1% |
| Tomorrow | persistence | 930 | 58.0% | 78.2% | 19.1% | 11.31 | – |
| Tomorrow | cams | 930 | 65.0% | 79.6% | 13.5% | 10.96 | – |
| Day after | model | 930 | 65.8% | 75.8% | 9.1% | 9.6 | 76.4% |
| Day after | persistence | 930 | 45.9% | 68.7% | 28.7% | 16.62 | – |
| Day after | cams (shipped) | 930 | 64.6% | 79.0% | 13.4% | 11.74 | – |

Tomorrow's target met: **no**.
