"""Charts for the PDF and the notebook (matplotlib). Every number is read from data/output or data/public.

Art direction (same as the earlier case studies): white cards on a grey-beige page, blue for the data, grey for
comparison, red for alerts and thresholds, dashed lines for thresholds, Segoe UI.
Each function returns a matplotlib figure; build_pdf.py saves them to docs/img/.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT, PUB, IMG = ROOT / "data" / "output", ROOT / "data" / "public", ROOT / "docs" / "img"
BLUE, GREY, RED, INK, MUTED, GRID, LIGHT = "#2A78D6", "#A3A19A", "#D03B3B", "#0B0B0B", "#52514E", "#E1E0D9", "#C9DDF5"
ORANGE, GREEN = "#EB6834", "#1BAF7A"
DEPT_COLORS = {"Delivery 1": "#86B6EF", "Delivery 2": "#5598E7", "Delivery 3": RED, "Data & Cloud": ORANGE}
plt.rcParams.update({
    "font.family": "Segoe UI", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "figure.facecolor": "white", "axes.facecolor": "white", "legend.frameon": False,
    "axes.titlesize": 11, "axes.titleweight": "semibold", "axes.titlecolor": INK, "axes.titlelocation": "left",
})
PCT = mtick.PercentFormatter(1.0, decimals=0)


def csv(name, folder=OUT):
    return pd.read_csv(folder / f"{name}.csv")


def mlabel(s):
    return pd.to_datetime(s).dt.strftime("%b %y")


def fig_ax(w=5.2, h=3.0):
    return plt.subplots(figsize=(w, h))


def month_axis(ax, labels, every=3):
    ax.set_xticks(range(len(labels))[::every])
    ax.set_xticklabels(list(labels)[::every], fontsize=8.5)


def save(fig, name):
    IMG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(IMG / f"{name}.png", dpi=200)
    plt.close(fig)
    return f"img/{name}.png"


# ---------------------------------------------------------------- page 1 · public market data
def market_wages():
    l = csv("eurostat_labour_cost_index_ict_lt", PUB)
    l = l[l.quarter >= "2021-Q1"]
    fig, ax = fig_ax()
    ax.plot(l.quarter, l.lci_ict_2020_100, color=BLUE, lw=2)
    ax.plot(l.quarter, l.lci_ict_2020_100.rolling(4).mean(), color=GREY, lw=1.2, ls="--", label="4-quarter average")
    ax.annotate(f"{l.lci_ict_2020_100.iloc[-1]:.0f}", (len(l) - 1, l.lci_ict_2020_100.iloc[-1]), xytext=(-4, 6),
                textcoords="offset points", ha="right", fontsize=9, color=BLUE, weight="semibold")
    month_axis(ax, l.quarter, 4)
    ax.set_ylabel("Index, 2020 = 100")
    ax.legend(fontsize=8.5, loc="upper left")
    return fig


def market_vacancies():
    j = csv("eurostat_job_vacancy_rate_ict", PUB)
    j = j[j.quarter >= "2021-Q1"]
    fig, ax = fig_ax()
    for geo, c, lab in [("LT", BLUE, "Lithuania"), ("EU27_2020", GREY, "EU-27"), ("FR", ORANGE, "France")]:
        d = j[j.geo == geo]
        ax.plot(d.quarter, d.job_vacancy_rate_pct, color=c, lw=2 if geo == "LT" else 1.3, label=lab)
    q = sorted(j.quarter.unique())
    month_axis(ax, q, 4)
    ax.set_ylabel("Job vacancy rate, ICT (%)")
    ax.legend(fontsize=8.5, ncol=3, loc="lower left")
    return fig


def market_earnings():
    o = csv("osp_average_monthly_earnings", PUB)
    o = o[(o.measure == "gross") & (o.quarter >= "2021-Q1")]
    fig, ax = fig_ax()
    for act, c in [("ICT (J58-J63)", BLUE), ("All activities", GREY)]:
        d = o[o.activity == act]
        ax.plot(d.quarter, d.eur_month, color=c, lw=2, label=act)
        ax.annotate(f"€{d.eur_month.iloc[-1]:,.0f}", (len(d) - 1, d.eur_month.iloc[-1]), xytext=(0, 6),
                    textcoords="offset points", ha="right", fontsize=9, color=c, weight="semibold")
    month_axis(ax, sorted(o.quarter.unique()), 4)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"€{x:,.0f}"))
    ax.set_ylabel("Average monthly gross earnings")
    ax.legend(fontsize=8.5, loc="upper left")
    return fig


# ---------------------------------------------------------------- page 2 · three definitions
def three_definitions():
    d = csv("attrition_definitions")
    lab = mlabel(d.month_start)
    fig, ax = fig_ax(6.4, 3.1)
    ax.plot(lab, d.rate_gross_month, color=RED, lw=1.6, label="Gross (every exit keyed)")
    ax.plot(lab, d.rate_excl_transfers_month, color=BLUE, lw=2, label="Excluding internal transfers")
    ax.plot(lab, d.rate_voluntary_month, color=GREY, lw=1.4, ls="--", label="Voluntary only")
    i = int(np.argmax(d.rate_gross_month))
    ax.annotate(f"{lab.iloc[i]}: {d.gross.iloc[i]} exits keyed,\nof which {d.gross.iloc[i] - d.excl_transfers.iloc[i]} are a reorganisation",
                (i, d.rate_gross_month.iloc[i]), xytext=(18, -40), textcoords="offset points", fontsize=8.5, color=RED,
                arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))
    month_axis(ax, lab, 3)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_ylabel("Exits / month-end headcount")
    ax.legend(fontsize=8.5, loc="upper left")
    return fig


def false_signal_d2():
    d = csv("attrition_false_signal")
    lab = mlabel(d.month_start)
    x = np.arange(len(d))
    fig, ax = fig_ax(4.2, 3.1)
    ax.bar(x - 0.2, d.exits_gross, 0.4, color=RED, label="Gross")
    ax.bar(x + 0.2, d.exits_excl_transfers, 0.4, color=BLUE, label="Excl. transfers")
    for xi, v in zip(x, d.exits_gross):
        ax.text(xi - 0.2, v + 1, str(v), ha="center", fontsize=8.5, color=MUTED)
    for xi, v in zip(x, d.exits_excl_transfers):
        ax.text(xi + 0.2, v + 1, str(v), ha="center", fontsize=8.5, color=MUTED)
    ax.set_xticks(x)
    ax.set_xticklabels(lab, fontsize=8.5)
    ax.set_ylabel("Exits, Delivery 2")
    ax.legend(fontsize=8.5)
    ax.grid(axis="x", visible=False)
    return fig


# ---------------------------------------------------------------- page 4 · who leaves
def dc_overload():
    u = csv("utilization_monthly")
    a = csv("attrition_monthly")
    u = u[u.department == "Data & Cloud"].reset_index(drop=True)
    a = a[a.department == "Data & Cloud"].reset_index(drop=True)
    lab = mlabel(u.month_start)
    fig, ax = fig_ax()
    ax.bar(range(len(a)), a.exits_regretted, color=LIGHT, label="Regretted resignations (right)", zorder=1)
    ax2 = ax.twinx()
    ax.set_zorder(ax2.get_zorder() - 1) if False else None
    ax2.plot(range(len(u)), u.overtime_share, color=RED, lw=2, label="Overtime / capacity (left)")
    ax2.axhline(0.15, color=RED, ls="--", lw=0.9)
    ax2.text(0.3, 0.155, "15% alert threshold", fontsize=8, color=RED)
    ax2.yaxis.set_major_formatter(PCT)
    ax2.yaxis.tick_left(); ax2.yaxis.set_label_position("left")
    ax.yaxis.tick_right(); ax.yaxis.set_label_position("right")
    ax.set_ylabel("Regretted exits")
    ax2.set_ylabel("Overtime share")
    ax2.grid(False)
    ax2.spines["top"].set_visible(False)
    month_axis(ax, lab, 3)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax2.legend(h2 + h1, l2 + l1, fontsize=8, loc="upper left")
    return fig


def tenure_exits():
    t = csv("exits_by_tenure")
    halves = list(t.half.unique())
    bands = ["0-1 y", "1-2 y", "2-4 y", "4+ y"]
    x = np.arange(len(bands))
    fig, ax = fig_ax()
    colors = [GRID, GREY, "#86B6EF", BLUE]
    for i, (h, c) in enumerate(zip(halves, colors)):
        d = t[t.half == h].set_index("tenure_band").reindex(bands)
        ax.bar(x + (i - 1.5) * 0.2, d.annualised_rate, 0.2, color=c, label=h.split(" ", 1)[1])
    ax.set_xticks(x)
    ax.set_xticklabels(["< 1 year", "1-2 years", "2-4 years", "4+ years"])
    ax.yaxis.set_major_formatter(PCT)
    ax.set_ylabel("Resignations, annualised")
    ax.legend(fontsize=8, ncol=2, loc="upper right")
    ax.grid(axis="x", visible=False)
    return fig


def pay_compression():
    p = csv("pay_compression")
    lfl = csv("pay_like_for_like").iloc[0]
    last = p[p.month_start == p.month_start.max()]
    fig, ax = fig_ax()
    x = np.arange(len(last))
    ax.bar(x - 0.2, last.tenure_2_4_median, 0.4, color=GREY, label="2-4 years of service")
    ax.bar(x + 0.2, last.new_hire_median, 0.4, color=BLUE, label="Hired < 1 year ago")
    for xi, r in zip(x, last.itertuples()):
        ax.text(xi + 0.2, r.new_hire_median + 60, f"+{r.new_hire_premium:.0%}", ha="center", fontsize=9, color=BLUE, weight="semibold")
    ax.set_xticks(x)
    ax.set_xticklabels(last.grade)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"€{v:,.0f}"))
    ax.set_ylabel("Median monthly gross, Oct 2026")
    ax.set_ylim(0, last.new_hire_median.max() * 1.25)
    ax.legend(fontsize=8.5, loc="upper left")
    ax.text(0.99, 0.97, f"Same people, Oct 25 to Oct 26: +{lfl.median_raise:.1%}\nMarket (ICT labour cost index): +{lfl.market_growth_4q:.1%}",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color=MUTED)
    ax.grid(axis="x", visible=False)
    return fig


def cohorts():
    c = csv("cohort_retention")
    c = c[c.six_months_observed]
    wave = c[(c.hire_quarter == "2025-Q2") & (c.site == "Vilnius")]
    rest = c[~((c.hire_quarter == "2025-Q2") & (c.site == "Vilnius"))]
    rows = [("Vilnius, Q2 2025\n(ramp-up wave)", int(wave.hires.sum()), wave.left_within_6m.sum() / wave.hires.sum(), RED),
            ("Kaunas, Q2 2025", int(c[(c.hire_quarter == "2025-Q2") & (c.site == "Kaunas")].hires.sum()),
             c[(c.hire_quarter == "2025-Q2") & (c.site == "Kaunas")].left_within_6m.sum() / max(1, c[(c.hire_quarter == "2025-Q2") & (c.site == "Kaunas")].hires.sum()), GREY),
            ("All other cohorts", int(rest.hires.sum()), rest.left_within_6m.sum() / rest.hires.sum(), BLUE)]
    fig, ax = fig_ax()
    for i, (lab, n, v, col) in enumerate(rows):
        ax.barh(i, v, color=col, height=0.55)
        ax.text(v + 0.01, i, f"{v:.0%}  (n = {n})", va="center", fontsize=9, color=MUTED)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows])
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(PCT)
    ax.set_xlim(0, 0.6)
    ax.set_xlabel("Hires who left within 6 months")
    ax.grid(axis="y", visible=False)
    return fig


# ---------------------------------------------------------------- page 5 · utilisation
def working_days():
    u = csv("utilization_delivery")
    lab = mlabel(u.month_start)
    fig, ax = fig_ax()
    ax.bar(range(len(u)), u.working_days, color=LIGHT)
    for i, v in enumerate(u.working_days):
        ax.text(i, v + 0.2, str(v), ha="center", fontsize=7.5, color=MUTED)
    month_axis(ax, lab, 3)
    ax.set_ylim(15, 24.5)
    ax.set_ylabel("Working days (Lithuania)")
    ax.grid(axis="x", visible=False)
    return fig


def bench():
    u = csv("utilization_monthly")
    fig, ax = fig_ax()
    for d, c in DEPT_COLORS.items():
        x = u[u.department == d]
        ax.plot(range(len(x)), x.bench_share, color=c, lw=2.2 if d == "Delivery 3" else 1.2, label=d)
    ax.axvline(19, color=RED, ls="--", lw=0.8)
    ax.text(18.7, 0.17, "client project\nends (May 26)", fontsize=8, color=RED, va="top", ha="right")
    month_axis(ax, mlabel(u[u.department == "Delivery 3"].month_start), 3)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_ylabel("Bench hours / capacity")
    ax.legend(fontsize=8, ncol=2, loc="upper left")
    return fig


def cutoff():
    u = csv("utilization_delivery")
    lab = mlabel(u.month_start)
    fig, ax = fig_ax()
    ax.plot(range(len(u)), u.utilization_all_months, color=GREY, lw=1.4, ls="--", label="Raw: every month as received")
    ax.plot(range(len(u)), u.utilization_closed_only, color=BLUE, lw=2.2, label="With cut-off rule (closed months only)")
    i = len(u) - 1
    ax.annotate(f"{lab.iloc[i]}: {u.utilization_all_months.iloc[i]:.0%}\nnot closed at extract date",
                (i, u.utilization_all_months.iloc[i]), xytext=(-125, -6), textcoords="offset points", fontsize=8.5, color=RED,
                arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))
    month_axis(ax, lab, 3)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_ylim(0.5, 0.85)
    ax.set_ylabel("Billable hours / capacity")
    ax.legend(fontsize=8.5, loc="lower left")
    return fig


# ---------------------------------------------------------------- page 6 · trust
def hr_vs_finance():
    h = csv("headcount_company")
    b = csv("recon_bridge")
    lab = mlabel(h.month_start)
    fig, ax = fig_ax()
    ax.plot(range(len(h)), h.headcount_raw, color=RED, lw=1.6, label="HR, raw HRIS")
    ax.plot(range(len(h)), h.headcount, color=BLUE, lw=2.2, label="HR, duplicates removed")
    idx = [list(h.month_start).index(m) for m in b.month_start]
    ax.plot(idx, b.finance_headcount, color=GREY, lw=1.4, ls="--", label="Finance, people paid")
    mig = list(h.month_start).index("2025-09-01")
    ax.axvline(mig, color=RED, ls=":", lw=0.8)
    ax.text(mig + 0.2, h.headcount.min() + 2, "HRIS migration", fontsize=8, color=RED)
    month_axis(ax, lab, 3)
    ax.set_ylabel("Headcount")
    ax.legend(fontsize=8.5, loc="upper left")
    return fig


def bridge():
    b = csv("recon_bridge")
    r = b[b.month_start == b.month_start.max()].iloc[0]
    steps = [("HR raw\nmonth end", r.hr_raw_month_end, "total"), ("Duplicate\nids", r.less_duplicate_ids, "delta"),
             ("Leavers paid\nin month", r.plus_leavers_in_month, "delta"), ("Finance\nheadcount", r.finance_headcount, "total"),
             ("Unexplained", r.residual, "delta")]
    fig, ax = fig_ax()
    run = 0
    for i, (lab, v, kind) in enumerate(steps):
        if kind == "total":
            ax.bar(i, v, color=BLUE if i == 0 else GREY, width=0.6)
            run = v
            ax.text(i, v + 2, f"{v:,.0f}", ha="center", fontsize=9, color=INK)
        else:
            base = run + min(0, v)
            ax.bar(i, abs(v) if v else 0.6, bottom=base, color=RED if v < 0 else GREEN, width=0.6)
            ax.text(i, run + max(0, v) + 2, f"{v:+,.0f}", ha="center", fontsize=9, color=INK)
            run += v
    ax.set_xticks(range(len(steps)))
    ax.set_xticklabels([s[0] for s in steps], fontsize=8.5)
    lo = min(r.finance_headcount, r.hr_raw_month_end) - 40
    ax.set_ylim(lo, r.hr_raw_month_end + 15)
    ax.set_ylabel(f"People, {pd.to_datetime(r.month_start):%b %Y}")
    ax.grid(axis="x", visible=False)
    return fig


def revenue_per_fte():
    r = csv("revenue_per_fte")
    d = r[r.department == "Data & Cloud"].reset_index(drop=True)
    lab = mlabel(d.month_start)
    x = np.arange(len(d))
    fig, ax = fig_ax()
    ax.bar(x, d.revenue_per_fte_reported, color=[RED if a != b else LIGHT for a, b in zip(d.revenue_per_fte_reported, d.revenue_per_fte_fixed)],
           label="As exported by finance")
    ax.plot(x, d.revenue_per_fte_fixed, color=BLUE, lw=2, label="With the HR cost-centre master")
    month_axis(ax, lab, 3)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"€{v / 1000:,.0f}k"))
    ax.set_ylabel("Data & Cloud revenue per FTE")
    ax.legend(fontsize=8.5, loc="upper left")
    ax.grid(axis="x", visible=False)
    return fig


ALL = {"p1_wages": market_wages, "p1_vacancies": market_vacancies, "p1_earnings": market_earnings,
       "p2_definitions": three_definitions, "p2_false_signal": false_signal_d2,
       "p4_dc_overload": dc_overload, "p4_tenure": tenure_exits, "p4_pay": pay_compression, "p4_cohorts": cohorts,
       "p5_working_days": working_days, "p5_bench": bench, "p5_cutoff": cutoff,
       "p6_hr_finance": hr_vs_finance, "p6_bridge": bridge, "p6_rev_fte": revenue_per_fte}


def build_all():
    return {name: save(f(), name) for name, f in ALL.items()}


if __name__ == "__main__":
    print(len(build_all()), "charts written to docs/img")
