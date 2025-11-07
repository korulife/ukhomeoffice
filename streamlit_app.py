
import streamlit as st
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import pandas as pd

# ------------------------------
# Helpers
# ------------------------------
def parse_ymd(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def to_day_serial(d: date) -> int:
    return (d - date(1970,1,1)).days

def from_day_serial(n: int) -> date:
    return date(1970,1,1) + timedelta(days=int(n))

def daterange_inclusive(start: date, end: date):
    n = (end - start).days
    for i in range(n + 1):
        yield start + timedelta(days=i)

def compute_dates(start_date: date):
    qualifying = start_date + relativedelta(years=5)
    earliest = qualifying - timedelta(days=28)
    return qualifying, earliest

def compute_absence(trips, start: date, end: date, cap: int = 180):
    # Build a set of absent days intersecting [start, end]
    absent = set()
    for out, back in trips:
        if out is None or back is None:
            continue
        # normalise
        a = min(out, back)
        b = max(out, back)
        # intersect with five-year window
        if b < start or a > end:
            continue
        a = max(a, start)
        b = min(b, end)
        for d in daterange_inclusive(a, b):
            absent.add(to_day_serial(d))

    absent_sorted = sorted(absent)
    max_in_any_window = 0
    # two-pointer sliding window over day-serials for 365-day window
    j = 0
    for i in range(len(absent_sorted)):
        start_window = absent_sorted[i] - 364  # previous 12 months inclusive
        while absent_sorted[j] < start_window:
            j += 1
        count = i - j + 1
        if count > max_in_any_window:
            max_in_any_window = count

    # Fixed anniversary blocks for reference
    fixed = []
    cur_start = start
    while cur_start <= end:
        cur_end = min(cur_start + relativedelta(years=1) - timedelta(days=1), end)
        days = 0
        for n in absent_sorted:
            d = from_day_serial(n)
            if cur_start <= d <= cur_end:
                days += 1
        fixed.append({
            "Year #": len(fixed) + 1,
            "Start": cur_start,
            "End": cur_end,
            "Absent days": days,
            "Status": "BREACH" if days > cap else "OK"
        })
        cur_start = cur_start + relativedelta(years=1)

    return {
        "total_absent_days": len(absent),
        "max_in_any_window": max_in_any_window,
        "fixed_blocks": fixed,
        "breach": max_in_any_window > cap
    }

# ------------------------------
# UI
# ------------------------------
st.set_page_config(page_title="ILR Dependant (Innovator) – Absence & Eligibility Calculator", layout="wide")
st.title("ILR Dependant (Innovator) – Absence & Eligibility Calculator")

with st.expander("About this tool", expanded=False):
    st.markdown(
        """
        This calculator helps **dependants of Innovator / Innovator Founder visa holders** check:
        - Your **5-year qualifying date** and **earliest application date** (28 days before).
        - Whether your **absences** breach the **rolling 12-month (180-day default)** rule.
        - A reference view of **anniversary-to-anniversary** 12-month blocks.

        **Important:** This is guidance only, not legal advice. Immigration Rules can change and individual facts matter.
        """
    )

col1, col2, col3 = st.columns([1.2, 1, 1])

with col1:
    res_start = st.date_input("Residence start date as dependant (YYYY‑MM‑DD)", value=None, format="YYYY-MM-DD")

with col2:
    cap = st.number_input("Absence cap per any 12 months", min_value=0, max_value=365, value=180, step=1)

with col3:
    st.write(" ")
    st.write(" ")

if "trips" not in st.session_state:
    st.session_state.trips = []  # list of tuples (out, back)

st.markdown("### Travel & Absences")
add = st.button("➕ Add a trip")
if add:
    st.session_state.trips.append((None, None))

# Render trip rows
to_delete = []
for idx, (out, back) in enumerate(st.session_state.trips):
    c1, c2, c3 = st.columns([1, 1, 0.2])
    with c1:
        out_val = st.date_input(f"Exit UK – trip {idx+1}", value=out, key=f"out_{idx}", format="YYYY-MM-DD")
    with c2:
        back_val = st.date_input(f"Re‑enter UK – trip {idx+1}", value=back, key=f"back_{idx}", format="YYYY-MM-DD")
    with c3:
        if st.button("🗑️", key=f"del_{idx}"):
            to_delete.append(idx)
    st.session_state.trips[idx] = (out_val, back_val)

# Delete selected trips
for i in sorted(to_delete, reverse=True):
    del st.session_state.trips[i]

st.divider()

if res_start is None:
    st.info("Enter your residence start date to see calculations.")
else:
    qualifying, earliest = compute_dates(res_start)
    colA, colB, colC = st.columns(3)
    with colA:
        st.metric("Qualifying date (+5 years)", qualifying.strftime("%d %b %Y"))
    with colB:
        st.metric("Earliest apply date (-28 days)", earliest.strftime("%d %b %Y"))
    with colC:
        today = date.today()
        st.metric("Today", today.strftime("%d %b %Y"))

    metrics = compute_absence(st.session_state.trips, res_start, qualifying, cap)

    colX, colY, colZ = st.columns(3)
    with colX:
        st.metric("Total absent days (5y window)", metrics["total_absent_days"])
    with colY:
        st.metric("Max absent in any rolling 12 months", f"{metrics['max_in_any_window']} / {cap}")
    with colZ:
        st.metric("Rolling status", "BREACH" if metrics["breach"] else "Within limit")

    if metrics["breach"]:
        st.error("Potential rolling 12‑month breach detected. Consider adjusting travel or timing and seek professional advice.")
    else:
        st.success("No rolling 12‑month breach detected based on entries.")

    # Fixed blocks table
    fixed_df = pd.DataFrame(metrics["fixed_blocks"])
    st.markdown("#### Fixed 12‑month blocks (anniversary‑to‑anniversary)")
    st.dataframe(fixed_df, use_container_width=True)

    # Export
    st.markdown("### Export summary")
    summary = {
        "Route": "Innovator Dependant (5 years)",
        "ResidenceStart": res_start.strftime("%Y-%m-%d"),
        "QualifyingDate(+5y)": qualifying.strftime("%Y-%m-%d"),
        "EarliestApplyDate(-28d)": earliest.strftime("%Y-%m-%d"),
        "CapPer12Months": cap,
        "TotalAbsentDays(5y)": metrics["total_absent_days"],
        "MaxAbsentInAnyRolling12m": metrics["max_in_any_window"],
        "RollingStatus": "BREACH" if metrics["breach"] else "Within limit",
    }
    summary_csv = pd.DataFrame([summary]).to_csv(index=False).encode("utf-8")
    st.download_button("Download summary CSV", data=summary_csv, file_name="ilr-dependant-innovator-absence-summary.csv", mime="text/csv")

    # Notes
    st.markdown(
        """
        **Notes**  
        - Rolling rule implemented as a 365‑day sliding window over each absent day.  
        - Travel days are counted as absent days **outside the UK** (inclusive).  
        - You must usually be **in the UK when you apply** and **not travel** until a decision is issued.
        """
    )
