from pathlib import Path
from datetime import datetime
import csv
import json
import re

from playwright.sync_api import sync_playwright


URL = "https://www.nseindia.com/resources/exchange-communication-holidays"

CSV_FILE = Path("data/nse_holidays.csv")
JSON_FILE = Path("data/nse_holidays.json")


def parse_date(text):
    text = text.strip()

    formats = [
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def main():

    print("Opening NSE holiday page...")

    current_year = datetime.now().year

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1366,
                "height": 900,
            },
            locale="en-IN",
        )

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        print("NSE page loaded.")

        # Wait for the holiday section.
        page.wait_for_timeout(8000)

        # Select current year if the year selector exists.
        selects = page.locator("select")

        print("Select elements found:", selects.count())

        for i in range(selects.count()):

            select = selects.nth(i)

            try:
                options = select.locator("option")

                values = []

                for j in range(options.count()):
                    option = options.nth(j)

                    values.append(
                        (
                            option.get_attribute("value"),
                            clean(option.inner_text()),
                        )
                    )

                year_option = None

                for value, text in values:
                    if str(current_year) in text or str(current_year) == str(value):
                        year_option = value
                        break

                if year_option:
                    print(
                        f"Selecting year {current_year}"
                    )

                    select.select_option(
                        year_option
                    )

                    page.wait_for_timeout(5000)

                    break

            except Exception:
                continue

        # Get all visible tables.
        tables = page.locator("table")

        print(
            "Tables found:",
            tables.count()
        )

        holidays = []

        for i in range(tables.count()):

            table = tables.nth(i)

            try:
                rows = table.locator("tr")

                for r in range(rows.count()):

                    cells = rows.nth(r).locator(
                        "th, td"
                    )

                    values = []

                    for c in range(cells.count()):
                        values.append(
                            clean(
                                cells.nth(c).inner_text()
                            )
                        )

                    if len(values) < 3:
                        continue

                    # Find date anywhere in the row.
                    date_value = None

                    for value in values:
                        parsed = parse_date(value)

                        if parsed:
                            date_value = parsed
                            break

                    if not date_value:
                        continue

                    # We only want the current year.
                    if not date_value.startswith(
                        str(current_year)
                    ):
                        continue

                    # NSE table format:
                    # Sr. No | Date | Day | Description
                    description = values[-1]

                    if (
                        description.lower()
                        in (
                            "description",
                            "day",
                            "date",
                        )
                    ):
                        continue

                    holidays.append(
                        {
                            "date": date_value,
                            "description": description,
                            "market": "NSE Equity",
                        }
                    )

            except Exception:
                continue

        browser.close()

    # Remove duplicates.
    unique = {}

    for holiday in holidays:
        unique[holiday["date"]] = holiday

    holidays = sorted(
        unique.values(),
        key=lambda x: x["date"],
    )

    if not holidays:
        raise RuntimeError(
            "Could not extract NSE holiday table."
        )

    CSV_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Save CSV.
    with CSV_FILE.open(
        "w",
        encoding="utf-8",
        newline="",
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

    # Save JSON.
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
        f"SUCCESS: {len(holidays)} holidays saved."
    )
    print()

    for holiday in holidays:
        print(
            holiday["date"],
            "|",
            holiday["description"],
        )


if __name__ == "__main__":
    main()
