# MYHaze backtest

Trained on days up to 2026-09-30; tested on later days. Bands are the official API bands of each day's average PM2.5. Target for tomorrow: ≥90% correct band and ≥90% of unhealthy-or-worse days caught.

| Lead | Method | Days | Correct band | Unhealthy+ caught | False alarms | Avg miss (µg/m³) | In 80% range |
|---|---|---|---|---|---|---|---|
| Tomorrow | model (shipped) | 1024 | 69.9% | 82.2% | 6.7% | 8.46 | 70.2% |
| Tomorrow | persistence | 1024 | 58.7% | 79.5% | 19.1% | 11.14 | – |
| Tomorrow | cams | 1024 | 64.0% | 79.6% | 12.8% | 11.42 | – |
| Day after | model | 1025 | 64.8% | 75.5% | 9.7% | 10.57 | 74.5% |
| Day after | persistence | 1025 | 46.2% | 71.3% | 29.7% | 16.41 | – |
| Day after | cams (shipped) | 1025 | 63.3% | 78.3% | 13.2% | 12.4 | – |

Tomorrow's target met: **no**.
