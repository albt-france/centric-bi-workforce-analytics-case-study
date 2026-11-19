# Challenge log

> Every time the request was questioned: the question asked, the evidence, the recommendation and the decision.
> Scenario with a fictional company; stakeholders are roles; data SIMULATED. Numbers come from `sql/` and [KPI_CHECKS.md](KPI_CHECKS.md).

| ID | Original ask | Question I asked | Evidence | Recommendation | Decision (scenario) |
|---|---|---|---|---|---|
| CL-01 | "Monthly turnover by department" | Which decision will this support, and which exits matter? | HR Director: "good people resigning". Monthly rates swing with one or two exits in small departments. | Headline KPI = **regretted voluntary attrition, rolling 12 months, excluding internal transfers**; gross and voluntary shown for reference. | **Accepted** by HR Director and CFO. |
| CL-02 | "Delivery 2 looked terrible in March" | Did 50 people really leave Delivery 2? | 50 exits on 31 Mar 2026, all 50 rehired on 1 Apr under the same id (reason "Reorganisation"). Excluding transfers: **0** exits in Delivery 2 that month. | **Do not escalate.** Treat exit + rehire within 31 days as an internal transfer; ask HR to key reorganisations as transfers. | **Accepted.** Rule built into SQL and DAX. |
| CL-03 | "Turnover = exits / headcount" | Which headcount: start, end, average? People or FTE? Duplicates? | Raw HRIS headcount is 3% too high since Sep 2025 (18 duplicate ids). | Denominator = **average month-end headcount** of master ids over the period. Same for every attrition rate. | **Accepted.** |
| CL-04 | (not asked) | Do people who join leave quickly? | 42% of the Vilnius Q2 2025 ramp-up hires left within 6 months, 15% for all other cohorts. | Add **early attrition** and a **cohort view**; review onboarding before the next ramp-up. | **Accepted** as "Should". |
| CL-05 | "Utilisation from timesheets" | Why does the last month always look bad? | Timesheets arrive up to 10 days late; at the 6 Nov extract, October utilisation reads 60% vs 78% in September. | **Cut-off rule**: report a month only when month end + 10 days <= extract date; label the open month "provisional". | **Accepted** by Head of Delivery. |
| CL-06 | "Revenue per FTE by department" | Does finance map cost centres the same way as HR? | CC-D1-VNO reported under Data & Cloud from May to July 2026: Data & Cloud revenue per FTE +62%, Delivery 1 -57%. | Map cost centres with the **HR master** in the model; monthly HR vs finance reconciliation before publishing. | **Accepted.** Finance to correct the export mapping. |
| CL-07 | (not asked) | Is overload a leading indicator of exits? | Data & Cloud overtime > 15% of capacity Jan-Apr 2026; regretted resignations then doubled (0.56 → 1.17 a month); "workload / burnout" became the first reason. | **Overtime alert** at 15% for two months in a row. | **Accepted.** |
| CL-08 | (not asked) | Are we losing people on pay? | Like-for-like raise +2.8% vs +3.7% for the ICT labour cost index (PUBLIC DATA); new hires earn 6-10% more than 2-4 year colleagues of the same grade; resignations at 2-4 years from 7% to 18% annualised. | Add **new-hire pay premium** and **cost per FTE vs market**; propose a pay review for 2-4 year staff. | **Accepted** for analysis; pay decision with the CFO. |
| CL-09 | "Show me who is likely to leave" (HR Director, follow-up) | Do we have a legal basis and the trust of employees for individual risk scores? | Not assessed; small groups; risk of self-fulfilling labels. | **Declined for this release**: aggregated drivers only. Revisit with a data protection assessment. | **Accepted** (moved to "Won't"). |
| CL-10 | "A dashboard for each department head" | Should they see other departments? Salaries? | Department heads asked for their own team; salary detail is sensitive. | One report, **row-level security** by department; no person-level salary visual. | **Accepted.** |

## How I phrase a challenge

1. Restate the request and the decision behind it ("So the goal is to know where to act on retention, right?").
2. Show one piece of evidence, not an opinion (the March reorganisation, the October cut-off).
3. Offer an option that still answers the original need, and keep the original figure visible for reference.
4. Write the decision down here, with the date, so that the definition does not drift.
