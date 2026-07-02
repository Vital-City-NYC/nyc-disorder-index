#!/usr/bin/env python3
# Title: Disorder index data pipeline
# Author: Generated with Claude Code for Vital City
# Date: 2026-07-02
# Data sources:
#   - 311 Service Requests from 2010 to Present (NYC Open Data, erm2-nwe9),
#     created_date 2021-01-01 through 2026-06-30. Accessed 2026-07-02.
#   - data/cd_populations.json (2020 decennial census, see build_populations.py)
# Description: Pulls server-side aggregates from the 311 dataset (no raw rows),
#   groups complaint types into ten strands of street disorder, and writes
#   data/disorder_data.json with monthly series, 12-month comparisons,
#   citywide standings and a concentration flag for districts where a small
#   number of addresses drives a strand's numbers.
# Dependencies: Python 3.9+ standard library only.

import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
BASE = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"

# Analysis window: 66 complete months.
START = "2021-01-01"
END = "2026-07-01"          # exclusive
LAST12_START = "2025-07-01"  # last 12 complete months
PRIOR12_START = "2024-07-01"

# The ten strands. Complaint types are exact values in the 311 dataset.
# Every 311 record whose complaint_type appears here is counted; nothing else is.
STRANDS = [
    {"id": "noise", "label": "Noise", "types": [
        "Noise - Residential", "Noise - Street/Sidewalk", "Noise - Commercial",
        "Noise - Vehicle", "Noise", "Noise - Park", "Noise - House of Worship"],
     "desc": "Loud music, parties, shouting and engine noise from homes, streets, businesses, vehicles and parks. Excludes helicopter noise."},
    {"id": "homelessness", "label": "Street homelessness", "types": [
        "Encampment", "Homeless Person Assistance"],
     "desc": "Reports of encampments and requests for outreach to homeless individuals in public spaces."},
    {"id": "rodents", "label": "Rats and rodents", "types": ["Rodent"],
     "desc": "Rat and mouse sightings and conditions attracting rodents."},
    {"id": "dirty", "label": "Dirty streets", "types": [
        "Dirty Condition", "Litter Basket Complaint"],
     "desc": "Litter, filthy sidewalks and overflowing public litter baskets. Excludes missed trash collection, which is a service failure rather than observed street conditions."},
    {"id": "dumping", "label": "Illegal dumping", "types": ["Illegal Dumping"],
     "desc": "Trash, debris or bulk items dumped illegally in public spaces or lots."},
    {"id": "graffiti", "label": "Graffiti", "types": ["Graffiti"],
     "desc": "Graffiti reported on buildings and public property."},
    {"id": "vehicles", "label": "Abandoned vehicles", "types": [
        "Abandoned Vehicle", "Derelict Vehicles"],
     "desc": "Cars left on streets without plates or in derelict condition, reported to police and sanitation."},
    {"id": "drugs", "label": "Public drug and alcohol use", "types": [
        "Drug Activity", "Drinking", "Urinating in Public"],
     "desc": "Reported drug activity, public drinking and public urination. Public urination generates few 311 calls and is likely undercounted."},
    {"id": "panhandling", "label": "Panhandling", "types": ["Panhandling"],
     "desc": "Reports of panhandling. Panhandling itself is legal; 311 accepts reports about aggressive or traffic-obstructing solicitation."},
    {"id": "decay", "label": "Streets in disrepair", "types": [
        "Street Condition", "Sidewalk Condition"],
     "desc": "Potholes, cave-ins, broken pavement and damaged sidewalks — physical decay of the streetscape."},
]

ALL_TYPES = [t for s in STRANDS for t in s["types"]]
TYPE_TO_STRAND = {t: s["id"] for s in STRANDS for t in s["types"]}

BORO_WORD_TO_CODE = {"MANHATTAN": 1, "BRONX": 2, "BROOKLYN": 3, "QUEENS": 4, "STATEN ISLAND": 5}


def cb_to_borocd(cb):
    """'01 MANHATTAN' -> '101'; returns None for Unspecified/JIA boards."""
    parts = cb.strip().split(" ", 1)
    if len(parts) != 2 or not parts[0].isdigit():
        return None
    num, boro = int(parts[0]), parts[1].strip().upper()
    if boro not in BORO_WORD_TO_CODE:
        return None
    boro_cd = BORO_WORD_TO_CODE[boro] * 100 + num
    return str(boro_cd)


def soda(params):
    url = BASE + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.load(r)
        except Exception as e:
            if attempt == 3:
                raise
            print(f"  retry {attempt+1} after {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def in_list(types):
    return "complaint_type in (" + ", ".join("'" + t.replace("'", "''") + "'" for t in types) + ")"


def main():
    pops = json.load(open(os.path.join(DATA, "cd_populations.json")))["populations"]
    cd_names = json.load(open(os.path.join(DATA, "cd_names.json")))

    # --- Query 1: monthly counts by board x complaint type -------------------
    print("Query 1: monthly counts by community board and complaint type ...")
    where = f"created_date >= '{START}' and created_date < '{END}' and " + in_list(ALL_TYPES)
    rows = soda({
        "$select": "community_board, complaint_type, date_trunc_ym(created_date) as month, count(*) as n",
        "$where": where,
        "$group": "community_board, complaint_type, month",
        "$limit": "300000",
    })
    print(f"  {len(rows)} aggregate rows")
    if len(rows) >= 300000:
        sys.exit("hit row limit; page the query")

    # months axis
    months = []
    y, m = 2021, 1
    while (y, m) < (2026, 7):
        months.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    mi = {mm: i for i, mm in enumerate(months)}

    # per-district and citywide monthly series per strand
    def blank():
        return {s["id"]: [0] * len(months) for s in STRANDS}
    district_monthly = {}
    citywide_monthly = blank()
    dropped = 0  # counts in Unspecified / park boards (still in citywide totals)
    for r in rows:
        sid = TYPE_TO_STRAND.get(r["complaint_type"])
        if sid is None:
            continue
        idx = mi[r["month"][:7]]
        n = int(r["n"])
        citywide_monthly[sid][idx] += n
        bcd = cb_to_borocd(r.get("community_board", ""))
        if bcd is None or bcd not in pops:
            dropped += n
            continue
        district_monthly.setdefault(bcd, blank())[sid][idx] += n
    total = sum(sum(v) for v in citywide_monthly.values())
    print(f"  total complaints in window: {total:,}; not assignable to a district: {dropped:,} ({dropped/total:.1%})")

    # --- Query 2 + 3: distinct addresses, last 12 and prior 12 months --------
    def addr_query(start, end):
        return soda({
            "$select": "community_board, complaint_type, count(*) as n, count(distinct incident_address) as addrs",
            "$where": f"created_date >= '{start}' and created_date < '{end}' and " + in_list(ALL_TYPES),
            "$group": "community_board, complaint_type",
            "$limit": "50000",
        })
    print("Query 2: distinct addresses, last 12 months ...")
    addr_last = addr_query(LAST12_START, END)
    print("Query 3: distinct addresses, prior 12 months ...")
    addr_prior = addr_query(PRIOR12_START, LAST12_START)

    def addr_rollup(rows_):
        out = {}
        for r in rows_:
            sid = TYPE_TO_STRAND.get(r["complaint_type"])
            bcd = cb_to_borocd(r.get("community_board", ""))
            if sid is None or bcd is None:
                continue
            d = out.setdefault(bcd, {}).setdefault(sid, {"n": 0, "addrs": 0})
            d["n"] += int(r["n"])
            d["addrs"] += int(r["addrs"])  # summed across types; approximate, see methodology
        return out
    a_last = addr_rollup(addr_last)

    # --- Derived metrics ------------------------------------------------------
    n_last_idx = [i for i, mm in enumerate(months) if mm >= LAST12_START[:7]]
    n_prior_idx = [i for i, mm in enumerate(months) if PRIOR12_START[:7] <= mm < LAST12_START[:7]]
    assert len(n_last_idx) == 12 and len(n_prior_idx) == 12

    citypop = sum(pops.values())
    citywide = {}
    for s in STRANDS:
        sid = s["id"]
        series = citywide_monthly[sid]
        n12 = sum(series[i] for i in n_last_idx)
        p12 = sum(series[i] for i in n_prior_idx)
        citywide[sid] = {
            "monthly": series, "n12": n12, "prior12": p12,
            "pct": round((n12 - p12) / p12 * 100, 1) if p12 else None,
            "rate": round(n12 / citypop * 1000, 2),
        }

    # city-level concentration baseline per strand (complaints per address)
    city_conc = {}
    for s in STRANDS:
        sid = s["id"]
        tn = sum(v.get(sid, {}).get("n", 0) for v in a_last.values())
        ta = sum(v.get(sid, {}).get("addrs", 0) for v in a_last.values())
        city_conc[sid] = tn / ta if ta else None

    districts = {}
    for bcd, strands in district_monthly.items():
        pop = pops[bcd]
        dd = {}
        for s in STRANDS:
            sid = s["id"]
            series = strands[sid]
            n12 = sum(series[i] for i in n_last_idx)
            p12 = sum(series[i] for i in n_prior_idx)
            ai = a_last.get(bcd, {}).get(sid, {})
            conc = (ai.get("n", 0) / ai["addrs"]) if ai.get("addrs") else None
            dd[sid] = {
                "monthly": series, "n12": n12, "prior12": p12,
                "pct": round((n12 - p12) / p12 * 100, 1) if p12 >= 30 else None,
                "rate": round(n12 / pop * 1000, 2),
                "addrs12": ai.get("addrs"),
                "conc": round(conc, 1) if conc else None,
                # flag: complaints per address at least 3x the citywide strand
                # norm and a meaningful volume -> a few addresses drive the number
                "conc_flag": bool(conc and city_conc[sid] and n12 >= 100 and conc >= 3 * city_conc[sid]),
            }
        districts[bcd] = {"name": cd_names[bcd], "borough": {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn", "4": "Queens", "5": "Staten Island"}[bcd[0]],
                          "population": pop, "strands": dd}

    # standings: rank of each district's last-12-month rate within each strand
    for s in STRANDS:
        sid = s["id"]
        ranked = sorted(districts, key=lambda b: districts[b]["strands"][sid]["rate"], reverse=True)
        for pos, bcd in enumerate(ranked):
            st = districts[bcd]["strands"][sid]
            st["rank"] = pos + 1  # 1 = highest report rate of 59
            st["tercile"] = "high" if pos < 20 else ("mid" if pos < 39 else "low")

    out = {
        "meta": {
            "generated": time.strftime("%Y-%m-%d"),
            "months": months,
            "last12": [months[n_last_idx[0]], months[n_last_idx[-1]]],
            "prior12": [months[n_prior_idx[0]], months[n_prior_idx[-1]]],
            "citywide_population": citypop,
            "total_complaints": total,
            "unassigned_share": round(dropped / total, 4),
            "source": "311 Service Requests from 2010 to Present (NYC Open Data, erm2-nwe9), accessed 2026-07-02; populations: 2020 decennial census",
        },
        "strands": [{"id": s["id"], "label": s["label"], "desc": s["desc"], "types": s["types"],
                     "citywide": citywide[s["id"]]} for s in STRANDS],
        "districts": districts,
    }
    path = os.path.join(DATA, "disorder_data.json")
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {path} ({os.path.getsize(path)/1e6:.1f} MB), {len(districts)} districts")

    # summary for cross-checking against the published page
    print("\nCitywide, last 12 months vs prior 12:")
    for s in STRANDS:
        c = citywide[s["id"]]
        print(f"  {s['label']:<28} {c['n12']:>8,} vs {c['prior12']:>8,}  ({c['pct']:+.1f}%)")


if __name__ == "__main__":
    main()
