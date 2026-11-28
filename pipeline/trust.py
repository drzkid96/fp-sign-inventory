"""Trust table for Mapillary's own sign detections, scored against our scanned areas.

For each CA MUTCD code family:
  found     = our high-confidence signs of that code that Mapillary also has, same code, within 15 m
  precision = Mapillary signs of that code near our scanned streets (within 30 m of any of our signs)
              that match one of our signs of the same code within 15 m
Trust: likely  = at least 5 of our signs, found >= 85% and precision >= 70% (or too few to test precision)
       mixed   = found >= 50%
       low     = below that
       untested = code not in our scanned areas yet
Output: data/base/trust.json. Reruns as more areas are scanned.
Usage: python3 pipeline/trust.py
"""
import json, math, glob, os, urllib.request, collections
import mapbox_vector_tile as mvt

T = open('js/config.js').read().split("MLY: '")[1].split("'")[0]
CM = json.load(open('data/classmap.json'))
fam = lambda c: (c or '').split('/')[0].split('(')[0].strip()
code = lambda v: fam((CM.get(v) or {}).get('code'))
kx, ky = 111320 * math.cos(math.radians(34)), 110540
dist = lambda a, b: math.hypot((a[0] - b[0]) * kx, (a[1] - b[1]) * ky)

def mly(w, so, e, n):
    z = 14; N = 2 ** z
    tx = lambda x: int((x + 180) / 360 * N); ty = lambda y: int((1 - math.asinh(math.tan(math.radians(y))) / math.pi) / 2 * N)
    out = []
    for x in range(tx(w), tx(e) + 1):
        for y in range(ty(n), ty(so) + 1):
            b = urllib.request.urlopen(f'https://tiles.mapillary.com/maps/vtp/mly_map_feature_traffic_sign/2/{z}/{x}/{y}?access_token={T}', timeout=60).read()
            for f in mvt.decode(b).get('traffic_sign', {}).get('features', []):
                px, py = f['geometry']['coordinates']; X = x + px / 4096; Y = y + 1 - py / 4096
                lon = X / N * 360 - 180; lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * Y / N))))
                if w <= lon <= e and so <= lat <= n: out.append((lon, lat, code(f['properties']['value'])))
    return out

ours_n = collections.Counter(); found = collections.Counter(); m_n = collections.Counter(); m_ok = collections.Counter(); areas = []
for f in sorted(glob.glob('data/areas/*/signs.json')):
    d = json.load(open(f)); allS = [(s['lon'], s['lat'], fam(s.get('code'))) for s in d['signs'] if 'lat' in s]
    V = [x for x, s in zip(allS, [s for s in d['signs'] if 'lat' in s]) if s.get('status') == 'verified']
    if not V: continue
    lo = [s[0] for s in allS]; la = [s[1] for s in allS]
    F = mly(min(lo) - 0.0005, min(la) - 0.0005, max(lo) + 0.0005, max(la) + 0.0005)
    for s in V:
        ours_n[s[2]] += 1
        if any(m[2] == s[2] and dist(m, s) < 15 for m in F): found[s[2]] += 1
    for m in F:
        if not m[2] or not any(dist(m, s) < 30 for s in allS): continue
        m_n[m[2]] += 1
        if any(s[2] == m[2] and dist(m, s) < 15 for s in V): m_ok[m[2]] += 1
    areas.append(d.get('area', f))

out = {}
for c in sorted(set(ours_n) | set(m_n)):
    if not c: continue
    n = ours_n[c]; r = found[c] / n if n else None; p = m_ok[c] / m_n[c] if m_n[c] >= 5 else None
    t = 'untested' if n < 5 else 'likely' if r >= 0.85 and (p is None or p >= 0.7) else 'mixed' if r >= 0.5 else 'low'
    out[c] = {'trust': t, 'ours': n, 'found': None if r is None else round(r, 2), 'mly': m_n[c], 'precision': None if p is None else round(p, 2)}
os.makedirs('data/base', exist_ok=True)
json.dump({'areas': areas, 'codes': out}, open('data/base/trust.json', 'w'), indent=1)
for k in ('likely', 'mixed', 'low'): print(k, [c for c, v in out.items() if v['trust'] == k])
