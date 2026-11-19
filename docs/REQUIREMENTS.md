# Requirements

> Scenario: fictional 600-person IT services company. Stakeholders are roles. All data SIMULATED.
> Source: [STAKEHOLDER_BRIEF.md](STAKEHOLDER_BRIEF.md). Status: agreed with the three stakeholders (scenario), version 1.0.

## Goal

Replace the requested *monthly turnover report by department* with a **workforce report** that tells leadership whether the right people
are leaving, why, at what cost, and whether delivery capacity is used, built on numbers that reconcile with finance.

## User stories and acceptance criteria (MoSCoW)

| # | Priority | User story | Acceptance criteria |
|---|---|---|---|
| R1 | **Must** | As HR Director, I want **regretted voluntary attrition over 12 rolling months, excluding internal transfers**, by department and site, so that I see whether good people are leaving. | Matches `sql/kpi_checks.sql` to 0.1 pt; internal transfers (exit + rehire of the same id within 31 days) excluded; gross rate shown next to it for reference. |
| R2 | **Must** | As HR Director, I want the **three definitions side by side** (gross, excl. transfers, voluntary), so that I can explain any gap. | One chart, three lines, same denominator (average month-end headcount). |
| R3 | **Must** | As CFO, I want **one headcount** that reconciles with payroll, so that the board sees one figure. | Duplicate ids removed; HR to finance bridge closes to 0 every closed month. |
| R4 | **Must** | As Head of Delivery, I want **utilisation, bench % and overtime %** by department, **closed months only**, so that the open month does not trigger false alarms. | A month is shown only when month end + 10 days <= extract date; open month labelled "provisional". |
| R5 | **Must** | As a department head, I want to see **only my department**. | Role `DepartmentManager` filters DimOrg and DimEmployee; tested with "View as". |
| R6 | **Should** | As HR Director, I want **early attrition** (leavers in their first 12 months) and **cohort exits** by hiring quarter and site. | Cohort table: hires, share left within 6 and 12 months. |
| R7 | **Should** | As CFO, I want **cost per FTE vs the market** (public data). | Company average gross vs Statistics Lithuania ICT average; like-for-like raise vs Eurostat ICT labour cost index. |
| R8 | **Should** | As Head of Delivery, I want an **overtime alert** above 15% of capacity. | Threshold line on the chart; department flagged two months in a row. |
| R9 | **Should** | As HR Director, I want **time to fill** for open roles. | Median days opened to filled, open requisitions. |
| R10 | **Could** | Exit reasons by department and quarter. | Table on the attrition page. |
| R11 | **Could** | A data-quality page anyone can read. | Duplicate ids, late timesheets, HR vs finance gap, mis-mapped cost centres. |
| R12 | **Won't (this release)** | Individual-level attrition risk scores. | Out of scope: ethics review and data protection assessment needed first. |

## Non-functional requirements

- **Accuracy:** every KPI in [KPI_DICTIONARY.md](KPI_DICTIONARY.md) has a reference value in SQL and is checked ([KPI_CHECKS.md](KPI_CHECKS.md)).
- **Privacy:** ids only, no names; department heads see their own department; no salary at person level in visuals.
- **Refresh:** monthly, after the timesheet cut-off (10 days after month end) and the finance close.
- **Ownership:** each KPI has an owner (see dictionary); definitions change only through the change log.

## Out of scope

- Individual predictions ("who will leave next"), performance ratings, names.
- Payroll detail beyond contracted monthly gross salary.
- Client-level profitability (finance export is by cost centre only).
- Real Centric data: this is a simulation of a fictional company.

## Open questions (to clear before go-live)

1. Can HR key reorganisations as transfers instead of exit + rehire? (see CL-02)
2. Who owns the cost-centre master, HR or finance? (see CL-06)
3. Is "regretted" flagged consistently by all managers? A short guideline is proposed in the adoption plan.
