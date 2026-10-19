"""NYS DOS Active Corporations (data.ny.gov n9v6-gdp6): service-of-process address per entity.

Entities sharing a process address (that is not a registered-agent / law-firm hub) are probably
run by the same operator. Only entity names already linked to a CAMIS are kept, and the address
is stored only as a hashed group id plus the number of food entities and all entities at it:
no person names or street addresses are written out.

CAVEAT: the dataset lists ACTIVE entities only, so dissolved operators are missing (survivor bias).
Output: entity_process_groups.parquet
"""
from __future__ import annotations

import hashlib
import io
import re

import pandas as pd

from ai_common import OUT, WEB, log, norm_name, write_out

URL = ("https://data.ny.gov/resource/n9v6-gdp6.csv?$select=dos_id,current_entity_name,initial_dos_filing_date,"
       "dos_process_address_1,dos_process_zip&$where=county in('New York','Kings','Queens','Bronx','Richmond')"
       "&$order=dos_id&$limit=50000&$offset={}")


def addr_key(a, z) -> str | None:
    if not isinstance(a, str) or not a.strip():
        return None
    a = re.sub(r"[^A-Z0-9 ]", " ", a.upper())
    a = re.sub(r"\b(SUITE|STE|FL|FLOOR|RM|ROOM|APT|UNIT)\b.*$", "", a)
    a = re.sub(r"\s+", " ", a).strip()
    return f"{a}|{str(z)[:5]}"


def build():
    keys = set(pd.read_parquet(OUT / "camis_entity_links.parquet", columns=["legal_key"])["legal_key"])
    keep, allcount = [], {}
    off = 0
    while True:
        r = WEB.get(URL.format(off), timeout=180)
        r.raise_for_status()
        d = pd.read_csv(io.StringIO(r.text), dtype=str)
        if d.empty:
            break
        d["ak"] = [addr_key(a, z) for a, z in zip(d["dos_process_address_1"], d["dos_process_zip"])]
        for k, n in d["ak"].value_counts().items():
            allcount[k] = allcount.get(k, 0) + n
        d["legal_key"] = d["current_entity_name"].map(norm_name)
        keep.append(d[d["legal_key"].isin(keys)][["dos_id", "legal_key", "initial_dos_filing_date", "ak"]])
        off += len(d)
        log.info("DOS active offset %d, kept %d", off, sum(map(len, keep)))
        if len(d) < 50000:
            break
    k = pd.concat(keep, ignore_index=True).dropna(subset=["ak"])
    k["n_entities_at_addr_all"] = k["ak"].map(allcount)
    k["n_food_entities_at_addr"] = k.groupby("ak")["legal_key"].transform("nunique")
    k["process_addr_group"] = [hashlib.sha1(a.encode()).hexdigest()[:12] for a in k["ak"]]
    # hubs: registered agents / accountants / lawyers serve hundreds of unrelated entities
    k["hub_address"] = k["n_entities_at_addr_all"] > 25
    k = k.drop(columns="ak")
    write_out(k, "entity_process_groups", "data.ny.gov n9v6-gdp6 (NYS DOS Active Corporations), NYC counties",
              "linked legal entities only; address hashed; hub_address = >25 entities of any kind share it")


if __name__ == "__main__":
    build()
