"""Download the public data used to calibrate the simulation and to fill the `Market` table.

Sources (no key, no account; neutral User-Agent):
  - Eurostat dissemination API: labour cost index (ICT sector J), job vacancy rate (J), ICT specialists share
  - Statistics Lithuania (OSP) SDMX: average monthly earnings by economic activity (J58-J63 and total)
  - Nager.Date: Lithuanian public holidays 2024-2026
Not used: Sodra open employer data (atvira.sodra.lt answers 403 to automated clients; not bypassed).

    python src/fetch_public.py
Writes data/public/*.csv. Raw downloads are cached in data/raw/ (not published).
"""
import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW, PUB = ROOT / "data" / "raw", ROOT / "data" / "public"
RAW.mkdir(parents=True, exist_ok=True)
PUB.mkdir(parents=True, exist_ok=True)
HEAD = {"User-Agent": "bi-case-study/1.0"}
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
OSP = "https://osp-rs.stat.gov.lt/rest_xml/data/S3R0050_M3060315_1/"


def get(url, name, binary=False):
    """Download once and cache in data/raw (re-runs use the cache)."""
    path = RAW / name
    if not path.exists():
        r = requests.get(url, headers=HEAD, timeout=180)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def eurostat(code, query, name):
    """Flatten a JSON-stat 2.0 answer into one row per observation."""
    js = json.loads(get(f"{EUROSTAT}{code}?{query}", name).read_text(encoding="utf-8"))
    dims, sizes = js["id"], js["size"]
    labels = {d: {i: k for k, i in js["dimension"][d]["category"]["index"].items()} for d in dims}
    rows = []
    for flat, value in js["value"].items():
        flat, pos = int(flat), {}
        for d, s in zip(reversed(dims), reversed(sizes)):
            pos[d] = labels[d][flat % s]
            flat //= s
        rows.append({**{d: pos[d] for d in dims}, "value": value})
    return pd.DataFrame(rows), js.get("updated", "")


def osp_earnings():
    """Average monthly earnings, whole economy excluding individual enterprises (sector 0ex), both sexes."""
    text = get(OSP, "osp_earnings_by_activity.xml").read_text(encoding="utf-8")
    keep = {"J58_TO_J63": "ICT (J58-J63)", "TOTAL": "All activities"}
    rows = []
    for m in re.finditer(r"<g:Obs>(.*?)</g:Obs>", text, re.S):
        d = dict(re.findall(r'id="(\w+)" value="([^"]*)"', m.group(1)))
        if d.get("EVRK2M3060207") in keep and d.get("Lytis") == "0" and d.get("Ekon_sektorM2040803") == "0ex":
            v = re.search(r'ObsValue value="([^"]+)"', m.group(1))
            if v:
                rows.append({"quarter": d["LAIKOTARPIS"].replace("K", "-Q"), "activity": keep[d["EVRK2M3060207"]],
                             "measure": {"bruto": "gross", "neto": "net"}[d["darboM3060321"]],
                             "eur_month": float(v.group(1))})
    return pd.DataFrame(rows).sort_values(["activity", "measure", "quarter"])


def holidays():
    rows = []
    for y in (2024, 2025, 2026):
        for h in json.loads(get(f"https://date.nager.at/api/v3/PublicHolidays/{y}/LT", f"holidays_{y}.json").read_text(encoding="utf-8")):
            rows.append({"date": h["date"], "name": h["name"], "local_name": h["localName"]})
    return pd.DataFrame(rows)


def main():
    today = dt.date.today().isoformat()
    sources = []

    lci, upd = eurostat("lc_lci_r2_q", "geo=LT&nace_r2=J&lcstruct=D1_D4_MD5&unit=I20&s_adj=NSA", "eurostat_lci.json")
    lci = lci[["time", "value"]].rename(columns={"time": "quarter", "value": "lci_ict_2020_100"})
    lci = lci[lci.quarter >= "2019"].sort_values("quarter")
    lci.to_csv(PUB / "eurostat_labour_cost_index_ict_lt.csv", index=False)
    sources.append(("eurostat_labour_cost_index_ict_lt.csv", "Eurostat lc_lci_r2_q (LT, NACE J, wages and salaries D1_D4_MD5, 2020=100, NSA)", upd))

    jvr, upd = eurostat("jvs_q_nace2", "geo=LT&geo=FR&geo=EU27_2020&nace_r2=J&s_adj=NSA&sizeclas=TOTAL&indic_em=JVR", "eurostat_jvr.json")
    jvr = jvr[["geo", "time", "value"]].rename(columns={"time": "quarter", "value": "job_vacancy_rate_pct"})
    jvr = jvr[jvr.quarter >= "2019"].sort_values(["geo", "quarter"])
    jvr.to_csv(PUB / "eurostat_job_vacancy_rate_ict.csv", index=False)
    sources.append(("eurostat_job_vacancy_rate_ict.csv", "Eurostat jvs_q_nace2 (NACE J, JVR, NSA; LT, FR, EU27_2020)", upd))

    ict, upd = eurostat("isoc_sks_itspt", "geo=LT&geo=EU27_2020&unit=PC_EMP", "eurostat_ict_share.json")
    ict = ict[["geo", "time", "value"]].rename(columns={"time": "year", "value": "ict_specialists_pct_employment"})
    ict.sort_values(["geo", "year"]).to_csv(PUB / "eurostat_ict_specialists_share.csv", index=False)
    sources.append(("eurostat_ict_specialists_share.csv", "Eurostat isoc_sks_itspt (% of total employment; LT, EU27_2020)", upd))

    osp = osp_earnings()
    osp.to_csv(PUB / "osp_average_monthly_earnings.csv", index=False)
    sources.append(("osp_average_monthly_earnings.csv", "Statistics Lithuania S3R0050_M3060315_1 (average monthly earnings, both sexes, whole economy excl. individual enterprises)", "2026-09-02"))

    hol = holidays()
    hol.to_csv(PUB / "lt_public_holidays.csv", index=False)
    sources.append(("lt_public_holidays.csv", "Nager.Date public holidays API, country LT, 2024-2026", ""))

    pd.DataFrame(sources, columns=["file", "source", "source_last_update"]).assign(retrieved=today) \
        .to_csv(PUB / "_sources.csv", index=False)
    print("LCI", lci.tail(1).to_dict("records"), "| JVR LT", jvr[jvr.geo == "LT"].tail(1).to_dict("records"),
          "| ICT", ict[ict.geo == "LT"].sort_values("year").tail(1).to_dict("records"),
          "| OSP", osp[(osp.measure == "gross")].groupby("activity").tail(1).to_dict("records"), "| holidays", len(hol))


if __name__ == "__main__":
    main()
