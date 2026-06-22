"""
EIA Data Fetcher — Alberta Gas Morning Brief
Pulls: Henry Hub spot price, US gas storage, LNG exports, rig count
All free via EIA Open Data API: https://www.eia.gov/opendata/
"""

import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
EIA_KEY = os.getenv("EIA_API_KEY")
BASE = "https://api.eia.gov/v2"


def _fetch(path: str, params: dict) -> list:
    """Base fetch with clear error messaging."""
    if not EIA_KEY or EIA_KEY == "your_key_here":
        raise EnvironmentError("EIA_API_KEY not set. Add it to your .env file.")
    params["api_key"] = EIA_KEY
    r = requests.get(f"{BASE}{path}", params=params, timeout=15)
    if r.status_code == 403:
        raise PermissionError(f"EIA API 403 — check your key or facets.\nURL: {r.url}")
    r.raise_for_status()
    data = r.json().get("response", {}).get("data", [])
    if not data:
        raise ValueError(f"No data returned from {path}. Facets may be wrong.")
    return data


def fetch_henry_hub(days: int = 60) -> pd.DataFrame:
    """
    Henry Hub Natural Gas Spot Price ($/MMBtu), daily.
    EIA v2 route: /natural-gas/pri/sum/data/
    Series: RNGWHHD | duoarea: NUS | product: EPG0
    """
    raw = _fetch("/natural-gas/pri/sum/data/", {
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": "RNGWHHD",
        "facets[duoarea][]": "NUS",
        "facets[product][]": "EPG0",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": days,
    })
    df = pd.DataFrame(raw)
    df["period"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.set_index("period").sort_index()
    return df[["value"]].rename(columns={"value": "henry_hub_usd_mmbtu"})


def fetch_storage(weeks: int = 260) -> pd.DataFrame:
    """
    US Working Gas in Underground Storage (Bcf), weekly.
    260 weeks = 5 years, needed to compute 5-year average in-house.
    EIA v2 route: /natural-gas/stor/wkly/data/
    Series: NW2_EPG0_SWO_R48_BCF | duoarea: R48
    """
    raw = _fetch("/natural-gas/stor/wkly/data/", {
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": "NW2_EPG0_SWO_R48_BCF",
        "facets[duoarea][]": "R48",
        "facets[process][]": "SWO",
        "facets[product][]": "EPG0",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": weeks,
    })
    df = pd.DataFrame(raw)
    df["period"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.set_index("period").sort_index()
    df = df.rename(columns={"value": "storage_bcf"})

    # Compute 5-year same-week average
    df["week"] = df.index.isocalendar().week.astype(int)
    df["year"] = df.index.year
    max_year = df["year"].max()
    five_yr = (
        df[df["year"].between(max_year - 5, max_year - 1)]
        .groupby("week")["storage_bcf"]
        .mean()
        .rename("avg_5yr_bcf")
    )
    df = df.join(five_yr, on="week")
    df["surplus_deficit_bcf"] = (df["storage_bcf"] - df["avg_5yr_bcf"]).round(1)
    df["surplus_deficit_pct"] = (
        df["surplus_deficit_bcf"] / df["avg_5yr_bcf"] * 100
    ).round(1)
    return df[["storage_bcf", "avg_5yr_bcf", "surplus_deficit_bcf", "surplus_deficit_pct"]]


def fetch_lng_exports(weeks: int = 12) -> pd.DataFrame:
    """
    US LNG exports (Bcf/month, converted to context).
    EIA v2 route: /natural-gas/move/lngc/data/
    Non-fatal if unavailable — endpoint structure varies.
    """
    try:
        raw = _fetch("/natural-gas/move/lngc/data/", {
            "frequency": "monthly",
            "data[0]": "value",
            "facets[series][]": "N9133US2",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": weeks,
        })
        df = pd.DataFrame(raw)
        df["period"] = pd.to_datetime(df["period"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.set_index("period").sort_index()
        return df[["value"]].rename(columns={"value": "lng_exports_bcf"})
    except Exception as e:
        print(f"Warning: LNG export fetch failed ({e}). Continuing without it.")
        return pd.DataFrame(columns=["lng_exports_bcf"])


def fetch_rig_count(weeks: int = 12) -> pd.DataFrame:
    """
    US Natural Gas Rotary Rig Count (Baker Hughes via EIA), weekly.
    EIA v2 route: /petroleum/crd/drill/data/
    """
    try:
        raw = _fetch("/petroleum/crd/drill/data/", {
            "frequency": "weekly",
            "data[0]": "value",
            "facets[series][]": "N166085_2",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": weeks,
        })
        df = pd.DataFrame(raw)
        df["period"] = pd.to_datetime(df["period"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.set_index("period").sort_index()
        return df[["value"]].rename(columns={"value": "gas_rigs"})
    except Exception as e:
        print(f"Warning: Rig count fetch failed ({e}). Continuing without it.")
        return pd.DataFrame(columns=["gas_rigs"])


def fetch_all() -> dict:
    """
    Master fetch — returns all datasets as a dict.
    Call this from the narrative engine.
    """
    print("Fetching EIA data...")
    return {
        "henry_hub": fetch_henry_hub(days=60),
        "storage": fetch_storage(weeks=260),
        "lng": fetch_lng_exports(weeks=6),
        "rigs": fetch_rig_count(weeks=8),
    }


if __name__ == "__main__":
    data = fetch_all()

    print("\n--- Henry Hub (last 5 trading days) ---")
    print(data["henry_hub"].tail(5).to_string())

    print("\n--- Storage vs 5yr avg (last 4 weeks) ---")
    cols = ["storage_bcf", "avg_5yr_bcf", "surplus_deficit_bcf", "surplus_deficit_pct"]
    print(data["storage"].tail(4)[cols].to_string())

    print("\n--- LNG Exports (last 4 periods) ---")
    print(data["lng"].tail(4).to_string() if not data["lng"].empty else "Unavailable")

    print("\n--- Gas Rig Count (last 4 weeks) ---")
    print(data["rigs"].tail(4).to_string() if not data["rigs"].empty else "Unavailable")
