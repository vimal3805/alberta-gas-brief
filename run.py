"""
Alberta Gas Morning Brief — Main Runner
Run this daily (or via GitHub Actions cron) to generate the brief.

Usage:
    python run.py                    # generate today's brief
    python run.py --mock             # test with synthetic data (no API key needed)
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
from datetime import datetime
from jinja2 import Template
from pathlib import Path

# Windows consoles default to cp1252, which can't print the emoji used in
# console output (sentiment markers, watch-item icons). Force UTF-8 so this
# runs the same on Windows, macOS/Linux, and GitHub Actions.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fetch_eia import fetch_all
from fetch_aeso import fetch_pool_price
from fetch_ngtl import fetch_capability
from narrative import generate_narrative


def mock_data() -> dict:
    """Synthetic data for testing layout and logic without API access."""
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.today(), periods=60, freq="B")
    hh_prices = 2.80 + np.cumsum(np.random.normal(0, 0.04, 60))

    stor_dates = pd.date_range(end=pd.Timestamp.today(), periods=260, freq="W")
    stor_values = 2500 + np.random.normal(0, 30, 260)

    lng_dates = pd.date_range(end=pd.Timestamp.today(), periods=6, freq="ME")

    rig_dates = pd.date_range(end=pd.Timestamp.today(), periods=8, freq="W")
    aeso_dates = pd.date_range(end=pd.Timestamp.today(), periods=14, freq="D")
    aeso_prices = 45 + np.cumsum(np.random.normal(0, 4, 14))

    return {
        "henry_hub": pd.DataFrame(
            {"henry_hub_usd_mmbtu": hh_prices}, index=dates
        ),
        "storage": pd.DataFrame(
            {
                "storage_bcf": stor_values,
                "avg_5yr_bcf": stor_values - 180,
                "surplus_deficit_bcf": [180.0] * 260,
                "surplus_deficit_pct": [7.7] * 260,
            },
            index=stor_dates,
        ),
        "lng": pd.DataFrame(
            {"lng_exports_bcf": [105, 108, 112, 109, 115, 118]},
            index=lng_dates,
        ),
        "rigs": pd.DataFrame(
            {"gas_rigs": [118, 119, 121, 124, 122, 125, 127, 124]},
            index=rig_dates,
        ),
        "aeso": pd.DataFrame(
            {"aeso_price_cad_mwh": aeso_prices}, index=aeso_dates
        ),
        "ngtl": pd.DataFrame(
            {
                "Area": ["EGAT", "WGAT", "Foothills SK", "Foothills BC"],
                "Capability Authorized %": [88.0, 92.0, 97.0, 81.0],
            }
        ),
    }


def render_html(brief: dict) -> str:
    template_path = Path(__file__).parent / "template.html"
    template_str = template_path.read_text(encoding="utf-8")
    tmpl = Template(template_str)

    # Derive display helpers
    price_class   = "up" if brief["price_change"] > 0 else ("down" if brief["price_change"] < 0 else "neutral")
    storage_class = "down" if brief["storage_surplus_pct"] > 5 else ("up" if brief["storage_surplus_pct"] < -5 else "neutral")
    sentiment_color_map = {
        "bullish": "#22c55e",
        "mildly bullish": "#84cc16",
        "bearish": "#ef4444",
        "mildly bearish": "#f97316",
        "mixed": "#6b7280",
    }

    return tmpl.render(
        **brief,
        price_class=price_class,
        storage_class=storage_class,
        sentiment_color=sentiment_color_map.get(brief["sentiment"], "#6b7280"),
        generated_at=datetime.now().strftime("%H:%M MT"),
    )


def main():
    parser = argparse.ArgumentParser(description="Alberta Gas Morning Brief generator")
    parser.add_argument("--mock", action="store_true", help="Use synthetic data (no API key needed)")
    parser.add_argument("--out", default="output/brief.html", help="Output path for HTML file")
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print("  Alberta Gas Morning Brief")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M MT')}")
    print(f"{'='*50}\n")

    # Fetch data
    if args.mock:
        print("Running in MOCK mode — using synthetic data.\n")
        data = mock_data()
    else:
        data = fetch_all()
        data["aeso"] = fetch_pool_price(days=14)
        data["ngtl"] = fetch_capability()

    # Generate narrative
    print("Generating narrative...\n")
    brief = generate_narrative(data)

    # Print console summary
    print(f"Date:      {brief['date']}")
    print(f"Sentiment: {brief['sentiment_emoji']} {brief['sentiment']}")
    print(f"HH Price:  ${brief['price_today']:.2f} ({brief['price_change']:+.3f})")
    print(f"Storage:   {brief['storage_bcf']:.0f} Bcf ({brief['storage_surplus_pct']:+.1f}% vs 5yr avg)")
    print(f"\n--- WHY PRICES MOVED ---")
    print(brief["causal_paragraph"])
    print(f"\n--- WATCH TODAY ---")
    print(brief["watch_item"])

    # Render HTML
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(brief)
    out_path.write_text(html, encoding="utf-8")
    print(f"\n✅ Brief saved to: {out_path.resolve()}")
    print("   Open this file in your browser to see the full formatted brief.\n")


if __name__ == "__main__":
    main()
