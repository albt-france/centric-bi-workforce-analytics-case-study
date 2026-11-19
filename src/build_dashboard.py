"""Self-contained interactive dashboard (one HTML file, Plotly embedded, works offline): dashboard/workforce_dashboard.html

Same four pages as the Power BI report, as tabs, with Site and Department filters. Reads data/model/*.csv (the tables
Power BI loads) and aggregates them by month and cost centre; every rate is recomputed in the browser for the selection.
    python src/build_dashboard.py
"""
import json
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "data" / "model"
OUT = ROOT / "dashboard"


def data():
    rd = lambda n: pd.read_csv(MODEL / f"{n}.csv")
    hc, mv, ts, fin, org, dd = rd("FactHeadcountMonthly"), rd("FactMovements"), rd("FactTimesheet"), rd("FactFinance"), rd("DimOrg"), rd("DimDate")
    months = sorted(hc.MonthStart.unique())
    mi = {m: i for i, m in enumerate(months)}
    mv["MonthStart"] = mv.Date.str[:7] + "-01"
    ccs = list(org.CostCenter)
    z = lambda: [0] * len(months)
    cc = {c: {k: z() for k in ["hc", "raw", "fte", "leavers", "cap", "bill", "bench", "ot", "logged", "gross", "excl", "vol", "reg", "hires",
                                "fin_hc", "rev", "rev_rep"]} for c in ccs}
    for r in hc.itertuples():
        a, i = cc[r.CostCenter], mi[r.MonthStart]
        if r.IsActiveMonthEnd:
            a["raw"][i] += 1
            if not r.IsDuplicateId:
                a["hc"][i] += 1
                a["fte"][i] += r.FTE
        elif not r.IsDuplicateId:
            a["leavers"][i] += 1
        if not r.IsDuplicateId:
            a["cap"][i] += r.CapacityHours
    for r in ts.itertuples():
        a, i = cc[r.CostCenter], mi[r.MonthStart]
        a["bill"][i] += r.BillableHours
        a["bench"][i] += r.BenchHours
        a["ot"][i] += r.OvertimeHours
        a["logged"][i] += r.BillableHours + r.BenchHours + r.NonBillableHours
    for r in mv.itertuples():
        if r.MonthStart not in mi:
            continue
        a, i = cc[r.CostCenter], mi[r.MonthStart]
        if r.MovementType == "Exit":
            a["gross"][i] += 1
            if not r.IsInternalTransfer:
                a["excl"][i] += 1
                a["vol"][i] += r.IsVoluntary
            a["reg"][i] += int(r.IsVoluntary and r.IsRegretted)
        elif r.MovementType == "Hire" and not r.IsInternalTransfer:
            a["hires"][i] += 1
    dept_of = org.set_index("CostCenter").Department
    for r in fin.itertuples():
        i = mi[r.MonthStart]
        cc[r.CostCenter]["fin_hc"][i] += r.PayrollHeadcount
        cc[r.CostCenter]["rev"][i] += r.Revenue
    # revenue as reported by finance: re-assign the cost centre's revenue to the reported department's cost centre of the same site
    for r in fin.itertuples():
        if r.DepartmentReported != dept_of[r.CostCenter]:
            target = org[(org.Department == r.DepartmentReported) & (org.Site == org.set_index("CostCenter").Site[r.CostCenter])].CostCenter.iloc[0]
        else:
            target = r.CostCenter
        cc[target]["rev_rep"][mi[r.MonthStart]] += r.Revenue
    for c in cc.values():
        for k in c:
            c[k] = [round(v, 1) for v in c[k]]
    ex = mv[(mv.MovementType == "Exit") & (mv.IsVoluntary == 1)]
    reasons = ex.groupby(["CostCenter", "ExitReason"]).agg(n=("MovementId", "count"), reg=("IsRegretted", "sum")).reset_index()
    tenure = ex.assign(half=pd.cut(pd.to_datetime(ex.Date), pd.to_datetime(["2024-10-31", "2025-04-30", "2025-10-31", "2026-04-30", "2026-10-31"]),
                                   labels=["Nov24-Apr25", "May-Oct25", "Nov25-Apr26", "May-Oct26"]).astype(str)) \
        .groupby(["CostCenter", "half", "TenureBand"]).size().reset_index(name="n")
    hct = hc[(hc.IsActiveMonthEnd == 1) & (hc.IsDuplicateId == 0)].copy()
    hct["half"] = pd.cut(pd.to_datetime(hct.MonthStart), pd.to_datetime(["2024-10-31", "2025-04-30", "2025-10-31", "2026-04-30", "2026-10-31"]),
                         labels=["Nov24-Apr25", "May-Oct25", "Nov25-Apr26", "May-Oct26"]).astype(str)
    tenure_hc = hct.groupby(["CostCenter", "half", "TenureBand"]).size().div(6).round(2).reset_index(name="avg_hc")
    closed = dd.drop_duplicates("MonthStart").set_index("MonthStart").IsClosedMonth.reindex(months).astype(int).tolist()
    fclosed = dd.drop_duplicates("MonthStart").set_index("MonthStart").IsFinanceClosedMonth.reindex(months).astype(int).tolist()
    return {"months": [pd.Timestamp(m).strftime("%b %y") for m in months], "closed": closed, "fclosed": fclosed,
            "org": json.loads(org[["CostCenter", "Department", "Site", "IsBillable"]].to_json(orient="records")), "cc": cc,
            "reasons": json.loads(reasons.to_json(orient="records")), "tenure": json.loads(tenure.to_json(orient="records")),
            "tenure_hc": json.loads(tenure_hc.to_json(orient="records"))}


HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Workforce Analytics Dashboard</title>
<style>
:root { color-scheme: light; --bg:#F4F4F2; --card:#FCFCFB; --line:#E1E0D9; --ink:#0B0B0B; --muted:#52514E; --accent:#2A78D6; --red:#D03B3B; --grey:#A3A19A; --sim:#FBE9E0; --simt:#9A3B12; --pub:#E3EEFB; --pubt:#1C5CAB; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark; --bg:#141413; --card:#1A1A19; --line:#33322F; --ink:#F0EFEC; --muted:#C3C2B7; --accent:#3987E5; --red:#E66767; --grey:#8A897F; --sim:#40261A; --simt:#F2B89C; --pub:#1C2E45; --pubt:#9CC3F2; } }
:root[data-theme="dark"] { color-scheme: dark; --bg:#141413; --card:#1A1A19; --line:#33322F; --ink:#F0EFEC; --muted:#C3C2B7; --accent:#3987E5; --red:#E66767; --grey:#8A897F; --sim:#40261A; --simt:#F2B89C; --pub:#1C2E45; --pubt:#9CC3F2; }
* { box-sizing:border-box; }
body { margin:0; font-family:'Segoe UI', Arial, sans-serif; background:var(--bg); color:var(--ink); }
.wrap { max-width:1280px; margin:0 auto; padding:20px 16px 40px; }
h1 { font-size:22px; margin:0 0 4px; } .sub { color:var(--muted); margin:0 0 12px; font-size:14px; }
.bar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-bottom:12px; }
nav { display:flex; gap:6px; flex-wrap:wrap; }
button, select { border:1px solid var(--line); background:var(--card); color:var(--ink); padding:7px 12px; border-radius:6px; font:inherit; font-size:14px; }
nav button { cursor:pointer; } nav button.on { background:var(--accent); color:#fff; border-color:var(--accent); }
label { font-size:13px; color:var(--muted); display:flex; gap:6px; align-items:center; }
.tab { display:none; } .tab.on { display:block; }
.grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 460px), 1fr)); gap:12px; }
.kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin-bottom:12px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px 14px; min-width:0; }
.card h2 { font-size:15px; margin:0 0 6px; } .k .v { font-size:28px; font-weight:700; } .k .l { font-size:12px; color:var(--muted); font-weight:600; }
.concl { font-size:14px; color:var(--muted); margin:0 0 12px; }
.tag { font-size:11px; font-weight:700; letter-spacing:.06em; padding:3px 7px; border-radius:4px; background:var(--sim); color:var(--simt); }
.plot { width:100%; height:300px; }
table { border-collapse:collapse; width:100%; font-size:13px; } th, td { text-align:left; padding:4px 6px; border-bottom:1px solid var(--line); }
footer { margin-top:18px; font-size:12px; color:var(--muted); }
</style></head><body><div class="wrap">
<h1>Workforce analytics: fictional 600-person IT services company <span class="tag">SIMULATED</span></h1>
<p class="sub">Companion to the Power BI model. Kaunas and Vilnius, Nov 2024 - Oct 2026, extract taken on 6 Nov 2026. Not Centric data.</p>
<div class="bar"><nav>
 <button data-t="t1" class="on">Executive overview</button><button data-t="t2">Attrition deep dive</button>
 <button data-t="t3">Utilization &amp; bench</button><button data-t="t4">Data quality &amp; reconciliation</button></nav>
 <label>Site <select id="fSite"><option>All</option><option>Kaunas</option><option>Vilnius</option></select></label>
 <label>Department <select id="fDept"><option>All</option></select></label>
</div>
<section id="t1" class="tab on">
 <p class="concl">Headline KPI agreed with the HR Director: regretted voluntary attrition over 12 rolling months, excluding internal transfers. Rates use the average month-end headcount; utilisation uses closed months only.</p>
 <div class="kpis" id="k1"></div>
 <div class="grid"><div class="card"><h2>Voluntary and regretted attrition, rolling 12 months</h2><div id="p1a" class="plot"></div></div>
 <div class="card"><h2>Headcount at month end (duplicate ids excluded)</h2><div id="p1b" class="plot"></div></div>
 <div class="card"><h2>Voluntary attrition by department, last 12 months</h2><div id="p1c" class="plot"></div></div>
 <div class="card"><h2>Utilisation (closed months) and bench share</h2><div id="p1d" class="plot"></div></div></div>
</section>
<section id="t2" class="tab">
 <p class="concl">March 2026: gross turnover jumps because a Delivery 2 reorganisation was keyed as exits + rehires; excluding transfers nothing moves. Do not escalate it.</p>
 <div class="grid"><div class="card"><h2>Monthly attrition under three definitions</h2><div id="p2a" class="plot"></div></div>
 <div class="card"><h2>Overtime share and regretted resignations (filter Data &amp; Cloud)</h2><div id="p2b" class="plot"></div></div>
 <div class="card"><h2>Resignations by length of service (annualised rate)</h2><div id="p2c" class="plot"></div></div>
 <div class="card"><h2>Exit reasons (resignations)</h2><div id="p2d"></div></div></div>
</section>
<section id="t3" class="tab">
 <p class="concl">October 2026 is provisional: timesheets arrive up to 10 days after month end. Delivery 3 bench rose to about 18% after a client project ended in May 2026.</p>
 <div class="kpis" id="k3"></div>
 <div class="grid"><div class="card"><h2>Utilisation with and without the cut-off rule</h2><div id="p3a" class="plot"></div></div>
 <div class="card"><h2>Bench share by department</h2><div id="p3b" class="plot"></div></div>
 <div class="card"><h2>Overtime share by department (alert above 15%)</h2><div id="p3c" class="plot"></div></div></div>
</section>
<section id="t4" class="tab">
 <p class="concl">18 duplicate ids since the HRIS migration (Sep 2025); one cost centre mis-mapped by finance (May-Jul 2026). The HR to finance bridge closes to zero.</p>
 <div class="kpis" id="k4"></div>
 <div class="grid"><div class="card"><h2>HR raw, HR clean and finance headcount</h2><div id="p4a" class="plot"></div></div>
 <div class="card"><h2>Revenue per FTE: finance export vs cost-centre master (filter Data &amp; Cloud or Delivery 1)</h2><div id="p4b" class="plot"></div></div>
 <div class="card"><h2>Bridge, last closed finance month</h2><div id="p4c" class="plot"></div></div></div>
</section>
<footer>SIMULATED data (seed 42) for a fictional company · Working days: Lithuanian public holidays (Nager.Date, PUBLIC DATA) · Independent case study based on public data · not affiliated with or endorsed by Centric</footer>
</div>
<script>__PLOTLY__</script>
<script>
const D = __DATA__;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const N = D.months.length, idx = [...Array(N).keys()];
const deptSel = document.getElementById('fDept');
[...new Set(D.org.map(o => o.Department))].forEach(d => { const o = document.createElement('option'); o.textContent = d; deptSel.appendChild(o); });
const pct = (v, d=1) => v == null || isNaN(v) ? '–' : (100 * v).toFixed(d) + '%';
const fmt = v => v == null || isNaN(v) ? '–' : Math.round(v).toLocaleString('en-US');
function sel(extra) {
  const s = document.getElementById('fSite').value, d = deptSel.value;
  return D.org.filter(o => (s === 'All' || o.Site === s) && (d === 'All' || o.Department === d) && (!extra || extra(o))).map(o => o.CostCenter);
}
function sum(key, ccs) { const out = Array(N).fill(0); ccs.forEach(c => D.cc[c][key].forEach((v, i) => out[i] += v)); return out; }
const div = (a, b) => a.map((v, i) => (v != null && b[i]) ? v / b[i] : null);
const roll = (num, den) => idx.map(i => { if (i < 11) return null; let n = 0, h = 0; for (let j = i - 11; j <= i; j++) { n += num[j]; h += den[j]; } return h ? n / (h / 12) : null; });
const layout = (extra={}) => Object.assign({ margin:{l:48, r:16, t:8, b:40}, paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Segoe UI, Arial', size:12, color:css('--muted')}, legend:{orientation:'h', y:-0.2},
  xaxis:{gridcolor:css('--line')}, yaxis:{gridcolor:css('--line'), zerolinecolor:css('--line')} }, extra);
const P = (id, traces, extra) => Plotly.react(id, traces, layout(extra), {displayModeBar:false, responsive:true});
const line = (y, name, color, dash) => ({x:D.months, y, name, type:'scatter', mode:'lines', line:{color, width:2, dash}});
const kpi = (el, items) => document.getElementById(el).innerHTML = items.map(([l, v]) => `<div class="card k"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');
const COL = {'Delivery 1':'#86B6EF', 'Delivery 2':'#5598E7', 'Delivery 3':'#D03B3B', 'Data & Cloud':'#EB6834', 'Sales':'#A3A19A', 'Support functions':'#52514E'};
const last = a => { for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null; };
const lastClosed = D.closed.lastIndexOf(1), lastFin = D.fclosed.lastIndexOf(1);

function render() {
  const ccs = sel(), bill = sel(o => o.IsBillable === 1);
  const hc = sum('hc', ccs), reg = sum('reg', ccs), vol = sum('vol', ccs), gross = sum('gross', ccs), excl = sum('excl', ccs);
  const capB = sum('cap', bill), billB = sum('bill', bill), benchB = sum('bench', bill), otB = sum('ot', bill), logB = sum('logged', bill);
  const util = div(billB, capB), utilClosed = util.map((v, i) => D.closed[i] ? v : null), bench = div(benchB, capB);
  const r12reg = roll(reg, hc), r12vol = roll(vol, hc);
  // tab 1
  kpi('k1', [['Headcount, Oct 26', fmt(hc[N-1])], ['Regretted attrition R12M', pct(r12reg[N-1])], ['Voluntary attrition R12M', pct(r12vol[N-1])],
             ['Utilisation, ' + D.months[lastClosed], pct(util[lastClosed])], ['Bench share, ' + D.months[lastClosed], pct(bench[lastClosed])]]);
  P('p1a', [line(r12reg, 'Regretted R12M', css('--accent')), line(r12vol, 'Voluntary R12M', css('--grey'), 'dash')], {yaxis:{tickformat:'.0%', gridcolor:css('--line')}});
  P('p1b', [{x:D.months, y:hc, type:'bar', name:'Headcount', marker:{color:css('--accent')}}], {});
  const depts = [...new Set(D.org.filter(o => ccs.includes(o.CostCenter)).map(o => o.Department))];
  const dv = depts.map(d => { const c = ccs.filter(x => D.org.find(o => o.CostCenter === x).Department === d); return roll(sum('vol', c), sum('hc', c))[N-1]; });
  P('p1c', [{y:depts, x:dv, type:'bar', orientation:'h', marker:{color:css('--accent')}, text:dv.map(v => pct(v)), textposition:'outside'}],
    {xaxis:{tickformat:'.0%', gridcolor:css('--line')}, yaxis:{autorange:'reversed'}, margin:{l:120, r:60, t:8, b:30}, cliponaxis:false});
  P('p1d', [line(utilClosed, 'Utilisation (closed months)', css('--accent')), line(bench, 'Bench', css('--red'), 'dot')], {yaxis:{tickformat:'.0%', gridcolor:css('--line')}});
  // tab 2
  P('p2a', [line(div(gross, hc), 'Gross', css('--red')), line(div(excl, hc), 'Excl. transfers', css('--accent')), line(div(vol, hc), 'Voluntary', css('--grey'), 'dash')],
    {yaxis:{tickformat:'.0%', gridcolor:css('--line')}});
  P('p2b', [{x:D.months, y:reg, type:'bar', name:'Regretted resignations (right)', marker:{color:'#C9DDF5'}},
            Object.assign(line(div(sum('ot', bill.filter(c => ccs.includes(c))), sum('cap', bill.filter(c => ccs.includes(c)))), 'Overtime / capacity (left)', css('--red')), {yaxis:'y2'})],
    {yaxis:{side:'right', showgrid:false, rangemode:'tozero'}, yaxis2:{overlaying:'y', side:'left', tickformat:'.0%', range:[0, 0.22], gridcolor:css('--line')},
     shapes:[{type:'line', xref:'paper', yref:'y2', x0:0, x1:1, y0:0.15, y1:0.15, line:{color:css('--red'), dash:'dash', width:1}}]});
  const halves = ['Nov24-Apr25', 'May-Oct25', 'Nov25-Apr26', 'May-Oct26'], bands = ['0-1 y', '1-2 y', '2-4 y', '4+ y'];
  const tcol = ['#E1E0D9', '#A3A19A', '#86B6EF', '#2A78D6'];
  P('p2c', halves.map((h, k) => ({x:bands, name:h, type:'bar', marker:{color:tcol[k]}, y:bands.map(b => {
      const n = D.tenure.filter(r => ccs.includes(r.CostCenter) && r.half === h && r.TenureBand === b).reduce((s, r) => s + r.n, 0);
      const a = D.tenure_hc.filter(r => ccs.includes(r.CostCenter) && r.half === h && r.TenureBand === b).reduce((s, r) => s + r.avg_hc, 0);
      return a ? 2 * n / a : null; })})), {yaxis:{tickformat:'.0%', gridcolor:css('--line')}, barmode:'group'});
  const rs = {}; D.reasons.filter(r => ccs.includes(r.CostCenter)).forEach(r => { rs[r.ExitReason] = rs[r.ExitReason] || [0, 0]; rs[r.ExitReason][0] += r.n; rs[r.ExitReason][1] += r.reg; });
  document.getElementById('p2d').innerHTML = '<table><tr><th>Reason</th><th>Resignations</th><th>Regretted</th></tr>' +
    Object.entries(rs).sort((a, b) => b[1][0] - a[1][0]).map(([k, v]) => `<tr><td>${k}</td><td>${v[0]}</td><td>${v[1]}</td></tr>`).join('') + '</table>';
  // tab 3
  kpi('k3', [['Utilisation, ' + D.months[lastClosed] + ' (closed)', pct(util[lastClosed])], ['Utilisation, ' + D.months[N-1] + ' (raw)', pct(util[N-1])],
             ['Timesheets received, ' + D.months[N-1], pct(logB[N-1] / capB[N-1])], ['Overtime, ' + D.months[lastClosed], pct(otB[lastClosed] / capB[lastClosed])]]);
  P('p3a', [line(util, 'Raw: every month as received', css('--grey'), 'dash'), line(utilClosed, 'Closed months only', css('--accent'))], {yaxis:{tickformat:'.0%', gridcolor:css('--line')}});
  const bd = [...new Set(D.org.filter(o => bill.includes(o.CostCenter)).map(o => o.Department))];
  P('p3b', bd.map(d => { const c = bill.filter(x => D.org.find(o => o.CostCenter === x).Department === d); return line(div(sum('bench', c), sum('cap', c)).map((v, i) => D.closed[i] ? v : null), d, COL[d]); }),
    {yaxis:{tickformat:'.0%', gridcolor:css('--line')}});
  P('p3c', bd.map(d => { const c = bill.filter(x => D.org.find(o => o.CostCenter === x).Department === d); return line(div(sum('ot', c), sum('cap', c)).map((v, i) => D.closed[i] ? v : null), d, COL[d]); }),
    {yaxis:{tickformat:'.0%', gridcolor:css('--line')}, shapes:[{type:'line', xref:'paper', x0:0, x1:1, y0:0.15, y1:0.15, line:{color:css('--red'), dash:'dash', width:1}}]});
  // tab 4
  const raw = sum('raw', ccs), fin = sum('fin_hc', ccs).map((v, i) => D.fclosed[i] ? v : null), lv = sum('leavers', ccs), fte = sum('fte', ccs);
  kpi('k4', [['Duplicate ids, Oct 26', fmt(raw[N-1] - hc[N-1])], ['HR raw, ' + D.months[lastFin], fmt(raw[lastFin])], ['Finance paid, ' + D.months[lastFin], fmt(fin[lastFin])],
             ['Finance - HR raw', fmt(fin[lastFin] - raw[lastFin])]]);
  P('p4a', [line(raw, 'HR raw HRIS', css('--red')), line(hc, 'HR clean', css('--accent')), line(fin, 'Finance (people paid)', css('--grey'), 'dash')], {});
  const rev = sum('rev', ccs).map((v, i) => D.fclosed[i] ? v : null), revRep = sum('rev_rep', ccs).map((v, i) => D.fclosed[i] ? v : null);
  P('p4b', [{x:D.months, y:div(revRep, fte), type:'bar', name:'As exported by finance', marker:{color:'#C9DDF5'}}, line(div(rev, fte), 'Cost-centre master', css('--accent'))],
    {yaxis:{tickformat:',.0f', tickprefix:'€', gridcolor:css('--line')}});
  const dup = raw[lastFin] - hc[lastFin];
  P('p4c', [{type:'waterfall', x:['HR raw', 'Duplicate ids', 'Leavers paid in month', 'Finance headcount', 'Unexplained'],
             measure:['absolute', 'relative', 'relative', 'total', 'relative'], y:[raw[lastFin], -dup, lv[lastFin], 0, fin[lastFin] - (raw[lastFin] - dup + lv[lastFin])],
             connector:{line:{color:css('--line')}}, increasing:{marker:{color:'#1BAF7A'}}, decreasing:{marker:{color:css('--red')}}, totals:{marker:{color:css('--accent')}}}],
    {showlegend:false, yaxis:{range:[Math.min(fin[lastFin], raw[lastFin]) - 40, raw[lastFin] + 15], gridcolor:css('--line')}});
}
document.querySelectorAll('nav button').forEach(b => b.onclick = () => {
  document.querySelectorAll('nav button').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.id === b.dataset.t));
  document.querySelectorAll('#' + b.dataset.t + ' .js-plotly-plot').forEach(el => Plotly.Plots.resize(el));
});
['fSite', 'fDept'].forEach(id => document.getElementById(id).onchange = render);
render();
const h0 = location.hash.slice(1); if (h0) { const b = document.querySelector('nav button[data-t="' + h0 + '"]'); if (b) b.click(); }
</script></body></html>"""


def main():
    OUT.mkdir(exist_ok=True)
    html = HTML.replace("__PLOTLY__", get_plotlyjs()).replace("__DATA__", json.dumps(data()))
    (OUT / "workforce_dashboard.html").write_text(html, encoding="utf-8")
    print("dashboard written:", round(len(html) / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
