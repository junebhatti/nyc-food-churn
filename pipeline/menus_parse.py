"""Parse an archived MenuPages restaurant or /menu page (2009-2018 layouts).

Returns header fields (name, address, lat/lon, $-rating, cuisine, neighborhood) and
the priced menu items as [section, item, price] (price = highest price on the row,
e.g. the large size or the dinner column).
"""
from __future__ import annotations

import html as htmllib
import re
import statistics

F = re.S | re.I
RX = {
    "name": re.compile(r'class="(?:title1respage fn|fn org)"[^>]*>([^<]+)', F),
    "price_key": re.compile(r'class="price-key pricerange">\s*(\$+)', F),
    "price_meta": re.compile(r'content\.price" content="(\$+)"', F),
    "cuisine": re.compile(r'class="cuisine category">([^<]*)', F),
    "street": re.compile(r'class="addr street-address">([^<]*)', F),
    "locality": re.compile(r'class="locality">([^<]*)', F),
    "zip": re.compile(r'class="postal-code">([^<]*)', F),
    "lat": re.compile(r'class="latitude">\s*(-?[\d.]+)', F),
    "lon": re.compile(r'class="longitude">\s*(-?[\d.]+)', F),
    "cross": re.compile(r'class="cross-street">([^<]*)', F),
    "hood": re.compile(r'neighborhood - ([a-z0-9-]+)', F),
    "serving": re.compile(r'Now Serving: <strong>(\d+)</strong>', F),
}
HEAD_RE = re.compile(r"<h[23][^>]*>(.*?)</h[23]>", F)
ROW_RE = re.compile(r"<tr[^>]*>\s*<th[^>]*>(.*?)</th>(.*?)</tr>", F)
CITE_RE = re.compile(r"<cite>(.*?)</cite>", F)
PRICE_RE = re.compile(r"(?<![\d.])(\d{1,4}\.\d{2})(?![\d])")
TAG_RE = re.compile(r"<[^>]+>")

# Sections that are not main courses (for the "median main" price).
NOT_MAIN = re.compile(
    r"appeti|starter|small plate|tapas|side|dessert|sweet|pastr|bakery|beverage|drink|"
    r"coffee|espresso|\btea\b|juice|smoothie|shake|soda|wine|beer|cocktail|liquor|spirit|"
    r"sake|\bbar\b|happy hour|extra|add[- ]?on|condiment|topping|sauce|dressing|kid|child|"
    r"breakfast|brunch|lunch|soup|salad|\bdips?\b|snack|bagel|muffin|donut|ice cream|"
    r"gelato|catering|party|platter tray|by the pound|per pound|\blb\b|\bpcs?\b|"
    r"bread|cheese plate|dim sum|oyster|raw bar|bottle|by the glass|pre-?theat|prix|tasting",
    re.I)


def _txt(s: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(TAG_RE.sub(" ", s))).strip()


def _first(key: str, h: str) -> str | None:
    m = RX[key].search(h)
    return _txt(m.group(1)) if m else None


def parse_items(h: str) -> list[list]:
    start = h.find('id="restaurant-menu"')
    if start < 0:
        m = re.search(r'<table class="prices', h)
        start = m.start() if m else -1
    if start < 0:
        return []
    body = h[start:]
    heads = [(m.start(), _txt(m.group(1))) for m in HEAD_RE.finditer(body)]
    items, hi = [], 0
    section = ""
    for m in ROW_RE.finditer(body):
        while hi < len(heads) and heads[hi][0] < m.start():
            section = heads[hi][1]
            hi += 1
        cite = CITE_RE.search(m.group(1))
        if not cite:
            continue
        prices = [float(p) for p in PRICE_RE.findall(_txt(m.group(2)))]
        prices = [p for p in prices if 0 < p < 1000]
        if prices:
            items.append([section[:80], _txt(cite.group(1))[:120], max(prices)])
    return items


def summarize(items: list[list]) -> dict:
    allp = [p for _, _, p in items]
    mains = [p for s, _, p in items if not NOT_MAIN.search(s) and 4 <= p <= 250]
    return {
        "n_items_priced": len(allp),
        "n_main_items": len(mains),
        "median_item_price": statistics.median(allp) if allp else None,
        "median_main_price": statistics.median(mains) if len(mains) >= 3 else None,
        "p75_item_price": statistics.quantiles(allp, n=4)[2] if len(allp) >= 4 else None,
    }


def parse_page(h: str) -> dict:
    rec = {k: _first(k, h) for k in RX}
    rec["price_level"] = rec.pop("price_key") or rec.pop("price_meta")
    rec.pop("price_meta", None)
    items = parse_items(h)
    rec.update(summarize(items))
    rec["items"] = items
    return rec
