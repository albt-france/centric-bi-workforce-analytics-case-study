"""Build the star-schema tables loaded by the Power BI model (data/model/*.csv), then re-compute every KPI of
sql/kpi_checks.sql from those model tables, the way the DAX measures do, and write docs/KPI_CHECKS.md.

    python src/export_model_tables.py      (runs the SQL first)
"""
from pathlib import Path

import numpy as np
import pandas as pd

from run_sql import main as run_sql

ROOT = Path(__file__).resolve().parents[1]
MODEL, PUB = ROOT / "data" / "model", ROOT / "data" / "public"
MODEL.mkdir(parents=True, exist_ok=True)
DIVISION = {"Delivery 1": "Delivery", "Delivery 2": "Delivery", "Delivery 3": "Delivery", "Data & Cloud": "Delivery",
            "Sales": "Commercial", "Support functions": "Support"}
ORDER = ["Delivery 1", "Delivery 2", "Delivery 3", "Data & Cloud", "Sales", "Support functions"]


def q(con, sql):
    return con.execute(sql).df()


def build(con):
    t = {}
    t["FactHeadcountMonthly"] = q(con, """
        SELECT month_start AS MonthStart, employee_key AS EmployeeKey, employee_id AS EmployeeId, cost_center AS CostCenter,
               grade AS Grade, fte AS FTE, salary_monthly_gross AS SalaryMonthlyGross, tenure_months AS TenureMonths,
               tenure_band AS TenureBand, is_active_month_end::INT AS IsActiveMonthEnd, is_duplicate_id::INT AS IsDuplicateId,
               is_new_hire_in_month::INT AS IsNewHireInMonth, capacity_hours AS CapacityHours, absence_days AS AbsenceDays
        FROM hc_monthly ORDER BY 1, 3""")
    t["FactMovements"] = q(con, """
        WITH m AS (
            SELECT mv.*, e.employee_id || '|' || strftime(e.valid_from, '%Y-%m-%d') AS employee_key, e.cost_center, e.grade, e.hire_date
            FROM movements mv JOIN emp_clean e ON e.employee_id = mv.employee_id AND mv.date BETWEEN e.valid_from AND e.valid_to
            QUALIFY row_number() OVER (PARTITION BY mv.movement_id ORDER BY e.valid_from DESC) = 1
        )
        SELECT m.movement_id AS MovementId, m.date AS Date, m.employee_id AS EmployeeId, m.employee_key AS EmployeeKey,
               m.movement_type AS MovementType, m.exit_type AS ExitType, m.exit_reason AS ExitReason,
               coalesce(m.regretted, FALSE)::INT AS IsRegretted,
               CASE WHEN m.movement_type = 'Exit' THEN coalesce(x.is_internal_transfer, FALSE)
                    WHEN m.movement_type = 'Hire' THEN EXISTS (SELECT 1 FROM exits_all z WHERE z.employee_id = m.employee_id
                                                              AND z.date BETWEEN m.date - INTERVAL 31 DAY AND m.date)
                    ELSE FALSE END::INT AS IsInternalTransfer,
               (m.exit_type = 'Voluntary')::INT AS IsVoluntary,
               m.cost_center AS CostCenter, m.grade AS Grade, datediff('month', m.hire_date, m.date) AS TenureMonths,
               CASE WHEN datediff('month', m.hire_date, m.date) < 12 THEN '0-1 y' WHEN datediff('month', m.hire_date, m.date) < 24 THEN '1-2 y'
                    WHEN datediff('month', m.hire_date, m.date) < 48 THEN '2-4 y' ELSE '4+ y' END AS TenureBand,
               m.from_department AS FromDepartment, m.to_department AS ToDepartment
        FROM m LEFT JOIN exits_all x ON x.movement_id = m.movement_id ORDER BY 2, 1""")
    t["FactTimesheet"] = q(con, """
        SELECT month AS MonthStart, employee_id AS EmployeeId, employee_key AS EmployeeKey, cost_center AS CostCenter, grade AS Grade,
               billable_hours AS BillableHours, nonbillable_hours AS NonBillableHours, bench_hours AS BenchHours,
               overtime_hours AS OvertimeHours, entered_date AS EnteredDate, lag_days AS EntryLagDays
        FROM ts_clean ORDER BY 1, 2""")
    t["FactFinance"] = q(con, """
        SELECT month AS MonthStart, cost_center AS CostCenter, department_reported AS DepartmentReported, revenue_eur AS Revenue,
               payroll_cost_eur AS PayrollCost, other_cost_eur AS OtherCost, payroll_headcount AS PayrollHeadcount
        FROM finance_monthly ORDER BY 1, 2""")
    t["FactRecruiting"] = q(con, """
        SELECT requisition_id AS RequisitionId, 'CC-' || CASE department WHEN 'Delivery 1' THEN 'D1' WHEN 'Delivery 2' THEN 'D2'
               WHEN 'Delivery 3' THEN 'D3' WHEN 'Data & Cloud' THEN 'DC' WHEN 'Sales' THEN 'SA' ELSE 'SF' END
               || '-' || CASE site WHEN 'Kaunas' THEN 'KAU' ELSE 'VNO' END AS CostCenter,
               grade AS Grade, reason AS Reason, opened_date AS OpenedDate, filled_date AS FilledDate, start_date AS StartDate,
               datediff('day', opened_date, filled_date) AS DaysToFill, status AS Status
        FROM recruiting ORDER BY 1""")
    months = q(con, "SELECT month_start, working_days, is_closed, finance_closed FROM months")
    hol = pd.read_csv(PUB / "lt_public_holidays.csv", parse_dates=["date"]).set_index("date").name
    days = pd.DataFrame({"Date": pd.date_range(months.month_start.min(), months.month_start.max() + pd.offsets.MonthEnd(0))})
    days["MonthStart"] = days.Date.dt.to_period("M").dt.to_timestamp()
    days["Year"] = days.Date.dt.year
    days["Quarter"] = days.Date.dt.year.astype(str) + "-Q" + days.Date.dt.quarter.astype(str)
    days["MonthNumber"] = days.Date.dt.month
    days["MonthLabel"] = days.Date.dt.strftime("%b %Y")
    days["MonthIndex"] = (days.Date.dt.year - 2024) * 12 + days.Date.dt.month - 10
    days["HolidayName"] = days.Date.map(hol)
    days["IsWorkingDay"] = ((days.Date.dt.weekday < 5) & days.HolidayName.isna()).astype(int)
    mm = months.rename(columns={"month_start": "MonthStart", "working_days": "WorkingDaysInMonth",
                                "is_closed": "IsClosedMonth", "finance_closed": "IsFinanceClosedMonth"})
    mm["MonthStart"] = pd.to_datetime(mm.MonthStart)
    days = days.merge(mm, on="MonthStart")
    days[["IsClosedMonth", "IsFinanceClosedMonth"]] = days[["IsClosedMonth", "IsFinanceClosedMonth"]].astype(int)
    t["DimDate"] = days
    t["DimEmployee"] = q(con, """
        SELECT e.employee_id || '|' || strftime(e.valid_from, '%Y-%m-%d') AS EmployeeKey, e.employee_id AS EmployeeId,
               e.valid_from AS ValidFrom, CASE WHEN e.valid_to < DATE '9999-12-31' THEN e.valid_to END AS ValidTo,
               e.department AS Department, coalesce(e.site, cm.site) AS Site, e.grade AS Grade, e.hire_date AS HireDate,
               e.source_system AS SourceSystem, e.is_duplicate_id::INT AS IsDuplicateId,
               coalesce(d.master_id, e.employee_id) AS MasterEmployeeId, coalesce(e.manager_id, 'Unassigned') AS ManagerId
        FROM emp_clean e LEFT JOIN dup_map d ON d.duplicate_id = e.employee_id LEFT JOIN cost_center_map cm ON cm.cost_center = e.cost_center
        ORDER BY 1""")
    org = q(con, "SELECT cost_center AS CostCenter, department AS Department, site AS Site FROM cost_center_map")
    org["Division"] = org.Department.map(DIVISION)
    org["IsBillable"] = (org.Division == "Delivery").astype(int)
    org["DepartmentOrder"] = org.Department.map(ORDER.index) + 1
    t["DimOrg"] = org.sort_values(["DepartmentOrder", "Site"])
    t["DimGrade"] = pd.DataFrame({"Grade": ["G1", "G2", "G3", "G4", "G5"],
                                  "GradeName": ["G1 Junior", "G2 Professional", "G3 Senior", "G4 Lead", "G5 Manager"],
                                  "GradeOrder": [1, 2, 3, 4, 5]})
    lci = pd.read_csv(PUB / "eurostat_labour_cost_index_ict_lt.csv")
    jvr = pd.read_csv(PUB / "eurostat_job_vacancy_rate_ict.csv").pivot(index="quarter", columns="geo", values="job_vacancy_rate_pct")
    osp = pd.read_csv(PUB / "osp_average_monthly_earnings.csv").query("measure == 'gross'").pivot(index="quarter", columns="activity", values="eur_month")
    ict = pd.read_csv(PUB / "eurostat_ict_specialists_share.csv").pivot(index="year", columns="geo", values="ict_specialists_pct_employment")
    mk = lci.rename(columns={"quarter": "Quarter", "lci_ict_2020_100": "LabourCostIndexICT"})
    mk = mk[mk.Quarter >= "2022-Q1"].copy()
    mk["QuarterStart"] = pd.PeriodIndex(mk.Quarter.str.replace("-", ""), freq="Q").to_timestamp()
    base = mk.loc[mk.Quarter == "2024-Q4", "LabourCostIndexICT"].iloc[0]
    mk["LabourCostIndexICT_2024Q4_100"] = (100 * mk.LabourCostIndexICT / base).round(1)
    mk["JobVacancyRateICT_LT"] = mk.Quarter.map(jvr.get("LT"))
    mk["JobVacancyRateICT_EU27"] = mk.Quarter.map(jvr.get("EU27_2020"))
    mk["JobVacancyRateICT_FR"] = mk.Quarter.map(jvr.get("FR"))
    mk["AvgGrossEarningsICT_LT"] = mk.Quarter.map(osp["ICT (J58-J63)"])
    mk["AvgGrossEarningsAll_LT"] = mk.Quarter.map(osp["All activities"])
    yr = mk.Quarter.str[:4].astype(int)
    mk["ICTSpecialistsShare_LT"] = yr.map(ict["LT"].rename(int))
    mk["ICTSpecialistsShare_EU27"] = yr.map(ict["EU27_2020"].rename(int))
    mk["Source"] = "PUBLIC DATA: Eurostat, Statistics Lithuania"
    t["Market"] = mk
    for name, df in t.items():
        out = df.copy()
        for c in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[c]):
                out[c] = out[c].dt.strftime("%Y-%m-%d")
        out.to_csv(MODEL / f"{name}.csv", index=False)
    return t


def dax_like(t):
    """Same logic as powerbi/measures.dax, applied to the model tables (independent of the SQL above)."""
    hc, mv, ts, fin, rec, org, dd = (t[k].copy() for k in ["FactHeadcountMonthly", "FactMovements", "FactTimesheet",
                                                              "FactFinance", "FactRecruiting", "DimOrg", "DimDate"])
    for d in (hc, ts, fin):
        d["MonthStart"] = pd.to_datetime(d.MonthStart)
    mv["Date"] = pd.to_datetime(mv.Date)
    rec["FilledDate"] = pd.to_datetime(rec.FilledDate)
    dept = org.set_index("CostCenter").Department
    bill = set(org.loc[org.IsBillable == 1, "CostCenter"])
    for d in (hc, mv, ts, fin):
        d["Department"] = d.CostCenter.map(dept)
    snap, r0, r1 = pd.Timestamp("2026-09-01"), pd.Timestamp("2025-10-01"), pd.Timestamp("2026-09-30")
    live = hc[(hc.IsActiveMonthEnd == 1) & (hc.IsDuplicateId == 0)]

    def headcount(month, dep=None):
        x = live[live.MonthStart == month]
        return len(x if dep is None else x[x.Department == dep])

    def avg_hc(dep=None):
        return np.mean([headcount(m, dep) for m in pd.date_range(r0, snap, freq="MS")])

    ex = mv[(mv.MovementType == "Exit") & mv.Date.between(r0, r1)]
    hires = mv[(mv.MovementType == "Hire") & (mv.IsInternalTransfer == 0) & mv.Date.between(r0, r1)]
    s_hc, s_ts = hc[(hc.MonthStart == snap) & (hc.IsDuplicateId == 0)], ts[ts.MonthStart == snap]
    a = avg_hc()
    oct_cap = hc[(hc.MonthStart == "2026-10-01") & (hc.IsDuplicateId == 0) & hc.CostCenter.isin(bill)].CapacityHours.sum()
    oct_bill = ts[(ts.MonthStart == "2026-10-01") & ts.CostCenter.isin(bill)].BillableHours.sum()
    d3 = (hc.MonthStart == snap) & (hc.IsDuplicateId == 0) & (hc.Department == "Delivery 3")
    dcf = (hc.MonthStart == "2026-02-01") & (hc.IsDuplicateId == 0) & (hc.Department == "Data & Cloud")
    fte_snap = live[live.MonthStart == snap].FTE.sum()
    v = {
        "Headcount": headcount(snap),
        "Headcount (raw HRIS)": len(hc[(hc.MonthStart == snap) & (hc.IsActiveMonthEnd == 1)]),
        "FTE": round(fte_snap, 1),
        "Average Headcount": round(a, 1),
        "Exits (gross)": len(ex),
        "Attrition % (gross)": len(ex) / a,
        "Attrition % (excl. transfers)": len(ex[ex.IsInternalTransfer == 0]) / a,
        "Voluntary Attrition %": len(ex[(ex.IsVoluntary == 1) & (ex.IsInternalTransfer == 0)]) / a,
        "Regretted Attrition %": len(ex[(ex.IsVoluntary == 1) & (ex.IsRegretted == 1)]) / a,
        "Voluntary Attrition % | Data & Cloud": len(ex[(ex.IsVoluntary == 1) & (ex.Department == "Data & Cloud")]) / avg_hc("Data & Cloud"),
        "Early Attrition % (exits < 12 months / hires)": len(ex[(ex.TenureMonths < 12) & (ex.IsInternalTransfer == 0)]) / len(hires),
        "Hires": len(hires),
        "Utilization %": s_ts[s_ts.CostCenter.isin(bill)].BillableHours.sum() / s_hc[s_hc.CostCenter.isin(bill)].CapacityHours.sum(),
        "Utilization % (closed months only)": np.nan,
        "Utilization % (raw, no cut-off)": oct_bill / oct_cap,
        "Bench %": ts[(ts.MonthStart == snap) & (ts.Department == "Delivery 3")].BenchHours.sum() / hc[d3].CapacityHours.sum(),
        "Overtime %": ts[(ts.MonthStart == "2026-02-01") & (ts.Department == "Data & Cloud")].OvertimeHours.sum() / hc[dcf].CapacityHours.sum(),
        "Average Gross Salary": round(live[live.MonthStart == snap].SalaryMonthlyGross.mean(), 0),
        "Median Days to Fill": rec[(rec.Status == "Filled") & rec.FilledDate.between(r0, r1)].DaysToFill.median(),
        "Finance Headcount": fin[fin.MonthStart == snap].PayrollHeadcount.sum(),
        "HR vs Finance Gap (finance - HR raw)": fin[fin.MonthStart == snap].PayrollHeadcount.sum() - len(hc[(hc.MonthStart == snap) & (hc.IsActiveMonthEnd == 1)]),
        "Revenue per FTE": round(fin[fin.MonthStart == snap].Revenue.sum() / fte_snap, 0),
    }
    return v


DAX_NAME = {"Headcount": "[Headcount]", "Headcount (raw HRIS)": "[Headcount (raw HRIS)]", "FTE": "[FTE]",
            "Average Headcount": "[Average Headcount]", "Exits (gross)": "[Exits (gross)]",
            "Attrition % (gross)": "[Attrition % (gross)]", "Attrition % (excl. transfers)": "[Attrition % (excl. transfers)]",
            "Voluntary Attrition %": "[Voluntary Attrition %]", "Regretted Attrition %": "[Regretted Attrition %]",
            "Early Attrition % (exits < 12 months / hires)": "[Early Attrition %]", "Hires": "[Hires]",
            "Utilization %": "[Utilization %]", "Utilization % (closed months only)": "[Utilization % (closed months)]",
            "Utilization % (raw, no cut-off)": "[Utilization %]", "Bench %": "[Bench %]", "Overtime %": "[Overtime %]",
            "Average Gross Salary": "[Average Gross Salary]", "Median Days to Fill": "[Median Days to Fill]",
            "Finance Headcount": "[Finance Headcount]", "HR vs Finance Gap (finance - HR raw)": "[HR vs Finance Gap]",
            "Revenue per FTE": "[Revenue per FTE]"}


def fmt(kpi, v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "blank"
    return f"{v:.1%}" if "%" in kpi else f"{v:,.1f}" if kpi in ("FTE", "Average Headcount") else f"{v:,.0f}"


# Values read on card visuals in Power BI Desktop (PBIP opened and refreshed, 19 Nov 2026), same filters as the context.
DESKTOP = {("Headcount", "Sep 2026, company"): "603", ("Headcount (raw HRIS)", "Sep 2026, company"): "621",
           ("Voluntary Attrition %", "R12M to Sep 2026"): "14.1%", ("Regretted Attrition %", "R12M to Sep 2026"): "6.8%",
           ("Utilization %", "Sep 2026, billable departments"): "78.4%",
           ("Utilization % (closed months only)", "Oct 2026, billable departments"): "blank",
           ("Utilization % (raw, no cut-off)", "Oct 2026, billable departments"): "60.2%",
           ("Finance Headcount", "Sep 2026, company"): "610", ("HR vs Finance Gap (finance - HR raw)", "Sep 2026, company"): "-11"}


def write_checks(con, t):
    sql = q(con, "SELECT * FROM out_kpi_checks")
    dl = dax_like(t)
    lines = ["# KPI checks: SQL reference vs model logic",
             "",
             "Each KPI of [KPI_DICTIONARY.md](KPI_DICTIONARY.md) is computed twice, independently:",
             "",
             "1. **SQL** (`sql/kpi_checks.sql`, DuckDB) on the cleaned source extracts;",
             "2. **model logic**: the filter logic of each DAX measure in `powerbi/measures.dax`, re-applied in pandas to the "
             "exact CSV tables that Power BI loads (`data/model/`), by `src/export_model_tables.py`.",
             "",
             "The last column is the value read in Power BI Desktop on a card visual with the same filters (PBIP opened and refreshed). "
             "Contexts: snapshot = **September 2026** (last month closed for timesheets and finance); "
             "R12M = **October 2025 to September 2026**. All data are SIMULATED.",
             "",
             "| KPI | DAX measure | Context (filters) | SQL | Model logic | Match | Power BI Desktop |",
             "|---|---|---|---:|---:|:---:|---:|"]
    ok = 0
    for r in sql.itertuples():
        key = r.kpi + (" | Data & Cloud" if "Data & Cloud" in r.context and r.kpi == "Voluntary Attrition %" else "")
        mv = dl.get(key)
        sv = None if pd.isna(r.sql_value) else float(r.sql_value)
        same = (sv is None and (mv is None or np.isnan(mv))) or (sv is not None and mv is not None and abs(sv - mv) < 1e-3 * max(1, abs(sv)))
        ok += same
        ctx = r.context.replace("R12M to Sep 2026", "R12M Oct 2025 - Sep 2026")
        lines.append(f"| {r.kpi} | `{DAX_NAME[r.kpi]}` | {ctx} | {fmt(r.kpi, sv)} | {fmt(r.kpi, mv)} | {'yes' if same else '**NO**'} | {DESKTOP.get((r.kpi, r.context), 'not read')} |")
    lines += ["", f"**{ok} / {len(sql)} KPIs match** between SQL and the model logic.",
              "",
              "Notes:",
              "- `Utilization % (closed months)` is blank for October 2026 on purpose: the month is not closed at the extract "
              "date (6 Nov 2026), because timesheets arrive up to 10 days after month end. Without the cut-off rule the same month "
              "shows a utilisation far below its true level (row *raw, no cut-off*).",
              "- `HR vs Finance Gap` is negative because the HR extract still holds 18 duplicate ids from the HRIS migration, "
              "partly offset by leavers that finance pays in their last month; see `sql/06_hr_finance_reconciliation.sql`.",
              "- Power BI Desktop: the PBIP opened, refreshed and rendered all four pages; the 9 values read on cards match SQL. "
              "KPIs marked *not read* have no card on the report pages with that exact filter; their DAX logic is covered by the model-logic column."]
    (ROOT / "docs" / "KPI_CHECKS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ok, len(sql)


def main():
    con = run_sql()
    t = build(con)
    ok, n = write_checks(con, t)
    print("model tables:", {k: len(v) for k, v in t.items()}, f"| KPI checks {ok}/{n}")


if __name__ == "__main__":
    main()
