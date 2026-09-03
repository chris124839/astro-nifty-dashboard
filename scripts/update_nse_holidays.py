import json
import re
from pathlib import Path
from datetime import datetime

import requests


NSE_HOME = "https://www.nseindia.com/"
NSE_HOLIDAY_API = "https://www.nseindia.com/api/holiday-master?type=trading"

OUTPUT_CSV = Path("data/nse_holidays.csv")
OUTPUT_JSON = Path("data/nse_holidays.json")


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HOME,
    "Connection": "keep-alive",
}


def get_nse_holidays():
    session = requests.Session()

    # First establish NSE session/cookies.
    r = session.get(
        NSE_HOME,
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()

    # Then request the official holiday API.
    r = session.get(
        NSE_HOLIDAY_API,
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()

    if not r.text.strip():
        raise RuntimeError("NSE returned an empty response")

    try:
        payload = r.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"NSE did not return JSON. HTTP {r.status_code}. "
            f"Response starts with: {r.text[:300]}"
        ) from exc

    return payload


def extract_holidays(payload):
    """
    NSE holiday-master returns segment-specific arrays.

    For the NIFTY dashboard we need the Capital Market /
    Equity trading holidays, normally under CM.
    """

    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected NSE holiday API response")

    # Common NSE structure:
    # {
    #   "CM": [...],
    #   "FO": [...],
    #   ...
    # }
    rows = payload.get("CM")

    # Some responses may use other capitalization.
    if rows is None:
        for key, value in payload.items():
            if str(key).upper() == "CM":
                rows = value
                break

    if not isinstance(rows, list):
        raise RuntimeError(
            "NSE Capital Market (CM) holiday data was not found. "
            f"Available keys: {list(payload.keys())}"
        )

    result = []

    for item in rows:
        if not isinstance(item, dict):
            continue

        # NSE commonly uses tradingDate / description.
        raw_date = (
            item.get("tradingDate")
            or item.get("date")
            or item.get("Date")
        )

        description = (
            item.get("description")
            or item.get("Description")
            or item.get("holiday")
            or item.get("Holiday")
            or ""
        )

        if not raw_date:
            continue

        # Convert DD-Mon-YYYY / DD-MM-YYYY / YYYY-MM-DD safely.
        parsed = None

        for fmt in (
            "%d-%b-%Y",
            "%d-%B-%Y",
            "%d-%m-%Y",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d/%b/%Y",
        ):
            try:
                parsed = datetime.strptime(
                    str(raw_date).strip(),
                    fmt,
                )
                break
            except ValueError:
                pass

        if parsed is None:
            # Last attempt: extract an ISO date.
            match = re.search(
                r"\d{4}-\d{2}-\d{2}",
                str(raw_date),
            )

            if match:
                parsed = datetime.strptime(
                    match.group(0),
                    "%Y-%m-%d",
                )

        if parsed is None:
            print(f"Skipping unrecognised NSE date: {raw_date}")
            continue

        result.append(
            {
                "date": parsed.strftime("%Y-%m-%d"),
                "description": str(description).strip(),
                "market": "NSE Equity",
            }
        )

    # Remove duplicates.
    unique = {}

    for row in result:
        unique[row["date"]] = row

    return sorted(
        unique.values(),
        key=lambda x: x["date"],
    )


def save_files(holidays):
    OUTPUT_CSV.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # CSV
    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        f.write("date,description,market\n")

        for row in holidays:
            description = row["description"].replace('"', '""')

            f.write(
                f'{row["date"]},"{description}",'
                f'"{row["market"]}"\n'
            )

    # JSON
    with OUTPUT_JSON.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            holidays,
            f,
            ensure_ascii=False,
            indent=2,
        )


def main():
    print("Fetching NSE trading holidays...")

    payload = get_nse_holidays()

    holidays = extract_holidays(payload)

    if not holidays:
        raise RuntimeError(
            "NSE returned no Capital Market holidays."
        )

    save_files(holidays)

    print()
    print(f"Saved {len(holidays)} NSE equity holidays.")
    print()

    for row in holidays:
        print(
            f'{row["date"]} | '
            f'{row["description"]}'
        )


if __name__ == "__main__":
    main()
