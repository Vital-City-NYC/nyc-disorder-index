#!/usr/bin/env python3
# Title: Community district populations from the 2020 census
# Author: Generated with Claude Code for Vital City
# Date: 2026-07-02
# Data sources:
#   - U.S. Census Bureau 2020 decennial census (PL 94-171), table P1_001N by
#     census tract, via api.census.gov. Accessed 2026-07-02.
#   - NYC Department of City Planning 2020 census tract -> NTA -> CDTA
#     relationship file (nyc2020census_tract_nta_cdta_relationships.xlsx,
#     r=092221). Accessed 2026-07-02.
# Description: Sums 2020 total population of census tracts into community
#   district tabulation areas (CDTAs), City Planning's tract-built
#   approximation of the 59 community districts, and writes
#   data/cd_populations.json keyed by boro_cd (e.g. "101" = Manhattan CD 1).
# Dependencies: Python 3.9+, pandas, openpyxl. Requires CENSUS_API_KEY env var.

import json
import os
import sys
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

KEY = os.environ.get("CENSUS_API_KEY")
if not KEY:
    sys.exit("Set CENSUS_API_KEY (free key; do not commit it).")

# County FIPS for the five boroughs; BoroCode used in boro_cd prefixes.
COUNTIES = {"061": 1, "005": 2, "047": 3, "081": 4, "085": 5}
BORO_PREFIX = {"MN": 1, "BX": 2, "BK": 3, "QN": 4, "SI": 5}

# 1. Tract -> CDTA crosswalk (only real community districts, CDTAType == 'CD';
#    excludes joint interest areas like parks).
rel = pd.read_excel(os.path.join(DATA, "tract_cdta_rel.xlsx"), sheet_name="NYC_CT2020_Relate", dtype={"GEOID": str})
rel = rel[rel["CDTAType"] == "CD"]
tract_to_cdta = dict(zip(rel["GEOID"], rel["CDTACode"]))
print(f"{len(rel)} tracts mapped to {rel['CDTACode'].nunique()} CDTAs")

# 2. 2020 census total population (P1_001N) for every tract in each borough.
pop_by_cdta = {}
unmatched = 0
for county in COUNTIES:
    url = (f"https://api.census.gov/data/2020/dec/pl?get=P1_001N"
           f"&for=tract:*&in=state:36%20county:{county}&key={KEY}")
    with urllib.request.urlopen(url) as r:
        rows = json.load(r)
    for pop, state, cty, tract in rows[1:]:
        geoid = f"{state}{cty}{tract}"
        cdta = tract_to_cdta.get(geoid)
        if cdta is None:
            unmatched += int(pop)  # tracts in parks/JIAs, not in a CD
            continue
        pop_by_cdta[cdta] = pop_by_cdta.get(cdta, 0) + int(pop)
print(f"population not assigned to a CD (parks/JIA tracts): {unmatched}")

# 3. CDTA code (e.g. MN01) -> boro_cd (e.g. 101), the join key used everywhere.
out = {}
for cdta, pop in sorted(pop_by_cdta.items()):
    boro_cd = str(BORO_PREFIX[cdta[:2]] * 100 + int(cdta[2:]))
    out[boro_cd] = pop

assert len(out) == 59, f"expected 59 districts, got {len(out)}"
citywide = sum(out.values())
print(f"59 districts, citywide total assigned to CDs: {citywide:,}")

with open(os.path.join(DATA, "cd_populations.json"), "w") as f:
    json.dump({"source": "2020 decennial census P1_001N by tract, summed to CDTAs (DCP tract-CDTA relationship file)",
               "accessed": "2026-07-02", "citywide_in_cds": citywide,
               "populations": out}, f, indent=1)
print("wrote data/cd_populations.json")
