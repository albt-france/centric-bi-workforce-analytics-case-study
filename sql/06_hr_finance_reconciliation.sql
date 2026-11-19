-- 06 · HR vs finance reconciliation, and revenue / cost per FTE (closed finance months only).
-- Finance counts people paid during the month by cost centre; HR counts ids active on the last day of the month.
-- Bridge (cascade):  HR raw month-end headcount
--                  - duplicate ids (HRIS migration)
--                  + leavers paid in the month but gone at month end
--                  = finance payroll headcount;   residual must be 0.

CREATE OR REPLACE TABLE out_recon_bridge AS
WITH hr AS (
    SELECT month_start,
           count(*) FILTER (WHERE is_active_month_end)                                 AS hr_raw_month_end,
           count(*) FILTER (WHERE is_active_month_end AND is_duplicate_id)             AS duplicate_ids,
           count(*) FILTER (WHERE NOT is_active_month_end AND NOT is_duplicate_id)     AS leavers_in_month
    FROM hc_monthly GROUP BY 1
), fin AS (SELECT month AS month_start, sum(payroll_headcount) AS finance_headcount FROM finance_monthly GROUP BY 1)
SELECT hr.month_start, hr.hr_raw_month_end, -hr.duplicate_ids AS less_duplicate_ids, hr.leavers_in_month AS plus_leavers_in_month,
       fin.finance_headcount,
       fin.finance_headcount - (hr.hr_raw_month_end - hr.duplicate_ids + hr.leavers_in_month) AS residual
FROM hr JOIN fin USING (month_start) ORDER BY 1;

-- By department: HR (people paid in the month, master ids) vs finance as exported (department_reported).
CREATE OR REPLACE TABLE out_recon_department AS
WITH hr AS (
    SELECT month_start, department, count(*) AS hr_paid FROM hc_monthly WHERE NOT is_duplicate_id GROUP BY ALL
), fin AS (
    SELECT month AS month_start, department_reported AS department, sum(payroll_headcount) AS finance_paid
    FROM finance_monthly GROUP BY ALL
)
SELECT month_start, department, hr_paid, coalesce(finance_paid, 0) AS finance_paid, coalesce(finance_paid, 0) - hr_paid AS gap
FROM hr JOIN fin USING (month_start, department) ORDER BY ALL;

-- Which cost centre causes a gap: finance department vs the HR cost-centre master.
CREATE OR REPLACE TABLE out_recon_cost_center AS
SELECT f.month AS month_start, f.cost_center, cm.department AS department_master, f.department_reported, f.payroll_headcount, f.revenue_eur
FROM finance_monthly f JOIN cost_center_map cm USING (cost_center)
WHERE f.department_reported <> cm.department ORDER BY ALL;

-- Revenue and cost per FTE by department: as exported vs with the cost-centre master applied.
CREATE OR REPLACE TABLE out_revenue_per_fte AS
WITH fte AS (
    SELECT month_start, department, sum(fte) AS fte FROM hc_monthly WHERE is_active_month_end AND NOT is_duplicate_id GROUP BY ALL
), rep AS (
    SELECT month AS month_start, department_reported AS department, sum(revenue_eur) AS revenue_reported FROM finance_monthly GROUP BY ALL
), fixd AS (
    SELECT f.month AS month_start, cm.department, sum(f.revenue_eur) AS revenue_fixed,
           sum(f.payroll_cost_eur + f.other_cost_eur) AS cost_fixed
    FROM finance_monthly f JOIN cost_center_map cm USING (cost_center) GROUP BY ALL
)
SELECT fte.month_start, fte.department, round(fte.fte, 1) AS fte,
       round(coalesce(rep.revenue_reported, 0) / fte.fte, 0) AS revenue_per_fte_reported,
       round(fixd.revenue_fixed / fte.fte, 0) AS revenue_per_fte_fixed,
       round(fixd.cost_fixed / fte.fte, 0) AS cost_per_fte
FROM fte JOIN fixd USING (month_start, department) LEFT JOIN rep USING (month_start, department)
ORDER BY ALL;
