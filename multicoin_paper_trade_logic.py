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
CLOSED_POSITIONS_PATH = Path("closed_positions.csv")

COLUMNS_OPEN = ["coin", "ticker", "event_ticker", "rank", "favored_side", "entry_price", "opened_at"]
COLUMNS_CLOSED = COLUMNS_OPEN + ["result", "won", "pnl", "closed_at"]


def get_open_markets(series_ticker):
    all_markets = []
    cursor = None
    while True:
        params = {"series_ticker": series_ticker, "status": "open", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(f"{BASE_URL}/markets", params=params)
        resp.raise_for_status()
        data = resp.json()
        markets = data.get("markets", [])
        all_markets.extend(markets)
        cursor = data.get("cursor")
        if not cursor or not markets:
            break
    return pd.DataFrame(all_markets)


def get_settled_status(tickers):
    results = {}
    for ticker in tickers:
        resp = requests.get(f"{BASE_URL}/markets/{ticker}")
        if resp.status_code == 200:
            results[ticker] = resp.json().get("market", {})
    return results


def load_positions():
    open_pos = pd.read_csv(OPEN_POSITIONS_PATH) if OPEN_POSITIONS_PATH.exists() else pd.DataFrame(columns=COLUMNS_OPEN)
    closed_pos = pd.read_csv(CLOSED_POSITIONS_PATH) if CLOSED_POSITIONS_PATH.exists() else pd.DataFrame(columns=COLUMNS_CLOSED)
    return open_pos, closed_pos


def check_and_close_settled(open_pos, closed_pos):
    if len(open_pos) == 0:
        return open_pos, closed_pos

    still_open_rows = []
    newly_closed_rows = []
    settlement_info = get_settled_status(open_pos["ticker"].tolist())

    for _, row in open_pos.iterrows():
        market = settlement_info.get(row["ticker"])
        if market and market.get("status") == "finalized":
            result = str(market.get("result", "")).lower()
            won = (result == row["favored_side"])
            pnl = (1 - row["entry_price"]) if won else -row["entry_price"]
            newly_closed_rows.append({
                **row.to_dict(),
                "result": result,
                "won": won,
                "pnl": pnl,
                "closed_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            still_open_rows.append(row.to_dict())

    if newly_closed_rows:
        closed_pos = pd.concat([closed_pos, pd.DataFrame(newly_closed_rows)], ignore_index=True)
    open_pos = pd.DataFrame(still_open_rows, columns=open_pos.columns)
    return open_pos, closed_pos


def find_new_entries_for_coin(coin, config, open_pos):
    markets_df = get_open_markets(config["series"])
    if len(markets_df) == 0:
        return pd.DataFrame(columns=COLUMNS_OPEN)

    markets_df["volume_fp"] = pd.to_numeric(markets_df["volume_fp"], errors="coerce")
    markets_df["yes_bid_dollars"] = pd.to_numeric(markets_df["yes_bid_dollars"], errors="coerce")
    markets_df["no_bid_dollars"] = pd.to_numeric(markets_df["no_bid_dollars"], errors="coerce")

    markets_df = markets_df[markets_df["volume_fp"] > 0].copy()
    if len(markets_df) == 0:
        return pd.DataFrame(columns=COLUMNS_OPEN)

    markets_df["rank_in_event"] = markets_df.groupby("event_ticker")["volume_fp"].rank(ascending=False, method="first")

    candidates = markets_df[
        (markets_df["rank_in_event"] >= config["min_rank"]) & (markets_df["rank_in_event"] <= config["max_rank"])
    ]

    already_open_tickers = set(open_pos[open_pos["coin"] == coin]["ticker"]) if len(open_pos) > 0 else set()

    new_rows = []
    for _, row in candidates.iterrows():
        if row["ticker"] in already_open_tickers:
            continue

        yes_bid = row["yes_bid_dollars"]
        no_bid = row["no_bid_dollars"]
        if pd.isna(yes_bid) or pd.isna(no_bid):
            continue

        if yes_bid >= config["min_favored_price"]:
            side, price = "yes", yes_bid
        elif no_bid >= config["min_favored_price"]:
            side, price = "no", no_bid
        else:
            continue

        new_rows.append({
            "coin": coin,
            "ticker": row["ticker"],
            "event_ticker": row["event_ticker"],
            "rank": int(row["rank_in_event"]),
            "favored_side": side,
            "entry_price": price,
            "opened_at": datetime.now(timezone.utc).isoformat(),
        })

    return pd.DataFrame(new_rows, columns=COLUMNS_OPEN)


def write_summary(open_pos, closed_pos):
    summary = f"## Multi-Coin Mid-Rank Edge — Paper Trading Dashboard\n\n"
    summary += f"**Last run:** {datetime.now(timezone.utc).isoformat()}\n\n"
    summary += f"### Overall: {len(open_pos)} open, {len(closed_pos)} closed\n\n"

    if len(closed_pos) > 0:
        summary += "### Per-coin performance:\n\n"
        per_coin = closed_pos.groupby("coin").agg(
            n=("won", "count"),
            win_rate=("won", "mean"),
            total_pnl=("pnl", "sum"),
        )
        per_coin["avg_pnl_per_trade"] = per_coin["total_pnl"] / per_coin["n"]
        summary += per_coin.to_markdown()
        summary += "\n\n"

    if len(open_pos) > 0:
        summary += f"### Currently open ({len(open_pos)}):\n\n"
        summary += open_pos[["coin", "ticker", "rank", "favored_side", "entry_price"]].to_markdown(index=False)
        summary += "\n\n"

    print(summary)

    import os
    if "GITHUB_STEP_SUMMARY" in os.environ:
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary)


def main():
    open_pos, closed_pos = load_positions()
    print(f"Loaded {len(open_pos)} open, {len(closed_pos)} closed positions")

    print("Checking for settled positions...")
    open_pos, closed_pos = check_and_close_settled(open_pos, closed_pos)

    for coin, config in COIN_CONFIG.items():
        print(f"Scanning {coin} (rank {config['min_rank']}-{config['max_rank']})...")
        new_entries = find_new_entries_for_coin(coin, config, open_pos)
        print(f"  Found {len(new_entries)} new entries")
        if len(new_entries) > 0:
            open_pos = pd.concat([open_pos, new_entries], ignore_index=True)

    open_pos.to_csv(OPEN_POSITIONS_PATH, index=False)
    closed_pos.to_csv(CLOSED_POSITIONS_PATH, index=False)

    write_summary(open_pos, closed_pos)


if __name__ == "__main__":
    main()
