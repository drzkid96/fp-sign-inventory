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

def lacounty_adt(L, feats, info):
    """Field names are read from the layer itself, since the county does not document them."""
    fields = info.get('fields') or []
    pick = lambda *pats: next((f for p in pats for f in fields if re.search(p, f, re.I)), None)
    fa = pick(r'^adt$', r'24.?h', r'adt', r'total.?vol', r'volume', r'^total$')
    fd = pick(r'count.?date', r'^date', r'date', r'year')
    fs = pick(r'^street', r'street.?name', r'road.?name', r'^road', r'primary', r'name')
    fx = pick(r'cross', r'limit', r'from', r'location', r'desc')
    fam = pick(r'^am', r'am.?peak'); fpm = pick(r'^pm', r'pm.?peak')
    NOTES['lacounty_adt'] = {'field_map': {'adt': fa, 'date': fd, 'street': fs, 'location': fx, 'am_peak': fam, 'pm_peak': fpm}}
    out = []
    for i, f in enumerate(feats):
        r = f['properties'] or {}
        from layers import iso
        d = iso(r.get(fd)) if fd else None
        p = {'adt': num(r.get(fa)) if fa else None, 'street': r.get(fs), 'location': r.get(fx), 'am_peak': num(r.get(fam)) if fam else None,
             'pm_peak': num(r.get(fpm)) if fpm else None, 'date': d, 'src_id': r.get(info.get('oid', 'OBJECTID'), i)}
        if d and len(d) == 10:
            p['daytype'] = 'Weekend' if datetime.date.fromisoformat(d).weekday() >= 5 else 'Weekday'
        if p['adt']: out.append({'type': 'Feature', 'geometry': f.get('geometry'), 'properties': p})
    return out

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
    S = streets(); out = []; status = []
    for rep in reps:
        st = {'city': rep['city'], 'year': rep['year'], 'title': rep.get('title'), 'url': rep.get('url')}
        try:
            path = rep.get('file')
            if not path:
                r = requests.get(rep['url'], headers=H, timeout=180)
                if r.status_code != 200 or not r.content.startswith(b'%PDF'): raise RuntimeError(f'download refused ({r.status_code}); put the PDF in inputs/speed-surveys/')
                path = f"/tmp/ets_{rep['year']}_{re.sub(r'[^a-z]', '', rep['city'].lower())}.pdf"; open(path, 'wb').write(r.content)
            rows = read(path); found = 0
            for i, x in enumerate(rows):
                seg = S.segment(x['street'], x['from'], x['to'], rep['city'])
                if not seg: continue
                found += 1
                out.append({'type': 'Feature', 'geometry': place(seg, True), 'properties': dict(
                    {k: x.get(k) for k in ('street', 'from', 'to', 'p85', 'p50', 'posted', 'adt', 'page')},
                    report=f"{rep['city']} {rep['year']}", city=rep['city'], how={'both': 'both limits found', 'one': 'one limit found, approximate'}[seg['how']],
                    date=str(rep['year']), src_id=f"{rep['city']}-{rep['year']}-{i}")})
            st.update(rows=len(rows), located=found)
        except Exception as e: st['error'] = str(e)[:200]
        status.append(st)
    NOTES['speed_surveys'] = {'reports': status}
    return out

def speed_surveys_notes(): return NOTES.get('speed_surveys', {})
