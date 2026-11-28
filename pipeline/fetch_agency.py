"""Download published agency asset layers (ArcGIS REST) to GeoJSON, then the workflow tiles them.

Each layer is paged with resultOffset and saved as data/base/src/<name>.geojson (WGS84).
Only fields the map uses are kept, renamed to a common set:
  code (sign or marking code), desc, status, date (install or last maintained), src (agency).
Usage: python3 pipeline/fetch_agency.py <out folder>
"""
import sys, json, time, urllib.request, urllib.parse, os

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
DPW = 'https://dpw.gis.lacounty.gov/dpw/rest/services'
LAYERS = [  # name, url, kind
    ('county_signs', f'{DPW}/cityworks/cityworks_osd/MapServer/0', 'sign'),
    ('county_striping', f'{DPW}/cityworks/cityworks_osd/MapServer/14', 'stripe'),
    ('county_markings', f'{DPW}/cityworks/cityworks_osd/MapServer/15', 'marking'),
    ('county_signals', f'{DPW}/PW_Jurisdiction_Locator/MapServer/16', 'signal'),
]
UA = {'User-Agent': 'Mozilla/5.0 (fp-sign-inventory; public data download)'}

def get(url, params):
    q = url + '?' + urllib.parse.urlencode(params)
    for t in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(q, headers=UA), timeout=120) as r: return json.load(r)
        except Exception as e:
            print('  retry', t, str(e)[:80]); time.sleep(5 * (t + 1))
    raise SystemExit('failed ' + url)

def pick(p, *names):
    for n in names:
        for k in p:
            if k.upper() == n and p[k] not in (None, '', ' '): return p[k]
    return ''

def day(v):
    if isinstance(v, (int, float)) and v > 0: return time.strftime('%Y-%m-%d', time.gmtime(v / 1000))
    return str(v or '')[:10]

summary = {}
for name, url, kind in LAYERS:
    meta = get(url, {'f': 'json'})
    n = get(url + '/query', {'where': '1=1', 'returnCountOnly': 'true', 'f': 'json'}).get('count', 0)
    step = min(meta.get('maxRecordCount') or 1000, 2000); feats = []; off = 0; bad = 0
    print(name, n, 'reported; fields:', [f['name'] for f in meta.get('fields', [])][:60])
    while True:   # page until a short page (the reported count can be 0 or wrong)
        d = get(url + '/query', {'where': '1=1', 'outFields': '*', 'outSR': 4326, 'f': 'geojson', 'resultOffset': off, 'resultRecordCount': step, 'orderByFields': meta.get('objectIdField') or 'OBJECTID'})
        got = d.get('features', []); off += step
        for f in got:
            p = f.get('properties') or {}
            f['properties'] = {
                'code': pick(p, 'SGN_CODE', 'MARKCODE', 'STRIPECODE', 'S_TYPE', 'SIG_TYPE', 'CODE', 'SIGNCODE'),
                'desc': pick(p, 'LONG_DESCRIPTION', 'SGN_DESC', 'DESCRIPTION', 'MARKDESC', 'S_DESC', 'DESC_'),
                'dir': pick(p, 'SGN_DIR'),
                'status': pick(p, 'STATUS'),
                'date': day(pick(p, 'LAST_MAINT_DATE', 'INSTALLDATE', 'INSTALL_DATE', 'LASTMODDATE')),
                'loc': pick(p, 'LOCATION', 'STREET'),
                'src': 'LA County Public Works', 'kind': kind}
            g = f.get('geometry') or {}
            if g.get('coordinates') and g['coordinates'] != [] and 'NaN' not in json.dumps(g['coordinates'])[:200]: feats.append(f)
            else: bad += 1
        if len(feats) % 20000 < step: print(f'  {len(feats)} kept, {bad} without location', flush=True)
        if len(got) < step: break
    print(f'  done: {len(feats)} kept, {bad} without location', flush=True)
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(f'{OUT}/{name}.geojson', 'w'), separators=(',', ':'))
    summary[name] = {'count': len(feats), 'no_location': bad, 'source': url, 'downloaded': time.strftime('%Y-%m-%d')}
json.dump(summary, open(f'{OUT}/summary.json', 'w'), indent=1)
print(json.dumps(summary, indent=1))
