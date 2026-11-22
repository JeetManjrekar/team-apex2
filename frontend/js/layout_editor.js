/* BauBuddy · visual site layout editor (replaces hand-editing JSON).
   Plan view in metres, north up. Drag a zone to move it, drag its white dots to reshape it, "+ Add zone" then drag a
   rectangle. Side panel: name, type, colour, schedule activities, delete. The site boundary is edited the same way.
   Undo (Ctrl/Cmd+Z), mouse wheel zoom, drag the background to pan. JSON stays available under "Advanced".
   API: LayoutEditor.mount(host, { layout, photos, schedule }) -> editor with .get(), .set(layout) */
(() => {
  "use strict";
  const DE = (() => { try { return localStorage.getItem("nw-lang") === "de"; } catch { return false; } })();
  const L = (en, de) => (DE ? de : en);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const COLORS = ["#9b5de5", "#3f88c5", "#e07a1f", "#d1495b", "#2a9d8f", "#f4a259", "#5c7cfa", "#8d99ae"];
  const KINDS = [["work", L("Work area", "Arbeitsbereich")], ["facilities", L("Site facilities (office, containers)", "Baustelleneinrichtung (Büro, Container)")],
    ["storage", L("Storage / laydown", "Lagerfläche")], ["access", L("Access road / gate", "Zufahrt / Tor")],
    ["future", L("Restricted / not in use yet", "Gesperrt / noch nicht in Betrieb")]];
  const snap = v => Math.round(v * 2) / 2;                 // 0.5 m grid
  const clone = o => JSON.parse(JSON.stringify(o));

  function mount(host, opts = {}) {
    const E = { lay: null, sel: null, mode: "select", undo: [], view: null, drag: null, photos: opts.photos || [], schedule: opts.schedule || [] };
    host.innerHTML = `<div class="le">
      <div class="le-bar">
        <button type="button" class="p s" data-a="add">＋ ${L("Add zone", "Zone hinzufügen")}</button>
        <button type="button" class="s" data-a="boundary">⬚ ${L("Edit site boundary", "Grenze bearbeiten")}</button>
        <button type="button" class="s" data-a="undo" title="Ctrl/Cmd+Z">↶ ${L("Undo", "Rückgängig")}</button>
        <button type="button" class="s" data-a="fit">⤢ ${L("Fit", "Einpassen")}</button>
        <span class="le-hint"></span></div>
      <div class="le-main"><svg class="le-svg" tabindex="0"></svg><div class="le-side"></div></div></div>`;
    const svg = host.querySelector(".le-svg"), side = host.querySelector(".le-side"), hint = host.querySelector(".le-hint");

    /* ---------------- view */
    function bounds() {
      const pts = [...(E.lay.boundary || []), ...E.lay.zones.flatMap(z => z.polygon), ...E.photos.filter(p => p.plan_xy).map(p => p.plan_xy)];
      if (!pts.length) return { x0: -40, x1: 40, y0: -30, y1: 30 };
      const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
      return { x0: Math.min(...xs) - 10, x1: Math.max(...xs) + 10, y0: Math.min(...ys) - 10, y1: Math.max(...ys) + 10 };
    }
    function fit() {
      const r = svg.getBoundingClientRect(), b = bounds(), w = r.width || 700, h = r.height || 480;
      const k = Math.min(w / (b.x1 - b.x0), h / (b.y1 - b.y0));
      E.view = { k, cx: (b.x0 + b.x1) / 2, cy: (b.y0 + b.y1) / 2 };
      render();
    }
    const W = () => svg.getBoundingClientRect().width || 700, H = () => svg.getBoundingClientRect().height || 480;
    const sx = x => (x - E.view.cx) * E.view.k + W() / 2, sy = y => (E.view.cy - y) * E.view.k + H() / 2;
    const toPlan = (px, py) => [(px - W() / 2) / E.view.k + E.view.cx, E.view.cy - (py - H() / 2) / E.view.k];
    const evPlan = e => { const r = svg.getBoundingClientRect(); return toPlan(e.clientX - r.left, e.clientY - r.top); };

    /* ---------------- drawing */
    function render() {
      if (!E.view) return;
      const w = W(), h = H(), [px0, py1] = toPlan(0, 0), [px1, py0] = toPlan(w, h);
      let g = "";
      const step = E.view.k > 9 ? 5 : 10;
      for (let x = Math.ceil(px0 / step) * step; x <= px1; x += step) g += `<line x1="${sx(x)}" y1="0" x2="${sx(x)}" y2="${h}" class="${x % 50 ? "g" : "g2"}"/>`;
      for (let y = Math.ceil(py0 / step) * step; y <= py1; y += step) g += `<line x1="0" y1="${sy(y)}" x2="${w}" y2="${sy(y)}" class="${y % 50 ? "g" : "g2"}"/>`;
      const poly = pts => pts.map(p => `${sx(p[0])},${sy(p[1])}`).join(" ");
      let out = `<g>${g}</g>`;
      if ((E.lay.boundary || []).length >= 3) out += `<polygon points="${poly(E.lay.boundary)}" class="bnd ${E.sel === "boundary" ? "on" : ""}" data-r="b"/>`;
      E.lay.zones.forEach((z, i) => {
        const c = z.color || COLORS[i % COLORS.length], on = E.sel === i;
        out += `<polygon points="${poly(z.polygon)}" data-r="z" data-i="${i}" class="zn ${on ? "on" : ""}" style="fill:${c};stroke:${c}"/>`;
      });
      E.lay.zones.forEach(z => {
        const cx = z.polygon.reduce((s, p) => s + p[0], 0) / z.polygon.length, cy = z.polygon.reduce((s, p) => s + p[1], 0) / z.polygon.length;
        out += `<text x="${sx(cx)}" y="${sy(cy)}" class="zl">${esc(z.name || "")}</text>`;
      });
      (E.lay.structures || []).filter(s => s.x != null).forEach(s => {
        out += `<rect x="${sx(s.x) - 4}" y="${sy(s.y) - 4}" width="8" height="8" class="st" transform="rotate(45 ${sx(s.x)} ${sy(s.y)})"/><text x="${sx(s.x) + 8}" y="${sy(s.y) - 6}" class="stl">${esc(s.name || "")}</text>`;
      });
      E.photos.filter(p => p.plan_xy).forEach(p => { out += `<circle cx="${sx(p.plan_xy[0])}" cy="${sy(p.plan_xy[1])}" r="4" class="ph"/>`; });
      const handles = E.sel === "boundary" ? E.lay.boundary.map((p, j) => ({ p, j, t: "b" })) : (E.sel != null && E.lay.zones[E.sel]) ? E.lay.zones[E.sel].polygon.map((p, j) => ({ p, j, t: "z" })) : [];
      handles.forEach(({ p, j, t }) => { out += `<circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="7" class="hd" data-r="v" data-t="${t}" data-j="${j}"/>`; });
      if (E.drag?.kind === "draw" && E.drag.b) {
        const [a, b] = [E.drag.a, E.drag.b];
        out += `<rect x="${Math.min(sx(a[0]), sx(b[0]))}" y="${Math.min(sy(a[1]), sy(b[1]))}" width="${Math.abs(sx(b[0]) - sx(a[0]))}" height="${Math.abs(sy(b[1]) - sy(a[1]))}" class="dr"/>`;
      }
      // scale bar + north
      const m = step * 2, len = m * E.view.k;
      out += `<g class="sc"><rect x="14" y="${h - 22}" width="${len}" height="5"/><text x="${20 + len}" y="${h - 16}">${m} m</text></g>
        <g class="nn" transform="translate(${w - 26},28)"><path d="M0,-14 L-8,8 L0,3 L8,8 Z"/><text y="22">N</text></g>`;
      svg.innerHTML = out;
      svg.classList.toggle("drawing", E.mode === "draw");
      hint.textContent = E.mode === "draw" ? L("Drag a rectangle on the plan for the new zone", "Rechteck für die neue Zone auf den Plan ziehen")
        : E.sel === "boundary" ? L("Drag the dots to change the site boundary", "Punkte ziehen, um die Baustellengrenze zu ändern")
        : E.sel != null ? L("Drag the zone to move it · drag the white dots to reshape", "Zone ziehen zum Verschieben · weiße Punkte ziehen zum Formen")
        : L("Click a zone to edit it · drag empty space to pan · wheel to zoom", "Zone anklicken zum Bearbeiten · leere Fläche ziehen zum Verschieben · Mausrad zum Zoomen");
    }

    /* ---------------- side panel */
    function renderSide() {
      const z = typeof E.sel === "number" ? E.lay.zones[E.sel] : null;
      if (!z) {
        side.innerHTML = `<b>${L("Zones", "Zonen")}</b>
          <div class="le-list">${E.lay.zones.map((z, i) => `<button type="button" class="le-item" data-sel="${i}"><i style="background:${z.color || COLORS[i % COLORS.length]}"></i>${esc(z.name || L("Unnamed", "Ohne Namen"))}<small>${esc((KINDS.find(k => k[0] === z.kind) || KINDS[0])[1])}</small></button>`).join("")
            || `<p class="mut">${L("No zones yet. Click “Add zone”.", "Noch keine Zonen. „Zone hinzufügen“ klicken.")}</p>`}</div>
          <p class="mut le-tip">${L("Zones decide where photos, machines and schedule activities belong, and which safety rules apply (no heavy machines in site facilities or restricted areas).",
                                     "Zonen bestimmen, wohin Fotos, Maschinen und Vorgänge gehören und welche Sicherheitsregeln gelten (keine schweren Maschinen in Baustelleneinrichtung oder Sperrbereichen).")}</p>`;
      } else {
        const acts = E.schedule || [];
        side.innerHTML = `<div class="le-row"><b>${L("Zone", "Zone")}</b><button type="button" class="s" data-a="done">✓ ${L("Done", "Fertig")}</button></div>
          <label>${L("Name", "Name")}<input type="text" data-f="name" value="${esc(z.name || "")}" maxlength="60"></label>
          <label>${L("Type", "Art")}<select data-f="kind">${KINDS.map(([k, t]) => `<option value="${k}" ${k === (z.kind || "work") ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label>
          <div class="le-lbl">${L("Colour", "Farbe")}</div><div class="le-cols">${COLORS.map(c => `<button type="button" data-col="${c}" class="${c === z.color ? "on" : ""}" style="background:${c}" aria-label="${c}"></button>`).join("")}</div>
          ${acts.length ? `<div class="le-lbl">${L("Work happening here (schedule)", "Arbeiten hier (Bauzeitenplan)")}</div>
            <div class="le-acts">${acts.map(a => `<label class="chk"><input type="checkbox" data-act="${esc(a.id)}" ${(z.activities || []).includes(a.id) ? "checked" : ""}> ${esc(a.name)}</label>`).join("")}</div>` : ""}
          <div class="le-size mut">${area(z.polygon)} m² · ${z.polygon.length} ${L("corners", "Ecken")}</div>
          <button type="button" class="s le-del" data-a="del">🗑 ${L("Delete zone", "Zone löschen")}</button>`;
      }
    }
    const area = pts => Math.round(Math.abs(pts.reduce((s, p, i) => { const q = pts[(i + 1) % pts.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0)) / 2);

    side.addEventListener("click", e => {
      const b = e.target.closest("[data-sel],[data-col],[data-a]"); if (!b) return;
      if (b.dataset.sel != null) { E.sel = +b.dataset.sel; E.mode = "select"; }
      if (b.dataset.col) { push(); E.lay.zones[E.sel].color = b.dataset.col; }
      if (b.dataset.a === "del") { push(); E.lay.zones.splice(E.sel, 1); E.sel = null; }
      if (b.dataset.a === "done") E.sel = null;
      render(); renderSide();
    });
    side.addEventListener("input", e => {
      const z = E.lay.zones[E.sel]; if (!z) return;
      if (e.target.dataset.f === "name") { z.name = e.target.value; render(); }
    });
    side.addEventListener("change", e => {
      const z = E.lay.zones[E.sel]; if (!z) return;
      push();
      if (e.target.dataset.f === "kind") z.kind = e.target.value;
      if (e.target.dataset.act) {
        const set = new Set(z.activities || []);
        e.target.checked ? set.add(e.target.dataset.act) : set.delete(e.target.dataset.act);
        z.activities = [...set];
      }
      render(); renderSide();
    });

    /* ---------------- toolbar */
    host.querySelector(".le-bar").addEventListener("click", e => {
      const a = e.target.closest("[data-a]")?.dataset.a; if (!a) return;
      if (a === "add") { E.mode = E.mode === "draw" ? "select" : "draw"; E.sel = null; }
      if (a === "boundary") {
        if (!(E.lay.boundary || []).length) { push(); const b = bounds(); E.lay.boundary = [[b.x0, b.y0], [b.x1, b.y0], [b.x1, b.y1], [b.x0, b.y1]].map(p => p.map(snap)); }
        E.sel = E.sel === "boundary" ? null : "boundary"; E.mode = "select";
      }
      if (a === "undo") undo();
      if (a === "fit") fit();
      render(); renderSide();
    });

    /* ---------------- pointer: move zones, drag corners, draw new zones, pan */
    function push() { E.undo.push(JSON.stringify(E.lay)); if (E.undo.length > 60) E.undo.shift(); }
    function undo() { const s = E.undo.pop(); if (s) { E.lay = JSON.parse(s); if (typeof E.sel === "number" && !E.lay.zones[E.sel]) E.sel = null; render(); renderSide(); } }
    svg.addEventListener("pointerdown", e => {
      svg.focus();
      const t = e.target, r = t.dataset?.r, p = evPlan(e);
      svg.setPointerCapture(e.pointerId);
      if (E.mode === "draw") { E.drag = { kind: "draw", a: p.map(snap), b: null }; return; }
      if (r === "v") {
        push();
        const pts = t.dataset.t === "b" ? E.lay.boundary : E.lay.zones[E.sel].polygon;
        E.drag = { kind: "vertex", pts, j: +t.dataset.j };
        return;
      }
      if (r === "z") {
        const i = +t.dataset.i;
        if (E.sel !== i) { E.sel = i; renderSide(); }
        push();
        E.drag = { kind: "move", i, start: p, orig: clone(E.lay.zones[i].polygon) };
        render();
        return;
      }
      E.drag = { kind: "pan", sx: e.clientX, sy: e.clientY, cx: E.view.cx, cy: E.view.cy, moved: false };
    });
    svg.addEventListener("pointermove", e => {
      const d = E.drag; if (!d) return;
      const p = evPlan(e);
      if (d.kind === "draw") d.b = p.map(snap);
      if (d.kind === "vertex") d.pts[d.j] = p.map(snap);
      if (d.kind === "move") {
        const dx = snap(p[0] - d.start[0]), dy = snap(p[1] - d.start[1]);
        E.lay.zones[d.i].polygon = d.orig.map(q => [q[0] + dx, q[1] + dy]);
      }
      if (d.kind === "pan") {
        d.moved = d.moved || Math.abs(e.clientX - d.sx) + Math.abs(e.clientY - d.sy) > 4;
        E.view.cx = d.cx - (e.clientX - d.sx) / E.view.k; E.view.cy = d.cy + (e.clientY - d.sy) / E.view.k;
      }
      render();
    });
    svg.addEventListener("pointerup", () => {
      const d = E.drag; E.drag = null; if (!d) return;
      if (d.kind === "draw" && d.b && Math.abs(d.b[0] - d.a[0]) >= 2 && Math.abs(d.b[1] - d.a[1]) >= 2) {
        push();
        const [x0, x1] = [d.a[0], d.b[0]].sort((a, b) => a - b), [y0, y1] = [d.a[1], d.b[1]].sort((a, b) => a - b);
        const n = E.lay.zones.length + 1, ids = new Set(E.lay.zones.map(z => z.id));
        let id = "z" + n; while (ids.has(id)) id += "x";
        E.lay.zones.push({ id, name: L(`New zone ${n}`, `Neue Zone ${n}`), kind: "work", color: COLORS[(n - 1) % COLORS.length], activities: [],
          polygon: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]] });
        E.sel = E.lay.zones.length - 1; E.mode = "select";
        setTimeout(() => side.querySelector('[data-f="name"]')?.select(), 30);
      }
      if (d.kind === "pan" && !d.moved && E.mode === "select") E.sel = null;
      render(); renderSide();
    });
    svg.addEventListener("wheel", e => {
      e.preventDefault();
      const r = svg.getBoundingClientRect(), before = toPlan(e.clientX - r.left, e.clientY - r.top);
      E.view.k = Math.max(1, Math.min(60, E.view.k * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
      const after = toPlan(e.clientX - r.left, e.clientY - r.top);
      E.view.cx += before[0] - after[0]; E.view.cy += before[1] - after[1];
      render();
    }, { passive: false });
    svg.addEventListener("keydown", e => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); }
      if ((e.key === "Delete" || e.key === "Backspace") && typeof E.sel === "number") { push(); E.lay.zones.splice(E.sel, 1); E.sel = null; render(); renderSide(); }
      if (e.key === "Escape") { E.mode = "select"; E.sel = null; render(); renderSide(); }
    });
    new ResizeObserver(() => { if (E.view) render(); }).observe(svg);

    const api = {
      set(layout) {
        E.lay = clone(layout || {}); E.lay.zones = E.lay.zones || []; E.lay.boundary = E.lay.boundary || [];
        E.lay.zones.forEach((z, i) => { z.color = z.color || COLORS[i % COLORS.length]; z.kind = z.kind || "work"; z.activities = z.activities || []; });
        E.sel = null; E.mode = "select"; E.undo = [];
        requestAnimationFrame(() => { fit(); renderSide(); });
      },
      get() {
        const out = clone(E.lay);
        out.zones = out.zones.filter(z => z.polygon?.length >= 3).map(z => ({ ...z, name: (z.name || "").trim() || z.id }));
        return out;
      },
      setContext(o) { if (o.photos) E.photos = o.photos; if (o.schedule) E.schedule = o.schedule; },
      changed() { return E.undo.length > 0; },
    };
    api.set(opts.layout || {});
    return api;
  }
  window.LayoutEditor = { mount };
})();
