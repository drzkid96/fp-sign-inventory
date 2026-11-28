"""Build every data layer listed in data/layers.json.

usage: python pipeline/layers.py [layer_id ...]        (no ids = all layers)
env:   TIGER_DIR (Census roads and places zips, for street-name matching), OUT (exports folder, default /tmp/layers-out)

For each layer: fetch (ArcGIS, Socrata or a hook in pipeline/sources/hooks.py) -> one record format -> date limit
-> geometry check -> map tiles (data/layers/<id>.pmtiles) -> summary (data/layers/<id>.json) -> exports
(GeoJSON, CSV, KMZ, GeoPackage, shapefile, DXF in CA State Plane Zone 5 ft) in OUT for the data release.
"""
import json, os, sys, time, datetime, zipfile, shutil, subprocess, traceback, re
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'pipeline'))
REG = json.load(open(os.path.join(ROOT, 'data/layers.json')))
SINCE = int(REG['since'][:4])
OUT = os.environ.get('OUT', '/tmp/layers-out')
TILES = os.path.join(ROOT, 'data/layers')
RELEASE = 'https://github.com/drzkid96/fp-sign-inventory/releases/download/data-latest/'
BBOX = (-119.0, 33.2, -117.5, 34.9)                     # LA County with margin
H = {'User-Agent': 'fp-sign-inventory data build (github.com/drzkid96/fp-sign-inventory)'}

def get(url, params=None, tries=4, post=False):
    for i in range(tries):
        try:
            r = (requests.post if post else requests.get)(url, params=None if post else params, data=params if post else None, headers=H, timeout=120)
            if r.status_code == 200: return r
            print(f'  {r.status_code} {url[:90]}')
        except Exception as e: print(f'  {type(e).__name__} {url[:90]}')
        time.sleep(3 * (i + 1))
    raise RuntimeError(f'failed: {url}')

# ---------- fetchers ----------
def esri_to_geojson(f, gtype):
    g = f.get('geometry') or {}
    if 'x' in g: geom = {'type': 'Point', 'coordinates': [g['x'], g['y']]}
    elif 'paths' in g: geom = {'type': 'MultiLineString', 'coordinates': g['paths']}
    elif 'rings' in g: geom = {'type': 'Polygon', 'coordinates': g['rings']}
    else: geom = None
    return {'type': 'Feature', 'geometry': geom, 'properties': f.get('attributes', {})}

def arcgis(spec):
    url = spec['url']; meta = get(url, {'f': 'json'}).json()
    if 'error' in meta: raise RuntimeError(meta['error'])
    ids = get(url + '/query', {'where': spec.get('where', '1=1'), 'returnIdsOnly': 'true', 'f': 'json'}).json().get('objectIds') or []
    oid = next((f['name'] for f in meta.get('fields', []) if f['type'] == 'esriFieldTypeOID'), 'OBJECTID')
    step = min(int(meta.get('maxRecordCount') or 1000), 1000); feats = []
    for i in range(0, len(ids), step):
        chunk = ','.join(map(str, sorted(ids)[i:i + step]))
        p = {'objectIds': chunk, 'outFields': '*', 'outSR': 4326, 'f': 'geojson', 'returnGeometry': 'true'}
        d = get(url + '/query', p, post=True).json()
        if 'features' not in d or d.get('error'):
            p['f'] = 'json'; d = get(url + '/query', p, post=True).json(); d['features'] = [esri_to_geojson(f, meta.get('geometryType')) for f in d.get('features', [])]
        feats += d['features']
    ed = (meta.get('editingInfo') or {}).get('lastEditDate')
    return feats, {'fields': [f['name'] for f in meta.get('fields', [])], 'oid': oid, 'last_edit': ed, 'name': meta.get('name')}

def socrata(spec):
    base = f"https://{spec['domain']}"; meta = get(f"{base}/api/views/{spec['id']}.json").json(); rows = []
    while True:
        d = get(f"{base}/resource/{spec['id']}.json", {'$limit': 50000, '$offset': len(rows), '$order': ':id'}).json()
        rows += d
        if len(d) < 50000: break
    return rows, {'fields': [c['fieldName'] for c in meta.get('columns', [])], 'last_edit': (meta.get('rowsUpdatedAt') or 0) * 1000, 'name': meta.get('name')}

# ---------- record format ----------
def iso(v, fmt=None):
    if v in (None, ''): return None
    if fmt == 'epoch_ms' or (isinstance(v, (int, float)) and v > 1e11): return datetime.datetime.fromtimestamp(v / 1000, datetime.UTC).strftime('%Y-%m-%d')
    s = str(v); m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m: return m.group(0)
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m: return f'{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}'
    m = re.search(r'(19|20)\d{2}', s); return m.group(0) if m else None

def k_label(v):
    try: v = float(v)
    except: return ''
    return f'{v / 1000:.0f}k' if v >= 10000 else (f'{v / 1000:.1f}k' if v >= 1000 else f'{v:.0f}')

def build(L):
    from sources import hooks
    t0 = time.time(); lid = L['id']; info = {}
    if L.get('fetch'):
        raw, info = {'arcgis': arcgis, 'socrata': socrata}[L['fetch']['type']](L['fetch'])
    else: raw = []
    hook = getattr(hooks, L['hook']) if L.get('hook') else None
    if L.get('map'):
        feats = [{'type': 'Feature', 'geometry': f.get('geometry'), 'properties': dict({k: (f.get('properties') or {}).get(v) for k, v in L['map'].items()}, _raw=f.get('properties') or {})} for f in raw]
    else: feats = raw
    if hook: feats = hook(L, feats, info)
    # dates
    ds = L.get('date', {}); edit = iso(info.get('last_edit'), 'epoch_ms') if info.get('last_edit') else None
    for f in feats:
        p = f['properties']; raw_p = p.pop('_raw', {}) or {}
        if 'date' not in p or p['date'] is None:
            if 'fixed' in ds: p['date'] = ds['fixed']
            elif 'field' in ds: p['date'] = iso(raw_p.get(ds['field'], p.get(ds['field'])), ds.get('fmt'))
            elif ds.get('edit'): p['date'] = edit
    if ds.get('layer_max') or L['kind'] == 'inventory':
        dates = [f['properties'].get('date') for f in feats if f['properties'].get('date')]
        as_of = max(dates + ([edit] if edit else [])) if (dates or edit) else None
        if ds.get('layer_max'):
            for f in feats: f['properties']['date'] = as_of
    else: as_of = None
    # checks
    drop = {'before_limit': 0, 'undated': 0, 'no_location': 0, 'outside_county': 0}; keep = []
    for n, f in enumerate(feats):
        p = f['properties']; g = f.get('geometry')
        y = int(str(p.get('date'))[:4]) if p.get('date') and str(p.get('date'))[:4].isdigit() else None
        p['year'] = y
        if L['kind'] == 'observed':
            if y is None: drop['undated'] += 1; continue
            if y < SINCE: drop['before_limit'] += 1; continue
        if not g or not g.get('coordinates'): drop['no_location'] += 1; continue
        c = first_xy(g['coordinates'])
        if not c or not (BBOX[0] < c[0] < BBOX[2] and BBOX[1] < c[1] < BBOX[3]): drop['outside_county'] += 1; continue
        p.setdefault('id', f'{lid}:{p.get("src_id", n)}'); p['layer'] = lid; p['src'] = L['source']['agency']
        for k in ('aadt', 'adt', 'total'):
            if p.get(k) is not None: p[k + '_k'] = k_label(p[k])
        keep.append({'type': 'Feature', 'geometry': g, 'properties': {k: v for k, v in p.items() if v not in (None, '') and not isinstance(v, (dict, list))}})
    summary = {'id': lid, 'title': L['title'], 'group': L['group'], 'geom': L['geom'], 'kind': L['kind'], 'count': len(keep), 'dropped': drop,
               'built': datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%MZ'), 'source': L['source'], 'source_fields': info.get('fields'), 'seconds': round(time.time() - t0)}
    if L['kind'] == 'inventory':
        summary['as_of'] = as_of
        if not as_of or int(as_of[:4]) < SINCE:
            summary['skipped'] = f'agency last update {as_of or "unknown"} is before {SINCE}'; keep = []
    years = {}
    for f in keep: years[f['properties'].get('year')] = years.get(f['properties'].get('year'), 0) + 1
    summary['years'] = {str(k): v for k, v in sorted(years.items(), key=lambda x: str(x[0]))}
    if hasattr(hooks, lid + '_notes'): summary.update(getattr(hooks, lid + '_notes')())
    return keep, summary

def first_xy(c):
    while isinstance(c, list) and c and isinstance(c[0], list): c = c[0]
    return c if isinstance(c, list) and len(c) >= 2 else None

# ---------- outputs ----------
def tiles(lid, fc_path, geom):
    out = os.path.join(TILES, lid + '.pmtiles')
    if not shutil.which('tippecanoe'): print('  tippecanoe not installed here; tiles skipped'); return False
    if os.path.exists(out): os.remove(out)
    args = ['tippecanoe', '-q', '-o', out, '--force', '-l', lid, '-Z6', '-z16', '--drop-densest-as-needed', '--extend-zooms-if-still-dropping']
    if geom == 'point': args += ['-r1', '--cluster-distance=2']
    else: args += ['--no-tiny-polygon-reduction', '--simplification=4']
    subprocess.run(args + [fc_path], check=True); return True

def exports(lid, fc, fc_path, all_layers=True):
    import geopandas as gpd
    os.makedirs(OUT, exist_ok=True); files = {}
    g = gpd.GeoDataFrame.from_features(fc['features'], crs=4326)
    shutil.copy(fc_path, os.path.join(OUT, lid + '.geojson')); files['GeoJSON'] = lid + '.geojson'
    c = g.copy()
    if (c.geom_type == 'Point').all(): c['lon'], c['lat'] = c.geometry.x.round(6), c.geometry.y.round(6)
    else: c['wkt'] = c.geometry.to_wkt()
    c.drop(columns='geometry').to_csv(os.path.join(OUT, lid + '.csv'), index=False); files['CSV'] = lid + '.csv'
    g.to_file(os.path.join(OUT, lid + '.gpkg'), driver='GPKG', layer=lid); files['GeoPackage'] = lid + '.gpkg'
    if all_layers: g.to_crs(2229).to_file(os.path.join(OUT, 'all-layers-2229.gpkg'), driver='GPKG', layer=lid)
    kml = os.path.join(OUT, lid + '.kml'); g.to_file(kml, driver='KML')
    with zipfile.ZipFile(os.path.join(OUT, lid + '.kmz'), 'w', zipfile.ZIP_DEFLATED) as z: z.write(kml, 'doc.kml')
    os.remove(kml); files['KMZ'] = lid + '.kmz'
    d = os.path.join('/tmp', 'shp_' + lid); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    import warnings
    fam = g.geom_type.str.replace('Multi', '')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for t, part in g.groupby(fam):                 # a shapefile holds one geometry type
            part.to_file(os.path.join(d, lid + ('' if fam.nunique() == 1 else '_' + t.lower()) + '.shp'))
    with zipfile.ZipFile(os.path.join(OUT, lid + '_shp.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for fn in os.listdir(d): z.write(os.path.join(d, fn), fn)
    files['Shapefile'] = lid + '_shp.zip'
    try:
        g[['geometry']].to_crs(2229).to_file(os.path.join(OUT, lid + '_2229.dxf'), driver='DXF'); files['DXF (CA SP 5, ft)'] = lid + '_2229.dxf'
    except Exception as e: print('  dxf skipped', e)
    return {k: RELEASE + v for k, v in files.items()}

def main(ids):
    os.makedirs(TILES, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    allgpkg = os.path.join(OUT, 'all-layers-2229.gpkg')
    if not ids and os.path.exists(allgpkg): os.remove(allgpkg)
    index_path = os.path.join(TILES, 'index.json')
    index = json.load(open(index_path)) if os.path.exists(index_path) else {}
    for L in REG['layers']:
        if ids and L['id'] not in ids: continue
        print(f"== {L['id']}")
        try:
            keep, s = build(L)
            fc = {'type': 'FeatureCollection', 'features': keep}
            p = os.path.join('/tmp', L['id'] + '.geojson'); json.dump(fc, open(p, 'w'))
            if keep:
                if tiles(L['id'], p, L['geom']): s['tiles'] = f"data/layers/{L['id']}.pmtiles"
                s['files'] = exports(L['id'], fc, p, all_layers=not ids)
            else:
                pm = os.path.join(TILES, L['id'] + '.pmtiles')
                if os.path.exists(pm): os.remove(pm)
        except Exception as e:
            traceback.print_exc()
            s = dict(index.get(L['id'], {}), error=f'{type(e).__name__}: {e}'[:400], failed=datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%MZ'))
            s.setdefault('id', L['id'])
        json.dump(s, open(os.path.join(TILES, L['id'] + '.json'), 'w'), indent=1)
        index[L['id']] = {k: v for k, v in s.items() if k != 'source_fields'}
        print(f"   {s.get('count', 0)} kept, dropped {s.get('dropped')}, {s.get('skipped') or s.get('error') or 'ok'}")
    index = {k: v for k, v in index.items() if any(L['id'] == k for L in REG['layers'])}
    json.dump(index, open(index_path, 'w'), indent=1)
    print('done')

if __name__ == '__main__':
    main(sys.argv[1:])
