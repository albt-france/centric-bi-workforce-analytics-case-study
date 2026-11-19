-- 02 · Headcount and FTE from the SCD2 history: one row per person and month in which the person was employed.
-- Headcount = people employed on the last day of the month (master ids only). FTE = sum of contracted FTE.

-- Employment spans: a hire, and the final exit (an exit followed by a rehire of the same id within 31 days is not final).
CREATE OR REPLACE TABLE exits_all AS
SELECT m.*,
       EXISTS (SELECT 1 FROM movements h WHERE h.employee_id = m.employee_id AND h.movement_type = 'Hire'
               AND h.date BETWEEN m.date AND m.date + INTERVAL 31 DAY) AS is_internal_transfer
FROM movements m WHERE m.movement_type = 'Exit';

CREATE OR REPLACE TABLE spans AS
SELECT e.employee_id, min(e.hire_date) AS hire_date,
       (SELECT max(x.date) FROM exits_all x WHERE x.employee_id = e.employee_id AND NOT x.is_internal_transfer) AS exit_date,
       bool_or(e.is_duplicate_id) AS is_duplicate_id
FROM emp_clean e GROUP BY e.employee_id;

-- Person-month grain: the SCD2 row valid on the last employed day of the month.
CREATE OR REPLACE TABLE hc_monthly AS
WITH pm AS (
    SELECT m.month_start, m.month_end, m.working_days, s.employee_id, s.hire_date, s.exit_date, s.is_duplicate_id,
           greatest(m.month_start, s.hire_date)                                         AS first_day,
           least(m.month_end, coalesce(s.exit_date, DATE '9999-12-31'))                 AS last_day_employed
    FROM months m JOIN spans s ON s.hire_date <= m.month_end AND coalesce(s.exit_date, DATE '9999-12-31') >= m.month_start
), r AS (
    SELECT pm.*, e.department, coalesce(e.site, cm.site) AS site, e.grade, e.fte, e.salary_monthly_gross, e.cost_center,
           e.valid_from, e.manager_id
    FROM pm
    JOIN emp_clean e ON e.employee_id = pm.employee_id AND pm.last_day_employed BETWEEN e.valid_from AND e.valid_to
    LEFT JOIN cost_center_map cm ON cm.cost_center = e.cost_center
)
SELECT r.month_start, r.employee_id, r.employee_id || '|' || strftime(r.valid_from, '%Y-%m-%d') AS employee_key,
       r.department, r.site, r.grade, r.fte, r.salary_monthly_gross, r.cost_center, r.hire_date, r.exit_date,
       (r.last_day_employed = r.month_end)                                         AS is_active_month_end,
       r.is_duplicate_id,
       (r.hire_date >= r.month_start)                                              AS is_new_hire_in_month,
       datediff('month', r.hire_date, r.month_end)                                 AS tenure_months,
       CASE WHEN datediff('month', r.hire_date, r.month_end) < 12 THEN '0-1 y'
            WHEN datediff('month', r.hire_date, r.month_end) < 24 THEN '1-2 y'
            WHEN datediff('month', r.hire_date, r.month_end) < 48 THEN '2-4 y'
            ELSE '4+ y' END                                                         AS tenure_band,
       -- contracted capacity: Lithuanian working days employed x 8 h x FTE, minus absences
       (SELECT count(*) FROM generate_series(r.first_day, r.last_day_employed, INTERVAL 1 DAY) g(d)
         WHERE isodow(d) <= 5 AND CAST(d AS DATE) NOT IN (SELECT CAST(date AS DATE) FROM holidays))  AS working_days_employed,
       coalesce((SELECT sum(a.days) FROM absences a WHERE a.employee_id = r.employee_id AND a.month = r.month_start), 0) AS absence_days
FROM r;

ALTER TABLE hc_monthly ADD COLUMN capacity_hours DOUBLE;
UPDATE hc_monthly SET capacity_hours = CASE WHEN is_duplicate_id THEN 0 ELSE round((working_days_employed - absence_days) * 8 * fte, 1) END;

CREATE OR REPLACE TABLE out_headcount_monthly AS
SELECT month_start, department, site,
       count(*) FILTER (WHERE is_active_month_end)                              AS headcount_raw,
       count(*) FILTER (WHERE is_active_month_end AND NOT is_duplicate_id)      AS headcount,
       round(sum(fte) FILTER (WHERE is_active_month_end AND NOT is_duplicate_id), 1) AS fte,
       count(*) FILTER (WHERE is_new_hire_in_month AND NOT is_duplicate_id)     AS new_hires,
       round(avg(salary_monthly_gross) FILTER (WHERE is_active_month_end AND NOT is_duplicate_id), 0) AS avg_salary
FROM hc_monthly GROUP BY ALL ORDER BY ALL;

CREATE OR REPLACE TABLE out_headcount_company AS
SELECT month_start, sum(headcount_raw) AS headcount_raw, sum(headcount) AS headcount, round(sum(fte), 1) AS fte,
       sum(headcount_raw) - sum(headcount) AS duplicate_ids,
       round(avg(sum(headcount)) OVER (ORDER BY month_start ROWS BETWEEN 11 PRECEDING AND CURRENT ROW), 1) AS avg_headcount_r12m
FROM out_headcount_monthly GROUP BY 1 ORDER BY 1;
