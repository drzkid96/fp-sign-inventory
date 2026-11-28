# LA COUNTY STREET INVENTORY: HOW TO WORK IN THIS REPO

One map platform for LA County street data: signs (the inventory), plus data layers (volumes, 85th percentile speeds, walk and bike counts, parking). Site: https://drzkid96.github.io/fp-sign-inventory/ (GitHub Pages, static).

## LAYOUT
- `index.html`, `js/map.js` (signs: three sources merged on screen), `js/layers.js` (every data layer, built from the registry), `css/map.css`.
- `data.html`: sources, dates, record counts and downloads for every layer.
- `data/layers.json`: the registry. One entry per layer: source, fetch, field map, date rule, style, card. The map and catalog read it; no front-end code per layer.
- `pipeline/layers.py`: builds layers. `pipeline/sources/hooks.py`: steps a field map can't do. `pipeline/sources/speed_pdf.py`: 85th percentile tables from E&TS PDFs. `pipeline/geo/streets.py`: "street between A and B" to a line, from Census TIGER roads.
- `.github/workflows/layers.yml`: nightly build; tiles and summaries to `data/layers/`, downloads to the `data-latest` release.
- Sign inventory pipeline: `pipeline/run.py`, `base_tiles.py`, `fetch_agency.py`, `trust.py`; workflows `inventory.yml`, `base.yml`. See PLAN.md.

## RULES
- Date limit 2021-01-01 (`since` in the registry). Observed data (counts, surveys, photos) is dropped when older or undated. Inventories are kept when the agency's last update is 2021 or later.
- Volumes: AADT only where the source publishes AADT (Caltrans); everything else is ADT, labeled as such. Weekday or weekend only where the count date or source says so.
- Speeds: 85th percentile only. No posted-limit layers.
- Never use Google Street View imagery as a data source (link-out only).
- Every record keeps its source, source id and date. Nothing is invented: unmatched records are listed in the layer summary, not placed by guess.
- Brand: F&P (Albert Sans, F&P colors). Table cells vertically centered.

## ADDING A LAYER
1. Find the source and read its fields and last update date.
2. Add an entry to `data/layers.json` (copy the closest existing entry). ArcGIS and Socrata need no code; anything else gets a hook named after the layer id.
3. Run locally: `OUT=/tmp/lo TIGER_DIR=/tmp/in python3 pipeline/layers.py <id>` (TIGER zips: tl_2025_06037_roads.zip, tl_2025_06_place.zip). Check `data/layers/<id>.json`: count, dropped, years.
4. Delete local `data/layers/` output, commit the registry change; the workflow builds and publishes. Check the site and `data.html`.
