"""OSM context for sign reads. No image reading here: only street facts from OpenStreetMap.

For each sign the model's class probabilities (averaged over its photos) are weighted by what OSM says about
the approach it faces: stop or signal control, one-way streets nearby, and the turn lanes on that approach.
Weights are modest, so a clear read still wins; they decide close calls. Lane-use signs (R3-5) also get their
arrow side from the turn lanes.
"""
import math, collections
import numpy as np
from scipy.spatial import cKDTree

SKIP = {'service', 'footway', 'cycleway', 'path', 'steps', 'pedestrian', 'track', None}
def adiff(a, b): return abs((a - b + 180) % 360 - 180)
def brg(p, q): return math.degrees(math.atan2(q[0] - p[0], q[1] - p[1])) % 360

def lanes_for(tags, forward):
    """turn:lanes for the travel direction, as a list of lane movements, left to right; None if OSM has none."""
    ow = tags.get('oneway') in ('yes', 'true', '1', '-1')
    key = 'turn:lanes' if ow else ('turn:lanes:forward' if forward else 'turn:lanes:backward')
    v = tags.get(key) or (tags.get('turn:lanes') if not ow else None)
    return [l.split(';') for l in v.split('|')] if v else None

def build(O, xy):
    ways = [w for w in O if w['type'] == 'way' and w.get('tags', {}).get('highway') not in SKIP]
    segs = []; byname = collections.defaultdict(set); nodes = {}
    for w in ways:
        pts = [xy(p['lon'], p['lat']) for p in w['geometry']]
        for a, b in zip(pts[:-1], pts[1:]): segs.append((np.array(a), np.array(b), w))
        for n, p in zip(w['nodes'], pts):
            nodes[n] = p
            if w['tags'].get('name'): byname[n].add(w['tags']['name'])
    inter = [nodes[n] for n, v in byname.items() if len(v) >= 2]
    ctl = [(e['tags']['highway'], e['tags'].get('stop'), xy(e['lon'], e['lat'])) for e in O if e['type'] == 'node' and e.get('tags', {}).get('highway') in ('traffic_signals', 'stop', 'give_way')]
    ow_pts = [p for a, b, w in segs if w['tags'].get('oneway') in ('yes', 'true', '1', '-1') for p in (a, b)]
    return dict(segs=segs, inter=np.array(inter) if inter else np.zeros((0, 2)), IT=cKDTree(inter) if inter else None,
                ctl=ctl, CT=cKDTree([c[2] for c in ctl]) if ctl else None, OW=cKDTree(ow_pts) if ow_pts else None)

def facts(s, G):
    """What OSM says about the approach a sign faces."""
    P0 = np.array([s['x'], s['y']]); trav = (s['face'] + 180) % 360
    tv = np.array([math.sin(math.radians(trav)), math.cos(math.radians(trav))])
    best = None
    for a, b, w in G['segs']:
        v = b - a; L = np.linalg.norm(v)
        if L < 0.5: continue
        t = np.clip((P0 - a) @ v / L ** 2, 0, 1); d = np.linalg.norm(a + t * v - P0)
        if d > 25: continue
        sb = brg(a, b); al = min(adiff(sb, trav), adiff(sb + 180, trav))
        if al < 40 and (best is None or d + 0.3 * al < best[0]): best = (d + 0.3 * al, w, adiff(sb, trav) < 90, a, v / L)
    f = dict(street=None, lanes=None, control='none', dist=None, oneway_near=False, side=None)
    if best:
        _, w, fwd, a, u = best; f['street'] = w['tags'].get('name'); f['lanes'] = lanes_for(w['tags'], fwd)
        # which side of the centerline the sign stands on, relative to travel
        d = P0 - a; cross = tv[0] * d[1] - tv[1] * d[0]; f['side'] = 'left' if cross > 0 else 'right'
    if G['IT'] is not None:
        cand = [(np.linalg.norm(G['inter'][i] - P0), i) for i in G['IT'].query_ball_point(P0, 90) if (G['inter'][i] - P0) @ tv > -5]
        if cand:
            d, i = min(cand); f['dist'] = round(float(d)); c = G['inter'][i]
            near = [G['ctl'][k] for k in G['CT'].query_ball_point(c, 45)] if G['CT'] is not None else []
            if any(h == 'traffic_signals' and math.dist(p, c) < 30 for h, st, p in near): f['control'] = 'signal'
            elif any(h == 'stop' and st == 'all' for h, st, p in near): f['control'] = 'all-way stop'
            else:
                for h, st, p in near:
                    # a stop or yield node on this approach sits between the sign and the intersection, or just behind it
                    if h in ('stop', 'give_way') and math.dist(p, c) < 40 and adiff(brg(c, p), (trav + 180) % 360) < 35:
                        f['control'] = 'stop' if h == 'stop' else 'yield'
    if G['OW'] is not None: f['oneway_near'] = bool(G['OW'].query_ball_point(P0, 60))
    return f

def weights(f, CL):
    w = np.ones(len(CL)); notes = []
    def mult(codes, k):
        for i, c in enumerate(CL):
            if c in codes: w[i] *= k
    at_int = f['dist'] is not None and f['dist'] <= 60
    if at_int and f['control'] in ('stop', 'all-way stop') and f['dist'] <= 45: mult({'R1-1'}, 4.0); notes.append(f"OSM: {f['control']} approach")
    elif at_int and f['control'] == 'signal': mult({'R1-1'}, 0.25); mult({'R10-11', 'R10-12', 'R10-7', 'R10-15'}, 1.5); notes.append('OSM: signal')
    elif at_int and f['control'] == 'yield': mult({'R1-2'}, 3.0); notes.append('OSM: yield approach')
    elif f['dist'] is not None: mult({'R1-1'}, 0.7)
    if f['control'] != 'signal': mult({'R10-11', 'R10-12'}, 0.35)
    if f['oneway_near']: mult({'R6-1', 'R6-2', 'R5-1'}, 1.5)
    else: mult({'R6-1', 'R6-2', 'R5-1'}, 0.5)
    L = f['lanes']
    if L:
        excl_l = any(l == ['left'] for l in L); excl_r = any(l == ['right'] for l in L)
        lu = {'R3-5', 'R3-6', 'R3-8', 'R3-18'}
        if excl_l or excl_r: mult(lu, 1.5); notes.append('OSM turn lanes: ' + '|'.join(';'.join(l) for l in L))
        else: mult(lu, 0.45)
        mult({'R3-7'}, 2.0 if L[-1] == ['right'] else 0.5)
    return w, notes

def apply(S, O, xy, CL):
    G = build(O, xy); changed = 0
    for s in S:
        if 'pv' not in s: continue
        f = facts(s, G); w, notes = weights(f, CL)
        p = np.array(s['pv']) * w; p /= p.sum(); k = int(p.argmax())
        s['code_model'] = s['code']; s['osm'] = f; s['osm_notes'] = notes
        new = CL[k]
        if new != s['code'] and new not in ('STREET', 'GUIDE', 'X') and s['code'] not in ('STREET', 'GUIDE'):
            s['code'] = new; changed += 1; s['osm_notes'].append(f"changed from {s['code_model']} by OSM context")
        s['conf'] = round(float(p[CL.index(s['code'])]) if s['code'] in CL else s['conf'], 3)
        if s['code'] == 'R3-5' and f['lanes']:
            el = any(l == ['left'] for l in f['lanes']); er = any(l == ['right'] for l in f['lanes'])
            s['arrow'] = 'L' if el and not er else ('R' if er and not el else ('L' if f['side'] == 'left' else 'R'))
    return changed
