
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="ILR Dependant (Innovator) – Absence Calculator (UKVI Policy)", layout="wide")
st.title("ILR Dependant (Innovator) – Absence & Eligibility Calculator")
st.caption("Implements **UKVI policy** counting: only whole days outside the UK; departure & return days are **not** counted as absences.")

# ------------------------------
# Helpers
# ------------------------------
def parse_date(s, dayfirst=True):
    if s is None or (isinstance(s, float) and pd.isna(s)) or (isinstance(s, str) and s.strip() == ""):
        return None
    try:
        # allow DD/MM/YYYY or YYYY-MM-DD
        return pd.to_datetime(s, dayfirst=dayfirst, errors="raise").date()
    except Exception:
        try:
            return pd.to_datetime(s, format="%Y-%m-%d").date()
        except Exception:
            return None

def daterange_inclusive(a: date, b: date):
    for i in range((b - a).days + 1):
        yield a + timedelta(days=i)

def compute_dates(res_start: date):
    qualifying = res_start + relativedelta(years=5)
    earliest = qualifying - timedelta(days=28)
    return qualifying, earliest

def normalise_trip(out: date, back: date):
    if out is None or back is None:
        return None, None
    if back < out:
        out, back = back, out
    return out, back

def count_absences_ukvi(trips: list[tuple[date, date]], fivey_start: date, fivey_end: date):
    """
    UKVI policy counting:
      - Only full days outside the UK
      - Do not count the day of departure or the day of return
      - Intersect with 5-year window
    Returns a set of absent dates.
    """
    absent = set()
    for out, back in trips:
        out, back = normalise_trip(out, back)
        if out is None or back is None:
            continue
        # exclude dep/return
        start = out + timedelta(days=1)
        end   = back - timedelta(days=1)
        if end < fivey_start or start > fivey_end:
            continue
        start = max(start, fivey_start)
        end   = min(end,   fivey_end)
        if start <= end:
            for d in daterange_inclusive(start, end):
                absent.add(d)
    return absent

def rolling_12m_max(absent_days: list[date]):
    """
    Compute max count of absent days in any rolling 365-day window (inclusive).
    Return (max_count, window_start, window_end)
    """
    if not absent_days:
        return 0, None, None
    days = sorted(absent_days)
    j = 0
    best = 0
    best_end = None
    for i, d in enumerate(days):
        start_win = d - timedelta(days=364)
        while days[j] < start_win:
            j += 1
        count = i - j + 1
        if count > best:
            best = count
            best_end = d
    best_start = best_end - timedelta(days=364) if best_end else None
    return best, best_start, best_end

def build_fixed_blocks(absent_set: set[date], res_start: date, fivey_end: date, cap: int):
    rows = []
    i = 0
    year_start = res_start
    while year_start <= fivey_end:
        year_end = min(year_start + relativedelta(years=1) - timedelta(days=1), fivey_end)
        count = sum(1 for d in absent_set if year_start <= d <= year_end)
        rows.append({
            "Year #": i + 1,
            "Start": year_start,
            "End": year_end,
            "Whole days absent": count,
            "Status": "BREACH" if count > cap else "OK"
        })
        year_start = year_start + relativedelta(years=1)
        i += 1
    return pd.DataFrame(rows)

# ------------------------------
# Inputs
# ------------------------------
with st.expander("About & instructions", expanded=False):
    st.markdown("""
    **What you can do here:**
    - Enter your **residence start date** (first physical entry to the UK as a dependant).
    - Upload a **CSV** of trips abroad (columns: `exit_uk_date`, `reenter_uk_date`). Dates can be `YYYY-MM-DD` or `DD/MM/YYYY`.
    - (Optional) Add a few manual trips inline.
    - See rolling **12‑month absence** check (cap default **180**).
    - Export a **summary CSV**.

    **Counting policy (UKVI):** Only **whole days** outside the UK are counted as absences. The day you depart and the day you return **do not** count.
    """)

c1, c2 = st.columns([1,1])
with c1:
    res_start = st.date_input("Residence start date (first UK entry) – required", value=None, format="YYYY-MM-DD")
with c2:
    cap = st.number_input("Absence cap per any 12 months", min_value=0, max_value=365, value=180, step=1)

st.markdown("### Upload trips (CSV)")
uploaded = st.file_uploader("Upload CSV with columns: exit_uk_date, reenter_uk_date", type=["csv"], accept_multiple_files=False)

uploaded_df = None
if uploaded is not None:
    try:
        tmp = pd.read_csv(uploaded)
        # normalise column names
        cols = {c.lower().strip(): c for c in tmp.columns}
        # map expected names
        exit_col = cols.get("exit_uk_date") or cols.get("exit") or cols.get("exit_date")
        back_col = cols.get("reenter_uk_date") or cols.get("reentry") or cols.get("reenter") or cols.get("return_date")
        if not exit_col or not back_col:
            st.error("CSV must include columns named 'exit_uk_date' and 'reenter_uk_date' (or close variants).")
        else:
            df = pd.DataFrame({
                "exit_uk_date": tmp[exit_col].apply(parse_date),
                "reenter_uk_date": tmp[back_col].apply(parse_date),
            })
            uploaded_df = df.dropna(how="all")
            st.success(f"Loaded {len(uploaded_df)} trip rows from CSV.")
            st.dataframe(uploaded_df, use_container_width=True, height=240)
    except Exception as e:
        st.error(f"Couldn't read CSV: {e}")

st.markdown("### Add manual trips (optional)")
if "manual_trips" not in st.session_state:
    st.session_state.manual_trips = []  # list of dicts

with st.form("add_trip_form", clear_on_submit=True):
    cc1, cc2, cc3 = st.columns([1,1,0.6])
    with cc1:
        man_out = st.date_input("Exit UK", value=None, format="YYYY-MM-DD", key="man_out")
    with cc2:
        man_in = st.date_input("Re-enter UK", value=None, format="YYYY-MM-DD", key="man_in")
    with cc3:
        st.write(" ")
        sub = st.form_submit_button("➕ Add trip")
    if sub and man_out and man_in:
        st.session_state.manual_trips.append({"exit_uk_date": man_out, "reenter_uk_date": man_in})

if st.session_state.manual_trips:
    st.dataframe(pd.DataFrame(st.session_state.manual_trips), use_container_width=True, height=200)
    if st.button("🗑️ Clear manual trips"):
        st.session_state.manual_trips = []

# Combine data
trips_list = []
if uploaded_df is not None:
    trips_list.extend(uploaded_df.to_dict("records"))
if st.session_state.manual_trips:
    trips_list.extend(st.session_state.manual_trips)

# ------------------------------
# Compute
# ------------------------------
if res_start is None:
    st.info("Enter your **residence start date** to enable calculations.")
else:
    qualifying, earliest = compute_dates(res_start)
    st.markdown("### Key dates")
    k1, k2, k3 = st.columns(3)
    with k1: st.metric("Qualifying date (+5 years)", qualifying.strftime("%d %b %Y"))
    with k2: st.metric("Earliest apply date (-28 days)", earliest.strftime("%d %b %Y"))
    with k3: st.metric("Today", date.today().strftime("%d %b %Y"))

    # Build trips tuples
    parsed_trips = []
    for r in trips_list:
        out = r["exit_uk_date"]
        inn = r["reenter_uk_date"]
        if isinstance(out, str): out = parse_date(out)
        if isinstance(inn, str): inn = parse_date(inn)
        out, inn = normalise_trip(out, inn)
        if out and inn:
            parsed_trips.append((out, inn))

    # Remove anything fully before entry
    parsed_trips = [(o,i) for (o,i) in parsed_trips if i >= res_start]

    # Count whole-day absences
    absent = count_absences_ukvi(parsed_trips, res_start, qualifying)

    # Rolling 12m
    max_count, wstart, wend = rolling_12m_max(list(absent))

    # Fixed blocks (reference)
    fixed_df = build_fixed_blocks(absent, res_start, qualifying, cap)

    # Metrics
    m1, m2, m3 = st.columns(3)
    with m1: st.metric("Total whole days absent (5y)", len(absent))
    with m2: st.metric("Max absent in any rolling 12 months", f"{max_count} / {cap}")
    with m3: st.metric("Rolling status", "✅ Within limit" if max_count <= cap else "❌ BREACH")

    if max_count <= cap:
        st.success("Your rolling 12‑month absences are within the cap using **UKVI policy** counting.")
    else:
        st.error("Potential breach detected under UKVI policy counting. Consider delaying application or adjusting travel.")

    st.markdown("#### Fixed 12‑month blocks (anniversary to anniversary – reference only)")
    st.dataframe(fixed_df, use_container_width=True)

    # Export
    st.markdown("### Export summary")
    summary = pd.DataFrame([{
        "ResidenceStart": res_start.strftime("%Y-%m-%d"),
        "QualifyingDate(+5y)": qualifying.strftime("%Y-%m-%d"),
        "EarliestApplyDate(-28d)": earliest.strftime("%Y-%m-%d"),
        "CapPer12Months": cap,
        "TotalWholeAbsentDays(5y)": len(absent),
        "MaxAbsentInAnyRolling12m": max_count,
        "RollingStatus": "Within limit" if max_count <= cap else "BREACH",
        "PeakWindowStart": "" if wstart is None else wstart.strftime("%Y-%m-%d"),
        "PeakWindowEnd": "" if wend is None else wend.strftime("%Y-%m-%d"),
    }])
    st.download_button("Download summary CSV", data=summary.to_csv(index=False).encode("utf-8"),
                       file_name="ilr-dependant-innovator-absence-summary-UKVI.csv", mime="text/csv")

    # Notes
    st.markdown("""
    **Notes**  
    - UKVI counting applied: only **whole** days outside the UK are counted. Departure & return days **not** counted.  
    - Rolling window is computed as any **365-day** span.  
    - You must apply **from inside the UK** and should **not travel** after submission until decision.
    """)
