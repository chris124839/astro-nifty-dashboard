import os
import re
import time
import openpyxl

from bs4 import BeautifulSoup
from datetime import datetime
from dateutil import parser

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# =========================================================
# SETTINGS
# =========================================================

GEONAME_ID = "1254360"
FILE = "data/Planets Transists.xlsx"

PLANETS = {
    "Mercury": "budha-transit-date-time",
    "Venus": "shukra-transit-date-time",
    "Mars": "mangal-transit-date-time",
    "Jupiter": "guru-transit-date-time",
    "Saturn": "shani-transit-date-time",
    "Sun": "surya-transit-date-time",
    "Moon": "chandra-transit-date-time",
}


# =========================================================
# DATE CONVERSION
# =========================================================

def safe_date(value):

    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()

    if not text:
        return None

    # Excel / ISO datetime
    try:
        return datetime.fromisoformat(
            text.replace("Z", "")
        )
    except Exception:
        pass

    # DD/MM/YYYY
    try:
        return datetime.strptime(
            text,
            "%d/%m/%Y"
        )
    except Exception:
        pass

    # General fallback
    try:
        return parser.parse(
            text,
            dayfirst=True
        )
    except Exception:
        return None


# =========================================================
# CHECK EXISTING FILE
# =========================================================

if not os.path.exists(FILE):

    raise FileNotFoundError(
        f"File not found: {FILE}"
    )


# =========================================================
# LOAD EXCEL
# =========================================================

wb = openpyxl.load_workbook(FILE)

if "02_Raw_Transits" not in wb.sheetnames:

    raise ValueError(
        "Sheet '02_Raw_Transits' not found."
    )

ws = wb["02_Raw_Transits"]


# =========================================================
# FIND LAST DATE
# =========================================================

last_date = None

for row in ws.iter_rows(
    min_row=2,
    values_only=True
):

    if not row:
        continue

    value = row[0]

    dt = safe_date(value)

    if dt is None:
        continue

    if last_date is None or dt > last_date:
        last_date = dt


if last_date is None:

    raise ValueError(
        "No valid dates found in the Excel file."
    )


next_year = last_date.year + 1

print(
    f"Existing last date: "
    f"{last_date.strftime('%d/%m/%Y')}"
)

print(
    f"Next year to scrape: {next_year}"
)


# =========================================================
# EXISTING RECORDS
# =========================================================

existing_records = set()

for row in ws.iter_rows(
    min_row=2,
    values_only=True
):

    if not row or not row[0]:
        continue

    key = tuple(
        str(x).strip()
        if x is not None
        else ""
        for x in row[:5]
    )

    existing_records.add(key)


# =========================================================
# CHROME
# =========================================================

options = Options()

options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")
options.add_argument("--lang=en-US")

driver = webdriver.Chrome(
    options=options
)

wait = WebDriverWait(
    driver,
    30
)


# =========================================================
# SCRAPE NEXT YEAR
# =========================================================

total_added = 0

try:

    for planet, slug in PLANETS.items():

        print()
        print("=" * 60)
        print(
            f"Scraping {planet} - {next_year}"
        )
        print("=" * 60)

        url = (
            "https://www.drikpanchang.com/"
            "planet/transit/"
            f"{slug}.html"
            f"?year={next_year}"
            f"&geoname-id={GEONAME_ID}"
            f"&lang=en"
        )

        print(url)

        try:

            driver.get(url)

            wait.until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        ".dpCard, .dpHighlightedCard"
                    )
                )
            )

            time.sleep(2)

        except Exception as e:

            print(
                f"Page loading error: {e}"
            )

            continue


        soup = BeautifulSoup(
            driver.page_source,
            "html.parser"
        )

        cards = soup.select(
            ".dpCard, .dpHighlightedCard"
        )

        added = 0

        for card in cards:

            title = card.find(
                "div",
                class_="dpTitle"
            )

            value = card.find(
                "div",
                class_="dpValue"
            )

            if not title or not value:
                continue

            raasi = title.get_text(
                " ",
                strip=True
            )

            raw = value.get_text(
                " ",
                strip=True
            )


            # =================================================
            # RETROGRADE
            # =================================================

            retrograde = (
                "Retrograde"
                if (
                    "\u21ba" in raw
                    or
                    "\u21bb" in raw
                    or
                    "Retrograde" in raw
                )
                else "Forward"
            )


            # =================================================
            # CLEAN TEXT
            # =================================================

            clean = raw

            clean = clean.replace(
                "\u21ba",
                " "
            )

            clean = clean.replace(
                "\u21bb",
                " "
            )

            clean = re.sub(
                r"\s+",
                " ",
                clean
            ).strip()


            # =================================================
            # FIND DATE + TIME
            # =================================================

            pattern = (
                r"([A-Za-z]+\s+\d{1,2},\s+\d{4}"
                r".*?"
                r"\d{1,2}:\d{2})"
            )

            match = re.search(
                pattern,
                clean
            )

            if not match:
                continue


            try:

                dt = parser.parse(
                    match.group(1)
                )

            except Exception:

                continue


            # =================================================
            # ONLY NEXT YEAR
            # =================================================

            if dt.year != next_year:
                continue


            date_value = dt.strftime(
                "%d/%m/%Y"
            )

            time_value = dt.strftime(
                "%H:%M"
            )


            # =================================================
            # RECORD
            # =================================================

            row = (
                date_value,
                planet,
                raasi,
                time_value,
                retrograde,
                retrograde
            )


            key = tuple(
                str(x)
                for x in row[:5]
            )


            # =================================================
            # DUPLICATE CHECK
            # =================================================

            if key in existing_records:
                continue


            ws.append(row)

            existing_records.add(key)

            added += 1
            total_added += 1


        print(
            f"Added: {added}"
        )


finally:

    driver.quit()


# =========================================================
# SORT COMPLETE DATASET
# =========================================================

rows = list(
    ws.iter_rows(
        min_row=2,
        values_only=True
    )
)


def sort_key(row):

    dt = safe_date(row[0])

    if dt is None:
        dt = datetime.max

    planet = (
        str(row[1])
        if row[1] is not None
        else ""
    )

    time_value = (
        str(row[3])
        if row[3] is not None
        else ""
    )

    return (
        dt,
        planet,
        time_value
    )


rows.sort(
    key=sort_key
)


# =========================================================
# REWRITE SORTED DATA
# =========================================================

if ws.max_row > 1:

    ws.delete_rows(
        2,
        ws.max_row - 1
    )


for row in rows:

    ws.append(row)


# =========================================================
# FORMAT
# =========================================================

ws.freeze_panes = "A2"

ws.auto_filter.ref = ws.dimensions

widths = {
    "A": 14,
    "B": 14,
    "C": 20,
    "D": 10,
    "E": 15,
    "F": 15
}

for column, width in widths.items():

    ws.column_dimensions[
        column
    ].width = width


# =========================================================
# SAVE
# =========================================================

wb.save(FILE)


# =========================================================
# RESULT
# =========================================================

print()
print("=" * 60)
print("PLANET TRANSIT UPDATE COMPLETE")
print("=" * 60)

print(
    f"Previous last year: {last_date.year}"
)

print(
    f"New year scraped: {next_year}"
)

print(
    f"New records added: {total_added}"
)

print(
    f"Total records now: {len(rows)}"
)

print(
    f"Saved: {FILE}"
)
