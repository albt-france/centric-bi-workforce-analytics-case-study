"""Write the Power BI project (PBIP, text format) from data/model/*.csv:
  powerbi/CentricWorkforce.pbip
  powerbi/CentricWorkforce.SemanticModel/definition/...  (TMDL: tables, Power Query, relationships, measures, RLS)
  powerbi/CentricWorkforce.Report/...                    (report shell; pages are written by build_report_pages.py)
  powerbi/measures.dax                                    (every measure, to paste by hand if needed)

    python src/build_pbip.py
The data source is the `DataFolder` parameter (default C:\\case-study-centric\\data\\model\\): change it in
Power BI Desktop (Transform data > Edit parameters) if the repository lives elsewhere.
"""
import json
import shutil
import uuid
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL_CSV = ROOT / "data" / "model"
PBI = ROOT / "powerbi"
SM = PBI / "CentricWorkforce.SemanticModel"
RP = PBI / "CentricWorkforce.Report"
DEF = SM / "definition"
DATA_FOLDER = r"C:\case-study-centric\data\model" + "\\"


def tag(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "centric-workforce/" + "/".join(parts)))


DATE_COLS = {"MonthStart", "Date", "EnteredDate", "OpenedDate", "FilledDate", "StartDate", "ValidFrom", "ValidTo", "HireDate", "QuarterStart"}
HIDDEN = {  # foreign keys and technical columns: users slice by the dimensions instead
    "FactHeadcountMonthly": {"MonthStart", "EmployeeKey", "CostCenter", "Grade"},
    "FactMovements": {"Date", "EmployeeKey", "CostCenter", "Grade"},
    "FactTimesheet": {"MonthStart", "EmployeeKey", "CostCenter", "Grade"},
    "FactFinance": {"MonthStart", "CostCenter"},
    "FactRecruiting": {"FilledDate", "OpenedDate", "CostCenter", "Grade"},
    "DimDate": {"MonthIndex"}, "DimOrg": {"DepartmentOrder"}, "DimGrade": {"GradeOrder"},
}
SORT_BY = {("DimDate", "MonthLabel"): "MonthIndex", ("DimOrg", "Department"): "DepartmentOrder", ("DimGrade", "GradeName"): "GradeOrder"}
FORMAT = {"FTE": "0.0", "SalaryMonthlyGross": "€#,0", "Revenue": "€#,0", "PayrollCost": "€#,0", "OtherCost": "€#,0",
          "CapacityHours": "#,0", "BillableHours": "#,0", "NonBillableHours": "#,0", "BenchHours": "#,0", "OvertimeHours": "#,0"}
EXTRA_STEPS = {  # Power Query steps beyond typing (applied after the "Typed" step)
    "FactTimesheet": ('Logged = Table.AddColumn(Typed, "LoggedHours", each [BillableHours] + [NonBillableHours] + [BenchHours], type number)', "Logged",
                      [("LoggedHours", "double")]),
    "DimOrg": ('OrgUnit = Table.AddColumn(Typed, "OrgUnit", each [Department] & " · " & [Site], type text)', "OrgUnit",
               [("OrgUnit", "string")]),
    "DimEmployee": ('Cleaned = Table.ReplaceValue(Typed, null, "Unknown", Replacer.ReplaceValue, {"Site"})', "Cleaned", []),
}
TABLE_DESC = {
    "FactHeadcountMonthly": "One row per person and month employed (from the SCD2 history). SIMULATED.",
    "FactMovements": "Hires, exits and transfers with exit type, regretted flag and internal-transfer flag. SIMULATED.",
    "FactTimesheet": "Hours per person and month as received at the extract date (6 Nov 2026). SIMULATED.",
    "FactFinance": "Finance export by cost centre, closed months only (to Sep 2026). SIMULATED.",
    "FactRecruiting": "Requisitions: opened, filled, days to fill. SIMULATED.",
    "DimDate": "Calendar Nov 2024 - Oct 2026 with Lithuanian public holidays, working days and the timesheet cut-off flag.",
    "DimEmployee": "SCD2 employee history, ids only (no names). SIMULATED.",
    "DimOrg": "Cost centre = department x site. Security (RLS) is applied here.",
    "DimGrade": "Grades G1-G5.",
    "Market": "PUBLIC DATA: Eurostat labour cost index and job vacancy rate (ICT, NACE J), ICT specialists share; Statistics Lithuania average earnings.",
}

# ------------------------------------------------------------------ measures: (folder, name, format, description, DAX)
SNAP = "REMOVEFILTERS ( DimDate ),\n        DimDate[MonthStart] = _m"
M = [
    ("1 Headcount", "Headcount", "#,0", "People employed on the last day of the last month in context. Duplicate ids excluded.",
     f"VAR _m = MAX ( DimDate[MonthStart] )\nRETURN\n    CALCULATE (\n        COUNTROWS ( FactHeadcountMonthly ),\n        FactHeadcountMonthly[IsActiveMonthEnd] = 1,\n        FactHeadcountMonthly[IsDuplicateId] = 0,\n        {SNAP}\n    )"),
    ("1 Headcount", "Headcount (raw HRIS)", "#,0", "Same as Headcount but counting every id in the HRIS, duplicates included. Data-quality view only.",
     f"VAR _m = MAX ( DimDate[MonthStart] )\nRETURN\n    CALCULATE (\n        COUNTROWS ( FactHeadcountMonthly ),\n        FactHeadcountMonthly[IsActiveMonthEnd] = 1,\n        {SNAP}\n    )"),
    ("1 Headcount", "Duplicate IDs", "#,0", "Ids created twice by the HRIS migration (Sep 2025) still active at month end.",
     "[Headcount (raw HRIS)] - [Headcount]"),
    ("1 Headcount", "FTE", "#,0.0", "Contracted full-time equivalents at the end of the last month in context.",
     f"VAR _m = MAX ( DimDate[MonthStart] )\nRETURN\n    CALCULATE (\n        SUM ( FactHeadcountMonthly[FTE] ),\n        FactHeadcountMonthly[IsActiveMonthEnd] = 1,\n        FactHeadcountMonthly[IsDuplicateId] = 0,\n        {SNAP}\n    )"),
    ("1 Headcount", "Average Headcount", "#,0.0", "Average of month-end headcounts over the months in context. Denominator of every attrition rate.",
     "AVERAGEX ( VALUES ( DimDate[MonthStart] ), [Headcount] )"),
    ("2 Attrition", "Exits (gross)", "#,0", "Every exit keyed in the HRIS, including internal moves keyed as exit + rehire.",
     'CALCULATE ( COUNTROWS ( FactMovements ), FactMovements[MovementType] = "Exit" )'),
    ("2 Attrition", "Exits (excl. transfers)", "#,0", "Exits minus internal transfers (an exit followed by a rehire of the same id within 31 days).",
     "CALCULATE ( [Exits (gross)], FactMovements[IsInternalTransfer] = 0 )"),
    ("2 Attrition", "Voluntary Exits", "#,0", "Resignations (excl. transfers).",
     "CALCULATE ( [Exits (excl. transfers)], FactMovements[IsVoluntary] = 1 )"),
    ("2 Attrition", "Regretted Exits", "#,0", "Resignations the manager flagged as regretted (high performers or scarce skills).",
     "CALCULATE ( [Voluntary Exits], FactMovements[IsRegretted] = 1 )"),
    ("2 Attrition", "Exits Under 12 Months Tenure", "#,0", "Exits (excl. transfers) of people with less than 12 months of service.",
     "CALCULATE ( [Exits (excl. transfers)], FactMovements[TenureMonths] < 12 )"),
    ("2 Attrition", "Hires", "#,0", "External hires (rehires that close an internal transfer are excluded).",
     'CALCULATE ( COUNTROWS ( FactMovements ), FactMovements[MovementType] = "Hire", FactMovements[IsInternalTransfer] = 0 )'),
    ("2 Attrition", "Attrition % (gross)", "0.0%", "Gross exits / average headcount. Shown for comparison only: inflated by transfers.",
     "DIVIDE ( [Exits (gross)], [Average Headcount] )"),
    ("2 Attrition", "Attrition % (excl. transfers)", "0.0%", "Exits excl. transfers / average headcount.",
     "DIVIDE ( [Exits (excl. transfers)], [Average Headcount] )"),
    ("2 Attrition", "Voluntary Attrition %", "0.0%", "Resignations / average headcount.",
     "DIVIDE ( [Voluntary Exits], [Average Headcount] )"),
    ("2 Attrition", "Regretted Attrition %", "0.0%", "Regretted resignations / average headcount. Headline KPI agreed with the HR Director.",
     "DIVIDE ( [Regretted Exits], [Average Headcount] )"),
    ("2 Attrition", "Early Attrition %", "0.0%", "Exits with less than 12 months of service / hires in the same period.",
     "DIVIDE ( [Exits Under 12 Months Tenure], [Hires] )"),
    ("2 Attrition", "Regretted Attrition % R12M", "0.0%", "Regretted attrition over the 12 months ending with the last date in context.",
     "VAR _end = MAX ( DimDate[Date] )\nRETURN\n    CALCULATE ( [Regretted Attrition %], DATESINPERIOD ( DimDate[Date], _end, -12, MONTH ) )"),
    ("2 Attrition", "Voluntary Attrition % R12M", "0.0%", "Voluntary attrition over the 12 months ending with the last date in context.",
     "VAR _end = MAX ( DimDate[Date] )\nRETURN\n    CALCULATE ( [Voluntary Attrition %], DATESINPERIOD ( DimDate[Date], _end, -12, MONTH ) )"),
    ("2 Attrition", "Attrition % (gross) R12M", "0.0%", "Gross attrition over the 12 months ending with the last date in context.",
     "VAR _end = MAX ( DimDate[Date] )\nRETURN\n    CALCULATE ( [Attrition % (gross)], DATESINPERIOD ( DimDate[Date], _end, -12, MONTH ) )"),
    ("2 Attrition", "Attrition % (excl. transfers) R12M", "0.0%", "Attrition excl. transfers over the 12 months ending with the last date in context.",
     "VAR _end = MAX ( DimDate[Date] )\nRETURN\n    CALCULATE ( [Attrition % (excl. transfers)], DATESINPERIOD ( DimDate[Date], _end, -12, MONTH ) )"),
    ("2 Attrition", "Regretted Exits LY", "#,0", "Regretted exits in the same period one year earlier.",
     "CALCULATE ( [Regretted Exits], SAMEPERIODLASTYEAR ( DimDate[Date] ) )"),
    ("3 Utilization", "Capacity Hours", "#,0", "Lithuanian working days employed x 8 h x FTE, minus absences. Billable departments only.",
     "CALCULATE (\n    SUM ( FactHeadcountMonthly[CapacityHours] ),\n    FactHeadcountMonthly[IsDuplicateId] = 0,\n    DimOrg[IsBillable] = 1\n)"),
    ("3 Utilization", "Billable Hours", "#,0", "Billable hours received in timesheets (billable departments).",
     "CALCULATE ( SUM ( FactTimesheet[BillableHours] ), DimOrg[IsBillable] = 1 )"),
    ("3 Utilization", "Bench Hours", "#,0", "Hours logged without a client project (billable departments).",
     "CALCULATE ( SUM ( FactTimesheet[BenchHours] ), DimOrg[IsBillable] = 1 )"),
    ("3 Utilization", "Overtime Hours", "#,0", "Hours above contracted capacity (billable departments).",
     "CALCULATE ( SUM ( FactTimesheet[OvertimeHours] ), DimOrg[IsBillable] = 1 )"),
    ("3 Utilization", "Logged Hours", "#,0", "Billable + non-billable + bench hours received (billable departments).",
     "CALCULATE ( SUM ( FactTimesheet[LoggedHours] ), DimOrg[IsBillable] = 1 )"),
    ("3 Utilization", "Utilization %", "0.0%", "Billable hours / capacity. Not reliable for a month that is not closed: use the closed-months version.",
     "DIVIDE ( [Billable Hours], [Capacity Hours] )"),
    ("3 Utilization", "Utilization % (closed months)", "0.0%", "Utilisation on closed months only (month end + 10 days <= extract date). Blank for the open month.",
     "CALCULATE ( [Utilization %], KEEPFILTERS ( DimDate[IsClosedMonth] = 1 ) )"),
    ("3 Utilization", "Bench %", "0.0%", "Bench hours / capacity.", "DIVIDE ( [Bench Hours], [Capacity Hours] )"),
    ("3 Utilization", "Overtime %", "0.0%", "Overtime hours / capacity. Alert threshold: 15% for two months in a row.",
     "DIVIDE ( [Overtime Hours], [Capacity Hours] )"),
    ("3 Utilization", "Timesheet Completeness %", "0.0%", "Logged hours / capacity: shows how much of the month has been received.",
     "DIVIDE ( [Logged Hours], [Capacity Hours] )"),
    ("4 Pay & market", "Average Gross Salary", "€#,0", "Average contracted monthly gross salary (full-time basis) at the end of the last month in context.",
     f"VAR _m = MAX ( DimDate[MonthStart] )\nRETURN\n    CALCULATE (\n        AVERAGE ( FactHeadcountMonthly[SalaryMonthlyGross] ),\n        FactHeadcountMonthly[IsActiveMonthEnd] = 1,\n        FactHeadcountMonthly[IsDuplicateId] = 0,\n        {SNAP}\n    )"),
    ("4 Pay & market", "Median Salary New Hires", "€#,0", "Median salary of people with < 1 year of service (use with a grade in context).",
     f'VAR _m = MAX ( DimDate[MonthStart] )\nRETURN\n    CALCULATE (\n        MEDIAN ( FactHeadcountMonthly[SalaryMonthlyGross] ),\n        FactHeadcountMonthly[TenureBand] = "0-1 y",\n        FactHeadcountMonthly[IsActiveMonthEnd] = 1,\n        FactHeadcountMonthly[IsDuplicateId] = 0,\n        {SNAP}\n    )'),
    ("4 Pay & market", "Median Salary 2-4 Years", "€#,0", "Median salary of people with 2 to 4 years of service (use with a grade in context).",
     f'VAR _m = MAX ( DimDate[MonthStart] )\nRETURN\n    CALCULATE (\n        MEDIAN ( FactHeadcountMonthly[SalaryMonthlyGross] ),\n        FactHeadcountMonthly[TenureBand] = "2-4 y",\n        FactHeadcountMonthly[IsActiveMonthEnd] = 1,\n        FactHeadcountMonthly[IsDuplicateId] = 0,\n        {SNAP}\n    )'),
    ("4 Pay & market", "New-Hire Pay Premium %", "0.0%", "How much more new hires earn than 2-4 year colleagues of the same grade (pay compression).",
     "DIVIDE ( [Median Salary New Hires], [Median Salary 2-4 Years] ) - 1"),
    ("4 Pay & market", "Market ICT Avg Gross", "€#,0", "PUBLIC DATA. Statistics Lithuania average monthly gross earnings, ICT (J58-J63), latest quarter published up to the quarter in context.",
     "VAR _q = MAX ( DimDate[Quarter] )\nRETURN\n    CALCULATE (\n        LASTNONBLANKVALUE ( Market[Quarter], MAX ( Market[AvgGrossEarningsICT_LT] ) ),\n        Market[Quarter] <= _q\n    )"),
    ("4 Pay & market", "Salary vs Market %", "+0.0%;-0.0%;0.0%", "Company average gross salary vs the Lithuanian ICT average (negative = below market).",
     "DIVIDE ( [Average Gross Salary], [Market ICT Avg Gross] ) - 1"),
    ("4 Pay & market", "Labour Cost Index ICT", "0.0", "PUBLIC DATA. Eurostat labour cost index, wages and salaries, ICT sector, Lithuania (2024-Q4 = 100).",
     "VAR _q = SELECTEDVALUE ( DimDate[Quarter], MAX ( DimDate[Quarter] ) )\nRETURN\n    CALCULATE ( MAX ( Market[LabourCostIndexICT_2024Q4_100] ), TREATAS ( { _q }, Market[Quarter] ) )"),
    ("5 Recruiting", "Median Days to Fill", "#,0", "Median days from requisition opened to offer accepted (by date filled).",
     'CALCULATE ( MEDIAN ( FactRecruiting[DaysToFill] ), FactRecruiting[Status] = "Filled" )'),
    ("5 Recruiting", "Open Requisitions", "#,0", "Requisitions still open at the extract date.",
     'CALCULATE ( COUNTROWS ( FactRecruiting ), FactRecruiting[Status] = "Open", REMOVEFILTERS ( DimDate ) )'),
    ("5 Recruiting", "Requisitions Opened", "#,0", "Requisitions opened in the period (inactive relationship on OpenedDate).",
     "CALCULATE ( COUNTROWS ( FactRecruiting ), USERELATIONSHIP ( FactRecruiting[OpenedDate], DimDate[Date] ) )"),
    ("6 Finance & reconciliation", "Revenue", "€#,0", "Revenue by cost centre (HR cost-centre master applied).", "SUM ( FactFinance[Revenue] )"),
    ("6 Finance & reconciliation", "Total Cost", "€#,0", "Payroll cost + other cost.", "SUM ( FactFinance[PayrollCost] ) + SUM ( FactFinance[OtherCost] )"),
    ("6 Finance & reconciliation", "Revenue per FTE", "€#,0", "Average monthly revenue per FTE over the months in context.",
     "DIVIDE ( [Revenue], SUMX ( VALUES ( DimDate[MonthStart] ), [FTE] ) )"),
    ("6 Finance & reconciliation", "Cost per FTE", "€#,0", "Average monthly cost per FTE over the months in context.",
     "DIVIDE ( [Total Cost], SUMX ( VALUES ( DimDate[MonthStart] ), [FTE] ) )"),
    ("6 Finance & reconciliation", "Revenue (as reported by finance)", "€#,0", "Revenue by the department written in the finance export (before the cost-centre fix).",
     "VAR _depts = VALUES ( DimOrg[Department] )\nRETURN\n    CALCULATE (\n        SUM ( FactFinance[Revenue] ),\n        REMOVEFILTERS ( DimOrg ),\n        TREATAS ( _depts, FactFinance[DepartmentReported] )\n    )"),
    ("6 Finance & reconciliation", "Revenue per FTE (as reported)", "€#,0", "Revenue per FTE using the finance department mapping: shows the mis-mapped cost centre.",
     "DIVIDE ( [Revenue (as reported by finance)], SUMX ( VALUES ( DimDate[MonthStart] ), [FTE] ) )"),
    ("6 Finance & reconciliation", "Finance Headcount", "#,0", "People paid in the last month in context (finance export).",
     "VAR _m = MAX ( DimDate[MonthStart] )\nRETURN\n    CALCULATE ( SUM ( FactFinance[PayrollHeadcount] ), REMOVEFILTERS ( DimDate ), DimDate[MonthStart] = _m )"),
    ("6 Finance & reconciliation", "HR vs Finance Gap", "+#,0;-#,0;0", "Finance headcount minus raw HRIS headcount. Explained by duplicate ids and leavers paid in their last month.",
     "IF ( NOT ISBLANK ( [Finance Headcount] ), [Finance Headcount] - [Headcount (raw HRIS)] )"),
    ("7 Data quality", "Late Timesheets %", "0.0%", "Share of timesheet rows entered more than 10 days after month end.",
     "DIVIDE ( CALCULATE ( COUNTROWS ( FactTimesheet ), FactTimesheet[EntryLagDays] > 10 ), COUNTROWS ( FactTimesheet ) )"),
    ("7 Data quality", "Month Status", "", "Closed or provisional (timesheet cut-off rule).",
     'IF ( MIN ( DimDate[IsClosedMonth] ) = 1, "Closed", "Provisional: timesheets still arriving" )'),
]


def qn(name):
    return name if name.replace("_", "").isalnum() else "'" + name.replace("'", "''") + "'"


def indent(text, n):
    return "\n".join("\t" * n + line if line else line for line in text.split("\n"))


def col_type(series, name):
    if name in DATE_COLS:
        return "dateTime", "type date"
    if pd.api.types.is_integer_dtype(series):
        return "int64", "Int64.Type"
    if pd.api.types.is_float_dtype(series):
        return "double", "type number"
    return "string", "type text"


def table_tmdl(name):
    df = pd.read_csv(MODEL_CSV / f"{name}.csv", nrows=5000)
    cols = [(c, *col_type(df[c], c)) for c in df.columns]
    extra = EXTRA_STEPS.get(name)
    lines = [f"/// {TABLE_DESC[name]}", f"table {name}", f"\tlineageTag: {tag(name)}"]
    if name == "DimDate":
        lines.append("\tdataCategory: Time")
    lines.append("")
    all_cols = [(c, t) for c, t, _ in cols] + ([(c, t) for c, t in extra[2]] if extra else [])
    for c, t in all_cols:
        lines.append(f"\tcolumn {qn(c)}")
        lines.append(f"\t\tdataType: {t}")
        if name == "DimDate" and c == "Date":
            lines.append("\t\tisKey")
        if c in HIDDEN.get(name, set()):
            lines.append("\t\tisHidden")
        if t == "dateTime":
            lines.append("\t\tformatString: yyyy-mm-dd")
        elif c in FORMAT:
            lines.append(f"\t\tformatString: {FORMAT[c]}")
        lines.append(f"\t\tlineageTag: {tag(name, c)}")
        lines.append("\t\tsummarizeBy: none")
        lines.append(f"\t\tsourceColumn: {c}")
        if (name, c) in SORT_BY:
            lines.append(f"\t\tsortByColumn: {SORT_BY[(name, c)]}")
        if t == "dateTime":
            lines += ["", "\t\tannotation UnderlyingDateTimeDataType = Date"]
        lines.append("")
    types = ", ".join(f'{{"{c}", {m}}}' for c, _, m in cols)
    steps = [f'Source = Csv.Document(File.Contents(DataFolder & "{name}.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
             "Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),",
             f'Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")']
    last = "Typed"
    if extra:
        steps[-1] += ","
        steps.append(extra[0])
        last = extra[1]
    lines += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet"]
    lines += ["\t\t\t\t\t" + s for s in steps]
    lines += ["\t\t\t\tin", f"\t\t\t\t\t{last}", ""]
    return "\n".join(lines)


def security_tmdl():
    rows = [("head.delivery1@company.example", "Delivery 1"), ("head.delivery2@company.example", "Delivery 2"),
            ("head.delivery3@company.example", "Delivery 3"), ("head.datacloud@company.example", "Data & Cloud"),
            ("head.sales@company.example", "Sales"), ("head.support@company.example", "Support functions")]
    body = ", ".join(f'{{"{u}", "{d}"}}' for u, d in rows)
    return "\n".join([
        "/// RLS mapping: user principal name -> department (placeholder accounts, replace with the real Entra ID group or users).",
        "table SecurityUserDepartment", "\tisHidden", f"\tlineageTag: {tag('sec')}", "",
        "\tcolumn UserPrincipalName", "\t\tdataType: string", "\t\tisHidden", f"\t\tlineageTag: {tag('sec', 'upn')}",
        "\t\tsummarizeBy: none", "\t\tsourceColumn: UserPrincipalName", "",
        "\tcolumn Department", "\t\tdataType: string", "\t\tisHidden", f"\t\tlineageTag: {tag('sec', 'dept')}",
        "\t\tsummarizeBy: none", "\t\tsourceColumn: Department", "",
        "\tpartition SecurityUserDepartment = m", "\t\tmode: import",
        f"\t\tsource = #table(type table [UserPrincipalName = text, Department = text], {{{body}}})", ""])


def measures_tmdl():
    lines = ["/// All measures, grouped in display folders. Reference values: docs/KPI_CHECKS.md.",
             "table _Measures", f"\tlineageTag: {tag('_Measures')}", ""]
    for folder, name, fmt, desc, dax in M:
        lines.append(f"\t/// {desc}")
        if "\n" in dax:
            lines.append(f"\tmeasure {qn(name)} =")
            lines.append(indent(dax, 3))
        else:
            lines.append(f"\tmeasure {qn(name)} = {dax}")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines.append(f"\t\tdisplayFolder: {folder}")
        lines.append(f"\t\tlineageTag: {tag('m', name)}")
        lines.append("")
    lines += ["\tpartition _Measures = m", "\t\tmode: import",
              '\t\tsource = #table(type table [Measures = text], {})', "",
              "\tcolumn Measures", "\t\tdataType: string", "\t\tisHidden", f"\t\tlineageTag: {tag('_Measures', 'col')}",
              "\t\tsummarizeBy: none", "\t\tsourceColumn: Measures", ""]
    return "\n".join(lines)


RELS = [  # (from table.column, to table.column, active)
    ("FactHeadcountMonthly.MonthStart", "DimDate.Date", True), ("FactHeadcountMonthly.CostCenter", "DimOrg.CostCenter", True),
    ("FactHeadcountMonthly.Grade", "DimGrade.Grade", True), ("FactHeadcountMonthly.EmployeeKey", "DimEmployee.EmployeeKey", True),
    ("FactMovements.Date", "DimDate.Date", True), ("FactMovements.CostCenter", "DimOrg.CostCenter", True),
    ("FactMovements.Grade", "DimGrade.Grade", True), ("FactMovements.EmployeeKey", "DimEmployee.EmployeeKey", True),
    ("FactTimesheet.MonthStart", "DimDate.Date", True), ("FactTimesheet.CostCenter", "DimOrg.CostCenter", True),
    ("FactTimesheet.Grade", "DimGrade.Grade", True), ("FactTimesheet.EmployeeKey", "DimEmployee.EmployeeKey", True),
    ("FactFinance.MonthStart", "DimDate.Date", True), ("FactFinance.CostCenter", "DimOrg.CostCenter", True),
    ("FactRecruiting.FilledDate", "DimDate.Date", True), ("FactRecruiting.OpenedDate", "DimDate.Date", False),
    ("FactRecruiting.CostCenter", "DimOrg.CostCenter", True), ("FactRecruiting.Grade", "DimGrade.Grade", True),
]
TABLES = ["FactHeadcountMonthly", "FactMovements", "FactTimesheet", "FactFinance", "FactRecruiting",
          "DimDate", "DimEmployee", "DimOrg", "DimGrade", "Market"]


def write_model():
    if DEF.exists():
        shutil.rmtree(DEF)
    (DEF / "tables").mkdir(parents=True)
    (DEF / "roles").mkdir()
    (SM / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": "CentricWorkforce"},
        "config": {"version": "2.0", "logicalId": tag("logical", "sm")}}, indent=2), encoding="utf-8")
    (SM / "definition.pbism").write_text(json.dumps({"version": "4.2", "settings": {}}, indent=2), encoding="utf-8")
    (DEF / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1606\n\n", encoding="utf-8")
    order = TABLES + ["SecurityUserDepartment", "_Measures"]
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3", "\tsourceQueryCulture: en-US",
             "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
             "annotation __PBI_TimeIntelligenceEnabled = 0", "",
             f"annotation PBI_QueryOrder = {json.dumps(['DataFolder'] + order)}", ""]
    model += [f"ref table {qn(t)}" for t in order]
    (DEF / "model.tmdl").write_text("\n".join(model) + "\n", encoding="utf-8")
    (DEF / "expressions.tmdl").write_text(
        f'/// Folder holding the model CSV files (data/model). Change it if the repository is not in C:\\case-study-centric.\n'
        f'expression DataFolder = "{DATA_FOLDER}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {tag('DataFolder')}\n\n\tannotation PBI_ResultType = Text\n", encoding="utf-8")
    rel = []
    for i, (f, t, active) in enumerate(RELS, 1):
        rel.append(f"relationship {tag('rel', f, t)}")
        if not active:
            rel.append("\tisActive: false")
        rel += [f"\tfromColumn: {f}", f"\ttoColumn: {t}", ""]
    (DEF / "relationships.tmdl").write_text("\n".join(rel), encoding="utf-8")
    for t in TABLES:
        (DEF / "tables" / f"{t}.tmdl").write_text(table_tmdl(t), encoding="utf-8")
    (DEF / "tables" / "SecurityUserDepartment.tmdl").write_text(security_tmdl(), encoding="utf-8")
    (DEF / "tables" / "_Measures.tmdl").write_text(measures_tmdl(), encoding="utf-8")
    lookup = "LOOKUPVALUE ( SecurityUserDepartment[Department], SecurityUserDepartment[UserPrincipalName], USERPRINCIPALNAME () )"
    (DEF / "roles" / "DepartmentManager.tmdl").write_text("\n".join([
        "/// A department head sees only their own department (all sites). Test it with View as > DepartmentManager + Other user.",
        "role DepartmentManager", "\tmodelPermission: read", "",
        f"\ttablePermission DimOrg = DimOrg[Department] = {lookup}", "",
        f"\ttablePermission DimEmployee = DimEmployee[Department] = {lookup}", "",
        f"\tannotation PBI_Id = {tag('role').replace('-', '')}", ""]), encoding="utf-8")


def write_dax():
    out = ["// Centric workforce analytics case study - all DAX measures (table _Measures).",
           "// SIMULATED data. Reference values for checking: docs/KPI_CHECKS.md.", ""]
    for folder, name, fmt, desc, dax in M:
        out += [f"// [{folder}] {desc}" + (f"  Format: {fmt}" if fmt else ""), f"{name} =", indent(dax, 1).replace("\t", "    "), ""]
    (PBI / "measures.dax").write_text("\n".join(out), encoding="utf-8")


def write_report_shell():
    (RP / "definition").mkdir(parents=True, exist_ok=True)
    (RP / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": "CentricWorkforce"},
        "config": {"version": "2.0", "logicalId": tag("logical", "rp")}}, indent=2), encoding="utf-8")
    (RP / "definition.pbir").write_text(json.dumps({"version": "4.0", "datasetReference": {"byPath": {"path": "../CentricWorkforce.SemanticModel"}}}, indent=2), encoding="utf-8")
    (RP / "definition" / "version.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0"}, indent=2), encoding="utf-8")
    theme = {"name": "Case Study Light", "dataColors": ["#2A78D6", "#EB6834", "#1BAF7A", "#EDA100", "#E87BA4", "#7A5BD6", "#A3A19A"],
             "background": "#FFFFFF", "foreground": "#0B0B0B", "tableAccent": "#2A78D6",
             "textClasses": {"label": {"fontFace": "Segoe UI", "fontSize": 10, "color": "#52514E"},
                             "title": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": "#0B0B0B"}},
             "visualStyles": {"page": {"*": {"background": [{"color": {"solid": {"color": "#F4F4F2"}}, "transparency": 0}]}},
                              "*": {"*": {"background": [{"color": {"solid": {"color": "#FFFFFF"}}, "transparency": 0}],
                                          "border": [{"show": True, "color": {"solid": {"color": "#E1E0D9"}}, "radius": 8}]}}}}
    res = RP / "StaticResources"
    (res / "RegisteredResources").mkdir(parents=True, exist_ok=True)
    (res / "RegisteredResources" / "CaseStudy_Light.json").write_text(json.dumps(theme, indent=2), encoding="utf-8")
    base_src = Path(r"C:\rovio-case-study\powerbi\RovioCaseStudy.Report\StaticResources\SharedResources\BaseThemes\Fluent2-CY26SU10.json")
    base_dst = res / "SharedResources" / "BaseThemes" / base_src.name
    if base_src.exists() and not base_dst.exists():
        base_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(base_src, base_dst)
    report = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
              "themeCollection": {
                  "baseTheme": {"name": "Fluent2-CY26SU10", "reportVersionAtImport": {"visual": "2.14.0", "report": "3.4.0", "page": "2.3.1"}, "type": "SharedResources"},
                  "customTheme": {"name": "CaseStudy_Light.json", "reportVersionAtImport": {"visual": "2.14.0", "report": "3.4.0", "page": "2.3.1"}, "type": "RegisteredResources"}},
              "objects": {"section": [{"properties": {"verticalAlignment": {"expr": {"Literal": {"Value": "'Top'"}}}}}]},
              "resourcePackages": [
                  {"name": "SharedResources", "type": "SharedResources", "items": [{"name": "Fluent2-CY26SU10", "path": "BaseThemes/Fluent2-CY26SU10.json", "type": "BaseTheme"}]},
                  {"name": "RegisteredResources", "type": "RegisteredResources", "items": [{"name": "CaseStudy_Light.json", "path": "CaseStudy_Light.json", "type": "CustomTheme"}]}],
              "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized", "defaultDrillFilterOtherVisuals": True,
                           "allowChangeFilterTypes": True, "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True}}
    (RP / "definition" / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (PBI / "CentricWorkforce.pbip").write_text(json.dumps({"version": "1.0", "artifacts": [{"report": {"path": "CentricWorkforce.Report"}}],
                                                         "settings": {"enableAutoRecovery": True}}, indent=2), encoding="utf-8")


def main():
    write_model()
    write_dax()
    write_report_shell()
    print(f"PBIP written: {len(TABLES) + 2} tables, {len(M)} measures, {len(RELS)} relationships, 1 role")


if __name__ == "__main__":
    main()
