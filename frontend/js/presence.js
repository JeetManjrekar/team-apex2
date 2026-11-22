/* BauBuddy · live location. Shares this device's browser geolocation (only after the user clicks 📍 Locate) and shows
   every active device as "You" in the 3D twin and on the map. "Simulate on site" places you at the site facilities,
   clearly marked, because the demo site is fictional. Positions stay in the server's memory for 90 s, never on disk. */
(() => {
  "use strict";
  const NW = window.NW; if (!NW) return;
  const q = s => document.querySelector(s), api = NW.api, esc = NW.esc;
  const de = (() => { try { return localStorage.getItem("nw-lang") === "de"; } catch { return false; } })();
  const L = (en, d) => (de ? d : en);
  const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
  const DEV = store.get("nw-dev") || (() => { const id = "lap-" + Math.random().toString(36).slice(2, 9); store.set("nw-dev", id); return id; })();
  const P = { on: false, sim: store.get("nw-sim") === "1", watch: null, last: null, list: [], told: false, markers: new Map() };

  // header button
  const btn = document.createElement("button");
  btn.className = "s"; btn.id = "locBtn"; btn.type = "button";
  btn.title = L("Show my live location in the 3D twin and on the map", "Meinen Live-Standort im 3D-Zwilling und auf der Karte zeigen");
  const paint = () => {
    btn.classList.toggle("on", P.on); btn.classList.toggle("sim", P.on && P.sim);
    btn.innerHTML = `<span class="dot"></span>${P.on ? (P.sim ? L("On site (sim.)", "Vor Ort (Sim.)") : L("Live location", "Live-Standort")) : "📍 " + L("Locate me", "Wo bin ich?")}`;
  };
  paint();
  (q("#storyBtn") || q("#autoBtn"))?.before(btn);

  async function send(body) {
    try {
      const r = await api("/api/site/presence", { json: { device: DEV, name: L("You", "Du"), kind: "laptop", ...body } });
      P.last = r;
      if (!P.told) { P.told = true; tell(r); }
      poll();
    } catch (e) { NW.toast?.(e.message); }
  }
  function tell(r) {
    const msg = r.simulated ? L("📍 You're on site (simulated) – site facilities", "📍 Du bist vor Ort (simuliert) – Baustelleneinrichtung")
      : r.on_site ? L(`📍 You're on site${r.zone ? "" : ""} · ±${Math.round(r.accuracy || 0)} m`, `📍 Du bist auf der Baustelle · ±${Math.round(r.accuracy || 0)} m`)
      : r.distance_m != null ? L(`📍 Found you: ${(r.distance_m / 1000).toFixed(1)} km from the site`, `📍 Gefunden: ${(r.distance_m / 1000).toFixed(1)} km von der Baustelle`)
      : L("📍 Found you", "📍 Standort gefunden");
    window.SFX?.done(msg.replace(/^📍\s*/, ""));
    if (window.SiteTwin?.focusPresence && document.getElementById("twin")?.classList.contains("on")) setTimeout(() => window.SiteTwin.focusPresence(DEV), 400);
  }
  function start() {
    P.on = true; P.told = false; paint();
    if (P.sim) return send({ simulate: true });
    if (!navigator.geolocation) { P.sim = true; return send({ simulate: true }); }
    btn.innerHTML = `<span class="dot"></span>${L("Locating…", "Suche…")}`;
    P.watch = navigator.geolocation.watchPosition(
      pos => { const c = pos.coords; send({ lat: c.latitude, lon: c.longitude, accuracy: c.accuracy, heading: c.heading }); paint(); },
      err => {
        P.on = false; paint();
        window.SFX?.alert();
        showMenu(L("Location blocked or unavailable. Allow it in the browser (lock icon in the address bar), or simulate being on site.",
                   "Standort blockiert oder nicht verfügbar. Im Browser erlauben (Schloss-Symbol) oder vor Ort simulieren."));
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 });
  }
  function stop() {
    P.on = false; paint();
    if (P.watch != null) navigator.geolocation.clearWatch(P.watch);
    P.watch = null;
    api(`/api/site/presence/${DEV}`, { method: "DELETE" }).catch(() => {});
    setTimeout(poll, 300);
  }
  btn.onclick = () => (P.on ? stop() : start());

  // small chooser: real GPS or simulated
  let menu;
  function showMenu(note) {
    menu?.remove();
    menu = document.createElement("div");
    menu.className = "card"; menu.style.cssText = "position:fixed;top:64px;right:16px;z-index:9300;max-width:320px;padding:14px 16px";
    menu.innerHTML = `<b>📍 ${L("Where am I?", "Wo bin ich?")}</b><p class="mut" style="margin:6px 0 10px;font-size:13px">${esc(note)}</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="p s" data-m="sim">${L("Simulate on site", "Vor Ort simulieren")}</button><button class="s" data-m="real">${L("Try GPS again", "GPS erneut")}</button><button class="s" data-m="x">✕</button></div>`;
    document.body.appendChild(menu);
    menu.onclick = e => {
      const m = e.target.closest("[data-m]")?.dataset.m; if (!m) return;
      menu.remove();
      if (m === "sim") { P.sim = true; store.set("nw-sim", "1"); start(); }
      if (m === "real") { P.sim = false; store.set("nw-sim", "0"); start(); }
    };
  }
  btn.addEventListener("contextmenu", e => { e.preventDefault(); showMenu(L("Use your real GPS position, or place yourself at the site facilities for the demo.", "Echte GPS-Position nutzen oder für die Demo in der Baustelleneinrichtung platzieren.")); });

  // everyone's positions -> twin + map
  const seenCounts = { photos: null, msgs: null };
  async function poll() {
    try { P.list = await api("/api/site/presence"); } catch { return; }
    window.SiteTwin?.setPresence?.(P.list);
    drawMap();
    window.BB?.emit?.("presence", P.list);
    if (P.list.some(p => p.kind === "phone") || seenCounts.photos === null) phoneSync();
  }
  // a phone added a photo or a note: refresh the laptop's views and say so
  async function phoneSync() {
    try {
      const [ph, ms] = await Promise.all([api("/api/photos"), api("/api/messages")]);
      const np = ph.length, nm = (Array.isArray(ms) ? ms : ms.messages || []).length;
      if (seenCounts.photos !== null && np > seenCounts.photos) {
        window.SiteTwin?.reload?.(); window.loadPhotos?.();
        window.SFX?.done(L("📱 New photo from the site phone", "📱 Neues Foto vom Baustellen-Handy").replace(/^📱\s*/, "📱 "));
      }
      if (seenCounts.msgs !== null && nm > seenCounts.msgs) { NW.loadMsgs?.(); }
      seenCounts.photos = np; seenCounts.msgs = nm;
    } catch {}
  }

  // ⋯ menu: phone app link + QR code
  function addPhoneItem() {
    const pop = q("#glMenuPop"); if (!pop || q("#phoneItem")) return !!pop;
    pop.insertAdjacentHTML("afterbegin", `<button type="button" class="s" id="phoneItem">📱 ${L("Phone app (QR)", "Handy-App (QR)")}</button><div class="gl-sep"></div>`);
    q("#phoneItem").onclick = phoneModal;
    return true;
  }
  if (!addPhoneItem()) addEventListener("load", addPhoneItem);
  async function phoneModal() {
    let info = {};
    try { info = await api("/api/site/phone"); } catch {}
    if (window.Story?.phoneCard) {                     // same animated "scan -> talk -> live" card as the preview
      const box = document.createElement("div");
      box.className = "st-phonebox on"; box.style.zIndex = 9600;
      box.innerHTML = window.Story.phoneCard(info);
      box.querySelector(".st-pside").insertAdjacentHTML("beforeend", `<div style="margin-top:14px"><button class="s" data-x>${L("Close", "Schließen")}</button></div>`);
      document.body.appendChild(box);
      box.onclick = e => { if (e.target === box || e.target.closest("[data-x]")) box.remove(); };
      return;
    }
    const box = document.createElement("div");
    box.className = "st-final on"; box.style.zIndex = 9600;
    box.innerHTML = `<div class="st-fbox" style="max-width:420px;text-align:center">
      <h2>📱 ${L("Scan to open on your phone", "Mit dem Handy scannen")}</h2>
      ${info.qr ? `<img src="${info.qr}" alt="QR" style="width:240px;height:240px;border-radius:14px;background:#fff;padding:8px;margin:14px auto;display:block">
        <p class="mut" style="word-break:break-all;font-size:12px">${esc(info.url)}</p>
        <p style="font-size:14px">${L("Hold to talk, take photos, share your location. Everything appears here live.", "Halten zum Sprechen, Fotos, Standort teilen. Alles erscheint hier live.")}</p>`
      : `<p style="font-size:14px;margin:16px 0">${L("Phones need a secure (HTTPS) link. Start it on this laptop:", "Handys brauchen einen sicheren (HTTPS-)Link. Auf diesem Laptop starten:")}</p>
        <pre style="text-align:left;background:rgba(0,0,0,.35);padding:10px;border-radius:10px;font-size:12px;overflow:auto">cd backend && ./scripts/phone_tunnel.sh</pre>
        <p class="mut" style="font-size:12.5px">${L("Then open this window again.", "Dann dieses Fenster erneut öffnen.")}</p>`}
      <div class="st-facts" style="justify-content:center"><button class="s" data-x>${L("Close", "Schließen")}</button></div></div>`;
    document.body.appendChild(box);
    box.onclick = e => { if (e.target === box || e.target.closest("[data-x]")) box.remove(); };
  }
  function mapButtons() {
    if (map._youCtl) return;
    const Ctl = window.L.Control.extend({ onAdd() {
      const d = window.L.DomUtil.create("div", "leaflet-bar");
      d.innerHTML = `<a href="#" title="${L("Show me", "Zeig mich")}" style="width:auto;padding:0 10px;font-weight:600">📍 ${L("Me", "Ich")}</a><a href="#" title="${L("Show the site", "Baustelle zeigen")}" style="width:auto;padding:0 10px;font-weight:600">🏗️ ${L("Site", "Baustelle")}</a>`;
      const [me, site] = d.querySelectorAll("a");
      window.L.DomEvent.disableClickPropagation(d);
      me.onclick = e => { e.preventDefault(); const p = P.list.find(x => x.device === DEV) || P.list[0]; if (!p) { start(); return; }
        const pts = [[p.lat, p.lon]]; if (typeof photos !== "undefined" && photos.length) pts.push([photos[0].lat, photos[0].lon]);
        pts.length > 1 && p.distance_m > 300 ? map.fitBounds(pts, { padding: [60, 60] }) : map.setView([p.lat, p.lon], 17); };
      site.onclick = e => { e.preventDefault(); const pts = (typeof photos !== "undefined" ? photos : []).map(x => [x.lat, x.lon]);
        pts.length ? map.fitBounds(pts, { padding: [40, 40], maxZoom: 18 }) : map.setView([cfg.site.lat, cfg.site.lon], 16); };
      return d; } });
    map._youCtl = new Ctl({ position: "topright" }).addTo(map);
  }
  function drawMap() {
    if (typeof map === "undefined" || !map || !window.L) return;       // Leaflet map of app.js (Map tab)
    mapButtons();
    const seen = new Set();
    for (const p of P.list) {
      if (p.lat == null) continue;
      seen.add(p.device);
      let m = P.markers.get(p.device);
      const icon = window.L.divIcon({ className: "", html: `<div class="you-map${p.simulated ? " sim" : ""}"><b></b><i></i></div>`, iconSize: [22, 22], iconAnchor: [11, 11] });
      if (!m) { m = window.L.marker([p.lat, p.lon], { icon, zIndexOffset: 1000 }).addTo(map); P.markers.set(p.device, m); }
      m.setLatLng([p.lat, p.lon]); m.setIcon(icon);
      m.bindTooltip(`${p.kind === "phone" ? "📱" : "📍"} ${esc(p.name)}${p.simulated ? " · simulated" : p.accuracy ? ` · ±${Math.round(p.accuracy)} m` : ""}${p.distance_m != null && !p.on_site ? ` · ${(p.distance_m / 1000).toFixed(1)} km to site` : ""}`, { permanent: true, direction: "top", offset: [0, -12] });
    }
    for (const [d, m] of P.markers) if (!seen.has(d)) { m.remove(); P.markers.delete(d); }
  }
  setInterval(poll, 3000);
  addEventListener("load", () => setTimeout(poll, 800));
  window.Presence = { start, stop, poll, get list() { return P.list; }, device: DEV };
})();
