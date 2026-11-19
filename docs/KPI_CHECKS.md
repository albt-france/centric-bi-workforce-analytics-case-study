# KPI checks: SQL reference vs model logic

Each KPI of [KPI_DICTIONARY.md](KPI_DICTIONARY.md) is computed twice, independently:

1. **SQL** (`sql/kpi_checks.sql`, DuckDB) on the cleaned source extracts;
2. **model logic**: the filter logic of each DAX measure in `powerbi/measures.dax`, re-applied in pandas to the exact CSV tables that Power BI loads (`data/model/`), by `src/export_model_tables.py`.

The last column is for the value read in Power BI Desktop (card visual with the same filters). Contexts: snapshot = **September 2026** (last month closed for timesheets and finance); R12M = **October 2025 to September 2026**. All data are SIMULATED.

| KPI | DAX measure | Context (filters) | SQL | Model logic | Match | Power BI Desktop |
|---|---|---|---:|---:|:---:|---:|
| Headcount | `[Headcount]` | Sep 2026, company | 603 | 603 | yes | to read |
| Headcount (raw HRIS) | `[Headcount (raw HRIS)]` | Sep 2026, company | 621 | 621 | yes | to read |
| FTE | `[FTE]` | Sep 2026, company | 591.4 | 591.4 | yes | to read |
| Average Headcount | `[Average Headcount]` | R12M Oct 2025 - Sep 2026 | 604.3 | 604.3 | yes | to read |
| Exits (gross) | `[Exits (gross)]` | R12M Oct 2025 - Sep 2026 | 153 | 153 | yes | to read |
| Attrition % (gross) | `[Attrition % (gross)]` | R12M Oct 2025 - Sep 2026 | 25.3% | 25.3% | yes | to read |
| Attrition % (excl. transfers) | `[Attrition % (excl. transfers)]` | R12M Oct 2025 - Sep 2026 | 17.0% | 17.0% | yes | to read |
| Voluntary Attrition % | `[Voluntary Attrition %]` | R12M Oct 2025 - Sep 2026 | 14.1% | 14.1% | yes | to read |
| Regretted Attrition % | `[Regretted Attrition %]` | R12M Oct 2025 - Sep 2026 | 6.8% | 6.8% | yes | to read |
| Voluntary Attrition % | `[Voluntary Attrition %]` | R12M Oct 2025 - Sep 2026, Data & Cloud | 14.5% | 14.5% | yes | to read |
| Early Attrition % (exits < 12 months / hires) | `[Early Attrition %]` | R12M Oct 2025 - Sep 2026 | 30.3% | 30.3% | yes | to read |
| Hires | `[Hires]` | R12M Oct 2025 - Sep 2026 | 109 | 109 | yes | to read |
| Utilization % | `[Utilization %]` | Sep 2026, billable departments | 78.4% | 78.4% | yes | to read |
| Utilization % (closed months only) | `[Utilization % (closed months)]` | Oct 2026, billable departments | blank | blank | yes | to read |
| Utilization % (raw, no cut-off) | `[Utilization %]` | Oct 2026, billable departments | 60.2% | 60.2% | yes | to read |
| Bench % | `[Bench %]` | Sep 2026, Delivery 3 | 17.6% | 17.6% | yes | to read |
| Overtime % | `[Overtime %]` | Feb 2026, Data & Cloud | 18.9% | 18.9% | yes | to read |
| Average Gross Salary | `[Average Gross Salary]` | Sep 2026, company | 3,526 | 3,526 | yes | to read |
| Median Days to Fill | `[Median Days to Fill]` | filled Oct 2025 - Sep 2026 | 32 | 32 | yes | to read |
| Finance Headcount | `[Finance Headcount]` | Sep 2026, company | 610 | 610 | yes | to read |
| HR vs Finance Gap (finance - HR raw) | `[HR vs Finance Gap]` | Sep 2026, company | -11 | -11 | yes | to read |
| Revenue per FTE | `[Revenue per FTE]` | Sep 2026, company | 5,815 | 5,815 | yes | to read |

**22 / 22 KPIs match** between SQL and the model logic.

Notes:
- `Utilization % (closed months)` is blank for October 2026 on purpose: the month is not closed at the extract date (6 Nov 2026), because timesheets arrive up to 10 days after month end. Without the cut-off rule the same month shows a utilisation far below its true level (row *raw, no cut-off*).
- `HR vs Finance Gap` is negative because the HR extract still holds 18 duplicate ids from the HRIS migration, partly offset by leavers that finance pays in their last month; see `sql/06_hr_finance_reconciliation.sql`.
- Status of the Power BI column: **not yet read in Power BI Desktop** (to be filled after opening the PBIP).
