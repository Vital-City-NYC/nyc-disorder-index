# The disorder index

Ten strands of everyday street disorder — noise, street homelessness, rats, dirty streets, illegal dumping, graffiti, abandoned vehicles, public drug and alcohol use, panhandling and streets in disrepair — tracked across New York City's 59 community districts from 311 reports, January 2021 through June 2026.

Built for Vital City. Story-first design per the July 2, 2026 team call: strands lead, data sources are the fine print, no single composite score. For each district and strand the page reports direction (past 12 months vs the prior 12), standing versus the rest of the city (reports per 1,000 residents, in thirds) and the full monthly trend, with a flag wherever a small number of addresses drives the numbers.

## Run locally

```
python3 -m http.server 8737 --directory /Users/joshgreenman/Experiments/nyc-disorder-index
```

Then open http://localhost:8737 (port registered in `.claude/launch.json` as `nyc-disorder-index`).

## Refresh the data (monthly)

```
cd nyc-disorder-index
python3 scripts/build_data.py          # ~1 minute; three aggregate queries against NYC Open Data
```

`scripts/build_populations.py` only needs re-running if the census denominators or district geography change (requires `CENSUS_API_KEY` in the environment; free key, do not commit it). After a refresh, update the window constants at the top of `build_data.py` (`LAST12_START`, `PRIOR12_START`, `END`) so the 12-month comparisons roll forward.

## Files

- `index.html`, `styles.css`, `app.js` — the site (static, no build step)
- `methodology.html` — full public methodology: sources, strand definitions, formulas, exclusions, limitations
- `scripts/build_data.py` — 311 aggregation pipeline → `data/disorder_data.json`
- `scripts/build_populations.py` — 2020 census tract populations → community districts
- `scripts/verify.py` — independent re-query of NYC Open Data that diffs every published number against the source (run `python3 scripts/verify.py`; prints PASS/FAIL per claim)
- `data/community_districts.geojson` — Department of City Planning boundaries, shoreline-clipped
- `data/cd_names.json` — district display names

## Sources

- 311 Service Requests from 2010 to Present (NYC Open Data, `erm2-nwe9`), accessed July 2, 2026
- 2020 decennial census (P1 total population by tract) via api.census.gov
- Department of City Planning tract → community district tabulation area relationship file and district boundaries

## Verification notes

`scripts/verify.py` independently re-queries NYC Open Data with different query shapes than the pipeline and diffs the result against every published figure. As of the July 2, 2026 build, all 29 checks pass: the full-window total (6,455,356), each strand's citywide 12-month count, trend denominators, every published percent change recomputed from its parts, the unassigned share (2.6%), the population denominator (8,803,186 of the city's 8,804,190 residents), a concentration-flagged case, and several district rates. The concentration flag independently surfaces the known Corona artifact (Queens CD 4 drug complaints driven by a handful of addresses) that was discussed on the team call.

Not yet deployed. Not yet editor-reviewed.
