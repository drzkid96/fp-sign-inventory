"""Intersection check against OpenStreetMap.

Every OSM intersection is split into approaches (one per street leg that carries traffic toward it).
Each approach gets its OSM control (signal, stop, all-way stop, yield or none), the signs found on it,
whether photos cover it, and a status:
  OK              control in OSM and signs found agree
  STOP NOT SEEN   OSM says stop, the approach has photos, no R1-1 was found
  STOP NOT IN OSM R1-1 found where OSM has no stop
  STOP AT SIGNAL  R1-1 found on a signalized approach
  NO PHOTOS       the approach has no street-level photos, nothing can be checked
"""
import math, collections
import numpy as np
from scipy.spatial import cKDTree

SKIP = {'service', 'footway', 'cycleway', 'path', 'steps', 'pedestrian', 'track', None}

def adiff(a, b): return abs((a - b + 180) % 360 - 180)
def brg(p, q): return math.degrees(math.atan2(q[0] - p[0], q[1] - p[1])) % 360
def short(n):
    for a, b in ((' North', ' N'), (' South', ' S'), ('North ', 'N '), ('South ', 'S '), (' Street', ' St'), (' Avenue', ' Av'), (' Drive', ' Dr'), (' Road', ' Rd'), (' Boulevard', ' Blvd'), (' Place', ' Pl'), (' Lane', ' Ln'), (' Way', ' Wy'), (' Court', ' Ct')): n = n.replace(a, b)
    return n
def dirlab(b, axis=None):
    if axis is None: return ['NB', 'EB', 'SB', 'WB'][int(((b + 45) % 360) // 90)]
    if abs(math.sin(math.radians(axis))) >= abs(math.cos(math.radians(axis))): return 'EB' if math.sin(math.radians(b)) >= 0 else 'WB'
    return 'NB' if math.cos(math.radians(b)) >= 0 else 'SB'

def check(O, S, photos_xy, xy, bbox_xy=None):
    """O: OSM elements; S: signs with x, y, face, code, id, conf; photos_xy: list of photo positions (m);
    xy: lon/lat -> local metres. Returns list of intersections."""
    ways = [w for w in O if w['type'] == 'way' and w.get('tags', {}).get('name') and w['tags'].get('highway') not in SKIP]
    nodes = {}; byname = collections.defaultdict(set); legs_at = collections.defaultdict(list)
    for w in ways:
        g = w['geometry']; nm = w['tags']['name']; ow = w['tags'].get('oneway', 'no')
        pts = [xy(p['lon'], p['lat']) for p in g]
        for i, n in enumerate(w['nodes']):
            nodes[n] = pts[i]; byname[n].add(nm)
            for step, inbound in ((-1, True), (1, False)):
                j = i + step; far = None
                while 0 <= j < len(pts):
                    far = pts[j]
                    if math.dist(pts[i], pts[j]) >= 15: break
                    j += step
                if far is None: continue
                # two-way streets: every leg carries traffic in; one-way: only the upstream leg
                if ow in ('yes', 'true', '1'): flows_in = inbound
                elif ow == '-1': flows_in = not inbound
                else: flows_in = True
                legs_at[n].append(dict(name=nm, away=brg(pts[i], far), flows_in=flows_in, far=far))
    ax = collections.defaultdict(lambda: [0.0, 0.0])
    for w in ways:
        g = w['geometry']; p = xy(g[0]['lon'], g[0]['lat']); q = xy(g[-1]['lon'], g[-1]['lat']); d = (q[0] - p[0], q[1] - p[1])
        if d[0] < 0: d = (-d[0], -d[1])
        ax[w['tags']['name']][0] += d[0]; ax[w['tags']['name']][1] += d[1]
    axis = {k: math.degrees(math.atan2(v[0], v[1])) % 360 for k, v in ax.items()}
    inter_nodes = [n for n, v in byname.items() if len(v) >= 2]
    if not inter_nodes: return []
    P = np.array([nodes[n] for n in inter_nodes])
    # cluster nodes of one intersection (divided streets) within 22 m
    parent = list(range(len(P))); tr = cKDTree(P)
    def find(a):
        while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for a, b in tr.query_pairs(22):
        parent[find(a)] = find(b)
    groups = collections.defaultdict(list)
    for i, n in enumerate(inter_nodes): groups[find(i)].append(n)
    ctrl = [(e, xy(e['lon'], e['lat'])) for e in O if e['type'] == 'node' and e.get('tags', {}).get('highway') in ('traffic_signals', 'stop', 'give_way')]
    CT = cKDTree([c[1] for c in ctrl]) if ctrl else None
    PH = cKDTree(photos_xy) if len(photos_xy) else None
    SG = cKDTree([(s['x'], s['y']) for s in S]) if S else None
    out = []
    for k, ns in groups.items():
        c = np.mean([nodes[n] for n in ns], axis=0)
        if bbox_xy and not (bbox_xy[0] <= c[0] <= bbox_xy[2] and bbox_xy[1] <= c[1] <= bbox_xy[3]): continue
        names = sorted(set().union(*[byname[n] for n in ns]))
        if len(names) < 2: continue
        # approaches: inbound legs, merged by street and bearing
        appr = []
        for n in ns:
            for l in legs_at[n]:
                if not l['flows_in']: continue
                far = np.array(l['far'])
                away = brg(c, far)
                m = next((a for a in appr if a['name'] == l['name'] and adiff(a['away'], away) < 35), None)
                if not m: appr.append(dict(name=l['name'], away=away))
        if not appr: continue
        near = [ctrl[i] for i in CT.query_ball_point(c, 45)] if CT is not None else []
        signal = any(e['tags']['highway'] == 'traffic_signals' and math.dist(p, c) < 30 for e, p in near)
        allway = any(e['tags']['highway'] == 'stop' and e['tags'].get('stop') == 'all' for e, p in near)
        res = []
        for a in appr:
            u = np.array([math.sin(math.radians(a['away'])), math.cos(math.radians(a['away']))])
            trav = (a['away'] + 180) % 360
            # OSM control on this approach
            ctl = 'signal' if signal else ('all-way stop' if allway else 'none')
            if not signal and not allway:
                for e, p in near:
                    v = np.array(p) - c; d = np.linalg.norm(v)
                    if d < 3 or e['tags']['highway'] == 'traffic_signals': continue
                    if adiff(brg(c, p), a['away']) < 30 and d < 40:
                        ctl = 'stop' if e['tags']['highway'] == 'stop' else 'yield'
            # signs serving this approach: travel direction matches and the sign stands out along this leg
            sg = []
            for i in (SG.query_ball_point(c, 50) if SG is not None else []):
                s = S[i]; v = np.array([s['x'], s['y']]) - c
                along = v @ u; perp = abs(v[0] * u[1] - v[1] * u[0])
                if along > -6 and perp < 22 and adiff((s['face'] + 180) % 360, trav) < 50: sg.append(s)
            codes = [s['code'] for s in sg]
            covered = PH is not None and all(PH.query_ball_point(c + u * t, 9) for t in (18, 32))  # photos on the approach itself, not just from the cross street
            has_stop = 'R1-1' in codes; has_yield = 'R1-2' in codes
            if not covered and not sg: st = 'NO PHOTOS'
            elif ctl in ('stop', 'all-way stop'): st = 'OK' if has_stop else ('STOP NOT SEEN' if covered else 'NO PHOTOS')
            elif ctl == 'signal': st = 'STOP AT SIGNAL' if has_stop else 'OK'
            elif ctl == 'yield': st = 'OK' if has_yield else ('YIELD NOT SEEN' if covered else 'NO PHOTOS')
            else: st = 'STOP NOT IN OSM' if has_stop else 'OK'
            res.append(dict(street=short(a['name']), dir=dirlab(trav, axis.get(a['name'])), control=ctl, signs=[s['id'] for s in sg], codes=codes, photos=bool(covered), status=st))
        out.append(dict(name=' / '.join(short(n) for n in names), x=float(c[0]), y=float(c[1]), signal=signal, approaches=sorted(res, key=lambda r: ['NB', 'SB', 'EB', 'WB'].index(r['dir']))))
    out.sort(key=lambda i: (-i['y'], i['x']))
    for k, i in enumerate(out): i['id'] = f'I-{k + 1:02d}'
    return out
