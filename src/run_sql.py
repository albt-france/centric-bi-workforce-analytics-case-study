"""Load the simulated extracts and the public data into DuckDB, run sql/01..06 and sql/kpi_checks.sql in order,
and export every table whose name starts with `out_` to data/output/<name>.csv.

    python src/run_sql.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SIM, PUB, OUT, SQL = ROOT / "data" / "sim", ROOT / "data" / "public", ROOT / "data" / "output", ROOT / "sql"
OUT.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "employees": SIM / "employees.csv", "movements": SIM / "movements.csv", "timesheets": SIM / "timesheets.csv",
    "absences": SIM / "absences.csv", "recruiting": SIM / "recruiting.csv", "finance_monthly": SIM / "finance_monthly.csv",
    "cost_center_map": SIM / "cost_center_map.csv", "extract_info": SIM / "extract_info.csv",
    "holidays": PUB / "lt_public_holidays.csv", "lci": PUB / "eurostat_labour_cost_index_ict_lt.csv",
    "jvr": PUB / "eurostat_job_vacancy_rate_ict.csv", "ict_share": PUB / "eurostat_ict_specialists_share.csv",
    "osp_earnings": PUB / "osp_average_monthly_earnings.csv",
}


def connect():
    con = duckdb.connect()
    con.execute("SET threads TO 1")         # single thread: float sums in the same order on every run
    for name, path in SOURCES.items():
        con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_csv_auto('{path.as_posix()}', header=true)")
    return con


def main():
    con = connect()
    files = sorted(SQL.glob("0*.sql")) + [SQL / "kpi_checks.sql"]
    for f in files:
        con.execute(f.read_text(encoding="utf-8"))
    outs = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'out_%' ORDER BY 1").fetchall()]
    for t in outs:
        con.execute(f"COPY {t} TO '{(OUT / (t[4:] + '.csv')).as_posix()}' (HEADER, DELIMITER ',')")
    print(f"{len(files)} SQL files, {len(outs)} outputs -> data/output/")
    return con


if __name__ == "__main__":
    main()
