import csv
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CSV_FILE = ROOT / "data" / "nifty_ohlc.csv"
JSON_FILE = ROOT / "data" / "nifty_ohlc.json"

# Yahoo Finance chart endpoint for NIFTY 50 (^NSEI).
# We keep the source isolated so it can be replaced later if needed.
URL = "https://query1.finance.yahoo.com/v8/finance/chart/^NSEI"

def fetch_nifty():
    now = int(time.time())
    start = now - 14 * 24 * 60 * 60
    url = f"{URL}?period1={start}&period2={now}&interval=1d&events=history"

    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_error = None

    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                payload = json.loads(response.read().decode("utf-8"))
            break
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError(f"Nifty request failed: {last_error}")

    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    rows = []
    for i, ts in enumerate(timestamps):
        o, h, l, c = (quote[k][i] for k in ("open", "high", "low", "close"))
        if None in (o, h, l, c):
            continue
        if not (h >= o and h >= c and l <= o and l <= c and h >= l):
            raise RuntimeError(f"Invalid OHLC for timestamp {ts}")

        # NIFTY timestamps are converted to India calendar date.
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        date = dt.date().isoformat()
        rows.append({
            "Date": date,
            "Open": round(float(o), 2),
            "High": round(float(h), 2),
            "Low": round(float(l), 2),
            "Close": round(float(c), 2),
        })

    if not rows:
        raise RuntimeError("No valid NIFTY OHLC rows returned.")

    return rows

def merge_and_write(new_rows):
    existing = {}
    if CSV_FILE.exists():
        with CSV_FILE.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Date"):
                    existing[row["Date"]] = {
                        "Date": row["Date"],
                        "Open": float(row["Open"]),
                        "High": float(row["High"]),
                        "Low": float(row["Low"]),
                        "Close": float(row["Close"]),
                    }

    for row in new_rows:
        existing[row["Date"]] = row

    rows = [existing[d] for d in sorted(existing)]

    CSV_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CSV_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Open", "High", "Low", "Close"])
        writer.writeheader()
        writer.writerows(rows)

    JSON_FILE.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    print(f"NIFTY UPDATE SUCCESS: received={len(new_rows)}, total={len(rows)}")
    print(f"Latest date: {rows[-1]['Date']}")

if __name__ == "__main__":
    merge_and_write(fetch_nifty())
