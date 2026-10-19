"""Link OATH DOHMH-BFSCS tribunal cases to DOHMH CAMIS and extend restaurant histories back.

Step 1 (direct): ticket <-> CAMIS where violation_date == inspection_date, same borough
and respondent house number == DOHMH building (union_inspections.parquet). If several
CAMIS share the address+date, keep the one whose DBA shares most name tokens with the
respondent; ties stay ambiguous (not linked).
Step 2 (entity): an "entity" is (normalised respondent name, borough, house). If the
entity's directly-linked tickets point to one CAMIS for >= 80% of them, every ticket of
that entity (including pre-2009 ones) is linked to that CAMIS.

Outputs (data/raw/early/):
  oath_bfscs_camis.csv.gz   ticket_number, violation_date, camis, method
  oath_entities.csv.gz      one row per entity: name, boro, house, zip, first/last date,
                            n_tickets, camis (if linked)
  early_camis_first_seen.csv  per linked CAMIS: first OATH date, first DOHMH inspection date
Run:  .venv/bin/python pipeline/early_link.py
"""
from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
EARLY = ROOT / "data/raw/early"
OATH = EARLY / "oath_bfscs.csv.gz"
UNION = ROOT / "data/raw/dohmh/union_inspections.parquet"

BORO = """case {c} when 'MANHATTAN' then '1' when 'BRONX' then '2' when 'BROOKLYN' then '3'
  when 'QUEENS' then '4' when 'STATEN IS' then '5' when 'STATEN ISLAND' then '5'
  when '1' then '1' when '2' then '2' when '3' then '3' when '4' then '4' when '5' then '5' end"""
# legal-form and filler words dropped before comparing names
STOP = ["INC", "CORP", "CORPORATION", "LLC", "LTD", "CO", "THE", "OF", "AND", "INCORPORATED",
        "DBA", "D/B/A", "REST", "RESTAURANT", "NY", "NYC", "LIMITED", "COMPANY"]


def main() -> None:
    for p in (OATH, UNION):
        if not p.exists():
            raise SystemExit(f"missing input {p}")
    con = duckdb.connect()
    stop = ", ".join(f"'{w}'" for w in STOP)
    con.sql(f"""create macro toks(s) as list_filter(
        string_split(regexp_replace(upper(coalesce(s, '')), '[^A-Z0-9 ]', ' ', 'g'), ' '),
        x -> length(x) > 1 and not list_contains([{stop}], x))""")
    con.sql(f"""create table o as select ticket_number,
        try_cast(substr(violation_date, 1, 10) as date) d,
        upper(trim(respondent_address_house)) house, {BORO.format(c='violation_location_borough')} b,
        violation_location_zip_code as zip, respondent_last_name as rname,
        array_to_string(list_sort(list_distinct(toks(respondent_last_name))), ' ') nkey
        from read_csv('{OATH}', all_varchar=true)
        where respondent_address_house is not null""")
    con.sql(f"""create table u as select camis, inspection_date d, upper(trim(building)) house,
        {BORO.format(c='upper(boro)')} b, dba from '{UNION}' where camis not like 'X%'""")

    # step 1: direct date+address matches, disambiguated by name-token overlap
    con.sql("""create table cand as select o.ticket_number, u.camis,
        len(list_intersect(toks(o.rname), toks(u.dba))) ov
        from o join u on o.d = u.d and o.b = u.b and o.house = u.house""")
    con.sql("""create table direct as
        with r as (select *, max(ov) over w mx from cand
                   window w as (partition by ticket_number))
        select ticket_number, camis from r where ov = mx
        qualify count(*) over (partition by ticket_number) = 1""")

    # step 2: propagate along (name key, boro, house) entities
    con.sql("""create table ent as select nkey, b, house, min(d) first_d, max(d) last_d,
        count(*) n_tickets, any_value(zip) zip, any_value(rname) as rname
        from o where nkey <> '' group by all""")
    con.sql("""create table ent_camis as
        with c as (select o.nkey, o.b, o.house, dr.camis, count(*) k
                   from o join direct dr using (ticket_number) group by all),
             t as (select *, sum(k) over (partition by nkey, b, house) tot from c)
        select nkey, b, house, camis from t where k >= 0.8 * tot""")
    con.sql("""create table link as
        select o.ticket_number, o.d violation_date, coalesce(dr.camis, ec.camis) camis,
               case when dr.camis is not null then 'date_addr' else 'entity' end as method
        from o left join direct dr using (ticket_number)
        left join ent_camis ec using (nkey, b, house)
        where coalesce(dr.camis, ec.camis) is not null""")
    con.sql(f"copy (select * from link order by violation_date, ticket_number) to '{EARLY / 'oath_bfscs_camis.csv.gz'}' (header, compression gzip)")
    con.sql(f"""copy (select e.rname as respondent, e.nkey, e.b boro, e.house, e.zip, e.first_d, e.last_d, e.n_tickets, ec.camis
        from ent e left join ent_camis ec using (nkey, b, house) order by first_d)
        to '{EARLY / 'oath_entities.csv.gz'}' (header, compression gzip)""")
    con.sql(f"""copy (select l.camis, min(l.violation_date) first_oath, f.first_insp,
            datediff('day', min(l.violation_date), f.first_insp) days_earlier, count(*) n_tickets
        from link l join (select camis, min(d) first_insp from u where d > '1900-01-01' group by 1) f using (camis)
        group by l.camis, f.first_insp order by 1)
        to '{EARLY / 'early_camis_first_seen.csv'}' (header)""")

    print(con.sql("select method, count(*) tickets, count(distinct camis) camis from link group by 1"))
    print(con.sql("""select year(violation_date) y, count(*) tickets, count(distinct camis) camis
        from link where violation_date < '2012-07-06' group by 1 order by 1"""))
    print(con.sql(f"""select count(*) camis, count(*) filter (where days_earlier > 30) pushed_earlier,
        count(*) filter (where first_oath < '2008-01-01') first_before_2008,
        median(days_earlier) filter (where days_earlier > 30) median_days
        from read_csv('{EARLY / 'early_camis_first_seen.csv'}')"""))
    print(con.sql("""select count(*) entities, count(*) filter (where camis is null) unlinked,
        count(*) filter (where camis is null and last_d < '2012-07-06') unlinked_pre2012,
        count(*) filter (where camis is null and last_d < '2009-01-01') unlinked_closed_pre2009
        from ent e left join ent_camis ec using (nkey, b, house)"""))


if __name__ == "__main__":
    main()
