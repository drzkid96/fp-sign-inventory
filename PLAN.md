# LA COUNTY STREET INVENTORY: PLAN

One county map of traffic signs, striping, pavement markings and curb, built first from what already exists, then kept current with street-level photos. Plan sheets and tables come out of it for any corridor. Car capture is only for projects.

## GOAL

- **Base (pass 1):** the best county-wide inventory that existing records and existing photos allow, every feature with its source, date and confidence.
- **Projects (pass 2):** project corridors captured by car with a 360 camera, which verify, update and add to the base where the project needs it.
- **Outputs:** the county map (this site), 1" = 30' plan sheets, Excel tables, the OSM intersection check.

## BUILD ORDER (WHERE)

The county is split into 1 km tiles, ranked by where the street inventory is densest. Every step below runs in this order.

- **Score** = weighted street km x (0.3 + 0.7 x urban share) x (0.4 + 0.6 x activity).
  - Street km from Census TIGER streets, plus OpenStreetMap arterials on top (primary and secondary +2, tertiary +1).
  - Urban share from the 2020 Census urban areas.
  - Activity = jobs + resident workers per sq km (LEHD LODES 2022), log scaled.
- **Priority P1 to P5:** each holds a fifth of the weighted street length. P1 is the dense core (about 600 tiles), P5 the outer edge.
- Arterials before local streets inside each tile. A project corridor can be moved to the front at any time.
- Code: `pipeline/base_tiles.py`, output `data/base/tiles.geojson`.

## SOURCES (WHAT)

| Source | Holds | Use |
|---|---|---|
| LA County Public Works asset layers | Signs (CA MUTCD codes), striping, markings, signals, with install and maintenance dates | Base records, unincorporated county. Also the accuracy benchmark. |
| City open data (88 cities) | Varies by city | Base records where published; inventoried city by city in build order |
| LADOT | Sign work orders, parking calendar signs, metered parking, Code the Curb (DTLA curb) | Base records and curb, City of LA |
| Caltrans | State routes | Base records on state highways |
| OpenStreetMap | Street network, lanes, turn lanes, crossings, stop and signal control | Network, context for sign reading, intersection check |
| Mapillary detections | 1,500 sign classes, 42 point classes incl. lane markings, where photos exist | Candidates and cross-check; mapped to CA MUTCD |
| Mapillary and KartaView photos | Street-level imagery, mostly 2017 to 2019 here | Our sign model reads and codes signs; dates every record (last seen) |
| Aerials | Curb lines, marking positions | Only from a source that allows tracing (LARIAC access to confirm) |
| F&P plans | Signing and striping plans | Ground truth for scoring; project base |

Not used: Google Street View imagery for extraction (its terms forbid creating data from it). It is a link-out on every feature for checking by eye.

## RECORD (ONE FORMAT FOR EVERY FEATURE)

`id, layer (sign, stripe, marking, curb, signal), code (CA MUTCD or marking type), value (speed, legend text, arrow), street, side, station along street, lat/lon, facing, source, source id, source date, last seen in photos, confidence, review status, conflict note`.

## MERGE RULES

1. Agency record first; photo-read features match to it within 15 m by code family and facing.
2. Matched: the record gets a last-seen date and the photo crop.
3. Agency record never seen in photos taken after its date: flagged "not seen", not removed.
4. Photo-read feature with no record: added as "photo only", with confidence.
5. Disagreeing code: both kept, flagged "conflict" for review.

## PHASES

| Phase | Work | Output |
|---|---|---|
| 0. Pre-build | Data inventory by jurisdiction in build order; record format; Mapillary rate limits and runner timing on one P1 tile; accuracy against the county inventory; aerial license | Coverage matrix and a go/no-go page |
| 1. Presentation map | This site: build order tiles, agency layers, photo coverage by year, Mapillary and FP sign layers, Street View link-out | Live now |
| 2. Base merge, P1 | Agency layers + OSM + Mapillary detections + our sign model on existing photos, merged by the rules above, tile by tile | P1 tiles complete with sources and dates |
| 3. Base, P2 to P5 | Same, nightly in the cloud, in build order | County base |
| 4. Markings and curb | Marking detector and curb attributes from photos; geometry from an aerial source that allows tracing | Marking and curb layers |
| 5. Projects | Car capture on project corridors (GoPro MAX 2, 8K 360 video), upload to Mapillary, rerun the corridor | Current-condition corridor inventory and plan sheets |

## CHECKS (AUTOMATIC)

- Accuracy per model change, scored against the county inventory and F&P plans: codes correct, signs found, position error.
- Every plan sheet: text overlap, clipping, crossing leaders, pole under callout; a failing sheet is flagged.
- Coverage per tile: share of street length with records, with photos, and photo age.

## RUNNING

- Everything runs in GitHub Actions on the public repo at no cost; no AI service runs in the pipeline.
- `County base` workflow: priority tiles and agency layers (`requests/base.json` or run by hand).
- `inventory` workflow: a corridor or area inventory with plan sheets (`requests/<area>.json`).
- Storage: points and lines as map tiles in the repo; photo crops load from Mapillary on click.
