#!/usr/bin/env python3
# Title: Resident quotes -> community districts
# Author: Generated with Claude Code for Vital City
# Date: 2026-07-02
# Data source: Resident interview quotes compiled by Vital City (Quality of
#   life.pdf), interviews dated Jan-Jul 2026. Provided directly, not public.
# Description: Parses the quote sheet, maps each neighborhood to its primary
#   community district, tags each quote by the disorder strand(s) it names,
#   and writes data/quotes_data.json. Only quotes that touch a disorder strand
#   this index tracks are kept; purely crime/gun-violence quotes are set aside
#   (the index is explicitly not a crime tracker). Every kept quote keeps its
#   verbatim text, attribution and interview date.
# Dependencies: Python 3.9+, pypdf.

import json
import os
import re
from datetime import datetime

from pypdf import PdfReader

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
PDF = "/Users/joshgreenman/Downloads/Quality of life.pdf"

# Neighborhood -> primary community district (boro_cd). Built against the
# canonical DCP community-district names. Neighborhoods that straddle two
# districts are assigned to their primary one; this is noted on the site.
NBHD_CD = {
    # Manhattan
    "Chelsea": "104", "East Harlem": "111", "East Village": "103",
    "Financial District": "101", "Gramercy": "106", "Hamilton Heights": "109",
    "Harlem": "110", "Inwood": "112", "Lower East Side": "103",
    "Midtown East": "106", "Midtown West": "104", "Murray Hill": "106",
    "Tribeca": "101", "Upper East Side": "108", "Upper West Side": "107",
    "Washington Heights": "112", "West Village": "102",
    # Brooklyn
    "Bay Ridge": "310", "Bedford-Stuyvesant": "303", "Borough Park": "312",
    "Brighton Beach": "313", "Brooklyn Heights": "302", "Brownsville": "316",
    "Bushwick": "304", "Canarsie": "318", "Coney Island": "313",
    "Crown Heights": "308", "East Flatbush": "317", "East New York": "305",
    "Flatbush": "309", "Fort Greene": "302", "Gravesend": "315",
    "Kensington": "312", "Park Slope": "306", "Prospect Heights": "308",
    "Sunset Park": "307", "Williamsburg": "301",
    # Queens
    "Arverne": "414", "Astoria": "401", "Bayside": "411",
    "Cambria Heights": "413", "Corona": "404", "East Elmhurst": "403",
    "Far Rockaway": "414", "Flushing": "407", "Forest Hills": "406",
    "Fresh Meadows": "408", "Glen Oaks": "413", "Hollis": "412",
    "Jamaica": "412", "Kew Gardens Hills": "408", "Long Island City": "401",
    "Middle Village": "405", "Ozone Park": "410", "Rego Park": "406",
    "Richmond Hill": "409", "South Ozone Park": "410",
    "South Richmond Hill": "409", "Springfield Gardens": "413",
    "St. Albans": "412", "Woodside": "402",
    # Staten Island
    "Great Kills": "503", "Mariner's Harbor": "501", "Port Richmond": "501",
    "Rosebank": "501", "Stapleton": "501", "West Brighton": "501",
    "Willowbrook": "502",
}

# Disorder strands (matches build_data.py ids) -> keywords that mark a quote as
# touching that strand. Word-ish matching, case-insensitive.
STRAND_KEYWORDS = {
    "homelessness": [r"homeless", r"encampment", r"sleeping (?:in|on)", r"living on the street", r"people on the street"],
    "rodents": [r"\brat\b", r"\brats\b", r"rodent", r"roach"],
    "dirty": [r"dirty", r"filth", r"garbage", r"trash", r"litter", r"grimy", r"grime", r"cleaner (?:street|area|park|subway)", r"streets? (?:are|is)? ?not clean", r"clean(?:er)? street"],
    "drugs": [r"\bdrug", r"overdose", r"addict", r"drinking in public", r"excessive drinking"],
    "public": [r"urinat", r"using the bathroom", r"bathroom (?:on|just on) the street", r"public bathroom"],
    "noise": [r"\bnoise\b", r"\bloud\b", r"blasting"],
    "panhandling": [r"begging", r"panhandl", r"asking for (?:change|money)"],
}
STRAND_LABEL = {"homelessness": "Street homelessness", "rodents": "Rats", "dirty": "Dirty streets",
                "drugs": "Drugs & alcohol", "public": "Public urination", "noise": "Noise",
                "panhandling": "Panhandling"}


def tag(text):
    t = text.lower()
    return [sid for sid, pats in STRAND_KEYWORDS.items() if any(re.search(p, t) for p in pats)]


def main():
    raw = "\n".join((p.extract_text() or "") for p in PdfReader(PDF).pages)
    # normalize curly quotes/dashes to make parsing predictable
    norm = (raw.replace("“", '"').replace("”", '"')
               .replace("—", "|").replace("–", "|").replace("’", "'"))

    header_re = re.compile(r"^([A-Za-z .'\-]+?)\((Manhattan|Brooklyn|Queens|Bronx|Staten Island)\)\s*$", re.M)
    headers = list(header_re.finditer(norm))

    quote_re = re.compile(r'"(.+?)"\s*\|\s*(.*?)Interviewed:\s*([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})', re.S)

    by_cd = {}
    total_quotes = kept = dropped_nbhd = crime_only = 0
    unmapped = set()
    for i, h in enumerate(headers):
        nbhd = h.group(1).strip()
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(norm)
        block = norm[start:end]
        cd = NBHD_CD.get(nbhd)
        if cd is None:
            unmapped.add(f"{nbhd} ({h.group(2)})")
        for m in quote_re.finditer(block):
            total_quotes += 1
            fix = lambda s: re.sub(r"(\d+)-\s*year-\s*old", r"\1-year-old", re.sub(r"\s+", " ", s)).strip()
            text = fix(m.group(1))
            who = fix(m.group(2)).rstrip(",").strip()
            date_str = m.group(3)
            iso = datetime.strptime(date_str, "%b %d, %Y").strftime("%Y-%m-%d")
            tags = tag(text)
            if not tags:
                crime_only += 1
                continue
            if cd is None:
                dropped_nbhd += 1
                continue
            kept += 1
            by_cd.setdefault(cd, {"neighborhoods": set(), "quotes": []})
            by_cd[cd]["neighborhoods"].add(nbhd)
            by_cd[cd]["quotes"].append({"text": text, "who": who, "date": date_str,
                                        "iso": iso, "tags": tags, "neighborhood": nbhd})

    # sort each district's quotes newest first
    out = {}
    for cd, d in by_cd.items():
        d["quotes"].sort(key=lambda q: q["iso"], reverse=True)
        out[cd] = {"neighborhoods": sorted(d["neighborhoods"]), "quotes": d["quotes"]}

    dates = [q["iso"] for d in out.values() for q in d["quotes"]]
    meta = {
        "generated": "2026-07-02",
        "source": "Resident interviews compiled by Vital City, provided directly (not public)",
        "kept": kept, "districts_with_quotes": len(out),
        "date_range": [min(dates), max(dates)] if dates else None,
        "note": "Quotes are matched to a resident's neighborhood and shown on its primary community district. Only quotes touching a tracked disorder strand are shown; purely crime/violence quotes are not.",
    }
    json.dump({"meta": meta, "strand_label": STRAND_LABEL, "districts": out},
              open(os.path.join(DATA, "quotes_data.json"), "w"), ensure_ascii=False, separators=(",", ":"))

    print(f"parsed {total_quotes} quotes across {len(headers)} neighborhoods")
    print(f"  kept (disorder-relevant): {kept} in {len(out)} districts, {meta['date_range']}")
    print(f"  set aside (crime/violence only, no disorder theme): {crime_only}")
    print(f"  disorder-relevant but neighborhood unmapped: {dropped_nbhd}")
    if unmapped:
        print(f"  UNMAPPED NEIGHBORHOODS: {sorted(unmapped)}")
    # strand distribution
    from collections import Counter
    c = Counter(t for d in out.values() for q in d["quotes"] for t in q["tags"])
    print("  by strand:", {STRAND_LABEL[k]: v for k, v in c.most_common()})


if __name__ == "__main__":
    main()
