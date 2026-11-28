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
