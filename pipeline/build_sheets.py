import json,math,numpy as np,cv2,os,sys,io,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import sheets_geo
REPO=os.environ['REPO'];AREA=os.environ['AREA'];sheets_geo.setup(json.loads(os.environ['BBOX']),int(os.environ.get('SCALE','40')));DATE=os.environ.get('DATE','')
from sheets_geo import *
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from scipy.spatial import cKDTree
FD=os.path.join(os.path.dirname(os.path.abspath(__file__)),'fonts')+'/'
for n,f in [('AS','Regular'),('ASM','Medium'),('ASS','SemiBold'),('ASB','Bold')]: pdfmetrics.registerFont(TTFont(n,FD+f'AlbertSans-{f}.ttf'))
SLATE=(0,0x24/255,0x2E/255);EMER=(0,0x57/255,0x4A/255);JADE=(0x1B/255,0x79/255,0x5A/255);ORG=(1,0x66/255,0x22/255);CREAM=(0xEE/255,0xED/255,0xE8/255);BAND=(0xF2/255,)*3
lib=json.load(open(REPO+'/data/library.json'));SPR=REPO+'/data/sprites/'
NC={'NC-PARK':'Parking sign (no standard code)','NC-WARN':'Warning sign (no standard code)','NC-ID':'Community ID sign (no standard code)'}
O=json.load(open('osm.json'))['elements'];G=json.load(open('frames.json'));F=G['frames'];cl=np.array(G['cl']).reshape(-1,2)
S=[s for s in json.load(open('signs3.json')) if s['code'] not in('STREET','GUIDE','X')]
A=json.load(open('all_images.json'))
# sheet assignment: the sheet whose map contains the sign (closest to its center), ids in sheet order
def inside(f,x,y):
    d=np.array([x,y])-np.array(f['c']); u=np.array([math.cos(f['ang']),math.sin(f['ang'])]); n=np.array([-u[1],u[0]])
    return max(abs(d@u)/(f['W']/2),abs(d@n)/(f['H']/2))
for s in S:
    best=min(F,key=lambda f:inside(f,s['x'],s['y'])); s['sheet']=best['i']
    d=np.array([s['x'],s['y']])-np.array(best['c']); u=np.array([math.cos(best['ang']),math.sin(best['ang'])]); s['sta']=float(d@u)
S.sort(key=lambda s:(s['sheet'],s['sta'],-s['y']))
for i,s in enumerate(S): s['id']=f'S-{i+1:03d}'
F=[f for f in F if any(s['sheet']==f['i'] for s in S)]
import intersections as IXM
_bb=json.loads(os.environ['BBOX']); _x1,_y1=xy(_bb[2],_bb[3])
IX=IXM.check(O,S,[xy(*a['computed_geometry']['coordinates']) for a in A],xy,(0,0,_x1,_y1))
json.dump(IX,open('intersections.json','w'))
for k,f in enumerate(F): f['n']=k+1
def speed_face(v):
    f=f'r2-1-{v}.png'
    if not os.path.exists(f):
        r=Image.open(SPR+'r2-1.webp').convert('RGBA');W_,H_=r.size;d=ImageDraw.Draw(r);d.rectangle((W_*0.12,H_*0.52,W_*0.88,H_*0.92),fill='white')
        d.text((W_/2,H_*0.72),v,font=ImageFont.truetype(FD+'AlbertSans-Bold.ttf',int(H_*0.4)),fill='black',anchor='mm');r.save(f)
    return f
def face_img(code):
    if code.startswith('R2-1/'): return speed_face(code.split('/')[1])
    if code=='R2-1': return SPR+'r2-1.webp'
    if code in NC: return None
    return SPR+lib[code]['s']+'.webp'
# R2-1 35 face
from PIL import Image,ImageDraw,ImageFont
r=Image.open(SPR+'r2-1.webp').convert('RGBA');W_,H_=r.size;d=ImageDraw.Draw(r);d.rectangle((W_*0.12,H_*0.52,W_*0.88,H_*0.92),fill='white')
d.text((W_/2,H_*0.72),'35',font=ImageFont.truetype(FD+'AlbertSans-Bold.ttf',int(H_*0.4)),fill='black',anchor='mm');r.save('r2-1-35.png')
IMGC={}
def ir(path):
    if path not in IMGC:
        im=Image.open(path).convert('RGBA'); bg=Image.new('RGBA',im.size,(255,255,255,0)); IMGC[path]=ImageReader(im)
    return IMGC[path]
def name(code): return NC.get(code) or ('Speed Limit' if code.startswith('R2-1') else None) or lib.get(code.split('/')[0],{}).get('n','') or code
def disp(code): return f"R2-1 ({code.split('/')[1]})" if code.startswith('R2-1/') else ('NO CODE' if code in NC else code)
# coverage (photos within 12 m)
Iall=cKDTree([xy(*a['computed_geometry']['coordinates']) for a in A])
nophoto=[]
for w in O:
    if w['type']!='way' or w.get('tags',{}).get('highway') in(None,'service','footway') or not w['tags'].get('name'): continue
    g=[np.array(xy(p['lon'],p['lat'])) for p in w['geometry']]
    for p,q in zip(g[:-1],g[1:]):
        L=np.linalg.norm(q-p); n=max(1,int(L//6))
        for t in range(n):
            a=p+(q-p)*t/n; b=p+(q-p)*(t+1)/n
            if not Iall.query_ball_point((a+b)/2,12): nophoto.append((a,b))
streets=[(w['tags']['name'],[np.array(xy(p['lon'],p['lat'])) for p in w['geometry']]) for w in O if w['type']=='way' and w.get('tags',{}).get('name') and w['tags'].get('highway') not in('service','footway',None)]
import reportlab.rl_config as rlc; rlc.canvas_basefontname='AS'
M=0.35; MX,MY=M,1.95
c=canvas.Canvas(sys.argv[1] if len(sys.argv)>1 else 'sheets.pdf',pagesize=(17*inch,11*inch))
c.setTitle('Sign Inventory - '+AREA.title()); c.setAuthor('Fehr & Peers')
NS=len(F)
def text(x,y,s,f='AS',sz=7,col=SLATE,anchor='l'):
    c.setFont(f,sz);c.setFillColorRGB(*col)
    (c.drawString if anchor=='l' else c.drawRightString if anchor=='r' else c.drawCentredString)(x*inch,y*inch,s)
for fr in F:
    sh=[s for s in S if s['sheet']==fr['i']]
    # map image
    im=render(fr); im=cv2.cvtColor(im,cv2.COLOR_BGR2RGB)
    im=(im.astype(np.float32)*0.78+255*0.22).astype(np.uint8)  # lighten aerial for legibility
    Image.fromarray(im).save(f'aerial_{fr["i"]}.jpg',quality=80,optimize=True)
    c.drawImage(f'aerial_{fr["i"]}.jpg',MX*inch,MY*inch,MAPW*inch,MAPH*inch)
    c.saveState(); p=c.beginPath(); p.rect(MX*inch,MY*inch,MAPW*inch,MAPH*inch); c.clipPath(p,stroke=0)
    P=lambda x,y:tuple(v for v in world_to_page(fr,x,y))
    # streets with no photos
    c.setStrokeColorRGB(*ORG); c.setLineWidth(2.2); c.setDash(5,3)
    for a,b in nophoto:
        pa=P(*a);pb=P(*b)
        if -1<pa[0]<MAPW+1 and -1<pa[1]<MAPH+1: c.line((MX+pa[0])*inch,(MY+pa[1])*inch,(MX+pb[0])*inch,(MY+pb[1])*inch)
    c.setDash()
    occ=[]
    # street names (once per street per sheet, at a point inside)
    done=set()
    for nm,g in streets:
        if nm in done: continue
        pts=[P(*q) for q in g]; ins=[(i,p) for i,p in enumerate(pts) if 0.8<p[0]<MAPW-0.8 and 0.5<p[1]<MAPH-0.5]
        if len(ins)<2: continue
        i,p=ins[len(ins)//2]; j=min(i+1,len(pts)-1); q=pts[j] if j!=i else pts[i-1]
        ang=math.degrees(math.atan2(q[1]-p[1],q[0]-p[0]));
        if ang>90: ang-=180
        if ang<-90: ang+=180
        c.saveState(); c.translate((MX+p[0])*inch,(MY+p[1])*inch); c.rotate(ang)
        lab=nm.upper(); c.setFont('ASB',7.5); w=c.stringWidth(lab,'ASB',7.5)
        c.setFillColorRGB(1,1,1); c.setFillAlpha(0.85); c.roundRect(-w/2-3,-3.5,w+6,11,2,stroke=0,fill=1); c.setFillAlpha(1)
        c.setFillColorRGB(*SLATE); c.drawCentredString(0,-0.5,lab); c.restoreState(); done.add(nm)
        hw=(w/72+0.1)/2; occ.append((p[0]-hw*abs(math.cos(math.radians(ang)))-0.08,p[1]-hw*abs(math.sin(math.radians(ang)))-0.08,p[0]+hw*abs(math.cos(math.radians(ang)))+0.08,p[1]+hw*abs(math.sin(math.radians(ang)))+0.08))
    IXP=[]
    for ix in IX:
        px_,py_=P(ix['x'],ix['y'])
        if 0.3<px_<MAPW-0.3 and 0.3<py_<MAPH-0.3: IXP.append((ix,px_,py_)); occ.append((px_-0.16,py_-0.16,px_+0.16,py_+0.16))
    # signs: poles, facing arrows, callouts
    poles=[]; occ.append((MAPW-0.8,MAPH-0.85,MAPW,MAPH))
    for s in sh: poles.append(P(s['x'],s['y']))
    for (px,py) in poles: occ.append((px-0.05,py-0.05,px+0.05,py+0.05))
    BW,BH=0.80,0.27
    for s,(px,py) in sorted(zip(sh,poles),key=lambda t:t[1][0]):
        side=1 if py>=MAPH/2+(0) else -1
        cands=[]
        for r_ in np.arange(0.3,2.6,0.12):
            for k in range(24):
                a=math.radians(90*side+[0,15,-15,30,-30,45,-45,60,-60,75,-75,90,-90,105,-105,120,-120,135,-135,150,-150,165,-165,180][k])
                cx=px+r_*math.cos(a)-BW/2; cy=py+r_*math.sin(a)-BH/2
                if cx<0.05 or cy<0.05 or cx+BW>MAPW-0.05 or cy+BH>MAPH-0.05: continue
                cands.append((cx,cy,r_,k))
        pick=None
        for cx,cy,r_,k in cands:
            bx=(cx-0.03,cy-0.03,cx+BW+0.03,cy+BH+0.03)
            if not any(not(bx[2]<o[0] or bx[0]>o[2] or bx[3]<o[1] or bx[1]>o[3]) for o in occ): pick=(cx,cy);break
        if pick is None: pick=(cands[0][0],cands[0][1]) if cands else (px+0.1,py+0.1)
        cx,cy=pick; occ.append((cx,cy,cx+BW,cy+BH)); s['_cb']=(cx,cy)
    for s,(px,py) in zip(sh,poles):
        cx,cy=s['_cb']; col=JADE if s['conf']>=0.8 else ORG
        # leader
        tx=min(max(px,cx),cx+BW); ty=min(max(py,cy),cy+BH)
        c.setStrokeColorRGB(*SLATE);c.setLineWidth(0.6);c.line((MX+px)*inch,(MY+py)*inch,(MX+tx)*inch,(MY+ty)*inch)
        # facing arrow (direction the sign face points)
        fa=math.radians(90-s['face'])-fr['ang']; ex,ey=px+0.16*math.cos(fa),py+0.16*math.sin(fa)
        c.setStrokeColorRGB(*EMER);c.setLineWidth(1.3);c.line((MX+px)*inch,(MY+py)*inch,(MX+ex)*inch,(MY+ey)*inch)
        h1=fa+math.radians(150);h2=fa-math.radians(150)
        pth=c.beginPath();pth.moveTo((MX+ex)*inch,(MY+ey)*inch);pth.lineTo((MX+ex+0.06*math.cos(h1))*inch,(MY+ey+0.06*math.sin(h1))*inch);pth.lineTo((MX+ex+0.06*math.cos(h2))*inch,(MY+ey+0.06*math.sin(h2))*inch);pth.close()
        c.setFillColorRGB(*EMER);c.drawPath(pth,stroke=0,fill=1)
        c.setFillColorRGB(1,1,1);c.setStrokeColorRGB(*SLATE);c.setLineWidth(0.8);c.circle((MX+px)*inch,(MY+py)*inch,2.4,stroke=1,fill=1)
        # callout box
        c.setFillColorRGB(1,1,1);c.setStrokeColorRGB(*col);c.setLineWidth(1.2);c.roundRect((MX+cx)*inch,(MY+cy)*inch,BW*inch,BH*inch,2,stroke=1,fill=1)
        fi=face_img(s['code'])
        if fi: c.drawImage(ir(fi),(MX+cx+0.025)*inch,(MY+cy+0.025)*inch,0.22*inch,0.22*inch,mask='auto',preserveAspectRatio=True,anchor='c')
        text(MX+cx+0.27,MY+cy+0.155,s['id'],'ASB',6.3); text(MX+cx+0.27,MY+cy+0.05,disp(s['code']),'ASM',6.0)
    for ix,px_,py_ in IXP:
        worst=[a_['status'] for a_ in ix['approaches']]
        col=ORG if any(w_ not in('OK','NO PHOTOS') for w_ in worst) else ((0.55,0.58,0.6) if all(w_=='NO PHOTOS' for w_ in worst) else JADE)
        c.setStrokeColorRGB(*col);c.setLineWidth(1.6);c.setFillColorRGB(1,1,1);c.circle((MX+px_)*inch,(MY+py_)*inch,0.13*inch,stroke=1,fill=1)
        text(MX+px_,MY+py_-0.03,ix['id'][2:].lstrip('0'),'ASB',6.5,col,'c')
    c.restoreState()
    c.setStrokeColorRGB(*SLATE);c.setLineWidth(0.8);c.rect(MX*inch,MY*inch,MAPW*inch,MAPH*inch)
    # north arrow on map
    na=math.radians(90)-fr['ang']; nx,ny=MX+MAPW-0.45,MY+MAPH-0.5
    c.setFillColorRGB(1,1,1);c.circle(nx*inch,ny*inch,0.26*inch,stroke=0,fill=1)
    tip=(nx+0.2*math.cos(na),ny+0.2*math.sin(na)); l=(nx+0.09*math.cos(na+2.5),ny+0.09*math.sin(na+2.5)); r_=(nx+0.09*math.cos(na-2.5),ny+0.09*math.sin(na-2.5))
    pth=c.beginPath();pth.moveTo(tip[0]*inch,tip[1]*inch);pth.lineTo(l[0]*inch,l[1]*inch);pth.lineTo(nx*inch,ny*inch);pth.lineTo(r_[0]*inch,r_[1]*inch);pth.close();c.setFillColorRGB(*SLATE);c.drawPath(pth,stroke=0,fill=1)
    text(nx-0.16*math.cos(na)+0.0,ny-0.16*math.sin(na)-0.04,'N','ASB',7,anchor='c')
    # ---- right column: sign table
    tx0,tw=13.15,3.5; ty=MY+MAPH
    c.setFillColorRGB(*EMER);c.rect(tx0*inch,(ty-0.24)*inch,tw*inch,0.24*inch,stroke=0,fill=1)
    cols=[('',0.24),('ID',0.44),('CODE',0.74),('APPROACH',1.58),('PHOTO',0.5)]
    xx=tx0
    for h,w in cols: text(xx+0.04,ty-0.165,h,'ASB',6.5,(1,1,1)); xx+=w
    n=len(sh); rh=min(0.24,(MAPH-0.24)/max(n,1)); y=ty-0.24; fs=6.4 if rh>=0.17 else 5.9
    for k,s in enumerate(sh):
        y-=rh
        if k%2: c.setFillColorRGB(*BAND);c.rect(tx0*inch,y*inch,tw*inch,rh*inch,stroke=0,fill=1)
        mid=y+rh/2; fi=face_img(s['code']); ph=min(0.18,rh-0.02)
        if fi: c.drawImage(ir(fi),(tx0+0.03)*inch,(mid-ph/2)*inch,ph*inch,ph*inch,mask='auto',preserveAspectRatio=True,anchor='c')
        text(tx0+0.28,mid-0.022,s['id'],'ASB',fs); text(tx0+0.72,mid-0.022,disp(s['code']),'ASM',fs)
        loc=s['loc']
        while c.stringWidth(loc,'AS',fs)>1.52*inch: loc=loc[:-2]
        text(tx0+1.46,mid-0.022,loc,'AS',fs)
        yr=max(s['years']); text(tx0+3.06,mid-0.022,str(yr),'ASM',fs,ORG if yr<2024 else SLATE)
        c.setFillColorRGB(*(JADE if s['conf']>=0.8 else ORG)); c.circle((tx0+3.38)*inch,mid*inch,2.6,stroke=0,fill=1)
    c.setStrokeColorRGB(*CREAM);c.setLineWidth(1.5);c.line(tx0*inch,y*inch,(tx0+tw)*inch,y*inch)
    # ---- bottom band
    by=0.35
    # legend
    lx=MX; text(lx,1.6,'LEGEND','ASB',7.5)
    c.setFillColorRGB(1,1,1);c.setStrokeColorRGB(*SLATE);c.setLineWidth(0.8);c.circle((lx+0.08)*inch,1.38*inch,2.4,stroke=1,fill=1)
    c.setStrokeColorRGB(*EMER);c.setLineWidth(1.3);c.line((lx+0.08)*inch,1.38*inch,(lx+0.24)*inch,1.38*inch)
    text(lx+0.36,1.35,'Sign post, arrow shows the way the sign faces','AS',6.8)
    for i,(col,lab) in enumerate([(JADE,'Code read with high confidence'),(ORG,'Low confidence, check in field')]):
        c.setFillColorRGB(1,1,1);c.setStrokeColorRGB(*col);c.setLineWidth(1.2);c.roundRect((lx+0.02)*inch,(1.14-i*0.19)*inch,0.26*inch,0.13*inch,2,stroke=1,fill=1);text(lx+0.36,1.16-i*0.19,lab,'AS',6.8)
    c.setStrokeColorRGB(*ORG);c.setLineWidth(2.2);c.setDash(5,3);c.line((lx+0.0)*inch,0.81*inch,(lx+0.3)*inch,0.81*inch);c.setDash();text(lx+0.36,0.78,'Street with no street-level photos (not inventoried)','AS',6.8)
    c.setStrokeColorRGB(*JADE);c.setLineWidth(1.6);c.setFillColorRGB(1,1,1);c.circle((lx+0.15)*inch,0.62*inch,0.09*inch,stroke=1,fill=1);text(lx+0.15,0.595,'7','ASB',5.5,JADE,'c')
    text(lx+0.36,0.595,'Intersection checked against OpenStreetMap (green OK, orange check)','AS',6.8)
    text(lx+0.36,0.42,'Photo year in orange: newest photo is before 2024','AS',6.8,ORG)
    # key map
    kx,ky,kw,kh=4.2,0.35,4.6,1.35
    c.setStrokeColorRGB(*CREAM);c.setLineWidth(0.8);c.rect(kx*inch,ky*inch,kw*inch,kh*inch)
    allp=np.vstack(([cl] if len(cl) else [])+[np.array([[f['c'][0]+sx*f['W']/2,f['c'][1]+sy*f['H']/2] for sx in(-1,1) for sy in(-1,1)]) for f in F]); x0,y0=allp.min(0)-60; x1,y1=allp.max(0)+60
    sc=min(kw/(x1-x0),kh/(y1-y0)); ox=kx+(kw-(x1-x0)*sc)/2; oy=ky+(kh-(y1-y0)*sc)/2
    K_=lambda x,y:((ox+(x-x0)*sc)*inch,(oy+(y-y0)*sc)*inch)
    c.saveState(); kp=c.beginPath(); kp.rect(kx*inch,ky*inch,kw*inch,kh*inch); c.clipPath(kp,stroke=0)
    c.setStrokeColorRGB(0.75,0.77,0.78);c.setLineWidth(0.4)
    for nm,g in streets:
        for a,b in zip(g[:-1],g[1:]):
            pa,pb=K_(*a),K_(*b)
            if kx*inch<pa[0]<(kx+kw)*inch and ky*inch<pa[1]<(ky+kh)*inch: c.line(*pa,*pb)
    for f in F:
        cc=np.array(f['c']);a=f['ang'];u=np.array([math.cos(a),math.sin(a)]);nn=np.array([-math.sin(a),math.cos(a)])
        corners=[cc+sx*f['W']/2*u+sy*f['H']/2*nn for sx,sy in((-1,-1),(1,-1),(1,1),(-1,1))]
        pth=c.beginPath();pth.moveTo(*K_(*corners[0]))
        for q in corners[1:]: pth.lineTo(*K_(*q))
        pth.close(); cur=f['i']==fr['i']
        c.setStrokeColorRGB(*(ORG if cur else SLATE));c.setLineWidth(1.4 if cur else 0.5)
        if cur: c.setFillColorRGB(*ORG);c.setFillAlpha(0.15)
        if len(F)==1 and not len(cl): pass
        c.drawPath(pth,stroke=1,fill=1 if cur else 0);c.setFillAlpha(1)
    c.setStrokeColorRGB(*SLATE);c.setLineWidth(1.4)
    for a,b in zip(cl[:-1],cl[1:]): c.line(*K_(*a),*K_(*b))
    c.restoreState()
    text(kx+0.06,ky+kh-0.14,'KEY MAP','ASB',6.5)
    # scale bar
    sx0,sy0=9.4,0.62; L=1.0
    for i in range(4):
        c.setFillColorRGB(*(SLATE if i%2==0 else (1,1,1)));c.setStrokeColorRGB(*SLATE);c.setLineWidth(0.6);c.rect((sx0+i*L/2)*inch,sy0*inch,L/2*inch,0.07*inch,stroke=1,fill=1)
    for i in range(5): text(sx0+i*L/2,sy0+0.12,str(int(i*SCALE/2)),'AS',6,anchor='c')
    text(sx0+2*L+0.12,sy0+0.0,'FEET','AS',6); text(sx0,sy0-0.17,f'SCALE: 1" = {SCALE}\' (11x17)','ASM',6.5)
    # title block
    tbx=12.55; c.setStrokeColorRGB(*SLATE);c.setLineWidth(0.8);c.line(tbx*inch,0.35*inch,tbx*inch,1.75*inch)
    c.drawImage(REPO+'/img/wordmark-slate.png',(tbx+0.2)*inch,1.38*inch,1.3*inch,0.25*inch,mask='auto',preserveAspectRatio=True,anchor='w')
    text(tbx+0.2,1.12,'EXISTING SIGN INVENTORY','ASS',11)
    text(tbx+0.2,0.94,AREA,'ASM',7.5)
    text(tbx+0.2,0.78,f"{len(sh)} signs on this sheet  |  {len(S)} signs total  |  {DATE}",'AS',6.8)
    for k_,ln in enumerate(['Sources: street-level photos, Mapillary (CC BY-SA); aerial, Esri;','streets, OpenStreetMap. Signs located from several photos; codes','per CA MUTCD 2026, read by a trained sign model.']): text(tbx+0.2,0.60-k_*0.1,ln,'AS',5.6,(0.33,0.4,0.42))
    c.setFillColorRGB(*SLATE);c.rect(15.85*inch,0.35*inch,0.8*inch,0.55*inch,stroke=0,fill=1)
    text(16.25,0.67,'SHEET','ASM',6,(1,1,1),'c'); text(16.25,0.44,f"{fr['n']} of {NS}",'ASB',9,(1,1,1),'c')
    c.showPage()
# ---- intersection check pages
rows=[(ix,a_) for ix in IX for a_ in ix['approaches']]
STC={'OK':JADE,'NO PHOTOS':(0.45,0.5,0.52)}
per=38; npg=max(1,(len(rows)+per-1)//per)
for pg in range(npg):
    text(0.5,10.35,'INTERSECTION CHECK','ASS',16); text(0.5,10.08,f'{AREA}  |  each approach: OpenStreetMap control against the signs found in the photos','AS',8.5,(0.33,0.4,0.42))
    cols=[('INT.',0.55),('INTERSECTION',3.6),('APPROACH',2.3),('OSM CONTROL',1.3),('SIGNS FOUND ON APPROACH',4.2),('PHOTOS',0.8),('STATUS',1.6),('SIGN IDS',1.65)]
    x0=0.5; y=9.75; c.setFillColorRGB(*EMER); c.rect(x0*inch,(y-0.26)*inch,16*inch,0.26*inch,stroke=0,fill=1); xx=x0
    for h,w in cols: text(xx+0.06,y-0.175,h,'ASB',7,(1,1,1)); xx+=w
    y-=0.26; prev=None
    for k,(ix,a_) in enumerate(rows[pg*per:(pg+1)*per]):
        y-=0.215
        if k%2: c.setFillColorRGB(*BAND); c.rect(x0*inch,y*inch,16*inch,0.215*inch,stroke=0,fill=1)
        m=y+0.075; xx=x0; first=ix['id']!=prev; prev=ix['id']
        vals=[(ix['id'] if first else '','ASB'),(ix['name'] if first else '','AS'),(f"{a_['dir']} {a_['street']}",'AS'),(a_['control'].upper(),'AS'),(', '.join(a_['codes']) or '-','AS'),('YES' if a_['photos'] else 'NO','AS'),(a_['status'],'ASB'),(', '.join(a_['signs'][:4])+(' +' if len(a_['signs'])>4 else ''),'AS')]
        for (v,f),(h,w) in zip(vals,cols):
            while c.stringWidth(v,f,7)>(w-0.12)*inch: v=v[:-2]
            col=STC.get(v,ORG) if h=='STATUS' else SLATE
            text(xx+0.06,m,v,f,7,col); xx+=w
    c.setStrokeColorRGB(*CREAM);c.setLineWidth(1.5);c.line(x0*inch,y*inch,(x0+16)*inch,y*inch)
    tot=collections.Counter(a_['status'] for _,a_ in rows)
    text(0.5,0.75,'  |  '.join(f'{k}: {v}' for k,v in tot.most_common()),'ASM',8)
    text(0.5,0.55,'OSM control comes from OpenStreetMap traffic signal and stop tags. STOP NOT SEEN: the approach has photos but no stop sign was read; confirm in field. NO PHOTOS: approach cannot be checked.','AS',7,(0.33,0.4,0.42))
    c.drawImage(REPO+'/img/wordmark-slate.png',13.6*inch,0.45*inch,1.3*inch,0.25*inch,mask='auto',preserveAspectRatio=True,anchor='w')
    c.setFillColorRGB(*SLATE);c.rect(15.85*inch,0.35*inch,0.8*inch,0.55*inch,stroke=0,fill=1)
    text(16.25,0.67,'CHECK','ASM',6,(1,1,1),'c'); text(16.25,0.44,f"{pg+1} of {npg}",'ASB',9,(1,1,1),'c')
    c.showPage()
c.save(); json.dump(S,open('signs_final.json','w'),default=float)
print('sheets',collections.Counter(s['sheet'] for s in S))
