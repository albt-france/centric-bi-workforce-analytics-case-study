-- 03 · Attrition under three definitions, side by side.
--   gross              : every exit keyed in the HRIS
--   excl. transfers    : minus exits followed by a rehire of the same id within 31 days (internal moves keyed as exit + hire)
--   voluntary          : resignations only (excl. transfers)
-- Rate = exits in the period / average month-end headcount of the period (master ids only).

CREATE OR REPLACE TABLE exits AS
SELECT x.movement_id, x.date, date_trunc('month', x.date)::DATE AS month_start, x.employee_id, x.exit_type, x.exit_reason,
       coalesce(x.regretted, FALSE) AS regretted, x.is_internal_transfer,
       e.department, coalesce(e.site, cm.site) AS site, e.grade, e.cost_center, e.hire_date,
       datediff('month', e.hire_date, x.date) AS tenure_months,
       CASE WHEN datediff('month', e.hire_date, x.date) < 12 THEN '0-1 y' WHEN datediff('month', e.hire_date, x.date) < 24 THEN '1-2 y'
            WHEN datediff('month', e.hire_date, x.date) < 48 THEN '2-4 y' ELSE '4+ y' END AS tenure_band
FROM exits_all x
JOIN emp_clean e ON e.employee_id = x.employee_id AND x.date BETWEEN e.valid_from AND e.valid_to
LEFT JOIN cost_center_map cm ON cm.cost_center = e.cost_center;

CREATE OR REPLACE TABLE out_attrition_monthly AS
WITH hc AS (SELECT month_start, department, sum(headcount) AS headcount FROM out_headcount_monthly GROUP BY ALL),
x AS (
    SELECT month_start, department,
           count(*)                                                                        AS exits_gross,
           count(*) FILTER (WHERE NOT is_internal_transfer)                                AS exits_excl_transfers,
           count(*) FILTER (WHERE exit_type = 'Voluntary' AND NOT is_internal_transfer)    AS exits_voluntary,
           count(*) FILTER (WHERE exit_type = 'Voluntary' AND regretted)                   AS exits_regretted,
           count(*) FILTER (WHERE tenure_months < 12 AND NOT is_internal_transfer)         AS exits_under_12m
    FROM exits GROUP BY ALL
)
SELECT hc.month_start, hc.department, hc.headcount,
       coalesce(exits_gross, 0) AS exits_gross, coalesce(exits_excl_transfers, 0) AS exits_excl_transfers,
       coalesce(exits_voluntary, 0) AS exits_voluntary, coalesce(exits_regretted, 0) AS exits_regretted,
       coalesce(exits_under_12m, 0) AS exits_under_12m
FROM hc LEFT JOIN x USING (month_start, department) ORDER BY ALL;

-- Company level, monthly and rolling 12 months (window functions), three definitions.
CREATE OR REPLACE TABLE out_attrition_definitions AS
WITH c AS (
    SELECT month_start, sum(headcount) AS headcount, sum(exits_gross) AS gross, sum(exits_excl_transfers) AS excl_transfers,
           sum(exits_voluntary) AS voluntary, sum(exits_regretted) AS regretted
    FROM out_attrition_monthly GROUP BY 1
)
SELECT month_start, headcount, gross, excl_transfers, voluntary, regretted,
       round(gross / headcount, 4) AS rate_gross_month, round(excl_transfers / headcount, 4) AS rate_excl_transfers_month,
       round(voluntary / headcount, 4) AS rate_voluntary_month,
       count(*) OVER w AS months_in_window,
       round(sum(gross) OVER w / avg(headcount) OVER w, 4)          AS rate_gross_r12m,
       round(sum(excl_transfers) OVER w / avg(headcount) OVER w, 4) AS rate_excl_transfers_r12m,
       round(sum(voluntary) OVER w / avg(headcount) OVER w, 4)      AS rate_voluntary_r12m,
       round(sum(regretted) OVER w / avg(headcount) OVER w, 4)      AS rate_regretted_r12m
FROM c WINDOW w AS (ORDER BY month_start ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
ORDER BY month_start;

-- The March 2026 spike, by department and definition (the false signal).
CREATE OR REPLACE TABLE out_attrition_false_signal AS
SELECT department, month_start, headcount, exits_gross, exits_excl_transfers, exits_voluntary,
       round(exits_gross / headcount, 3) AS rate_gross, round(exits_excl_transfers / headcount, 3) AS rate_excl_transfers
FROM out_attrition_monthly WHERE month_start BETWEEN DATE '2026-01-01' AND DATE '2026-05-01' AND department = 'Delivery 2'
ORDER BY month_start;

-- Hire cohorts: share of hires who left within 6 and 12 months (rehires after the reorganisation excluded).
CREATE OR REPLACE TABLE out_cohort_retention AS
WITH hires AS (
    SELECT h.employee_id, h.date AS start_date, s.exit_date, e.department, coalesce(e.site, cm.site) AS site
    FROM movements h
    JOIN spans s ON s.employee_id = h.employee_id
    JOIN emp_clean e ON e.employee_id = h.employee_id AND h.date BETWEEN e.valid_from AND e.valid_to
    LEFT JOIN cost_center_map cm ON cm.cost_center = e.cost_center
    WHERE h.movement_type = 'Hire' AND NOT EXISTS (SELECT 1 FROM exits_all x WHERE x.employee_id = h.employee_id
                                                    AND x.date BETWEEN h.date - INTERVAL 31 DAY AND h.date)
), info AS (SELECT any_value(extract_date) AS extract_date FROM months)
SELECT strftime(start_date, '%Y') || '-Q' || quarter(start_date) AS hire_quarter, site,
       count(*) AS hires,
       count(*) FILTER (WHERE exit_date < start_date + INTERVAL 6 MONTH)  AS left_within_6m,
       round(count(*) FILTER (WHERE exit_date < start_date + INTERVAL 6 MONTH) / count(*), 3) AS share_left_6m,
       round(count(*) FILTER (WHERE exit_date < start_date + INTERVAL 12 MONTH) / count(*), 3) AS share_left_12m,
       bool_and(start_date + INTERVAL 6 MONTH <= (SELECT extract_date FROM info))  AS six_months_observed
FROM hires GROUP BY ALL ORDER BY ALL;

-- Voluntary exits by tenure band, half-years (pay compression shows up at 2-4 years).
CREATE OR REPLACE TABLE out_exits_by_tenure AS
WITH hc AS (
    SELECT CASE WHEN month_start < DATE '2025-05-01' THEN 'H0 Nov24-Apr25' WHEN month_start < DATE '2025-11-01' THEN 'H1 May-Oct25'
                WHEN month_start < DATE '2026-05-01' THEN 'H2 Nov25-Apr26' ELSE 'H3 May-Oct26' END AS half, tenure_band,
           count(*) / count(DISTINCT month_start) AS avg_headcount
    FROM hc_monthly WHERE is_active_month_end AND NOT is_duplicate_id GROUP BY ALL
), x AS (
    SELECT CASE WHEN month_start < DATE '2025-05-01' THEN 'H0 Nov24-Apr25' WHEN month_start < DATE '2025-11-01' THEN 'H1 May-Oct25'
                WHEN month_start < DATE '2026-05-01' THEN 'H2 Nov25-Apr26' ELSE 'H3 May-Oct26' END AS half, tenure_band,
           count(*) AS voluntary_exits,
           count(*) FILTER (WHERE exit_reason = 'Better pay elsewhere') AS pay_reason
    FROM exits WHERE exit_type = 'Voluntary' GROUP BY ALL
)
SELECT hc.half, hc.tenure_band, round(hc.avg_headcount, 1) AS avg_headcount, coalesce(voluntary_exits, 0) AS voluntary_exits,
       coalesce(pay_reason, 0) AS pay_reason_exits, round(2 * coalesce(voluntary_exits, 0) / hc.avg_headcount, 3) AS annualised_rate
FROM hc LEFT JOIN x USING (half, tenure_band) ORDER BY ALL;

-- Exit reasons per department and half-year (supports the Data & Cloud story).
CREATE OR REPLACE TABLE out_exit_reasons AS
SELECT department, date_trunc('quarter', date)::DATE AS quarter_start, exit_reason, count(*) AS exits,
       count(*) FILTER (WHERE regretted) AS regretted
FROM exits WHERE exit_type = 'Voluntary' GROUP BY ALL ORDER BY ALL;
