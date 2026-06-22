"""
AESO Pool Price Fetcher — Alberta Gas Morning Brief
Pulls the Alberta power pool price (CAD/MWh) from AESO's public API
(Azure APIM gateway). Power price is context for in-province gas-fired
generation demand, not a Henry Hub driver — treated as a light-weight signal.

Setup:
  1. Sign up for a free key at https://developer-apim.aeso.ca/ (Products ->
     subscribe to the Pool Price Report product).
  2. Add the primary key to your .env as AESO_API_KEY=<key>.

Known uncertainty (flagging honestly rather than guessing silently):
AESO has published this report under two different hosts depending on
era/docs, and the auth header name varies across their own examples:
  - https://api.aeso.ca/report/v1.1/price/poolPrice
  - https://apimgw.aeso.ca/public/poolprice-api/v1.1/price/poolPrice
  - header name: "API-KEY" (per AESO's own APIM gateway PDF) — some examples
    use "X-API-Key" or "Ocp-Apim-Subscription-Key" instead.
This module tries each host/header combo in turn and reports exactly which
one worked (or why all failed) so a real key + a live run can confirm/correct
this in one pass.
"""

import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
AESO_KEY = os.getenv("AESO_API_KEY")

_ENDPOINTS = [
    "https://api.aeso.ca/report/v1.1/price/poolPrice",
    "https://apimgw.aeso.ca/public/poolprice-api/v1.1/price/poolPrice",
]
_HEADER_NAMES = ["API-KEY", "X-API-Key", "Ocp-Apim-Subscription-Key"]


def fetch_pool_price(days: int = 30) -> pd.DataFrame:
    """
    Alberta Pool Price (CAD/MWh), hourly from AESO -> resampled to daily mean.
    Returns DataFrame indexed by date with column 'aeso_price_cad_mwh'.
    Non-fatal: returns an empty DataFrame (with a printed warning) if the key
    is missing or every endpoint/header combo fails, so the rest of the brief
    still generates.
    """
    if not AESO_KEY:
        print("Warning: AESO_API_KEY not set. Skipping AESO power price.")
        return pd.DataFrame(columns=["aeso_price_cad_mwh"])

    end = datetime.today().date()
    start = end - timedelta(days=days)
    params = {"startDate": start.strftime("%Y-%m-%d"), "endDate": end.strftime("%Y-%m-%d")}

    attempts = []
    for url in _ENDPOINTS:
        for header_name in _HEADER_NAMES:
            try:
                r = requests.get(url, headers={header_name: AESO_KEY}, params=params, timeout=15)
                if r.status_code in (401, 403):
                    attempts.append(f"{r.status_code} @ {url} [{header_name}]")
                    continue
                r.raise_for_status()
                payload = r.json()
                rows = (
                    payload.get("return", {}).get("Pool Price Report")
                    or payload.get("return", {}).get("Pool.Price.Report")
                    or []
                )
                if not rows:
                    attempts.append(f"200 but no rows @ {url} [{header_name}]")
                    continue
                df = pd.DataFrame(rows)
                date_col = next((c for c in df.columns if "datetime" in c.lower()), None)
                price_col = next((c for c in df.columns if c.lower() == "pool_price"), None)
                if not date_col or not price_col:
                    attempts.append(f"unexpected shape @ {url}: {list(df.columns)}")
                    continue
                df[date_col] = pd.to_datetime(df[date_col])
                df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
                daily = (
                    df.set_index(date_col)[price_col]
                    .resample("D").mean()
                    .rename("aeso_price_cad_mwh")
                    .to_frame()
                )
                print(f"AESO pool price OK via {url} [{header_name}]")
                return daily
            except Exception as e:
                attempts.append(f"{type(e).__name__} @ {url} [{header_name}]: {e}")
                continue

    print("Warning: AESO pool price fetch failed on all endpoint/header combos:")
    for a in attempts:
        print(f"  - {a}")
    print("Continuing without AESO power price.")
    return pd.DataFrame(columns=["aeso_price_cad_mwh"])


if __name__ == "__main__":
    df = fetch_pool_price(days=14)
    print(df.tail(10).to_string() if not df.empty else "No data / AESO_API_KEY not configured.")
