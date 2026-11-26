"""Sign inventory pipeline for one area. No model API calls: every step is deterministic code.

usage: python pipeline/run.py requests/<key>.json
Steps: street-level photos -> sign boxes -> crops -> trained sign model (ONNX) -> group views into signs
by crossing sight lines -> street, direction and cross street -> 11x17 plan sheets and site data.
"""
import json, math, os, sys, io, time, base64, collections, subprocess, datetime
import numpy as np, cv2, requests
import concurrent.futures as cf
from scipy.spatial import cKDTree
from sklearn.cluster import DBSCAN

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
req_path = sys.argv[1]; KEY = os.path.basename(req_path)[:-5]; REQ = json.load(open(req_path))
BBOX = REQ['bbox']; AREA = REQ['name']
W = os.path.join(REPO, 'work', KEY); os.makedirs(W, exist_ok=True); os.chdir(W)
CFG = open(os.path.join(REPO, 'js', 'config.js')).read()
TOKEN = os.environ.get('MLY_TOKEN') or CFG.split("MLY: '")[1].split("'")[0]
LON0, LAT0 = BBOX[0], BBOX[1]; K = math.cos(math.radians((BBOX[1] + BBOX[3]) / 2)) * 111320; KL = 110540
xy = lambda lo, la: ((lo - LON0) * K, (la - LAT0) * KL)
log = lambda *a: print(time.strftime('%H:%M:%S'), *a, flush=True)
HIGH = 0.7  # mean model probability over the views of a sign; on held-out Culver City signs every sign at or above this was read right
SIGN = ('object--traffic-sign', 'regulatory--', 'warning--', 'information--', 'complementary--', 'object--sign--information')

UA = {'User-Agent': 'fp-sign-inventory/1.0 (+https://github.com/drzkid96/fp-sign-inventory)'}
FAILS = collections.Counter()
def get(url, **p):
    for t in range(6):
        try:
            r = requests.get(url, params=p, timeout=90, headers=UA)
            if r.status_code == 200: return r
            if r.status_code in (400, 404): break
        except Exception: pass
        time.sleep(2 + 4 * t)
    FAILS[url.split('?')[0].split('/')[2]] += 1
    return None

# 1. photos in the area
def quarter(b):
    mx, my = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return [[b[0], b[1], mx, my], [mx, b[1], b[2], my], [b[0], my, mx, b[3]], [mx, my, b[2], b[3]]]
def cell(bx):
    r = get('https://graph.mapillary.com/images', access_token=TOKEN, bbox=','.join(f'{v:.6f}' for v in bx), limit=2000,
            fields='id,captured_at,computed_geometry,computed_compass_angle,is_pano,width,height,camera_parameters,thumb_original_url,thumb_2048_url')
    if r is None: raise SystemExit(f'photo list failed for part of the area {bx}; nothing was written')
    data = [d for d in r.json().get('data', []) if d.get('computed_geometry') and d.get('computed_compass_angle') is not None]
    if len(r.json().get('data', [])) >= 2000 and bx[2] - bx[0] > 0.0004: return [d for q in quarter(bx) for d in cell(q)]
    return data
def images():
    if os.path.exists('all_images.json'): return json.load(open('all_images.json'))
    out = {}; n = max(1, int(max(BBOX[2] - BBOX[0], BBOX[3] - BBOX[1]) / 0.003))
    for i in range(n):
        for j in range(n):
            bx = [BBOX[0] + (BBOX[2] - BBOX[0]) * i / n, BBOX[1] + (BBOX[3] - BBOX[1]) * j / n, BBOX[0] + (BBOX[2] - BBOX[0]) * (i + 1) / n, BBOX[1] + (BBOX[3] - BBOX[1]) * (j + 1) / n]
            r = get('https://graph.mapillary.com/images', access_token=TOKEN, bbox=','.join(f'{v:.6f}' for v in bx), limit=2000,
                    fields='id,captured_at,computed_geometry,computed_compass_angle,is_pano,width,height,camera_parameters,thumb_original_url,thumb_2048_url')
            if r is None: raise SystemExit(f'photo list failed for part of the area {bx}; nothing was written')
            data = r.json().get('data', [])
            if len(data) >= 2000:
                for sub in quarter(bx):
                    for d in cell(sub): out[d['id']] = d
                continue
            for d in data:
                if d.get('computed_geometry') and d.get('computed_compass_angle') is not None: out[d['id']] = d
    A = list(out.values()); json.dump(A, open('all_images.json', 'w')); return A

# 2. sign boxes per photo
import mapbox_vector_tile as mvt
def bbox_of(g):
    t = mvt.decode(base64.b64decode(g), default_options={'y_coord_down': True}); layer = list(t.values())[0]; ext = layer.get('extent', 4096); pts = []
    def walk(c):
        if isinstance(c[0], (int, float)): pts.append(c)
        else: [walk(x) for x in c]
    for f in layer['features']: walk(f['geometry']['coordinates'])
    xs = [p[0] / ext for p in pts]; ys = [p[1] / ext for p in pts]; return min(xs), min(ys), max(xs), max(ys)
def dets(A):
    if os.path.exists('dets.json'): return json.load(open('dets.json'))
    def one(a):
        r = get(f"https://graph.mapillary.com/{a['id']}/detections", access_token=TOKEN, fields='value,geometry')
        out = []
        for d in (r.json().get('data', []) if r else []):
            v = d['value']
            if not v.startswith(SIGN) or 'back' in v or 'advertisement' in v or 'store' in v: continue
            try: out.append(dict(v=v, b=bbox_of(d['geometry'])))
            except Exception: pass
        return a['id'], out
    with cf.ThreadPoolExecutor(12) as ex: D = dict(ex.map(one, A))
    json.dump(D, open('dets.json', 'w')); return D

# 3. crops with bearings
def crops(A, D):
    if os.path.exists('recs.json'): return json.load(open('recs.json'))
    os.makedirs('dc', exist_ok=True); AI = {a['id']: a for a in A}
    def one(i):
        ds = D.get(i) or []; a = AI[i]
        if not ds: return []
        url = a.get('thumb_original_url') if a.get('is_pano') else a.get('thumb_2048_url')
        r = get(url) if url else None
        if r is None: return []
        im = cv2.imdecode(np.frombuffer(r.content, np.uint8), 1)
        if im is None: return []
        H, Wd = im.shape[:2]
        if a.get('is_pano') and Wd > 5760: im = cv2.resize(im, (5760, 2880)); H, Wd = 2880, 5760
        out = []
        for k, d in enumerate(ds):
            x0, y0, x1, y1 = d['b']; X0, X1, Y0, Y1 = x0 * Wd, x1 * Wd, y0 * H, y1 * H
            w, h = X1 - X0, Y1 - Y0
            if w < 14 or h < 14: continue
            if a.get('is_pano'):
                brg = (a['computed_compass_angle'] + ((x0 + x1) / 2 - 0.5) * 360) % 360; angw = (x1 - x0) * 360; elev = (0.5 - (y0 + y1) / 2) * 180
            else:
                cp = a.get('camera_parameters') or [0.6]; f = (cp[0] or 0.6) * max(Wd, H)
                brg = (a['computed_compass_angle'] + math.degrees(math.atan2(((x0 + x1) / 2 - 0.5) * Wd, f))) % 360
                angw = math.degrees(math.atan2(w, f)); elev = math.degrees(math.atan2((0.5 - (y0 + y1) / 2) * H, f))
            p = 0.12 * max(w, h); c = im[max(0, int(Y0 - p)):int(Y1 + p), max(0, int(X0 - p)):int(X1 + p)]
            if c.size == 0: continue
            rid = f'{i}_{k}'; cv2.imwrite(f'dc/{rid}.jpg', c, [cv2.IMWRITE_JPEG_QUALITY, 92])
            lo, la = a['computed_geometry']['coordinates']
            out.append(dict(id=rid, img=i, v=d['v'], brg=brg, angw=angw, elev=elev, wpx=w, hpx=h, lon=lo, lat=la, pano=bool(a.get('is_pano')), t=a['captured_at']))
        return out
    R = []
    with cf.ThreadPoolExecutor(6) as ex:
        for n, rr in enumerate(ex.map(one, [i for i in D if D[i]])):
            R += rr
            if n % 200 == 0: log('photos cropped', n)
    json.dump(R, open('recs.json', 'w')); return R

# 4. trained sign model
def classify(R):
    import onnxruntime as ort
    S = ort.InferenceSession(os.path.join(HERE, 'model', 'signnet.onnx'), providers=['CPUExecutionProvider'])
    CL = json.load(open(os.path.join(HERE, 'model', 'signnet_classes.json')))
    M = np.array([0.485, 0.456, 0.406], np.float32); SD = np.array([0.229, 0.224, 0.225], np.float32)
    def prep(bgr):
        h, w = bgr.shape[:2]; s = max(h, w); c = np.full((s, s, 3), 128, np.uint8); c[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = bgr
        x = cv2.resize(c, (112, 112), interpolation=cv2.INTER_AREA)[:, :, ::-1].astype(np.float32) / 255; return ((x - M) / SD).transpose(2, 0, 1)
    P = []
    for i in range(0, len(R), 64):
        P.append(S.run(None, {'x': np.stack([prep(cv2.imread(f"dc/{r['id']}.jpg")) for r in R[i:i + 64]])})[0])
    return (np.concatenate(P) if P else np.zeros((0, len(CL)))), CL

def adiff(a, b): return abs((a - b + 180) % 360 - 180)

# 5. group views into physical signs
def group(R, P, CL):
    for i, r in enumerate(R):
        r['x'], r['y'] = xy(r['lon'], r['lat']); r['rng'] = 0.75 / max(math.tan(math.radians(max(r['angw'], 0.3))), 1e-3)
        r['c'] = CL[int(P[i].argmax())]; r['p'] = float(P[i].max()); r['i'] = i
    use = [r for r in R if r['c'] != 'X' and r['p'] >= 0.35]
    if len(use) < 2: return []
    X = np.array([[r['x'], r['y']] for r in use]); Bv = np.radians([r['brg'] for r in use]); Dv = np.stack([np.sin(Bv), np.cos(Bv)], 1)
    tr = cKDTree(X); pts = []
    for i in range(len(use)):
        for j in tr.query_ball_point(X[i], 45):
            if j <= i or use[i]['img'] == use[j]['img'] or use[i]['c'] != use[j]['c']: continue
            Mt = np.array([Dv[i], -Dv[j]]).T
            if abs(np.linalg.det(Mt)) < math.sin(math.radians(5)): continue
            ti, tj = np.linalg.solve(Mt, X[j] - X[i])
            if not (1.2 < ti < 45 and 1.2 < tj < 45): continue
            if not (0.35 < ti / use[i]['rng'] < 2.8 and 0.35 < tj / use[j]['rng'] < 2.8): continue
            hi = ti * math.tan(math.radians(use[i]['elev'])); hj = tj * math.tan(math.radians(use[j]['elev']))
            if abs(hi - hj) > 0.7: continue
            p = X[i] + ti * Dv[i]; pts.append((p[0], p[1], (hi + hj) / 2, i, j, use[i]['c']))
    by = collections.defaultdict(list)
    for p in pts: by[p[5]].append(p)
    signs = []
    for c, ps in by.items():
        Q = np.array([p[:3] for p in ps]); lab = DBSCAN(eps=1.0, min_samples=2).fit(np.c_[Q[:, 0], Q[:, 1], Q[:, 2] * 1.5]).labels_
        for l in set(lab) - {-1}:
            cen = np.median(Q[lab == l], 0); mem = set()
            for p, ll in zip(ps, lab):
                if ll == l: mem |= {p[3], p[4]}
            signs.append(dict(code=c, x=float(cen[0]), y=float(cen[1]), h=float(cen[2]), mem=sorted(mem), npts=int((lab == l).sum())))
    signs.sort(key=lambda s: -s['npts']); taken = {}
    for k, s in enumerate(signs):
        s['mem'] = [m for m in s['mem'] if m not in taken]
        for m in s['mem']: taken[m] = k
    signs = [s for s in signs if len(set(use[m]['img'] for m in s['mem'])) >= 2]
    out = []
    for s in sorted(signs, key=lambda s: -len(s['mem'])):
        d = next((o for o in out if o['code'] == s['code'] and math.hypot(o['x'] - s['x'], o['y'] - s['y']) < 1.5 and abs(o['h'] - s['h']) < 0.6), None)
        if d: d['mem'] += s['mem']
        else: out.append(s)
    res = []
    for s in out:
        mem = [use[m] for m in s['mem']]; ci = CL.index(s['code'])
        cam = [(m['x'] - s['x'], m['y'] - s['y']) for m in mem]
        face = math.degrees(math.atan2(np.mean([v[0] / max(math.hypot(*v), 1e-6) for v in cam]), np.mean([v[1] / max(math.hypot(*v), 1e-6) for v in cam]))) % 360
        best = max(mem, key=lambda m: (m['t'] > 1.7e12, min(m['wpx'], m['hpx'])))
        res.append(dict(code=s['code'], x=s['x'], y=s['y'], lon=LON0 + s['x'] / K, lat=LAT0 + s['y'] / KL, h=s['h'], face=face,
                        conf=round(float(np.mean([P[m['i']][ci] for m in mem])), 3), nviews=len(mem), years=sorted(set(time.gmtime(m['t'] / 1000).tm_year for m in mem)),
                        best=best['id'], best_img=best['img'], members=[m['id'] for m in mem]))
    # same sign seen in several photo years
    res.sort(key=lambda s: (-max(s['years']), -s['nviews'])); out = []
    for s in res:
        d = next((o for o in out if o['code'] == s['code'] and math.hypot(o['x'] - s['x'], o['y'] - s['y']) < 5 and adiff(o['face'], s['face']) < 60), None)
        if d: d['years'] = sorted(set(d['years']) | set(s['years'])); d['nviews'] += s['nviews']; d['conf'] = max(d['conf'], s['conf']); d['members'] += s['members']
        else: out.append(s)
    new = [o for o in out if max(o['years']) >= 2024]; keep = []
    for o in out:
        if max(o['years']) < 2024:
            d = min([n for n in new if n['code'] == o['code'] and adiff(n['face'], o['face']) < 70], key=lambda n: math.hypot(n['x'] - o['x'], n['y'] - o['y']), default=None)
            if d and math.hypot(d['x'] - o['x'], d['y'] - o['y']) < 12: d['years'] = sorted(set(d['years']) | set(o['years'])); d['nviews'] += o['nviews']; d['members'] += o['members']; continue
        keep.append(o)
    return keep

# 6. streets: approach and cross street
def osm():
    if os.path.exists('osm.json'): return json.load(open('osm.json'))['elements']
    b = f'{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]}'
    q = f'[out:json][timeout:120];(way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified|living_street|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link|service)$"]({b});node["highway"~"^(stop|give_way|traffic_signals)$"]({b}););out geom;'
    for u in ('https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://maps.mail.ru/osm/tools/overpass/api/interpreter'):
        try:
            r = requests.post(u, data={'data': q}, timeout=200, headers={'User-Agent': 'fp-sign-inventory/1.0'})
            if r.status_code == 200: open('osm.json', 'w').write(r.text); return r.json()['elements']
        except Exception: pass
    raise SystemExit('street network not available')
def short(n):
    for a, b in ((' North', ' N'), (' South', ' S'), ('North ', 'N '), ('South ', 'S '), (' Street', ' St'), (' Avenue', ' Av'), (' Drive', ' Dr'), (' Road', ' Rd'), (' Boulevard', ' Blvd'), (' Place', ' Pl'), (' Lane', ' Ln'), (' Way', ' Wy'), (' Court', ' Ct')): n = n.replace(a, b)
    return n
def approach(S, O):
    ways = [e for e in O if e['type'] == 'way' and e.get('tags', {}).get('highway') not in (None, 'service') and e['tags'].get('name')]
    segs = []; nodeways = collections.defaultdict(set); nodexy = {}; axis = {}
    for w in ways:
        g = w['geometry']; nm = w['tags']['name']
        for a, b in zip(g[:-1], g[1:]): segs.append((np.array(xy(a['lon'], a['lat'])), np.array(xy(b['lon'], b['lat'])), nm))
        for n, pt in zip(w['nodes'], g): nodeways[n].add(nm); nodexy[n] = xy(pt['lon'], pt['lat'])
        p = xy(g[0]['lon'], g[0]['lat']); q = xy(g[-1]['lon'], g[-1]['lat']); d = (q[0] - p[0], q[1] - p[1])
        if d[0] < 0: d = (-d[0], -d[1])
        v = axis.setdefault(nm, [0, 0]); v[0] += d[0]; v[1] += d[1]
    axis = {k: math.degrees(math.atan2(v[0], v[1])) % 360 for k, v in axis.items()}
    inter = [(nodexy[n], sorted(v)) for n, v in nodeways.items() if len(v) >= 2]
    def lab(b, ax):
        if abs(math.sin(math.radians(ax))) >= abs(math.cos(math.radians(ax))): return 'EB' if math.sin(math.radians(b)) >= 0 else 'WB'
        return 'NB' if math.cos(math.radians(b)) >= 0 else 'SB'
    for s in S:
        trav = (s['face'] + 180) % 360; P0 = np.array([s['x'], s['y']]); best = None; near = None
        for p, q, nm in segs:
            v = q - p; L = np.linalg.norm(v)
            if L < 0.5: continue
            t = np.clip((P0 - p) @ v / L ** 2, 0, 1); d = np.linalg.norm(p + t * v - P0)
            if near is None or d < near[0]: near = (d, nm)
            if d > 30: continue
            sb = math.degrees(math.atan2(v[0], v[1])) % 180; al = min(adiff(sb, trav % 180), adiff(sb + 180, trav % 180))
            if al < 40 and (best is None or d + 0.4 * al < best[0]): best = (d + 0.4 * al, nm)
        st = (best or near or (0, ''))[1]; s['street'] = short(st); s['dir'] = lab(trav, axis.get(st, 0))
        tv = np.array([math.sin(math.radians(trav)), math.cos(math.radians(trav))]); cand = []
        for pt, names in inter:
            if st not in names: continue
            v = np.array(pt) - P0; d = np.linalg.norm(v)
            if d > 120: continue
            cand.append((d if v @ tv > -8 else d + 60, [n for n in names if n != st]))
        s['at'] = short(sorted(cand, key=lambda c: c[0])[0][1][0]) if cand else ''
        s['loc'] = f"{s['dir']} {s['street']}" + (f" at {s['at']}" if s['at'] else '')
    return S

# 7. coverage of the street network by photos
def coverage(A, O):
    I = cKDTree([xy(*a['computed_geometry']['coordinates']) for a in A]); tot = hit = 0
    for w in O:
        if w['type'] != 'way' or w.get('tags', {}).get('highway') in (None, 'service') or not w['tags'].get('name'): continue
        g = [np.array(xy(p['lon'], p['lat'])) for p in w['geometry']]
        for p, q in zip(g[:-1], g[1:]):
            n = max(1, int(np.linalg.norm(q - p) // 5))
            for t in range(n): tot += 1; hit += bool(I.query_ball_point(p + (q - p) * (t + .5) / n, 12))
    return round(100 * hit / max(tot, 1))

if __name__ == '__main__':
    A = images(); log('photos', len(A))
    if not A: raise SystemExit('no street-level photos in this area')
    D = dets(A); log('photos with sign boxes', sum(1 for v in D.values() if v))
    R = crops(A, D); log('sign views', len(R))
    if FAILS: log('requests that failed after retries', dict(FAILS))
    nd = sum(1 for v in D.values() if v)
    if FAILS.get('graph.mapillary.com', 0) > 0.05 * len(A): raise SystemExit('too many sign-box requests failed; rerun later')
    P, CL = classify(R); log('classified')
    S = group(R, P, CL); log('signs', len(S))
    O = osm(); S = approach(S, O); cov = coverage(A, O); log('street length with photos', cov, '%')
    json.dump(S, open('signs3.json', 'w'))
    corridor = REQ.get('corridor') or collections.Counter(s['street'] for s in S if s['code'] not in ('STREET', 'GUIDE')).most_common(1)[0][0]
    full = next((w['tags']['name'] for w in O if w['type'] == 'way' and short(w['tags'].get('name', '')) == corridor), corridor)
    sys.path.insert(0, HERE); import sheets_geo; sheets_geo.setup(BBOX, REQ.get('scale') or (80 if REQ.get('layout') == 'grid' else 40))
    if REQ.get('layout') == 'grid':
        cl = np.zeros((0, 2)); F = sheets_geo.frames_grid([s for s in S if s['code'] not in ('STREET', 'GUIDE', 'X')], BBOX)
    else:
        cl = sheets_geo.centerline(O, full); F = sheets_geo.frames(cl, S)
    json.dump({'cl': cl.tolist(), 'frames': F}, open('frames.json', 'w'))
    date = datetime.date.today().isoformat()
    os.makedirs(os.path.join(REPO, 'data', 'areas', KEY, 'crops'), exist_ok=True)
    pdf = os.path.join(REPO, 'data', 'areas', KEY, f'{date}_SIGN-INVENTORY_{KEY.upper()}.pdf')
    scale = REQ.get('scale') or (80 if REQ.get('layout') == 'grid' else 40); sheets_geo.setup(BBOX, scale)
    env = dict(os.environ, REPO=REPO, AREA=AREA, BBOX=json.dumps(BBOX), DATE=date, SCALE=str(scale))
    subprocess.run([sys.executable, os.path.join(HERE, 'build_sheets.py'), pdf], check=True, env=env, cwd=W)
    Sf = json.load(open('signs_final.json')); IXR = json.load(open('intersections.json'))
    for i in IXR: i['lon'], i['lat'] = LON0 + i['x'] / K, LAT0 + i['y'] / KL
    site = []
    for s in Sf:
        c = cv2.imread(f"dc/{s['best']}.jpg"); cv2.imwrite(os.path.join(REPO, 'data', 'areas', KEY, 'crops', s['id'] + '.jpg'), c, [cv2.IMWRITE_JPEG_QUALITY, 85])
        code = s['code'].split('/')[0] if s['code'].startswith('R2-1') else ('' if s['code'].startswith('NC-') else s['code'])
        site.append(dict(id=s['id'], lat=s['lat'], lon=s['lon'], code=code, val=s['code'].split('/')[1] if s['code'].startswith('R2-1/') else '',
                         status='verified' if s['conf'] >= HIGH else 'review', conf=s['conf'], dir=round(s['face']), loc=s['loc'],
                         seen=str(max(s['years'])), years=s['years'], views=s['nviews'], img=s['best_img'], crop=s['id'] + '.jpg',
                         cls={'NC-PARK': 'Parking sign (no standard code)', 'NC-WARN': 'Warning sign (no standard code)', 'NC-ID': 'Community ID sign'}.get(s['code'], '')))
    names = [dict(lat=s['lat'], lon=s['lon'], kind=s['code'], loc=s['loc'], seen=str(max(s['years']))) for s in S if s['code'] in ('STREET', 'GUIDE')]
    json.dump(dict(key=KEY, area=AREA, bbox=BBOX, date=date, coverage=cov, sheets=os.path.basename(pdf), complete=True,
                   method='Found by scanning street-level photos, placed by crossing sight lines from several photos, codes read by a trained sign model (no manual reads).',
                   signs=site, name_signs=names, intersections=IXR), open(os.path.join(REPO, 'data', 'areas', KEY, 'signs.json'), 'w'))
    log('done', len(site), 'signs,', len(names), 'street name or guide signs, sheets', os.path.basename(pdf))
