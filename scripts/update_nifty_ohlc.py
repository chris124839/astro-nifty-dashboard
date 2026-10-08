import csv
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CSV_FILE = ROOT / "data" / "nifty_ohlc.csv"
JSON_FILE = ROOT / "data" / "nifty_ohlc.json"

URLS = [
    "https://query1.finance.yahoo.com/v8/finance/chart/^NSEI",
    "https://query2.finance.yahoo.com/v8/finance/chart/^NSEI",
]
IST = ZoneInfo("Asia/Kolkata")


def fetch_url(base_url):
    now = int(time.time())
    start = now - 30 * 24 * 60 * 60
    url = f"{base_url}?period1={start}&period2={now}&interval=1d&events=history"
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
    })
    with urlopen(req, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))

    result = payload.get("chart", {}).get("result")
    if not result:
        raise RuntimeError("Yahoo returned no chart result")
    result = result[0]
    timestamps = result.get("timestamp") or []
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    rows = []

    for i, ts in enumerate(timestamps):
        try:
            o, h, l, c = (quote[k][i] for k in ("open", "high", "low", "close"))
        except (IndexError, KeyError, TypeError):
            continue
        if None in (o, h, l, c):
            continue
        if not (h >= o and h >= c and l <= o and l <= c and h >= l):
            continue
        # Yahoo timestamps are epoch seconds. Convert to the NSE calendar date.
        d = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(IST).date()
        rows.append({
            "Date": d.isoformat(),
            "Open": round(float(o), 2),
            "High": round(float(h), 2),
            "Low": round(float(l), 2),
            "Close": round(float(c), 2),
        })

    if not rows:
        raise RuntimeError("No valid NIFTY rows returned")
    return rows


def fetch_nifty():
    errors = []
    for attempt in range(8):
        for url in URLS:
            try:
                rows = fetch_url(url)
                print(f"Yahoo source OK: {url}")
                print(f"Fetched {len(rows)} rows; latest={rows[-1]['Date']}")
                return rows
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                print(f"Attempt {attempt + 1} failed: {url} -> {exc}")
        if attempt < 7:
            time.sleep(15)
    raise RuntimeError("NIFTY fetch failed after retries:\n" + "\n".join(errors[-8:]))


def read_existing():
    existing = {}
    if CSV_FILE.exists():
        with CSV_FILE.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("Date"):
                    continue
                try:
                    existing[row["Date"]] = {
                        "Date": row["Date"],
                        "Open": float(row["Open"]),
                        "High": float(row["High"]),
                        "Low": float(row["Low"]),
                        "Close": float(row["Close"]),
                    }
                except (KeyError, ValueError):
                    continue
    return existing


def write_data(rows):
    CSV_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CSV_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Open", "High", "Low", "Close"])
        writer.writeheader()
        writer.writerows(rows)
    JSON_FILE.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def main():
    new_rows = fetch_nifty()
    existing = read_existing()
    old_latest = max(existing) if existing else "NONE"

    for row in new_rows:
        existing[row["Date"]] = row

    rows = [existing[d] for d in sorted(existing)]
    new_latest = rows[-1]["Date"]
    changed = new_latest != old_latest or any(existing.get(r["Date"]) != r for r in new_rows if r["Date"] in existing)

    write_data(rows)

    print(f"NIFTY UPDATE: previous_latest={old_latest}")
    print(f"NIFTY UPDATE: current_latest={new_latest}")
    print(f"NIFTY UPDATE: total_rows={len(rows)}")

    # Never silently call an old dataset a successful refresh on a normal weekday.
    now_ist = datetime.now(IST)
    if now_ist.weekday() < 5:
        age_days = (now_ist.date() - datetime.fromisoformat(new_latest).date()).days
        # A 3-day allowance covers a weekend and a single exchange holiday.
        if age_days > 3:
            raise RuntimeError(
                f"DATA STALE: latest NIFTY session is {new_latest}; today is {now_ist.date()}. "
                "Yahoo did not provide a sufficiently recent trading session."
            )

    print("NIFTY UPDATE SUCCESS")


if __name__ == "__main__":
    main()
