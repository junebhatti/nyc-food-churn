"""Early (pre-2012-07) NYC restaurant history. See data/notes/early.md.

Run:  .venv/bin/python pipeline/fetch_early.py
  1. early_oath.py  - OATH tribunal cases issued by DOHMH food safety (BFSCS), to 2014
  2. early_link.py  - link tickets to DOHMH CAMIS, write first-seen dates
early_ia.py is the shared, throttled archive.org client used for the Wayback searches.
"""
import early_link
import early_oath

if __name__ == "__main__":
    if not early_oath.OUT.exists():
        early_oath.main()
    early_link.main()
