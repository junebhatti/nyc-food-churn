# DOHMH gap filling, round 3: extra2 copies

Status 2026-10-18. Round 3 adds **8 copies** (6 FULL, 2 PARTIAL... see table) in `data/raw/dohmh/extra2/`, registered in `manifest.csv` as `extra2/<name>`. `pipeline/dohmh_extra2.py` re-creates them (it reuses the fetch/xlsx helpers of `dohmh_extra.py`), and `dohmh_profile.py` picks them up unchanged. Read `dohmh_gaps.md` first for rounds 1–2.

PLACEHOLDER
