# Bars 2011–2014 (partial; agent stopped 2026-10-18 for diminishing returns)

The agent was stopped before it reported, and its community board PDF download was killed mid-run. Outputs are partial but read cleanly:

| file | rows | what |
|---|---|---|
| `data/raw/bars/bars_pre2015_evidence.parquet` | 5,755 | lots with pre-2015 bar evidence (combined) |
| `data/raw/bars/cb_sla_items.parquet` | 1,645 | community board liquor items beyond CB3 (download incomplete) |
| `data/raw/bars/cabaret_licenses.parquet` | 594 | DCA cabaret licenses |
| `data/raw/bars/sla_snapshot_20160219.parquet` | 6,659 | 2016-02 NYSLA on-premises snapshot, normalized |

Code: `pipeline/fetch_bars.py`, `pipeline/bars_*.py`. Check row-level provenance before use; this pass was never audited.
To resume the CB download: `cd pipeline && ../.venv/bin/python -W ignore -u bars_cb.py download` (archive.org, one client).
