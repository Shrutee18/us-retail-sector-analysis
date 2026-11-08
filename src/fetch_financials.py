import json
import os
import ssl
import time
import urllib.request
from pathlib import Path

import certifi
import pandas as pd

USER_AGENT = os.environ.get("SEC_USER_AGENT", "")
assert USER_AGENT, "Set SEC_USER_AGENT to your name and email, e.g. SEC_USER_AGENT=\"Your Name you@example.com\""

TICKERS = ["WMT", "TGT", "COST", "KR", "HD", "LOW", "BBY", "DG"]
FIRST_YEAR, LAST_YEAR = 2019, 2025

METRICS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
                        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
                        "CostOfGoodsSoldExcludingDepreciationDepletionAndAmortization"],
    "gross_profit": ["GrossProfit"],
    "sga_expense": ["SellingGeneralAndAdministrativeExpense"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "inventory": ["InventoryNet"],
    "fifo_inventory": ["FIFOInventoryAmount"],
    "lifo_reserve": ["InventoryLIFOReserve"],
    "total_assets": ["Assets"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
}
INSTANT = {"inventory", "fifo_inventory", "lifo_reserve", "total_assets"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        return json.loads(r.read())


def aligned_year(end):
    # Fiscal years ending January to June are mostly the previous calendar year
    return end.year - 1 if end.month <= 6 else end.year


raw_dir = Path("data/raw")
raw_dir.mkdir(parents=True, exist_ok=True)
tmap = get("https://www.sec.gov/files/company_tickers.json")
by_ticker = {v["ticker"]: v for v in tmap.values()}

rows = []
for t in TICKERS:
    info = by_ticker.get(t)
    if not info:
        print(f"{t}: not found in ticker map")
        continue
    cik = str(info["cik_str"]).zfill(10)
    time.sleep(0.2)
    facts = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    (raw_dir / f"companyfacts_{t}.json").write_text(json.dumps(facts))
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for metric, tags in METRICS.items():
        covered = set()
        for tag in tags:
            items = gaap.get(tag, {}).get("units", {}).get("USD", [])
            best = {}
            for it in items:
                if it.get("form") not in ("10-K", "10-K/A") or it.get("fp") != "FY":
                    continue
                end = pd.to_datetime(it["end"])
                if metric not in INSTANT:
                    if "start" not in it:
                        continue
                    days = (end - pd.to_datetime(it["start"])).days
                    if not 350 <= days <= 380:
                        continue
                key = it["end"]
                if key not in best or it["filed"] > best[key]["filed"]:
                    best[key] = it
            for end_s, it in best.items():
                if end_s in covered:
                    continue
                covered.add(end_s)
                end = pd.to_datetime(end_s)
                note = ""
                if "ExcludingDepreciation" in tag:
                    note = "cost excludes depreciation; not comparable with other companies"
                if tag == "NetIncomeLossAvailableToCommonStockholdersBasic":
                    note = "net income available to common stockholders"
                rows.append({"ticker": t, "company": info["title"], "metric": metric,
                             "period_end": end_s, "calendar_year": aligned_year(end),
                             "value_usd": it["val"], "tag_used": tag, "filed": it["filed"],
                             "note": note})
    print(f"{t}: fetched {info['title']}")

long = pd.DataFrame(rows)
long = long[(long.calendar_year >= FIRST_YEAR) & (long.calendar_year <= LAST_YEAR)]
# if two period ends map to one calendar year for a company and metric, keep the latest
long = long.sort_values("period_end").groupby(["ticker", "metric", "calendar_year"], as_index=False).last()

# Derive inventory where there is no ordinary inventory tag: FIFO inventory minus LIFO reserve
helpers = long[long.metric.isin(["fifo_inventory", "lifo_reserve"])]
long = long[~long.metric.isin(["fifo_inventory", "lifo_reserve"])]
f = helpers[helpers.metric == "fifo_inventory"].set_index(["ticker", "calendar_year"])
r = helpers[helpers.metric == "lifo_reserve"].set_index(["ticker", "calendar_year"])
have = set(zip(long[long.metric == "inventory"].ticker, long[long.metric == "inventory"].calendar_year))
extra = []
for key in f.index.intersection(r.index):
    if key in have:
        continue
    extra.append({"ticker": key[0], "company": f.loc[key, "company"], "metric": "inventory",
                  "calendar_year": key[1], "period_end": f.loc[key, "period_end"],
                  "value_usd": f.loc[key, "value_usd"] - r.loc[key, "value_usd"],
                  "tag_used": "derived: FIFOInventoryAmount - InventoryLIFOReserve", "filed": "",
                  "note": "derived, check against the balance sheet"})
if extra:
    long = pd.concat([long, pd.DataFrame(extra)], ignore_index=True)

Path("data/clean").mkdir(parents=True, exist_ok=True)
long.to_csv("data/clean/retail_financials_long.csv", index=False)
wide = long.pivot_table(index=["ticker", "company", "calendar_year"], columns="metric", values="value_usd").reset_index()
wide.to_csv("data/clean/retail_financials_wide.csv", index=False)

print("\nRows:", len(long))
print("\nHow many fiscal years we have, by company and metric:")
print(long.pivot_table(index="ticker", columns="metric", values="value_usd", aggfunc="count").fillna(0).astype(int).to_string())
print("\nRevenue (billions USD) by company and year:")
print((wide.pivot(index="calendar_year", columns="ticker", values="revenue") / 1e9).round(1).to_string())
print("\nKroger inventory and cost of revenue (billions USD):")
print((wide[wide.ticker == "KR"].set_index("calendar_year")[["inventory", "cost_of_revenue"]] / 1e9).round(2).to_string())
print("\nTarget net income (billions USD):")
print((wide[wide.ticker == "TGT"].set_index("calendar_year")["net_income"] / 1e9).round(2).to_string())
print("\nRows carrying a comparability note:")
print(long[long.note != ""].groupby(["ticker", "metric", "tag_used"]).size().to_string())
