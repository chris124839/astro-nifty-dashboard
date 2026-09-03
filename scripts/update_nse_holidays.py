import requests
import pandas as pd
from io import StringIO
from pathlib import Path
from datetime import datetime

URL = "https://www.nseindia.com/resources/exchange-communication-holidays"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

response = requests.get(URL, headers=headers, timeout=30)
response.raise_for_status()

tables = pd.read_html(StringIO(response.text))

holiday_table = None

for table in tables:
    cols = [str(c).lower() for c in table.columns]
    if any("date" in c for c in cols) and any(
        "description" in c for c in cols
    ):
        holiday_table = table
        break

if holiday_table is None:
    raise RuntimeError("NSE holiday table not found")

holiday_table.columns = [
    str(c).strip().replace(" ", "_").lower()
    for c in holiday_table.columns
]

# Keep only actual holiday rows
date_col = next(c for c in holiday_table.columns if "date" in c)
desc_col = next(c for c in holiday_table.columns if "description" in c)

holiday_table["date"] = pd.to_datetime(
    holiday_table[date_col],
    errors="coerce",
    dayfirst=True
)

holiday_table = holiday_table.dropna(subset=["date"])

holiday_table["date"] = holiday_table["date"].dt.strftime("%Y-%m-%d")

holiday_table = holiday_table[
    ["date", desc_col]
].rename(columns={desc_col: "description"})

holiday_table["market"] = "NSE Equity"

holiday_table = holiday_table.drop_duplicates(
    subset=["date"]
).sort_values("date")

Path("data").mkdir(exist_ok=True)

holiday_table.to_csv(
    "data/nse_holidays.csv",
    index=False
)

holiday_table.to_json(
    "data/nse_holidays.json",
    orient="records",
    indent=2
)

print(f"Saved {len(holiday_table)} NSE holidays")
print(holiday_table.tail(10).to_string(index=False))
