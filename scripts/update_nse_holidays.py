import csv
import re
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup


URL = "https://www.nseindia.com/resources/exchange-communication-holidays"

CSV_FILE = Path("data/nse_holidays.csv")
JSON_FILE = Path("data/nse_holidays.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def parse_date(text):
    text = clean(text)

    formats = [
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d %b %Y",
        "%d %B %Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def main():

    print("Fetching NSE holiday page...")

    session = requests.Session()

    # Establish NSE session first
    home = session.get(
        "https://www.nseindia.com/",
        headers=HEADERS,
        timeout=40,
    )

    print("NSE home status:", home.status_code)

    response = session.get(
        URL,
        headers=HEADERS,
        timeout=40,
    )

    print("Holiday page status:", response.status_code)

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    holidays = []

    # Search every table on the NSE page.
    for table in soup.find_all("table"):

        rows = table.find_all("tr")

        for row in rows:

            cells = [
                clean(cell.get_text(" ", strip=True))
                for cell in row.find_all(["td", "th"])
            ]

            if len(cells) < 3:
                continue

            # Skip header
            if (
                cells[0].lower() in ("sr. no.", "sr.no", "sr no", "sr. no")
                or cells[1].lower() == "date"
            ):
                continue

            # NSE format:
            # Sr. No | Date | Day | Description
            date_value = None
            description = ""

            # Look for a recognizable date in the row.
            for cell in cells:
                parsed = parse_date(cell)

                if parsed:
                    date_value = parsed
                    break

            if not date_value:
                continue

            # Description is normally the last cell.
            description = cells[-1]

            # Ignore rows that are not actual holiday entries.
            if not description:
                continue

            holidays.append(
                {
                    "date": date_value,
                    "description": description,
                    "market": "NSE Equity",
                }
            )

    # Remove duplicates
    unique = {}

    for item in holidays:
        unique[item["date"]] = item

    holidays = sorted(
        unique.values(),
        key=lambda x: x["date"],
    )

    if not holidays:
        raise RuntimeError(
            "No NSE holiday rows were found on the page. "
            "NSE may have changed the webpage structure."
        )

    # Save directory
    CSV_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # CSV
    with CSV_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "date",
                "description",
                "market",
            ],
        )

        writer.writeheader()
        writer.writerows(holidays)

    # JSON
    import json

    with JSON_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            holidays,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(
        f"SUCCESS: {len(holidays)} NSE equity holidays saved."
    )

    print()

    for item in holidays:
        print(
            item["date"],
            "|",
            item["description"],
        )


if __name__ == "__main__":
    main()
