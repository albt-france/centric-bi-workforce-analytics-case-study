# Adoption plan

> Scenario: fictional company; audiences are roles. A report nobody opens has no value, so adoption is planned and measured.

## 1. Present the results (week 1)

- **One-page read-out** for the HR Director, CFO and Head of Delivery (30 minutes): the request, the three definitions, the false signal
  that was **not** raised, the five real findings, the decisions asked for. Same page as the PDF overview.
- Start with the question they asked ("monthly turnover by department"), then show why the answer is a different KPI.
- Close with three decisions: adopt the headline KPI, fix the two source issues (HRIS duplicates, finance mapping), agree the overtime alert.

## 2. Train (week 2)

**30-minute session** per audience (HR business partners, department heads, finance controllers):

| Minutes | Content |
|---|---|
| 0-5 | Why regretted attrition R12M, not monthly turnover |
| 5-15 | Live tour of the four pages; how to filter by site, department, month |
| 15-22 | Reading the provisional month and the data-quality page |
| 22-27 | What department heads see under RLS; how to flag "regretted" consistently |
| 27-30 | Where to send questions; release notes |

Guideline handed out: *"Regretted = you would have made a counter-offer, or the skill is hard to replace. Flag it within 5 days of the resignation."*

## 3. Release notes

Each monthly refresh ships with five lines in the report and in the team channel: what changed (data, definitions, visuals), known issues,
next release date. Definitions only change through [CHALLENGE_LOG.md](CHALLENGE_LOG.md).

## 4. Feedback loop

- A "Feedback" button on each page (Microsoft Form link) and a 15-minute check-in with each stakeholder after the first two refreshes.
- Requests go to a backlog with the MoSCoW priority of [REQUIREMENTS.md](REQUIREMENTS.md).

## 5. Measure usage

Source: Power BI service **usage metrics report** (views, unique viewers, pages viewed) for the workspace, reviewed monthly.

| Metric | Target after 3 months |
|---|---|
| Unique viewers / intended audience | ≥ 70% |
| Views of the executive page per month | ≥ 1 per stakeholder |
| Department heads opening their filtered view | ≥ 5 of 6 |
| Excel exports of the old HRIS file | Falling to 0 |
| Decisions logged that cite the report | ≥ 1 per month |

## 6. If nobody opens it

1. Ask, don't guess: 10-minute call with two non-users: wrong KPI, wrong timing, or wrong channel?
2. Push instead of pull: e-mail subscription to the executive page on refresh day; KPI in the monthly management pack.
3. Cut: remove visuals with no views after two months; keep the page short.
4. If the question has changed, go back to the stakeholder brief and start again: the goal is the decision, not the report.
