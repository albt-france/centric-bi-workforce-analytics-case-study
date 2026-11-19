"""Simulate the HR, timesheet, recruiting and finance extracts of a FICTIONAL 600-person IT services company
(two sites: Kaunas and Vilnius; 24 months: Nov 2024 - Oct 2026; extract taken on 2026-11-06). Seed 42.

Nothing here is Centric data. Public data only calibrates the simulation:
  - market pay growth  <- Eurostat labour cost index, ICT sector (J), Lithuania (4-quarter average)
  - time to fill        <- Eurostat job vacancy rate, ICT sector (J), Lithuania (last value carried forward)
  - working days        <- Lithuanian public holidays (Nager.Date)

Eight events are planted on purpose; they are listed in data/_hidden_truth.csv (kept out of the repository)
so that the analysis has to find them from the data alone.

    python src/simulate_company.py
Writes data/sim/*.csv (the "source system extracts").
"""
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PUB, SIM = ROOT / "data" / "public", ROOT / "data" / "sim"
SIM.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(42)

MONTHS = pd.date_range("2024-11-01", "2026-10-01", freq="MS")
EXTRACT = pd.Timestamp("2026-11-06")          # date the extracts were taken
FIN_LAST = pd.Timestamp("2026-09-01")         # finance has closed up to September 2026
OPEN_END = pd.Timestamp("9999-12-31")

DEPTS = {  # initial size, share in Kaunas, pay factor, billable, hourly rate (EUR)
    "Delivery 1": (135, 0.55, 1.00, True, 52), "Delivery 2": (125, 0.70, 1.00, True, 50),
    "Delivery 3": (108, 0.60, 1.00, True, 55), "Data & Cloud": (92, 0.45, 1.08, True, 68),
    "Sales": (40, 0.60, 0.92, False, 0), "Support functions": (70, 0.65, 0.85, False, 0)}
DCODE = {"Delivery 1": "D1", "Delivery 2": "D2", "Delivery 3": "D3", "Data & Cloud": "DC", "Sales": "SA", "Support functions": "SF"}
SCODE = {"Kaunas": "KAU", "Vilnius": "VNO"}
GRADES, GRADE_P = ["G1", "G2", "G3", "G4", "G5"], [0.20, 0.35, 0.28, 0.12, 0.05]
BAND = {"G1": 2100, "G2": 3200, "G3": 4400, "G4": 5500, "G5": 6400}   # gross EUR/month at Nov-2024 market level
PASS_THROUGH = 0.55                            # share of market pay growth given to incumbents each January


# ------------------------------------------------------------------ public calibration
def market_index():
    """Monthly market pay index (1.0 = Nov 2024) from the 4-quarter moving average of the ICT labour cost index."""
    lci = pd.read_csv(PUB / "eurostat_labour_cost_index_ict_lt.csv")
    lci["ma4"] = lci.lci_ict_2020_100.rolling(4).mean()
    lci = lci.dropna()
    lci["mid"] = pd.PeriodIndex(lci.quarter.str.replace("-", ""), freq="Q").to_timestamp() + pd.DateOffset(months=1)
    s = lci.set_index("mid").ma4
    idx = pd.date_range("2005-01-01", "2027-12-01", freq="MS")
    s = s.reindex(idx.union(s.index)).interpolate(limit_area="inside").reindex(idx)
    first, last = s.first_valid_index(), s.last_valid_index()
    g_back = (s[first + pd.DateOffset(years=1)] / s[first]) ** (1 / 12)
    g_fwd = (s[last] / s[last - pd.DateOffset(years=1)]) ** (1 / 12)
    for d in idx:
        if d < first:
            s[d] = s[first] / g_back ** ((first.year - d.year) * 12 + first.month - d.month)
        elif d > last:
            s[d] = s[last] * g_fwd ** ((d.year - last.year) * 12 + d.month - last.month)
    return s / s[pd.Timestamp("2024-11-01")]


def vacancy_rate():
    j = pd.read_csv(PUB / "eurostat_job_vacancy_rate_ict.csv")
    j = j[j.geo == "LT"].set_index("quarter").job_vacancy_rate_pct
    return j, j.loc["2022-Q1":].mean()


def working_days():
    hol = set(pd.to_datetime(pd.read_csv(PUB / "lt_public_holidays.csv").date))
    days = pd.date_range("2024-11-01", "2026-10-31")
    wd = [d for d in days if d.weekday() < 5 and d not in hol]
    return pd.Series(1, index=pd.DatetimeIndex(wd))


MKT = market_index()
JVR, JVR_MEAN = vacancy_rate()
WD = working_days()


def mkt(d):
    return MKT[pd.Timestamp(d.year, d.month, 1)]


def wd_between(a, b):
    return int(WD[(WD.index >= a) & (WD.index <= b)].sum())


# ------------------------------------------------------------------ state
class Company:
    def __init__(self):
        self.next_id, self.cur, self.start, self.rows, self.moves = 1, {}, {}, [], []
        self.scheduled_exit, self.hires_log, self.exit_log = {}, [], defaultdict(list)

    def new_id(self):
        eid = f"E{self.next_id:04d}"
        self.next_id += 1
        return eid

    def open(self, eid, attrs, d):
        self.cur[eid], self.start[eid] = dict(attrs), d

    def close(self, eid, d_end):
        self.rows.append({"employee_id": eid, "valid_from": self.start[eid], "valid_to": d_end, **self.cur[eid]})

    def change(self, eid, d, **kw):
        if self.start[eid] == d:                      # second change on the same day: update the open row
            self.cur[eid].update(kw)
            return
        self.close(eid, d - pd.Timedelta(days=1))
        attrs = {**self.cur[eid], **kw}
        self.open(eid, attrs, d)

    def leave(self, eid, d):
        self.close(eid, d)
        del self.cur[eid], self.start[eid]


co = Company()


def manager_of(dept, site):
    """Most senior employee of the org unit (lowest id at the highest grade); ids only."""
    cands = [(a["grade"], e) for e, a in co.cur.items() if a["department"] == dept and a["site"] == site and not a.get("ghost")]
    if not cands:
        return None
    g = max(c[0] for c in cands)
    return min(e for gg, e in cands if gg == g)


def new_attrs(dept, site, grade, d, hire_date, birth_key=None, salary=None):
    pay = DEPTS[dept][2]
    if salary is None:
        salary = BAND[grade] * pay * mkt(d) * rng.normal(1, 0.05)
    return {"department": dept, "site": site, "grade": grade, "fte": 1.0 if rng.random() > 0.05 else float(rng.choice([0.5, 0.6, 0.8])),
            "salary_monthly_gross": round(float(salary), 0), "cost_center": f"CC-{DCODE[dept]}-{SCODE[site]}",
            "hire_date": hire_date, "birth_key": birth_key or f"{rng.integers(0, 16**8):08x}", "manager_id": None,
            "source_system": "Legacy HRIS"}


# ------------------------------------------------------------------ initial population (1 Nov 2024)
T0 = MONTHS[0]
for dept, (n, kau, *_rest) in DEPTS.items():
    for _ in range(n):
        site = "Kaunas" if rng.random() < kau else "Vilnius"
        grade = rng.choice(GRADES, p=GRADE_P)
        tenure_m = int(min(rng.exponential(48), 180)) + 1
        hire = (T0 - pd.DateOffset(months=tenure_m)).replace(day=int(rng.integers(1, 28)))
        sal = BAND[grade] * DEPTS[dept][2] * (mkt(hire) / mkt(T0)) ** (1 - PASS_THROUGH) * rng.normal(1, 0.05)
        a = new_attrs(dept, site, grade, T0, hire, salary=sal)
        co.open(co.new_id(), a, hire if hire > pd.Timestamp("2024-01-01") else pd.Timestamp("2024-01-01"))
for eid, a in co.cur.items():
    a["manager_id"] = manager_of(a["department"], a["site"])


# ------------------------------------------------------------------ events (the hidden truth)
REORG_DATE = pd.Timestamp("2026-03-31")                 # 1. Delivery 2 reorg keyed as exit + rehire
MIGRATION = pd.Timestamp("2025-09-01")                  # 2. HRIS migration: 18 second ids
DC_OT = {pd.Timestamp(m): v for m, v in [("2025-12-01", .10), ("2026-01-01", .17), ("2026-02-01", .18),
                                          ("2026-03-01", .17), ("2026-04-01", .16), ("2026-05-01", .10)]}  # 3. overload
DC_EXIT = (pd.Timestamp("2026-03-01"), pd.Timestamp("2026-08-01"))   # 3. ... then regretted exits double
WAVE = (pd.Timestamp("2025-04-01"), pd.Timestamp("2025-06-01"))       # 5. Vilnius hiring wave
MISMAP = (pd.Timestamp("2026-05-01"), pd.Timestamp("2026-07-01"), "CC-D1-VNO", "Data & Cloud")  # 7.
BENCH_D3 = pd.Timestamp("2026-06-01")                                 # 8. large client project ends 31 May


def comp_multiplier(m, tenure_y):
    """4. pay compression: voluntary exits of 2-4 year tenure rise once market pay outruns incumbents' raises."""
    if not 2 <= tenure_y < 4:
        return 1.0
    if m >= pd.Timestamp("2026-01-01"):
        return 2.1
    if m >= pd.Timestamp("2025-07-01"):
        return 1.5
    return 1.0


def exit_reason(kind):
    pools = {"comp": (["Better pay elsewhere", "Career growth", "Other"], [.65, .25, .10]),
             "dc": (["Workload / burnout", "Better pay elsewhere", "Career growth"], [.6, .2, .2]),
             "early": (["Role not as expected", "Onboarding / team fit", "Better pay elsewhere"], [.45, .4, .15]),
             "base": (["Career growth", "Better pay elsewhere", "Relocation", "Personal", "Other"], [.32, .28, .12, .14, .14])}
    v, p = pools[kind]
    return str(rng.choice(v, p=p))


def do_exit(eid, d, typ, reason, regretted):
    a = co.cur[eid]
    co.moves.append({"date": d, "employee_id": eid, "movement_type": "Exit", "exit_type": typ, "exit_reason": reason,
                     "regretted": regretted, "from_department": a["department"], "to_department": None})
    co.exit_log[pd.Timestamp(d.year, d.month, 1)].append((a["department"], a["site"], a["grade"], typ))
    co.leave(eid, d)


def do_hire(dept, site, grade, d, reason, early_p):
    eid = co.new_id()
    a = new_attrs(dept, site, grade, d, d)
    a["manager_id"] = manager_of(dept, site)
    if d >= MIGRATION:
        a["source_system"] = "New HRIS"
    co.open(eid, a, d)
    co.moves.append({"date": d, "employee_id": eid, "movement_type": "Hire", "exit_type": None, "exit_reason": None,
                     "regretted": None, "from_department": None, "to_department": dept})
    co.hires_log.append({"employee_id": eid, "start_date": d, "department": dept, "site": site, "grade": grade, "reason": reason})
    if rng.random() < early_p:
        co.scheduled_exit[eid] = d + pd.DateOffset(months=int(rng.integers(2, 6)), days=int(rng.integers(0, 25)))


def rand_day(m, lo=1):
    last = (m + pd.offsets.MonthEnd(0)).day
    return m + pd.Timedelta(days=int(rng.integers(lo - 1, last)))


ghosts = []
for m in MONTHS:
    me = m + pd.offsets.MonthEnd(0)
    # January raises (market growth of the past year, partly passed through) and promotions (Jan, Jul)
    if m.month == 1:
        growth = mkt(m) / mkt(m - pd.DateOffset(years=1))
        for eid, a in list(co.cur.items()):
            if not a.get("ghost"):
                co.change(eid, m, salary_monthly_gross=round(a["salary_monthly_gross"] * growth ** PASS_THROUGH * rng.normal(1, .01), 0))
    if m.month in (1, 7):
        for eid, a in list(co.cur.items()):
            if a["grade"] != "G5" and not a.get("ghost") and rng.random() < 0.04:
                g = GRADES[GRADES.index(a["grade"]) + 1]
                sal = max(a["salary_monthly_gross"] * 1.08, BAND[g] * DEPTS[a["department"]][2] * mkt(m) * 0.92)
                co.change(eid, m + pd.Timedelta(days=0 if m.month == 1 else 0), grade=g, salary_monthly_gross=round(sal, 0))
    # 2. HRIS migration: every live record re-keyed into the new system; 18 people get a second id
    if m == MIGRATION:
        live = [e for e, a in co.cur.items()]
        overlap = set(rng.choice(live, 5, replace=False))
        for eid in live:
            co.change(eid, m, source_system="New HRIS")
            if eid in overlap:                       # legacy row not closed on time -> overlapping SCD2 periods
                co.rows[-1]["valid_to"] = m + pd.Timedelta(days=3)
        for eid in rng.choice(live, 18, replace=False):
            g = co.new_id()
            co.open(g, {**co.cur[eid], "ghost": True}, m)
            ghosts.append((g, eid))
    # monthly exits
    for eid, a in list(co.cur.items()):
        if a.get("ghost"):
            continue
        d = rand_day(m)
        if eid in co.scheduled_exit and co.scheduled_exit[eid] <= me:
            do_exit(eid, min(co.scheduled_exit[eid], me), "Voluntary", exit_reason("early"), bool(rng.random() < .05))
            continue
        ten_y = (m - a["hire_date"]).days / 365.25
        tmod = 1.25 if ten_y < 1 else 1.15 if ten_y < 2 else 1.05 if ten_y < 4 else 0.8 if ten_y < 7 else 0.5
        dmod = {"Sales": 1.3, "Support functions": 0.8}.get(a["department"], 1.0)
        cm = comp_multiplier(m, ten_y)
        dc = a["department"] == "Data & Cloud" and DC_EXIT[0] <= m <= DC_EXIT[1]
        p_vol = 0.0072 * tmod * dmod * cm * (3.0 if dc else 1.0)
        r = rng.random()
        if r < p_vol:
            kind = "dc" if dc else "comp" if cm > 1 else "base"
            p_reg = 0.75 if dc else 0.55 if a["grade"] in ("G3", "G4") else 0.40
            do_exit(eid, d, "Voluntary", exit_reason(kind), bool(rng.random() < p_reg))
        elif r < p_vol + 0.0020:
            do_exit(eid, d, "Involuntary", str(rng.choice(["Performance", "End of fixed-term contract", "Misconduct"], p=[.5, .4, .1])), False)
    # ordinary internal transfers (keyed correctly as transfers)
    for eid, a in list(co.cur.items()):
        if not a.get("ghost") and DEPTS[a["department"]][3] and rng.random() < 0.003:
            to = str(rng.choice([x for x in ["Delivery 1", "Delivery 2", "Delivery 3", "Data & Cloud"] if x != a["department"]]))
            d = m + pd.Timedelta(days=int(rng.integers(0, 27)))
            co.moves.append({"date": d, "employee_id": eid, "movement_type": "Transfer", "exit_type": None, "exit_reason": None,
                             "regretted": None, "from_department": a["department"], "to_department": to})
            co.change(eid, d, department=to, cost_center=f"CC-{DCODE[to]}-{SCODE[a['site']]}", manager_id=manager_of(to, a["site"]))
    # 1. Delivery 2 reorganisation keyed as 50 exits on 31 March and 50 rehires on 1 April (same ids)
    if m == REORG_DATE.replace(day=1):
        d2 = [e for e, a in co.cur.items() if a["department"] == "Delivery 2" and not a.get("ghost")]
        for eid in rng.choice(d2, 50, replace=False):
            keep = dict(co.cur[eid])
            do_exit(eid, REORG_DATE, "Organisational change", "Reorganisation", False)
            co.exit_log[m].pop()                     # not a real departure: no replacement requisition
            d = REORG_DATE + pd.Timedelta(days=1)
            co.open(eid, keep, d)
            co.moves.append({"date": d, "employee_id": eid, "movement_type": "Hire", "exit_type": None, "exit_reason": None,
                             "regretted": None, "from_department": None, "to_department": "Delivery 2"})
        for eid in d2:
            if eid in co.cur:
                co.cur[eid]["manager_id"] = manager_of("Delivery 2", co.cur[eid]["site"])
    # hires: replacements of exits two months earlier, slow growth, and the Vilnius wave
    prev = co.exit_log.get(m - pd.DateOffset(months=2), None)
    if prev is None:
        prev = [(str(rng.choice(list(DEPTS), p=np.array([v[0] for v in DEPTS.values()]) / 570)), "Kaunas" if rng.random() < .6 else "Vilnius",
                 str(rng.choice(GRADES[:3])), "Voluntary") for _ in range(8)]
    for dept, site, grade, typ in prev:
        if rng.random() < 0.88:
            g = grade if rng.random() < 0.65 or grade == "G1" else GRADES[GRADES.index(grade) - 1]
            do_hire(dept, site, g, rand_day(m), "Replacement", 0.08)
    for _ in range(rng.poisson(0.6)):
        dept = str(rng.choice(list(DEPTS), p=[.22, .12, .14, .32, .10, .10]))
        do_hire(dept, "Kaunas" if rng.random() < .6 else "Vilnius", str(rng.choice(GRADES[:4], p=[.35, .4, .2, .05])), rand_day(m), "Growth", 0.08)
    if WAVE[0] <= m <= WAVE[1]:                      # 5. Vilnius wave: 30% leave within 6 months (onboarding)
        for _ in range(15):
            do_hire(str(rng.choice(["Delivery 1", "Data & Cloud"], p=[.6, .4])), "Vilnius", str(rng.choice(["G1", "G2"], p=[.6, .4])),
                    rand_day(m), "Growth - Vilnius ramp-up", 0.30)

# close the open records at the extract date
for eid in list(co.cur):
    co.close(eid, OPEN_END)

emp = pd.DataFrame(co.rows)
emp["ghost"] = emp["ghost"].eq(True)
# 2b. legacy data gaps: missing manager / site on a few legacy rows
leg = emp.index[emp.source_system == "Legacy HRIS"]
emp.loc[rng.choice(leg, 9, replace=False), "manager_id"] = None
emp.loc[rng.choice(leg, 4, replace=False), "site"] = None
emp = emp.sort_values(["employee_id", "valid_from"]).reset_index(drop=True)
mov = pd.DataFrame(co.moves).sort_values(["date", "employee_id"]).reset_index(drop=True)
mov.insert(0, "movement_id", [f"M{i:05d}" for i in range(1, len(mov) + 1)])


# ------------------------------------------------------------------ timesheets and absences (real people only)
def active_spans(df):
    """Employment spans per real employee: first valid_from to last valid_to, split by attribute rows."""
    return df[~df.ghost]


real = active_spans(emp)
ts_rows, ab_rows = [], []
SEASON_VAC = {1: .6, 2: .8, 3: .8, 4: 1.0, 5: 1.2, 6: 2.2, 7: 4.0, 8: 3.5, 9: 1.0, 10: .8, 11: .7, 12: 2.4}
for m in MONTHS:
    me = m + pd.offsets.MonthEnd(0)
    rows = real[(real.valid_from <= me) & (real.valid_to >= m)]
    # one line per employee and month, attributes of the row valid at month end (or last day employed)
    rows = rows.sort_values("valid_from").groupby("employee_id").tail(1)
    for r in rows.itertuples():
        first_day = max(m, r.valid_from) if r.hire_date >= m else m
        span = real[(real.employee_id == r.employee_id)]
        last_day = min(me, span.valid_to.max())
        wdays = wd_between(max(first_day, r.hire_date), last_day)
        if wdays <= 0:
            continue
        vac = min(wdays, rng.poisson(SEASON_VAC[m.month] * wdays / 21))
        sick = min(wdays - vac, rng.poisson(0.6 * wdays / 21))
        if vac:
            ab_rows.append({"employee_id": r.employee_id, "month": m, "absence_type": "Annual leave", "days": int(vac)})
        if sick:
            ab_rows.append({"employee_id": r.employee_id, "month": m, "absence_type": "Sick leave", "days": int(sick)})
        avail = (wdays - vac - sick) * 8 * r.fte
        dept = r.department
        if DEPTS[dept][3]:
            bench_mu = 0.18 if (dept == "Delivery 3" and m >= BENCH_D3) else 0.065 if dept == "Delivery 3" else 0.06
            bench = float(np.clip(rng.normal(bench_mu, 0.05), 0, 1))
            nonbill = float(np.clip(rng.normal(0.13, 0.03), 0.03, 1 - bench))
            bill = max(0.0, 1 - bench - nonbill)
            ot_mu = DC_OT.get(m, 0.045) if dept == "Data & Cloud" else 0.045
            if dept == "Data & Cloud" and m not in DC_OT:
                ot_mu = 0.05
        else:
            bench, nonbill, bill, ot_mu = 0.0, 1.0, 0.0, 0.02
        ot = float(np.clip(rng.normal(ot_mu, ot_mu * 0.35), 0, 0.4)) * (bill > 0 or not DEPTS[dept][3])
        lag = int(rng.choice(range(11), p=[.12, .14, .13, .12, .10, .09, .08, .07, .06, .05, .04]))
        if rng.random() < 0.02:
            lag = int(rng.integers(11, 31))
        ts_rows.append({"employee_id": r.employee_id, "month": m, "billable_hours": round(avail * bill, 1),
                        "nonbillable_hours": round(avail * nonbill, 1), "bench_hours": round(avail * bench, 1),
                        "overtime_hours": round(avail * ot, 1), "entered_date": me + pd.Timedelta(days=lag),
                        "_dept": dept, "_cc": r.cost_center})
ts_all = pd.DataFrame(ts_rows)
ts = ts_all[ts_all.entered_date <= EXTRACT].drop(columns=["_dept", "_cc"])     # 6. late entries not in the extract yet
ab = pd.DataFrame(ab_rows)


# ------------------------------------------------------------------ recruiting (one requisition per hire + still-open ones)
rec = []
for i, h in enumerate(co.hires_log, 1):
    q = f"{h['start_date'].year}-Q{(h['start_date'].month - 1) // 3 + 1}"
    jvr = JVR.get(q, JVR.iloc[-1])
    base = {"G1": 28, "G2": 38, "G3": 50, "G4": 62, "G5": 75}[h["grade"]]
    days = int(base * (jvr / JVR_MEAN) ** 1.5 * rng.lognormal(0, 0.25))
    notice = int(rng.integers(14, 36))
    filled = h["start_date"] - pd.Timedelta(days=notice)
    rec.append({"requisition_id": f"R{i:04d}", "department": h["department"], "site": h["site"], "grade": h["grade"],
                "reason": h["reason"], "opened_date": filled - pd.Timedelta(days=days), "filled_date": filled,
                "start_date": h["start_date"], "hired_employee_id": h["employee_id"], "status": "Filled"})
for j in range(16):
    dept = str(rng.choice(list(DEPTS), p=[.2, .15, .1, .35, .1, .1]))
    rec.append({"requisition_id": f"R{len(rec) + 1:04d}", "department": dept, "site": "Kaunas" if rng.random() < .6 else "Vilnius",
                "grade": str(rng.choice(GRADES[:4])), "reason": "Replacement", "opened_date": EXTRACT - pd.Timedelta(days=int(rng.integers(5, 80))),
                "filled_date": pd.NaT, "start_date": pd.NaT, "hired_employee_id": None, "status": "Open"})
rec = pd.DataFrame(rec)
rec = rec[rec.opened_date >= pd.Timestamp("2024-09-01")]    # requisitions opened before the HR system window are not exported


# ------------------------------------------------------------------ finance export (by cost centre, closed months only)
ccmap = pd.DataFrame([{"cost_center": f"CC-{DCODE[d]}-{SCODE[s]}", "department": d, "site": s} for d in DEPTS for s in SCODE])
fin = []
for m in MONTHS[MONTHS <= FIN_LAST]:
    me = m + pd.offsets.MonthEnd(0)
    paid = real[(real.valid_from <= me) & (real.valid_to >= m)].sort_values("valid_from").groupby("employee_id").tail(1)
    tsm = ts_all[ts_all.month == m]
    for cc in ccmap.itertuples():
        p = paid[paid.cost_center == cc.cost_center]
        dept = cc.department
        rev = tsm.loc[tsm._cc == cc.cost_center, "billable_hours"].sum() * DEPTS[dept][4] * rng.normal(1, 0.02)
        payroll = (p.salary_monthly_gross * p.fte).sum() * 1.0177
        reported = MISMAP[3] if (cc.cost_center == MISMAP[2] and MISMAP[0] <= m <= MISMAP[1]) else dept
        fin.append({"month": m, "cost_center": cc.cost_center, "department_reported": reported, "revenue_eur": round(rev, 0),
                    "payroll_cost_eur": round(payroll, 0), "other_cost_eur": round(len(p) * 700 + 6000 * rng.normal(1, .05), 0),
                    "payroll_headcount": int(len(p))})
fin = pd.DataFrame(fin)


# ------------------------------------------------------------------ write
def fmt_dates(df):
    out = df.copy()
    for c in out.columns:
        if np.issubdtype(out[c].dtype, np.datetime64):
            out[c] = out[c].dt.strftime("%Y-%m-%d")
    return out


emp_out = emp.drop(columns=["ghost"])
emp_out["valid_to"] = emp_out.valid_to.where(emp_out.valid_to < OPEN_END, pd.NaT)
fmt_dates(emp_out).to_csv(SIM / "employees.csv", index=False)
fmt_dates(mov).to_csv(SIM / "movements.csv", index=False)
fmt_dates(ts).to_csv(SIM / "timesheets.csv", index=False)
fmt_dates(ab).to_csv(SIM / "absences.csv", index=False)
fmt_dates(rec).to_csv(SIM / "recruiting.csv", index=False)
fmt_dates(fin).to_csv(SIM / "finance_monthly.csv", index=False)
ccmap.to_csv(SIM / "cost_center_map.csv", index=False)
pd.DataFrame({"key": ["extract_date", "finance_closed_through", "first_month", "last_month"],
              "value": [EXTRACT.date(), FIN_LAST.date(), MONTHS[0].date(), MONTHS[-1].date()]}).to_csv(SIM / "extract_info.csv", index=False)

truth = [
    (1, "False signal", "2026-03", "Delivery 2", "Reorganisation keyed as 50 exits (31 Mar) + 50 rehires (1 Apr) with the same ids", "Gross turnover spikes; excluding internal transfers nothing moves", "Do NOT alert"),
    (2, "HRIS migration duplicates", "2025-09 onwards", "All", "18 employees received a second id; ghost records never closed; 5 overlapping SCD2 rows", "Headcount +3%; duplicate birth_key+hire_date+grade; no timesheets", "Fix"),
    (3, "Overload then regretted exits", "OT 2026-01..04, exits 2026-03..08", "Data & Cloud", "Overtime >15% for 4 months, then voluntary hazard x3.0 with 75% regretted", "Regretted voluntary exits about double", "Alert"),
    (4, "Pay compression", "2025-07 onwards", "All", "New hires paid at market index; incumbents get 55% of market growth; 2-4y tenure exit hazard x1.5 then x2.1", "New hires out-earn 2-4y incumbents of same grade; 2-4y exits rise", "Alert"),
    (5, "Vilnius hiring wave", "2025-04..06", "Delivery 1, Data & Cloud (Vilnius)", "45 extra hires with 30% probability of leaving within 6 months (10% elsewhere)", "6-month cohort exit rate ~30% vs ~10%", "Alert"),
    (6, "Incomplete last month", "2026-10", "All", "Timesheets entered up to 10 days after month end; extract on 2026-11-06", "Last month looks under-utilised", "Cut-off rule"),
    (7, "Cost centre mis-mapped in finance", "2026-05..07", "CC-D1-VNO reported as Data & Cloud", "Finance export maps the cost centre to the wrong department", "Revenue per FTE anomaly; HR vs finance headcount gap by department", "Fix"),
    (8, "Large project ends", "2026-06 onwards", "Delivery 3", "Bench share 6% -> 18%", "Real utilisation drop", "Alert / plan"),
]
pd.DataFrame(truth, columns=["id", "event", "period", "scope", "mechanism", "expected_signal", "action"]).to_csv(ROOT / "data" / "_hidden_truth.csv", index=False)

hc = [((real.valid_from <= m + pd.offsets.MonthEnd(0)) & (real.valid_to >= m + pd.offsets.MonthEnd(0))).sum() for m in MONTHS]
print(f"ids {co.next_id - 1} | SCD2 rows {len(emp)} | moves {len(mov)} (exits {(mov.movement_type == 'Exit').sum()}, hires {(mov.movement_type == 'Hire').sum()}) "
      f"| true month-end HC min/avg/max {min(hc)}/{np.mean(hc):.0f}/{max(hc)} | ts {len(ts)}/{len(ts_all)} | rec {len(rec)} | fin {len(fin)}")
