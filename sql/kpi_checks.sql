-- kpi_checks · Reference value of every KPI in docs/KPI_DICTIONARY.md, computed in SQL independently of DAX.
-- Fixed contexts so that Power BI can be checked by hand:
--   snapshot month  = September 2026 (last month closed for both timesheets and finance)
--   rolling 12 months (R12M) = October 2025 .. September 2026

CREATE OR REPLACE TABLE out_kpi_checks AS
WITH p AS (SELECT DATE '2026-09-01' AS snap, DATE '2025-10-01' AS r_from, DATE '2026-09-30' AS r_to),
hc12 AS (
    SELECT avg(n) AS avg_hc FROM (
        SELECT month_start, count(*) AS n FROM hc_monthly, p
        WHERE is_active_month_end AND NOT is_duplicate_id AND month_start BETWEEN p.r_from AND p.snap GROUP BY 1)
),
dc12 AS (
    SELECT avg(n) AS avg_hc FROM (
        SELECT month_start, count(*) AS n FROM hc_monthly, p
        WHERE is_active_month_end AND NOT is_duplicate_id AND department = 'Data & Cloud' AND month_start BETWEEN p.r_from AND p.snap GROUP BY 1)
),
x12 AS (SELECT exits.* FROM exits, p WHERE date BETWEEN p.r_from AND p.r_to),
hires12 AS (
    SELECT count(*) AS n FROM movements h, p
    WHERE h.movement_type = 'Hire' AND h.date BETWEEN p.r_from AND p.r_to
      AND NOT EXISTS (SELECT 1 FROM exits_all x WHERE x.employee_id = h.employee_id AND x.date BETWEEN h.date - INTERVAL 31 DAY AND h.date)
),
snap AS (SELECT h.* FROM hc_monthly h, p WHERE h.month_start = p.snap),
ts_snap AS (SELECT t.* FROM ts_clean t, p WHERE t.month = p.snap),
billable_depts AS (SELECT unnest(['Delivery 1', 'Delivery 2', 'Delivery 3', 'Data & Cloud']) AS department)
SELECT * FROM (VALUES
  ('Headcount', 'Sep 2026, company', (SELECT count(*) FROM snap WHERE is_active_month_end AND NOT is_duplicate_id)::DOUBLE),
  ('Headcount (raw HRIS)', 'Sep 2026, company', (SELECT count(*) FROM snap WHERE is_active_month_end)::DOUBLE),
  ('FTE', 'Sep 2026, company', (SELECT round(sum(fte), 1) FROM snap WHERE is_active_month_end AND NOT is_duplicate_id)),
  ('Average Headcount', 'R12M to Sep 2026', (SELECT round(avg_hc, 1) FROM hc12)),
  ('Exits (gross)', 'R12M to Sep 2026', (SELECT count(*) FROM x12)::DOUBLE),
  ('Attrition % (gross)', 'R12M to Sep 2026', (SELECT round(count(*) / (SELECT avg_hc FROM hc12), 4) FROM x12)),
  ('Attrition % (excl. transfers)', 'R12M to Sep 2026', (SELECT round(count(*) FILTER (WHERE NOT is_internal_transfer) / (SELECT avg_hc FROM hc12), 4) FROM x12)),
  ('Voluntary Attrition %', 'R12M to Sep 2026', (SELECT round(count(*) FILTER (WHERE exit_type = 'Voluntary' AND NOT is_internal_transfer) / (SELECT avg_hc FROM hc12), 4) FROM x12)),
  ('Regretted Attrition %', 'R12M to Sep 2026', (SELECT round(count(*) FILTER (WHERE exit_type = 'Voluntary' AND regretted) / (SELECT avg_hc FROM hc12), 4) FROM x12)),
  ('Voluntary Attrition %', 'R12M to Sep 2026, Data & Cloud', (SELECT round(count(*) FILTER (WHERE exit_type = 'Voluntary' AND department = 'Data & Cloud') / (SELECT avg_hc FROM dc12), 4) FROM x12)),
  ('Early Attrition % (exits < 12 months / hires)', 'R12M to Sep 2026', (SELECT round(count(*) FILTER (WHERE tenure_months < 12 AND NOT is_internal_transfer) / (SELECT n FROM hires12), 4) FROM x12)),
  ('Hires', 'R12M to Sep 2026', (SELECT n FROM hires12)::DOUBLE),
  ('Utilization %', 'Sep 2026, billable departments',
      (SELECT round((SELECT sum(billable_hours) FROM ts_snap WHERE department IN (SELECT department FROM billable_depts))
                  / sum(capacity_hours), 4) FROM snap WHERE NOT is_duplicate_id AND department IN (SELECT department FROM billable_depts))),
  ('Utilization % (closed months only)', 'Oct 2026, billable departments', NULL),
  ('Utilization % (raw, no cut-off)', 'Oct 2026, billable departments',
      (SELECT utilization_all_months FROM out_utilization_delivery WHERE month_start = DATE '2026-10-01')),
  ('Bench %', 'Sep 2026, Delivery 3', (SELECT bench_share FROM out_utilization_monthly WHERE month_start = DATE '2026-09-01' AND department = 'Delivery 3')),
  ('Overtime %', 'Feb 2026, Data & Cloud', (SELECT overtime_share FROM out_utilization_monthly WHERE month_start = DATE '2026-02-01' AND department = 'Data & Cloud')),
  ('Average Gross Salary', 'Sep 2026, company', (SELECT round(avg(salary_monthly_gross), 0) FROM snap WHERE is_active_month_end AND NOT is_duplicate_id)),
  ('Median Days to Fill', 'filled Oct 2025 - Sep 2026', (SELECT median(datediff('day', opened_date, filled_date)) FROM recruiting, p WHERE status = 'Filled' AND filled_date BETWEEN p.r_from AND p.r_to)),
  ('Finance Headcount', 'Sep 2026, company', (SELECT sum(payroll_headcount) FROM finance_monthly, p WHERE month = p.snap)::DOUBLE),
  ('HR vs Finance Gap (finance - HR raw)', 'Sep 2026, company', (SELECT finance_headcount - hr_raw_month_end FROM out_recon_bridge, p WHERE month_start = p.snap)::DOUBLE),
  ('Revenue per FTE', 'Sep 2026, company', (SELECT round(sum(revenue_eur) / (SELECT sum(fte) FROM snap WHERE is_active_month_end AND NOT is_duplicate_id), 0) FROM finance_monthly, p WHERE month = p.snap))
) t(kpi, context, sql_value);
