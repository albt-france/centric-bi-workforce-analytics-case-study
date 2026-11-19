-- 01 · Data quality checks on the HR, timesheet and finance extracts (DuckDB).
-- Every later query reads the cleaned objects created here (dup_map, emp_clean, months).

-- Calendar of reporting months, Lithuanian working days, and the timesheet cut-off rule:
-- a month is "closed" only when month end + 10 days <= extract date (timesheets arrive up to 10 days late).
CREATE OR REPLACE TABLE months AS
WITH info AS (
    SELECT max(CASE WHEN key = 'extract_date' THEN CAST(value AS DATE) END)           AS extract_date,
           max(CASE WHEN key = 'first_month' THEN CAST(value AS DATE) END)            AS first_month,
           max(CASE WHEN key = 'last_month' THEN CAST(value AS DATE) END)             AS last_month,
           max(CASE WHEN key = 'finance_closed_through' THEN CAST(value AS DATE) END) AS fin_closed
    FROM extract_info
), m AS (
    SELECT CAST(d AS DATE) AS month_start FROM info, generate_series(info.first_month, info.last_month, INTERVAL 1 MONTH) g(d)
)
SELECT m.month_start,
       last_day(m.month_start)                                                        AS month_end,
       (SELECT count(*) FROM generate_series(m.month_start, last_day(m.month_start), INTERVAL 1 DAY) s(d)
         WHERE isodow(d) <= 5 AND CAST(d AS DATE) NOT IN (SELECT CAST(date AS DATE) FROM holidays)) AS working_days,
       last_day(m.month_start) + INTERVAL 10 DAY <= info.extract_date                AS is_closed,
       m.month_start <= info.fin_closed                                               AS finance_closed,
       info.extract_date
FROM m, info;

-- Check 1: one person, two ids. The HRIS migration (Sep 2025) re-created some people under a new id.
-- Same coded birth date + same hire date = same person; the id that appears later (and logs no time) is the duplicate.
CREATE OR REPLACE TABLE dup_map AS
WITH ids AS (
    SELECT employee_id, birth_key, hire_date, min(valid_from) AS first_seen,
           arg_min(grade, valid_from) AS first_grade
    FROM employees GROUP BY ALL
), pairs AS (
    SELECT birth_key, hire_date, employee_id, first_seen, first_grade,
           row_number() OVER (PARTITION BY birth_key, hire_date ORDER BY first_seen, employee_id) AS rn,
           first_value(employee_id) OVER (PARTITION BY birth_key, hire_date ORDER BY first_seen, employee_id) AS master_id,
           count(*) OVER (PARTITION BY birth_key, hire_date) AS n_ids
    FROM ids
)
SELECT p.employee_id AS duplicate_id, p.master_id, p.birth_key, p.hire_date, p.first_seen,
       (SELECT count(*) FROM timesheets t WHERE t.employee_id = p.employee_id) AS timesheet_rows
FROM pairs p WHERE n_ids > 1 AND rn > 1;

-- Check 2: overlapping SCD2 periods (a legacy row not closed when the new HRIS row starts).
CREATE OR REPLACE TABLE scd2_overlaps AS
SELECT employee_id, valid_from, valid_to, next_from, datediff('day', next_from, valid_to) + 1 AS overlap_days
FROM (
    SELECT employee_id, valid_from, coalesce(valid_to, DATE '9999-12-31') AS valid_to,
           lead(valid_from) OVER (PARTITION BY employee_id ORDER BY valid_from) AS next_from
    FROM employees
) WHERE next_from IS NOT NULL AND valid_to >= next_from;

-- Clean SCD2: duplicate ids flagged, overlaps cut at the day before the next row starts, open end = 9999-12-31.
CREATE OR REPLACE TABLE emp_clean AS
SELECT e.* EXCLUDE (valid_to),
       least(coalesce(e.valid_to, DATE '9999-12-31'),
             coalesce(lead(e.valid_from) OVER (PARTITION BY e.employee_id ORDER BY e.valid_from) - INTERVAL 1 DAY, DATE '9999-12-31'))::DATE AS valid_to,
       d.duplicate_id IS NOT NULL AS is_duplicate_id
FROM employees e LEFT JOIN dup_map d ON d.duplicate_id = e.employee_id;

-- Check 3: missing mandatory fields.
CREATE OR REPLACE TABLE out_dq_missing_fields AS
SELECT 'employees' AS source, f.field, f.missing_rows, count(*) OVER () AS checks
FROM (
    SELECT 'manager_id' AS field, count(*) FILTER (WHERE manager_id IS NULL) AS missing_rows FROM employees
    UNION ALL SELECT 'site', count(*) FILTER (WHERE site IS NULL) FROM employees
    UNION ALL SELECT 'grade', count(*) FILTER (WHERE grade IS NULL) FROM employees
    UNION ALL SELECT 'department', count(*) FILTER (WHERE department IS NULL) FROM employees
    UNION ALL SELECT 'salary_monthly_gross', count(*) FILTER (WHERE salary_monthly_gross IS NULL) FROM employees
) f;

-- Check 4: timesheet entry lag and completeness by month.
CREATE OR REPLACE TABLE out_dq_timesheet_lag AS
SELECT t.month AS month_start,
       count(*)                                                                  AS rows_received,
       round(avg(datediff('day', last_day(t.month), t.entered_date)), 1)         AS avg_lag_days,
       round(avg((datediff('day', last_day(t.month), t.entered_date) > 10)::INT), 3) AS share_after_10_days,
       any_value(m.is_closed)                                                    AS is_closed
FROM timesheets t JOIN months m ON m.month_start = t.month
GROUP BY 1 ORDER BY 1;

CREATE OR REPLACE TABLE out_dq_duplicates AS SELECT * FROM dup_map ORDER BY first_seen, duplicate_id;
CREATE OR REPLACE TABLE out_dq_overlaps AS SELECT * FROM scd2_overlaps ORDER BY employee_id;

CREATE OR REPLACE TABLE out_dq_summary AS
SELECT 'Duplicate employee ids (same person, two ids)' AS check_name, (SELECT count(*) FROM dup_map) AS issues,
       'Flag is_duplicate_id; count the master id only' AS fix
UNION ALL SELECT 'Overlapping SCD2 periods', (SELECT count(*) FROM scd2_overlaps), 'Cut the older row the day before the next row starts'
UNION ALL SELECT 'Rows with missing manager_id', (SELECT count(*) FROM employees WHERE manager_id IS NULL), 'Report as "Unassigned"; ask HR to complete'
UNION ALL SELECT 'Rows with missing site', (SELECT count(*) FROM employees WHERE site IS NULL), 'Take the site from the cost centre'
UNION ALL SELECT 'Timesheets entered > 10 days after month end', (SELECT count(*) FROM timesheets WHERE datediff('day', last_day(month), entered_date) > 10), 'Cut-off rule: report closed months only'
UNION ALL SELECT 'Months not closed at extract date', (SELECT count(*) FROM months WHERE NOT is_closed), 'Show as provisional, excluded from KPIs';
