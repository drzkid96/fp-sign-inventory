"""OSM arterials (trunk, primary, secondary, tertiary) for Los Angeles County, in chunks, to osm_art.json.
Usage: python3 pipeline/fetch_osm_art.py <out folder>"""
import sys, json, time, urllib.request, urllib.parse
OUT = sys.argv[1]
MIRRORS = ['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
x0, y0, x1, y1 = -118.95, 33.70, -117.64, 34.83; n = 4; out = {}
for i in range(n):
    for j in range(n):
        b = (y0 + (y1 - y0) * j / n, x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * (j + 1) / n, x0 + (x1 - x0) * (i + 1) / n)
        q = '[out:json][timeout:300];way(%.4f,%.4f,%.4f,%.4f)["highway"~"^(trunk|primary|secondary|tertiary)(_link)?$"];out tags geom;' % b
        for t in range(8):
            m = MIRRORS[t % len(MIRRORS)]
            try:
                req = urllib.request.Request(m, data=urllib.parse.urlencode({'data': q}).encode(), headers={'User-Agent': 'fp-sign-inventory'})
                d = json.load(urllib.request.urlopen(req, timeout=400))
                for e in d['elements']: out[e['id']] = {'tags': {'highway': e['tags'].get('highway', ''), 'name': e['tags'].get('name', '')}, 'geometry': e.get('geometry', [])}
                print(i, j, len(d['elements']), flush=True); break
            except Exception as e:
                print('retry', i, j, m, str(e)[:60], flush=True); time.sleep(20)
        else: raise SystemExit('overpass failed')
json.dump({'elements': list(out.values())}, open(f'{OUT}/osm_art.json', 'w'))
print('ways', len(out))
