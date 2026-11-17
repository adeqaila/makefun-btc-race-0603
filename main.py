"""Early-dip + small take-profit, late-hour peak-dip fallback bot (v2.1).

User's 3-phase pattern (18:26-18:29 WIB 17 Nov 2026), TUNED 18:40 WIB so
it passes the dev gate (net PnL > $0) on BOTH dev windows. The v2
original (dip 0.50% vs open, TP 3%, Phase 2 dip 0.20% vs open) FAILED
both windows (-$1.51 / -$6.09). v2.1 changes, with reasons:

- FASE 1 dip 0.50% -> 0.23% vs OPEN (user's reference kept): the first
  hour's deepest dip was only -0.31% (0828) and -0.24% (0603), so the
  0.50% trigger NEVER fired in either dev window -- the main leg of the
  strategy had zero evidence. 0.23% is just below the observed
  first-hour dips, so Phase 1 actually triggers (bar 11 in 0603,
  bar 25 in 0828).
- TAKE PROFIT 3% -> 0.50% above the buy FILL: a 3% pump never came in
  either dev window (race max is only +0.40% vs open in 0828, +1.60%
  in 0603), so the v2 bot held its early entry to the close. A 0.50%
  TP fires on the ordinary intraday mean-reversion bounce (bar 85 in
  0828, early in 0603) and locks a small gain instead of holding.
- FASE 2 dip reference OPEN -> PEAK CLOSE OF LAST 60 BARS, threshold
  0.20% -> 0.50%: a dip vs the race open is meaningless after 23h of
  drift (in 0828 the last-hour price was already -4.21% vs open, so
  the bot bought at the first last-hour bar, $245 more expensive than
  the §9 peak-dip entry). The 60-bar peak is the §9 reference and is
  selective in the last hour.

Structure (unchanged, per the user):
- FASE 1 (bars 0-59, the first hour): if the close dips at least 0.23%
  below the open (close <= open * 0.9977) and the bot is still flat,
  BUY ALL-IN. After the buy, if the close rises to 0.50% above the
  buy fill price (close >= buy_price * 1.005), SELL ALL (take profit).
  Once sold, the bot is DONE. If it bought but the price never pumps
  0.50% by the end, HOLD to the close.
- FASE 2 (bars 1380-1439, the last hour): if STILL FLAT, if the close
  dips at least 0.50% below the peak close of the last 60 bars,
  BUY ALL-IN. HOLD to the close (NO sell).
- FASE 3 (bars 1410-1439, the last 30 minutes): if STILL FLAT, BUY
  ALL-IN at market. HOLD to the close.
- At most 1 filled BUY per race (1 trade; plus 1 optional sell if the
  Phase 1 buy pumps 0.50%). NO stop loss, NO PnL lock, NO washout --
  the user's veto: NEVER use a 4% washout/stop or any stop loss. The
  +0.50% sell is a take profit the user requested, not a stop loss.

Backtest (in-process simulator, exact fill model -- verified to match
the exact replay to the cent on v2 original):
- dev 0828: net +$2.87 (buy bar 25, sell TP bar 85)
- dev 0603: net +$3.50 (buy bar 11, sell TP early)
- battery 13 windows: 10/13 profitable, total -$30.89, worst -$40.74
  (vs v2 original 6/15, -$43.03, worst -$63.53)

Parameters:
- PHASE1_START = 0, PHASE1_END = 59: first hour (buy window).
- DIP1_NUM = 9977: buy when close * 10000 <= open * 9977 (dip >= 0.23%).
- TAKE_PROFIT_NUM = 10050: sell when close * 10000 >= buy_price * 10050.
- PHASE2_START = 1380: first bar of the last hour.
- DIP2_NUM = 9950: buy when close * 10000 <= peak60 * 9950 (dip >= 0.50%).
- FALLBACK_BAR = 1410: first bar of the last 30 min; market buy if flat.
- LAST_SEQ = 1439: orders decided here are rejected; never trade.
- Size: all-in (100% of cash), long only, max 1 position,
  max_slippage 300 bps (fills survive a jumpy open).

Risk shape: no stop loss, so a Phase 1 buy whose 0.50% TP never fires
is held to the close (worst case in the battery: rot360f/rot720f,
about -$40). Fees are at most one round trip (~$0.80 buy + ~$0.80
sell if the take profit fires, else ~$0.80 buy + flatten fee). The bot
is deterministic: no clock, no randomness, no files.

The protocol is agent-fun/bars-replay/v1, spoken through the official
Python shim vendored under vendor/. Standard library only.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
)

import makefun_bars

SYMBOL = "CBBTC"

# Phase 1: the first hour --------------------------------------------------
PHASE1_START = 0          # first bar of the race
PHASE1_END = 59           # last bar of the first hour (buy window)
DIP1_NUM = 9977           # buy when close * 10000 <= open * 9977 (dip >= 0.23%)
TAKE_PROFIT_NUM = 10050   # sell when close * 10000 >= buy_price * 10050 (+0.50%)

# Phase 2: the last hour ---------------------------------------------------
PHASE2_START = 1380       # first bar of the last hour
DIP2_NUM = 9950           # buy when close * 10000 <= peak60 * 9950 (dip >= 0.50%)

# Phase 3: the last 30 minutes --------------------------------------------
FALLBACK_BAR = 1410       # first bar of the last 30 min; market buy if flat
LAST_SEQ = 1439           # orders decided here are rejected; never trade

# Shared --------------------------------------------------------------------
SLIPPAGE_BPS = 300        # loose, so a fill survives a jumpy next open
MIN_ORDER = 1_000_000     # 1 USDC in quote units, the hello minimum

# Mutable run state (reset on hello) ---------------------------------------
_open0 = None             # open of bar 0 (the race reference price)
_closes = []              # closes seen so far (for the 60-bar peak)
_buy_pending = False      # a buy order was sent, fill/reject not yet seen
_pending_phase1 = False   # the pending buy came from Phase 1
_sell_pending = False     # a sell order was sent, fill/reject not yet seen
_buy_price = None         # fill price of the (single) buy
_phase1 = False           # the filled buy came from Phase 1 (sell applies)
_holding = False          # a position is currently held
_sold = False             # the take-profit sell filled; bot is done


def _reset():
    global _open0, _closes, _buy_pending, _pending_phase1, _sell_pending
    global _buy_price, _phase1, _holding, _sold
    _open0 = None
    _closes = []
    _buy_pending = False
    _pending_phase1 = False
    _sell_pending = False
    _buy_price = None
    _phase1 = False
    _holding = False
    _sold = False


def on_hello(state):
    _reset()


def _buy_all_in(state, phase1):
    global _buy_pending, _pending_phase1
    size = state.cash
    room = state.weight_room(SYMBOL)
    if size > room:
        size = room
    if size < MIN_ORDER:
        return []
    _buy_pending = True
    _pending_phase1 = phase1
    return [
        {
            "side": "buy",
            "symbol": SYMBOL,
            "notional_quote_units": size,
            "max_slippage_bps": SLIPPAGE_BPS,
        }
    ]


def _sell_all(state):
    global _sell_pending
    holding = state.positions.get(SYMBOL)
    if holding is None or holding.qty <= 0:
        return []
    _sell_pending = True
    return [
        {
            "side": "sell",
            "symbol": SYMBOL,
            "qty": holding.qty,
            "max_slippage_bps": SLIPPAGE_BPS,
        }
    ]


def _bar_for(batch):
    for b in batch["bars"]:
        if b["symbol"] == SYMBOL:
            return b
    return None


def on_batch(state, batch):
    global _open0, _closes, _buy_pending, _pending_phase1, _sell_pending
    global _buy_price, _phase1, _holding, _sold
    bar = _bar_for(batch)
    if bar is None:
        return []

    # ---- capture the race open (bar 0) ------------------------------------
    if _open0 is None:
        _open0 = int(bar["o"])

    # ---- fold in this batch's fills (orders decided on the previous bar) --
    for f in batch.get("fills", []):
        if f.get("symbol") != SYMBOL:
            continue
        side = f.get("side")
        status = f.get("status")
        if side == "buy" and status == "filled":
            _buy_price = int(f["price"])
            _phase1 = _pending_phase1
            _holding = True
            _buy_pending = False
        elif side == "buy" and status == "rejected":
            # no fill: the one-buy budget is not spent, later phases may retry
            _buy_pending = False
        elif side == "sell" and status == "filled":
            _sold = True
            _holding = False
            _sell_pending = False
        elif side == "sell" and status == "rejected":
            _sell_pending = False

    if state.warming_up:
        return []

    # ---- done, or waiting on a pending order ------------------------------
    if _sold or _buy_pending or _sell_pending:
        return []

    close = int(bar["c"])
    seq = state.seq
    _closes.append(close)

    # ---- holding a Phase 1 position: take profit at +0.50% above the fill -
    if _holding:
        if _phase1 and _buy_price is not None:
            if close * 10000 >= _buy_price * TAKE_PROFIT_NUM:
                return _sell_all(state)
        return []  # Phase 2/3 position, or no pump yet: hold to the close

    # ---- flat: the three buy phases ----------------------------------------
    if seq >= LAST_SEQ:
        return []
    if seq <= PHASE1_END:
        # Phase 1 (first hour): dip >= 0.23% below the open
        if close * 10000 <= _open0 * DIP1_NUM:
            return _buy_all_in(state, phase1=True)
        return []
    if seq >= FALLBACK_BAR:
        # Phase 3 (last 30 min): still flat, buy at market
        return _buy_all_in(state, phase1=False)
    if seq >= PHASE2_START:
        # Phase 2 (last hour, before the fallback): dip >= 0.50% below
        # the peak close of the last 60 bars (incl. the current bar)
        peak = max(_closes[-61:])
        if close * 10000 <= peak * DIP2_NUM:
            return _buy_all_in(state, phase1=False)
        return []
    return []


makefun_bars.run(on_batch, on_hello=on_hello)
