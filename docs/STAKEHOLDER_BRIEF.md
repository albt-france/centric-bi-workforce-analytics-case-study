# Stakeholder brief

> **Written scenario.** The company is a **fictional 600-person IT services company** with offices in Kaunas and Vilnius.
> The stakeholders are **roles, not people**, and the interviews below are **written scenarios**, not real conversations.
> All internal data are **SIMULATED**. Nothing here describes Centric, its clients or its employees.

## The request

> *"I need a monthly turnover report by department."* (HR Director, by e-mail)

A clear request, quick to build, and easy to get wrong: "turnover" has no agreed definition in the company, and nobody had said
what decision the report should support. Before building anything, I booked three 30-minute conversations.

## Interview 1 · HR Director (requester)

| Question I asked | Answer (scenario) |
|---|---|
| What decision will you take with this report? | "Whether to launch a retention plan, and where. The board asked me why people are leaving." |
| What made you ask now? | "Delivery 2 looked terrible in March. And I keep hearing that Data & Cloud is losing its best people." |
| Which exits worry you? | "Good people resigning. Not contract ends, not the people we let go." |
| Are internal moves turnover? | "No. But I am not sure how the HRIS records them." |
| Who else will read it? | "The CFO and the Head of Delivery, and each department head for their own team only." |
| How do you report today? | "An Excel file from the HRIS export. Headcount never matches finance." |

**What the HR Director really needs:** to know whether the *right* people are leaving, why, and early enough to act; and to defend one
headcount figure in front of the board.

## Interview 2 · CFO

| Question I asked | Answer (scenario) |
|---|---|
| What would you do with an attrition report? | "Price it. Every senior leaver costs recruitment fees, months of vacancy and lost billable hours." |
| Which numbers do you trust today? | "Finance headcount from payroll. HR headcount is always higher and nobody can explain why." |
| What is your key ratio? | "Revenue and cost per FTE by department, against what the market pays." |
| Any known issue? | "A cost centre was moved between departments this year, I am not sure the export followed." |

**What the CFO really needs:** one reconciled headcount, revenue and cost per FTE that can be trusted, and the cost of attrition.

## Interview 3 · Head of Delivery

| Question I asked | Answer (scenario) |
|---|---|
| What keeps you awake? | "Utilisation. If people sit on the bench we lose money; if they do overtime for months, they leave." |
| How do you see utilisation today? | "From timesheets. The last month always looks bad, then it gets better." |
| What happened in Delivery 3? | "A large client project ended in May. We have people without a project." |
| What happened in Delivery 2 in March? | "A reorganisation: two teams were merged. Nobody left." |
| Would you use a department view? | "Yes, but I only want my departments, with the same numbers as HR." |

**What the Head of Delivery really needs:** utilisation, bench and overtime by department, with a rule that stops the incomplete last month
from triggering false alarms, and an early warning on overload.

## What each stakeholder will decide with the solution

| Stakeholder | Decision | KPIs that support it |
|---|---|---|
| HR Director | Where to run retention actions; how to fix onboarding | Regretted attrition R12M, early attrition, exits by tenure, exit reasons |
| CFO | Budget for pay review and backfills; trust in headcount | Cost per FTE vs market, revenue per FTE, HR vs finance gap |
| Head of Delivery | Staffing, redeployment, overload alerts | Utilisation (closed months), bench %, overtime % |
| Department heads | Act on their own team | Same report, row-level security by department |

Next documents: [REQUIREMENTS.md](REQUIREMENTS.md) (what will be built) and [CHALLENGE_LOG.md](CHALLENGE_LOG.md) (where the request was challenged).
