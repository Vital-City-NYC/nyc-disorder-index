#!/usr/bin/env python3
# Title: The conditions layer — inspection data that corroborates 311 strands
# Author: Generated with Claude Code for Vital City
# Date: 2026-07-02
# Data sources:
#   - Rodent Inspection (NYC Open Data, p937-wjvj), DOHMH pest-control
#     inspections. Initial inspections, inspection_date 2024-07-01 through
#     2026-06-30. Accessed 2026-07-02.
#   - Street Pavement Ratings (NYC Open Data, 6yyb-pb25), DOT road-surface
#     ratings. Segments inspected 2023-01-01 onward. Accessed 2026-07-02.
#   - data/community_districts.geojson (DCP boundaries) for point-in-polygon.
# Description: Unlike the 311 strands (which count resident *reports*), these
#   are *inspections* — the city sending someone to look. They let the site
#   show reports next to conditions. Writes data/conditions_data.json keyed by
#   the strand each one corroborates ("rodents", "decay").
# Dependencies: Python 3.9+, shapely 2.x. Standard library for HTTP.

import json
import os
import sys
import time
import urllib.parse
import urllib.request

from shapely.geometry import shape, Point
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

LAST12_START, PRIOR12_START, END = "2025-07-01", "2024-07-01", "2026-07-01"
BOROUGH = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn", "4": "Queens", "5": "Staten Island"}


# ---- point-in-polygon: assign a lon/lat to a community district ------------
def build_locator():
    geo = json.load(open(os.path.join(DATA, "community_districts.geojson")))
    polys, codes = [], []
    for f in geo["features"]:
        polys.append(shape(f["geometry"]))
        codes.append(f["properties"]["cd_code"])
    tree = STRtree(polys)

    # ~0.0015 deg ≈ 150 m: recovers waterfront points that the shoreline-clipped
    # boundaries drop, without reaching across rivers into another district.
    TOL = 0.0015

    def locate(lon, lat):
        p = Point(lon, lat)
        for i in tree.query(p):          # bbox candidates, then exact test
            if polys[i].contains(p):
                return codes[i]
        j = tree.nearest(p)              # fallback: nearest district if very close
        if polys[j].distance(p) <= TOL:
            return codes[j]
        return None
    return locate


def soda(dataset, params):
    url = f"https://data.cityofnewyork.us/resource/{dataset}.json?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                return json.load(r)
        except Exception as e:
            if attempt == 3:
                raise
            print(f"  retry {attempt+1}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def paginate(dataset, params, page=50000):
    """Pull every row for a query in $id order (stable pagination)."""
    out, offset = [], 0
    while True:
        p = dict(params, **{"$limit": str(page), "$offset": str(offset), "$order": ":id"})
        rows = soda(dataset, p)
        out.extend(rows)
        if len(rows) < page:
            return out
        offset += page
        print(f"    …{len(out)} rows", file=sys.stderr)


def rate_trend(last, prior, min_base=30):
    """Relative percent change between two rates, with the site's ±10% words.
       No call when the prior window is too thin to be meaningful."""
    if prior["base"] < min_base or last["base"] < min_base or prior["rate"] == 0:
        return None, None
    pct = round((last["rate"] - prior["rate"]) / prior["rate"] * 100, 1)
    word = "rising" if pct >= 10 else ("falling" if pct <= -10 else "steady")
    return pct, word


def rank_and_terciles(districts, keyfn, reverse=True):
    ranked = sorted(districts, key=keyfn, reverse=reverse)
    for pos, bcd in enumerate(ranked):
        yield bcd, pos + 1, ("high" if pos < 20 else ("mid" if pos < 39 else "low"))


def main():
    locate = build_locator()
    out = {"meta": {"generated": time.strftime("%Y-%m-%d")}, "strands": {}}

    # ========================================================================
    # RODENT INSPECTIONS  ->  corroborates the "rats and rodents" strand
    # Metric: of DOHMH *initial* inspections, the share that found active rat
    # signs ("Failed for Rat Activity"). This is inspectors looking, not
    # residents calling — an independent read on where rats actually are.
    # ========================================================================
    print("Rodent inspections: pulling initial inspections, 24 months ...")
    rows = paginate("p937-wjvj", {
        "$select": "latitude,longitude,result,inspection_date",
        "$where": f"inspection_type='Initial' and inspection_date >= '{PRIOR12_START}' "
                  f"and inspection_date < '{END}' and latitude IS NOT NULL",
    })
    print(f"  {len(rows):,} inspections with coordinates")

    def blank():
        return {"last": {"base": 0, "hit": 0}, "prior": {"base": 0, "hit": 0}}
    dist = {}
    city = blank()
    unlocated = 0
    for r in rows:
        try:
            lon, lat = float(r["longitude"]), float(r["latitude"])
        except (TypeError, ValueError):
            continue
        window = "last" if r["inspection_date"] >= LAST12_START else "prior"
        hit = 1 if str(r["result"]).startswith("Failed for Rat Activity") else 0
        city[window]["base"] += 1
        city[window]["hit"] += hit
        bcd = locate(lon, lat)
        if bcd is None:
            unlocated += 1
            continue
        d = dist.setdefault(bcd, blank())
        d[window]["base"] += 1
        d[window]["hit"] += hit
    print(f"  {unlocated:,} inspections fell outside all 59 districts (parks, water, geocoding)")

    def rate(w):
        return round(w["hit"] / w["base"] * 100, 1) if w["base"] else 0.0

    city_last, city_prior = {"rate": rate(city["last"]), "base": city["last"]["base"]}, \
                            {"rate": rate(city["prior"]), "base": city["prior"]["base"]}
    cpct, cword = rate_trend(city_last, city_prior)
    rodents = {
        "source": "Rodent Inspection", "source_id": "p937-wjvj",
        "source_url": "https://data.cityofnewyork.us/resource/p937-wjvj",
        "kind": "inspection", "trendable": True,
        "metric_label": "of city rat inspections found active rat signs",
        "short_label": "found active rat signs",
        "window": f"{LAST12_START[:7]} to {END[:7]}, initial inspections only",
        "citywide": {"value": city_last["rate"], "prior": city_prior["rate"],
                     "base": city_last["base"], "pct": cpct, "trend": cword},
        "districts": {},
    }
    for bcd, d in dist.items():
        last = {"rate": rate(d["last"]), "base": d["last"]["base"]}
        prior = {"rate": rate(d["prior"]), "base": d["prior"]["base"]}
        pct, word = rate_trend(last, prior)
        rodents["districts"][bcd] = {"value": last["rate"], "prior": prior["rate"],
                                     "base": last["base"], "pct": pct, "trend": word}
    for bcd, rk, terc in rank_and_terciles(rodents["districts"], lambda b: rodents["districts"][b]["value"]):
        rodents["districts"][bcd]["rank"] = rk
        rodents["districts"][bcd]["tercile"] = terc
    out["strands"]["rodents"] = rodents
    print(f"  citywide: {city_last['rate']}% of inspections found rats "
          f"(was {city_prior['rate']}%), {city_last['base']:,} inspections")

    # ========================================================================
    # STREET PAVEMENT RATINGS  ->  corroborates "streets in disrepair"
    # DOT rates road segments 1-10 (10 = best). Ratings are done on a rolling
    # multi-year cycle, so this is a *condition snapshot*, NOT a 12-month
    # trend. We use segments inspected 2023 onward, keep each segment's most
    # recent rating, and length-weight so a long bad road counts more than a
    # short one. Reported: length-weighted share of rated roadway in poor
    # condition (rating below 4) and the average rating.
    # ========================================================================
    print("Street pavement ratings: pulling segments inspected 2023+ ...")
    prows = paginate("6yyb-pb25", {
        "$select": "the_geom,systemrating,inspection,locationgeometry_stlength,oftcode",
        "$where": "systemrating > 0 and inspection >= '2023-01-01'",
    })
    print(f"  {len(prows):,} rated segments")

    # keep most recent rating per segment id (oftcode)
    latest = {}
    for r in prows:
        oid = r.get("oftcode")
        if oid is None or r.get("the_geom") is None:
            continue
        if oid not in latest or r["inspection"] > latest[oid]["inspection"]:
            latest[oid] = r
    print(f"  {len(latest):,} unique segments after keeping latest rating")

    pdist = {}   # bcd -> {"len": total_ft, "poor_len": ft_poor, "wsum": len*rating}
    pcity = {"len": 0.0, "poor_len": 0.0, "wsum": 0.0}
    years = []
    for r in latest.values():
        try:
            rating = float(r["systemrating"])
            length = float(r["locationgeometry_stlength"])
        except (TypeError, ValueError):
            continue
        coords = r["the_geom"]["coordinates"]
        # representative point: midpoint of the first line in the multiline
        line = coords[0]
        lon, lat = line[len(line) // 2]
        years.append(r["inspection"][:4])
        poor = length if rating < 4 else 0.0
        pcity["len"] += length
        pcity["poor_len"] += poor
        pcity["wsum"] += length * rating
        bcd = locate(lon, lat)
        if bcd is None:
            continue
        d = pdist.setdefault(bcd, {"len": 0.0, "poor_len": 0.0, "wsum": 0.0})
        d["len"] += length
        d["poor_len"] += poor
        d["wsum"] += length * rating

    def share_poor(d):
        return round(d["poor_len"] / d["len"] * 100, 1) if d["len"] else None

    def avg_rating(d):
        return round(d["wsum"] / d["len"], 1) if d["len"] else None

    yrs = sorted(set(years))
    decay = {
        "source": "Street Pavement Ratings", "source_id": "6yyb-pb25",
        "source_url": "https://data.cityofnewyork.us/resource/6yyb-pb25",
        "kind": "inspection", "trendable": False,
        "metric_label": "of rated roadway in poor condition",
        "short_label": "of rated roadway in poor condition",
        "window": f"roads last inspected {yrs[0]}–{yrs[-1]}; a condition snapshot, not a 12-month trend",
        "citywide": {"value": share_poor(pcity), "avg_rating": avg_rating(pcity),
                     "miles": round(pcity["len"] / 5280, 0)},
        "districts": {},
    }
    for bcd, d in pdist.items():
        decay["districts"][bcd] = {"value": share_poor(d), "avg_rating": avg_rating(d),
                                   "miles": round(d["len"] / 5280, 1)}
    for bcd, rk, terc in rank_and_terciles(decay["districts"], lambda b: decay["districts"][b]["value"] or 0):
        decay["districts"][bcd]["rank"] = rk
        decay["districts"][bcd]["tercile"] = terc
    out["strands"]["decay"] = decay
    print(f"  citywide: {decay['citywide']['value']}% of rated roadway poor, "
          f"avg rating {decay['citywide']['avg_rating']}/10")

    path = os.path.join(DATA, "conditions_data.json")
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"\nwrote {path} ({os.path.getsize(path)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
