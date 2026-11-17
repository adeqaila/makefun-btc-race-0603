[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/adeqaila/makefun-btc-race-0603/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/adeqaila/makefun-btc-race-0603/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

# BTC Race 20261117-0603 — entry slot 1

Bounty: "Race a BTC trading bot live for 24 hours"
([`btc-race-24h-20261117-0603`](https://make.fun/bounty/btc-race-24h-20261117-0603), $250, top 10 paid, 1st $60).
Opened 17 Nov 2026 06:03 UTC, deadline 17 Nov 2026 12:03 UTC (19:03 WIB).
Race live 24h from 12:18 UTC 17 Nov → 12:18 UTC 18 Nov.

## Strategy — v2.1 (user's 3-phase pattern, tuned 18:40 WIB 17 Nov 2026)

- **Fase 1 (bars 0–59, first hour):** buy all-in when close dips ≥ 0,23% below the race OPEN; sell all when close rises 0,50% above the buy fill (take profit).
- **Fase 2 (bars 1380–1439, last hour):** if still flat, buy all-in when close dips ≥ 0,50% below the rolling 60-bar peak close; hold to close.
- **Fase 3 (bars 1410–1439, last 30 min):** if still flat, buy all-in at market; hold to close.
- Max 1 buy. NO stop loss, NO PnL lock, NO washout. Deterministic; stdlib only; no network, no clock, no files.

## Dev gate (exact replay, same driver as §9)

- **dev 0603: net +$3,4976 — GATE PASS** (buy bar 11 @ $64.374,48 → sell bar 57 @ $64.651,36; deterministic, 2 runs byte-identical).
- dev 0828 (simulator): +$2,87. Battery 13 windows (simulator): 10/13 profit.

This bot is from `~/workspace/makefun-btc-race-next-v2/main.py` (v2.1).
Protocol agent-fun/bars-replay/v1; Python SDK shim byte-identical to the kit.

Run: `python3 -P -s main.py` (grader runs it with `PYTHONHASHSEED=0`).
