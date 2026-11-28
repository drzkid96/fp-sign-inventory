"""Street-name geocoder for LA County: 'Main St between 1st St and 3rd St' -> line, midpoint.

Uses Census TIGER all-roads for LA County (tl_2025_06037_roads.zip) and, for a city hint, TIGER places.
Works in CA State Plane Zone 5 (EPSG:2229, US ft); returns WGS84 shapes.
"""
import re, math, functools
import geopandas as gpd
from shapely.geometry import Point, LineString, MultiLineString
from shapely.ops import linemerge, substring, nearest_points, unary_union

SUF = {'avenue': 'ave', 'av': 'ave', 'street': 'st', 'boulevard': 'blvd', 'bl': 'blvd', 'blv': 'blvd', 'drive': 'dr', 'road': 'rd', 'place': 'pl',
       'lane': 'ln', 'court': 'ct', 'parkway': 'pkwy', 'pky': 'pkwy', 'highway': 'hwy', 'terrace': 'ter', 'circle': 'cir', 'way': 'way', 'wy': 'way',
       'square': 'sq', 'trail': 'trl', 'freeway': 'fwy', 'expressway': 'expy', 'alley': 'aly', 'walk': 'walk', 'mall': 'mall', 'plaza': 'plz'}
DIRS = {'n', 's', 'e', 'w', 'north', 'south', 'east', 'west', 'ne', 'nw', 'se', 'sw'}
ALIAS = {'del longpre ave': 'de longpre ave', '405 fwy': 'i- 405', '110 fwy': 'i- 110', '10 fwy': 'i- 10', '101 fwy': 'us hwy 101', '5 fwy': 'i- 5', '105 fwy': 'i- 105', '710 fwy': 'i- 710', '210 fwy': 'i- 210', '605 fwy': 'i- 605'}
ORD = {'first': '1st', 'second': '2nd', 'third': '3rd', 'fourth': '4th', 'fifth': '5th', 'sixth': '6th', 'seventh': '7th', 'eighth': '8th', 'ninth': '9th', 'tenth': '10th'}

def norm(name):
    s = re.sub(r'\(.*?\)', ' ', str(name or '').lower()); s = re.sub(r'[.,#]', ' ', s); s = re.sub(r'\s+', ' ', s).strip()
    s = ALIAS.get(s, s)
    w = [ORD.get(x, x) for x in s.split()]
    if len(w) == 2 and w[0] in ('avenue', 'av', 'ave') and w[1].isdigit(): w[0] = 'ave'
    while len(w) > 1 and w[0] in DIRS: w = w[1:]
    while len(w) > 1 and w[-1] in DIRS: w = w[:-1]
    if len(w) > 1 and w[-1] in SUF: w[-1] = SUF[w[-1]]
    return ' '.join(w)

def base(n):                                    # name without its suffix: "olympic blvd" -> "olympic"
    w = n.split(); return ' '.join(w[:-1]) if len(w) > 1 and w[-1] in SUF.values() else n

class Streets:
    def __init__(self, roads_zip, places_zip=None):
        r = gpd.read_file(roads_zip, columns=['FULLNAME'])
        r = r[r.FULLNAME.notna()].to_crs(2229); r['k'] = r.FULLNAME.map(norm); r['b'] = r.k.map(base)
        self.r = r; self.by = {k: g for k, g in r.groupby('k')}; self.byb = {k: g for k, g in r.groupby('b')}
        self.places = None
        if places_zip:
            p = gpd.read_file(places_zip, columns=['NAME', 'CLASSFP']).to_crs(2229); self.places = {n.lower(): g.geometry.union_all() for n, g in p.groupby('NAME')}
            self.incorp = p[p.CLASSFP.str.startswith('C')].geometry.union_all()

    def lines(self, name, area=None):
        k = norm(name); g = self.by.get(k)
        if g is None: g = self.byb.get(base(k))          # suffix missing or different (Alta vs Alta Ave)
        if g is None: return None
        if area is not None: g = g[g.intersects(area)]
        return None if g.empty else g.geometry.union_all()

    def area(self, city, pad_ft=1500):
        if not city or not self.places: return None
        a = self.places.get(city.lower()); return a.buffer(pad_ft) if a is not None else None

    def corner(self, a, b, near=None):
        """points where line sets a and b meet (or come within 60 ft)"""
        x = a.intersection(b); pts = [g for g in getattr(x, 'geoms', [x]) if g.geom_type == 'Point'] if not x.is_empty else []
        if not pts:
            pa, pb = nearest_points(a, b)
            if pa.distance(pb) < 60: pts = [Point((pa.x + pb.x) / 2, (pa.y + pb.y) / 2)]
        return pts

    def segment(self, street, frm, to, city=None, prefer_uninc=False):
        """-> dict(line, mid, how) in WGS84, or None. how: 'both' (two limits found), 'one' (one limit found)"""
        self._uninc = prefer_uninc
        g = self._segment(street, frm, to, self.area(city))
        if (g is None or g['how'] != 'both') and city:            # street may sit just outside the city line
            g2 = self._segment(street, frm, to, None)
            if g2 and (g is None or g2['how'] == 'both'): g = g2
        return g

    def _segment(self, street, frm, to, ar):
        s = self.lines(street, ar)
        if s is None: return None
        c1 = self.corner(s, self.lines(frm, ar)) if frm and self.lines(frm, ar) is not None else []
        c2 = self.corner(s, self.lines(to, ar)) if to and self.lines(to, ar) is not None else []
        best = None
        for p in c1:
            for q in c2:
                d = p.distance(q)
                if 30 < d < 30000 and (best is None or d < best[0]): best = (d, p, q)
        if best:
            _, p, q = best; geom = self._along(s, p, q); how = 'both'
        elif c1 or c2:
            cs = c1 or c2
            if getattr(self, '_uninc', False) and getattr(self, 'incorp', None) is not None:
                cs = sorted(cs, key=lambda p: self.incorp.contains(p))
            p = cs[0]; geom = Point(p); how = 'one'
        else: return None
        mid = geom.interpolate(0.5, normalized=True) if geom.geom_type == 'LineString' else geom
        to84 = lambda g: gpd.GeoSeries([g], crs=2229).to_crs(4326).iloc[0]
        return {'line': to84(geom) if geom.geom_type == 'LineString' else None, 'mid': to84(mid), 'how': how}

    def _along(self, s, p, q):
        box = LineString([p, q]).buffer(max(p.distance(q) * 0.25, 300))
        part = s.intersection(box); m = linemerge(part) if part.geom_type == 'MultiLineString' else part
        cand = [g for g in getattr(m, 'geoms', [m]) if g.geom_type == 'LineString']
        cand = [g for g in cand if g.distance(p) < 80 and g.distance(q) < 80]
        if cand:
            g = min(cand, key=lambda g: g.length); a, b = sorted((g.project(p), g.project(q)))
            sub = substring(g, a, b)
            if sub.geom_type == 'LineString' and sub.length > 20: return sub
        return LineString([p, q])
