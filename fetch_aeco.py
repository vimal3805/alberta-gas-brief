"""
AECO Price Fetcher — Alberta Gas Morning Brief (OPTIONAL PAID DATA PLUG-IN)

This is the actual missing piece for a true "Alberta gas" price — AECO-C /
NIT (Nova Inventory Transfer) is the real Alberta benchmark, distinct from
Henry Hub (US gas) and from AESO (Alberta *power*, not gas).

Researched directly (see project notes): there is no free, daily AECO
source anywhere legitimate. The Alberta Energy Regulator only publishes an
ANNUAL average (useless for a daily brief). The only real daily sources are
paid subscriptions:
  - NGI (Natural Gas Intelligence) — naturalgasintel.com, API at
    api.ngidata.com, point code "CDNNOVA" for NOVA/AECO C.
  - ICE NGX — ice.com/ngx, the exchange AECO actually trades on.

This module is entirely optional and gated: if AECO_API_KEY / AECO_API_URL
aren't set in .env, it silently returns nothing and the rest of the brief
runs exactly as it does today — zero impact on anyone without a
subscription. If you have one, fill in the request logic below to match.

Honesty flag: the exact request/response shape below is an ILLUSTRATIVE
SKELETON, not a verified working call — I don't have access to either
paid API's actual documentation (they're behind the subscription wall by
design). Whoever wires this up with a real key will need to adjust the
request params, headers, and response parsing to match their provider's
actual docs. The contract narrative.py depends on is fixed though:

    fetch_aeco_price(days=14) -> pd.DataFrame
        index: dates
        column: 'aeco_price_cad_gj'   (CAD per gigajoule, daily)

Setup:
  1. Add to your .env (leave blank/omit to skip this feature entirely):
       AECO_API_KEY=<your subscription key>
       AECO_API_URL=<your provider's base price endpoint>
  2. Adjust the request below — headers, params, response parsing — to
     match whatever your subscription's actual API documentation says.
"""

import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
AECO_API_KEY = os.getenv("AECO_API_KEY")
AECO_API_URL = os.getenv("AECO_API_URL")  # e.g. your NGI/ICE NGX endpoint


def fetch_aeco_price(days: int = 14) -> pd.DataFrame:
    """
    AECO-C / NIT price (CAD/GJ), daily. Requires a paid NGI or ICE NGX
    subscription (see module docstring). Silently returns an empty
    DataFrame if AECO_API_KEY/AECO_API_URL aren't set — no warning spam
    for the majority of users who don't have a subscription. Non-fatal
    on any other failure too, so a misconfigured key never breaks the
    rest of the brief.
    """
    if not AECO_API_KEY or not AECO_API_URL:
        return pd.DataFrame(columns=["aeco_price_cad_gj"])

    try:
        end = datetime.today().date()
        start = end - timedelta(days=days)

        # --- ADJUST to match your provider's actual API ---
        r = requests.get(
            AECO_API_URL,
            headers={"Authorization": f"Bearer {AECO_API_KEY}"},
            params={
                "location": "CDNNOVA",      # NGI's point code for NOVA/AECO C
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            timeout=15,
        )
        r.raise_for_status()
        payload = r.json()

        # --- ADJUST to match your provider's actual response shape ---
        rows = payload.get("data", payload if isinstance(payload, list) else [])
        df = pd.DataFrame(rows)
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        price_col = next((c for c in df.columns if "price" in c.lower()), None)
        if not date_col or not price_col:
            print(f"Warning: unexpected AECO response shape {list(df.columns)}. "
                  f"Adjust fetch_aeco.py's parsing to match your provider's actual API.")
            return pd.DataFrame(columns=["aeco_price_cad_gj"])

        df[date_col] = pd.to_datetime(df[date_col])
        df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
        df = df.set_index(date_col).sort_index()
        return df[[price_col]].rename(columns={price_col: "aeco_price_cad_gj"})
    except Exception as e:
        print(f"Warning: AECO price fetch failed ({e}). Continuing without it.")
        return pd.DataFrame(columns=["aeco_price_cad_gj"])


if __name__ == "__main__":
    df = fetch_aeco_price(days=14)
    print(df.to_string() if not df.empty else "No data — AECO_API_KEY/AECO_API_URL not configured (expected if you don't have a subscription).")
