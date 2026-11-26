# FP Sign Inventory

Live site: https://drzkid96.github.io/fp-sign-inventory/

Street signs on an aerial map, each shown with its standard sign code and a small picture of the sign face, plus a sign inventory. Exports an 11x17 PDF sheet and an Excel workbook in F&P format. Static site on GitHub Pages: no server and no paid services.

## Use
1. **Area:** open the verified test area (Huntington Dr S, El Sereno), frame any area and use the map view, or draw a box (up to about 6 sq km).
2. **Load:** signs load from street-level imagery sign tiles in a few seconds, with a progress bar.
3. **Inventory:** one row per code. Click a row to zoom to those signs; click a sign for its photo, legend, status and links to the photo and Street View.
4. **Export:** PDF 11X17 (print to PDF) or EXCEL (SUMMARY and SIGNS tabs).

Link to the test area directly: `?area=hds`.

## Sign status
| Status | Meaning |
|---|---|
| VERIFIED | Read from photos by two independent model reads, every disagreement decided by a third, stronger review, and checked against the standard sign face |
| AUTO | Code from the detected sign class through a checked class table; not individually read |
| NO CODE | A sign with no standard code (custom or local text) |
| UNREADABLE | Photos too blurry, or only the back of the sign is visible |

## Files
| Path | Contents |
|---|---|
| `js/app.js` | Map, sign tiles, matching, grouping, print sheet, Excel export |
| `js/config.js` | Imagery API client token, test area, data version |
| `data/library.json` | Standard sign codes and names (CA MUTCD 2026) |
| `data/sprites/` | Small sign face pictures, one per code |
| `data/classmap.json` | Detected sign class to code table (`src` notes how each entry was checked) |
| `data/verified/` | Verified area files and sign photo crops |

Sources: sign positions and photos, Mapillary (CC BY-SA); aerial, Esri World Imagery.
