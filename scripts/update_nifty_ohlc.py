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


def fetch_niftyindices():
    """Fetch official daily NIFTY 50 OHLC from NSE Indices as a Yahoo fallback."""
    now_ist = datetime.now(IST).date()
    start = now_ist - timedelta(days=35)
    cinfo = (
        "{'name':'NIFTY 50',"
        f"'startDate':'{start.strftime('%d %b %Y')}',"
        f"'endDate':'{now_ist.strftime('%d %b %Y')}',"
        "'indexName':'NIFTY 50'}"
    )
    body = json.dumps({"cinfo": cinfo}).encode("utf-8")
    page_url = "https://www.niftyindices.com/reports/historical-data"
    api_url = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": page_url,
        "Origin": "https://www.niftyindices.com",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }

    # The historical page establishes a session with the site's edge protection.
    # Do not fail the API fetch solely because this optional bootstrap is blocked.
    try:
        with urlopen(Request(page_url, headers={"User-Agent": headers["User-Agent"]}), timeout=8) as page:
            page.read(1024)
    except Exception as exc:
        print(f"NSE page bootstrap warning: {exc}")

    last_error = None
    payload = None
    for attempt in range(3):
        try:
            req = Request(api_url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=45) as response:
                response_text = response.read().decode("utf-8", errors="replace")
                if "json" not in response.headers.get("Content-Type", "").lower() and not response_text.lstrip().startswith("{"):
                    raise RuntimeError(
                        f"NSE returned non-JSON content (HTTP {response.status}, "
                        f"Content-Type={response.headers.get('Content-Type', 'unknown')})"
                    )
                payload = json.loads(response_text)
            break
        except Exception as exc:
            last_error = exc
            print(f"NSE Indices attempt {attempt + 1}/3 failed: {exc}")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    if payload is None:
        raise RuntimeError(f"NSE Indices API unavailable after retries: {last_error}")

    raw = payload.get("d", "[]")
    data = json.loads(raw) if isinstance(raw, str) and raw not in ("", "false", "[]") else raw
    rows = []
    for item in data or []:
        try:
            d = datetime.strptime(item["HistoricalDate"].strip(), "%d %b %Y").date()
            row = {
                "Date": d.isoformat(),
                "Open": round(float(item["OPEN"].replace(",", "")), 2),
                "High": round(float(item["HIGH"].replace(",", "")), 2),
                "Low": round(float(item["LOW"].replace(",", "")), 2),
                "Close": round(float(item["CLOSE"].replace(",", "")), 2),
            }
            if row["High"] >= max(row["Open"], row["Close"]) and row["Low"] <= min(row["Open"], row["Close"]):
                rows.append(row)
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        raise RuntimeError("NSE Indices returned no valid NIFTY 50 OHLC rows")
    rows.sort(key=lambda r: r["Date"])
    return rows


def fetch_nifty():
    errors = []
    # Prefer the official index publisher. Yahoo is retained as a fallback.
    try:
        rows = fetch_niftyindices()
        print(f"NSE Indices source OK; fetched {len(rows)} rows; latest={rows[-1]['Date']}")
        return rows
    except Exception as exc:
        errors.append(f"NSE Indices: {exc}")
        print(f"NSE Indices source failed: {exc}")

    for attempt in range(4):
        for url in URLS:
            try:
                rows = fetch_url(url)
                print(f"Yahoo source OK: {url}")
                print(f"Fetched {len(rows)} rows; latest={rows[-1]['Date']}")
                return rows
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                print(f"Attempt {attempt + 1} failed: {url} -> {exc}")
        if attempt < 3:
            time.sleep(10)
    raise RuntimeError("NIFTY fetch failed after retries:\n" + "\n".join(errors[-10:]))
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

    print(f"NIFTY UPDATE: previous_latest={old_latest}")
    print(f"NIFTY UPDATE: current_latest={new_latest}")
    print(f"NIFTY UPDATE: total_rows={len(rows)}")

    # Evaluate freshness using India Standard Time, not the runner's UTC clock.
    # NSE holidays are not equivalent to weekdays; allow a holiday/weekend grace
    # window so a valid last trading session does not become a false failure.
    now_ist = datetime.now(IST)
    latest_date = datetime.fromisoformat(new_latest).date()
    age_days = (now_ist.date() - latest_date).days
    print(f"NIFTY UPDATE: current_ist={now_ist.isoformat(timespec='seconds')}")
    print(f"NIFTY UPDATE: latest_session_age_calendar_days={age_days}")

    # A successful provider response can legitimately end several calendar days
    # back because of exchange holidays, weekends, or a delayed holiday calendar.
    # Fail only when the data is clearly stale; otherwise log the last session.
    if age_days > 5:
        raise RuntimeError(
            f"DATA STALE: latest NIFTY session is {new_latest} ({age_days} calendar days old in IST). "
            "More than 5 days have passed without a new session; check source availability and NSE holidays."
        )
    if age_days > 1:
        print(
            f"NIFTY UPDATE WARNING: latest session is {new_latest}; "
            "this may be normal around NSE holidays/weekends. Verify the exchange calendar if unexpected."
        )

    changed = new_latest != old_latest or any(existing.get(r["Date"]) != r for r in new_rows if r["Date"] in existing)
    write_data(rows)
    print(f"NIFTY UPDATE: data_changed={changed}")
    print("NIFTY UPDATE SUCCESS")


if __name__ == "__main__":
    main()
