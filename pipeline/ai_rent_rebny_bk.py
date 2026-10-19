"""Parse REBNY Brooklyn Retail Report appendix tables (pdftotext -layout output) into tidy rows.

Usage: python -I ai_rent_rebny_bk.py <txt_dir> <out_csv>
"""
import csv
import re
import sys
from pathlib import Path

BASE = "https://www.rebny.com/reports/"

# report slug -> (report_label, coverage_year, period_label, coverage note, source pdf url)
REPORTS = {
    "3rd-quarter-2015-brooklyn-retail-report": ("3Q 2015", 2015, "Q3-2015", "Q3 2015 listings", "https://assets.ctfassets.net/6zi14rd5umxw/gco2l7R3CpZVneoym5Pf9/99b7aa4df86c5eb578173bc20feadbe9/Brooklyn_Retail_Report_3Q15.pdf"),
    "q1-winter-2016-brooklyn-retail-report": ("Winter 2016", 2016, "W-2016", "Winter = Oct prior yr - Mar", "https://assets.ctfassets.net/6zi14rd5umxw/cqCF3Oamc19ELJxdjoNsU/8a30770034e86016641cf24c73cb426b/Brooklyn_Retail_Report_First_Quarter_Winter_2016.pdf"),
    "summer-2016-brooklyn-retail-report": ("Summer 2016", 2016, "S-2016", "Summer = Apr - Sep", "https://assets.ctfassets.net/6zi14rd5umxw/1c0ZEoxaM8A1RnAXD1uQds/d6899ff5d224e226903cb13511ab131d/Brooklyn_Retail_Report_Summer_2016.pdf"),
    "winter-2017-brooklyn-retail-report": ("Winter 2017", 2017, "W-2017", "Winter = Oct prior yr - Mar", "https://assets.ctfassets.net/6zi14rd5umxw/3v3Xh9Oyg0Eco5UdmtM22E/ea3ae1bde63a34aa610f476d9405e575/2017_Winter_Brooklyn_Retail_Report.pdf"),
    "summer-2017-brooklyn-retail-report": ("Summer 2017", 2017, "S-2017", "Summer = Apr - Sep", "https://assets.ctfassets.net/6zi14rd5umxw/1FJuf7DsIKxbJcGM3m0ylk/2b9b24dd19acf9d22758df504186fb5e/REBNY_Brooklyn_Retail_Report_Summer_2017.pdf"),
    "summer-2018-brooklyn-retail-report": ("Summer 2018", 2018, "S-2018", "Summer = Apr - Sep", "https://assets.ctfassets.net/6zi14rd5umxw/7v9NoZzePBPBJyBrJ4z8pM/cc56b694b7e901ca32286947c26682de/REBNY_Brooklyn_Retail_Report_Summer_2018.pdf"),
    "winter-2019-brooklyn-retail-report": ("Winter 2019", 2019, "W-2019", "Winter = Oct prior yr - Mar", "https://assets.ctfassets.net/6zi14rd5umxw/6XbC3V9jCokYTyDNSubbUa/e7ef32047845e68ed5317331fc163c00/REBNY_Brooklyn_Retail_Report_Winter_2019.pdf"),
    "summer-2019-brooklyn-retail-report": ("Summer 2019", 2019, "S-2019", "Summer = Apr - Sep", "https://assets.ctfassets.net/6zi14rd5umxw/3JqtRTjsP2EQlkVTVX2rYM/f14eb481ab42a28696187b86fc8785b7/2019_Summer_BrooklynRetailReport.pdf"),
    "winter-2020-brooklyn-retail-report": ("Winter 2020", 2020, "W-2020", "Winter = Oct prior yr - Mar", "https://assets.ctfassets.net/6zi14rd5umxw/4w0UxfU0nOb3vZjyRd11oQ/74043040b163ebdc22469270923fd53a/2020_Winter_BrooklynRetailReport.pdf"),
    "winter-2021-brooklyn-retail-report": ("Winter 2021", 2021, "W-2021", "Winter = Oct prior yr - Mar", "https://assets.ctfassets.net/6zi14rd5umxw/3FPtn6MjBrg7FAfwngdzoR/90d65ed99b9d3784f566b4c18e7f409f/REBNY_Brooklyn_Retail_Winter_2021.pdf"),
    "summer-2021-brooklyn-retail-report": ("Summer 2021", 2021, "S-2021", "Summer = Apr - Sep", "https://assets.ctfassets.net/6zi14rd5umxw/13NjT8lgojMaiPshX6DbOk/00b49e92f1cc4d6ef8bfaffc55a5a386/REBNY_Brooklyn_Retail_2021-Summer_FINAL.pdf"),
    "winter-2022-brooklyn-retail-report": ("Winter 2022", 2022, "W-2022", "Winter = Oct prior yr - Mar", "https://assets.ctfassets.net/6zi14rd5umxw/2TNIXGBdBCq5BRYwTBuSMA/da9729064f1c2efbeca7d2a50f6ffc0f/REBNY_2022_Report_BrooklynRetail_Winter.pdf"),
    "summer-2022-brooklyn-retail-report": ("Summer 2022", 2022, "S-2022", "Summer = Apr - Sep", "https://assets.ctfassets.net/6zi14rd5umxw/2qBP4qdtnlOFKRYQvaq993/9cf8c6a51086577f0d2d281806c0a59c/REBNY_2022_Report_BrooklynRetail_Summer_final.pdf"),
    "winter-2023-brooklyn-retail-report": ("Winter 2023", 2023, "W-2023", "Winter = Oct prior yr - Mar; later reports relabel as 1H-2023", "https://assets.ctfassets.net/6zi14rd5umxw/L5mpuQVrWtvPIbLnkfkZu/79cd84c91bca6f1cf593a6f94a760842/REBNY_2023_Report_BrooklynRetail_Winter_v04.pdf"),
    "brooklyn-retail-report-second-half-2023": ("2H 2023", 2023, "2H-2023", "second half 2023", "https://assets.ctfassets.net/6zi14rd5umxw/3lPhFFO3XK95whtGjtl8X4/b6db02a48b7477d76e424c12819789b8/REBNY_2024_Report_BrooklynRetail_H2.pdf"),
    "brooklyn-retail-report-2024": ("2024", 2024, "2024", "Jan-Oct 2024 (2025 report relabels this H2 2024)", "https://assets.ctfassets.net/6zi14rd5umxw/1ZnBEM09dl8NLyFxzVIDcP/89ee4ad7fa0c518014c2275f01e1b840/REBNY_2024_Report_BrooklynRetail_H1-24_v03final.pdf"),
    "brooklyn-retail-report-2025": ("H1 2025", 2025, "H1-2025", "first half 2025", "https://downloads.ctfassets.net/6zi14rd5umxw/2OQPh00FcwumMMHeFzfQ2e/2ff67bb2dd8f58df6e114a21bc8fb6d5/REBNY_Brooklyn_Retail_Report__2025.pdf"),
}
# Reports with no own usable table: take a prior-period column from a later report.
# (later report slug, column index of that period, period label, year, note)
BACKFILL = [
    ("summer-2018-brooklyn-retail-report", 1, "W-2018", 2018,
     "Winter 2018 report appendix has broken font encoding; value from Summer 2018 report's prior-period column"),
    ("winter-2021-brooklyn-retail-report", 1, "S-2020", 2020,
     "No Summer 2020 report published; value from Winter 2021 report's prior-period column"),
]

NEIGHBORHOODS = {"greenpoint", "williamsburg", "dumbo", "brooklyn heights", "downtown", "downtown brooklyn",
                 "prospect heights", "cobble hill", "carroll gardens", "cobble hill/carroll gardens",
                 "park slope", "bay ridge", "boerum hill", "gowanus"}

AVG_RE = re.compile(r"^\s*(AVERAGE (GROUND FLOOR|ASKING) RENT|Average Asking Rent PPSF\*?\s*$|Average PPSF\s*$)")
MED_RE = re.compile(r"^\s*(MEDIAN (GROUND FLOOR|ASKING) RENT|Median Asking Rent PPSF|Median PPSF\s*$)")
RNG_RE = re.compile(r"^\s*(RANGE OF|Asking Rent PPSF Range|PPSF Range\s*$)")
# OK to also see "ASKING RENT PSF: SELECTED" in 2015
ALL_RE = re.compile(r"^\s*ASKING RENT PSF: SELECTED")
END_RE = re.compile(r"Average Asking Rent PPSF\s*[–-]\s*Min/Max|ACKNOWLEDGEMENTS|Acknowledgements|New Lease Openings|Methodology")

TOKEN = r"(?:\$?[\d,]+(?:\.\d+)?|N/?A|NA)"
ROW_RE = re.compile(r"^\s*\"?(?P<name>[A-Za-z0-9][^$]*?[A-Za-z.)*])\s{2,}(?P<vals>(?:" + TOKEN + r"|[_-])(?:\s+(?:" + TOKEN + r"|[_-]|-?[\d.]+%|N/A))*)\s*$")


def canon(name):
    n = name.lower().replace(".", "").replace("*", "")
    n = n.replace("eighth", "8th").replace("sixth", "6th").replace("fourth", "4th").replace("fifth", "5th").replace("seventh", "7th").replace("ninth", "9th")
    if "franklin" in n: return "Franklin St (Meserole Ave - Commercial St)"
    if "manhattan ave" in n: return "Manhattan Ave (Driggs Ave - Ash St)"
    if "bedford" in n:
        if "8th" in n and "12" in n: return "Bedford Ave (N 8th St - N 12th St)"
        if "8th" in n: return "Bedford Ave (Grand St - N 8th St)"
        return "Bedford Ave (Grand St - N 12th St) [pre-split]"
    if re.search(r"north 6", n): return "N 6th St (Driggs Ave - Kent Ave)"
    if re.search(r"north 4", n): return "N 4th St (Driggs Ave - Kent Ave)"
    if n.startswith("grand st"): return "Grand St (Havemeyer St - Kent Ave)"
    if "washington" in n or n.startswith("dumbo"): return "DUMBO (Washington/Front/Water/Main St)"
    if "montague" in n: return "Montague St (Hicks St - Cadman Plaza)"
    if "fulton" in n: return "Fulton St/Fulton Mall (Boerum Pl - Flatbush Ave)"
    if "flatbush ave" in n: return "Flatbush Ave (5th Ave - Grand Army Plaza)"
    if "court st" in n and "pierrepont" in n: return "Court St (Atlantic Ave - Pierrepont St)"
    if "court st" in n: return "Court St (Atlantic Ave - Carroll St)"
    if "smith" in n: return "Smith St (Atlantic Ave - Carroll St)"
    if n.startswith("7th"): return "7th Ave (Union St - 9th St)"
    if n.startswith("5th"): return "5th Ave (Union St - 9th St)"
    if "86th" in n: return "86th St (4th Ave - Fort Hamilton Pkwy)"
    raise ValueError(f"unmapped corridor name: {name!r}")


def num(tok):
    if tok is None or re.fullmatch(r"N/?A|NA", tok):
        return None
    return float(tok.replace("$", "").replace(",", ""))


def parse_tables(text):
    """Return {kind: [(neighborhood, corridor, [value tokens])]} for kind in all/avg/med/rng (first occurrence)."""
    out, kind, nbhd = {}, None, ""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if re.fullmatch(r"\s*appendix\s*", l, re.I)), None)
    if start is None:
        start = next((max(0, i - 4) for i, l in enumerate(lines) if re.match(r"^\s*Corridor\s{2,}", l)), 0)
    for line in lines[start:]:
        if END_RE.search(line):
            kind = None
            continue
        for k, rx in (("all", ALL_RE), ("avg", AVG_RE), ("med", MED_RE), ("rng", RNG_RE)):
            if rx.search(line):
                # only keep the first table of each kind that actually has rows
                kind = k if not out.get(k) else None
                out.setdefault(k, [])
                break
        else:
            if kind is None:
                continue
            s = line.strip()
            if s.lower().rstrip(":") in NEIGHBORHOODS:
                nbhd = s
                continue
            m = ROW_RE.match(line)
            if not m:
                continue
            name = re.sub(r"\s+", " ", m.group("name")).strip()
            if name.lower().startswith(("corridor", "winter", "summer", "low", "s-20", "w-20")):
                continue
            toks = [t for t in m.group("vals").split() if t not in ("_", "-") and not t.endswith("%")]
            if not toks:
                continue
            out[kind].append((nbhd, name, toks))
    return out


def main(txt_dir, out_csv):
    rows = []
    for slug, (rlabel, year, period, cov, url) in REPORTS.items():
        f = Path(txt_dir) / f"rebny_{slug}.txt"
        t = parse_tables(f.read_text(errors="replace"))
        src = f"REBNY Brooklyn Retail Report {rlabel}"
        if "all" in t and t["all"]:  # 2015: Average, Median, Low, High in one table
            for nb, name, tk in t["all"]:
                v = [num(x) for x in tk] + [None] * 4
                rows.append(dict(source=src, report_date=rlabel, year=year, period=period, borough="Brooklyn",
                                 neighborhood=nb, corridor=canon(name), rent_psf_year_avg=v[0], rent_psf_median=v[1],
                                 rent_psf_low=v[2], rent_psf_high=v[3],
                                 notes=f"Ground-floor asking rent, available listings; {cov}; corridor as printed: {name}", source_url=url))
            continue
        if not t.get("avg"):
            print(f"WARN no average table in {slug}", file=sys.stderr)
            continue
        med = {c: tk for n, c, tk in t.get("med", [])}
        rng = {c: tk for n, c, tk in t.get("rng", [])}
        for nb, name, tk in t["avg"]:
            mt, rt = med.get(name, []), rng.get(name, [])
            agg = name.lower() in NEIGHBORHOODS
            rows.append(dict(source=src, report_date=rlabel, year=year, period=period, borough="Brooklyn",
                             neighborhood=nb if not agg else name, corridor=canon(name) if not agg else f"{name} (neighborhood aggregate)",
                             rent_psf_year_avg=num(tk[0]), rent_psf_median=num(mt[0]) if mt else None,
                             rent_psf_low=num(rt[0]) if len(rt) > 0 else None,
                             rent_psf_high=num(rt[1]) if len(rt) > 1 else None,
                             notes=f"Ground-floor asking rent, available listings; {cov}; corridor as printed: {name}", source_url=url))
    for slug, col, period, year, note in BACKFILL:
        rlabel, _, _, _, url = REPORTS[slug]
        t = parse_tables((Path(txt_dir) / f"rebny_{slug}.txt").read_text(errors="replace"))
        med = {c: tk for n, c, tk in t.get("med", [])}
        rng = {c: tk for n, c, tk in t.get("rng", [])}
        for nb, name, tk in t["avg"]:
            mt, rt = med.get(name, []), rng.get(name, [])
            agg = name.lower() in NEIGHBORHOODS
            rows.append(dict(source=f"REBNY Brooklyn Retail Report {rlabel} (prior-period column)",
                             report_date=rlabel, year=year, period=period, borough="Brooklyn",
                             neighborhood=nb if not agg else name,
                             corridor=canon(name) if not agg else f"{name} (neighborhood aggregate)",
                             rent_psf_year_avg=num(tk[col]) if len(tk) > col else None,
                             rent_psf_median=num(mt[col]) if len(mt) > col else None,
                             rent_psf_low=num(rt[2 * col]) if len(rt) > 2 * col else None,
                             rent_psf_high=num(rt[2 * col + 1]) if len(rt) > 2 * col + 1 else None,
                             notes=f"Ground-floor asking rent; {note}; corridor as printed: {name}", source_url=url))
    cols = ["source", "report_date", "year", "period", "borough", "neighborhood", "corridor",
            "rent_psf_year_avg", "rent_psf_median", "rent_psf_low", "rent_psf_high", "notes", "source_url"]
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out_csv}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
