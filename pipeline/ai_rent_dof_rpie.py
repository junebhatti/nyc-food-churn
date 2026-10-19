"""Extract DOF RPIE retail gross income / expense per sq ft by borough from the
'Additional Statistical Distributions' PDFs (pdftotext -layout output).

Usage: python -I ai_rent_dof_rpie.py <txt_dir> <out_csv>
(txt_dir holds add_<fy>.txt = `pdftotext -layout rent/pdf/dof_additional_distributions_<fy>.pdf`)
"""
import csv
import re
import sys
from pathlib import Path

URLS = {
    "fy2015": "https://www.nyc.gov/assets/finance/downloads/pdf/13pdf/fy2015_additional_guidelines.pdf",
    "fy2016": "https://www.nyc.gov/assets/finance/downloads/pdf/15pdf/fy2016_additional_guidelines.pdf",
    "fy2017": "https://web.archive.org/web/20210708012121/https://www1.nyc.gov/assets/finance/downloads/pdf/17pdf/fy2017-additional-statistical-distributions-and-capitalization-rate-methodology.pdf",
    "fy2018": "https://web.archive.org/web/20210708012114/https://www1.nyc.gov/assets/finance/downloads/pdf/18pdf/fy2018-additional-statistical-distributions-and-capitalization-rate-methodology.pdf",
    "fy2019": "https://www.nyc.gov/assets/finance/downloads/pdf/19pdf/fy2019-additional-statistical-distributions-and-capitalization-rate-methodology.pdf",
    "fy2020": "https://www.nyc.gov/assets/finance/downloads/pdf/20pdf/fy2020-additional-statistical-distributions-and-capitalization-rate-methodology.pdf",
    "fy2021": "https://www.nyc.gov/assets/finance/downloads/pdf/21pdf/fy2021-additional-statistical-distributions-and-capitalization-rate-methodology.pdf",
    "fy2022": "https://www.nyc.gov/assets/finance/downloads/pdf/21pdf/fy2022-additional-statistical-distributions-and-capitalization-rate-methodology.pdf",
    "fy2023": "https://www.nyc.gov/assets/finance/downloads/pdf/23pdf/fy2023-additional-statistical-distributions-and-capitalization-methodology-publish.pdf",
    "fy2024": "https://www.nyc.gov/assets/finance/downloads/pdf/23pdf/fy2024-additional-statistical-distributions-and-capitalization-rate-methodology.pdf",
    "fy2025": "https://www.nyc.gov/assets/finance/downloads/pdf/25pdf/additional-income-expense-dist-fy-2025.pdf",
    "fy2026": "https://www.nyc.gov/assets/finance/downloads/pdf/25pdf/additional-income-expense-dist-fy-2026.pdf",
    "fy2027": "https://www.nyc.gov/assets/finance/downloads/pdf/26pdf/additional-income-expense-dist-fy-2027.pdf",
}
BOROS = ["Manhattan", "Bronx", "Brooklyn", "Queens", "Staten Island"]
SEC_RE = re.compile(r"Retail Properties By Borough|Distribution by Borough-Retail", re.I)
MONEY = r"\$([\d,]+\.\d{2})"
VAR_RE = re.compile(r"\b(Income|Expense)\s+" + r"\s+".join([MONEY] * 4))


def parse(fy, text):
    lines = text.splitlines()
    rpie = re.search(r"RPIE (20\d\d)", text)
    if not rpie:
        raise ValueError(f"{fy}: no RPIE year found")
    rpie_year = int(rpie.group(1))
    start = next((i for i, l in enumerate(lines) if SEC_RE.search(l)), None)
    if start is None:
        raise ValueError(f"{fy}: retail-by-borough section not found")
    events = []
    for l in lines[start:start + 60]:
        b = next((b for b in BOROS if re.search(rf"\b{b}\b", l)), None)
        cnt = re.search(r"\b(?:" + "|".join(BOROS) + r")\s+([\d,]+)\b", l)
        v = VAR_RE.search(l)
        if b:
            events.append(("boro", b, int(cnt.group(1).replace(",", "")) if cnt else None))
        if v:
            events.append((v.group(1).lower(), [float(x.replace(",", "")) for x in v.groups()[1:]]))
        if "Notes:" in l and any(e[0] == "boro" for e in events):
            break
    # Assign: each borough gets the income/expense lines in its block. Blocks are delimited by
    # borough lines; in the FY2015 layout the Income line sits one line above the borough line.
    out = {}
    order = [e for e in events]
    boro_idx = [i for i, e in enumerate(order) if e[0] == "boro"]
    for k, i in enumerate(boro_idx):
        name, count = order[i][1], order[i][2]
        lo = boro_idx[k - 1] + 1 if k else 0
        hi = boro_idx[k + 1] if k + 1 < len(boro_idx) else len(order)
        block = order[lo:hi]
        incs = [e[1] for e in block if e[0] == "income"]
        exps = [e[1] for e in block if e[0] == "expense"]
        # income nearest at/after previous borough's expense: take the last income before the
        # borough line if layout is income-first, else the first after it.
        before = [e[1] for e in order[lo:i + 1] if e[0] == "income"]
        after = [e[1] for e in order[i:hi] if e[0] == "income"]
        inc = after[0] if after and (not before or order[i + 1][0] == "income") else (before[-1] if before else None)
        exp_after = [e[1] for e in order[i:hi] if e[0] == "expense"]
        out[name] = (count, inc, exp_after[0] if exp_after else (exps[0] if exps else None))
    if set(out) != set(BOROS):
        raise ValueError(f"{fy}: boroughs found {sorted(out)}")
    return rpie_year, out


# FY2016 table is an embedded image; transcribed by hand from page 9 (count, income p25/p50/p75/mean, expense p25/p50/p75/mean)
MANUAL = {"fy2016": (2013, {
    "Manhattan": (1017, [31.36, 52.86, 88.23, 73.38], [5.14, 9.44, 16.78, 13.51]),
    "Bronx": (1059, [15.52, 23.12, 34.29, 28.21], [3.33, 5.86, 9.40, 7.27]),
    "Brooklyn": (1828, [15.00, 23.25, 34.30, 28.03], [2.40, 4.57, 8.02, 6.19]),
    "Queens": (2198, [18.06, 27.33, 41.32, 34.78], [3.04, 5.69, 9.44, 7.65]),
    "Staten Island": (417, [14.33, 22.89, 32.30, 30.39], [2.78, 5.12, 7.77, 7.91]),
})}


def main(txt_dir, out_csv):
    rows = []
    for fy, url in URLS.items():
        if fy in MANUAL:
            rpie_year, res = MANUAL[fy]
        else:
            rpie_year, res = parse(fy, (Path(txt_dir) / f"add_{fy}.txt").read_text(errors="replace"))
        for b, (count, inc, exp) in res.items():
            if inc is None:
                raise ValueError(f"{fy} {b}: no income parsed")
            rows.append(dict(source=f"NYC DOF Additional Statistical Distributions {fy.upper()} (RPIE {rpie_year})",
                             report_date=f"{fy.upper()} assessment roll", year=rpie_year, borough=b,
                             n_properties=count, income_p25=inc[0], income_median=inc[1], income_p75=inc[2],
                             income_mean=inc[3], expense_median=exp[1] if exp else None,
                             notes=("Table transcribed manually from image (p.9); " if fy in MANUAL else "") + "Gross income per sq ft of RETAIL major building category (RPIE filers, all space incl. upper floors; in-place rents, not asking); excludes outliers/partial-year filers",
                             source_url=url))
    cols = list(rows[0].keys())
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
