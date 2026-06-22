# Alberta Gas Morning Brief

A daily automated market brief for Alberta natural gas. Pulls public data,
runs it through a rule-based (no AI/LLM) narrative engine, and renders a
dark-themed HTML brief. Runs locally or on a 6am Mountain Time GitHub
Actions schedule.

## What it actually covers

| Data | Source | Cost | Freshness |
|---|---|---|---|
| Henry Hub spot price | EIA | Free | ~1 week lag (EIA's own publishing cadence) |
| US gas storage | EIA | Free | ~1 week lag (matches EIA's weekly report) |
| US LNG exports | EIA | Free | ~3-4 months lag (EIA only publishes monthly) |
| US gas-directed rig count | EIA | Free | ~3-4 months lag (EIA only has monthly, not weekly Baker Hughes) |
| AESO Alberta pool price | AESO API | Free | Same-day |
| NGTL capability/utilization | TC Energy (public CSV) | Free | Daily |
| AECO-C (real Alberta gas benchmark) | NGI or ICE NGX | **Paid subscription** | Same-day, if configured |

**Important nuance:** Henry Hub is a US benchmark. AESO is Alberta *power*,
not gas. NGTL's public data is pipeline capacity, not the actual bulletin
board (OFOs/critical-day notices — that's behind a TC Energy Customer
Express shipper login). The one number that's genuinely "Alberta gas
price" — AECO — is not available for free anywhere legitimate; the
Alberta Energy Regulator only publishes an annual average. AECO support
here is an optional plug-in for people who already pay for NGI or ICE NGX
data (see below).

## Setup

```bash
pip install -r requirements.txt
```

Copy `env.txt` to `.env` and fill in your keys:

```
EIA_API_KEY=...        # free, https://www.eia.gov/opendata/
AESO_API_KEY=...       # free, https://developer-apim.aeso.ca/ (Pool Price Report product)
AECO_API_KEY=          # optional, paid — see "Adding AECO" below
AECO_API_URL=          # optional, paid
```

## Running

```bash
python run.py --mock     # synthetic data, no keys needed — good for testing layout/logic
python run.py             # live pull, writes output/brief.html
```

## Project layout

- `run.py` — entry point; orchestrates fetching + narrative + HTML render
- `fetch_eia.py` — Henry Hub, storage, LNG, rig count (all free, EIA)
- `fetch_aeso.py` — Alberta power pool price (free, AESO)
- `fetch_ngtl.py` — NGTL pipeline capability (free, public CSV)
- `fetch_aeco.py` — AECO benchmark (**optional, requires a paid NGI/ICE NGX subscription**)
- `narrative.py` — rule-based signal classification + sentiment scoring + brief text
- `template.html` — Jinja2 template for the rendered brief
- `.github/workflows/daily-brief.yml` — GitHub Actions automation, 6am MT daily

## GitHub Actions automation

The workflow runs at 6am Mountain Time year-round (it fires at both 12:00
and 13:00 UTC and self-skips whichever one doesn't land on 6am MT that day,
so it survives the MST/MDT switch automatically). Add these as repo
secrets (Settings → Secrets and variables → Actions):

- `EIA_API_KEY` (required for a live run)
- `AESO_API_KEY` (required for AESO data)
- `AECO_API_KEY`, `AECO_API_URL` (optional — only if you have a subscription)

It commits the generated `output/brief.html` back to the repo after each run.

## Adding AECO (if you have a paid subscription)

`fetch_aeco.py` is a **skeleton, not a verified integration** — I don't
have access to NGI's or ICE NGX's paywalled API docs, so the request
shape in there is an educated guess. To actually use it:

1. Open `fetch_aeco.py`, find the two `# --- ADJUST ---` comments.
2. Edit the request URL, headers, and response field parsing to match
   what your subscription's actual API documentation says.
3. Add `AECO_API_KEY` and `AECO_API_URL` to `.env` (and as GitHub secrets
   if you want it in the automated run too).

If you skip step 1 and just add a key, it'll fail gracefully — a warning
printed, the rest of the brief generates fine — but it won't actually pull
AECO data until the code matches your provider's real format.

If you don't have a subscription, leave those two variables blank. Nothing
else changes; the brief works exactly the same without AECO.

## Known limitations (by design, not bugs)

- Henry Hub date shown in the brief reflects EIA's most recently published
  data, not necessarily today — usually about a week behind.
- LNG export and rig count "month-over-month" comparisons are working off
  EIA's monthly data, which itself runs several months behind the calendar.
- The rule-based narrative's threshold constants (storage %, price move
  size, etc., all near the top of `narrative.py`) are reasonable starting
  points, not backtested against historical price reactions. Treat the
  bullish/bearish call as directional color, not a validated trading signal.
- AESO and NGTL signals are useful regional context but are proxies, not
  the actual Alberta gas price — see the cost/freshness table above.

## License / disclaimer

For informational and educational purposes only. Not investment advice.
All data subject to revision by the originating source agencies.
