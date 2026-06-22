"""
Narrative Engine — Alberta Gas Morning Brief
Rule-based system that connects market signals to plain-English explanations.
No AI/LLM — deterministic, auditable, credible.

Logic structure:
  1. Classify each signal (bullish / bearish / neutral)
  2. Combine signals → overall market sentiment
  3. Generate causal paragraph explaining the move
"""

import pandas as pd
from dataclasses import dataclass
from typing import Optional

from fetch_ngtl import latest_capability_summary


# ── Signal thresholds (tunable) ─────────────────────────────────────────────

STORAGE_BEARISH_PCT   = 5.0    # storage >5% above 5yr avg → bearish
STORAGE_BULLISH_PCT   = -5.0   # storage >5% below 5yr avg → bullish
PRICE_MOVE_NOTABLE    = 0.05   # $/MMBtu — moves smaller than this called "flat"
PRICE_MOVE_LARGE      = 0.20   # $/MMBtu — moves larger than this called "sharp"
RIG_CHANGE_NOTABLE    = 5      # rig count change to mention
LNG_CHANGE_NOTABLE    = 1.0    # Bcf change in LNG exports worth mentioning
AESO_PRICE_CHANGE_NOTABLE_PCT = 25.0   # day-over-day % move in AB pool price worth flagging
NGTL_UTIL_TIGHT_PCT   = 95.0   # NGTL area utilization considered "constrained"
AECO_CHANGE_NOTABLE_PCT = 8.0   # day-over-day % move in AECO worth flagging (real gas benchmark, lower bar than AESO power)


@dataclass
class Signal:
    name: str
    direction: str          # "bullish", "bearish", "neutral"
    magnitude: str          # "strong", "moderate", "weak"
    sentence: str           # plain-English one-liner for this signal


@dataclass
class MarketSnapshot:
    date: str
    price_today: float
    price_yesterday: float
    price_change: float
    price_change_pct: float
    price_30d_avg: float
    storage_bcf: float
    storage_avg_bcf: float
    storage_surplus_bcf: float
    storage_surplus_pct: float
    lng_exports_bcf: Optional[float]
    lng_prev_bcf: Optional[float]
    gas_rigs: Optional[int]
    gas_rigs_prev: Optional[int]
    aeso_price_today: Optional[float]
    aeso_price_prev: Optional[float]
    ngtl_area: Optional[str]
    ngtl_util_pct: Optional[float]
    aeco_price_today: Optional[float]
    aeco_price_prev: Optional[float]


def build_snapshot(data: dict) -> MarketSnapshot:
    """Pull the most recent values out of the raw DataFrames."""
    hh = data["henry_hub"].dropna()
    stor = data["storage"].dropna()
    lng = data["lng"]
    rigs = data["rigs"]

    # Henry Hub
    price_today     = float(hh["henry_hub_usd_mmbtu"].iloc[-1])
    price_yesterday = float(hh["henry_hub_usd_mmbtu"].iloc[-2]) if len(hh) > 1 else price_today
    price_30d_avg   = float(hh["henry_hub_usd_mmbtu"].tail(22).mean())  # ~22 trading days
    price_change    = round(price_today - price_yesterday, 3)
    price_change_pct = round((price_change / price_yesterday) * 100, 1) if price_yesterday else 0.0

    # Storage
    latest_stor = stor.iloc[-1]
    storage_bcf         = float(latest_stor["storage_bcf"])
    storage_avg_bcf     = float(latest_stor["avg_5yr_bcf"])
    storage_surplus_bcf = float(latest_stor["surplus_deficit_bcf"])
    storage_surplus_pct = float(latest_stor["surplus_deficit_pct"])

    # LNG (optional)
    lng_exports_bcf = float(lng["lng_exports_bcf"].iloc[-1]) if not lng.empty else None
    lng_prev_bcf    = float(lng["lng_exports_bcf"].iloc[-2]) if (not lng.empty and len(lng) > 1) else None

    # Rigs (optional)
    gas_rigs      = int(rigs["gas_rigs"].iloc[-1]) if not rigs.empty else None
    gas_rigs_prev = int(rigs["gas_rigs"].iloc[-2]) if (not rigs.empty and len(rigs) > 1) else None

    # AESO Alberta power price (optional)
    aeso = data.get("aeso", pd.DataFrame()).dropna() if "aeso" in data else pd.DataFrame()
    aeso_price_today = float(aeso["aeso_price_cad_mwh"].iloc[-1]) if not aeso.empty else None
    aeso_price_prev  = float(aeso["aeso_price_cad_mwh"].iloc[-2]) if (not aeso.empty and len(aeso) > 1) else None

    # NGTL capability (optional)
    ngtl_df = data.get("ngtl", pd.DataFrame())
    ngtl_summary = latest_capability_summary(ngtl_df) if ngtl_df is not None and not ngtl_df.empty else None
    ngtl_area     = ngtl_summary["area"] if ngtl_summary else None
    ngtl_util_pct = ngtl_summary["value_pct"] if ngtl_summary else None

    # AECO (optional, paid-subscription plug-in — see fetch_aeco.py)
    aeco = data.get("aeco", pd.DataFrame()).dropna() if "aeco" in data else pd.DataFrame()
    aeco_price_today = float(aeco["aeco_price_cad_gj"].iloc[-1]) if not aeco.empty else None
    aeco_price_prev  = float(aeco["aeco_price_cad_gj"].iloc[-2]) if (not aeco.empty and len(aeco) > 1) else None

    return MarketSnapshot(
        date             = hh.index[-1].strftime("%A, %B %d, %Y"),
        price_today      = price_today,
        price_yesterday  = price_yesterday,
        price_change     = price_change,
        price_change_pct = price_change_pct,
        price_30d_avg    = price_30d_avg,
        storage_bcf      = storage_bcf,
        storage_avg_bcf  = storage_avg_bcf,
        storage_surplus_bcf = storage_surplus_bcf,
        storage_surplus_pct = storage_surplus_pct,
        lng_exports_bcf  = lng_exports_bcf,
        lng_prev_bcf     = lng_prev_bcf,
        gas_rigs         = gas_rigs,
        gas_rigs_prev    = gas_rigs_prev,
        aeso_price_today = aeso_price_today,
        aeso_price_prev  = aeso_price_prev,
        ngtl_area        = ngtl_area,
        ngtl_util_pct    = ngtl_util_pct,
        aeco_price_today = aeco_price_today,
        aeco_price_prev  = aeco_price_prev,
    )


def _classify_storage(s: MarketSnapshot) -> Signal:
    pct = s.storage_surplus_pct
    surplus = s.storage_surplus_bcf
    bcf_str = f"{abs(surplus):.0f} Bcf"
    pct_str = f"{abs(pct):.1f}%"

    if pct >= STORAGE_BEARISH_PCT:
        mag = "strong" if pct >= 10 else "moderate"
        return Signal(
            name="storage", direction="bearish", magnitude=mag,
            sentence=(
                f"US storage sits at {s.storage_bcf:.0f} Bcf — {bcf_str} ({pct_str}) "
                f"above the 5-year average, signalling ample supply."
            )
        )
    elif pct <= STORAGE_BULLISH_PCT:
        mag = "strong" if pct <= -10 else "moderate"
        return Signal(
            name="storage", direction="bullish", magnitude=mag,
            sentence=(
                f"US storage is at {s.storage_bcf:.0f} Bcf — {bcf_str} ({pct_str}) "
                f"below the 5-year average, a supply-supportive signal."
            )
        )
    else:
        return Signal(
            name="storage", direction="neutral", magnitude="weak",
            sentence=(
                f"US storage at {s.storage_bcf:.0f} Bcf is near the 5-year average "
                f"({s.storage_avg_bcf:.0f} Bcf), providing little directional signal."
            )
        )


def _classify_price_trend(s: MarketSnapshot) -> Signal:
    diff_from_avg = s.price_today - s.price_30d_avg
    if diff_from_avg > 0.10:
        return Signal(
            name="trend", direction="bullish", magnitude="moderate",
            sentence=(
                f"At ${s.price_today:.2f}/MMBtu, the prompt price is "
                f"${diff_from_avg:.2f} above its 30-day average of ${s.price_30d_avg:.2f}, "
                f"reflecting a broader upward trend."
            )
        )
    elif diff_from_avg < -0.10:
        return Signal(
            name="trend", direction="bearish", magnitude="moderate",
            sentence=(
                f"At ${s.price_today:.2f}/MMBtu, the prompt price is "
                f"${abs(diff_from_avg):.2f} below its 30-day average of ${s.price_30d_avg:.2f}, "
                f"reflecting a broader downward trend."
            )
        )
    else:
        return Signal(
            name="trend", direction="neutral", magnitude="weak",
            sentence=(
                f"The prompt price of ${s.price_today:.2f}/MMBtu is near its "
                f"30-day average of ${s.price_30d_avg:.2f}, suggesting range-bound conditions."
            )
        )


def _classify_lng(s: MarketSnapshot) -> Optional[Signal]:
    if s.lng_exports_bcf is None or s.lng_prev_bcf is None:
        return None
    change = s.lng_exports_bcf - s.lng_prev_bcf
    if abs(change) < LNG_CHANGE_NOTABLE:
        return None
    direction = "bullish" if change > 0 else "bearish"
    verb = "rose" if change > 0 else "fell"
    return Signal(
        name="lng", direction=direction, magnitude="moderate",
        sentence=(
            f"US LNG export volumes {verb} by {abs(change):.1f} Bcf month-over-month "
            f"to {s.lng_exports_bcf:.1f} Bcf, "
            f"{'drawing more gas away from domestic supply' if change > 0 else 'freeing more gas for domestic markets'}."
        )
    )


def _classify_rigs(s: MarketSnapshot) -> Optional[Signal]:
    """
    NOTE: EIA's open API only exposes gas rig count monthly (no weekly Baker
    Hughes feed is available through it), and it runs a few months behind
    the calendar date — see fetch_eia.py's fetch_rig_count() for detail.
    So this is a month-over-month comparison, not week-over-week.
    """
    if s.gas_rigs is None or s.gas_rigs_prev is None:
        return None
    change = s.gas_rigs - s.gas_rigs_prev
    if abs(change) < RIG_CHANGE_NOTABLE:
        return None
    direction = "bearish" if change > 0 else "bullish"  # more rigs = more future supply = bearish
    verb = "increased" if change > 0 else "declined"
    implication = "pointing to rising future supply" if change > 0 else "suggesting producers are pulling back"
    return Signal(
        name="rigs", direction=direction, magnitude="weak",
        sentence=(
            f"The US gas-directed rig count {verb} by {abs(change)} rigs month-over-month "
            f"to {s.gas_rigs} rigs, {implication}."
        )
    )


def _classify_power_price(s: MarketSnapshot) -> Optional[Signal]:
    """
    AESO Alberta pool price is context for in-province gas-fired generation
    demand, not a direct Henry Hub driver — kept weak-weighted so it colors
    the brief without dominating the overall HH-centric sentiment score.
    """
    if s.aeso_price_today is None or s.aeso_price_prev is None or s.aeso_price_prev == 0:
        return None
    change_pct = (s.aeso_price_today - s.aeso_price_prev) / s.aeso_price_prev * 100
    if abs(change_pct) < AESO_PRICE_CHANGE_NOTABLE_PCT:
        return None
    direction = "bullish" if change_pct > 0 else "bearish"
    verb = "spiked" if change_pct > 0 else "dropped"
    implication = (
        "pointing to stronger gas-fired generation demand within Alberta"
        if change_pct > 0
        else "easing in-province gas-fired generation demand"
    )
    return Signal(
        name="power", direction=direction, magnitude="weak",
        sentence=(
            f"Alberta's AESO pool price {verb} {abs(change_pct):.0f}% day-over-day "
            f"to ${s.aeso_price_today:.2f}/MWh, {implication}."
        )
    )


def _classify_ngtl(s: MarketSnapshot) -> Optional[Signal]:
    """
    NGTL pipeline capability/utilization as a proxy for Alberta gas takeaway
    tightness. Informational/weak-weighted — see fetch_ngtl.py for the scope
    note on why this is capability data rather than bulletin notices.
    """
    if s.ngtl_util_pct is None or s.ngtl_area is None:
        return None
    if s.ngtl_util_pct >= NGTL_UTIL_TIGHT_PCT:
        return Signal(
            name="pipeline", direction="bullish", magnitude="weak",
            sentence=(
                f"NGTL's {s.ngtl_area} segment is running at {s.ngtl_util_pct:.0f}% of authorized "
                f"capability — near-full utilization that can pressure Alberta basis pricing "
                f"and tighten takeaway."
            )
        )
    return None


def _classify_aeco(s: MarketSnapshot) -> Optional[Signal]:
    """
    AECO-C/NIT is the actual Alberta gas benchmark (paid-subscription
    plug-in — see fetch_aeco.py). Unlike the AESO power-price signal,
    this IS the real regional gas price, so it's weighted "moderate" —
    same tier as the LNG signal — rather than "weak".
    """
    if s.aeco_price_today is None or s.aeco_price_prev is None or s.aeco_price_prev == 0:
        return None
    change_pct = (s.aeco_price_today - s.aeco_price_prev) / s.aeco_price_prev * 100
    if abs(change_pct) < AECO_CHANGE_NOTABLE_PCT:
        return None
    direction = "bullish" if change_pct > 0 else "bearish"
    verb = "rose" if change_pct > 0 else "fell"
    return Signal(
        name="aeco", direction=direction, magnitude="moderate",
        sentence=(
            f"AECO-C {verb} {abs(change_pct):.1f}% day-over-day to ${s.aeco_price_today:.2f}/GJ, "
            f"{'reflecting tighter Alberta basis' if change_pct > 0 else 'reflecting continued Alberta basis weakness'}."
        )
    )


def _overall_sentiment(signals: list[Signal]) -> str:
    """Score signals and return overall market tone."""
    score = 0
    weights = {"strong": 2, "moderate": 1, "weak": 0.5}
    for sig in signals:
        w = weights.get(sig.magnitude, 1)
        if sig.direction == "bullish":
            score += w
        elif sig.direction == "bearish":
            score -= w

    if score >= 2:
        return "bullish"
    elif score <= -2:
        return "bearish"
    elif score > 0:
        return "mildly bullish"
    elif score < 0:
        return "mildly bearish"
    else:
        return "mixed"


def _price_move_sentence(s: MarketSnapshot) -> str:
    """Lead sentence describing today's price move."""
    chg = s.price_change
    pct = s.price_change_pct
    direction = "rose" if chg > 0 else ("fell" if chg < 0 else "was unchanged")
    magnitude = ""
    if abs(chg) >= PRICE_MOVE_LARGE:
        magnitude = "sharply "
    elif abs(chg) < PRICE_MOVE_NOTABLE:
        return (
            f"Henry Hub was essentially flat at ${s.price_today:.2f}/MMBtu on {s.date}, "
            f"a move of just {chg:+.3f}/MMBtu ({pct:+.1f}%) from the prior session."
        )

    return (
        f"Henry Hub {magnitude}{direction} {abs(chg):.2f}/MMBtu ({pct:+.1f}%) "
        f"to ${s.price_today:.2f}/MMBtu on {s.date}."
    )


def _watch_item(s: MarketSnapshot, signals: list[Signal]) -> str:
    """Single most important thing to watch today."""
    today = pd.Timestamp.today()
    dow = today.weekday()  # 0=Mon, 3=Thu, 4=Fri

    if dow == 3:
        return (
            "📅 EIA Natural Gas Storage Report drops this morning at 10:30am ET "
            "(8:30am MT). Expect price volatility at release. "
            f"Market consensus is roughly {s.storage_avg_bcf:.0f} Bcf — "
            "a significant miss either way will move prompt prices."
        )
    else:
        dominant = max(signals, key=lambda x: {"strong": 3, "moderate": 2, "weak": 1}.get(x.magnitude, 1))
        if dominant.direction == "bearish":
            return (
                "👀 Storage surplus remains the dominant bearish overhang. "
                "Watch for any demand surprise (cold snap, LNG outage) that could offset."
            )
        elif dominant.direction == "bullish":
            return (
                "👀 Supply tightness is the key bullish driver. "
                "Watch this Thursday's EIA storage report for confirmation."
            )
        else:
            return (
                "👀 Market signals are mixed. "
                "Thursday's EIA storage report will be the next major directional catalyst."
            )


def generate_narrative(data: dict) -> dict:
    """
    Master function. Takes raw DataFrames, returns a structured brief dict
    ready for the HTML template.
    """
    s = build_snapshot(data)

    # Build signals
    signals = [sig for sig in [
        _classify_storage(s),
        _classify_price_trend(s),
        _classify_lng(s),
        _classify_rigs(s),
        _classify_power_price(s),
        _classify_ngtl(s),
        _classify_aeco(s),
    ] if sig is not None]

    sentiment = _overall_sentiment(signals)
    sentiment_emoji = {
        "bullish": "🟢", "mildly bullish": "🟡",
        "bearish": "🔴", "mildly bearish": "🟡", "mixed": "⚪"
    }.get(sentiment, "⚪")

    # Causal paragraph: price move + signal sentences + conclusion
    signal_sentences = " ".join(sig.sentence for sig in signals)
    bearish_count = sum(1 for sig in signals if sig.direction == "bearish")
    bullish_count = sum(1 for sig in signals if sig.direction == "bullish")

    if bearish_count > bullish_count:
        conclusion = "Taken together, the weight of evidence points to continued bearish pressure on the near-term curve."
    elif bullish_count > bearish_count:
        conclusion = "On balance, supply fundamentals appear supportive of further price gains near-term."
    else:
        conclusion = "Signals are pulling in opposite directions — the market is in a wait-and-see mode ahead of the next major data release."

    causal_paragraph = f"{_price_move_sentence(s)} {signal_sentences} {conclusion}"

    return {
        "date": s.date,
        "price_today": s.price_today,
        "price_change": s.price_change,
        "price_change_pct": s.price_change_pct,
        "price_30d_avg": s.price_30d_avg,
        "storage_bcf": s.storage_bcf,
        "storage_avg_bcf": s.storage_avg_bcf,
        "storage_surplus_bcf": s.storage_surplus_bcf,
        "storage_surplus_pct": s.storage_surplus_pct,
        "lng_exports_bcf": s.lng_exports_bcf,
        "gas_rigs": s.gas_rigs,
        "aeso_price_today": s.aeso_price_today,
        "ngtl_area": s.ngtl_area,
        "ngtl_util_pct": s.ngtl_util_pct,
        "aeco_price_today": s.aeco_price_today,
        "sentiment": sentiment,
        "sentiment_emoji": sentiment_emoji,
        "signals": signals,
        "causal_paragraph": causal_paragraph,
        "watch_item": _watch_item(s, signals),
    }


if __name__ == "__main__":
    # Test with synthetic data to validate logic without needing live API
    import numpy as np

    dates = pd.date_range(end=pd.Timestamp.today(), periods=60, freq="B")
    hh_prices = 2.50 + np.cumsum(np.random.normal(0, 0.05, 60))

    stor_dates = pd.date_range(end=pd.Timestamp.today(), periods=260, freq="W")
    stor_values = 2800 + np.random.normal(0, 50, 260)

    mock_data = {
        "henry_hub": pd.DataFrame(
            {"henry_hub_usd_mmbtu": hh_prices}, index=dates
        ),
        "storage": pd.DataFrame(
            {
                "storage_bcf": stor_values,
                "avg_5yr_bcf": stor_values - 150,  # simulate 150 Bcf surplus
                "surplus_deficit_bcf": [150.0] * 260,
                "surplus_deficit_pct": [5.8] * 260,
            },
            index=stor_dates
        ),
        "lng": pd.DataFrame(columns=["lng_exports_bcf"]),
        "rigs": pd.DataFrame(columns=["gas_rigs"]),
    }

    result = generate_narrative(mock_data)
    print(f"\nDate: {result['date']}")
    print(f"Sentiment: {result['sentiment_emoji']} {result['sentiment']}")
    print(f"\nNarrative:\n{result['causal_paragraph']}")
    print(f"\nWatch today:\n{result['watch_item']}")
