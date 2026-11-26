(() => {
'use strict';
const C = window.CFG;
const $ = s => document.querySelector(s);
const STATUS_TXT = {verified:'HIGH CONFIDENCE', review:'CHECK IN FIELD', auto:'AUTO', nomatch:'NO CODE', unreadable:'UNREADABLE'};
let AREAKEY = '', NAMESIGNS = [];
let LIB = {}, CLASSMAP = {}, signs = [], area = null, areaName = '', layer, areaRect;

// ---------- map ----------
const map = L.map('map', {zoomControl:true, preferCanvas:false}).setView([34.0835,-118.1860], 16);
const base = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
  maxZoom: 21, maxNativeZoom: 19,
  attribution: 'Aerial: Esri, Maxar, Earthstar Geographics | Signs: Mapillary (CC BY-SA)'
}).addTo(map);
layer = L.layerGroup().addTo(map);
const zoomClass = () => {
  const z = document.body.classList.contains('printing') ? 99 : map.getZoom(), el = $('#map');
  el.classList.toggle('z-lo', z < 17);
  el.classList.toggle('z-mid', z === 17);
};
map.on('zoomend', zoomClass); zoomClass();

// ---------- helpers ----------
const setBar = (p, t) => { $('#bar-fill').style.width = Math.round(p*100) + '%'; if (t) $('#status').textContent = t; };
const sprite = code => LIB[code] ? `data/sprites/${LIB[code].s}.webp` : '';
// speed limit faces drawn with the posted number (the library face shows a sample value)
const SPEED = {'R2-1': 0, 'SR4-1(CA)': 1};
const speedFace = (code, val) => 'data:image/svg+xml,' + encodeURIComponent(SPEED[code]
  ? `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 64"><rect x="1" y="1" width="46" height="62" rx="3" fill="#fff" stroke="#000" stroke-width="2"/><rect x="2" y="2" width="44" height="12" fill="#C6D92E"/><text x="24" y="11.5" font-family="Arial" font-weight="700" font-size="9" text-anchor="middle">SCHOOL</text><text x="24" y="23" font-family="Arial" font-weight="700" font-size="7.5" text-anchor="middle">SPEED LIMIT</text><text x="24" y="49" font-family="Arial" font-weight="700" font-size="24" text-anchor="middle">${val}</text></svg>`
  : `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 60"><rect x="1" y="1" width="46" height="58" rx="3" fill="#fff" stroke="#000" stroke-width="2"/><text x="24" y="15" font-family="Arial" font-weight="700" font-size="10" text-anchor="middle">SPEED</text><text x="24" y="26" font-family="Arial" font-weight="700" font-size="10" text-anchor="middle">LIMIT</text><text x="24" y="52" font-family="Arial" font-weight="700" font-size="26" text-anchor="middle">${val}</text></svg>`);
const FACE = {};   // speed faces turned into plain images (keeps vector fonts out of exports)
const pic = s => (s.code in SPEED && s.val) ? (FACE[s.code + s.val] || speedFace(s.code, s.val)) : sprite(s.code);
async function rasterFaces() {
  const need = [...new Set(signs.filter(s => s.code in SPEED && s.val).map(s => s.code + '|' + s.val))].filter(k => !FACE[k.replace('|', '')]);
  await Promise.all(need.map(k => new Promise(r => { const [code, val] = k.split('|'), im = new Image();
    im.onload = () => { const c = document.createElement('canvas'), h = 96, w = Math.round(h * im.width / im.height); c.width = w; c.height = h;
      c.getContext('2d').drawImage(im, 0, 0, w, h); FACE[code + val] = c.toDataURL('image/png'); r(); };
    im.onerror = r; im.src = speedFace(code, val); })));
}
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const getJSON = async u => { const r = await fetch(u); if (!r.ok) throw new Error(r.status + ' ' + u); return r.json(); };
const sv = s => `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${s.lat},${s.lon}` + (s.dir!=null ? `&heading=${Math.round((s.dir+180)%360)}` : '');
const mly = s => s.img ? `https://www.mapillary.com/app/?pKey=${s.img}&focus=photo` : `https://www.mapillary.com/app/?lat=${s.lat}&lng=${s.lon}&z=19`;

// minimal Mapbox vector tile reader: returns bbox [x0,y0,x1,y1] in 0..1 of the first feature
function mvtBBox(b64) {
  const b = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const rd = (buf, i) => { let v = 0, s = 0, x; do { x = buf[i++]; v += (x & 0x7f) * 2 ** s; s += 7; } while (x & 0x80); return [v, i]; };
  const fields = (buf) => { const out = []; let i = 0; while (i < buf.length) { let k; [k, i] = rd(buf, i); const f = k >> 3, w = k & 7;
      if (w === 0) { let v; [v, i] = rd(buf, i); out.push([f, v]); } else if (w === 2) { let l; [l, i] = rd(buf, i); out.push([f, buf.subarray(i, i + l)]); i += l; }
      else if (w === 5) { i += 4; } else if (w === 1) { i += 8; } else break; } return out; };
  const lay = fields(b).find(f => f[0] === 3)[1];
  const lf = fields(lay); const ext = (lf.find(f => f[0] === 5) || [0, 4096])[1];
  const feat = lf.find(f => f[0] === 2)[1];
  const geo = fields(feat).find(f => f[0] === 4)[1];
  const cmds = []; let i = 0; while (i < geo.length) { let v; [v, i] = rd(geo, i); cmds.push(v); }
  let x = 0, y = 0, k = 0; const xs = [], ys = [];
  while (k < cmds.length) { const id = cmds[k] & 7, n = cmds[k] >> 3; k++;
    if (id === 7) continue;
    for (let j = 0; j < n; j++) { const dx = cmds[k++], dy = cmds[k++]; x += (dx >> 1) ^ -(dx & 1); y += (dy >> 1) ^ -(dy & 1); xs.push(x / ext); ys.push(y / ext); } }
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

// ---------- markers ----------
function icon(s) {
  const im = s.code && LIB[s.code] ? `<img src="${pic(s)}" alt="">` : `<b>?</b>`;
  const lab = s.code ? s.code + (s.val ? ` (${s.val})` : '') : STATUS_TXT[s.status];
  const dir = s.dir != null ? `<div class="dir" style="transform:rotate(${s.dir}deg)"></div>` : '';
  return L.divIcon({className:'', iconSize:[28,28], iconAnchor:[14,14],
    html:`<div class="sg st-${s.status}">${dir}<div class="ico">${im}</div><div class="lab">${esc(lab)}</div></div>`});
}
const PRI = {verified:0, review:1, auto:2, nomatch:3, unreadable:4};
function poleIcon(g) {
  const show = g.slice(0, 4);
  const icos = show.map(s => `<div class="ico st-${s.status}">${s.code && LIB[s.code] ? `<img src="${pic(s)}" alt="">` : '<b>?</b>'}</div>`).join('');
  const more = g.length > 4 ? `<span class="more">+${g.length - 4}</span>` : '';
  const lab = g.map(s => s.code ? s.code + (s.val ? ` (${s.val})` : '') : STATUS_TXT[s.status]).filter((v, i, a) => a.indexOf(v) === i).join(' · ');
  const w = Math.min(g.length, 4) * 28 + (more ? 22 : 0);
  return L.divIcon({className:'', iconSize:[w, 26], iconAnchor:[13, 13],
    html:`<div class="pole st-${g[0].status}">${icos}${more}<div class="lab">${esc(lab)}</div></div>`});
}
function openSign(s, latlng) {
  const p = L.popup({maxWidth:300}).setLatLng(latlng || [s.lat, s.lon]).setContent(popup(s)).openOn(map);
  if (s.status !== 'verified') liveCrop(s);
  return p;
}
// group signs whose screen positions fall close together (same pole or same corner)
function groupAt(z, R0, IW = 28) {
  const R = R0 || (z >= 20 ? 30 : z >= 19 ? 46 : 64), out = [];
  const pts = signs.map(s => ({s, p: map.project([s.lat, s.lon], z)})).sort((a, b) => PRI[a.s.status] - PRI[b.s.status]);
  for (const o of pts) { const g = out.find(g => g.p.distanceTo(o.p) < R); if (g) g.list.push(o.s); else out.push({p: o.p, list: [o.s]}); }
  // merge groups whose icon rows would overlap (each icon 28 px wide, up to 4 plus a count chip)
  const box = g => { const w = Math.min(g.list.length, 4) * IW + (g.list.length > 4 ? 24 : 0), h = IW / 2 + 2; return [g.p.x - h, g.p.y - h, g.p.x - h + w + 4, g.p.y + h]; };
  const hit = (a, b) => !(a[2] < b[0] || a[0] > b[2] || a[3] < b[1] || a[1] > b[3]);
  for (let again = true; again;) { again = false;
    for (let i = 0; i < out.length && !again; i++) for (let j = i + 1; j < out.length; j++)
      if (hit(box(out[i]), box(out[j]))) { out[i].list.push(...out[j].list); out.splice(j, 1); again = true; break; } }
  return out;
}
const loadImg = src => new Promise(r => { const i = new Image(); i.crossOrigin = 'anonymous'; i.onload = () => r(i); i.onerror = () => r(null); i.src = src; });
// still image of the map for the 11x17 sheet: aerial, area outline, sign pictures and codes, north arrow, scale bar
async function renderPrintMap(Wc, Hc) {
  const S = 2, cv = document.createElement('canvas'); cv.width = Wc * S; cv.height = Hc * S;
  const g = cv.getContext('2d'); g.scale(S, S); g.fillStyle = '#ddd'; g.fillRect(0, 0, Wc, Hc);
  const z = map.getZoom(), tz = Math.min(19, Math.ceil(z)), f = 2 ** (z - tz);
  const c = map.project(map.getCenter(), z), ox = c.x - Wc / 2, oy = c.y - Hc / 2;
  const tiles = [];
  for (let tx = Math.floor(ox / f / 256); tx <= Math.floor((ox + Wc) / f / 256); tx++)
    for (let ty = Math.floor(oy / f / 256); ty <= Math.floor((oy + Hc) / f / 256); ty++) tiles.push([tx, ty]);
  const imgs = await Promise.all(tiles.map(([tx, ty]) => loadImg(`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${tz}/${ty}/${tx}`)));
  tiles.forEach(([tx, ty], i) => { if (imgs[i]) g.drawImage(imgs[i], tx * 256 * f - ox, ty * 256 * f - oy, 256 * f + 0.5, 256 * f + 0.5); });
  const P = ll => { const p = map.project(ll, z); return [p.x - ox, p.y - oy]; };
  // area outline
  const a = P([area[3], area[0]]), b = P([area[1], area[2]]);
  g.save(); g.setLineDash([7, 5]); g.strokeStyle = '#FF6622'; g.lineWidth = 2; g.strokeRect(a[0], a[1], b[0] - a[0], b[1] - a[1]); g.restore();
  // signs
  const cols = {verified:'#1B795A', review:'#FF6622', auto:'#568CBB', nomatch:'#FF6622', unreadable:'#8a8f91'};
  const groups = groupAt(z, 20, 20), keys = [...new Set(signs.filter(s => s.code).map(pic))];
  const spr = {}; (await Promise.all(keys.map(k => loadImg(k)))).forEach((im, i) => spr[keys[i]] = im);
  const boxes = [], labels = [];
  g.font = "700 10px 'Albert Sans'"; g.textBaseline = 'middle';
  for (const gr of groups) {
    const [x, y] = [gr.p.x - ox, gr.p.y - oy], show = gr.list.slice(0, 4);
    show.forEach((sg, i) => {
      const bx = x - 9 + i * 20, by = y - 9;
      g.fillStyle = '#fff'; g.strokeStyle = cols[sg.status]; g.lineWidth = 2;
      g.beginPath(); g.roundRect(bx, by, 18, 18, 2); g.fill(); g.stroke();
      if (sg.code && spr[pic(sg)]) { const im = spr[pic(sg)], k = Math.min(15 / im.width, 15 / im.height); g.drawImage(im, bx + 9 - im.width * k / 2, by + 9 - im.height * k / 2, im.width * k, im.height * k); }
      else { g.fillStyle = '#FF6622'; g.fillText('?', bx + 6, by + 9); }
      boxes.push([bx - 2, by - 2, bx + 20, by + 20]);
    });
    if (gr.list.length > 4) { const mx = x - 9 + 4 * 20; g.fillStyle = '#00242E'; g.fillRect(mx, y - 7, 20, 14); g.fillStyle = '#fff'; g.fillText('+' + (gr.list.length - 4), mx + 2, y); boxes.push([mx, y - 7, mx + 20, y + 7]); }
    const txt = gr.list.map(sg => sg.code ? sg.code + (sg.val ? ` (${sg.val})` : '') : STATUS_TXT[sg.status]).filter((v, i, arr) => arr.indexOf(v) === i).join(' · ');
    labels.push([txt, x - 9, y + 12]);
  }
  const hit = (p, q) => !(p[2] < q[0] || p[0] > q[2] || p[3] < q[1] || p[1] > q[3]);
  const placed = [];
  for (const [txt, lx, ly] of labels) {
    const w = g.measureText(txt).width + 8, r = [lx, ly, lx + w, ly + 14];
    if (r[2] > Wc - 4 || r[3] > Hc - 20 || placed.some(q => hit(r, q)) || boxes.some(q => hit(r, q))) continue;
    placed.push(r); g.fillStyle = '#00242E'; g.fillRect(r[0], r[1], w, 14); g.fillStyle = '#fff'; g.fillText(txt, lx + 4, ly + 7);
  }
  // north arrow
  g.fillStyle = 'rgba(255,255,255,.92)'; g.fillRect(Wc - 52, 12, 40, 52); g.fillStyle = '#00242E';
  g.beginPath(); g.moveTo(Wc - 32, 18); g.lineTo(Wc - 42, 44); g.lineTo(Wc - 32, 38); g.lineTo(Wc - 22, 44); g.closePath(); g.fill();
  g.font = "700 12px 'Albert Sans'"; g.textAlign = 'center'; g.fillText('N', Wc - 32, 54); g.textAlign = 'left';
  // scale bar in feet
  const mpp = 40075016.686 * Math.cos(map.getCenter().lat * Math.PI / 180) / (256 * 2 ** z), ftpp = mpp * 3.28084;
  const nice = [50, 100, 200, 250, 500, 1000, 2000].find(v => v / ftpp > 90) || 2000, len = nice / ftpp;
  g.fillStyle = 'rgba(255,255,255,.92)'; g.fillRect(12, Hc - 44, len + 70, 32); g.fillStyle = '#00242E';
  g.fillRect(20, Hc - 26, len / 2, 6); g.strokeStyle = '#00242E'; g.lineWidth = 1; g.strokeRect(20, Hc - 26, len, 6);
  g.font = "600 10px 'Albert Sans'"; g.fillText('0', 17, Hc - 35); g.fillText(nice + ' FT', 20 + len - 8, Hc - 35);
  // attribution
  g.font = "500 9px 'Albert Sans'"; const at = 'Aerial: Esri, Maxar, Earthstar Geographics | Imagery: Mapillary (CC BY-SA)';
  const aw = g.measureText(at).width + 10; g.fillStyle = 'rgba(255,255,255,.85)'; g.fillRect(Wc - aw - 2, Hc - 16, aw, 14); g.fillStyle = '#00242E'; g.fillText(at, Wc - aw + 3, Hc - 9);
  return cv.toDataURL('image/jpeg', 0.9);
}
function draw() {
  layer.clearLayers();
  const z = map.getZoom(), groupsArr = groupAt(z);
  for (const g of groupsArr) {
    const ll = map.unproject(g.p, z);
    if (g.list.length === 1) {
      const s = g.list[0], m = L.marker(ll, {icon: icon(s), riseOnHover:true});
      m.on('click', () => openSign(s, ll)); s.m = m; m.addTo(layer); continue;
    }
    const m = L.marker(ll, {icon: poleIcon(g.list), riseOnHover:true});
    m.on('click', () => {
      const html = '<div class="plist">' + g.list.map((s, i) => `<div data-i="${i}">${s.code && LIB[s.code] ? `<img src="${pic(s)}" alt="">` : '<b>?</b>'}<span><b>${esc(s.code || STATUS_TXT[s.status])}</b>${s.val ? ' (' + esc(s.val) + ')' : ''}</span><i>${STATUS_TXT[s.status]}</i></div>`).join('') + '</div>';
      const p = L.popup({maxWidth:300}).setLatLng(ll).setContent(html).openOn(map);
      p.getElement().querySelector('.plist').onclick = e => { const d = e.target.closest('[data-i]'); if (d) openSign(g.list[+d.dataset.i], ll); };
    });
    g.list.forEach(s => s.m = m); m.addTo(layer);
  }
  requestAnimationFrame(declutter);
}
// hide any code label that would overlap another label or a sign icon
function declutter() {
  const boxes = [...document.querySelectorAll('#map .ico, #map .more')].map(e => e.getBoundingClientRect());
  const placed = [];
  const hit = (a, b) => !(a.right < b.left - 2 || a.left > b.right + 2 || a.bottom < b.top - 1 || a.top > b.bottom + 1);
  for (const el of document.querySelectorAll('#map .lab')) {
    el.style.visibility = '';
    const r = el.getBoundingClientRect(); if (!r.width) continue;
    if (placed.some(p => hit(r, p)) || boxes.some(b => hit(r, b))) el.style.visibility = 'hidden';
    else placed.push(r);
  }
}
map.on('moveend', () => requestAnimationFrame(declutter));
let lastZ = null;
map.on('zoomend', () => { if (signs.length && map.getZoom() !== lastZ) { lastZ = map.getZoom(); draw(); } });
function popup(s) {
  const L0 = LIB[s.code];
  const crop = s.crop ? `<img class="crop" src="data/areas/${AREAKEY}/crops/${s.crop}" alt="">` : `<div class="crop" id="crop-${s.id}"></div>`;
  return `<div class="pop">
    <div class="row">${L0 ? `<img class="ref" src="${sprite(s.code)}" alt="">` : ''}
      <div><h3>${esc(s.code || STATUS_TXT[s.status])}</h3><div class="nm">${esc(L0 ? L0.n : (s.cls || ''))}</div></div></div>
    ${crop}
    <table>
      <tr><td>STATUS</td><td><b>${STATUS_TXT[s.status]}</b>${s.conf ? ' / ' + esc(s.conf) : ''}</td></tr>
      ${s.loc ? `<tr><td>APPROACH</td><td>${esc(s.loc)}</td></tr>` : ''}
      ${s.legend ? `<tr><td>LEGEND</td><td>${esc(s.legend)}</td></tr>` : ''}
      ${s.val ? `<tr><td>VALUE</td><td>${esc(s.val)}</td></tr>` : ''}
      ${s.plaque ? `<tr><td>PLAQUE</td><td>${esc(s.plaque)}</td></tr>` : ''}
      ${s.arrow ? `<tr><td>ARROW</td><td>${esc(s.arrow)}</td></tr>` : ''}
      ${s.seen ? `<tr><td>PHOTO</td><td>${esc(s.seen)}${(Date.now() - Date.parse(s.seen)) > 3*365.25*864e5 ? ' <span class="old">OVER 3 YEARS OLD</span>' : ''}</td></tr>` : ''}
    </table>
    <div class="links"><a href="${mly(s)}" target="_blank" rel="noopener">PHOTO</a><a href="${sv(s)}" target="_blank" rel="noopener">STREET VIEW</a></div>
  </div>`;
}
async function liveCrop(s) {
  const el = document.getElementById('crop-' + s.id); if (!el || el.dataset.done) return; el.dataset.done = 1;
  try {
    const d = (await getJSON(`https://graph.mapillary.com/${s.id}/detections?access_token=${C.MLY}&fields=image,geometry`)).data;
    let best = null;
    for (const x of d) { try { const b = mvtBBox(x.geometry); const a = (b[2]-b[0])*(b[3]-b[1]); if (!best || a > best.a) best = {b, a, img: x.image.id}; } catch (e) {} }
    if (!best) { el.textContent = 'No photo crop'; return; }
    const im = await getJSON(`https://graph.mapillary.com/${best.img}?access_token=${C.MLY}&fields=thumb_1024_url,captured_at`);
    s.img = best.img;
    const [x0,y0,x1,y1] = best.b, w = x1-x0, h = y1-y0, pad = Math.max(w,h)*0.7;
    const cx = (x0+x1)/2, cy = (y0+y1)/2, span = Math.max(w,h) + 2*pad;
    const img = new Image();
    img.onload = () => {
      const W = el.clientWidth, H = 170, iw = img.naturalWidth, ih = img.naturalHeight;
      const k = Math.min(W / (span * iw), H / (span * ih));          // screen px per image px
      el.style.cssText = 'height:170px;position:relative;overflow:hidden;background:#111';
      img.style.cssText = `position:absolute;max-width:none;width:${iw*k}px;height:${ih*k}px;left:${W/2 - cx*iw*k}px;top:${H/2 - cy*ih*k}px`;
      el.innerHTML = ''; el.appendChild(img);
    };
    img.onerror = () => { el.textContent = 'Photo not available'; };
    img.src = im.thumb_1024_url;
  } catch (e) { el.textContent = 'Photo not available'; }
}

// ---------- inventory ----------
function groups() {
  const g = new Map();
  for (const s of signs) {
    const key = s.code ? s.code + (s.code in SPEED && s.val ? ` (${s.val})` : '') : STATUS_TXT[s.status];
    const r = g.get(key) || {key, code: s.code, n: 0, arrows: new Set(), list: [], status: s.status};
    r.n++; if (s.arrow === 'L' || s.arrow === 'R') r.arrows.add(s.arrow); r.list.push(s); g.set(key, r);
  }
  return [...g.values()].sort((a, b) => (!a.code) - (!b.code) || a.key.localeCompare(b.key, undefined, {numeric:true}));
}
const label = r => r.code ? r.key + (r.arrows.size === 2 ? ' (LT/RT)' : r.arrows.has('L') ? ' (LT)' : r.arrows.has('R') ? ' (RT)' : '') : r.key;
const nameOf = r => r.code ? LIB[r.code]?.n || '' : (r.status === 'nomatch' ? 'Sign with no standard code' : 'Sign could not be read');
function rowsHTML() {
  return groups().map(r => `<tr data-k="${esc(r.key)}"><td class="pic">${r.code ? `<img src="${pic(r.list[0])}" alt="">` : ''}</td>
    <td class="code">${esc(label(r))}</td><td>${esc(nameOf(r))}</td><td class="qty">${r.n}</td></tr>`).join('');
}
function inventory() {
  $('#inv tbody').innerHTML = rowsHTML();
  $('#inv-count').textContent = signs.length ? `${signs.length} SIGNS` : '';
  $('#inv tbody').onclick = e => { const tr = e.target.closest('tr'); if (!tr) return;
    const r = groups().find(x => x.key === tr.dataset.k); if (!r) return;
    const b = L.latLngBounds(r.list.map(s => [s.lat, s.lon])); map.fitBounds(b.pad(0.3), {maxZoom: 19});
    if (r.list.length === 1) setTimeout(() => openSign(r.list[0]), 400); };
}

// ---------- data ----------
function fromClass(f) {
  const v = f.object_value, cm = CLASSMAP[v];
  const [lon, lat] = f.geometry.coordinates;
  const s = {id: f.id, lat, lon, cls: v, dir: f.aligned_direction ?? null,
    seen: f.last_seen_at ? new Date(f.last_seen_at).toISOString().slice(0,10) : ''};
  if (cm && cm.code && LIB[cm.code]) { s.code = cm.code; s.val = cm.val || ''; s.arrow = cm.arrow || ''; s.status = 'auto'; }
  else s.status = 'nomatch';
  return s;
}
// ---- sign tiles (traffic signs only, about 15 KB each) ----
function decodeSignTile(buf, tx, ty, z) {
  const rd = (b, i) => { let v = 0, sh = 0, x; do { x = b[i++]; v += (x & 0x7f) * 2 ** sh; sh += 7; } while (x & 0x80); return [v, i]; };
  const fields = b => { const out = []; let i = 0; while (i < b.length) { let k; [k, i] = rd(b, i); const f = Math.floor(k / 8), w = k & 7;
      if (w === 0) { let v; [v, i] = rd(b, i); out.push([f, v]); } else if (w === 2) { let l; [l, i] = rd(b, i); out.push([f, b.subarray(i, i + l)]); i += l; }
      else if (w === 5) { out.push([f, new DataView(b.buffer, b.byteOffset + i, 4).getFloat32(0, true)]); i += 4; }
      else if (w === 1) { out.push([f, new DataView(b.buffer, b.byteOffset + i, 8).getFloat64(0, true)]); i += 8; } else break; } return out; };
  const dec = new TextDecoder(), res = [];
  for (const [f, lay] of fields(buf)) {
    if (f !== 3) continue;
    const lf = fields(lay), keys = [], vals = []; let ext = 4096; const feats = [];
    for (const [k, v] of lf) {
      if (k === 3) keys.push(dec.decode(v));
      else if (k === 4) { const vf = fields(v)[0]; vals.push(vf[0] === 1 ? dec.decode(vf[1]) : vf[1]); }
      else if (k === 5) ext = v;
      else if (k === 2) feats.push(v);
    }
    for (const fb of feats) {
      const ff = fields(fb), props = {}; let geo = null, tags = null;
      for (const [k, v] of ff) { if (k === 2) tags = v; if (k === 4) geo = v; }
      if (tags) { const t = []; let i = 0; while (i < tags.length) { let x; [x, i] = rd(tags, i); t.push(x); } for (let j = 0; j < t.length; j += 2) props[keys[t[j]]] = vals[t[j + 1]]; }
      if (!geo) continue;
      const g = []; let i = 0; while (i < geo.length) { let x; [x, i] = rd(geo, i); g.push(x); }
      const px = (g[1] >> 1) ^ -(g[1] & 1), py = (g[2] >> 1) ^ -(g[2] & 1);
      const n = 2 ** z, X = tx + px / ext, Y = ty + py / ext;
      const lon = X / n * 360 - 180, lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * Y / n))) * 180 / Math.PI;
      res.push({id: String(props.id), object_value: props.value, geometry: {coordinates: [lon, lat]}, last_seen_at: props.last_seen_at});
    }
  }
  return res;
}
async function pull(bbox) {
  const [w, so, e, n] = bbox, z = 14, N = 2 ** z;
  const tx = lon => Math.floor((lon + 180) / 360 * N);
  const ty = lat => Math.floor((1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * N);
  const tiles = [];
  for (let x = tx(w); x <= tx(e); x++) for (let y = ty(n); y <= ty(so); y++) tiles.push([x, y]);
  const out = new Map(); let done = 0;
  await Promise.all(tiles.map(async ([x, y]) => {
    const r = await fetch(`https://tiles.mapillary.com/maps/vtp/mly_map_feature_traffic_sign/2/${z}/${x}/${y}?access_token=${C.MLY}`);
    if (!r.ok) throw new Error('sign tile ' + r.status);
    for (const f of decodeSignTile(new Uint8Array(await r.arrayBuffer()), x, y, z)) {
      const [lon, lat] = f.geometry.coordinates;
      if (lon >= w && lon <= e && lat >= so && lat <= n) out.set(f.id, f);
    }
    done++; setBar(0.1 + 0.7 * done / tiles.length, `Loading signs: tile ${done} of ${tiles.length}, ${out.size} found`);
  }));
  return [...out.values()];
}
async function run(bbox, name, verifiedKey) {
  const a = (bbox[2]-bbox[0]) * (bbox[3]-bbox[1]);
  if (a > C.MAX_AREA_DEG2) { setBar(0, 'Area too large. Zoom in to about 6 sq km or less.'); return; }
  area = bbox; areaName = name; signs = []; layer.clearLayers(); inventory(); map.closePopup();
  if (areaRect) map.removeLayer(areaRect);
  areaRect = L.rectangle([[bbox[1], bbox[0]], [bbox[3], bbox[2]]], {color:'#FF6622', weight:2, dashArray:'6 5', fill:false, interactive:false}).addTo(map);
  try {
    setBar(0.05, 'Loading sign library');
    await ready;
    let ver = {};
    AREAKEY = verifiedKey || ''; NAMESIGNS = [];
    if (verifiedKey) { setBar(0.08, 'Loading scanned signs'); ver = await getJSON(`data/areas/${verifiedKey}/signs.json?v=${C.DATA_V}`).catch(() => ({})); NAMESIGNS = ver.name_signs || []; }
    const sl = $('#btn-sheets'); if (sl) { if (ver.sheets) { sl.href = `data/areas/${verifiedKey}/${ver.sheets}`; sl.hidden = false; } else sl.hidden = true; }
    const feats = ver.complete ? [] : await pull(bbox);
    setBar(0.85, 'Matching sign codes');
    const byId = new Map();
    for (const f of feats) byId.set(f.id, fromClass(f));
    for (const v of (ver.signs || [])) byId.set(v.id, Object.assign(byId.get(v.id) || {}, v));
    signs = [...byId.values()];
    for (const s of signs) if (s.code in SPEED && !s.val) { const m = /(\d{2})/.exec(s.legend || ''); if (m) s.val = m[1]; }
    setBar(0.95, 'Drawing map');
    await rasterFaces();
    map.fitBounds(areaRect.getBounds(), {animate:false}); lastZ = map.getZoom(); draw(); inventory();
    const cnt = k => signs.filter(s => s.status === k).length;
    setBar(1, `Done. ${signs.length} signs: ` + ['verified','review','auto','nomatch','unreadable'].filter(k => cnt(k)).map(k => cnt(k) + ' ' + STATUS_TXT[k].toLowerCase()).join(', ') + (ver.coverage != null ? `. Photos cover ${ver.coverage}% of street length in this area.` : '.'));
  } catch (e) { setBar(0, 'Load failed: ' + e.message + '. Try again.'); console.error(e); }
}
const ready = Promise.all([getJSON('data/library.json?v=' + C.DATA_V), getJSON('data/classmap.json?v=' + C.DATA_V)]).then(([l, c]) => { LIB = l; CLASSMAP = c; });

// ---------- area tools ----------
{ const b0 = $('#btn-test'); C.AREAS.forEach((a, i) => { const b = i ? b0.cloneNode(true) : b0; b.id = i ? '' : 'btn-test'; b.textContent = a.name.split(',')[0]; b.onclick = () => run(a.bbox, a.name, a.key); if (i) b0.parentNode.insertBefore(b, b0.nextSibling); }); }
$('#btn-view').onclick = () => { const b = map.getBounds(); run([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], 'MAP VIEW'); };
$('#btn-draw').onclick = () => {
  const btn = $('#btn-draw'); btn.classList.add('on'); map.dragging.disable(); $('#area-hint').textContent = 'Drag a box on the map.';
  let start, box;
  const down = e => { start = e.latlng; box = L.rectangle([start, start], {color:'#FF6622', weight:2, dashArray:'6 5', fillOpacity:.06}).addTo(map); };
  const move = e => { if (box) box.setBounds([start, e.latlng]); };
  const up = () => { map.off('mousedown', down).off('mousemove', move).off('mouseup', up); map.dragging.enable(); btn.classList.remove('on');
    if (!box) return; const b = box.getBounds(); map.removeLayer(box); $('#area-hint').textContent = 'Box set.';
    run([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], 'DRAWN AREA'); };
  map.on('mousedown', down).on('mousemove', move).on('mouseup', up);
};

// ---------- exports ----------
const today = () => new Date().toLocaleDateString('en-CA');
async function preparePrint() {
  if (!signs.length) { setBar(0, 'Load an area first.'); return false; }
  $('#sheet-title').textContent = 'SIGN INVENTORY';
  const cnt = k => signs.filter(s => s.status === k).length;
  $('#sheet-meta').innerHTML = `<b>${esc(areaName)}</b><br>${today()} &nbsp;|&nbsp; ${signs.length} signs &nbsp;|&nbsp; ` + ['verified','review','auto','nomatch','unreadable'].filter(k => cnt(k)).map(k => cnt(k) + ' ' + STATUS_TXT[k].toLowerCase()).join(', ');
  const rows = groups(); const fit = rows.slice(0, 33);
  $('#sheet-table tbody').innerHTML = fit.map(r => `<tr><td class="pic">${r.code ? `<img src="${pic(r.list[0])}" alt="">` : ''}</td><td class="code">${esc(label(r))}</td><td>${esc(nameOf(r))}</td><td class="qty">${r.n}</td></tr>`).join('');
  $('#sheet-notes').textContent = (rows.length > fit.length ? `${rows.length - fit.length} more code${rows.length - fit.length === 1 ? '' : 's'} in the Excel export. ` : '') +
    'Sources: street-level imagery, Mapillary (CC BY-SA); aerial, Esri. Codes per CA MUTCD 2026. Signs found by scanning every photo, placed from several views, read twice and checked against the standard sign face.';
  document.body.classList.add('printing'); zoomClass();
  const el = $('#map'); el.style.flex = 'none'; el.style.width = '1046px'; el.style.height = '979px'; map.invalidateSize();
  map.options.zoomSnap = 0.25; map.closePopup();
  const sb = L.latLngBounds(signs.map(s => [s.lat, s.lon]));
  map.fitBounds(sb.pad(0.06), {padding:[30,30], animate:false});
  lastZ = map.getZoom(); draw();
  await document.fonts.ready;
  $('#print-map').src = await renderPrintMap(1046, 979);
}
$('#btn-pdf').onclick = async () => { if (await preparePrint() !== false) window.print(); };
window.addEventListener('afterprint', () => { map.options.zoomSnap = 1; const el = $('#map'); el.style.flex = ''; el.style.width = ''; el.style.height = ''; document.body.classList.remove('printing'); zoomClass(); map.invalidateSize(); });

$('#btn-xlsx').onclick = async () => {
  if (!signs.length) { setBar(0, 'Load an area first.'); return; }
  setBar(1, 'Building Excel file');
  if (!window.ExcelJS) await new Promise((res, rej) => { const s = document.createElement('script'); s.src = 'https://cdn.jsdelivr.net/npm/exceljs@4.4.0/dist/exceljs.min.js'; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
  const wb = new ExcelJS.Workbook(); const F = {name:'Albert Sans', size:10, color:{argb:'FF00242E'}};
  const sheet = (name, cols, data) => {
    const ws = wb.addWorksheet(name, {views:[{state:'frozen', ySplit:1}]});
    ws.columns = cols.map(([h, w]) => ({header:h, width:w}));
    data.forEach(r => ws.addRow(r));
    ws.eachRow((row, i) => row.eachCell({includeEmpty:true}, c => {
      c.font = i === 1 ? {...F, bold:true, color:{argb:'FFFFFFFF'}} : F;
      c.alignment = {vertical:'middle', wrapText:true};
      if (i === 1) c.fill = {type:'pattern', pattern:'solid', fgColor:{argb:'FF00574A'}};
      else if (i % 2 === 1) c.fill = {type:'pattern', pattern:'solid', fgColor:{argb:'FFF2F2F2'}};
    }));
    ws.getRow(1).height = 20;
  };
  sheet('SUMMARY', [['CODE',16],['SIGN',40],['QTY',8]], groups().map(r => [label(r), nameOf(r), r.n]));
  sheet('SIGNS', [['ID',10],['CODE',12],['SIGN',32],['VALUE',8],['APPROACH',34],['STATUS',16],['CONFIDENCE',11],['LAT',11],['LON',12],['FACING',8],['PHOTO YEARS',14],['PHOTO',40],['STREET VIEW',40]],
    signs.map(s => [s.id, s.code || '', s.code ? LIB[s.code]?.n || '' : (s.cls || ''), s.val || '', s.loc || '', STATUS_TXT[s.status], s.conf || '', +s.lat.toFixed(6), +s.lon.toFixed(6), s.dir != null ? Math.round(s.dir) : '', (s.years || [s.seen]).join(', '), mly(s), sv(s)]));
  if (NAMESIGNS.length) sheet('STREET NAME SIGNS', [['TYPE',12],['LOCATION',40],['PHOTO YEAR',12],['LAT',11],['LON',12]], NAMESIGNS.map(n => [n.kind === 'GUIDE' ? 'GUIDE' : 'STREET NAME', n.loc, n.seen, +n.lat.toFixed(6), +n.lon.toFixed(6)]));
  const buf = await wb.xlsx.writeBuffer();
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([buf], {type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
  a.download = `${today()}_SIGN-INVENTORY_${areaName.replace(/[^A-Z0-9]+/gi, '-').replace(/-+$/, '').toUpperCase()}.xlsx`; a.click();
  setBar(1, 'Excel file downloaded.');
};
// link parameters: ?area=hds opens the test area; &print=1 sets the 11x17 sheet layout (for PDF export tools)
const Q = new URLSearchParams(location.search);
const QA = C.AREAS.find(a => a.key === Q.get('area'));
if (QA) run(QA.bbox, QA.name, QA.key).then(() => { if (Q.get('print') === '1') setTimeout(preparePrint, 600); });
})();
