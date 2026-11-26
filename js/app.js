(() => {
'use strict';
const C = window.CFG;
const $ = s => document.querySelector(s);
const STATUS_TXT = {verified:'VERIFIED', auto:'AUTO', nomatch:'NO CODE', unreadable:'UNREADABLE'};
let LIB = {}, CLASSMAP = {}, signs = [], area = null, areaName = '', layer, areaRect;

// ---------- map ----------
const map = L.map('map', {zoomControl:true, preferCanvas:false}).setView([34.0835,-118.1860], 16);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
  maxZoom: 21, maxNativeZoom: 19,
  attribution: 'Aerial: Esri, Maxar, Earthstar Geographics | Signs: Mapillary (CC BY-SA)'
}).addTo(map);
layer = L.layerGroup().addTo(map);
const zoomClass = () => {
  const z = map.getZoom(), el = $('#map');
  el.classList.toggle('z-lo', z < 17);
  el.classList.toggle('z-mid', z === 17);
};
map.on('zoomend', zoomClass); zoomClass();

// ---------- helpers ----------
const setBar = (p, t) => { $('#bar-fill').style.width = Math.round(p*100) + '%'; if (t) $('#status').textContent = t; };
const sprite = code => LIB[code] ? `data/sprites/${LIB[code].s}.webp` : '';
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
  const pic = s.code && LIB[s.code] ? `<img src="${sprite(s.code)}" alt="">` : `<b>?</b>`;
  const lab = s.code ? s.code + (s.val ? ` (${s.val})` : '') : STATUS_TXT[s.status];
  const dir = s.dir != null ? `<div class="dir" style="transform:rotate(${s.dir}deg)"></div>` : '';
  return L.divIcon({className:'', iconSize:[28,28], iconAnchor:[14,14],
    html:`<div class="sg st-${s.status}">${dir}<div class="ico">${pic}</div><div class="lab">${esc(lab)}</div></div>`});
}
const PRI = {verified:0, auto:1, nomatch:2, unreadable:3};
function poleIcon(g) {
  const show = g.slice(0, 4);
  const icos = show.map(s => `<div class="ico st-${s.status}">${s.code && LIB[s.code] ? `<img src="${sprite(s.code)}" alt="">` : '<b>?</b>'}</div>`).join('');
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
function draw() {
  layer.clearLayers();
  // group signs whose screen positions fall within 34 px (same pole or same corner)
  const z = map.getZoom(), R = z >= 20 ? 30 : z >= 19 ? 46 : 64, groupsArr = [];
  const pts = signs.map(s => ({s, p: map.project([s.lat, s.lon], z)})).sort((a, b) => PRI[a.s.status] - PRI[b.s.status]);
  for (const o of pts) {
    const g = groupsArr.find(g => g.p.distanceTo(o.p) < R);
    if (g) g.list.push(o.s); else groupsArr.push({p: o.p, list: [o.s]});
  }
  for (const g of groupsArr) {
    const ll = map.unproject(g.p, z);
    if (g.list.length === 1) {
      const s = g.list[0], m = L.marker(ll, {icon: icon(s), riseOnHover:true});
      m.on('click', () => openSign(s, ll)); s.m = m; m.addTo(layer); continue;
    }
    const m = L.marker(ll, {icon: poleIcon(g.list), riseOnHover:true});
    m.on('click', () => {
      const html = '<div class="plist">' + g.list.map((s, i) => `<div data-i="${i}">${s.code && LIB[s.code] ? `<img src="${sprite(s.code)}" alt="">` : '<b>?</b>'}<span><b>${esc(s.code || STATUS_TXT[s.status])}</b>${s.val ? ' (' + esc(s.val) + ')' : ''}</span><i>${STATUS_TXT[s.status]}</i></div>`).join('') + '</div>';
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
  const crop = s.crop ? `<img class="crop" src="data/verified/crops/${s.crop}" alt="">` : `<div class="crop" id="crop-${s.id}"></div>`;
  return `<div class="pop">
    <div class="row">${L0 ? `<img class="ref" src="${sprite(s.code)}" alt="">` : ''}
      <div><h3>${esc(s.code || STATUS_TXT[s.status])}</h3><div class="nm">${esc(L0 ? L0.n : (s.cls || ''))}</div></div></div>
    ${crop}
    <table>
      <tr><td>STATUS</td><td><b>${STATUS_TXT[s.status]}</b>${s.conf ? ' / ' + esc(s.conf) : ''}</td></tr>
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
    const key = s.code ? s.code : STATUS_TXT[s.status];
    const r = g.get(key) || {key, code: s.code, n: 0, arrows: new Set(), list: [], status: s.status};
    r.n++; if (s.arrow === 'L' || s.arrow === 'R') r.arrows.add(s.arrow); r.list.push(s); g.set(key, r);
  }
  return [...g.values()].sort((a, b) => (!a.code) - (!b.code) || a.key.localeCompare(b.key, undefined, {numeric:true}));
}
const label = r => r.code ? r.key + (r.arrows.size === 2 ? ' (LT/RT)' : r.arrows.has('L') ? ' (LT)' : r.arrows.has('R') ? ' (RT)' : '') : r.key;
const nameOf = r => r.code ? LIB[r.code]?.n || '' : (r.status === 'nomatch' ? 'Sign with no standard code' : 'Sign could not be read');
function rowsHTML() {
  return groups().map(r => `<tr data-k="${esc(r.key)}"><td class="pic">${r.code ? `<img src="${sprite(r.code)}" alt="">` : ''}</td>
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
    if (verifiedKey) { setBar(0.08, 'Loading verified signs'); ver = await getJSON(`data/verified/${verifiedKey}.json?v=${C.DATA_V}`).catch(() => ({})); }
    const feats = await pull(bbox);
    setBar(0.85, 'Matching sign codes');
    const byId = new Map();
    for (const f of feats) byId.set(f.id, fromClass(f));
    for (const v of (ver.signs || [])) byId.set(v.id, Object.assign(byId.get(v.id) || {}, v));
    signs = [...byId.values()];
    setBar(0.95, 'Drawing map');
    map.fitBounds(areaRect.getBounds()); lastZ = map.getZoom(); draw(); inventory();
    const cnt = k => signs.filter(s => s.status === k).length;
    setBar(1, `Done. ${signs.length} signs: ${cnt('verified')} verified, ${cnt('auto')} auto, ${cnt('nomatch')} no code, ${cnt('unreadable')} unreadable.`);
  } catch (e) { setBar(0, 'Load failed: ' + e.message + '. Try again.'); console.error(e); }
}
const ready = Promise.all([getJSON('data/library.json?v=' + C.DATA_V), getJSON('data/classmap.json?v=' + C.DATA_V)]).then(([l, c]) => { LIB = l; CLASSMAP = c; });

// ---------- area tools ----------
$('#btn-test').onclick = () => run(C.TEST.bbox, C.TEST.name, C.TEST.key);
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
const today = () => new Date().toISOString().slice(0,10);
async function preparePrint() {
  if (!signs.length) { setBar(0, 'Load an area first.'); return false; }
  $('#sheet-title').textContent = 'SIGN INVENTORY';
  const cnt = k => signs.filter(s => s.status === k).length;
  $('#sheet-meta').innerHTML = `<b>${esc(areaName)}</b><br>${today()} &nbsp;|&nbsp; ${signs.length} signs &nbsp;|&nbsp; ${cnt('verified')} verified, ${cnt('auto')} auto, ${cnt('nomatch')} no code, ${cnt('unreadable')} unreadable`;
  const rows = groups(); const fit = rows.slice(0, 30);
  $('#sheet-table tbody').innerHTML = fit.map(r => `<tr><td class="pic">${r.code ? `<img src="${sprite(r.code)}" alt="">` : ''}</td><td class="code">${esc(label(r))}</td><td>${esc(nameOf(r))}</td><td class="qty">${r.n}</td></tr>`).join('');
  $('#sheet-notes').textContent = (rows.length > fit.length ? `${rows.length - fit.length} more codes in the Excel export. ` : '') +
    'Sources: street-level imagery and sign positions, Mapillary (CC BY-SA); aerial, Esri. Codes per CA MUTCD 2026. Verified signs read from photos and checked against the standard sign face.';
  document.body.classList.add('printing');
  const el = $('#map'); el.style.width = '1046px'; el.style.height = '979px'; map.invalidateSize();
  map.fitBounds(areaRect.getBounds(), {padding:[10,10]});
  await new Promise(r => setTimeout(r, 1800));
}
$('#btn-pdf').onclick = async () => { if (await preparePrint() !== false) window.print(); };
window.addEventListener('afterprint', () => { const el = $('#map'); el.style.width = ''; el.style.height = ''; document.body.classList.remove('printing'); map.invalidateSize(); });

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
  sheet('SIGNS', [['ID',18],['CODE',12],['SIGN',32],['VALUE',8],['LEGEND',30],['ARROW',7],['PLAQUE',10],['STATUS',12],['CONFIDENCE',11],['LAT',11],['LON',12],['FACING',8],['PHOTO DATE',12],['PHOTO',40],['STREET VIEW',40]],
    signs.map(s => [s.id, s.code || '', s.code ? LIB[s.code]?.n || '' : '', s.val || '', s.legend || '', s.arrow || '', s.plaque || '', STATUS_TXT[s.status], s.conf || '', +s.lat.toFixed(6), +s.lon.toFixed(6), s.dir != null ? Math.round(s.dir) : '', s.seen || '', mly(s), sv(s)]));
  const buf = await wb.xlsx.writeBuffer();
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([buf], {type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
  a.download = `${today()}_SIGN-INVENTORY_${areaName.replace(/[^A-Z0-9]+/gi, '-').replace(/-+$/, '').toUpperCase()}.xlsx`; a.click();
  setBar(1, 'Excel file downloaded.');
};
// link parameters: ?area=hds opens the test area; &print=1 sets the 11x17 sheet layout (for PDF export tools)
const Q = new URLSearchParams(location.search);
if (Q.get('area') === C.TEST.key) run(C.TEST.bbox, C.TEST.name, C.TEST.key).then(() => { if (Q.get('print') === '1') { document.querySelector('link[media=print]').media = 'all'; preparePrint(); } });
})();
