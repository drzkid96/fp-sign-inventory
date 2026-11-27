"""County priority tiles: 1 km grid over Los Angeles County, ranked by street density and urban coverage.

Inputs (US Census TIGER/Line 2025, public domain): county roads, county boundary, 2020 urban areas, places.
Output: data/base/tiles.geojson (WGS84), one feature per tile that has streets.

score = weighted street km x (0.3 + 0.7 x urban share) x (0.4 + 0.6 x activity)
  street km: TIGER streets (S1400 local, S1200 secondary, S1100 primary) at 1, plus OSM arterials on top
  (primary and secondary +2, tertiary +1) when osm_art.json is present; alleys, ramps, service, trails left out.
  activity: jobs + resident workers per sq km (LEHD LODES 2022, census blocks), log scaled to 0-1 at 50,000.
Priority 1-5: tiles in score order, split where the running total of weighted street km passes 20/40/60/80 percent.
Usage: python3 pipeline/base_tiles.py <folder with the TIGER zips> <repo>
"""
import sys, json, os
import numpy as np, geopandas as gpd
from shapely.geometry import box

src, repo = sys.argv[1], sys.argv[2]
CRS = 3310  # California Albers, meters
cty = gpd.read_file(f'{src}/tl_2025_us_county.zip', where="GEOID='06037'").to_crs(CRS)
roads = gpd.read_file(f'{src}/tl_2025_06037_roads.zip').to_crs(CRS)
W = {'S1200': 1.0, 'S1400': 1.0, 'S1100': 1.0}
roads = roads[roads.MTFCC.isin(W)].copy(); roads['w'] = roads.MTFCC.map(W)
ua = gpd.read_file(f'{src}/tl_2025_us_uac20.zip', bbox=tuple(cty.to_crs(4269).total_bounds)).to_crs(CRS)
pl = gpd.read_file(f'{src}/tl_2025_06_place.zip').to_crs(CRS)
pl = pl[pl.CLASSFP.isin(['C1'])]   # incorporated cities

x0, y0, x1, y1 = cty.total_bounds; S = 1000
cells = [box(x, y, x + S, y + S) for x in np.arange(x0 - x0 % S, x1, S) for y in np.arange(y0 - y0 % S, y1, S)]
g = gpd.GeoDataFrame(geometry=cells, crs=CRS)
g = g[g.intersects(cty.geometry.iloc[0])].reset_index(drop=True); g['tid'] = g.index

# weighted and plain street km per tile
seg = gpd.overlay(roads[['MTFCC', 'w', 'geometry']], g[['tid', 'geometry']], how='intersection', keep_geom_type=True)
seg['km'] = seg.length / 1000
k = seg.groupby('tid').apply(lambda d: (d.km * d.w).sum()).rename('wkm')
art = seg[seg.MTFCC == 'S1200'].groupby('tid').km.sum().rename('art_km')
loc = seg[seg.MTFCC == 'S1400'].groupby('tid').km.sum().rename('local_km')
fwy = seg[seg.MTFCC == 'S1100'].groupby('tid').km.sum().rename('hwy_km')
g = g.join(k, on='tid').join(art, on='tid').join(loc, on='tid').join(fwy, on='tid').fillna(0)
g = g[g.wkm > 0].copy()

# OSM arterials on top (TIGER classes do not mark most city arterials)
if os.path.exists(f'{src}/osm_art.json'):
    from shapely.geometry import LineString
    E = json.load(open(f'{src}/osm_art.json'))['elements']
    AW = {'primary': 2, 'secondary': 2, 'tertiary': 1, 'trunk': 0}
    rows = [(AW.get(e['tags']['highway'].replace('_link', ''), 0), LineString([(p['lon'], p['lat']) for p in e['geometry']])) for e in E if len(e.get('geometry', [])) > 1]
    o = gpd.GeoDataFrame({'w': [r[0] for r in rows]}, geometry=[r[1] for r in rows], crs=4326).to_crs(CRS)
    o = o[o.w > 0].drop_duplicates(subset='geometry')
    os_ = gpd.overlay(o, g[['tid', 'geometry']], how='intersection', keep_geom_type=True); os_['km'] = os_.length / 1000
    g = g.join(os_.groupby('tid').apply(lambda d: (d.km * d.w).sum()).rename('oart'), on='tid').fillna({'oart': 0})
    g['art_km'] = g.tid.map(os_[os_.w == 2].groupby('tid').km.sum()).fillna(0)
    g['wkm'] = g.wkm + g.oart

# activity: jobs (WAC) + resident workers (RAC) per block, placed at block centroids
import pandas as pd
xw = pd.read_csv(f'{src}/ca_xwalk.csv.gz', usecols=['tabblk2020', 'cty', 'blklatdd', 'blklondd'], dtype={'tabblk2020': str})
xw = xw[xw.cty == 6037]
wac = pd.read_csv(f'{src}/ca_wac_S000_JT00_2022.csv.gz', usecols=['w_geocode', 'C000'], dtype={'w_geocode': str})
rac = pd.read_csv(f'{src}/ca_rac_S000_JT00_2022.csv.gz', usecols=['h_geocode', 'C000'], dtype={'h_geocode': str})
xw = xw.merge(wac.rename(columns={'w_geocode': 'tabblk2020', 'C000': 'jobs'}), how='left').merge(rac.rename(columns={'h_geocode': 'tabblk2020', 'C000': 'res'}), how='left').fillna(0)
pts = gpd.GeoDataFrame(xw, geometry=gpd.points_from_xy(xw.blklondd, xw.blklatdd), crs=4326).to_crs(CRS)
j = gpd.sjoin(pts[['jobs', 'res', 'geometry']], g[['tid', 'geometry']], predicate='within')
act = j.groupby('tid')[['jobs', 'res']].sum()
g = g.join(act, on='tid').fillna({'jobs': 0, 'res': 0})
g['act'] = (np.log10(1 + g.jobs + g.res) / np.log10(1 + 50000)).clip(0, 1)

# urban share and city (largest overlap; unincorporated otherwise)
u = gpd.overlay(g[['tid', 'geometry']], ua[['geometry']], how='intersection'); u['a'] = u.area
g = g.join(u.groupby('tid').a.sum().rename('ua'), on='tid').fillna({'ua': 0})
g['urban'] = (g.ua / (S * S)).clip(0, 1)
c = gpd.overlay(g[['tid', 'geometry']], pl[['NAME', 'geometry']], how='intersection'); c['a'] = c.area
city = c.sort_values('a').groupby('tid').tail(1).set_index('tid').NAME
g['city'] = g.tid.map(city).fillna('Unincorporated')

g['score'] = g.wkm * (0.3 + 0.7 * g.urban) * (0.4 + 0.6 * g.act)
g = g.sort_values('score', ascending=False).reset_index(drop=True)
g['rank'] = g.index + 1
cum = g.wkm.cumsum() / g.wkm.sum()
g['priority'] = np.searchsorted([0.2, 0.4, 0.6, 0.8], cum.values, side='left') + 1
out = g.to_crs(4326)
os.makedirs(f'{repo}/data/base', exist_ok=True)
feats = []
for r in out.itertuples():
    feats.append({'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[[round(x, 5), round(y, 5)] for x, y in r.geometry.exterior.coords]]},
                  'properties': {'id': int(r.tid), 'rank': int(r.rank), 'p': int(r.priority), 'city': r.city, 'score': round(r.score, 1),
                                 'art': round(r.art_km, 2), 'loc': round(r.local_km, 2), 'hwy': round(r.hwy_km, 2), 'urban': round(r.urban, 2), 'jobs': int(r.jobs), 'res': int(r.res)}})
json.dump({'type': 'FeatureCollection', 'features': feats}, open(f'{repo}/data/base/tiles.geojson', 'w'), separators=(',', ':'))
s = g.groupby('priority').agg(tiles=('tid', 'size'), street_km=('wkm', 'size'))
print(len(g), 'tiles'); print(g.groupby('priority').agg(tiles=('tid', 'size'), art_km=('art_km', 'sum'), local_km=('local_km', 'sum')).round(0))
print(g.head(15)[['rank', 'city', 'score', 'art_km', 'local_km', 'jobs', 'res']])
