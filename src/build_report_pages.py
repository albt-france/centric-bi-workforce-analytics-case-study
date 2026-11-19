"""Generate the four Power BI report pages (PBIR format) in powerbi/CentricWorkforce.Report.

    python src/build_report_pages.py
Close Power BI Desktop first: every page is rewritten from this script. Page size 1920 x 1080.
"""
import json, shutil, sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1] / "powerbi" / "CentricWorkforce.Report"
PAGES = REPORT / "definition" / "pages"
VC_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json"
M = "_Measures"

# ink & palette (validated reference palette, light mode)
INK, INK2, MUTED = "#0B0B0B", "#52514E", "#898781"
BLUE = "#2A78D6"
SEQ = {"100": "#CDE2FB", "250": "#86B6EF", "350": "#5598E7", "450": "#2A78D6", "650": "#104281"}
NEUTRAL, RED_TINT, BLUE_TINT = "#F0EFEC", "#F4C7C6", "#B7D3F6"
AUTHOR = "Independent case study based on public data · not affiliated with or endorsed by Centric"


# ---------- expression helpers ----------
def raw(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (int, float)):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"Literal": {"Value": s}}

def lit(v):
    return {"expr": raw(v)}

def color(hexv):
    return {"solid": {"color": lit(hexv)}}

def col(table, column):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}}

def meas(name):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": M}}, "Property": name}}

def agg_sum(table, column):
    return {"Aggregation": {"Expression": col(table, column), "Function": 0}}

def qref(field):
    if "Column" in field:
        c = field["Column"]
        return f'{c["Expression"]["SourceRef"]["Entity"]}.{c["Property"]}'
    if "Measure" in field:
        return f'{M}.{field["Measure"]["Property"]}'
    c = field["Aggregation"]["Expression"]["Column"]
    return f'Sum({c["Expression"]["SourceRef"]["Entity"]}.{c["Property"]})'

def proj(field, label=None):
    p = {"field": field, "queryRef": qref(field)}
    if "Column" in field:
        p["nativeQueryRef"] = field["Column"]["Property"]
    elif "Measure" in field:
        p["nativeQueryRef"] = field["Measure"]["Property"]
    else:
        p["nativeQueryRef"] = "Sum of " + field["Aggregation"]["Expression"]["Column"]["Property"]
        p["displayName"] = field["Aggregation"]["Expression"]["Column"]["Property"]
    if label:
        p["displayName"] = label
    return p

def C(t, c): return col(t, c)
def Ms(*names): return [meas(n) for n in names]

def series_color(field, hexv):
    return {"properties": {"fill": color(hexv)}, "selector": {"metadata": qref(field)}}

def ref_line(value, label, hexv=INK2, selector_id="1"):
    v = {"expr": value} if isinstance(value, dict) else lit(value)
    return {"properties": {"show": lit(True), "value": v, "displayName": lit(label), "lineColor": color(hexv),
                           "style": lit("dashed"), "dataLabelShow": lit(True), "dataLabelColor": color(hexv)},
            "selector": {"id": selector_id}}

def bg_rule(field, lo, hi, mid=None, mid_value=None):
    """Background-colour scale (conditional formatting) on a table/matrix value column."""
    rule = {"min": {"color": raw(lo)}, "max": {"color": raw(hi)},
            "nullColoringStrategy": {"strategy": raw("asZero")}}
    key = "linearGradient2"
    if mid:
        key = "linearGradient3"
        rule["mid"] = {"color": raw(mid)}
        if mid_value is not None:
            rule["mid"]["value"] = raw(mid_value)
    return {"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {"Input": field, "FillRule": {key: rule}}}}}}},
            "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": qref(field)}}


def table_style(extra_values=(), matrix=False):
    """Readable table: 12pt text, no misleading total row/column."""
    fs = {"properties": {"fontSize": lit(12)}}
    objs = {"values": [fs, *extra_values], "columnHeaders": [{"properties": {"fontSize": lit(12), "fontColor": color(INK2)}}]}
    if matrix:
        objs["rowHeaders"] = [fs]
        objs["subTotals"] = [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}]
    else:
        objs["total"] = [{"properties": {"totals": lit(False)}}]
    return objs


# ---------- page / visual builders ----------
class Page:
    def __init__(self, pid, name):
        self.pid, self.name, self.visuals, self.interactions, self.n = pid, name, [], [], 0

    def _add(self, vid, x, y, w, h, visual):
        self.n += 1
        self.visuals.append({"$schema": VC_SCHEMA, "name": vid,
                             "position": {"x": round(x), "y": round(y), "z": self.n * 1000,
                                          "height": round(h), "width": round(w), "tabOrder": self.n * 1000},
                             "visual": visual})
        return vid

    def chart(self, vid, vtype, x, y, w, h, roles, title=None, objects=None, labels=None,
              sort=None, exclude_organic=False, only=None):
        labels = labels or {}
        visual = {"visualType": vtype,
                  "query": {"queryState": {r: {"projections": [proj(f, labels.get(qref(f))) for f in fs]}
                                           for r, fs in roles.items() if fs}},
                  "drillFilterOtherVisuals": True}
        if sort:
            field, direction = sort
            visual["query"]["sortDefinition"] = {"sort": [{"field": field, "direction": direction}],
                                                 "isDefaultSort": False}
        if objects:
            visual["objects"] = objects
        vco = {"subTitle": [{"properties": {"show": lit(False)}}]}
        vco["title"] = [{"properties": {"show": lit(bool(title)), **({"text": lit(title)} if title else {})}}]
        visual["visualContainerObjects"] = vco
        vid = self._add(vid, x, y, w, h, visual)
        if exclude_organic:
            only = ("Channel", "channel", ["Organic"], True)
        if only:
            table, column, values, negate = only
            cond = {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                           "Values": [[{"Literal": {"Value": f"{v}L"}} if isinstance(v, int) and not isinstance(v, bool) else raw(v)] for v in values]}}
            if negate:
                cond = {"Not": {"Expression": cond}}
            self.visuals[-1]["filterConfig"] = {"filters": [{
                "name": "visualFilter", "type": "Categorical", "field": col(table, column),
                "filter": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                           "Where": [{"Condition": cond}]}}]}
        return vid

    def text(self, vid, x, y, w, h, paragraphs, boxed=False):
        """paragraphs: list of paragraphs; each paragraph = list of (text, size, colour, bold) runs."""
        paras = [{"textRuns": [{"value": t, "textStyle": {"fontSize": f"{s}pt", "color": c,
                                                         **({"fontWeight": "bold"} if b else {})}}
                               for t, s, c, b in runs]} for runs in paragraphs]
        visual = {"visualType": "textbox",
                  "objects": {"general": [{"properties": {"paragraphs": paras}}]},
                  "visualContainerObjects": {"background": [{"properties": {"show": lit(boxed)}}],
                                             "border": [{"properties": {"show": lit(boxed)}}],
                                             **({"padding": [{"properties": {"top": lit(16), "bottom": lit(16),
                                                                             "left": lit(20), "right": lit(20)}}]}
                                                if boxed else {})}}
        return self._add(vid, x, y, w, h, visual)

    def header(self, title, conclusion, tag):
        self.text("title", 32, 20, 1500, 56, [[(title, 24, INK, True)]])
        self.text("tag", 1540, 28, 348, 40, [[(tag, 10, INK2, True)]])
        self.text("conclusion", 32, 76, 1856, 64, [[(conclusion, 13, INK2, False)]])

    def footer(self, source):
        self.text("footer", 32, 1040, 1856, 32, [[(source + "   ·   " + AUTHOR, 9, MUTED, False)]])

    def slicer(self, vid, x, y, w, h, field, title, dropdown=True, single=False):
        objs = {"header": [{"properties": {"show": lit(False)}}]}
        if dropdown:
            objs["data"] = [{"properties": {"mode": lit("Dropdown")}}]
        if single:
            objs["selection"] = [{"properties": {"singleSelect": lit(True), "strictSingleSelect": lit(True)}}]
        return self.chart(vid, "slicer", x, y, w, h, {"Values": [field]}, title, objs)

    def card(self, vid, x, y, w, h, measure, title, only=None):
        return self.chart(vid, "card", x, y, w, h, {"Values": [meas(measure)]}, title,
                          {"labels": [{"properties": {"color": color(INK), "fontSize": lit(28)}}],
                           "categoryLabels": [{"properties": {"show": lit(False)}}]}, only=only)

    def no_filter(self, source, target):
        self.interactions.append({"source": source, "target": target, "type": "NoFilter"})

    def write(self):
        d = PAGES / self.pid
        if d.exists():
            shutil.rmtree(d)
        (d / "visuals").mkdir(parents=True)
        page = {"$schema": PAGE_SCHEMA, "name": self.pid, "displayName": self.name,
                "displayOption": "FitToPage", "height": 1080, "width": 1920}
        if self.interactions:
            page["visualInteractions"] = self.interactions
        (d / "page.json").write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding="utf-8")
        for v in self.visuals:
            vd = d / "visuals" / v["name"]
            vd.mkdir()
            (vd / "visual.json").write_text(json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- layout grid ----------
L, R, TOP, BOT, GAP = 32, 1888, 156, 1028, 24
W = R - L

def cols(n, x0=L, x1=R):
    w = (x1 - x0 - (n - 1) * GAP) / n
    return [(x0 + i * (w + GAP), w) for i in range(n)]

def kpi_row(p, items, y=TOP, h=120, x0=L, x1=R, only=None):
    for (x, w), (m, t) in zip(cols(len(items), x0, x1), items):
        p.card("kpi_" + "".join(ch for ch in m if ch.isalnum())[:30], x, y, w, h, m, t, only=only)
    return y + h + GAP

# ---------- fields ----------
MONTH = C("DimDate", "MonthLabel")
DEPT, SITE, GRADE = C("DimOrg", "Department"), C("DimOrg", "Site"), C("DimGrade", "GradeName")
BY_MONTH = (MONTH, "Ascending")
SRC_SIM = "SIMULATED data (fictional 600-person IT services company, seed 42) - not Centric data"
SRC_MIX = SRC_SIM + "  ·  PUBLIC DATA: Eurostat, Statistics Lithuania, Nager.Date"
pages = []


def slicers(p, y=TOP):
    p.slicer("slicerSite", L, y, 300, 70, SITE, "Site")
    p.slicer("slicerDept", L + 324, y, 340, 70, DEPT, "Department")
    p.slicer("slicerMonth", L + 688, y, 340, 70, MONTH, "Month (cards show the last month selected)")
    return y + 70 + GAP


# ======================= Page 1 - Executive overview =======================
p = Page("c1a0000000000000exec", "Executive overview")
p.header("Executive overview: regretted attrition, not monthly turnover",
         "The HR Director asked for 'monthly turnover by department'. The agreed headline is regretted voluntary attrition over "
         "12 rolling months, excluding internal transfers, next to the utilisation and bench that drive delivery capacity.",
         "SIMULATED")
y = slicers(p)
y = kpi_row(p, [("Headcount", "Headcount (month end)"), ("Regretted Attrition % R12M", "Regretted attrition, R12M"),
                ("Voluntary Attrition % R12M", "Voluntary attrition, R12M"), ("Utilization % (closed months)", "Utilisation, closed months"),
                ("Bench %", "Bench share"), ("Open Requisitions", "Open requisitions")], y=y)
h = (BOT - y - GAP) / 2
(x1, w1), (x2, w2) = cols(2)
p.chart("attrTrend", "lineChart", x1, y, w1, h, {"Category": [MONTH], "Y": Ms("Regretted Attrition % R12M", "Voluntary Attrition % R12M")},
        "Voluntary and regretted attrition, rolling 12 months", sort=BY_MONTH)
p.chart("hcTrend", "clusteredColumnChart", x2, y, w2, h, {"Category": [MONTH], "Y": Ms("Headcount")},
        "Headcount at month end (duplicate ids excluded)", sort=BY_MONTH)
y2 = y + h + GAP
p.chart("volByDept", "clusteredBarChart", x1, y2, w1, h, {"Category": [DEPT], "Y": Ms("Voluntary Attrition %", "Regretted Attrition %")},
        "Voluntary and regretted attrition by department (period selected)")
p.chart("utilTrend", "lineChart", x2, y2, w2, h, {"Category": [MONTH], "Y": Ms("Utilization % (closed months)", "Bench %")},
        "Utilisation (closed months) and bench share", sort=BY_MONTH)
p.footer(SRC_SIM)
pages.append(p)

# ======================= Page 2 - Attrition deep dive =======================
p = Page("c2a0000000000000attr", "Attrition deep dive")
p.header("Attrition deep dive: three definitions, one false signal, three real causes",
         "March 2026: gross turnover jumps because a Delivery 2 reorganisation was keyed as exits + rehires; excluding transfers nothing moves. "
         "The real stories are Data & Cloud overload, pay compression at 2-4 years of service, and the Vilnius 2025 cohort.",
         "SIMULATED")
y = slicers(p)
(x1, w1), (x2, w2), (x3, w3) = cols(3)
h = (BOT - y - GAP) / 2
p.chart("threeDefs", "lineChart", x1, y, w1 + w2 + GAP, h,
        {"Category": [MONTH], "Y": Ms("Attrition % (gross)", "Attrition % (excl. transfers)", "Voluntary Attrition %")},
        "Monthly attrition under three definitions (the March spike is the reorganisation)", sort=BY_MONTH)
p.chart("reasons", "tableEx", x3, y, w3, h, {"Values": [C("FactMovements", "ExitReason"), meas("Voluntary Exits"), meas("Regretted Exits")]},
        "Exit reasons (resignations)", table_style(), sort=(meas("Voluntary Exits"), "Descending"))
y2 = y + h + GAP
p.chart("dcRegretted", "clusteredColumnChart", x1, y2, w1, h, {"Category": [MONTH], "Y": Ms("Regretted Exits", "Overtime %")},
        "Data & Cloud: overtime, then regretted exits", sort=BY_MONTH, only=("DimOrg", "Department", ["Data & Cloud"], False))
p.chart("tenure", "clusteredColumnChart", x2, y2, w2, h, {"Category": [C("FactMovements", "TenureBand")], "Y": Ms("Voluntary Exits")},
        "Resignations by length of service", sort=(C("FactMovements", "TenureBand"), "Ascending"))
p.chart("premium", "clusteredBarChart", x3, y2, w3, h, {"Category": [GRADE], "Y": Ms("New-Hire Pay Premium %")},
        "New hires vs 2-4 year colleagues, same grade (median pay)")
p.footer(SRC_SIM)
pages.append(p)

# ======================= Page 3 - Utilization & bench =======================
p = Page("c3a0000000000000util", "Utilization & bench")
p.header("Utilisation and bench: Delivery 3 lost a large project; the last month always looks bad",
         "Bench in Delivery 3 rose from about 6% to 18% after the end of a client project in May 2026. October 2026 is provisional: "
         "timesheets arrive up to 10 days after month end, so its raw utilisation is far too low until the month closes.",
         "SIMULATED")
y = slicers(p)
y = kpi_row(p, [("Utilization % (closed months)", "Utilisation, closed months"), ("Utilization %", "Utilisation, raw (no cut-off)"),
                ("Timesheet Completeness %", "Timesheet completeness"), ("Overtime %", "Overtime share"), ("Month Status", "Month status")], y=y)
h = (BOT - y - GAP) / 2
(x1, w1), (x2, w2) = cols(2)
p.chart("cutoff", "lineChart", x1, y, w1, h, {"Category": [MONTH], "Y": Ms("Utilization %", "Utilization % (closed months)")},
        "Utilisation with and without the cut-off rule", sort=BY_MONTH)
p.chart("bench", "lineChart", x2, y, w2, h, {"Category": [MONTH], "Y": Ms("Bench %"), "Series": [DEPT]},
        "Bench share by department", sort=BY_MONTH, only=("DimOrg", "IsBillable", [1], False))
y2 = y + h + GAP
p.chart("overtime", "lineChart", x1, y2, w1, h, {"Category": [MONTH], "Y": Ms("Overtime %"), "Series": [DEPT]},
        "Overtime share by department (alert above 15%)", sort=BY_MONTH, only=("DimOrg", "IsBillable", [1], False))
p.chart("utilDept", "tableEx", x2, y2, w2, h,
        {"Values": [DEPT, meas("Utilization % (closed months)"), meas("Bench %"), meas("Overtime %"), meas("Capacity Hours")]},
        "By department (period selected, closed months)", table_style(), only=("DimOrg", "IsBillable", [1], False))
p.footer(SRC_SIM + "  ·  Working days: Lithuanian public holidays (Nager.Date, PUBLIC DATA)")
pages.append(p)

# ======================= Page 4 - Data quality & reconciliation =======================
p = Page("c4a0000000000000dqrc", "Data quality & reconciliation")
p.header("Can we trust the numbers? Duplicate ids, a mis-mapped cost centre, and a bridge that closes to zero",
         "The HRIS migration (Sep 2025) left 18 people with two ids (+3% headcount). Finance mapped cost centre CC-D1-VNO to Data & Cloud "
         "from May to July 2026. Reconciling HR and finance headcount finds both; the remaining gap is leavers paid in their last month.",
         "SIMULATED")
y = slicers(p)
y = kpi_row(p, [("Duplicate IDs", "Duplicate ids (month end)"), ("Headcount (raw HRIS)", "Headcount, raw HRIS"), ("Headcount", "Headcount, clean"),
                ("Finance Headcount", "Finance headcount (paid)"), ("HR vs Finance Gap", "Finance - HR raw"), ("Late Timesheets %", "Timesheets > 10 days late")], y=y)
h = (BOT - y - GAP) / 2
(x1, w1), (x2, w2) = cols(2)
p.chart("rawVsClean", "lineChart", x1, y, w1, h, {"Category": [MONTH], "Y": Ms("Headcount (raw HRIS)", "Headcount", "Finance Headcount")},
        "HR raw, HR clean and finance headcount", sort=BY_MONTH)
p.chart("revFte", "clusteredColumnChart", x2, y, w2, h, {"Category": [MONTH], "Y": Ms("Revenue per FTE (as reported)", "Revenue per FTE")},
        "Data & Cloud revenue per FTE: as reported vs cost-centre master", sort=BY_MONTH, only=("DimOrg", "Department", ["Data & Cloud"], False))
y2 = y + h + GAP
p.chart("deptRecon", "tableEx", x1, y2, w1, h,
        {"Values": [DEPT, meas("Revenue"), meas("Revenue (as reported by finance)"), meas("Revenue per FTE"), meas("Revenue per FTE (as reported)")]},
        "Revenue by department: cost-centre master vs finance export", table_style())
p.chart("dupList", "tableEx", x2, y2, w2, h,
        {"Values": [C("DimEmployee", "EmployeeId"), C("DimEmployee", "MasterEmployeeId"), C("DimEmployee", "SourceSystem"), C("DimEmployee", "ValidFrom")]},
        "Duplicate ids and the master id they belong to", table_style(), only=("DimEmployee", "IsDuplicateId", [1], False))
p.footer(SRC_SIM)
pages.append(p)

# ---------- write ----------
PAGES.mkdir(parents=True, exist_ok=True)
keep = {pg.pid for pg in pages}
for d in PAGES.iterdir():
    if d.is_dir() and d.name not in keep:
        shutil.rmtree(d)
for pg in pages:
    pg.write()
meta = {"$schema": PAGES_SCHEMA, "pageOrder": [pg.pid for pg in pages], "activePageName": pages[0].pid}
(PAGES / "pages.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print("pages:", [(pg.name, len(pg.visuals)) for pg in pages])
