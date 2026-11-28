"""Per-layer steps that a field map alone can't do. Each hook takes (layer spec, features, source info) and returns
features in the record format: GeoJSON features whose properties carry the layer's fields plus 'date' (YYYY or
YYYY-MM-DD) and 'src_id'. A layer with no 'fetch' builds its features here from scratch.
"""
import os, re, json, glob, datetime, io
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TIGER = os.environ.get('TIGER_DIR', '/tmp/in')
H = {'User-Agent': 'Mozilla/5.0 (fp-sign-inventory data build)'}
_streets = None
NOTES = {}

def streets():
    global _streets
    if _streets is None:
        from geo.streets import Streets
        _streets = Streets(f'{TIGER}/tl_2025_06037_roads.zip', f'{TIGER}/tl_2025_06_place.zip')
    return _streets

def num(v):
    try: return int(float(str(v).replace(',', '')))
    except: return None

def place(seg, keep_line):
    if keep_line and seg.get('line') is not None: g = seg['line']
    else: g = seg['mid']
    return json.loads(json.dumps(g.__geo_interface__))

# ---------- volumes ----------
def caltrans_aadt(L, feats, info):
    for f in feats:
        p = f['properties']
        for k in ('aadt_back', 'aadt_ahead', 'peak_hour_back', 'peak_hour_ahead', 'peak_month_back', 'peak_month_ahead'): p[k] = num(p.get(k))
        p['aadt'] = max([v for v in (p['aadt_back'], p['aadt_ahead']) if v] or [None]) if (p['aadt_back'] or p['aadt_ahead']) else None
        p['peak_hour'] = ' / '.join(f'{v:,}' if v else '-' for v in (p['peak_hour_back'], p['peak_hour_ahead']))
        p['peak_month'] = ' / '.join(f'{v:,}' if v else '-' for v in (p['peak_month_back'], p['peak_month_ahead']))
        p['src_id'] = f"{p.get('route')}-{p.get('pm')}"
    return [f for f in feats if f['properties'].get('aadt')]

CUT = re.compile(r'\s+(?:(N|S|E|W)/O|(N|S|E|W)\.?\s*OF|AT|@|&|AND|BET(?:WEEN)?|BTWN|B/W|BTW|/)\s+', re.I)

def lacounty_adt(L, feats, info):
    """The county table has no map location: STREETS holds text such as 'MAIN ST N/O 1ST ST'. Each count is placed at
    the named corner, moved 150 ft in the direction given (N/O = north of); counts that don't match are listed, not guessed."""
    fields = info.get('fields') or []
    pick = lambda *pats: next((f for p in pats for f in fields if re.search(p, f, re.I)), None)
    fa = pick(r'total.?vol', r'^adt$', r'adt', r'volume'); fd = pick(r'count.?date', r'date'); fs = pick(r'^streets?$', r'street', r'location'); fw = pick(r'day.?of.?week', r'^day')
    S = streets(); out = []; miss = []; samples = []
    from layers import iso
    for i, f in enumerate(feats):
        r = f['properties'] or {}; txt = str(r.get(fs) or '').strip(); d = iso(r.get(fd)) if fd else None
        if len(samples) < 25: samples.append(txt)
        geom = f.get('geometry'); how = 'agency location'
        if not geom or not geom.get('coordinates'):
            pt, how = place_text(S, txt)
            if pt is None: miss.append(txt); continue
            geom = {'type': 'Point', 'coordinates': [round(pt[0], 6), round(pt[1], 6)]}
        dow = str(r.get(fw) or '').strip()
        if not dow and d and len(d) == 10: dow = datetime.date.fromisoformat(d).strftime('%A')
        wk = 'Weekend' if dow[:3].lower() in ('sat', 'sun') else 'Weekday' if dow else None
        p = {'adt': num(r.get(fa)), 'street': txt.split('  ')[0], 'location': txt, 'day': dow.title() or None, 'daytype': wk, 'how': how, 'date': d, 'src_id': r.get(info.get('oid') or 'OBJECTID', i)}
        if p['adt']: out.append({'type': 'Feature', 'geometry': geom, 'properties': p})
    NOTES['lacounty_adt'] = {'field_map': {'adt': fa, 'date': fd, 'location': fs, 'day': fw}, 'samples': samples, 'not_located': len(miss), 'not_located_examples': miss[:40]}
    return out

def place_text(S, txt):
    parts = CUT.split(txt)                       # [street, dir, dir, cross, (dir, dir, cross2)]
    if len(parts) < 4: return None, None
    a, mark, b = parts[0], (parts[1] or parts[2] or '').upper(), parts[3]
    if len(parts) >= 7 and not mark: seg = S.segment(a, b, parts[6], prefer_uninc=True); how = 'between the named streets'
    else: seg = S.segment(a, b, None, prefer_uninc=True); how = 'at the named corner' + (f', moved 150 ft {mark}' if mark else '')
    if not seg: return None, None
    x, y = seg['mid'].x, seg['mid'].y
    if mark in ('N', 'S', 'E', 'W'):
        dx, dy = {'N': (0, 1), 'S': (0, -1), 'E': (1, 0), 'W': (-1, 0)}[mark]; x += dx * 150 / 302000; y += dy * 150 / 364000
    return (x, y), how

def lacounty_adt_notes(): return NOTES.get('lacounty_adt', {})

# ---------- parking ----------
def ladot_meters(L, rows, info):
    from layers import iso
    d = iso(info.get('last_edit'), 'epoch_ms'); out = []
    for r in rows:
        ll = r.get('latlng') or {}
        try: x, y = float(ll['longitude']), float(ll['latitude'])
        except: continue
        out.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [x, y]},
                    'properties': {'space': r.get('spaceid'), 'blockface': r.get('blockface'), 'metertype': r.get('metertype'), 'ratetype': r.get('ratetype'),
                                   'rate': r.get('raterange'), 'timelimit': r.get('timelimit'), 'date': d, 'src_id': r.get('spaceid')}})
    return out

# ---------- walk and bike ----------
WB = [(2021, '9tzi-nz7g'), (2023, '6ux4-qj74'), (2025, 'hiwe-xzrt')]

def ladot_walkbike(L, feats, info):
    S = streets(); out = []; miss = []
    for year, ds in WB:
        rows = requests.get(f'https://data.lacity.org/resource/{ds}.json', params={'$limit': 5000}, headers=H, timeout=120).json()
        for r in rows:
            g = lambda *ks: next((r[k] for k in ks if r.get(k) not in (None, '')), None)
            seg = S.segment(r.get('street_name'), r.get('limit_1'), r.get('limit_2'), 'Los Angeles')
            if not seg: miss.append(f"{year} {r.get('street_name')} ({r.get('limit_1')} / {r.get('limit_2')})"); continue
            pw, pe = num(g('ped_weekday', 'ped_weekday_total')), num(g('ped_weekend', 'ped_weekend_total'))
            bw, be = num(g('bike_weekday', 'bike_weekday_total')), num(g('bike_weekend', 'bike_weekend_total'))
            sw, se = num(g('scooter_weekday_total')), num(g('scooter_weekend_total'))
            tot = num(g('all_total')) or sum(v or 0 for v in (num(g('ped_total')), num(g('bike_total')), num(g('scooter_total')), num(g('other_total'))))
            out.append({'type': 'Feature', 'geometry': place(seg, False), 'properties': {
                'street': r.get('street_name'), 'from': r.get('limit_1'), 'to': r.get('limit_2'), 'facility': r.get('facility_type'),
                'ped_weekday': pw, 'ped_weekend': pe, 'bike_weekday': bw, 'bike_weekend': be,
                'scooter': f"{sw if sw is not None else '-'} / {se if se is not None else '-'}", 'total': tot,
                'how': {'both': 'both limits found', 'one': 'one limit found, approximate'}[seg['how']],
                'date': str(year), 'src_id': f"{year}-{g('index', '_2021_index') or len(out)}"}})
    NOTES['ladot_walkbike'] = {'not_located': miss}
    return out

def ladot_walkbike_notes(): return NOTES.get('ladot_walkbike', {})

# ---------- speed surveys ----------
def speed_surveys(L, feats, info):
    """Reports listed in data/sources/speed_surveys.json, plus PDFs dropped in inputs/speed-surveys/
    (file name YYYY_City_anything.pdf). Each PDF is read with sources/speed_pdf.py."""
    from sources.speed_pdf import read
    reps = json.load(open(os.path.join(ROOT, 'data/sources/speed_surveys.json')))['reports']
    for p in sorted(glob.glob(os.path.join(ROOT, 'inputs/speed-surveys/*.pdf'))):
        m = re.match(r'(\d{4})_([^_]+)', os.path.basename(p))
        if m: reps.append({'city': m.group(2).replace('-', ' '), 'year': int(m.group(1)), 'title': os.path.basename(p), 'file': p})
    for p in sorted(glob.glob(os.path.join(ROOT, 'inputs/speed-surveys/*.csv'))):
        meta = dict(re.match(r'#\s*(\w+):\s*(.*)', l).groups() for l in open(p) if re.match(r'#\s*\w+:', l))
        reps.append({'city': meta.get('city'), 'year': int(meta.get('year', 0)), 'title': meta.get('title'), 'url': meta.get('source'), 'csv': p, 'method': meta.get('method')})
    S = streets(); out = []; status = []
    for rep in reps:
        st = {'city': rep['city'], 'year': rep['year'], 'title': rep.get('title'), 'url': rep.get('url')}
        try:
            path = rep.get('file')
            if rep.get('csv'):
                import csv
                rows = []
                for r in csv.DictReader(l for l in open(rep['csv']) if not l.startswith('#')):
                    v = lambda k: float(r[k]) if r.get(k) not in (None, '') else None
                    adt = num(r.get('total_volume') or r.get('adt')) or max([num(r.get(k)) or 0 for k in ('nb_eb_daily', 'sb_wb_daily')]) or None
                    rows.append({'street': r['street'], 'from': r['from'], 'to': r['to'], 'p85': v('p85'), 'p50': v('p50'), 'posted': v('posted'), 'adt': adt, 'page': 'table'})
                path = None
            elif not path:
                r = requests.get(rep['url'], headers=H, timeout=180)
                if r.status_code != 200 or not r.content.startswith(b'%PDF'): raise RuntimeError(f'download refused ({r.status_code}); put the PDF in inputs/speed-surveys/')
                path = f"/tmp/ets_{rep['year']}_{re.sub(r'[^a-z]', '', rep['city'].lower())}.pdf"; open(path, 'wb').write(r.content)
            if path: rows = read(path)
            found = 0
            for i, x in enumerate(rows):
                seg = S.segment(x['street'], x['from'], x['to'], rep['city'])
                if not seg: continue
                found += 1
                out.append({'type': 'Feature', 'geometry': place(seg, True), 'properties': dict(
                    {k: x.get(k) for k in ('street', 'from', 'to', 'p85', 'p50', 'posted', 'adt', 'page')},
                    report=f"{rep['city']} {rep['year']}", city=rep['city'], method=rep.get('method') or 'read from the PDF table', how={'both': 'both limits found', 'one': 'one limit found, approximate'}[seg['how']],
                    date=str(rep['year']), src_id=f"{rep['city']}-{rep['year']}-{i}")})
            st.update(rows=len(rows), located=found)
        except Exception as e: st['error'] = str(e)[:200]
        status.append(st)
    NOTES['speed_surveys'] = {'reports': status}
    return out

def speed_surveys_notes(): return NOTES.get('speed_surveys', {})

# ---------- LADOT counts on NavigateLA (TMC, 24-hour volumes, speed studies) ----------
_nla = None
WEEKEND = ('sat', 'sun')

def _navigatela(info_feats):
    global _nla
    if _nla is None:
        from sources import navigatela
        from layers import arcgis, REG
        feats, _ = arcgis({'url': 'https://maps.lacity.org/lahub/rest/services/LADOT/MapServer/21', 'where': '1=1'})
        pts = []
        for f in feats:
            p = f['properties']; g = f.get('geometry') or {}
            if p.get('TrafficID') and g.get('coordinates'): pts.append((int(p['TrafficID']), p.get('intersection'), *g['coordinates'][:2]))
        if os.environ.get('NLA_LIMIT'): pts = pts[:int(os.environ['NLA_LIMIT'])]       # local tests only
        _nla = navigatela.collect(pts, REG['since'])
        NOTES['navigatela'] = _nla[1]
    return _nla

def _nla_layer(kind, build):
    files, stats = _navigatela(None); out = []
    for url, ((tid, inter, x, y), d, rec) in files.items():
        if f'/{ {"tmc": "manual_counts", "adt": "automatic_counts", "speed": "survey_data"}[kind]}/' not in url or not rec or 'error' in rec: continue
        p = build(rec); p.update({'intersection': inter, 'pdf': url, 'date': d, 'src_id': url.rsplit('/', 1)[-1]})
        day = str(rec.get('day') or datetime.date.fromisoformat(d).strftime('%a')).lower()
        p['daytype'] = 'Weekend' if day[:3] in WEEKEND else 'Weekday'
        out.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [x, y]}, 'properties': p})
    return out

def _peaks(r, fmt=lambda h: h):
    c = lambda v: f'{v:,}' if isinstance(v, int) else '-'
    out = {}
    for k in ('am', 'pm'):
        if r.get(k + '_peak_hour'): out[k + '_peak'] = f"{fmt(r[k + '_peak_hour'])}, {c(r.get(k + '_peak_vol'))} vehicles"
    return out
def _hr(h):                                    # '15-16' or '3-4' (PM) -> '3-4 PM'
    a, b = (int(x) for x in h.split('-')); pm = a >= 12 or 1 <= a <= 5
    a, b = (a - 12 if a > 12 else a), (b - 12 if b > 12 else b)
    return f'{a}-{b} {"PM" if pm else "AM"}'
def lacity_adt(L, feats, info):
    return _nla_layer('adt', lambda r: dict(r, dirs=' / '.join(f'{v:,}' if isinstance(v, int) else '-' for v in (r.get('vol_nb_wb'), r.get('vol_sb_eb'))), **_peaks(r)))
def lacity_tmc(L, feats, info): return _nla_layer('tmc', lambda r: dict(r, **_peaks(r, _hr)))
def lacity_speeds(L, feats, info): return _nla_layer('speed', lambda r: dict(r))
def lacity_adt_notes(): return {'navigatela': NOTES.get('navigatela')}
lacity_tmc_notes = lacity_speeds_notes = lacity_adt_notes

# ---------- intersection control from OpenStreetMap ----------
OSM_Q = '[out:json][timeout:300];(node["highway"~"^(traffic_signals|stop|give_way|mini_roundabout)$"](33.70,-118.95,34.82,-117.65);node["crossing"="traffic_signals"](33.70,-118.95,34.82,-117.65););out body;'
MIRRORS = ['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']

def osm_control(L, feats, info):
    d = None
    for m in MIRRORS * 2:
        try:
            r = requests.post(m, data={'data': OSM_Q}, headers=H, timeout=400)
            if r.status_code == 200: d = r.json(); break
        except Exception: pass
    if d is None: raise RuntimeError('Overpass did not answer')
    stamp = (d.get('osm3s') or {}).get('timestamp_osm_base', '')[:10]; out = []
    for e in d.get('elements', []):
        t = e.get('tags', {}); h = t.get('highway')
        if h == 'traffic_signals' or t.get('crossing') == 'traffic_signals':
            kind = 'Signal' if h == 'traffic_signals' and t.get('traffic_signals') not in ('crossing', 'pedestrian_crossing') and t.get('crossing') != 'traffic_signals' else 'Pedestrian signal'
            if t.get('traffic_signals') in ('emergency', 'blinker'): kind = 'Flashing or emergency signal'
        elif h == 'stop': kind = 'All-way stop' if t.get('stop') == 'all' else 'Stop'
        elif h == 'give_way': kind = 'Yield'
        elif h == 'mini_roundabout': kind = 'Mini roundabout'
        else: continue
        out.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [e['lon'], e['lat']]},
                    'properties': {'control': kind, 'osm_id': e['id'], 'direction': t.get('direction'), 'date': stamp, 'src_id': e['id']}})
    return out

# ---------- transit (GTFS feeds of every operator in the county) ----------
_gtfs = None
CATALOG = 'https://share.mobilitydata.org/catalogs-csv'
BOX = (-118.95, 33.70, -117.65, 34.82)
MODE = {0: 'Light rail', 1: 'Subway', 2: 'Commuter rail', 3: 'Bus', 4: 'Ferry', 5: 'Cable car', 11: 'Trolleybus', 700: 'Bus', 702: 'Express bus', 900: 'Light rail'}

def _transit():
    global _gtfs
    if _gtfs is not None: return _gtfs
    import csv, zipfile, collections
    rows = list(csv.DictReader(io.StringIO(requests.get(CATALOG, headers=H, timeout=120).text)))
    def inbox(x):
        try: return float(x['location.bounding_box.minimum_longitude']) < BOX[2] and float(x['location.bounding_box.maximum_longitude']) > BOX[0] and \
                    float(x['location.bounding_box.minimum_latitude']) < BOX[3] and float(x['location.bounding_box.maximum_latitude']) > BOX[1]
        except Exception: return False
    feeds = [x for x in rows if x.get('data_type') == 'gtfs' and x.get('location.subdivision_name') == 'California' and x.get('status', '') in ('', 'active')
             and not x.get('redirect.id') and x.get('urls.direct_download') and inbox(x) and x.get('urls.authentication_type', '') in ('', '0')]
    routes, stops, status = [], [], []
    inb = lambda lon, lat: BOX[0] < lon < BOX[2] and BOX[1] < lat < BOX[3]
    for fd in feeds:
        name = fd['provider']; url = fd.get('urls.latest') or fd['urls.direct_download']; st = {'operator': name, 'url': fd['urls.direct_download']}
        try:
            r = requests.get(url, headers=H, timeout=180)
            if r.status_code != 200 and url != fd['urls.direct_download']: r = requests.get(fd['urls.direct_download'], headers=H, timeout=180)
            z = zipfile.ZipFile(io.BytesIO(r.content)); names = {n.rsplit('/', 1)[-1]: n for n in z.namelist()}
            rd = lambda f: list(csv.DictReader(io.TextIOWrapper(z.open(names[f]), 'utf-8-sig'))) if f in names else []
            ag = {a.get('agency_id', ''): a.get('agency_name') for a in rd('agency.txt')}
            rt = {x['route_id']: x for x in rd('routes.txt')}
            cal = [c.get('end_date', '') for c in rd('calendar.txt')] + [c.get('date', '') for c in rd('calendar_dates.txt')]
            end = max([c for c in cal if c] or [''])
            shp = collections.defaultdict(list)
            for s in rd('shapes.txt'): shp[s['shape_id']].append((int(float(s['shape_pt_sequence'])), float(s['shape_pt_lon']), float(s['shape_pt_lat'])))
            best = {}
            for t in rd('trips.txt'):
                sid = t.get('shape_id'); k = (t['route_id'], t.get('direction_id', ''))
                if sid in shp and (k not in best or len(shp[sid]) > len(shp[best[k]])): best[k] = sid
            if not best:                                  # feeds without shapes: draw each route through its stops in order
                sxy = {x['stop_id']: (float(x['stop_lon']), float(x['stop_lat'])) for x in rd('stops.txt') if x.get('stop_lon')}
                trip = {}
                for t in rd('trips.txt'): trip.setdefault((t['route_id'], t.get('direction_id', '')), t['trip_id'])
                want = set(trip.values()); seq = collections.defaultdict(list)
                for x in rd('stop_times.txt'):
                    if x['trip_id'] in want: seq[x['trip_id']].append((int(x['stop_sequence']), x['stop_id']))
                for k, tid in trip.items():
                    pts = [sxy[sid] for _, sid in sorted(seq[tid]) if sid in sxy]
                    if len(pts) > 1: shp['_' + tid] = [(i, x, y) for i, (x, y) in enumerate(pts)]; best[k] = '_' + tid
                st['note'] = 'no route shapes in feed; drawn stop to stop'
            n = 0
            for (rid, dr), sid in best.items():
                pts = [(x, y) for _, x, y in sorted(shp[sid])]
                if not any(inb(x, y) for x, y in pts[::10] + pts[-1:]): continue
                rr = rt.get(rid, {}); col = rr.get('route_color') or ''
                routes.append({'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': [[round(x, 6), round(y, 6)] for x, y in pts]}, 'properties': {
                    'route': rr.get('route_short_name') or rr.get('route_long_name') or rid, 'name': rr.get('route_long_name') or '', 'operator': ag.get(rr.get('agency_id', ''), name) or name,
                    'mode': MODE.get(int(rr.get('route_type') or 3), 'Bus'), 'color': '#' + col if re.fullmatch(r'[0-9A-Fa-f]{6}', col) else None,
                    'service_to': f'{end[:4]}-{end[4:6]}-{end[6:8]}' if len(end) == 8 else None, 'src_id': f'{name}:{rid}:{dr}'}}); n += 1
            m = 0
            for s in rd('stops.txt'):
                try: x, y = float(s['stop_lon']), float(s['stop_lat'])
                except Exception: continue
                if s.get('location_type', '0') not in ('', '0') or not inb(x, y): continue
                stops.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [round(x, 6), round(y, 6)]},
                              'properties': {'stop': s.get('stop_name'), 'code': s.get('stop_code'), 'operator': name, 'src_id': f"{name}:{s['stop_id']}"}}); m += 1
            st.update(routes=n, stops=m, service_to=end)
        except Exception as e: st['error'] = f'{type(e).__name__}: {e}'[:160]
        status.append(st)
    today = datetime.date.today().isoformat()
    for f in routes + stops: f['properties']['date'] = today
    _gtfs = (routes, stops); NOTES['transit'] = {'feeds': status}
    return _gtfs

def transit_routes(L, feats, info): return _transit()[0]
def transit_stops(L, feats, info): return _transit()[1]
def transit_routes_notes(): return NOTES.get('transit', {})
transit_stops_notes = transit_routes_notes

# ---------- LADOT stop and yield signs (intersection control) ----------
def ladot_stop_yield(L, feats, info):
    for f in feats:
        p = f['properties']; t = str(p.pop('tooltip', '') or '').replace('\\n', '\n')
        g = lambda k: (re.search(k + r':\s*(.+)', t) or [None, None])[1]
        p['control'] = {1: 'Stop', 2: 'Yield'}.get(num(p.get('sign_type')), 'Stop or yield')
        p['faces'] = g('Faces Traffic Going'); p['street'] = g('Primary Street'); p['cross'] = g('Cross Street'); p['src_id'] = p.get('oid')
    return feats

def ladot_signals(L, feats, info):
    for f in feats:
        p = f['properties']; p['name'] = ' / '.join(x for x in (p.get('st1'), p.get('st2'), p.get('st3')) if x); p['src_id'] = p.get('sid')
    return feats
