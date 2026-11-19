# KPI dictionary

> One definition per KPI, agreed and owned. DAX: `powerbi/measures.dax` (table `_Measures`). Reference values: [KPI_CHECKS.md](KPI_CHECKS.md).
> Fictional company, SIMULATED data. Owners are roles. "R12M" = 12 months ending with the last date in the filter context.

| KPI | Definition | Formula | DAX measure | Grain | Filters that apply | Owner | Threshold | Known pitfall |
|---|---|---|---|---|---|---|---|---|
| **Headcount** | People employed on the last day of the month | count of master ids active at month end | `[Headcount]` | month | site, department, grade | HR Director | - | Counting raw HRIS ids adds 18 duplicates since Sep 2025; across several months the measure shows the **last** month, not a sum. |
| **FTE** | Contracted full-time equivalents at month end | sum of FTE of master ids | `[FTE]` | month | same | HR Director | - | Part-timers: 600 people ≠ 600 FTE. |
| **Average headcount** | Mean of month-end headcounts in the period | AVERAGEX(months, Headcount) | `[Average Headcount]` | period | same | HR Director | - | Denominator of every attrition rate: never mix with start or end headcount. |
| **Attrition % (gross)** | Every exit keyed in the HRIS | exits / average headcount | `[Attrition % (gross)]` | period | same | HR Director | reference only | Includes reorganisations keyed as exit + rehire (March 2026). |
| **Attrition % (excl. transfers)** | Exits that are real departures | (exits - internal transfers) / average headcount | `[Attrition % (excl. transfers)]` | period | same | HR Director | - | Transfer rule: exit followed by a rehire of the same id within 31 days. |
| **Voluntary attrition %** | Resignations | voluntary exits / average headcount | `[Voluntary Attrition %]`, `... R12M` | period | same | HR Director | > 15% R12M | Monthly values are noisy in small departments: use R12M. |
| **Regretted attrition % R12M** *(headline)* | Resignations of people the manager wanted to keep | regretted voluntary exits / average headcount, 12 rolling months | `[Regretted Attrition % R12M]` | R12M | same | HR Director | > 6% R12M | "Regretted" must be flagged consistently: guideline in the adoption plan. |
| **Early attrition %** | Hires who leave in their first year | exits with tenure < 12 months / hires in the period | `[Early Attrition %]` | period | same | HR Director | > 20% | Not a cohort rate: use the cohort table for "share of a hiring quarter that left". |
| **Hires** | External hires | hires excluding rehires that close an internal transfer | `[Hires]` | period | same | HR Director | - | Rehire rows from the March reorganisation must not count. |
| **Utilisation % (closed months)** | Share of capacity billed to clients | billable hours / capacity, closed months only | `[Utilization % (closed months)]` | month | billable departments | Head of Delivery | < 75% | The open month is incomplete (timesheets up to 10 days late): blank until closed. |
| **Capacity hours** | Hours people could work | LT working days employed × 8 h × FTE − absences | `[Capacity Hours]` | month | billable departments | Head of Delivery | - | Uses Lithuanian public holidays: months have 19 to 23 working days. |
| **Bench %** | Capacity without a client project | bench hours / capacity | `[Bench %]` | month | billable departments | Head of Delivery | > 10% | A one-off client loss (Delivery 3, June 2026) is a staffing issue, not a trend. |
| **Overtime %** | Hours above contracted capacity | overtime hours / capacity | `[Overtime %]` | month | billable departments | Head of Delivery | > 15% two months in a row | Leading indicator of regretted exits (about two months later). |
| **Timesheet completeness %** | How much of the month has been received | logged hours / capacity | `[Timesheet Completeness %]` | month | billable departments | Head of Delivery | < 95% = provisional | Low in the open month by design. |
| **Average gross salary** | Contracted monthly gross, full-time basis | average at month end | `[Average Gross Salary]` | month | site, department, grade | CFO | - | Mix effect: hiring juniors lowers the average without any pay change. |
| **New-hire pay premium %** | Pay compression | median pay < 1 year ÷ median pay 2-4 years − 1, same grade | `[New-Hire Pay Premium %]` | month | grade required | CFO / HR | > 5% | Meaningless without a grade in context. |
| **Salary vs market %** | Company vs Lithuanian ICT average (PUBLIC DATA) | average gross ÷ Statistics Lithuania ICT average − 1 | `[Salary vs Market %]` | quarter | company, grade | CFO | - | The national ICT average mixes all ICT jobs and both main cities: context, not a target. Latest published quarter is used. |
| **Median days to fill** | Speed of hiring | median (filled date − opened date) | `[Median Days to Fill]` | period (by date filled) | department, site, grade | HR Director | > 45 days | Uses the active relationship on FilledDate; `[Requisitions Opened]` uses OpenedDate. |
| **Revenue per FTE** | Productivity | revenue ÷ month-end FTE, average per month | `[Revenue per FTE]` | month | department, site | CFO | - | Use the HR cost-centre master: the finance export mis-mapped CC-D1-VNO (May-Jul 2026). |
| **Cost per FTE** | Cost base | (payroll + other cost) ÷ FTE, average per month | `[Cost per FTE]` | month | department, site | CFO | - | Finance closes later: October 2026 not available. |
| **HR vs finance gap** | Do HR and payroll agree? | finance paid headcount − HR raw month-end headcount | `[HR vs Finance Gap]` | month | company, department | CFO + HR | ≠ bridge | Expected gap = − duplicate ids + leavers paid in their last month; residual must be 0. |
| **Duplicate ids** | Data quality | raw HRIS headcount − headcount | `[Duplicate IDs]` | month | - | HRIS owner | > 0 | Root cause: HRIS migration, Sep 2025. |
| **Late timesheets %** | Data quality | rows entered > 10 days after month end ÷ rows | `[Late Timesheets %]` | month | - | Head of Delivery | > 3% | Late rows change closed months: refresh history after the cut-off. |

## Rules shared by every KPI

- **Master ids only**: rows flagged `IsDuplicateId = 1` are excluded everywhere except the data-quality page.
- **Closed months**: utilisation, bench and overtime are read on closed months; the open month is labelled "provisional".
- **Internal transfer rule**: an exit followed by a rehire of the same id within 31 days is a transfer, in SQL and in DAX.
- **One denominator**: average month-end headcount over the period, for every rate.
