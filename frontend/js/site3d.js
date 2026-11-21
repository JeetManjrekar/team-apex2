// Construction-site digital twin: 2D engineering plan + 3D isometric view, one Three.js scene.
// Plan coordinates are metres (x = east, y = north). World: X = east, Y = up, Z = -north.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const API = window.API_BASE || "";
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = (u, o = {}) => {
  o.headers = { ...(o.headers || {}), "X-Lang": (() => { try { return localStorage.getItem("nw-lang") === "de" ? "de" : "en"; } catch { return "en"; } })() };
  if (o.json) { o.method = o.method || "POST"; o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(o.json); }
  return fetch(API + u, o).then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || r.statusText); return j; });
};
const P = (x, y, h = 0) => new THREE.Vector3(x, h, -y);
const pct = c => `${Math.round(c * 100)}%`;
const NICE = { excavator: "Excavator", dump_truck: "Dump truck", bulldozer: "Bulldozer", car: "Car", person: "Person", tractor: "Tractor" };
const nice = c => NICE[c?.toLowerCase()] || (c || "").replace(/_/g, " ").replace(/^./, m => m.toUpperCase());
const CLASS_COLOR = { excavator: "#f0901e", dump_truck: "#d65a2a", bulldozer: "#b85c12", car: "#2f6db5", person: "#ff6a00", tractor: "#3c8d3c" };
const classColor = c => CLASS_COLOR[c?.toLowerCase()] || "#7a5cc0";
// blueprint-at-night palette
const C = { paper: 0x071224, site: 0x0c1d36, outside: 0x061020, grid: 0x10284a, gridMajor: 0x1d4274, ink: 0xdbe7ff, road: 0x15253d, acc: 0xff7a00, edge: 0x9fc3ff, holo: 0x4cc9ff, zoneEdge: 0x4f79b5 };
const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const CAM_SVG = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>';

const S = {
  data: null, mode: "2d", built: false, visible: false, sel: null, hover: null, placing: null,
  show: { det: true, lbl: true, pho: true, zon: true }, minConf: 0,
  photoNo: {}, pickables: [], anims: [], touring: false, flying: null, labels: { zone: [], dim: [], struct: [], photo: [], det: [] },
};
let renderer, labelRenderer, scene, camera, controls, root, selRing, ghost, stage, fitSize = 100, center = new THREE.Vector3();
let composer = null, bloom = null, siteBounds = null, fitHalfW = 60;
const lights = {};

/* ------------------------------------------------------------------ setup */
function init() {
  stage = $("#twCanvas");
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  stage.appendChild(renderer.domElement);
  labelRenderer = new CSS2DRenderer();
  labelRenderer.domElement.className = "tw-labels";
  stage.appendChild(labelRenderer.domElement);

  scene = new THREE.Scene();
  scene.background = new THREE.Color(C.paper);
  // studio environment: gives every standard material soft reflections (the "glossy" look)
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(renderer), 0.04).texture;
  camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 5000);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.12;
  controls.screenSpacePanning = true;
  controls.minZoom = 0.3;
  controls.maxZoom = 25;
  controls.addEventListener("change", updateOverlays);

  lights.hemi = new THREE.HemisphereLight(0xbfdcff, 0x0b1428, 1.0);
  lights.sun = new THREE.DirectionalLight(0xffffff, 1.6);
  lights.sun.castShadow = true;
  lights.sun.shadow.mapSize.set(2048, 2048);
  lights.sun.shadow.bias = -0.0005;
  scene.add(lights.hemi, lights.sun, lights.sun.target);

  new ResizeObserver(resize).observe(stage);
  renderer.domElement.addEventListener("pointerdown", onDown);
  renderer.domElement.addEventListener("pointerup", onUp);
  renderer.domElement.addEventListener("pointermove", onMove);
  renderer.domElement.addEventListener("pointerleave", () => setHover(null));
  renderer.domElement.addEventListener("contextmenu", e => { if (S.placing) { e.preventDefault(); finishPlacing(); } });
  addEventListener("keydown", e => { if (e.key === "Escape" && S.placing) finishPlacing(true); });
  renderer.domElement.addEventListener("wheel", () => { if (S.touring) stopTour(); }, { passive: true });
  addEventListener("keydown", e => { if (e.key === "Escape" && S.touring) stopTour(); });
  bindToolbar();
  setupBloom();
  loop();
}

// bloom glow (optional: if the post-processing modules fail to load, plain rendering continues)
async function setupBloom() {
  try {
    const [{ EffectComposer }, { RenderPass }, { UnrealBloomPass }, { OutputPass }] = await Promise.all([
      import("three/addons/postprocessing/EffectComposer.js"), import("three/addons/postprocessing/RenderPass.js"),
      import("three/addons/postprocessing/UnrealBloomPass.js"), import("three/addons/postprocessing/OutputPass.js")]);
    composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    bloom = new UnrealBloomPass(new THREE.Vector2(stage.clientWidth || 800, stage.clientHeight || 600), 0.5, 0.45, 0.62);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());
    applyLook();
    resize();
  } catch (e) { console.warn("bloom disabled:", e); composer = null; }
}

function applyLook() {
  const is3d = S.mode === "3d";
  if (bloom) { bloom.strength = is3d ? 0.6 : 0.42; bloom.threshold = is3d ? 0.86 : 0.8; bloom.radius = 0.5; }
  renderer.toneMappingExposure = is3d ? 1.0 : 0.95;
  scene.fog = is3d ? new THREE.Fog(C.paper, 700, 1300) : null;
}

function bindToolbar() {
  document.querySelectorAll("#twMode button").forEach(b => b.onclick = () => setMode(b.dataset.mode));
  const tog = (id, key) => { $(id).onchange = e => { S.show[key] = e.target.checked; applyVisibility(); }; };
  tog("#twDet", "det"); tog("#twLbl", "lbl"); tog("#twPho", "pho"); tog("#twZon", "zon");
  $("#twConf").oninput = e => { S.minConf = e.target.value / 100; $("#twConfV").textContent = e.target.value + "%"; applyVisibility(); };
  $("#twReset").onclick = () => setMode(S.mode, true);
  $("#twTour").onclick = () => (S.touring ? stopTour() : tour());
  $("#twLayout").onclick = openLayoutEditor;
  $("#twLaySave").onclick = saveLayout;
  $("#twLayReset").onclick = async () => {
    if (!confirm("Replace the site layout with the default bridge-site layout?")) return;
    await api("/api/site/layout/reset", { method: "POST" }); $("#twDlg").close(); await load(true);
  };
  $("#twLayCancel").onclick = () => $("#twDlg").close();
}

function resize() {
  const w = stage.clientWidth, h = stage.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h);
  labelRenderer.setSize(w, h);
  if (composer) { composer.setPixelRatio(renderer.getPixelRatio()); composer.setSize(w, h); }
  const a = w / h, half = Math.max(fitSize, fitHalfW / a);   // fit both width and height (portrait phones)
  camera.left = -half * a; camera.right = half * a; camera.top = half; camera.bottom = -half;
  camera.updateProjectionMatrix();
  updateOverlays();
}

function loop() {
  requestAnimationFrame(loop);
  if (!S.visible) return;
  controls.update();
  const t = performance.now() / 1000;
  if (selRing) { selRing.material.opacity = 0.55 + 0.35 * Math.sin(t * 1.7); selRing.scale.setScalar(1 + 0.04 * Math.sin(t * 3.4)); }
  if (!RM) for (const f of S.anims) f(t);
  if (composer) composer.render(); else renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
  declutter();
}

// CSS2DRenderer re-sorts z-index every frame; keep open cards on top and push overlapping detection chips apart
let frame = 0;
function declutter() {
  stage.querySelectorAll(".twl.open").forEach(el => el.style.zIndex = 100000);
  if (frame++ % 3) return;
  const els = [...stage.querySelectorAll(".twl.det:not(.open), .twl.photo")].filter(el => el.style.display !== "none");
  const rects = els.map(el => { const r = el.getBoundingClientRect(), m = parseFloat(el.style.marginTop) || 0; return { el, l: r.left, r: r.right, t: r.top - m, b: r.bottom - m }; })
    .sort((a, b) => b.t - a.t);
  const placed = [];
  for (const q of rects) {
    let shift = 0, moved = true;
    while (moved) {
      moved = false;
      for (const o of placed) if (q.l < o.r && q.r > o.l && q.t + shift < o.b && q.b + shift > o.t) { shift = o.t - q.b - 2; moved = true; }
    }
    q.el.style.marginTop = shift + "px";
    placed.push({ l: q.l, r: q.r, t: q.t + shift, b: q.b + shift });
  }
}

/* ------------------------------------------------------------------ data */
async function load(keepView) {
  try {
    S.data = await api("/api/site/twin");
  } catch (e) {
    $("#twSide").innerHTML = `<div class="pad"><b>Site plan could not be loaded</b><p class="mut">${esc(e.message)}</p></div>`;
    return;
  }
  const order = [...S.data.photos].sort((a, b) => (a.taken_at || "").localeCompare(b.taken_at || "") || a.id.localeCompare(b.id));
  S.photoNo = Object.fromEntries(order.map((p, i) => [p.id, `P${i + 1}`]));
  build();
  if (!keepView || !S.built) setMode(S.mode, true);
  S.built = true;
  restoreSelection();
}

const photo = id => S.data.photos.find(p => p.id === id);
const zone = id => S.data.layout.zones.find(z => z.id === id);
const zoneSum = id => S.data.zones.find(z => z.id === id);
const act = id => S.data.schedule.find(a => a.id === id);
const frac = id => { const a = act(id); return a && a.total ? Math.max(0, Math.min(1, a.actual / a.total)) : 0; };

/* ------------------------------------------------------------------ geometry helpers */
const mat = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.42, metalness: 0.25, envMapIntensity: 0.9, ...o });
const flat = (color, o = {}) => new THREE.MeshBasicMaterial({ color, ...o });

function poly(points, color, h, o = {}) {
  const shape = new THREE.Shape(points.map(([x, y]) => new THREE.Vector2(x, y)));
  const g = new THREE.ShapeGeometry(shape);
  g.rotateX(-Math.PI / 2);
  const m = new THREE.Mesh(g, o.basic ? flat(color, o.m) : mat(color, o.m));
  m.position.y = h;
  m.receiveShadow = true;
  return m;
}

// thick line as flat quads (WebGL lines are 1px); optional dash pattern [dash, gap]
function ribbon(points, width, color, h, o = {}) {
  const grp = new THREE.Group();
  const material = flat(color, { transparent: o.opacity != null, opacity: o.opacity ?? 1, depthWrite: o.opacity == null });
  const pts = o.closed ? [...points, points[0]] : points;
  const seg = (a, b) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy);
    if (len < 1e-6) return;
    const m = new THREE.Mesh(new THREE.PlaneGeometry(len, width), material);
    m.rotation.x = -Math.PI / 2;
    m.rotation.z = Math.atan2(dy, dx);
    m.position.copy(P((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, h));
    grp.add(m);
  };
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i], b = pts[i + 1];
    if (!o.dash) { seg(a, b); continue; }
    const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy), [d, gap] = o.dash;
    for (let t = 0; t < len; t += d + gap) {
      const t2 = Math.min(len, t + d);
      seg([a[0] + dx * t / len, a[1] + dy * t / len], [a[0] + dx * t2 / len, a[1] + dy * t2 / len]);
    }
  }
  if (!o.dash) for (let i = o.closed ? 0 : 1; i < pts.length - 1; i++) {   // round joints
    const j = new THREE.Mesh(new THREE.CircleGeometry(width / 2, 16), material);
    j.rotation.x = -Math.PI / 2; j.position.copy(P(pts[i][0], pts[i][1], h)); grp.add(j);
  }
  return grp;
}

function withEdges(mesh, o = {}) {
  const e = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 20),
    o.dashed ? new THREE.LineDashedMaterial({ color: o.color ?? C.holo, dashSize: 0.8, gapSize: 0.6, transparent: true, opacity: o.opacity ?? 0.9 })
             : new THREE.LineBasicMaterial({ color: o.color ?? C.edge, transparent: true, opacity: o.opacity ?? 0.32 }));
  if (o.dashed) e.computeLineDistances();
  mesh.add(e);
  return mesh;
}

function box(w, d, h, color, o = {}) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), o.material || mat(color, o.m));
  m.castShadow = !o.noShadow; m.receiveShadow = true;
  if (o.edges !== false) withEdges(m, o.edgeOpts);
  return m;
}

function place(obj, x, y, z = 0, rotDeg = 0) {
  obj.position.copy(P(x, y, z));
  obj.rotation.y = rotDeg * Math.PI / 180;
  return obj;
}

function label(html, cls, x, y, z, group) {
  const el = document.createElement("div");
  el.className = "twl " + cls;
  el.innerHTML = html;
  const o = new CSS2DObject(el);
  o.position.copy(P(x, y, z));
  root.add(o);
  if (group) S.labels[group].push(o);
  return o;
}

function pickable(obj, type, id, extra = {}) {
  obj.traverse(c => { c.userData.pick = { type, id, ...extra }; });
  obj.userData.pick = { type, id, ...extra };
  S.pickables.push(obj);
  return obj;
}

/* ------------------------------------------------------------------ equipment models (low-poly, from primitives) */
function cyl(r, h, color, axis = "y") {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 18), mat(color));
  if (axis === "z") m.rotation.x = Math.PI / 2;
  m.castShadow = true;
  return m;
}
function part(w, d, h, color, x, y, z, o) { const b = box(w, d, h, color, o); b.position.set(x, y + h / 2, z); return b; }

const MODELS = {
  excavator(col) {
    const g = new THREE.Group();
    g.add(part(4.6, 0.8, 0.9, 0x34312c, 0, 0, 1.25), part(4.6, 0.8, 0.9, 0x34312c, 0, 0, -1.25), part(2.6, 2.2, 0.4, 0x4a463f, 0, 0.9, 0));
    const up = new THREE.Group(); up.position.y = 1.3; up.rotation.y = 0.35; g.add(up);
    up.add(part(3.2, 2.5, 1.2, col, -0.4, 0, 0), part(1.2, 1.0, 1.5, col, 0.8, 1.2, 0.7), part(1.0, 2.4, 0.9, 0x3b3833, -1.9, 0.1, 0));
    const boom = part(3.8, 0.55, 0.6, col, 0, 0, 0); boom.position.set(2.2, 1.9, -0.4); boom.rotation.z = 0.55; up.add(boom);
    const arm = part(2.6, 0.45, 0.45, col, 0, 0, 0); arm.position.set(4.2, 2.1, -0.4); arm.rotation.z = -1.0; up.add(arm);
    const bucket = part(0.9, 1.1, 0.8, 0x3b3833, 0, 0, 0); bucket.position.set(4.9, 0.2, -0.4); up.add(bucket);
    return g;
  },
  dump_truck(col) {
    const g = new THREE.Group();
    g.add(part(7.8, 2.2, 0.5, 0x3b3833, 0, 0.6, 0), part(1.9, 2.4, 2.2, col, 3.0, 1.1, 0));
    const bed = new THREE.Group(); bed.position.set(-1.0, 1.1, 0); g.add(bed);
    bed.add(part(5.4, 2.5, 0.25, 0x8d939b, 0, 0, 0), part(5.4, 0.15, 1.3, 0x8d939b, 0, 0.25, 1.2), part(5.4, 0.15, 1.3, 0x8d939b, 0, 0.25, -1.2),
      part(0.15, 2.5, 1.3, 0x8d939b, 2.65, 0.25, 0), part(0.15, 2.5, 1.0, 0x8d939b, -2.65, 0.25, 0));
    for (const x of [2.9, -0.9, -2.5]) for (const z of [1.15, -1.15]) { const w = cyl(0.55, 0.45, 0x1f1f1f, "z"); w.position.set(x, 0.55, z); g.add(w); }
    return g;
  },
  bulldozer(col) {
    const g = new THREE.Group();
    g.add(part(4.0, 0.7, 1.0, 0x34312c, 0, 0, 1.1), part(4.0, 0.7, 1.0, 0x34312c, 0, 0, -1.1), part(3.2, 1.8, 1.2, col, -0.2, 1.0, 0),
      part(1.4, 1.5, 1.3, col, -0.9, 2.2, 0), part(0.35, 3.6, 1.3, 0x5c5850, 2.5, 0.1, 0));
    return g;
  },
  tractor(col) {
    const g = new THREE.Group();
    g.add(part(3.2, 1.3, 1.0, col, 0.2, 0.8, 0), part(1.3, 1.4, 1.5, col, -0.8, 1.8, 0));
    for (const z of [1.0, -1.0]) { const r = cyl(0.85, 0.5, 0x1f1f1f, "z"); r.position.set(-0.8, 0.85, z); g.add(r);
      const f = cyl(0.5, 0.35, 0x1f1f1f, "z"); f.position.set(1.4, 0.5, z * 0.9); g.add(f); }
    return g;
  },
  car(col) {
    const g = new THREE.Group();
    g.add(part(4.4, 1.8, 0.8, col, 0, 0.35, 0), part(2.2, 1.6, 0.6, 0xbcc7d3, -0.2, 1.15, 0));
    for (const x of [1.4, -1.4]) for (const z of [0.85, -0.85]) { const w = cyl(0.35, 0.25, 0x1f1f1f, "z"); w.position.set(x, 0.35, z); g.add(w); }
    return g;
  },
  person(col) {
    const g = new THREE.Group();
    const b = cyl(0.25, 1.3, col); b.position.y = 0.65; g.add(b);
    const h = new THREE.Mesh(new THREE.SphereGeometry(0.2, 14, 10), mat(0xff7a00)); h.position.y = 1.55; h.castShadow = true; g.add(h);
    return g;
  },
  generic(col) { const g = new THREE.Group(); g.add(part(3, 2, 2, col, 0, 0, 0)); return g; },
};
const FOOTPRINT = { excavator: 3.4, dump_truck: 4.4, bulldozer: 2.8, tractor: 2.4, car: 2.6, person: 0.8 };

/* ------------------------------------------------------------------ scene build */
function build() {
  if (root) { scene.remove(root); root.traverse(o => { o.geometry?.dispose?.(); if (o.element) o.element.remove(); }); }
  root = new THREE.Group(); scene.add(root);
  S.pickables = []; S.anims = []; Object.keys(S.labels).forEach(k => S.labels[k] = []); selRing = null; ghost = null;
  const L = S.data.layout;

  // bounds
  const bnd = L.boundary.length >= 3 ? L.boundary : [[-30, -20], [30, -20], [30, 20], [-30, 20]];   // empty layout: neutral view window only, nothing drawn
  const xs = bnd.map(p => p[0]), ys = bnd.map(p => p[1]);
  const b = { x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) };
  const unplaced = S.data.photos.filter(p => !p.plan_xy);
  const stripY = b.y0 - 14;
  const yLow = unplaced.length ? stripY - 8 : b.y0;
  center = P((b.x0 + b.x1) / 2, (yLow + b.y1) / 2 + 4);
  fitSize = Math.max((b.x1 - b.x0) * 0.44, (b.y1 - yLow) * 0.62, 20);
  fitHalfW = (b.x1 - b.x0) * 0.56;
  const span = Math.max(b.x1 - b.x0, b.y1 - yLow);
  const sun = lights.sun;
  sun.position.copy(center).add(new THREE.Vector3(-span * 0.6, span * 1.1, span * 0.4));
  sun.target.position.copy(center);
  Object.assign(sun.shadow.camera, { left: -span, right: span, top: span, bottom: -span, near: 1, far: span * 4 });
  sun.shadow.camera.updateProjectionMatrix();

  // ground + grid (minor 2 m, major 10 m)
  const pad = 30, gx0 = Math.floor((b.x0 - pad) / 10) * 10, gx1 = Math.ceil((b.x1 + pad) / 10) * 10;
  const gy0 = Math.floor((yLow - pad) / 10) * 10, gy1 = Math.ceil((b.y1 + pad) / 10) * 10;
  const ground = poly([[gx0, gy0], [gx1, gy0], [gx1, gy1], [gx0, gy1]], C.outside, -0.02);
  root.add(ground);
  const minor = [], major = [];
  for (let x = gx0; x <= gx1; x += 2) (x % 10 ? minor : major).push(P(x, gy0, 0.005), P(x, gy1, 0.005));
  for (let y = gy0; y <= gy1; y += 2) (y % 10 ? minor : major).push(P(gx0, y, 0.005), P(gx1, y, 0.005));
  root.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(minor), new THREE.LineBasicMaterial({ color: C.grid, transparent: true, opacity: 0.6 })));
  root.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(major), new THREE.LineBasicMaterial({ color: C.gridMajor })));

  // site surface + boundary (property line: thick dash-dot) + fence in 3D
  const hasBoundary = L.boundary.length >= 3;
  const siteFloor = hasBoundary ? poly(L.boundary, C.site, 0.0, { m: { roughness: 0.38, metalness: 0.5, envMapIntensity: 0.32 } }) : null;   // reflective deck
  if (hasBoundary) { root.add(siteFloor); root.add(ribbon(L.boundary, 0.7, C.ink, 0.06, { closed: true })); }
  siteBounds = b;
  addSweep(b);
  const fence = new THREE.Group();
  (hasBoundary ? L.boundary : []).forEach((a, i) => {
    const c = L.boundary[(i + 1) % L.boundary.length], len = Math.hypot(c[0] - a[0], c[1] - a[1]);
    const f = new THREE.Mesh(new THREE.PlaneGeometry(len, 2.4), flat(C.holo, { transparent: true, opacity: 0.12, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending }));
    f.position.copy(P((a[0] + c[0]) / 2, (a[1] + c[1]) / 2, 1.2)); f.rotation.y = Math.atan2(c[1] - a[1], c[0] - a[0]);
    fence.add(f);
    // dimension label, offset outward
    const mx = (a[0] + c[0]) / 2, my = (a[1] + c[1]) / 2, nx = (c[1] - a[1]) / len, ny = -(c[0] - a[0]) / len;
    const cx = (b.x0 + b.x1) / 2, cy = (b.y0 + b.y1) / 2, out = ((mx - cx) * nx + (my - cy) * ny) > 0 ? 1 : -1;
    label(`${len.toFixed(1)} m`, "dim", mx + nx * 4 * out, my + ny * 4 * out, 0.1, "dim");
  });
  fence.name = "fence"; root.add(fence);

  // zones: light fill + internal division lines + label
  for (const z of L.zones) {
    const m = poly(z.polygon, new THREE.Color(z.color || "#888"), 0.02, { basic: true, m: { transparent: true, opacity: 0.09, depthWrite: false } });
    m.userData.baseOpacity = 0.09; m.name = "zone:" + z.id;
    root.add(pickable(m, "zone", z.id));
    const edge = ribbon(z.polygon, 0.28, C.zoneEdge, 0.04, { closed: true, dash: z.kind === "future" ? [2.2, 1.2] : null });
    edge.name = "zoneEdge"; root.add(edge);
    const zx = Math.min(...z.polygon.map(q => q[0])), zy = Math.max(...z.polygon.map(q => q[1])), zs = zoneSum(z.id);
    const n = zs ? zs.photos.length : 0, m2 = zs ? zs.machinery.reduce((s, x) => s + x.count, 0) : 0;
    label(`<div class="tl"><b>${esc(z.name)}</b><span>${n} photo${n === 1 ? "" : "s"} · ${m2} object${m2 === 1 ? "" : "s"}</span></div>`, "zone", zx + 1.5, zy - 1.5, 0.1, "zone")
      .element.addEventListener("click", () => select({ type: "zone", id: z.id }));
  }

  // roads + gates
  for (const r of L.roads) {
    if (r.points.length < 2) continue;
    root.add(ribbon(r.points, r.width || 5, C.road, 0.03));
    root.add(ribbon(r.points, 0.18, 0x6f93c4, 0.035, { dash: [2, 2] }));
    const i = Math.floor((r.points.length - 1) / 2), a = r.points[i], c = r.points[i + 1];
    label(esc(r.name || "Road"), "road", (a[0] + c[0]) / 2, (a[1] + c[1]) / 2, 0.1, "struct");
  }
  for (const g of L.gates || []) {
    for (const dx of [-3.5, 3.5]) root.add(place(box(0.5, 0.5, 2.2, 0x3b3833), g.at[0] + dx, g.at[1], 1.1));
    label(`▲ ${esc(g.name)}`, "gate", g.at[0], g.at[1] - 4, 0.1, "struct");
  }

  // structures
  for (const s of L.structures) buildStructure(s);

  // photos
  for (const p of S.data.photos) if (p.plan_xy) buildPhoto(p, p.plan_xy, false);
  if (unplaced.length) {
    const gap = Math.max(8, Math.min(16, (b.x1 - b.x0 - 12) / Math.max(1, unplaced.length - 1)));
    root.add(ribbon([[b.x0, stripY + 5], [b.x0 + Math.max(60, unplaced.length * gap + 10), stripY + 5]], 0.15, 0x8a8780, 0.03, { dash: [1.5, 1] }));
    label(`<div class="tl">PHOTOS WITHOUT GPS — select one, then “Place on plan”</div>`, "strip", b.x0, stripY + 8, 0.1, "photo");
    unplaced.forEach((p, i) => buildPhoto(p, [b.x0 + 6 + i * gap, stripY], true));
  }

  // AI detections
  for (const p of S.data.photos) if (p.plan_xy) for (const d of p.detections) if (d.xy) buildDetection(p, d);

  renderLegend();
  applyVisibility();
  applyHighlights();
}

function centroid(pts) {
  let a = 0, cx = 0, cy = 0;
  pts.forEach((p, i) => { const q = pts[(i + 1) % pts.length], f = p[0] * q[1] - q[0] * p[1]; a += f; cx += (p[0] + q[0]) * f; cy += (p[1] + q[1]) * f; });
  return a ? [cx / (3 * a), cy / (3 * a)] : pts[0];
}

function buildStructure(s) {
  const g = new THREE.Group(); g.name = "struct:" + s.id;
  const planned = !!s.planned;
  const ghostMat = () => mat(C.holo, { transparent: true, opacity: 0.1, depthWrite: false, emissive: C.holo, emissiveIntensity: 0.22, blending: THREE.AdditiveBlending });
  const f = s.activity ? frac(s.activity) : 1;
  let lx = s.x, ly = s.y, lz = 0.2;
  switch (s.kind) {
    case "container": {
      const h1 = 2.6, n = Math.max(1, Math.round((s.h || 2.6) / h1));
      for (let i = 0; i < n; i++) g.add(place(box(s.w, s.d, h1 - 0.05, i ? 0x4a6894 : 0x9aa9bf), 0, 0, h1 / 2 + i * h1));
      place(g, s.x, s.y, 0, s.rot || 0); lz = n * h1 + 0.5; break;
    }
    case "stockpile": {
      const col = s.activity === "rebar" ? 0x8a5a3c : 0xb79a6b;
      for (let i = 0; i < 4; i++) g.add(place(box(s.w - i * 0.2, s.d / 4 - 0.3, s.h, col, { edgeOpts: { opacity: 0.3 } }), 0, -s.d / 2 + s.d / 8 + i * s.d / 4, s.h / 2));
      place(g, s.x, s.y, 0, s.rot || 0); break;
    }
    case "crane": {
      const yel = 0xff8a1f, jib = s.jib || 40, h = s.h || 30;
      g.add(place(box(4, 4, 1, 0x8d939b), 0, 0, 0.5));
      const mast = box(1.6, 1.6, h, yel, { m: { transparent: true, opacity: 0.35 }, edgeOpts: { color: 0x7a3a00, opacity: 0.9 } });
      g.add(place(mast, 0, 0, h / 2));
      const top = new THREE.Group(); top.position.y = h; top.rotation.y = (s.rot || 0) * Math.PI / 180; g.add(top);
      const j = box(jib, 1.2, 1.2, yel); j.position.set(jib / 2, 0.6, 0); top.add(j);
      const cj = box(jib * 0.3, 1.2, 1.2, yel); cj.position.set(-jib * 0.15, 0.6, 0); top.add(cj);
      const cw = box(3, 2, 2, 0x8d939b); cw.position.set(-jib * 0.27, -0.6, 0); top.add(cw);
      const cab = box(2, 2, 2, 0x5d6d7e); cab.position.set(1.4, -1.0, 1.2); top.add(cab);
      place(g, s.x, s.y);
      // reach circle on the ground (plan convention)
      const pts = [];
      for (let i = 0; i <= 96; i++) { const a = i / 96 * Math.PI * 2; pts.push([s.x + jib * Math.cos(a), s.y + jib * Math.sin(a)]); }
      const reach = ribbon(pts, 0.2, 0xc2610c, 0.045, { dash: [1.6, 1.2] }); reach.name = "reach"; root.add(reach);
      lz = h + 3; break;
    }
    case "pile_row": {
      const n = s.count || 10, done = Math.floor(act(s.activity)?.actual ?? 0), light = act(s.activity)?.light;
      for (let i = 0; i < n; i++) {
        const t = n === 1 ? 0.5 : i / (n - 1), x = s.x1 + (s.x2 - s.x1) * t, y = s.y1 + (s.y2 - s.y1) * t;
        const state = i < done ? "done" : i === done ? "current" : "planned";
        const col = state === "done" ? 0x34d399 : state === "current" ? (light === "red" ? 0xf87171 : 0xff9a1f) : C.holo;
        const pile = new THREE.Mesh(new THREE.CylinderGeometry(s.diameter / 2 * 1.6, s.diameter / 2 * 1.6, state === "planned" ? 0.1 : 1.4, 24),
          state === "planned" ? ghostMat() : mat(col, { emissive: col, emissiveIntensity: state === "current" ? 0.9 : 0.35 }));
        if (state === "current") { const ph = i; S.anims.push(t => { pile.material.emissiveIntensity = 0.5 + 0.6 * (0.5 + 0.5 * Math.sin(t * 4 + ph)); }); }
        pile.castShadow = state !== "planned";
        place(pile, x, y, state === "planned" ? 0.06 : 0.7);
        const ring = new THREE.Mesh(new THREE.RingGeometry(s.diameter * 0.8, s.diameter * 0.8 + 0.18, 32), flat(col));
        ring.rotation.x = -Math.PI / 2; place(ring, x, y, 0.07); ring.rotation.x = -Math.PI / 2;
        root.add(ring);
        g.add(pile);
        label(`${i + 1}`, "pile " + state, x, y - 2.2, 0.1, "struct");
      }
      lx = (s.x1 + s.x2) / 2; ly = (s.y1 + s.y2) / 2 - 4.5; lz = 0.1; break;
    }
    case "beam": case "abutment": {
      const full = box(s.w, s.d, s.h, 0, { material: ghostMat(), edgeOpts: { dashed: true, color: C.holo } });
      g.add(place(full, 0, 0, s.h / 2));
      if (!planned && f > 0) {
        // built part: beam grows in length (rebar progress), abutment in height (formwork progress)
        const built = s.kind === "beam" ? box(s.w * f, s.d, s.h, 0x8fa0b8) : box(s.w, s.d, s.h * f, 0x8fa0b8);
        g.add(s.kind === "beam" ? place(built, -s.w / 2 + s.w * f / 2, 0, s.h / 2) : place(built, 0, 0, s.h * f / 2));
      }
      place(g, s.x, s.y, 0, s.rot || 0); lz = s.h + 1.5; break;
    }
    case "deck": {
      const d = box(s.w, s.d, s.h, 0, { material: ghostMat(), edgeOpts: { dashed: true, color: C.holo } });
      d.castShadow = false;
      g.add(place(d, 0, 0, (s.z || 6) + s.h / 2));
      place(g, s.x, s.y, 0, s.rot || 0); lx = s.x + s.w / 2 + 6; lz = (s.z || 6) + s.h + 1; break;
    }
    case "heap": {
      const cone = new THREE.Mesh(new THREE.ConeGeometry(s.r || 6, s.h || 3, 28), mat(0x8a6a44, { roughness: 0.8, metalness: 0 }));
      cone.castShadow = true; cone.receiveShadow = true; withEdges(cone, { opacity: 0.25 });
      g.add(place(cone, 0, 0, (s.h || 3) / 2)); place(g, s.x, s.y); lz = (s.h || 3) + 1; break;
    }
    default: {
      g.add(place(box(s.w || 4, s.d || 4, s.h || 3, 0xc9c4b5), 0, 0, (s.h || 3) / 2)); place(g, s.x, s.y, 0, s.rot || 0); lz = (s.h || 3) + 1;
    }
  }
  root.add(pickable(g, "structure", s.id));
  if (s.kind !== "pile_row") label(esc(s.name), "struct" + (planned ? " planned" : ""), lx, ly, lz, "struct");
}

function wedge(pos, heading, color, opacity, radius = 16) {
  const half = (S.data.camera.hfov_deg / 2) * Math.PI / 180;
  // CircleGeometry angles are CCW from +x in its own plane; after rotateX(-PI/2) its +y maps to -z (north)
  const startCCW = Math.PI / 2 - heading * Math.PI / 180 - half;
  const g = new THREE.CircleGeometry(radius, 24, startCCW, half * 2);
  g.rotateX(-Math.PI / 2);
  const m = new THREE.Mesh(g, flat(color, { transparent: true, opacity, depthWrite: false, side: THREE.DoubleSide }));
  m.position.copy(P(pos[0], pos[1], 0.05));
  return m;
}

function buildPhoto(p, xy, unplaced) {
  const g = new THREE.Group(); g.name = "photo:" + p.id;
  const col = unplaced ? 0x8a8780 : C.acc;
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 3, 8), mat(0x3b3833)); stem.position.y = 1.5;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.75, 20, 14), mat(col, { emissive: col, emissiveIntensity: unplaced ? 0.2 : 1.4 })); head.position.y = 3.3;
  const disk = new THREE.Mesh(new THREE.RingGeometry(1.1, 1.6, 32), flat(col, { transparent: unplaced, opacity: unplaced ? 0.7 : 1 }));
  disk.rotation.x = -Math.PI / 2; disk.position.y = 0.06;
  const hit = new THREE.Mesh(new THREE.CircleGeometry(1.7, 20), flat(0xffffff, { transparent: true, opacity: 0, depthWrite: false }));
  hit.rotation.x = -Math.PI / 2; hit.position.y = 0.07;
  stem.castShadow = head.castShadow = true;
  g.add(stem, head, disk, hit);
  if (!unplaced) { const ph = Math.random() * 6; S.anims.push(t => { head.position.y = 3.3 + 0.25 * Math.sin(t * 2 + ph); disk.scale.setScalar(1 + 0.12 * Math.sin(t * 2 + ph)); }); }
  place(g, xy[0], xy[1]);
  root.add(pickable(g, "photo", p.id));
  if (!unplaced && p.heading != null) { const w = wedge(xy, p.heading, C.acc, 0.13); w.name = "fov"; root.add(pickable(w, "photo", p.id)); }
  const tag = unplaced ? "" : p.position_method === "gps" ? "GPS" : "plan";
  const l = label(`${CAM_SVG}<b>${S.photoNo[p.id]}</b><span>${tag}</span>`, "photo" + (unplaced ? " unplaced" : ""), xy[0], xy[1], 4.6, "photo");
  l.element.title = `${p.original_name} · ${p.evidence_id}${unplaced ? " · no GPS" : ""}`;
  l.element.addEventListener("click", () => select({ type: "photo", id: p.id }));
}

function buildDetection(p, d) {
  const cls = (d.class || "").toLowerCase(), col = new THREE.Color(classColor(cls));
  const g = new THREE.Group(); g.name = `det:${p.id}:${d.index}`;
  const model = (MODELS[cls] || MODELS.generic)(col);
  // orientation is unknown from a single photo: face the camera
  model.rotation.y = Math.atan2(p.plan_xy[1] - d.xy[1], p.plan_xy[0] - d.xy[0]);
  g.add(model);
  const r = FOOTPRINT[cls] || 2.5;
  const ring = new THREE.Mesh(new THREE.RingGeometry(r, r + 0.35, 40), flat(col, { transparent: true, opacity: 0.85 }));
  ring.rotation.x = -Math.PI / 2; ring.position.y = 0.08; g.add(ring);
  const ph = Math.random() * 6; S.anims.push(t => { const k = 0.5 + 0.5 * Math.sin(t * 2.6 + ph); ring.scale.setScalar(1 + 0.18 * k); ring.material.opacity = 0.95 - 0.5 * k; });
  place(g, d.xy[0], d.xy[1]);
  g.userData.conf = d.confidence;
  root.add(pickable(g, "det", `${p.id}:${d.index}`, { conf: d.confidence }));
  // sight line camera -> object
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([P(p.plan_xy[0], p.plan_xy[1], 0.1), P(d.xy[0], d.xy[1], 0.1)]),
    new THREE.LineDashedMaterial({ color: col, dashSize: 0.8, gapSize: 0.6 }));
  line.computeLineDistances(); line.userData.conf = d.confidence; line.name = "sight";
  root.add(line); S.labels.det.push(line);
  const l = label(detCard(p, d, false), "det", d.xy[0], d.xy[1], 5.2, "det");
  l.userData.conf = d.confidence;
  l.element.style.setProperty("--c", classColor(cls));
  l.element.addEventListener("click", () => select({ type: "det", id: `${p.id}:${d.index}` }));
  l.element.addEventListener("mouseenter", () => { l.element.innerHTML = detCard(p, d, true); l.element.classList.add("open"); });
  l.element.addEventListener("mouseleave", () => { if (!(S.sel?.type === "det" && S.sel.id === `${p.id}:${d.index}`)) { l.element.innerHTML = detCard(p, d, false); l.element.classList.remove("open"); } });
  l.userData.det = { p, d };
}

function locationText(p, d) {
  if (p.gps_is_real) {
    const est = d?.gps_estimate ? `<br>object ≈ ${d.gps_estimate[0].toFixed(6)}, ${d.gps_estimate[1].toFixed(6)} (${d.position_method === "pinhole_estimate" ? `${d.distance_m} m at ${d.bearing_deg}°` : "near camera"})` : "";
    return `camera ${p.lat.toFixed(6)}, ${p.lon.toFixed(6)} (${p.location_source === "exif" ? "EXIF GPS" : "GPS set by user"})${est}`;
  }
  if (p.plan_xy) return `No GPS in photo · plan position x ${p.plan_xy[0].toFixed(1)} m, y ${p.plan_xy[1].toFixed(1)} m (placed manually)`;
  return "No GPS in photo · not placed on the plan";
}

function detCard(p, d, open) {
  const head = `<i></i><b>${esc(nice(d.class))}</b> ${pct(d.confidence)}`;
  if (!open) return head;
  return `${head}<div class="card2">
    <div><span>Object</span>${esc(nice(d.class))}</div>
    <div><span>Detection confidence</span>${(d.confidence * 100).toFixed(1)}%</div>
    <div><span>Model</span>${esc(p.detector?.name || S.data.models.detector)}</div>
    <div><span>Evidence</span>${esc(p.evidence_id)} · ${esc(p.original_name)}</div>
    <div><span>Location</span>${locationText(p, d)}</div>
    <div><span>Position on plan</span>${d.position_method === "pinhole_estimate" ? `estimated from camera heading (${d.distance_m} m)` : "approximate – drawn next to the camera (no heading)"}</div></div>`;
}

/* ------------------------------------------------------------------ visibility, legend, overlays */
function applyVisibility() {
  if (!root) return;
  const { det, lbl, pho, zon } = S.show, is2d = S.mode === "2d";
  for (const o of S.pickables) {
    const t = o.userData.pick.type;
    if (t === "det") o.visible = det && o.userData.conf >= S.minConf;
    if (t === "photo") o.visible = pho;
    if (t === "zone") o.visible = zon;
  }
  root.traverse(o => { if (o.name === "zoneEdge") o.visible = zon; if (o.name === "fence") o.visible = !is2d; });
  S.labels.det.forEach(o => o.visible = det && o.userData.conf >= S.minConf && (o.isLine || lbl));
  S.labels.photo.forEach(o => o.visible = pho);
  S.labels.zone.forEach(o => o.visible = zon && lbl);
  S.labels.struct.forEach(o => o.visible = lbl);
  S.labels.dim.forEach(o => o.visible = lbl && is2d);
  // CSS2DRenderer only checks the object's own flag; hide DOM explicitly for robustness
  Object.values(S.labels).flat().forEach(o => { if (o.element) o.element.style.display = o.visible ? "" : "none"; });
  const shown = S.data ? S.data.photos.reduce((n, p) => n + (p.plan_xy ? p.detections.filter(d => d.confidence >= S.minConf).length : 0), 0) : 0;
  if ($("#twCount")) $("#twCount").textContent = det ? `${shown} detection${shown === 1 ? "" : "s"} on plan` : "detections hidden";
}

function renderLegend() {
  const classes = [...new Set(S.data.photos.flatMap(p => p.detections.map(d => d.class.toLowerCase())))];
  $("#twLegend").innerHTML = `<summary>Legend</summary>` +
    `<div><i class="sw" style="background:#c8501e;border-radius:50%"></i>Photo location</div>` +
    `<div><i class="sw" style="background:#8a8780;border-radius:50%"></i>Photo without GPS</div>` +
    classes.map(c => `<div><i class="sw" style="background:${classColor(c)}"></i>${esc(nice(c))} (${esc(S.data.models.detector)})</div>`).join("") +
    `<div><i class="sw" style="background:#2f7d4a"></i>Built (from progress log)</div><div><i class="sw ghost"></i>Planned (dashed)</div>`;
}

const NICE_STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200];
function updateOverlays() {
  if (!stage) return;
  const h = stage.clientHeight;
  const pxPerM = h / ((camera.top - camera.bottom) / camera.zoom);
  const m = NICE_STEPS.find(v => v * pxPerM >= 70) || 200;
  $("#twScale").style.display = S.mode === "2d" ? "" : "none";
  $("#twScaleBar").style.width = `${m * pxPerM}px`;
  $("#twScaleTxt").textContent = `${m} m`;
  // north arrow follows camera azimuth
  const dir = new THREE.Vector3(); camera.getWorldDirection(dir);
  const up = camera.up.clone().applyQuaternion(camera.quaternion);
  let az = 0;
  if (S.mode === "3d") { az = Math.atan2(dir.x, -dir.z); }
  else { az = Math.atan2(up.x, -up.z); }
  $("#twNorth").style.transform = `rotate(${-az}rad)`;
  const rot = L => L && (L.rotation_deg || 0);
  $("#twNorth").title = S.data?.layout ? `Plan north${rot(S.data.layout) ? ` (true north ${rot(S.data.layout)}° offset)` : " = true north"}` : "";
}

/* ------------------------------------------------------------------ camera modes */
let anim = null;
function setMode(mode, refit) {
  if (S.built && mode !== S.mode && !RM) { const st = stage.parentElement; st.classList.remove("wipe"); void st.offsetWidth; st.classList.add("wipe"); setTimeout(() => st.classList.remove("wipe"), 750); }
  S.mode = mode;
  if (scene) applyLook();
  document.querySelectorAll("#twMode button").forEach(b => b.classList.toggle("on", b.dataset.mode === mode));
  const D = 600;
  let target = controls.target.clone(), zoom = camera.zoom;
  if (refit) { target = center.clone(); zoom = 1; }
  let pos;
  if (mode === "2d") {
    pos = target.clone().add(new THREE.Vector3(0, D, 0.01));
    controls.enableRotate = false;
    controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
    controls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_PAN };
    lights.sun.castShadow = false; lights.hemi.intensity = 1.1; lights.sun.intensity = 0.6;
  } else {
    pos = target.clone().add(new THREE.Vector3(-1, 1, 1).normalize().multiplyScalar(D));   // true isometric from SW
    controls.enableRotate = true;
    controls.maxPolarAngle = 1.48;
    controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
    controls.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };
    lights.sun.castShadow = true; lights.hemi.intensity = 0.7; lights.sun.intensity = 1.8;
  }
  controls.minPolarAngle = 0;
  if (mode === "3d") controls.maxPolarAngle = 1.48;
  const from = { pos: camera.position.clone(), tgt: controls.target.clone(), zoom: camera.zoom }, t0 = performance.now();
  if (anim) cancelAnimationFrame(anim);
  const first = !S.built;
  const step = () => {
    const k = first ? 1 : Math.min(1, (performance.now() - t0) / 450), e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
    camera.position.lerpVectors(from.pos, pos, e);
    controls.target.lerpVectors(from.tgt, target, e);
    camera.zoom = from.zoom + (zoom - from.zoom) * e;
    camera.updateProjectionMatrix();
    camera.lookAt(controls.target);
    if (k < 1) anim = requestAnimationFrame(step);
    else { if (mode === "2d") controls.maxPolarAngle = 0; controls.update(); updateOverlays(); }
  };
  step();
  resize();
  applyVisibility();
  $("#twHelpTxt").textContent = mode === "2d" ? "Drag to pan · scroll to zoom · click to inspect" : "Drag to rotate · right-drag to pan · scroll to zoom · click to inspect";
}

/* ------------------------------------------------------------------ picking */
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2(), groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const PRIORITY = { det: 0, photo: 1, structure: 2, zone: 3 };
let downAt = null;

function setNdc(e) {
  const r = renderer.domElement.getBoundingClientRect();
  ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
}
function pick(e) {
  setNdc(e);
  const hits = ray.intersectObjects(S.pickables.filter(o => o.visible), true).filter(h => {
    let o = h.object; while (o) { if (!o.visible) return false; o = o.parent; } return true;
  });
  if (!hits.length) return null;
  hits.sort((a, b) => (PRIORITY[a.object.userData.pick.type] - PRIORITY[b.object.userData.pick.type]) || a.distance - b.distance);
  return hits[0].object.userData.pick;
}
function groundPoint(e) {
  setNdc(e);
  const v = new THREE.Vector3();
  return ray.ray.intersectPlane(groundPlane, v) ? [v.x, -v.z] : null;
}

function onDown(e) { downAt = [e.clientX, e.clientY]; if (S.touring && e.isTrusted) stopTour(); }
function onUp(e) {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5 || e.button !== 0) { downAt = null; return; }
  downAt = null;
  if (S.placing) return placeClick(e);
  const p = pick(e);
  select(p ? { type: p.type, id: p.id } : null);
}
function onMove(e) {
  if (S.placing) return placeMove(e);
  if (e.buttons) return;
  setHover(pick(e));
  const tip = $("#twTip");
  if (S.hover) {
    tip.style.display = "block";
    const r = stage.getBoundingClientRect();
    tip.style.left = e.clientX - r.left + 14 + "px"; tip.style.top = e.clientY - r.top + 14 + "px";
    tip.textContent = hoverText(S.hover);
  } else tip.style.display = "none";
}
function hoverText(h) {
  if (h.type === "zone") return zone(h.id)?.name;
  if (h.type === "structure") return S.data.layout.structures.find(s => s.id === h.id)?.name;
  if (h.type === "photo") { const p = photo(h.id); return `${S.photoNo[p.id]} · ${p.original_name}`; }
  if (h.type === "det") { const [pid, i] = h.id.split(":"); const d = photo(pid).detections[+i]; return `${nice(d.class)} ${pct(d.confidence)}`; }
  return "";
}
function setHover(h) {
  const key = h ? h.type + h.id : null;
  if (key === (S.hover ? S.hover.type + S.hover.id : null)) return;
  // zone fill highlight
  for (const o of S.pickables) if (o.userData.pick.type === "zone") {
    const on = (h?.type === "zone" && h.id === o.userData.pick.id) || (S.sel?.type === "zone" && S.sel.id === o.userData.pick.id);
    o.material.opacity = on ? 0.26 : o.userData.baseOpacity;
  }
  S.hover = h;
  renderer.domElement.style.cursor = h ? "pointer" : "";
  if (!h) $("#twTip").style.display = "none";
}

/* ------------------------------------------------------------------ selection */
function objFor(sel) {
  if (!sel) return null;
  const name = sel.type === "det" ? `det:${sel.id}` : sel.type === "photo" ? `photo:${sel.id}` : sel.type === "structure" ? `struct:${sel.id}` : `zone:${sel.id}`;
  return root.getObjectByName(name);
}
function select(sel, opts = {}) {
  S.sel = sel;
  if (selRing) { root.remove(selRing); selRing = null; }
  S.labels.det.forEach(l => { if (l.element && l.userData.det) { const { p, d } = l.userData.det; const on = sel?.type === "det" && sel.id === `${p.id}:${d.index}`; l.element.innerHTML = detCard(p, d, on); l.element.classList.toggle("open", on); } });
  for (const o of S.pickables) if (o.userData.pick.type === "zone") o.material.opacity = sel?.type === "zone" && sel.id === o.userData.pick.id ? 0.26 : o.userData.baseOpacity;
  const obj = objFor(sel);
  if (obj && sel.type !== "zone") {
    const bb = new THREE.Box3().setFromObject(obj), c = bb.getCenter(new THREE.Vector3()), sz = bb.getSize(new THREE.Vector3());
    const r = Math.max(2, Math.min(30, Math.max(sz.x, sz.z) / 2 + 1));
    selRing = new THREE.Mesh(new THREE.RingGeometry(r, r + 0.6, 48), flat(C.acc, { transparent: true, opacity: 0.8, depthWrite: false }));
    selRing.rotation.x = -Math.PI / 2; selRing.position.set(c.x, 0.1, c.z); root.add(selRing);
    if (opts.focus) controls.target.set(c.x, 0, c.z);
  }
  renderSide();
}
function restoreSelection() { if (S.sel && objFor(S.sel)) select(S.sel); else select(null); }

/* ------------------------------------------------------------------ side panel */
function renderSide() {
  const el = $("#twSide"), s = S.sel;
  if (!s) return renderOverview(el);
  if (s.type === "zone") return renderZone(el, s.id);
  if (s.type === "photo") return renderPhoto(el, s.id);
  if (s.type === "det") { const [pid, i] = s.id.split(":"); return renderDet(el, photo(pid), +i); }
  if (s.type === "structure") return renderStructure(el, s.id);
}
const back = `<button class="s tw-back" data-back>← Site overview</button>`;
function bindSide(el) {
  el.querySelectorAll("[data-back]").forEach(b => b.onclick = () => select(null));
  el.querySelectorAll("[data-sel]").forEach(b => b.onclick = () => { const [t, ...id] = b.dataset.sel.split(":"); select({ type: t, id: id.join(":") }, { focus: true }); });
  el.querySelectorAll("[data-place]").forEach(b => b.onclick = () => startPlacing(b.dataset.place, "pos"));
  el.querySelectorAll("[data-heading]").forEach(b => b.onclick = () => startPlacing(b.dataset.heading, "heading"));
}
function lightBadge(a) {
  const t = { green: "on plan", yellow: "slightly behind", red: "delayed", grey: "not started" }[a.light] || a.light;
  return `<span class="tw-light ${a.light}">${t}</span>`;
}
function actRow(a) {
  const f = a.total ? Math.min(1, a.actual / a.total) : 0, pl = a.total ? Math.min(1, a.planned / a.total) : 0;
  return `<div class="tw-act"><div class="row2"><b>${esc(a.name)}</b>${lightBadge(a)}</div>
    <div class="bar"><i style="width:${f * 100}%"></i><u style="left:${pl * 100}%"></u></div>
    <span class="mut">actual ${a.actual} ${esc(a.unit)} / planned ${a.planned} of ${a.total} ${esc(a.unit)}${a.delay_days > 0 ? ` · ${a.delay_days} days behind` : ""} · ${esc(a.start)} → ${esc(a.end)}</span></div>`;
}

function renderOverview(el) {
  const d = S.data, L = d.layout, unplaced = d.photos.filter(p => !p.plan_xy);
  const nDet = d.photos.reduce((n, p) => n + p.detections.length, 0);
  el.innerHTML = `<div class="pad">
    <div class="tw-kicker">Site digital twin</div><h3>${esc(L.name || "Construction site")}</h3>
    <p class="mut">${L.origin ? `Georeferenced: origin ${L.origin.lat.toFixed(5)}, ${L.origin.lon.toFixed(5)}${L.rotation_deg ? `, plan rotated ${L.rotation_deg}°` : ""}. Photos with real GPS are positioned automatically.` : "Not georeferenced: relative coordinates only. Place photos manually."}</p>
    <div class="tw-stats"><div><b data-count="${d.photos.length}">${d.photos.length}</b><span>photos</span></div><div><b data-count="${d.photos.length - unplaced.length}">${d.photos.length - unplaced.length}</b><span>on plan</span></div>
      <div><b data-count="${nDet}">${nDet}</b><span>detections</span></div><div><b data-count="${L.zones.length}">${L.zones.length}</b><span>zones</span></div></div>
    <h4>Zones</h4>${L.zones.map(z => { const zs = zoneSum(z.id); return `<button class="tw-item" data-sel="zone:${z.id}"><i class="sw" style="background:${esc(z.color || "#888")}"></i>
      <span><b>${esc(z.name)}</b><span class="mut">${zs.photos.length} photos · ${zs.machinery.map(m => `${m.count}× ${esc(nice(m.class))}`).join(", ") || "no machinery detected"}</span></span></button>`; }).join("")}
    ${unplaced.length ? `<h4>Photos without GPS (${unplaced.length})</h4><p class="mut">These photos carry no EXIF GPS, so their position is unknown. Place each one where it was taken; optionally click a second time to set the viewing direction, which positions the detected objects.</p>
      ${unplaced.map(p => `<div class="tw-item"><img src="${API}/data/${esc(p.file)}" data-sel="photo:${p.id}"><span><b>${S.photoNo[p.id]} · ${esc(p.original_name)}</b>
        <span class="mut">${p.detections.map(x => `${esc(nice(x.class))} ${pct(x.confidence)}`).join(", ") || "no detections"}</span></span><button class="s p" data-place="${p.id}">Place</button></div>`).join("")}` : ""}
    <h4>Models</h4><p class="mut">Object detection: <b>${esc(d.models.detector)}</b> (confidence values from stored model output).<br>Vision description: <b>${esc(d.models.vision)}</b> (only where a description was stored at upload).</p>
  </div>`;
  bindSide(el);
}

function photoThumbs(ids) {
  return `<div class="tw-thumbs">${ids.map(id => { const p = photo(id); return `<figure data-sel="photo:${id}"><img src="${API}/data/${esc(p.file)}"><figcaption>${S.photoNo[id]}</figcaption></figure>`; }).join("")}</div>`;
}

function renderZone(el, id) {
  const z = zone(id), zs = zoneSum(id);
  el.innerHTML = `<div class="pad">${back}
    <div class="tw-kicker" style="color:${esc(z.color)}">Zone · ${esc(z.kind || "")}</div><h3>${esc(z.name)}</h3>
    <h4>Construction activity</h4>${zs.activities.length ? zs.activities.map(actRow).join("") : `<p class="mut">No scheduled activity linked to this zone.</p>`}
    <h4>Detected machinery</h4>${zs.machinery.length ? `<table class="tw-tab"><tr><th>Object</th><th>Count</th><th>Best confidence</th></tr>${zs.machinery.map(m =>
      `<tr><td><i class="sw" style="background:${classColor(m.class)}"></i>${esc(nice(m.class))}</td><td>${m.count}</td><td>${pct(m.max_confidence)}</td></tr>`).join("")}</table>
      <p class="mut">Detections per photo; the same machine seen in two photos counts twice.</p>` : `<p class="mut">No photos with detections in this zone.</p>`}
    <h4>Photographs (${zs.photos.length})</h4>${zs.photos.length ? photoThumbs(zs.photos) : `<p class="mut">No photos placed in this zone.</p>`}
    <h4>Timeline</h4>${zs.timeline.length ? `<ol class="tw-tl">${zs.timeline.slice(0, 30).map(t => `<li class="${t.kind}"><span class="mut">${esc(t.date.replace("T", " ").slice(0, 16))}</span>${esc(t.text)} <code>${esc(t.evidence_id)}</code></li>`).join("")}</ol>` : `<p class="mut">No events yet.</p>`}
    <h4>Evidence records</h4>${zs.evidence.length ? `<ul class="tw-ev">${zs.evidence.map(e => `<li><code>${esc(e.id)}</code> ${esc(e.label)} <span class="mut">${e.kind}</span></li>`).join("")}</ul>` : `<p class="mut">None.</p>`}
  </div>`;
  bindSide(el);
}

function renderPhoto(el, id) {
  const p = photo(id), zones = S.data.layout.zones;
  el.innerHTML = `<div class="pad">${back}
    <div class="tw-kicker">Photo ${S.photoNo[p.id]} · ${esc(p.category || "")}</div><h3>${esc(p.original_name)}</h3>
    <div class="tw-img"><img id="twImg" src="${API}/data/${esc(p.file)}"><canvas id="twCv"></canvas></div>
    <label class="tw-chk"><input type="checkbox" id="twBoxes" checked> Bounding boxes</label>
    <h4>${esc(p.detector?.name || S.data.models.detector)} detections</h4>
    ${p.detections.length ? `<table class="tw-tab"><tr><th>Object</th><th>Confidence</th><th>On plan</th></tr>${p.detections.map(d => `<tr class="${d.confidence < S.minConf ? "dim" : ""}">
      <td><i class="sw" style="background:${classColor(d.class)}"></i>${d.xy ? `<a href="#" data-sel="det:${p.id}:${d.index}">${esc(nice(d.class))}</a>` : esc(nice(d.class))}</td><td>${(d.confidence * 100).toFixed(1)}%</td>
      <td class="mut">${d.position_method === "pinhole_estimate" ? `${d.distance_m} m @ ${d.bearing_deg}°` : d.xy ? "near camera" : "—"}</td></tr>`).join("")}</table>
      ${p.detector && p.detector.recorded === false ? `<p class="mut">Model name not recorded with this older photo; shown from current config.</p>` : ""}`
      : `<p class="mut">${p.mock ? "Uploaded in mock mode – detector was not configured." : "No objects detected."}</p>`}
    <h4>Vision description</h4>${p.caption ? `<p>${esc(p.caption)}</p><p class="mut">Model: ${esc(p.caption_model || "not recorded")}</p>` : `<p class="mut">No description stored for this photo (the vision model was not available when it was uploaded).</p>`}
    <h4>Record</h4><table class="tw-kv">
      <tr><th>Evidence ID</th><td><code>${esc(p.evidence_id)}</code></td></tr>
      <tr><th>Timestamp</th><td>${esc((p.taken_at || "").replace("T", " "))}</td></tr>
      <tr><th>GPS</th><td>${p.gps_is_real ? `${p.lat.toFixed(6)}, ${p.lon.toFixed(6)} <span class="mut">(${p.location_source === "exif" ? "EXIF" : "set by user"})</span>` : `<span class="mut">none in photo</span>`}</td></tr>
      <tr><th>Plan position</th><td>${p.plan_xy ? `x ${p.plan_xy[0].toFixed(1)} m, y ${p.plan_xy[1].toFixed(1)} m <span class="mut">(${p.position_method === "gps" ? "from GPS" : "placed on plan"})</span>${p.plan_gps && !p.gps_is_real ? `<br><span class="mut">≈ ${p.plan_gps[0].toFixed(6)}, ${p.plan_gps[1].toFixed(6)} derived from plan</span>` : ""}` : `<span class="mut">not placed</span>`}</td></tr>
      <tr><th>Direction</th><td>${p.heading != null ? `${p.heading}° <span class="mut">(${esc(p.heading_source || "")})</span>` : `<span class="mut">unknown</span>`}</td></tr>
      <tr><th>Zone</th><td><select id="twZoneSel"><option value="">auto (from position)${p.zone && p.zone_source === "auto" ? ` – ${esc(zone(p.zone)?.name)}` : ""}</option>${zones.map(z => `<option value="${z.id}" ${p.zone_source === "user" && p.zone === z.id ? "selected" : ""}>${esc(z.name)}</option>`).join("")}</select></td></tr>
      ${p.docs.length ? `<tr><th>Used in</th><td>${p.docs.map(d => `${esc(d.title)} <span class="mut">(${esc(d.status)})</span>`).join("<br>")}</td></tr>` : ""}
    </table>
    <div class="tw-actions">
      ${p.position_method !== "gps" ? `<button class="s p" data-place="${p.id}">${p.plan_xy ? "Move on plan" : "Place on plan"}</button>` : ""}
      ${p.plan_xy ? `<button class="s" data-heading="${p.id}">Set direction</button>` : ""}
      ${p.heading != null && p.heading_source === "user" ? `<button class="s" id="twClrHead">Clear direction</button>` : ""}
      ${p.position_method === "plan" ? `<button class="s" id="twUnplace">Remove from plan</button>` : ""}
    </div></div>`;
  bindSide(el);
  const img = $("#twImg"), cv = $("#twCv");
  const draw = () => drawBoxes(cv, img.naturalWidth, img.naturalHeight, $("#twBoxes").checked ? p.detections : []);
  img.onload = draw; if (img.complete) draw();
  $("#twBoxes").onchange = draw;
  $("#twZoneSel").onchange = e => patch(p.id, { zone: e.target.value || null });
  $("#twClrHead") && ($("#twClrHead").onclick = () => patch(p.id, { heading: null }));
  $("#twUnplace") && ($("#twUnplace").onclick = () => patch(p.id, { site_xy: null, heading: null }));
}

function drawBoxes(cv, w, h, dets) {
  if (!w) return;
  cv.width = w; cv.height = h;
  const c = cv.getContext("2d"), lw = Math.max(2, w / 300), fs = Math.max(13, w / 55);
  c.clearRect(0, 0, w, h); c.lineWidth = lw; c.font = `600 ${fs}px system-ui,sans-serif`;
  dets.forEach(d => {
    const col = classColor(d.class), x = d.bbox.x - d.bbox.width / 2, y = d.bbox.y - d.bbox.height / 2, t = `${nice(d.class)} ${pct(d.confidence)}`;
    c.strokeStyle = c.fillStyle = col; c.strokeRect(x, y, d.bbox.width, d.bbox.height);
    const tw = c.measureText(t).width + 10;
    c.fillRect(x - lw / 2, y - fs - 8, tw, fs + 8); c.fillStyle = "#fff"; c.fillText(t, x + 4, y - 6);
  });
}

function renderDet(el, p, i) {
  const d = p.detections[i];
  el.innerHTML = `<div class="pad">${back}
    <div class="tw-kicker" style="color:${classColor(d.class)}">AI detection</div><h3>${esc(nice(d.class))}</h3>
    <canvas id="twCrop" class="tw-crop"></canvas>
    <table class="tw-kv">
      <tr><th>Object</th><td>${esc(nice(d.class))} <span class="mut">(class “${esc(d.class)}”)</span></td></tr>
      <tr><th>Detection confidence</th><td><b>${(d.confidence * 100).toFixed(1)}%</b></td></tr>
      <tr><th>Model</th><td>${esc(p.detector?.name || S.data.models.detector)}</td></tr>
      <tr><th>Evidence</th><td><a href="#" data-sel="photo:${p.id}"><code>${esc(p.evidence_id)}</code> ${esc(p.original_name)}</a></td></tr>
      <tr><th>Location</th><td>${locationText(p, d)}</td></tr>
      <tr><th>Plan position</th><td>x ${d.xy[0].toFixed(1)} m, y ${d.xy[1].toFixed(1)} m</td></tr>
      <tr><th>How positioned</th><td class="mut">${d.position_method === "pinhole_estimate"
        ? `Estimated: bearing from the box’s column in the image and camera direction ${p.heading}°, distance from box height assuming a ${S.data.camera.object_height_m[d.class.toLowerCase()] ?? 2.5} m tall object and a ${S.data.camera.hfov_deg}° lens. Accuracy roughly ±30 %.`
        : "Approximate: the photo has no viewing direction, so the object is drawn next to the camera. Use “Set direction” on the photo for a better estimate."}</td></tr>
      <tr><th>Taken</th><td>${esc((p.taken_at || "").replace("T", " "))}</td></tr>
      <tr><th>Pixel box</th><td class="mut">${Math.round(d.bbox.width)}×${Math.round(d.bbox.height)} px at (${Math.round(d.bbox.x)}, ${Math.round(d.bbox.y)})</td></tr>
    </table></div>`;
  bindSide(el);
  const img = new Image();
  img.onload = () => {
    const cv = $("#twCrop"); if (!cv) return;
    const m = 0.15, bw = d.bbox.width * (1 + 2 * m), bh = d.bbox.height * (1 + 2 * m);
    const sx = Math.max(0, d.bbox.x - bw / 2), sy = Math.max(0, d.bbox.y - bh / 2);
    cv.width = Math.min(bw, img.naturalWidth - sx); cv.height = Math.min(bh, img.naturalHeight - sy);
    const c = cv.getContext("2d"); c.drawImage(img, sx, sy, cv.width, cv.height, 0, 0, cv.width, cv.height);
    c.strokeStyle = classColor(d.class); c.lineWidth = Math.max(2, cv.width / 120);
    c.strokeRect(d.bbox.x - d.bbox.width / 2 - sx, d.bbox.y - d.bbox.height / 2 - sy, d.bbox.width, d.bbox.height);
  };
  img.src = API + "/data/" + p.file;
}

function renderStructure(el, id) {
  const s = S.data.layout.structures.find(x => x.id === id), a = s.activity ? act(s.activity) : null;
  const inZone = S.data.layout.zones.find(z => pointInPoly(s.x ?? (s.x1 + s.x2) / 2, s.y ?? (s.y1 + s.y2) / 2, z.polygon));
  let extra = "";
  if (s.kind === "pile_row" && a) {
    const done = Math.floor(a.actual);
    extra = `<p>${done} of ${s.count} piles complete${done < s.count ? `; pile ${done + 1} is current` : ""}.</p>`;
    const zs = inZone && zoneSum(inZone.id);
    const n = zs?.timeline.filter(t => t.kind === "progress" && t.evidence_id === `sched:${s.activity}`).slice(0, 3) || [];
    if (n.length) extra += `<ol class="tw-tl">${n.map(t => `<li class="progress"><span class="mut">${esc(t.date)}</span>${esc(t.text)}</li>`).join("")}</ol>`;
  }
  el.innerHTML = `<div class="pad">${back}
    <div class="tw-kicker">${s.planned ? "Planned structure" : "Structure"} · ${esc(s.kind)}</div><h3>${esc(s.name)}</h3>
    ${inZone ? `<p class="mut">In zone <a href="#" data-sel="zone:${inZone.id}">${esc(inZone.name)}</a></p>` : ""}
    ${a ? `<h4>Linked activity</h4>${actRow(a)}<p class="mut">The 3D model shows the built share from the progress log (${Math.round(frac(s.activity) * 100)}%).</p>` : s.planned ? `<p class="mut">Not started – drawn dashed / translucent.</p>` : ""}
    ${extra}</div>`;
  bindSide(el);
}
function pointInPoly(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-12) + xi) inside = !inside;
  }
  return inside;
}

/* ------------------------------------------------------------------ placing photos on the plan */
function startPlacing(id, step) {
  const p = photo(id);
  S.placing = { id, step, pos: step === "heading" ? p.plan_xy : null };
  $("#twHint").style.display = "block";
  $("#twHint").innerHTML = step === "pos"
    ? `<b>${S.photoNo[id]}</b> Click where the photo was taken. <span class="mut">Esc to cancel</span>`
    : `<b>${S.photoNo[id]}</b> Click in the direction the camera was pointing. <span class="mut">Right-click / Esc to skip</span>`;
  renderer.domElement.style.cursor = "crosshair";
}
function placeMove(e) {
  const g = groundPoint(e); if (!g) return;
  if (ghost) { root.remove(ghost); ghost = null; }
  if (S.placing.step === "pos") {
    ghost = new THREE.Mesh(new THREE.RingGeometry(1.1, 1.6, 32), flat(C.acc, { transparent: true, opacity: 0.6 }));
    ghost.rotation.x = -Math.PI / 2; ghost.position.copy(P(g[0], g[1], 0.1));
  } else {
    const [x, y] = S.placing.pos, hd = (Math.atan2(g[0] - x, g[1] - y) * 180 / Math.PI + 360) % 360;
    ghost = wedge([x, y], hd, C.acc, 0.3, 20);
  }
  root.add(ghost);
}
async function placeClick(e) {
  const g = groundPoint(e); if (!g) return;
  const pl = S.placing;
  if (pl.step === "pos") {
    pl.pos = [Math.round(g[0] * 10) / 10, Math.round(g[1] * 10) / 10];
    await api("/api/photos/" + pl.id, { method: "PATCH", json: { site_xy: pl.pos } });
    startPlacing(pl.id, "heading");
    S.placing.pos = pl.pos;
    const sel = { type: "photo", id: pl.id }; S.sel = sel;
    await load(true);
  } else {
    const hd = (Math.atan2(g[0] - pl.pos[0], g[1] - pl.pos[1]) * 180 / Math.PI + 360) % 360;
    await api("/api/photos/" + pl.id, { method: "PATCH", json: { heading: Math.round(hd * 10) / 10 } });
    finishPlacing();
    await load(true);
  }
}
function finishPlacing(cancel) {
  const id = S.placing?.id;
  S.placing = null;
  if (ghost) { root.remove(ghost); ghost = null; }
  $("#twHint").style.display = "none";
  renderer.domElement.style.cursor = "";
  if (id) S.sel = { type: "photo", id };
  if (!cancel) renderSide(); else restoreSelection();
}
async function patch(id, body) {
  try { await api("/api/photos/" + id, { method: "PATCH", json: body }); } catch (e) { alert(e.message); }
  S.sel = { type: "photo", id };
  await load(true);
}

/* ------------------------------------------------------------------ layout editor */
async function openLayoutEditor() {
  const lay = await api("/api/site/layout");
  $("#twLayTxt").value = JSON.stringify(lay, null, 2);
  $("#twLayErr").textContent = "";
  $("#twDlg").showModal();
}
async function saveLayout() {
  let obj;
  try { obj = JSON.parse($("#twLayTxt").value); } catch (e) { $("#twLayErr").textContent = "JSON error: " + e.message; return; }
  try { await api("/api/site/layout", { method: "PUT", json: obj }); } catch (e) { $("#twLayErr").textContent = e.message; return; }
  $("#twDlg").close();
  await load(false);
}

/* ------------------------------------------------------------------ radar sweep across the site */
function addSweep(b) {
  const cv = document.createElement("canvas"); cv.width = 256; cv.height = 4;
  const g = cv.getContext("2d"), gr = g.createLinearGradient(0, 0, 256, 0);
  gr.addColorStop(0, "rgba(34,211,238,0)"); gr.addColorStop(0.85, "rgba(34,211,238,0.18)"); gr.addColorStop(0.97, "rgba(160,240,255,0.5)"); gr.addColorStop(1, "rgba(34,211,238,0)");
  g.fillStyle = gr; g.fillRect(0, 0, 256, 4);
  const w = 26, h = b.y1 - b.y0;
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(cv), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
  m.rotation.x = -Math.PI / 2;
  root.add(m);
  const span = b.x1 - b.x0 + w * 2;
  S.anims.push(t => { const k = (t % 7) / 7; m.position.copy(P(b.x0 - w + k * span, (b.y0 + b.y1) / 2, 0.15)); m.material.opacity = Math.sin(Math.PI * k); });
}

/* ------------------------------------------------------------------ camera flights */
const ease = k => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);
function flyTo({ target, zoom, theta, phi, dur = 1500 } = {}) {
  return new Promise(res => {
    const D = 600, off = camera.position.clone().sub(controls.target), sph = new THREE.Spherical().setFromVector3(off);
    const from = { t: controls.target.clone(), z: camera.zoom, th: sph.theta, ph: sph.phi };
    const to = { t: target ? target.clone() : from.t.clone(), z: zoom ?? from.z, th: theta ?? from.th, ph: phi ?? from.ph };
    while (to.th - from.th > Math.PI) to.th -= 2 * Math.PI;
    while (from.th - to.th > Math.PI) to.th += 2 * Math.PI;
    const t0 = performance.now(), id = {};
    S.flying = id; controls.enabled = false;
    const step = () => {
      if (S.flying !== id) return res();
      const k = RM ? 1 : Math.min(1, (performance.now() - t0) / dur), e = ease(k);
      const tg = from.t.clone().lerp(to.t, e);
      const s2 = new THREE.Spherical(D, from.ph + (to.ph - from.ph) * e, from.th + (to.th - from.th) * e);
      camera.position.copy(tg).add(new THREE.Vector3().setFromSpherical(s2));
      camera.zoom = from.z + (to.z - from.z) * e;
      camera.updateProjectionMatrix();
      controls.target.copy(tg);
      camera.lookAt(tg);
      updateOverlays();
      if (k < 1) requestAnimationFrame(step);
      else { S.flying = null; controls.enabled = true; res(); }
    };
    step();
  });
}

/* ------------------------------------------------------------------ automated tour (driven by the live twin data) */
function stopTour() {
  if (!S.touring) return;
  S.touring = false; S.flying = null; controls.enabled = true;
  $("#twTour")?.classList.remove("on"); if ($("#twTour")) $("#twTour").textContent = "▶ Tour";
  if (!window.FX?.autopilotOn) window.FX?.hideCaption();
}
async function tour({ isCancelled = () => false } = {}) {
  if (S.touring || !S.data) return;
  S.touring = true;
  $("#twTour").classList.add("on"); $("#twTour").textContent = "■ Stop";
  const off = () => !S.touring || isCancelled();
  const cap = (k, t, x, ms) => (window.FX ? FX.caption(k, t, x, ms) : sleep(ms));
  const hold = async ms => { const t0 = performance.now(); while (!off() && performance.now() - t0 < ms) await sleep(80); };
  const d = S.data, L = d.layout;
  const placed = d.photos.filter(p => p.plan_xy), nDet = d.photos.reduce((n, p) => n + p.detections.length, 0);
  const zoomFor = pts => { const xs = pts.map(q => q[0]), ys = pts.map(q => q[1]); return Math.max(1, Math.min(3.4, fitSize / (Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) * 0.62))); };
  try {
    select(null);
    if (S.mode !== "3d") { setMode("3d"); await sleep(650); }
    cap("Digital twin", L.name || "Construction site", `${L.zones.length} zones · ${d.photos.length} photos · ${nDet} AI detections · ${placed.length} photos on the plan`, 5200);
    await flyTo({ target: center, zoom: 0.95, theta: -Math.PI / 4, phi: 0.98, dur: 1600 });
    if (off()) return;
    await flyTo({ theta: Math.PI / 5, phi: 0.82, zoom: 1.05, dur: 3400 });
    let th = Math.PI / 5;
    for (const z of L.zones) {
      if (off()) return;
      const zs = zoneSum(z.id), c = centroid(z.polygon);
      th += 0.55;
      select({ type: "zone", id: z.id });
      const acts = zs.activities.map(a => `${a.name}: ${a.actual}/${a.total} ${a.unit}${a.delay_days > 0.4 ? ` · ${a.delay_days} d behind` : ""}`).join(" · ");
      const mach = zs.machinery.map(m => `${m.count}× ${nice(m.class)}`).join(", ");
      cap("Zone", z.name, [acts || "No scheduled activity", mach ? `Detected: ${mach}` : `${zs.photos.length} photos`].join(" — "), 3600);
      await flyTo({ target: P(c[0], c[1]), zoom: zoomFor(z.polygon), theta: th, phi: 0.9, dur: 1500 });
      await hold(2100);
    }
    const piles = L.structures.find(s => s.kind === "pile_row" && s.activity);
    if (piles && !off()) {
      const a = act(piles.activity), done = Math.floor(a?.actual ?? 0);
      const note = [...(S.data.zones.flatMap(z => z.timeline))].find(t => t.evidence_id === `sched:${piles.activity}` && t.text.includes("–"));
      select({ type: "structure", id: piles.id });
      cap(a?.light === "red" ? "Early warning" : "Structure", `${done} of ${piles.count} piles complete`, note ? note.text : (a ? `${a.name} · planned ${a.planned} ${a.unit}` : ""), 4200);
      await flyTo({ target: P((piles.x1 + piles.x2) / 2, (piles.y1 + piles.y2) / 2), zoom: 3.2, theta: th + 0.5, phi: 0.95, dur: 1600 });
      await hold(2600);
    }
    const dets = placed.flatMap(p => p.detections.filter(x => x.xy).map(x => ({ p, x }))).sort((a, b) => b.x.confidence - a.x.confidence).slice(0, 3);
    for (const { p, x } of dets) {
      if (off()) return;
      select({ type: "det", id: `${p.id}:${x.index}` });
      cap(`AI detection · ${p.detector?.name || d.models.detector}`, `${nice(x.class)} · ${(x.confidence * 100).toFixed(1)}%`,
        `Evidence ${p.evidence_id} (${p.original_name}) · ${x.position_method === "pinhole_estimate" ? `${x.distance_m} m from camera, estimated` : "near the camera"}`, 3800);
      await flyTo({ target: P(x.xy[0], x.xy[1]), zoom: 4.2, theta: th + 0.9, phi: 0.92, dur: 1500 });
      await hold(2300);
    }
    if (!dets.length && !off()) {
      const un = d.photos.length - placed.length;
      cap("Photo evidence", `${un} photo${un === 1 ? "" : "s"} waiting for a position`, "No GPS in these photos. Place them on the plan and the detected machines appear in 3D.", 3800);
      await hold(3800);
    }
    if (off()) return;
    select(null);
    cap("Digital twin", "Every marker traces back to evidence", "Schedule, photos and AI detections in one model.", 4000);
    await flyTo({ target: center, zoom: 1, theta: -Math.PI / 4, phi: 0.955, dur: 2200 });
    await hold(1800);
  } finally {
    const wasOn = S.touring;
    S.touring = false; controls.enabled = true;
    $("#twTour").classList.remove("on"); $("#twTour").textContent = "▶ Tour";
    if (wasOn && !window.FX?.autopilotOn) window.FX?.hideCaption();
  }
}

/* ------------------------------------------------------------------ AI control (driven by js/command.js through the BB bus) */
const HL_COLOR = { red: 0xff3b30, amber: 0xffa500, green: 0x2ecc71, blue: 0x4cc9ff };
S.hl = {};
function applyHighlights() {
  if (!root || !S.data) return;
  for (const o of S.pickables) {
    if (o.userData.pick.type !== "zone") continue;
    const id = o.userData.pick.id, lvl = S.hl[id], z = zone(id);
    if (lvl) { o.material.color.setHex(HL_COLOR[lvl] || HL_COLOR.amber); o.userData.baseOpacity = 0.28; o.userData.hl = true; }
    else { o.material.color.set(z?.color || "#888"); o.userData.baseOpacity = 0.09; o.userData.hl = false; }
    o.material.opacity = o.userData.baseOpacity;
  }
  if (!S.anims.includes(pulseHighlights)) S.anims.push(pulseHighlights);
}
function pulseHighlights(t) {
  for (const o of S.pickables) if (o.userData.hl && !(S.sel?.type === "zone" && S.sel.id === o.userData.pick.id)) o.material.opacity = 0.18 + 0.14 * (0.5 + 0.5 * Math.sin(t * 3));
}
const waitData = async () => { for (let i = 0; i < 100 && !(S.data && root); i++) await sleep(80); return !!(S.data && root); };
async function focusZone(id, { mode = "3d" } = {}) {
  if (!(await waitData())) return false;
  const z = zone(id); if (!z) return false;
  stopTour();
  if (mode && S.mode !== mode) { setMode(mode); await sleep(500); }
  select({ type: "zone", id });
  const c = centroid(z.polygon), xs = z.polygon.map(q => q[0]), ys = z.polygon.map(q => q[1]);
  const zoom = Math.max(1, Math.min(3.4, fitSize / (Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) * 0.62)));
  await flyTo({ target: P(c[0], c[1]), zoom, ...(S.mode === "3d" ? { theta: Math.PI / 5, phi: 0.9 } : {}), dur: 1400 });
  return true;
}
async function focusPhoto(id) {
  if (!(await waitData())) return false;
  const p = photo(id); if (!p) return false;
  select({ type: "photo", id }, { focus: !!p.plan_xy });
  if (p.plan_xy) await flyTo({ target: P(p.plan_xy[0], p.plan_xy[1]), zoom: 2.6, dur: 1200 });
  return !!p.plan_xy;
}
function snapshot() {
  if (!renderer || !S.data) return null;
  try { if (composer) composer.render(); else renderer.render(scene, camera); return renderer.domElement.toDataURL("image/jpeg", 0.85); }
  catch (e) { console.warn("snapshot failed", e); return null; }
}

/* ------------------------------------------------------------------ public */
window.SiteTwin = {
  focusZone, focusPhoto, snapshot,
  highlight(list) { S.hl = {}; (list || []).forEach(h => { if (h?.id) S.hl[h.id] = h.level || "amber"; }); applyHighlights(); },
  clearHighlights() { S.hl = {}; applyHighlights(); },
  reload() { return S.visible ? load(true) : Promise.resolve(); },
  get ready() { return !!(S.data && root); },
  async show() {
    try {
      const first = !renderer;
      if (first) init();
      S.visible = true;
      await load(S.built);
      resize();
      if (first && !RM) {
        const st = stage.parentElement; st.classList.add("boot"); setTimeout(() => st.classList.remove("boot"), 1800);
        camera.zoom = 0.45; camera.updateProjectionMatrix(); flyTo({ zoom: 1, dur: 1700 });
      }
    } catch (e) {
      console.error(e);
      $("#twSide").innerHTML = `<div class="pad"><b style="color:var(--bad)">Site twin could not start</b><p class="mut">${esc(e.message || e)}</p>
        <p class="mut">${/WebGL/i.test(String(e.message)) ? "WebGL is disabled in this browser (check chrome://gpu or hardware acceleration settings)." : "Try a hard reload (Cmd+Shift+R)."}</p></div>`;
    }
  },
  hide() { S.visible = false; stopTour(); },
  tour, stopTour,
};
document.dispatchEvent(new Event("sitetwin-ready"));
