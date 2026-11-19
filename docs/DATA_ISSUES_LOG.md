# Data issues log

> Fictional company, SIMULATED extracts (`data/sim/`), extract date 6 Nov 2026. Checks: `sql/01_data_quality.sql` and
> `sql/06_hr_finance_reconciliation.sql`. Status as at the end of the case study.

| ID | Issue | Evidence | Impact | Fix | Status |
|---|---|---|---|---|---|
| DI-01 | **Duplicate employee ids** after the HRIS migration | 18 ids share coded birth date + hire date with an older id; all first seen on 1 Sep 2025; none logs time. | Raw headcount +18 (+3%) from Sep 2025; HR never matched payroll. | Flag `is_duplicate_id`, map to `master_id`; KPIs count master ids only. HRIS owner to merge the records. | Fixed in the model; **open** in the HRIS. |
| DI-02 | **Overlapping SCD2 periods** | 5 legacy rows end on 4 Sep 2025 while the new HRIS row starts on 1 Sep. | Up to 4 days double-counted; wrong attributes on those days. | Cut the older row the day before the next row starts (`emp_clean`). | Fixed in the model. |
| DI-03 | **Missing manager id** | 9 legacy rows. | Manager-level views incomplete. | Shown as "Unassigned"; HR to complete. | Open (low). |
| DI-04 | **Missing site** | 4 legacy rows. | Site filters drop those rows. | Site taken from the cost centre (`cost_center_map`). | Fixed in the model. |
| DI-05 | **Reorganisation keyed as exit + rehire** | Delivery 2: 50 exits on 31 Mar 2026, the same 50 ids rehired on 1 Apr, reason "Reorganisation". | Gross turnover spikes to 10% in March (company), 41% in Delivery 2: a **false signal**. | Transfer rule (exit + rehire within 31 days); HR to key reorganisations as transfers. | Fixed in the model; process change agreed. |
| DI-06 | **Late timesheets / open month** | Timesheets entered up to 10 days after month end (252 rows later than 10 days over the period). At the 6 Nov extract, October is 67% logged. | October utilisation reads 60% instead of about 78%. | Cut-off rule: `IsClosedMonth`; open month blank in KPIs and labelled "provisional". | Fixed (rule). |
| DI-07 | **Cost centre mis-mapped in the finance export** | CC-D1-VNO (Delivery 1, Vilnius) reported under Data & Cloud from May to July 2026 (89-91 people). | Data & Cloud revenue per FTE +62%, Delivery 1 -57%; department headcounts off by about 90. | Use the HR cost-centre master in the model; keep `DepartmentReported` for the audit view; finance to fix the export. | Fixed in the model; **open** in finance. |
| DI-08 | **HR vs finance headcount gap** | Finance (people paid) − HR raw month end = −11 in Sep 2026. | Two "official" headcounts. | Bridge: HR raw − duplicate ids + leavers paid in their last month = finance; residual 0 every closed month. | Explained; monthly check. |
| DI-09 | **Finance months not closed** | Finance export stops at Sep 2026. | October revenue and cost per FTE not available. | `IsFinanceClosedMonth`; finance measures blank for October. | By design. |
| DI-10 | **Public data lag** (PUBLIC DATA) | Statistics Lithuania earnings to 2025-Q4; Eurostat job vacancy rate to 2025-Q4. | Market comparison lags the company data by up to three quarters. | `LASTNONBLANKVALUE`: latest published quarter, labelled with its date. | By design. |
