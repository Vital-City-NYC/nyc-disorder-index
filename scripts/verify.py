#!/usr/bin/env python3
# Independent verification of the published disorder_data.json.
# Re-queries NYC Open Data with DIFFERENT query shapes than build_data.py
# (whole-window totals, per-strand totals, distinct-address checks) and diffs
# against what the site actually serves. Prints PASS/FAIL for each claim.

import json, os, urllib.parse, urllib.request, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
BASE = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"

D = json.load(open(os.path.join(DATA, "disorder_data.json")))
POPS = json.load(open(os.path.join(DATA, "cd_populations.json")))

def q(params):
    url = BASE + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=180) as r:
        return json.load(r)

def one(params):
    return int(q(params)[0]["count"])

def inlist(types):
    return "complaint_type in (" + ", ".join("'" + t.replace("'", "''") + "'" for t in types) + ")"

results = []
def check(name, published, source, tol=0):
    ok = abs(published - source) <= tol
    results.append(ok)
    flag = "PASS" if ok else "*** FAIL ***"
    print(f"[{flag}] {name}: published={published:,} source={source:,} diff={published-source:+,}")

ALL_TYPES = [t for s in D["strands"] for t in s["types"]]

print("=" * 70)
print("1. Full-window total across all ten strands (hero number)")
src_total = one({"$select": "count(*)",
                 "$where": f"created_date >= '2021-01-01' and created_date < '2026-07-01' and " + inlist(ALL_TYPES)})
check("total_complaints", D["meta"]["total_complaints"], src_total)

print("\n2. Citywide last-12 count for EACH strand (independent per-strand query)")
for s in D["strands"]:
    src = one({"$select": "count(*)",
               "$where": f"created_date >= '2025-07-01' and created_date < '2026-07-01' and " + inlist(s["types"])})
    check(f"  {s['label']} n12", s["citywide"]["n12"], src)

print("\n3. Citywide prior-12 for two strands (trend denominator)")
for sid in ["rodents", "decay"]:
    s = next(x for x in D["strands"] if x["id"] == sid)
    src = one({"$select": "count(*)",
               "$where": f"created_date >= '2024-07-01' and created_date < '2025-07-01' and " + inlist(s["types"])})
    check(f"  {s['label']} prior12", s["citywide"]["prior12"], src)

print("\n4. Recompute a published percent change from its own parts")
for s in D["strands"]:
    c = s["citywide"]
    if c["prior12"]:
        recomp = round((c["n12"] - c["prior12"]) / c["prior12"] * 100, 1)
        check(f"  {s['label']} pct", c["pct"], recomp, tol=0.05)

print("\n5. Unassigned share (reports with no real community district)")
# Independent: count reports NOT in the 59 real boards. Query the complement
# by pulling per-board counts and summing the ones we drop.
rows = q({"$select": "community_board, count(*) as n",
          "$where": f"created_date >= '2021-01-01' and created_date < '2026-07-01' and " + inlist(ALL_TYPES),
          "$group": "community_board", "$limit": "1000"})
BORO = {"MANHATTAN":1,"BRONX":2,"BROOKLYN":3,"QUEENS":4,"STATEN ISLAND":5}
def valid(cb):
    p = cb.strip().split(" ",1)
    if len(p)!=2 or not p[0].isdigit(): return None
    boro=p[1].strip().upper()
    if boro not in BORO: return None
    return str(BORO[boro]*100+int(p[0]))
dropped = sum(int(r["n"]) for r in rows if valid(r.get("community_board","")) not in POPS["populations"])
total = sum(int(r["n"]) for r in rows)
src_share = round(dropped/total, 4)
check("dropped reports", int(round(D["meta"]["unassigned_share"]*D["meta"]["total_complaints"])), dropped, tol=2000)
print(f"       published share={D['meta']['unassigned_share']:.4f}  source share={src_share:.4f}")

print("\n6. Population denominators (2020 census P1_001N)")
print(f"       citywide-in-CDs published={D['meta']['citywide_population']:,}")
print(f"       (NYC 2020 census total is 8,804,190; parks/JIA tracts hold the remainder)")
check("citywide_population", D["meta"]["citywide_population"], POPS["citywide_in_cds"])

print("\n7. Concentration-flagged case: Elmhurst/South Corona (QN CD4) drugs")
s = next(x for x in D["strands"] if x["id"] == "drugs")
n = one({"$select": "count(*)",
         "$where": f"created_date >= '2025-07-01' and created_date < '2026-07-01' and community_board='04 QUEENS' and " + inlist(s["types"])})
check("  QN CD4 drugs n12", D["districts"]["404"]["strands"]["drugs"]["n12"], n)

print("\n8. A district rate recomputed from n12 and population")
for bcd, sid in [("306","noise"), ("101","dirty"), ("501","rodents")]:
    st = D["districts"][bcd]["strands"][sid]
    pop = D["districts"][bcd]["population"]
    recomp = round(st["n12"]/pop*1000, 2)
    check(f"  {bcd} {sid} rate", st["rate"], recomp, tol=0.01)

print("\n9. Noise:graffiti citywide ratio (methodology claim check)")
noise = next(x for x in D["strands"] if x["id"]=="noise")["citywide"]["n12"]
graf = next(x for x in D["strands"] if x["id"]=="graffiti")["citywide"]["n12"]
print(f"       noise={noise:,}  graffiti={graf:,}  ratio={noise/graf:.1f}x")

print("\n10. Conditions layer — rodent inspection citywide rate (independent)")
try:
    COND = json.load(open(os.path.join(DATA, "conditions_data.json")))
    ROD = "https://data.cityofnewyork.us/resource/p937-wjvj.json"
    def rq(params):
        url = ROD + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=180) as r:
            return int(json.load(r)[0]["count"])
    for label, start, end, key in [("last12", "2025-07-01", "2026-07-01", "value"),
                                   ("prior12", "2024-07-01", "2025-07-01", "prior")]:
        base = "inspection_type='Initial' and inspection_date >= '%s' and inspection_date < '%s'" % (start, end)
        tot = rq({"$select": "count(*)", "$where": base})
        hit = rq({"$select": "count(*)", "$where": base + " and starts_with(result,'Failed for Rat Activity')"})
        src_rate = round(hit / tot * 100, 1)
        pub = COND["strands"]["rodents"]["citywide"][key]
        check(f"  rodent inspection {label} rate", pub, src_rate, tol=0.1)
    print("       (note: source total includes null-coordinate rows; published citywide counts all geocoded rows)")

    print("\n11. Conditions layer — pavement citywide poor share sanity bounds")
    pv = COND["strands"]["decay"]["citywide"]
    ok = 0 <= pv["value"] <= 100 and 1 <= pv["avg_rating"] <= 10
    results.append(ok)
    print(f"[{'PASS' if ok else '*** FAIL ***'}] pavement poor%={pv['value']} avg={pv['avg_rating']}/10 within valid ranges")
except FileNotFoundError:
    print("       conditions_data.json not present — skipping (run build_conditions.py)")

print("\n" + "=" * 70)
print(f"RESULT: {sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
