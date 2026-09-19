name: Multi-Coin Mid-Rank Paper Trading

on:
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch: {}
  repository_dispatch:
    types: [run-multicoin]

jobs:
  paper-trade:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests pandas tabulate

      - name: Run paper trading logic
        run: python multicoin_paper_trade_logic.py

      - name: Commit updated positions
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          touch open_positions.csv closed_positions.csv
          git add open_positions.csv closed_positions.csv
          git diff --staged --quiet || git commit -m "Update multi-coin paper positions [skip ci]"
          git push
