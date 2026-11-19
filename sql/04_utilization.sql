-- 04 · Utilisation, bench and overtime (billable departments).
-- Capacity comes from HR (Lithuanian working days x 8 h x FTE - absences); hours come from timesheets.
-- Utilisation = billable hours / capacity. Bench % = bench hours / capacity. Overtime % = overtime hours / capacity.
-- Cut-off rule: a month is reported only when month end + 10 days <= extract date (months.is_closed).

CREATE OR REPLACE TABLE ts_clean AS
SELECT t.*, h.department, h.site, h.cost_center, h.grade, h.employee_key,
       datediff('day', last_day(t.month), t.entered_date) AS lag_days
FROM timesheets t
JOIN hc_monthly h ON h.employee_id = t.employee_id AND h.month_start = t.month;

CREATE OR REPLACE TABLE out_utilization_monthly AS
WITH cap AS (
    SELECT month_start, department, sum(capacity_hours) AS capacity_hours
    FROM hc_monthly WHERE NOT is_duplicate_id GROUP BY ALL
), hrs AS (
    SELECT month AS month_start, department, sum(billable_hours) AS billable, sum(bench_hours) AS bench,
           sum(nonbillable_hours) AS nonbillable, sum(overtime_hours) AS overtime,
           sum(billable_hours + bench_hours + nonbillable_hours) AS logged
    FROM ts_clean GROUP BY ALL
)
SELECT c.month_start, c.department, m.working_days, m.is_closed,
       round(c.capacity_hours, 0) AS capacity_hours, round(h.billable, 0) AS billable_hours, round(h.bench, 0) AS bench_hours,
       round(h.overtime, 0) AS overtime_hours,
       round(h.billable / c.capacity_hours, 4) AS utilization,
       round(h.bench / c.capacity_hours, 4) AS bench_share,
       round(h.overtime / c.capacity_hours, 4) AS overtime_share,
       round(h.logged / c.capacity_hours, 4) AS timesheet_completeness
FROM cap c JOIN hrs h USING (month_start, department) JOIN months m USING (month_start)
ORDER BY ALL;

-- Delivery total (the four billable departments), with and without the cut-off rule.
CREATE OR REPLACE TABLE out_utilization_delivery AS
SELECT month_start, any_value(is_closed) AS is_closed, any_value(working_days) AS working_days,
       round(sum(billable_hours) / sum(capacity_hours), 4) AS utilization_all_months,
       round(CASE WHEN any_value(is_closed) THEN sum(billable_hours) / sum(capacity_hours) END, 4) AS utilization_closed_only,
       round(sum(bench_hours) / sum(capacity_hours), 4) AS bench_share,
       round(sum(billable_hours + bench_hours) / sum(capacity_hours), 4) AS logged_share
FROM out_utilization_monthly WHERE department IN ('Delivery 1', 'Delivery 2', 'Delivery 3', 'Data & Cloud')
GROUP BY 1 ORDER BY 1;
