"""LADOT count reports published on NavigateLA, read into three layers.

Each LADOT Traffic Data location (lahub LADOT MapServer layer 21) has a report page listing count PDFs:
  manual_counts/    turning movement counts (TMC), 7-10 AM and 3-6 PM
  automatic_counts/ 24-hour directional volume counts
  survey_data/      24-hour speed and volume studies, one lane and direction per file (85th percentile)
The count date is in the file name (YYMMDD). Files dated before the limit are not downloaded. Parsed files are
cached in data/cache/navigatela.json so a nightly run only reads new files; report pages are re-read in sevenths.
"""
import os, re, json, io, datetime, concurrent.futures as cf
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, 'data/cache/navigatela.json')
PAGE = 'https://navigatela.lacity.org/navigatela/reports/dot_traffic_data_report.cfm?trafficid={}'
H = {'User-Agent': 'Mozilla/5.0 (fp-sign-inventory data build)'}
PARSER_V = 2      # bump when a parser changes; files read by an older parser are read again
KIND = {'manual_counts': 'tmc', 'automatic_counts': 'adt', 'survey_data': 'speed'}

def file_date(url):
    """YYMMDD in the file name -> ISO date, or None"""
    for m in re.finditer(r'(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)', url.rsplit('/', 1)[-1]):
        y, mo, d = 2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31 and y <= datetime.date.today().year:
            try: return datetime.date(y, mo, d).isoformat()
            except ValueError: pass
    return None

N = lambda s: int(str(s).replace(',', '').replace(' ', '')) if s not in (None, '') else None

def parse_adt(t):
    g = lambda p: (re.search(p, t) or [None, None])[1]
    tot = re.search(r'24 HOUR VEHICLES TOTAL\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)', t)
    if not tot: return parse_adt_nds(t)
    r = {'location': g(r'Location\s+(.+?)\s+Day of Week'), 'day': g(r'Day of Week\s+(\w+)'), 'direction': g(r'Direction\s+(.+?)\s+DOT'),
         'vol_nb_wb': N(tot[1]), 'vol_sb_eb': N(tot[2]), 'adt': N(tot[3])}
    for k, lab in (('am', 'First'), ('pm', 'Last')):
        m = re.search(lab + r' 12H Peak\s+(\d+ [AP]M|\d+ NN)\s+[\d ,]+?\s+(\d+ [AP]M|\d+ NN)\s+[\d ,]+?\s+(\d+ [AP]M|\d+ NN)\s+([\d ,]+)$', t, re.M)
        if m: r[k + '_peak_hour'], r[k + '_peak_vol'] = m[3], N(m[4])
    return r

ROW = re.compile(r'^(\d{1,2}-\d{1,2})\s+(\d+) (\d+) (\d+) (\d+)\s+\S+\s+(\d+) (\d+) (\d+) (\d+)\s+(\d+)\s+(\d+) (\d+) (\d+) (\d+)', re.M)
TOT = re.compile(r'^TOTAL\s+(\d+) (\d+) (\d+) (\d+)\s+TOTAL\s+(\d+) (\d+) (\d+) (\d+)\s+(\d+)\s+(\d+) (\d+) (\d+) (\d+)', re.M)

def parse_tmc_nds(t):
    """consultant (NDS) turning movement report: one page per period, movements SB WB NB EB as R T L"""
    pages = re.split(r'Turning Movement Count Report', t)[1:]
    if not pages: return None
    g = lambda p: (re.search(p, t) or [None, None])[1]
    app = {k: [0, 0, 0] for k in ('sb', 'wb', 'nb', 'eb')}; total = 0; out = {}
    for pg in pages:
        per = pg.strip().split('\n')[0].strip().upper()
        tv = re.search(r'Total Volume:\s+((?:\d+\s+){12}\d+)', pg)
        if not tv: continue
        v = list(map(int, tv[1].split())); total += v[12]
        for i, k in enumerate(('sb', 'wb', 'nb', 'eb')):
            r_, t_, l_ = v[i * 3:i * 3 + 3]; app[k][0] += l_; app[k][1] += t_; app[k][2] += r_
        pk = re.search(r'Peak Hr Begin:\s*(\d{1,2}:\d{2})', pg); phv = re.search(r'PHV\s+((?:\d+\s+){12}\d+)', pg)
        k = 'am' if per.startswith('AM') else 'pm' if per.startswith('PM') else None
        if k and pk and phv:
            hh, mm = map(int, pk[1].split(':')); out[k + '_peak_hour'] = f"{hh - 12 if hh > 12 else hh}:{mm:02d} {'AM' if hh < 12 else 'PM'}"; out[k + '_peak_vol'] = int(phv[1].split()[-1])
    if not total: return None
    out.update({'ns_street': g(r'North/South:\s*(.+?)\s+Date:'), 'ew_street': g(r'East/West:\s*(.+?)\s+City:'), 'day': None, 'hours': 'count periods in the report',
                'total': total, 'peds': None, 'bikes': None, **{k: '/'.join(map(str, v)) for k, v in app.items()}})
    return out

def parse_adt_nds(t):
    m = re.search(r'DAILY TOTALS\s+DAILY TOTALS\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)', t)
    if not m: return None
    nb, sb, eb, wb, tot = (N(x) for x in m.groups()); lines = t.split('\n')
    loc = next((l.strip() for l in lines[1:5] if re.search(r'\b(S/O|N/O|E/O|W/O|at|AT|BTWN|bet)\b', l)), None)
    return {'location': loc, 'day': (re.search(r'Day:\s*(\w+)', t) or [None, None])[1], 'direction': 'N/S STREET' if nb or sb else 'E/W STREET',
            'vol_nb_wb': nb or wb, 'vol_sb_eb': sb or eb, 'adt': tot}

def parse_tmc(t):
    rows, tots = ROW.findall(t), TOT.findall(t)
    if len(tots) < 2 or len(rows) < 2: return parse_tmc_nds(t)
    half = len(rows) // 2; ns, ew = rows[:half], rows[half:]
    hours = {}
    for blk in (ns, ew):
        for r in blk: hours[r[0]] = hours.get(r[0], 0) + int(r[9])
    am = {h: v for h, v in hours.items() if int(h.split('-')[0]) in (6, 7, 8, 9)}
    pm = {h: v for h, v in hours.items() if int(h.split('-')[0]) not in (6, 7, 8, 9)}
    a, b = tots[0], tots[1]
    g = lambda p: (re.search(p, t) or [None, None])[1]
    bikes = re.search(r'^BIKES\s+(\d+) (\d+) (\d+) (\d+)', t, re.M)
    hours_note = g(r'Hours:\s*(.+?)\s+(?:Staff|Chekrs)')
    return {'ns_street': g(r'North/South\s+(.+)'), 'ew_street': g(r'East/West\s+(.+)'), 'day': g(r'Day:\s*(\w+)'),
            'hours': hours_note or '7-10 AM and 3-6 PM',
            'nb': '/'.join(a[0:3]), 'sb': '/'.join(a[4:7]), 'eb': '/'.join(b[0:3]), 'wb': '/'.join(b[4:7]),
            'total': int(a[8]) + int(b[8]),
            'am_peak_hour': max(am, key=am.get) if am else None, 'am_peak_vol': max(am.values()) if am else None,
            'pm_peak_hour': max(pm, key=pm.get) if pm else None, 'pm_peak_vol': max(pm.values()) if pm else None,
            'peds': sum(int(x[9]) + int(x[11]) for x in (a, b)), 'bikes': sum(map(int, bikes.groups())) if bikes else None}

def parse_speed(t):
    p85 = re.search(r'85th percentile\s+was\s+([\d.]+)\s*MPH', t, re.I)
    if not p85: return None
    g = lambda p: (re.search(p, t, re.I) or [None, None])[1]
    ln = re.search(r'in the\s+(\w+)\s+Lane\s+(\d+)', t)
    return {'street': g(r'Street:\s*(.+)'), 'at': g(r'Location:\s*(.+)'), 'dir': ln[1] if ln else None, 'lane': ln[2] if ln else None,
            'p85': float(p85[1]), 'avg': N(g(r'average speed for all classif\w* vehicles was\s+(\d+)')), 'posted': N(g(r'posted speed of\s+(\d+)')),
            'volume': N(g(r'total recorded volume showed\s+([\d,]+)'))}

def read_pdf(url):
    import pdfplumber
    r = requests.get(url, headers=H, timeout=90)
    if r.status_code != 200 or not r.content.startswith(b'%PDF'): return {'error': f'http {r.status_code}'}
    with pdfplumber.open(io.BytesIO(r.content)) as pdf: t = '\n'.join((p.extract_text() or '') for p in pdf.pages[:6])
    kind = next((v for k, v in KIND.items() if f'/{k}/' in url), None)
    rec = {'tmc': parse_tmc, 'adt': parse_adt, 'speed': parse_speed}[kind](t) if kind else None
    return dict(rec or {'error': 'format not read'}, v=PARSER_V)

def collect(points, since):
    """points: [(trafficid, intersection, lon, lat)] -> {'files': {url: rec}, 'stats': {...}}"""
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {'pages': {}, 'files': {}}
    today = datetime.date.today(); slice_ = today.toordinal() % 7
    def page(tid):
        try:
            t = requests.get(PAGE.format(tid), headers=H, timeout=60).text
            return tid, sorted(set(re.findall(r'href="([^"]+\.pdf)"', t, re.I)))
        except Exception: return tid, None
    todo = [p[0] for p in points if str(p[0]) not in cache['pages'] or p[0] % 7 == slice_]
    with cf.ThreadPoolExecutor(8) as ex:
        for tid, links in ex.map(page, todo):
            if links is not None: cache['pages'][str(tid)] = links
    want = {}
    for p in points:
        for u in cache['pages'].get(str(p[0]), []):
            d = file_date(u)
            if d and d >= since and any(f'/{k}/' in u for k in KIND) and not re.search(r'PED|BIKE', u.rsplit('/', 1)[-1], re.I): want[u] = (p, d)
    new = [u for u in want if (cache['files'].get(u) or {}).get('v') != PARSER_V]
    with cf.ThreadPoolExecutor(8) as ex:
        for u, rec in zip(new, ex.map(read_pdf, new)):
            cache['files'][u] = rec
    json.dump(cache, open(CACHE, 'w'), separators=(',', ':'))
    links = [u for v in cache['pages'].values() for u in v]
    stats = {'locations': len(points), 'pages_read': len(todo), 'pdf_links': len(links),
             'undated_links': sum(1 for u in links if not file_date(u)), 'files_since_limit': len(want), 'new_files_read': len(new),
             'not_read': sum(1 for u in want if 'error' in (cache['files'].get(u) or {'error': 1}))}
    return {u: (want[u][0], want[u][1], cache['files'].get(u) or {}) for u in want}, stats
