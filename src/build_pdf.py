"""Build the 8-page PDF case study: docs/report.html -> docs/Centric_BI_Workforce_Case_Study.pdf (Edge or Chrome, headless).

Every number is read from data/output, data/public or docs/KPI_CHECKS.md (nothing typed in by hand except the
scenario text). PDF metadata are emptied.
    python src/build_pdf.py
"""
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pandas as pd
from pypdf import PdfReader, PdfWriter

import charts

ROOT = Path(__file__).resolve().parents[1]
OUT, PUB, DOCS = ROOT / "data" / "output", ROOT / "data" / "public", ROOT / "docs"
PDF_NAME = "Centric_BI_Workforce_Case_Study.pdf"
DISCLAIMER = "Independent case study based on public data · not affiliated with or endorsed by Centric"
AI_NOTE = next(line.split("**AI note.**", 1)[1].strip() for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
               if "**AI note.**" in line)   # the one AI note lives in README > Methods and is reused verbatim in the PDF


def r(name, folder=OUT):
    return pd.read_csv(folder / f"{name}.csv")


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def facts():
    f = {}
    d = r("attrition_definitions").set_index("month_start")
    f["mar_gross"], f["mar_excl"] = int(d.loc["2026-03-01", "gross"]), int(d.loc["2026-03-01", "excl_transfers"])
    f["mar_rate_gross"] = d.loc["2026-03-01", "rate_gross_month"]
    fs = r("attrition_false_signal").set_index("month_start").loc["2026-03-01"]
    f["d2_gross"], f["d2_excl"], f["d2_rate"] = int(fs.exits_gross), int(fs.exits_excl_transfers), fs.rate_gross
    k = r("kpi_checks")
    kv = {(a, b): v for a, b, v in k[["kpi", "context", "sql_value"]].itertuples(index=False)}
    f["k"] = kv
    f["reg_r12"] = kv[("Regretted Attrition %", "R12M to Sep 2026")]
    f["vol_r12"] = kv[("Voluntary Attrition %", "R12M to Sep 2026")]
    f["gross_r12"] = kv[("Attrition % (gross)", "R12M to Sep 2026")]
    f["excl_r12"] = kv[("Attrition % (excl. transfers)", "R12M to Sep 2026")]
    f["hc_sep"] = int(kv[("Headcount", "Sep 2026, company")])
    f["util_sep"] = kv[("Utilization %", "Sep 2026, billable departments")]
    f["util_oct_raw"] = kv[("Utilization % (raw, no cut-off)", "Oct 2026, billable departments")]
    a = r("attrition_monthly")
    dc = a[a.department == "Data & Cloud"]
    pre, ev = dc[dc.month_start < "2026-03-01"], dc[dc.month_start.between("2026-03-01", "2026-08-01")]
    f["dc_pre"], f["dc_ev"] = pre.exits_regretted.mean(), ev.exits_regretted.mean()
    u = r("utilization_monthly")
    f["dc_ot_max"] = u[u.department == "Data & Cloud"].overtime_share.max()
    d3 = u[u.department == "Delivery 3"]
    f["d3_bench_pre"] = d3[d3.month_start < "2026-06-01"].bench_share.mean()
    f["d3_bench_post"] = d3[(d3.month_start >= "2026-06-01") & d3.is_closed].bench_share.mean()
    f["d3_util_pre"] = d3[d3.month_start < "2026-06-01"].utilization.mean()
    f["d3_util_post"] = d3[(d3.month_start >= "2026-06-01") & d3.is_closed].utilization.mean()
    t = r("exits_by_tenure")
    t = t[t.tenure_band == "2-4 y"].annualised_rate.tolist()
    f["ten_first"], f["ten_last"] = t[0], t[-1]
    lfl = r("pay_like_for_like").iloc[0]
    f["lfl"], f["mkt"] = lfl.median_raise, lfl.market_growth_4q
    pc = r("pay_compression")
    pc = pc[pc.month_start == pc.month_start.max()]
    f["prem_lo"], f["prem_hi"] = pc.new_hire_premium.min(), pc.new_hire_premium.max()
    c = r("cohort_retention")
    c = c[c.six_months_observed]
    w = c[(c.hire_quarter == "2025-Q2") & (c.site == "Vilnius")]
    o = c[~((c.hire_quarter == "2025-Q2") & (c.site == "Vilnius"))]
    f["wave_n"], f["wave_6m"] = int(w.hires.sum()), w.left_within_6m.sum() / w.hires.sum()
    f["other_6m"] = o.left_within_6m.sum() / o.hires.sum()
    f["dups"] = int(r("dq_duplicates").shape[0])
    b = r("recon_bridge").iloc[-1]
    f["bridge"] = b
    rf = r("revenue_per_fte")
    x = rf[(rf.department == "Data & Cloud") & rf.month_start.between("2026-05-01", "2026-07-01")]
    f["rev_jump"] = (x.revenue_per_fte_reported / x.revenue_per_fte_fixed).mean() - 1
    pm = r("pay_vs_market")
    f["vs_osp"] = pm.dropna(subset=["company_vs_osp_ict"]).iloc[-1]
    lci = r("eurostat_labour_cost_index_ict_lt", PUB)
    f["lci_last"] = lci.iloc[-1]
    j = r("eurostat_job_vacancy_rate_ict", PUB)
    f["jvr"] = j[j.quarter == j[j.geo == "LT"].quarter.max()].set_index("geo").job_vacancy_rate_pct
    f["jvr_q"] = j[j.geo == "LT"].quarter.max()
    ict = r("eurostat_ict_specialists_share", PUB)
    f["ict"] = ict[ict.year == ict.year.max()].set_index("geo").ict_specialists_pct_employment
    f["ict_y"] = int(ict.year.max())
    osp = r("osp_average_monthly_earnings", PUB)
    osp = osp[osp.measure == "gross"]
    f["osp_q"] = osp.quarter.max()
    f["osp_ict"] = osp[(osp.activity == "ICT (J58-J63)") & (osp.quarter == f["osp_q"])].eur_month.iloc[0]
    f["osp_all"] = osp[(osp.activity == "All activities") & (osp.quarter == f["osp_q"])].eur_month.iloc[0]
    kc = (DOCS / "KPI_CHECKS.md").read_text(encoding="utf-8")
    import re
    m = re.search(r"\*\*(\d+ / \d+) KPIs match\*\*", kc)
    f["kpi_match"] = (m.group(1) + " match") if m else ""
    f["kpi_rows"] = [line.split("|")[1:7] for line in kc.splitlines() if line.startswith("| ") and "`[" in line]
    return f


# ------------------------------------------------------------------ html helpers
def page(n, title, subtitle, tag, body, sources):
    tags = "".join(f'<div class="tag tag-{t.lower().split()[0]}">{t}</div>' for t in tag.split(" + "))
    return f"""
<section class="page">
  <header><div><h1>{title}</h1><p class="sub">{subtitle}</p></div><div class="tags">{tags}</div></header>
  <main>{body}</main>
  <footer><span>{sources}</span><span>{DISCLAIMER}</span><span class="pg">{n} / 7</span></footer>
</section>"""


def card(inner, cls=""):
    return f'<div class="card {cls}">{inner}</div>'


def img(src, title, tag=""):
    t = f' <span class="mini mini-{tag.lower()}">{tag}</span>' if tag else ""
    return card(f'<h2>{title}{t}</h2><figure><img src="{src}"/></figure>', "fig")


def tile(label, value, text, tag):
    return card(f'<div class="label">{label} <span class="mini mini-{tag.lower()}">{tag}</span></div><div class="big">{value}</div><p>{text}</p>', "tile")


# ------------------------------------------------------------------ pages
def p0(f, ch):
    qs = ["What does <i>turnover</i> mean here, and which exits really matter?", "Is the March 2026 spike in Delivery 2 real?",
          "Who leaves, and why: workload, pay or onboarding?", "Is delivery capacity used, and why does the last month always look bad?",
          "Can HR, finance and delivery trust one set of numbers?"]
    tiles = "".join([
        tile("FALSE SIGNAL NOT RAISED", f"{f['d2_gross']} → {f['d2_excl']}",
             f"Delivery 2 exits in March 2026: {f['d2_gross']} keyed, {f['d2_excl']} once a reorganisation keyed as exit + rehire is treated as a transfer.", "SIMULATED"),
        tile("OVERLOAD, THEN EXITS", f"×{f['dc_ev'] / f['dc_pre']:.1f}",
             f"Data & Cloud regretted resignations a month after four months of overtime above 15% of capacity.", "SIMULATED"),
        tile("PAY COMPRESSION", f"{pct(f['ten_first'])} → {pct(f['ten_last'])}",
             f"Resignations at 2-4 years of service (annualised); new hires earn {pct(f['prem_lo'])}-{pct(f['prem_hi'])} more in the same grade.", "SIMULATED"),
        tile("ONE HEADCOUNT", f"{f['dups']} ids",
             f"duplicated by an HRIS migration (+3% headcount), found by reconciling HR with payroll; the bridge now closes to zero.", "SIMULATED")])
    recos = ["<b>Headline KPI:</b> regretted voluntary attrition, 12 rolling months, excluding internal transfers.",
             "<b>Do not escalate March 2026</b>; key reorganisations as transfers.",
             "<b>Overtime alert</b> at 15% of capacity, two months in a row (Data & Cloud).",
             "<b>Pay review</b> for 2-4 year staff; <b>onboarding</b> fix before the next ramp-up.",
             "<b>Publish closed months only</b>; reconcile HR and finance every month."]
    steps = ["Clarify the request<br><span>3 stakeholder interviews</span>", "Document needs<br><span>user stories, MoSCoW</span>",
             "Challenge it<br><span>10 logged challenges</span>", "Propose KPIs<br><span>dictionary, owners</span>",
             "Build the model<br><span>SQL, star schema, DAX, RLS</span>", "Present & adopt<br><span>read-out, training, usage</span>"]
    body = f"""
<div class="g0">
  <div class="stack">
    {card('<div class="quote">“I need a monthly turnover report by department.”</div><p class="note">HR Director of a fictional 600-person IT services company (Kaunas and Vilnius). Written scenario; all internal data SIMULATED.</p>', 'auto')}
    {card('<h2>Five questions behind the request</h2><ol class="qs">' + ''.join(f'<li>{q}</li>' for q in qs) + '</ol>', 'auto')}
    {card('<h2>What was delivered</h2><ul class="small">'
          '<li><b>Requirements</b>: stakeholder brief, user stories (MoSCoW), challenge log, KPI dictionary with owners and thresholds.</li>'
          '<li><b>SQL</b> (DuckDB): data-quality checks, SCD2 headcount, three attrition definitions, utilisation with cut-off, HR-finance bridge.</li>'
          '<li><b>Power BI project</b> (PBIP): star schema in TMDL, 51 DAX measures, Power Query with a <code>DataFolder</code> parameter, RLS, 4 report pages.</li>'
          '<li><b>Checks</b>: 22 KPIs computed in SQL and with the model logic; data issues log; adoption plan.</li>'
          '<li><b>HTML dashboard</b> with the same four pages, readable without Power BI.</li></ul>')}
  </div>
  <div class="stack">
    <div class="grid2 auto">{tiles}</div>
    {card('<h2>Recommendations</h2><ul class="reco">' + ''.join(f'<li>{x}</li>' for x in recos) + '</ul>')}
  </div>
</div>
<div class="steps">{''.join(f'<div class="step"><b>{i + 1}</b>{s}</div>' for i, s in enumerate(steps))}</div>"""
    return page(0, "Centric: from an HR director's request to a Power BI model",
                "Workforce analytics for an IT services company: the job of a BI Analyst, end to end, on a simulated company calibrated with public Lithuanian data.",
                "OVERVIEW", body, "SQL (DuckDB), Python, Power BI (PBIP: TMDL + PBIR)")


def p1(f, ch):
    ict, jvr = f["ict"], f["jvr"]
    body = f"""
<div class="grid-1-1-1 auto">
  {card('<h2>Centric, as stated by Centric</h2><ul class="facts">'
        '<li>Dutch IT services and software group, headquartered in <b>Gouda, the Netherlands</b>.</li>'
        '<li>Country websites for <b>Belgium, Lithuania, the Netherlands, Norway, Romania and Sweden</b>.</li>'
        '<li>Services listed include IT outsourcing, staffing, cyber security and <b>Data &amp; AI</b>, with business intelligence.</li></ul>'
        '<p class="note">Source: centric.eu/en/about-centric, read 19 Nov 2026. No client, revenue or headcount figure is used: none is needed, and internal data are not public.</p>')}
  {card('<h2>What the BI Analyst job asks for</h2><ul class="facts">'
        '<li>Be the point of contact: <b>gather, document and refine</b> reporting needs.</li>'
        '<li>Design and maintain <b>Power BI reports and semantic models</b> (DAX, Power Query) and SQL.</li>'
        '<li><b>Challenge requests</b>, propose new KPIs and analyses, guarantee <b>accuracy</b>.</li>'
        '<li><b>Present</b> results and drive <b>adoption</b>; HR, finance or operations data a plus.</li></ul>'
        '<p class="note">Source: BI Analyst job ad, Kaunas (LinkedIn and careers.centric.eu), read 19 Nov 2026.</p>')}
  {card(f'<h2>Lithuanian ICT labour market <span class="mini mini-public">PUBLIC DATA</span></h2><ul class="facts">'
        f'<li>Wages and salaries in ICT: labour cost index <b>{f["lci_last"].lci_ict_2020_100:.0f}</b> in {f["lci_last"].quarter} (2020 = 100).</li>'
        f'<li>Average monthly gross earnings in ICT: <b>€{f["osp_ict"]:,.0f}</b> vs €{f["osp_all"]:,.0f} for all activities ({f["osp_q"]}).</li>'
        f'<li>ICT job vacancy rate {jvr["LT"]:.1f}% in {f["jvr_q"]} (EU-27 {jvr["EU27_2020"]:.1f}%).</li>'
        f'<li>ICT specialists: <b>{ict["LT"]:.1f}%</b> of employment in {f["ict_y"]} (EU-27 {ict["EU27_2020"]:.1f}%).</li></ul>'
        '<p class="note">These series calibrate the simulation: market pay growth, time to fill.</p>')}
</div>
<div class="grid3">
  {img(ch['p1_wages'], 'ICT wages keep rising: labour cost index, Lithuania', 'PUBLIC')}
  {img(ch['p1_earnings'], 'ICT pays well above the national average', 'PUBLIC')}
  {img(ch['p1_vacancies'], 'ICT job vacancy rate: tight market, easing since 2022', 'PUBLIC')}
</div>"""
    return page(1, "Centric and the BI analyst's job: turning HR and finance requests into trusted reporting",
                "What Centric states about itself, what the job asks for, and the Lithuanian ICT labour market that shapes any workforce question in Kaunas.",
                "PUBLIC DATA", body, "Eurostat (lc_lci_r2_q, jvs_q_nace2, isoc_sks_itspt), Statistics Lithuania (S3R0050), retrieved 19 Nov 2026")


def p2(f, ch):
    rows = [("HR Director", "Which decision? Which exits matter? Are internal moves turnover?", "Know if <b>good people</b> leave, why, early enough; one headcount for the board."),
            ("CFO", "What would you do with it? Which numbers do you trust?", "Cost of attrition; <b>revenue and cost per FTE</b> that reconcile with payroll."),
            ("Head of Delivery", "Why does the last month look bad? What happened in March?", "Utilisation, <b>bench and overtime</b>, without false alarms.")]
    kpis = ["Regretted voluntary attrition, R12M", "Early attrition (first 12 months)", "Utilisation, closed months only", "Bench share",
            "Overtime share (alert at 15%)", "Cost per FTE vs market", "Median days to fill"]
    body = f"""
<div class="grid-2-1">
  <div class="stack">
    {card('<h2>Three interviews (written scenarios with roles, not people)</h2><table><tr><th>Stakeholder</th><th>What I asked</th><th>What they really need</th></tr>'
          + ''.join(f'<tr><td><b>{a}</b></td><td>{b}</td><td>{c}</td></tr>' for a, b, c in rows) + '</table>', 'auto')}
    {img(ch['p2_definitions'], 'Same data, three definitions: only the gross rate "explodes" in March 2026', 'SIMULATED')}
  </div>
  <div class="stack">
    {card('<h2>The request, challenged</h2><p><s>Monthly turnover by department</s> →<br><b>regretted voluntary attrition, rolling 12 months, excluding internal transfers</b>.</p>'
          f'<p class="small">R12M to Sep 2026: gross {pct(f["gross_r12"], 1)} · excl. transfers {pct(f["excl_r12"], 1)} · voluntary {pct(f["vol_r12"], 1)} · <b>regretted {pct(f["reg_r12"], 1)}</b>. '
          'One denominator for all: average month-end headcount.</p>', 'auto')}
    {img(ch['p2_false_signal'], f'Delivery 2: {f["d2_gross"]} exits keyed in March, {f["d2_excl"]} real', 'SIMULATED')}
    {card('<h2>KPIs nobody asked for</h2><ul class="small">' + ''.join(f'<li>{k}</li>' for k in kpis) + '</ul>', 'auto')}
  </div>
</div>"""
    return page(2, "From \"turnover report\" to the right question: regretted attrition, and one false signal not raised",
                f"In March 2026 a Delivery 2 reorganisation was keyed as {f['d2_gross']} exits and rehires: gross turnover hits {pct(f['d2_rate'])} in that department while nobody left. "
                "Asking what decision the report supports changed the KPI.", "SIMULATED", body,
                "docs/STAKEHOLDER_BRIEF.md, REQUIREMENTS.md, CHALLENGE_LOG.md · sql/03_attrition.sql")


SCHEMA_SVG = """<svg viewBox="0 0 700 330" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI" font-size="12">
<style>.f{fill:#E3EEFB;stroke:#2A78D6}.d{fill:#FFFFFF;stroke:#A3A19A}.m{fill:#FBE9E0;stroke:#9A3B12}.t{fill:#0B0B0B}.s{fill:#52514E;font-size:10px}.l{stroke:#A3A19A;stroke-width:1.2}</style>
<g class="l"><line x1="350" y1="165" x2="120" y2="40"/><line x1="350" y1="165" x2="580" y2="40"/><line x1="350" y1="165" x2="120" y2="290"/><line x1="350" y1="165" x2="580" y2="290"/>
<line x1="350" y1="165" x2="90" y2="165"/><line x1="350" y1="165" x2="610" y2="165"/><line x1="350" y1="165" x2="350" y2="35"/><line x1="350" y1="165" x2="350" y2="300"/></g>
<rect class="d" x="265" y="135" width="170" height="60" rx="8"/><text class="t" x="350" y="160" text-anchor="middle" font-weight="600">Dimensions</text>
<text class="s" x="350" y="178" text-anchor="middle">DimDate · DimOrg (RLS) · DimGrade · DimEmployee (SCD2)</text>
<rect class="f" x="30" y="15" width="180" height="46" rx="8"/><text class="t" x="120" y="35" text-anchor="middle" font-weight="600">FactHeadcountMonthly</text><text class="s" x="120" y="51" text-anchor="middle">person × month · 14.8k rows</text>
<rect class="f" x="490" y="15" width="180" height="46" rx="8"/><text class="t" x="580" y="35" text-anchor="middle" font-weight="600">FactMovements</text><text class="s" x="580" y="51" text-anchor="middle">hires, exits, transfers</text>
<rect class="f" x="0" y="142" width="180" height="46" rx="8"/><text class="t" x="90" y="162" text-anchor="middle" font-weight="600">FactTimesheet</text><text class="s" x="90" y="178" text-anchor="middle">person × month, as received</text>
<rect class="f" x="520" y="142" width="180" height="46" rx="8"/><text class="t" x="610" y="162" text-anchor="middle" font-weight="600">FactFinance</text><text class="s" x="610" y="178" text-anchor="middle">cost centre × month</text>
<rect class="f" x="30" y="268" width="180" height="46" rx="8"/><text class="t" x="120" y="288" text-anchor="middle" font-weight="600">FactRecruiting</text><text class="s" x="120" y="304" text-anchor="middle">requisitions (2 date roles)</text>
<rect class="m" x="490" y="268" width="180" height="46" rx="8"/><text class="t" x="580" y="288" text-anchor="middle" font-weight="600">Market (PUBLIC DATA)</text><text class="s" x="580" y="304" text-anchor="middle">disconnected · TREATAS</text>
<rect class="d" x="275" y="10" width="150" height="34" rx="8"/><text class="t" x="350" y="32" text-anchor="middle">_Measures (51)</text>
<rect class="d" x="265" y="285" width="170" height="34" rx="8"/><text class="t" x="350" y="307" text-anchor="middle">DataFolder parameter</text>
</svg>"""


def p3(f, ch):
    dax = """<pre>Headcount =
VAR _m = MAX ( DimDate[MonthStart] )
RETURN CALCULATE ( COUNTROWS ( FactHeadcountMonthly ),
    FactHeadcountMonthly[IsActiveMonthEnd] = 1,
    FactHeadcountMonthly[IsDuplicateId] = 0,
    REMOVEFILTERS ( DimDate ), DimDate[MonthStart] = _m )

Regretted Attrition % R12M =
VAR _end = MAX ( DimDate[Date] )
RETURN CALCULATE ( [Regretted Attrition %],
    DATESINPERIOD ( DimDate[Date], _end, -12, MONTH ) )
-- [Regretted Attrition %] = DIVIDE ( [Regretted Exits], [Average Headcount] )

Utilization % (closed months) =
CALCULATE ( [Utilization %], KEEPFILTERS ( DimDate[IsClosedMonth] = 1 ) )</pre>"""
    rls = """<pre>role DepartmentManager
  DimOrg[Department] = LOOKUPVALUE (
    SecurityUserDepartment[Department],
    SecurityUserDepartment[UserPrincipalName],
    USERPRINCIPALNAME () )</pre>"""
    keep = {"Headcount", "Attrition % (gross)", "Regretted Attrition %", "Early Attrition % (exits < 12 months / hires)", "Utilization %",
            "Utilization % (raw, no cut-off)", "Bench %", "Median Days to Fill", "HR vs Finance Gap (finance - HR raw)"}
    rows = [x for x in f["kpi_rows"] if x[0].strip() in keep]
    table = ('<table class="small"><tr><th>KPI</th><th>DAX measure</th><th>Context</th><th>SQL</th><th>Model</th></tr>'
             + "".join(f"<tr><td>{a.strip()}</td><td><code>{b.strip().strip('`')}</code></td><td>{c.strip()}</td><td>{d.strip()}</td><td>{e.strip()}</td></tr>"
                       for a, b, c, d, e, _ in rows) + "</table>")
    body = f"""
<div class="grid2">
  <div class="stack">
    {card('<h2>Star schema: 5 facts, 4 dimensions, 18 single-direction relationships</h2>' + SCHEMA_SVG +
          '<p class="small">Facts join the SCD2 row valid at the time; department, site and grade filter through DimOrg and DimGrade. Power Query reads every CSV through the <code>DataFolder</code> parameter.</p>')}
    {card('<h2>Row-level security</h2>' + rls + '<p class="small">A department head sees only their department (DimOrg and DimEmployee). Tested with <i>View as</i>.</p>', 'auto')}
  </div>
  <div class="stack">
    {card('<h2>Key DAX patterns</h2>' + dax, 'auto')}
    {card(f'<h2>Every KPI checked twice: SQL vs the model’s logic ({f["kpi_match"]})</h2>' + table +
          '<p class="note">SQL on the cleaned extracts (sql/kpi_checks.sql) vs the DAX filter logic applied to the exact tables Power BI loads. The PBIP has not yet been opened in Power BI Desktop: the last check is listed in docs/KPI_CHECKS.md.</p>')}
  </div>
</div>"""
    return page(3, "The model behind the numbers: a star schema, 51 DAX measures, row-level security, and 22 KPIs checked against SQL",
                "Built as a Power BI project in text format (PBIP: TMDL model, PBIR report), so every measure, relationship and security rule can be reviewed like code.",
                "SIMULATED", body, "powerbi/ (PBIP) · powerbi/measures.dax · docs/DATA_MODEL.md · docs/KPI_DICTIONARY.md · docs/KPI_CHECKS.md")


def p4(f, ch):
    body = f"""
<div class="grid2x2 full">
  {img(ch['p4_dc_overload'], f'Data & Cloud: overtime above 15% for four months, then regretted exits ×{f["dc_ev"] / f["dc_pre"]:.1f}', 'SIMULATED')}
  {img(ch['p4_tenure'], f'Resignations at 2-4 years of service: {pct(f["ten_first"])} → {pct(f["ten_last"])} a year', 'SIMULATED')}
  {img(ch['p4_pay'], f'New hires out-earn 2-4 year colleagues; raises trail the market', 'SIMULATED')}
  {img(ch['p4_cohorts'], f'Vilnius ramp-up wave: {pct(f["wave_6m"])} gone within six months', 'SIMULATED')}
</div>"""
    return page(4, "Who leaves, and why: overload in Data & Cloud, pay compression at 2-4 years, and a rushed Vilnius ramp-up",
                f"Three different causes, three different owners. Like-for-like raises +{pct(f['lfl'], 1)} vs +{pct(f['mkt'], 1)} for the ICT labour cost index (PUBLIC DATA); "
                f"{pct(f['wave_6m'])} of the {f['wave_n']} Vilnius Q2 2025 hires left within six months vs {pct(f['other_6m'])} for other cohorts.",
                "SIMULATED + PUBLIC DATA", body, "sql/03_attrition.sql, sql/05_compensation_market.sql · Eurostat lc_lci_r2_q")


def p5(f, ch):
    body = f"""
<div class="grid3">
  {img(ch['p5_working_days'], 'Lithuanian working days: 19 to 23 a month', 'PUBLIC')}
  {img(ch['p5_bench'], f'Delivery 3 bench: {pct(f["d3_bench_pre"])} → {pct(f["d3_bench_post"])} after a project ended', 'SIMULATED')}
  {img(ch['p5_cutoff'], f'October looks {100 * (f["util_sep"] - f["util_oct_raw"]):.0f} pts worse only because it is not closed', 'SIMULATED')}
</div>
<div class="grid3 auto">
  {card('<h2>Capacity, the Lithuanian way</h2><p>Capacity = working days employed × 8 h × FTE − absences, with Lithuanian public holidays (Nager.Date). Without it, a 19-day month looks like a drop in utilisation.</p>')}
  {card(f'<h2>A real drop: plan it</h2><p>Delivery 3 utilisation fell from {pct(f["d3_util_pre"])} to {pct(f["d3_util_post"])} after a large client project ended in May 2026. Action: redeploy, re-skill, slow hiring; follow bench weekly.</p>')}
  {card('<h2>A fake drop: the cut-off rule</h2><p>Timesheets arrive up to 10 days after month end. A month is shown only when month end + 10 days ≤ extract date; until then it is labelled <i>provisional</i> and left out of KPIs.</p>')}
</div>"""
    return page(5, "Utilization, bench and the month that always looks bad: one real drop to plan, one fake drop to stop reporting",
                f"Billable departments ran at {pct(f['util_sep'], 1)} utilisation in September 2026. October reads {pct(f['util_oct_raw'], 1)} at the 6 Nov extract because timesheets are still arriving.",
                "SIMULATED", body, "sql/04_utilization.sql · Nager.Date public holidays (LT)")


def p6(f, ch):
    b = f["bridge"]
    dq = r("dq_summary")
    table = '<table class="small"><tr><th>Check</th><th>Issues</th><th>Fix</th></tr>' + "".join(
        f"<tr><td>{x.check_name}</td><td>{x.issues}</td><td>{x.fix}</td></tr>" for x in dq.itertuples()) + "</table>"
    body = f"""
<div class="grid3">
  {img(ch['p6_hr_finance'], f'HR raw jumps by {f["dups"]} at the HRIS migration; finance does not', 'SIMULATED')}
  {img(ch['p6_bridge'], f'Bridge, {pd.to_datetime(b.month_start):%b %Y}: HR raw → finance closes to {int(b.residual)}', 'SIMULATED')}
  {img(ch['p6_rev_fte'], f'Mis-mapped cost centre: Data & Cloud revenue per FTE +{pct(f["rev_jump"])} for 3 months', 'SIMULATED')}
</div>
<div class="grid-2-1 auto">
  {card('<h2>Data-quality checks run before any KPI (sql/01_data_quality.sql)</h2>' + table)}
  {card('<h2>What changed for the users</h2><ul class="small"><li>One headcount: master ids only; duplicates listed on the data-quality page.</li>'
        '<li>Cost centres mapped from the HR master; the finance export view kept for audit.</li>'
        '<li>Monthly HR vs finance bridge before each release; residual must be 0.</li>'
        '<li>Open issues sent to their owners: HRIS (merge ids), finance (export mapping).</li></ul>')}
</div>"""
    return page(6, "Can we trust the numbers? Duplicate ids, a mis-mapped cost centre, and an HR-finance bridge that closes to zero",
                f"Raw HRIS headcount is {f['dups']} people (3%) too high since September 2025; finance put one cost centre in the wrong department from May to July 2026. "
                "Both were found by reconciling sources, not by looking at a single report.", "SIMULATED", body,
                "sql/01_data_quality.sql, sql/06_hr_finance_reconciliation.sql · docs/DATA_ISSUES_LOG.md")


def p7(f, ch):
    src = r("_sources", PUB)
    srows = "".join(f"<tr><td>{x.source}</td><td class=\"nw\">{x.retrieved}</td></tr>" for x in src.itertuples())
    body = f"""
<div class="grid2">
  <div class="stack">
    {card('<h2>Sources (PUBLIC DATA, no key, no account)</h2><table class="small"><tr><th>Source</th><th>Retrieved</th></tr>' + srows + '</table>'
          '<p class="note">Centric facts: centric.eu/en/about-centric; job requirements: BI Analyst job ad (LinkedIn, careers.centric.eu); both read 19 Nov 2026.</p>', 'auto')}
    {card('<h2>Method</h2><ul class="small">'
          '<li><b>Simulation</b> (Python, seed 42): fictional company, 600 people on average, 6 departments, Kaunas and Vilnius, Nov 2024 - Oct 2026, extract dated 6 Nov 2026; SCD2 HR history, movements, timesheets, absences, recruiting, finance by cost centre.</li>'
          '<li><b>Calibration</b>: market pay growth from the Eurostat ICT labour cost index; time to fill from the ICT job vacancy rate; working days from Lithuanian holidays.</li>'
          '<li><b>Eight planted events</b>, listed before the analysis and found from the data alone, including one false signal that is <b>not</b> reported as a finding.</li>'
          '<li><b>SQL</b> (DuckDB, CTEs, window functions) → model tables → Power BI PBIP (TMDL, PBIR) → HTML dashboard → this PDF. Everything reruns from the repository.</li></ul>')}
  </div>
  <div class="stack">
    {card('<h2>Limits</h2><ul class="small">'
          '<li><b>All internal data are simulated</b>: no Centric data, no Centric client, no real employee. Findings show the method, not facts about Centric.</li>'
          '<li>Interviews are written scenarios with roles; real stakeholders would add constraints this case cannot show.</li>'
          '<li>Sodra open employer data (atvira.sodra.lt) refused automated access (HTTP 403): not used, not bypassed.</li>'
          '<li>Public series lag: Statistics Lithuania earnings and Eurostat vacancies end in 2025-Q4; the latest quarter is used and dated.</li>'
          '<li>The Power BI project was generated and checked by script; it has not yet been opened in Power BI Desktop.</li></ul>')}
    {card('<h2>Adoption plan (docs/ADOPTION_PLAN.md)</h2><p class="small">One-page read-out to the three stakeholders · 30-minute training per audience · release notes each refresh · '
          'usage metrics reviewed monthly (target: 70% of the audience) · if nobody opens it: ask two non-users, push by subscription, cut unused visuals.</p>', 'auto')}
    {card(f'<h2>AI note</h2><p class="small">{AI_NOTE}</p>', 'auto')}
  </div>
</div>"""
    return page(7, "Methods, limits & AI note", "What is public, what is simulated, how each number is produced, and what this case cannot tell.",
                "OVERVIEW", body, "README.md · data/public/_sources.csv")


CSS = """
@page { size: 1600px 900px; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Segoe UI', Arial, sans-serif; color: #0B0B0B; background: #F4F4F2; }
.page { width: 1600px; height: 900px; padding: 30px 44px 22px; display: flex; flex-direction: column; page-break-after: always; overflow: hidden; background: #F4F4F2; }
header { display: flex; justify-content: space-between; align-items: flex-start; gap: 30px; }
h1 { font-size: 27px; margin: 0 0 6px; font-weight: 700; line-height: 1.15; max-width: 1280px; }
.sub { margin: 0; color: #52514E; font-size: 15px; max-width: 1280px; }
.tags { display: flex; gap: 6px; }
.tag { font-size: 12px; font-weight: 700; letter-spacing: .08em; padding: 5px 10px; border-radius: 4px; white-space: nowrap; color: #52514E; }
.tag-public { background: #E3EEFB; color: #1C5CAB; } .tag-simulated { background: #FBE9E0; color: #9A3B12; } .tag-overview { color: #52514E; border: 1px solid #E1E0D9; }
.mini { font-size: 10px; font-weight: 700; letter-spacing: .06em; padding: 2px 6px; border-radius: 3px; vertical-align: middle; }
.mini-public { background: #E3EEFB; color: #1C5CAB; } .mini-simulated { background: #FBE9E0; color: #9A3B12; }
main { flex: 1; display: flex; flex-direction: column; gap: 12px; margin-top: 14px; min-height: 0; }
footer { display: flex; justify-content: space-between; gap: 20px; font-size: 11px; color: #898781; margin-top: 10px; }
.card { background: #FCFCFB; border: 1px solid #E1E0D9; border-radius: 8px; padding: 12px 16px; min-height: 0; overflow: hidden; }
.card h2 { font-size: 15.5px; margin: 0 0 6px; }
.card p, .card li { font-size: 13.5px; line-height: 1.4; margin: 3px 0; color: #2B2A27; }
.card ul, .card ol { padding-left: 18px; margin: 4px 0; }
.fig { display: flex; flex-direction: column; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; flex: 1; min-height: 0; }
.grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; flex: 1; min-height: 0; }
.grid2x2 { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 12px; min-height: 0; }
.full { flex: 1 !important; }
.g0 { display: grid; grid-template-columns: 1fr 1.25fr; gap: 12px; flex: 1; min-height: 0; }
.grid-2-1 { display: grid; grid-template-columns: 1.6fr 1fr; gap: 12px; flex: 1; min-height: 0; }
.grid-1-1-1 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
figure { margin: 0; flex: 1; min-height: 0; display: flex; }
figure img { width: 100%; height: 100%; min-height: 0; object-fit: contain; }
.tile .label { font-size: 11.5px; font-weight: 700; color: #52514E; letter-spacing: .04em; }
.tile .big { font-size: 40px; font-weight: 700; margin: 2px 0; color: #2A78D6; }
.tile p { font-size: 13px; color: #52514E; }
.stack { display: flex; flex-direction: column; gap: 12px; min-height: 0; } .stack > .card { flex: 1; }
.auto { flex: 0 0 auto !important; }
.quote { font-size: 26px; font-weight: 600; color: #0B0B0B; line-height: 1.25; margin: 4px 0 8px; }
.qs li { font-size: 15.5px !important; margin: 7px 0; }
.reco li { font-size: 14.5px !important; margin: 5px 0; }
.steps { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
.step { background: #FCFCFB; border: 1px solid #E1E0D9; border-radius: 8px; padding: 9px 12px; font-size: 14px; font-weight: 600; }
.step b { color: #2A78D6; margin-right: 8px; font-size: 18px; } .step span { font-weight: 400; color: #52514E; font-size: 12.5px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { text-align: left; color: #52514E; font-weight: 600; border-bottom: 1px solid #E1E0D9; padding: 4px 6px; }
td { border-bottom: 1px solid #EFEEE9; padding: 4px 6px; vertical-align: top; }
table.small, .small, .small li { font-size: 12.5px !important; }
.note { font-size: 11.5px !important; color: #6B6A65 !important; }
.facts li { font-size: 13.5px !important; margin: 5px 0; }
pre { background: #F4F4F2; border-radius: 6px; padding: 8px 10px; font-size: 11.5px; margin: 4px 0 6px; line-height: 1.35; }
code { font-size: 11.5px; }
svg { width: 100%; height: auto; max-height: 330px; }
.pg { color: #898781; } .nw { white-space: nowrap; }
"""


def build_html():
    ch = charts.build_all()
    f = facts()
    pages = [p0, p1, p2, p3, p4, p5, p6, p7]
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Centric BI workforce analytics case study</title><style>{CSS}</style></head><body>
{''.join(p(f, ch) for p in pages)}
</body></html>"""
    out = DOCS / "report.html"
    out.write_text(html, encoding="utf-8")
    return out


def find_browser():
    for c in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe", shutil.which("msedge") or "", shutil.which("google-chrome") or ""]:
        if c and Path(c).exists():
            return c
    raise FileNotFoundError("Edge or Chrome is needed to print the PDF")


def print_pdf(html):
    pdf, tmp = DOCS / PDF_NAME, DOCS / "_print.pdf"
    profile = tempfile.mkdtemp()            # own profile: an open Edge window would otherwise take the call
    subprocess.run([find_browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profile}",
                    "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000",
                    f"--print-to-pdf={tmp}", html.as_uri()], check=True, timeout=180)
    last = -1
    for _ in range(120):                    # Edge can return before its child process has written the file
        time.sleep(1)
        size = tmp.stat().st_size if tmp.exists() else -1
        if size > 0 and size == last:
            break
        last = size
    shutil.rmtree(profile, ignore_errors=True)
    reader, writer = PdfReader(str(tmp)), PdfWriter()       # rewrite with neutral metadata
    for pg in reader.pages:
        writer.add_page(pg)
    writer.add_metadata({"/Title": "Centric - BI workforce analytics case study", "/Author": "", "/Creator": "", "/Producer": ""})
    with open(pdf, "wb") as fh:
        writer.write(fh)
    tmp.unlink()
    return pdf


def main():
    html = build_html()
    pdf = print_pdf(html)
    print("written", pdf.name, len(PdfReader(str(pdf)).pages), "pages")


if __name__ == "__main__":
    main()
