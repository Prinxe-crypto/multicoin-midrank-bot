"""
Multi-coin paper trading bot. Same architecture as the BTC (KXBTCD) bot,
extended to run all 5 coins in one script/workflow, each using its OWN
discovered rank band (not BTC's rank 5-10 blindly applied).

Rank bands, from the separate backtests:
  HYPE : rank 5-10  (strongest edge, ~14-23% ROI)
  SOL  : rank 3-9   (~6-8% ROI)
  BNB  : rank 6-14  (~12-19% ROI)
  XRP  : rank 8-15  (~9-15% ROI, only the ignored tail)
  DOGE : rank 5-7   (weak/unconfirmed edge -- included cautiously with a
         higher price threshold; treat DOGE results with more skepticism
         than the other four)

Known bug already fixed once for BTC: Kalshi's settled status value is
"finalized", not "settled" -- applied here from the start.
"""

import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

COIN_CONFIG = {
    "HYPE": {"series": "KXHYPED", "min_rank": 5,  "max_rank": 10, "min_favored_price": 0.60},
    "SOL":  {"series": "KXSOLD",  "min_rank": 3,  "max_rank": 9,  "min_favored_price": 0.60},
    "BNB":  {"series": "KXBNBD",  "min_rank": 6,  "max_rank": 14, "min_favored_price": 0.60},
    "XRP":  {"series": "KXXRPD",  "min_rank": 8,  "max_rank": 15, "min_favored_price": 0.60},
    "DOGE": {"series": "KXDOGED", "min_rank": 5,  "max_rank": 7,  "min_favored_price": 0.70},
}

OPEN_POSITIONS_PATH = Path("open_positions.csv")
