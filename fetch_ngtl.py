"""
NGTL Capability Fetcher — Alberta Gas Morning Brief
Pulls TC Energy's public NGTL System capability dashboard CSV.

Important scope note: TC Energy's actual Bulletin Board (OFOs, critical/
non-critical day notices, force majeure postings) lives behind a Customer
Express shipper login at my.tccustomerexpress.com and is NOT scraped here —
that page explicitly flags itself as requiring a User ID and password.

What this module pulls instead is the public, no-login capability CSV that
feeds the NGTL dashboard at tccustomerexpress.com/ngtl.html (authorized /
forecast capacity by area: EGAT, WGAT, Foothills SK/BC, OSDA, Greater USJR).
It's a genuine substitute signal (pipeline tightness), just not bulletins.

Honesty flag: the exact column names in that CSV weren't directly
inspectable ahead of a live run (the URL serves as application/octet-stream
and the sandbox used to build this couldn't render it as text). The parser
below is intentionally defensive — it auto-detects an area-like column and
any percent/utilization-like column rather than hardcoding names, and fails
soft (empty DataFrame + warning) rather than crashing the whole brief. First
live run should be spot-checked against the real CSV; column-name tweaks
here are a 5-minute fix once we see actual output.
"""

import requests
import pandas as pd
from io import StringIO

CSV_URL = "https://www.tccustomerexpress.com/alberta/dashboard/ngtldash.csv"


def fetch_capability() -> pd.DataFrame:
    """
    Returns the NGTL capability CSV as a DataFrame, columns as-served
    (whitespace-stripped). Non-fatal: empty DataFrame + warning on failure.
    """
    try:
        r = requests.get(CSV_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        print(f"Warning: NGTL capability fetch failed ({e}). Continuing without it.")
        return pd.DataFrame()


def latest_capability_summary(df: pd.DataFrame) -> dict | None:
    """
    Best-effort extraction of the most-utilized area for the narrative
    engine. Returns None (not an exception) if the schema doesn't match
    expectations — verify column names against a real fetch and adjust the
    detection heuristics below if needed.

    Shape assumption: one row per area (EGAT, WGAT, Foothills SK/BC, etc.)
    as shown on the NGTL dashboard table, NOT one row per date — so this
    scans every row for the single highest utilization figure rather than
    just taking the last row. If the real CSV turns out to be a time series
    instead (one row per date, columns per area), this needs reshaping —
    flag and fix once seen live.
    """
    if df is None or df.empty:
        return None
    try:
        pct_cols = [c for c in df.columns if any(k in c.lower() for k in ("%", "pct", "percent", "utiliz"))]
        area_col = next((c for c in df.columns if "area" in c.lower()), df.columns[0])
        if not pct_cols:
            return None
        best_area, best_col, best_val = None, None, -1.0
        for _, row in df.iterrows():
            for c in pct_cols:
                val = pd.to_numeric(row.get(c), errors="coerce")
                if pd.notna(val) and val > best_val:
                    best_area, best_col, best_val = row.get(area_col, "NGTL System"), c, val
        if best_col is None:
            return None
        return {
            "area": str(best_area),
            "metric": best_col,
            "value_pct": float(best_val),
        }
    except Exception:
        return None


if __name__ == "__main__":
    df = fetch_capability()
    if not df.empty:
        print(df.head(10).to_string())
        print("\nColumns:", list(df.columns))
        print("Summary:", latest_capability_summary(df))
    else:
        print("No data.")
