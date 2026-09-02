# NIFTY OHLC Automation

This folder contains a GitHub Actions automation that updates NIFTY 50 daily OHLC data.

Source: Yahoo Finance chart endpoint for `^NSEI`.

Schedule:
- Monday-Friday
- 6:45 PM IST
- Manual run is also available from GitHub Actions.

Generated files:
- `data/nifty_ohlc.csv`
- `data/nifty_ohlc.json`

This automation intentionally does NOT change planetary data, NSE holidays, or dashboard calculations.
