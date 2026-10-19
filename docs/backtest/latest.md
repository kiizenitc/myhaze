# MYHaze backtest

Trained on days up to 2026-09-30; tested on later days. Bands are the Real Feel bands (aqicn's US AQI numbers, Malaysia's band names) of each day's average PM2.5. Target for tomorrow: ≥90% correct band and ≥90% of unhealthy-or-worse days caught.

| Lead | Method | Days | Correct band | Unhealthy+ caught | False alarms | Avg miss (µg/m³) | In 80% range |
|---|---|---|---|---|---|---|---|
| Tomorrow | model | 1085 | 83.6% | 83.2% | 8.0% | 9.14 | 68.8% |
| Tomorrow | persistence | 1085 | 73.2% | 79.1% | 18.9% | 11.98 | – |
| Tomorrow | cams (shipped) | 1085 | 78.1% | 83.5% | 14.9% | 12.01 | – |
| Day after | model | 1087 | 79.0% | 78.0% | 11.5% | 11.4 | 79.7% |
| Day after | persistence | 1087 | 65.0% | 72.4% | 28.1% | 17.28 | – |
| Day after | cams (shipped) | 1087 | 77.2% | 82.3% | 16.1% | 12.78 | – |

Tomorrow's target met: **no**.
