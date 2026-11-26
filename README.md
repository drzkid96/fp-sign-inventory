# FP Sign Inventory

Live site: https://drzkid96.github.io/fp-sign-inventory/

Existing street signs found in street-level photos, placed on an aerial map with each sign's standard code and a small picture of the sign face, plus 11x17 plan sheets and an Excel inventory in F&P format. Everything runs on GitHub: GitHub Pages for the site, GitHub Actions for the inventory. Nothing calls a language model; every step is code and a small trained sign model that gives the same answer every run.

## Run an area
Add a file to `requests/`, for example `requests/hds.json`:

```json
{"name": "HUNTINGTON DR, EL SERENO, LOS ANGELES", "bbox": [-118.1945, 34.0780, -118.1770, 34.0875], "corridor": "Huntington Dr"}
```

Pushing the file starts the `inventory` Action (or run it from the Actions tab with the area key). It writes `data/areas/<key>/`: `signs.json`, a photo crop per sign and the plan sheet PDF. The site shows the area at `?area=<key>`.

## How it works
1. **Photos:** every street-level photo in the area (Mapillary), 360° panoramas and older dash-cam photos.
2. **Sign boxes:** the box drawn around each sign in each photo; backs of signs and advertising are dropped.
3. **Codes:** each sign view is read by `pipeline/model/signnet.onnx`, an image model fine-tuned on hand-checked views of signs in El Sereno plus synthetic views made from the standard sign faces.
4. **Placement:** views of the same code from different photos are matched by crossing their sight lines, so each pole gets its own position and signs stacked on one pole stay separate. The same sign seen in several photo years is merged.
5. **Approach:** each sign is tied to its street, the direction of travel it serves (from the way it faces) and the next cross street, from OpenStreetMap.
6. **Sheets:** 11x17 at 1" = 40', rotated along the corridor, with a callout and a sign picture at every pole, a sign table, a key map and every street that has no photos marked.

## Accuracy (held-out signs the model never saw)
| | Share of signs | Correct |
|---|---|---|
| All signs | 100% | about 89% |
| High confidence (shown green) | about 83% | about 96% |
| Check in field (shown orange) | about 17% | lower; confirm in the field |

The limit is photo coverage, not reading: a street with no photos cannot be inventoried, and the sheets mark those streets.

## Files
| Path | Contents |
|---|---|
| `pipeline/run.py` | The full inventory for one area |
| `pipeline/build_sheets.py`, `pipeline/sheets_geo.py` | Plan sheets |
| `pipeline/model/` | Trained sign model (ONNX), its classes and the training labels |
| `requests/` | One file per area |
| `data/areas/` | Results per area |
| `js/app.js` | Map, inventory table, print sheet, Excel export |
| `data/library.json`, `data/sprites/` | Standard sign codes, names and sign face pictures (CA MUTCD 2026) |

Sources: street-level photos, Mapillary (CC BY-SA); aerial, Esri World Imagery; streets, OpenStreetMap (ODbL).
