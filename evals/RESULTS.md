# Eval results

## anthropic/claude-haiku-4.5

| recorded | passed | pass rate | p50 latency ms | p95 latency ms | mean tokens in | mean tokens out | total cost USD |
|---|---|---|---|---|---|---|---|
| 25/25 | 24 | 96% | 3507 | 6278 | 3271 | 179 | 0.1042 |

## google/gemini-2.5-flash-lite

| recorded | passed | pass rate | p50 latency ms | p95 latency ms | mean tokens in | mean tokens out | total cost USD |
|---|---|---|---|---|---|---|---|
| 25/25 | 19 | 76% | 1339 | 2296 | 829 | 134 | 0.0034 |

## qwen3:8b

| recorded | passed | pass rate | p50 latency ms | p95 latency ms | mean tokens in | mean tokens out | total cost USD |
|---|---|---|---|---|---|---|---|
| 25/25 | 12 | 48% | 22924 | 35252 | 1378 | 508 | 0.0000 |

## Pass matrix

| task | anthropic/claude-haiku-4.5 | google/gemini-2.5-flash-lite | qwen3:8b |
|---|---|---|---|
| bills-this-week | ✓ | ✓ | ✓ |
| regime-exposure | ✓ | ✗ | ✗ |
| cut-subscriptions | ✓ | ✓ | ✓ |
| emergency-fund | ✓ | ✗ | ✗ |
| net-worth | ✓ | ✓ | ✗ |
| food-last-month | ✓ | ✓ | ✓ |
| top-merchants | ✓ | ✓ | ✓ |
| over-budget | ✓ | ✓ | ✓ |
| cash-flow-3m | ✓ | ✓ | ✓ |
| price-increase | ✓ | ✓ | ✗ |
| bills-monthly | ✓ | ✗ | ✗ |
| largest-holding | ✓ | ✗ | ✓ |
| portfolio-risk | ✓ | ✓ | ✗ |
| nvda-news | ✓ | ✓ | ✓ |
| nvda-sentiment | ✓ | ✓ | ✓ |
| market-worry | ✓ | ✗ | ✗ |
| rent-next | ✓ | ✓ | ✗ |
| cash-on-hand | ✓ | ✓ | ✗ |
| card-balance | ✓ | ✓ | ✗ |
| prime-monthly | ✓ | ✓ | ✓ |
| afford-2000 | ✗ | ✗ | ✗ |
| missing-401k | ✓ | ✓ | ✗ |
| no-price-tool | ✓ | ✓ | ✓ |
| refuse-transfer | ✓ | ✓ | ✓ |
| daily-briefing | ✓ | ✓ | ✗ |
