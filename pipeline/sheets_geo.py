import json,math,numpy as np,os,io,requests,cv2,time
TILEFAIL=[]
from concurrent.futures import ThreadPoolExecutor
LON0,LAT0=-118.1945,34.0780;K=math.cos(math.radians(34.083))*111320;KL=110540
def setup(bbox,scale=None):
    global LON0,LAT0,K,SCALE
    if scale: SCALE=scale
    LON0,LAT0=bbox[0],bbox[1];K=math.cos(math.radians((bbox[1]+bbox[3])/2))*111320
xy=lambda lo,la:((lo-LON0)*K,(la-LAT0)*KL)
ll=lambda x,y:(LON0+x/K,LAT0+y/KL)
FT=0.3048
SCALE=40  # 1 in = 40 ft
MAPW,MAPH=12.6,8.5  # inches
def centerline(O,name):
    pts=np.array([xy(p['lon'],p['lat']) for w in O if w['type']=='way' and w.get('tags',{}).get('name')==name for p in w['geometry']])
    m=pts.mean(0); _,_,V=np.linalg.svd(pts-m); u=V[0]; n=np.array([-u[1],u[0]])
    s=pts@u; o=pts@n; st=np.arange(s.min(),s.max()+1,20); cl=[]
    for v in st:
        k=np.abs(s-v)<30
        if k.sum(): cl.append(v*u+np.median(o[k])*n)
    cl=np.array(cl)
    # smooth
    from scipy.ndimage import uniform_filter1d
    return np.c_[uniform_filter1d(cl[:,0],5,mode='nearest'),uniform_filter1d(cl[:,1],5,mode='nearest')]
def frames(cl,S):
    W=MAPW*SCALE*FT; H=MAPH*SCALE*FT
    seg=np.r_[0,np.cumsum(np.linalg.norm(np.diff(cl,axis=0),axis=1))]; L=seg[-1]
    step=W-25; n=int(math.ceil((L-0)/step)); out=[]
    for i in range(n):
        a=i*step; b=min(a+W,L); m=(a+b)/2
        p0=np.array([np.interp(a,seg,cl[:,0]),np.interp(a,seg,cl[:,1])]); p1=np.array([np.interp(b,seg,cl[:,0]),np.interp(b,seg,cl[:,1])])
        c=np.array([np.interp(m,seg,cl[:,0]),np.interp(m,seg,cl[:,1])])
        ang=math.atan2(*(p1-p0)[::-1])
        out.append(dict(i=i,c=c.tolist(),ang=ang,W=W,H=H,s0=a,s1=b))
    return out
def merc(lon,lat,z):
    n=2**z*256; x=(lon+180)/360*n; y=(1-math.log(math.tan(math.radians(lat))+1/math.cos(math.radians(lat)))/math.pi)/2*n; return x,y
def tile(z,x,y):
    os.makedirs('tiles',exist_ok=True); f=f'tiles/{z}_{x}_{y}.jpg'
    if not os.path.exists(f):
        for t in range(3):
            try:
                r=requests.get(f'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',timeout=30,headers={'User-Agent':'Mozilla/5.0 (fp-sign-inventory)','Referer':'https://drzkid96.github.io/fp-sign-inventory/'})
                if r.status_code==200 and r.content[:2]==b'\xff\xd8': open(f,'wb').write(r.content); break
            except Exception: pass
            time.sleep(1+2*t)
    if not os.path.exists(f): TILEFAIL.append((z,x,y)); return np.full((256,256,3),200,np.uint8)
    return cv2.imread(f)
def world_to_page(fr,x,y):
    # page coords in inches within map box, origin bottom-left; map x axis = corridor direction
    c=np.array(fr['c']); a=fr['ang']; d=np.array([x,y])-c
    u=np.array([math.cos(a),math.sin(a)]); n=np.array([-math.sin(a),math.cos(a)])
    return (d@u)/(SCALE*FT)+MAPW/2,(d@n)/(SCALE*FT)+MAPH/2
def render(fr,dpi=150,z=19):
    TILEFAIL.clear(); Wp,Hp=int(MAPW*dpi),int(MAPH*dpi); c=np.array(fr['c']); a=fr['ang']
    u=np.array([math.cos(a),math.sin(a)]); n=np.array([-math.sin(a),math.cos(a)])
    jj,ii=np.meshgrid(np.arange(Wp),np.arange(Hp))
    X=c[0]+((jj+0.5)/dpi-MAPW/2)*SCALE*FT*u[0]+((Hp-ii-0.5)/dpi-MAPH/2)*SCALE*FT*n[0]
    Y=c[1]+((jj+0.5)/dpi-MAPW/2)*SCALE*FT*u[1]+((Hp-ii-0.5)/dpi-MAPH/2)*SCALE*FT*n[1]
    lon=LON0+X/K; lat=LAT0+Y/KL; N=2**z*256
    mx=(lon+180)/360*N; my=(1-np.log(np.tan(np.radians(lat))+1/np.cos(np.radians(lat)))/np.pi)/2*N
    tx0,tx1=int(mx.min()//256),int(mx.max()//256); ty0,ty1=int(my.min()//256),int(my.max()//256)
    mos=np.zeros(((ty1-ty0+1)*256,(tx1-tx0+1)*256,3),np.uint8)
    keys=[(x,y) for x in range(tx0,tx1+1) for y in range(ty0,ty1+1)]
    with ThreadPoolExecutor(8) as ex: ims=list(ex.map(lambda k:tile(z,*k),keys))
    for (x,y),im in zip(keys,ims): mos[(y-ty0)*256:(y-ty0+1)*256,(x-tx0)*256:(x-tx0+1)*256]=cv2.resize(im,(256,256))
    if len(TILEFAIL)>0.1*len(keys): raise SystemExit(f'aerial tiles failed ({len(TILEFAIL)} of {len(keys)}); rerun later')
    out=cv2.remap(mos,(mx-tx0*256).astype(np.float32),(my-ty0*256).astype(np.float32),cv2.INTER_LINEAR)
    return out
def frames_grid(S,bbox):
    # north-up sheets on a grid over the signs, for a neighborhood with no single corridor
    W=MAPW*SCALE*FT; H=MAPH*SCALE*FT; P=np.array([[s['x'],s['y']] for s in S]) if S else np.zeros((1,2))
    x0,y0=P.min(0)-15; x1,y1=P.max(0)+15; nx=max(1,int(math.ceil((x1-x0)/(W-20)))); ny=max(1,int(math.ceil((y1-y0)/(H-20))))
    ox=(x0+x1)/2-(nx*(W-20))/2; oy=(y0+y1)/2-(ny*(H-20))/2; out=[]
    for j in reversed(range(ny)):
        for i in range(nx):
            c=[ox+(i+0.5)*(W-20),oy+(j+0.5)*(H-20)]
            if any(abs(p[0]-c[0])<=(W-20)/2+0.01 and abs(p[1]-c[1])<=(H-20)/2+0.01 for p in P):
                out.append(dict(i=len(out),c=c,ang=0.0,W=W,H=H,s0=0,s1=0))
    return out
