"""Pull 85th percentile speeds out of an Engineering and Traffic Survey (E&TS) PDF.

usage: python pipeline/sources/speed_pdf.py report.pdf  -> prints rows as JSON lines

Reads every table on pages that mention the 85th percentile. A table counts when one header names the
85th percentile and another names the street. Header cells set the column spans; wrapped cells are joined
and continuation rows fold into the row above. Output fields: street, from, to, p85, p50, posted, adt, page.
"""
import re, sys, json
import pdfplumber

KEYS = [('p85', r'85'), ('p50', r'50\s*th|median'), ('posted', r'posted|existing|current'), ('rec', r'recommend|proposed'),
        ('adt', r'adt|volume|daily'), ('from', r'^from|limit.*from|beginning|^begin'), ('to', r'^to\b|limit.*to|^end'),
        ('street', r'street|roadway|road name|segment|name|location'), ('date', r'date')]
NUM = re.compile(r'(\d{2}(?:\.\d)?)')

def spans(head):
    """header rows -> [(start_col, end_col, label)]; values sit loosely under their header, so each column
    reaches halfway to the next header"""
    import math
    n = max(len(r) for r in head); lab = [' '.join(str(r[i] or '').strip() for r in head if i < len(r)).strip() for i in range(n)]
    starts = [i for i, t in enumerate(lab) if t]
    cut = [0] + [math.ceil((a + b) / 2) for a, b in zip(starts, starts[1:])] + [n]
    return [[cut[j], cut[j + 1], lab[i]] for j, i in enumerate(starts)]

def role(label):
    l = label.lower()
    for k, p in KEYS:
        if re.search(p, l): return k
    return None

def table_rows(t, page):
    if not t or len(t) < 3: return []
    for h in (1, 2, 3):                       # header may run over 1-3 rows
        sp = spans(t[:h]); roles = [role(s[2]) for s in sp]
        if 'p85' in roles and ('street' in roles or 'from' in roles): break
    else: return []
    rows = []
    for r in t[h:]:
        cell = lambda a, b: ' '.join(str(x).replace('\n', ' ').strip() for x in r[a:b] if x and str(x).strip())
        vals = {}
        for (a, b, _), k in zip(sp, roles):
            if k and k not in vals: vals[k] = cell(a, b)
        filled = sum(1 for v in vals.values() if v)
        if rows and (not vals.get('p85') or filled <= 2):          # wrapped text from the row above
            for k, v in vals.items():
                if v and k in ('street', 'from', 'to'): rows[-1][k] = (rows[-1].get(k, '') + ' ' + v).strip()
            continue
        if vals.get('p85'): rows.append(dict(vals, page=page))
    out = []
    for v in rows:
        m = NUM.findall(v['p85'])
        if not m: continue
        p85 = float(m[-1])
        if not 10 <= p85 <= 80: continue
        rec = {'street': v.get('street', ''), 'from': v.get('from', ''), 'to': v.get('to', ''), 'p85': p85, 'page': v['page']}
        for k in ('p50', 'posted', 'rec'):
            mm = NUM.findall(v.get(k, '') or '')
            if mm: rec[k] = float(mm[-1])
        a = re.findall(r'\d[\d,]{2,}', v.get('adt', '') or '')
        if a: rec['adt'] = int(a[-1].replace(',', ''))
        if v.get('date'): rec['date_text'] = v['date']
        out.append(rec)
    return out

def read(path):
    out = []
    with pdfplumber.open(path) as pdf:
        for i, p in enumerate(pdf.pages):
            t = p.extract_text() or ''
            if not re.search(r'85\s*(th|%|percentile)', t, re.I): continue
            for tb in p.extract_tables(): out += table_rows(tb, i + 1)
    seen, uniq = set(), []
    for r in out:
        k = (r['street'].lower(), r['from'].lower(), r['to'].lower(), r['p85'])
        if k not in seen: seen.add(k); uniq.append(r)
    return uniq

if __name__ == '__main__':
    for r in read(sys.argv[1]): print(json.dumps(r))
