-- 05 · Pay by grade and tenure, new hires vs incumbents, and the company against the public market series.

-- Median monthly gross salary (full-time equivalent) by grade and tenure band, last month of the extract.
CREATE OR REPLACE TABLE out_pay_grade_tenure AS
SELECT grade, tenure_band, count(*) AS people, round(median(salary_monthly_gross), 0) AS median_salary
FROM hc_monthly
WHERE month_start = (SELECT max(month_start) FROM months) AND is_active_month_end AND NOT is_duplicate_id
GROUP BY ALL ORDER BY ALL;

-- Compression: new hires (< 1 year) vs 2-4 year incumbents of the same grade, each month.
CREATE OR REPLACE TABLE out_pay_compression AS
WITH p AS (
    SELECT month_start, grade,
           median(salary_monthly_gross) FILTER (WHERE tenure_band = '0-1 y') AS new_hire_median,
           median(salary_monthly_gross) FILTER (WHERE tenure_band = '2-4 y') AS tenure_2_4_median
    FROM hc_monthly WHERE is_active_month_end AND NOT is_duplicate_id AND grade IN ('G1', 'G2', 'G3') GROUP BY ALL
)
SELECT month_start, grade, round(new_hire_median, 0) AS new_hire_median, round(tenure_2_4_median, 0) AS tenure_2_4_median,
       round(new_hire_median / tenure_2_4_median - 1, 4) AS new_hire_premium
FROM p ORDER BY ALL;

-- Company vs market, quarterly. Indices: 2024-Q4 = 100.
CREATE OR REPLACE TABLE out_pay_vs_market AS
WITH co AS (
    SELECT strftime(month_start, '%Y') || '-Q' || quarter(month_start) AS quarter,
           avg(salary_monthly_gross) AS company_avg_gross
    FROM hc_monthly WHERE is_active_month_end AND NOT is_duplicate_id GROUP BY 1
), mk AS (
    SELECT l.quarter, l.lci_ict_2020_100,
           o.eur_month AS osp_ict_avg_gross, t.eur_month AS osp_all_avg_gross
    FROM lci l
    LEFT JOIN osp_earnings o ON o.quarter = l.quarter AND o.activity = 'ICT (J58-J63)' AND o.measure = 'gross'
    LEFT JOIN osp_earnings t ON t.quarter = l.quarter AND t.activity = 'All activities' AND t.measure = 'gross'
    WHERE l.quarter >= '2023-Q1'
)
SELECT mk.quarter, round(co.company_avg_gross, 0) AS company_avg_gross, mk.osp_ict_avg_gross, mk.osp_all_avg_gross, mk.lci_ict_2020_100,
       round(100 * co.company_avg_gross / first_value(co.company_avg_gross) OVER (ORDER BY (co.company_avg_gross IS NULL), mk.quarter), 1) AS company_index,
       round(100 * mk.lci_ict_2020_100 / (SELECT lci_ict_2020_100 FROM lci WHERE quarter = '2024-Q4'), 1) AS lci_index,
       round(co.company_avg_gross / mk.osp_ict_avg_gross, 3) AS company_vs_osp_ict
FROM mk LEFT JOIN co USING (quarter) ORDER BY mk.quarter;

-- Time to fill (opened -> offer accepted) by quarter filled, with the ICT job vacancy rate of the quarter.
CREATE OR REPLACE TABLE out_time_to_fill AS
SELECT strftime(filled_date, '%Y') || '-Q' || quarter(filled_date) AS quarter, count(*) AS filled,
       round(median(datediff('day', opened_date, filled_date)), 0) AS median_days_to_fill,
       any_value(j.job_vacancy_rate_pct) AS lt_ict_job_vacancy_rate
FROM recruiting r
LEFT JOIN jvr j ON j.geo = 'LT' AND j.quarter = strftime(r.filled_date, '%Y') || '-Q' || quarter(r.filled_date)
WHERE status = 'Filled' AND filled_date >= DATE '2024-11-01'
GROUP BY 1 ORDER BY 1;

-- Like-for-like pay growth: same people, same grade, October of one year vs October of the next, against the market index.
CREATE OR REPLACE TABLE out_pay_like_for_like AS
WITH a AS (SELECT employee_id, grade, salary_monthly_gross FROM hc_monthly WHERE month_start = DATE '2025-10-01' AND is_active_month_end AND NOT is_duplicate_id),
     b AS (SELECT employee_id, grade, salary_monthly_gross FROM hc_monthly WHERE month_start = DATE '2026-10-01' AND is_active_month_end AND NOT is_duplicate_id)
SELECT count(*) AS people, round(median(b.salary_monthly_gross / a.salary_monthly_gross - 1), 4) AS median_raise,
       round((SELECT avg(lci_ict_2020_100) FROM lci WHERE quarter BETWEEN '2025-Q3' AND '2026-Q2')
           / (SELECT avg(lci_ict_2020_100) FROM lci WHERE quarter BETWEEN '2024-Q3' AND '2025-Q2') - 1, 4) AS market_growth_4q
FROM a JOIN b USING (employee_id, grade);
