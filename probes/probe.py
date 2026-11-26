import json, urllib.request, collections
UA={'User-Agent':'fp-sign-inventory/1.0'}
def get(u):
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=60); return r.status, r.read()
    except Exception as e: return str(e)[:120], b''
areas={'hds':(34.0828,-118.1857,900),'culver':(34.0225,-118.3960,450)}
for k,(la,lo,rad) in areas.items():
    for u in [f'https://api.openstreetcam.org/2.0/photo/?lat={la}&lng={lo}&radius={rad}&itemsPerPage=1000',
              f'https://api.openstreetcam.org/2.0/sequence/?lat={la}&lng={lo}&radius={rad}&itemsPerPage=100']:
        st,b=get(u)
        try:
            d=json.loads(b); r=d.get('result',{}).get('data',[])
            yrs=collections.Counter(str(x.get('shotDate') or x.get('dateAdded') or '')[:4] for x in r)
            print(k,u.split('?')[0].split('/')[-2],st,len(r),dict(yrs),json.dumps(r[0])[:600] if r else '')
        except Exception as e: print(k,u,st,str(e)[:100],b[:200])
