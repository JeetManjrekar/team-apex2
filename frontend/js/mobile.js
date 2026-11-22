/* BauBuddy · phone capture page (m.html). Same backend as the laptop:
   voice  -> /api/voice (transcribe) -> /api/agent (incident? question?) -> /api/chat for drafting
   photo  -> /api/photos (detector + incident rules); without EXIF GPS it takes the phone's live position
   place  -> /api/site/presence every few seconds while sharing ("📱 Site phone" in the laptop's 3D twin) */
(() => {
  "use strict";
  const $ = s => document.querySelector(s);
  const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
  let lang = store.get("nw-lang") === "de" ? "de" : "en";        // English by default, same switch as the laptop
  const L = (en, de) => (lang === "de" ? de : en);
  const DEV = store.get("nw-mdev") || (() => { const id = "ph-" + Math.random().toString(36).slice(2, 9); store.set("nw-mdev", id); return id; })();
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const api = (u, o = {}) => {
    o.headers = { ...(o.headers || {}), "X-Lang": lang };
    if (o.json) { o.method = o.method || "POST"; o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(o.json); }
    return fetch(u, o).then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || r.statusText); return j; });
  };
  const buzz = ms => { try { navigator.vibrate?.(ms); } catch {} };

  /* ---------------- ui text */
  function texts() {
    $("#lang").textContent = lang.toUpperCase();
    $("#txt").placeholder = L("Type a note…", "Notiz tippen…");
    $("#camL").textContent = L("Photo", "Foto");
    $("#simL").textContent = L("On site", "Vor Ort");
    $("#hint").textContent = L("Hold to talk · release to send", "Gedrückt halten · loslassen zum Senden");
    const e = $(".empty");
    if (e) e.innerHTML = L("<b>Hold the button and talk</b>“Excavator idle since 10, hydraulic failure at Axis 1”<br>or take a photo of the site.",
                           "<b>Knopf halten und sprechen</b>„Bagger steht seit 10 Uhr, Hydraulikschaden an Achse 1“<br>oder ein Foto der Baustelle machen.");
    paintLoc();
  }
  $("#lang").onclick = () => { lang = lang === "de" ? "en" : "de"; store.set("nw-lang", lang); texts(); };
  api("/api/config").then(c => { $("#site").textContent = c.site?.name || "Site"; }).catch(() => {});

  /* ---------------- feed */
  function add(role, html, cls = "") {
    $(".empty")?.remove();
    const el = document.createElement("div");
    el.className = `msg ${role} ${cls}`; el.innerHTML = html;
    $("#feed").appendChild(el); $("#feed").scrollTop = 1e9;
    return el;
  }
  let tt;
  function toast(t, bad) {
    const el = $("#toast"); el.textContent = t; el.classList.toggle("bad", !!bad); el.classList.add("on");
    clearTimeout(tt); tt = setTimeout(() => el.classList.remove("on"), 2400);
  }

  /* ---------------- the assistant: same routing as the laptop's AI Manager */
  let ctx = {};
  async function ask(text, { voice = false } = {}) {
    text = (text || "").trim(); if (!text) return;
    add("me", esc(text) + (voice ? `<small>🎙 ${L("voice", "Sprache")}</small>` : ""));
    window.SFX?.send();
    const wait = add("ai", "…");
    try {
      const r = await api("/api/agent", { json: { text, ctx, lang } });
      ctx = r.ctx || ctx;
      if (r.handoff === "chat") {
        const c = await api("/api/chat", { json: { text, voice, lang } });
        const rep = (c.replies || []).filter(m => m.role === "assistant");
        wait.remove();
        rep.forEach(m => add("ai", esc(m.text), /^✓/.test(m.text) ? "ok" : ""));
        const made = rep.find(m => /^✓ (Draft ready|Added to|Entwurf fertig|Ergänzt)/.test(m.text));
        if (made) { buzz([30, 40, 30]); window.SFX?.done(); toast("✓ " + made.text.replace(/^✓\s*/, "").split(".")[0]); }
        return;
      }
      wait.remove();
      const inc = (r.actions || []).some(a => a.type === "incident.open") && r.intents?.includes("reported");
      add("ai", esc(r.speech || L("Done.", "Erledigt.")), inc ? "warn" : "");
      if (inc) { buzz([80, 60, 80]); window.SFX?.alert(); toast(L("⚠ Incident sent to the site manager", "⚠ Vorfall an die Bauleitung gemeldet"), true); }
    } catch (e) { wait.remove(); add("ai", esc(e.message), "warn"); window.SFX?.alert(); }
  }
  $("#send").onclick = () => { const t = $("#txt").value; $("#txt").value = ""; ask(t); };
  $("#txt").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); $("#send").click(); } };

  /* ---------------- hold to talk */
  let rec = null, chunks = [], t0 = 0, stream = null;
  const mic = $("#mic");
  async function down(e) {
    e.preventDefault();
    if (rec || mic.classList.contains("busy")) return;
    if (!navigator.mediaDevices?.getUserMedia) return toast(L("Microphone needs HTTPS", "Mikrofon braucht HTTPS"), true);
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch { return toast(L("Microphone blocked", "Mikrofon blockiert"), true); }
    const type = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find(t => window.MediaRecorder?.isTypeSupported?.(t)) || "";
    rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    chunks = []; rec.ondataavailable = ev => ev.data.size && chunks.push(ev.data);
    rec.start(); t0 = performance.now();
    mic.classList.add("rec"); buzz(20); window.SFX?.tap();
    $("#hint").textContent = L("Listening… release to send", "Hört zu… loslassen zum Senden");
  }
  async function up(e) {
    e?.preventDefault?.();
    if (!rec) return;
    const r = rec; rec = null;
    mic.classList.remove("rec");
    const dur = performance.now() - t0;
    await new Promise(res => { r.onstop = res; r.stop(); });
    stream?.getTracks().forEach(t => t.stop());
    if (dur < 600) { $("#hint").textContent = L("Hold a bit longer", "Etwas länger halten"); return; }
    const blob = new Blob(chunks, { type: r.mimeType || "audio/webm" });
    mic.classList.add("busy"); $("#hint").textContent = L("Transcribing…", "Wird transkribiert…");
    try {
      const fd = new FormData();
      fd.append("audio", blob, blob.type.includes("mp4") ? "voice.m4a" : "voice.webm"); fd.append("submit", "false"); fd.append("language", lang);
      const tr = await fetch("/api/voice", { method: "POST", body: fd }).then(x => x.json());
      const text = tr?.transcript?.text || "";
      if (!text) throw new Error(tr?.detail || L("Nothing understood", "Nichts verstanden"));
      await ask(text, { voice: true });
    } catch (err) { toast(err.message, true); }
    finally { mic.classList.remove("busy"); $("#hint").textContent = L("Hold to talk · release to send", "Gedrückt halten · loslassen zum Senden"); }
  }
  mic.addEventListener("pointerdown", down);
  ["pointerup", "pointercancel", "pointerleave"].forEach(ev => mic.addEventListener(ev, up));

  /* ---------------- photo */
  $("#cam").onchange = async e => {
    const f = e.target.files?.[0]; e.target.value = ""; if (!f) return;
    const url = URL.createObjectURL(f);
    const bubble = add("me", `<img src="${url}" alt=""><small>📷 ${L("uploading…", "wird hochgeladen…")}</small>`);
    try {
      const fd = new FormData(); fd.append("files", f, f.name || "photo.jpg");
      const [p] = await fetch("/api/photos", { method: "POST", body: fd }).then(async r => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || r.statusText); return j; });
      let where = p.location_source === "exif" ? L("GPS from photo", "GPS aus Foto") : "";
      if (p.location_source !== "exif" && loc.last?.lat != null) {          // browsers often strip GPS: use the live position
        await api(`/api/photos/${p.id}`, { method: "PATCH", json: { lat: loc.last.lat, lon: loc.last.lon } }).catch(() => {});
        where = loc.last.simulated ? L("placed at your (simulated) position", "an deiner (simulierten) Position") : L("placed at your live position", "an deinem Live-Standort");
      }
      const dets = (p.detections || []).map(d => `${d.class.replace(/_/g, " ")} ${Math.round(d.confidence * 100)}%`).join(", ");
      bubble.querySelector("small").textContent = `📷 ${dets || L("no machines detected", "keine Maschinen erkannt")}${where ? " · " + where : ""}`;
      buzz(30); window.SFX?.done(); toast(L("✓ Photo on the site plan", "✓ Foto im Lageplan"));
    } catch (err) { bubble.querySelector("small").textContent = "⚠ " + err.message; window.SFX?.alert(); }
  };

  /* ---------------- live location */
  const loc = { on: false, sim: store.get("nw-msim") === "1", watch: null, last: null, timer: null };
  function paintLoc() {
    const el = $("#loc"), r = loc.last;
    el.classList.toggle("on", loc.on && !loc.sim); el.classList.toggle("sim", loc.on && loc.sim);
    $("#locBtn").textContent = loc.on ? L("Stop", "Stopp") : L("Share", "Teilen");
    $("#sim").style.borderColor = loc.sim ? "#8b5cf6" : "";
    if (!loc.on) { $("#locT").textContent = L("Location off", "Standort aus"); $("#locS").textContent = L("Tap Share to appear in the 3D twin", "Teilen tippen, um im 3D-Zwilling zu erscheinen"); return; }
    if (!r) { $("#locT").textContent = L("Locating…", "Suche Standort…"); $("#locS").textContent = ""; return; }
    if (r.simulated) { $("#locT").textContent = L("📍 On site (simulated)", "📍 Vor Ort (simuliert)"); $("#locS").textContent = L("Visible in the 3D twin", "Im 3D-Zwilling sichtbar"); return; }
    $("#locT").textContent = r.on_site ? L("📍 You're on site", "📍 Du bist auf der Baustelle") : `📍 ${(r.distance_m / 1000).toFixed(1)} km ${L("from the site", "von der Baustelle")}`;
    $("#locS").textContent = `±${Math.round(r.accuracy || 0)} m · ${L("live in the 3D twin", "live im 3D-Zwilling")}`;
  }
  async function send(body) {
    try { loc.last = await api("/api/site/presence", { json: { device: DEV, name: L("Site phone", "Baustellen-Handy"), kind: "phone", ...body } }); }
    catch (e) { toast(e.message, true); }
    paintLoc();
  }
  function startLoc() {
    loc.on = true; loc.last = null; paintLoc();
    clearInterval(loc.timer);
    if (loc.sim || !navigator.geolocation) {
      send({ simulate: true }); loc.timer = setInterval(() => send({ simulate: true }), 15000);
      return;
    }
    loc.watch = navigator.geolocation.watchPosition(
      p => send({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy, heading: p.coords.heading }),
      () => { toast(L("Location blocked – simulating on site", "Standort blockiert – simuliere vor Ort"), true); loc.sim = true; store.set("nw-msim", "1"); startLoc(); },
      { enableHighAccuracy: true, maximumAge: 4000, timeout: 15000 });
    // keep the entry alive while standing still
    loc.timer = setInterval(() => { if (loc.last && !loc.sim) send({ lat: loc.last.lat, lon: loc.last.lon, accuracy: loc.last.accuracy }); }, 30000);
  }
  function stopLoc() {
    loc.on = false; paintLoc();
    if (loc.watch != null) navigator.geolocation.clearWatch(loc.watch);
    loc.watch = null; clearInterval(loc.timer);
    fetch(`/api/site/presence/${DEV}`, { method: "DELETE" }).catch(() => {});
  }
  $("#locBtn").onclick = () => (loc.on ? stopLoc() : startLoc());
  $("#loc").onclick = e => { if (!e.target.closest("button") && !loc.on) startLoc(); };
  $("#sim").onclick = () => { loc.sim = !loc.sim; store.set("nw-msim", loc.sim ? "1" : "0"); toast(loc.sim ? L("🏗️ Simulating: on site", "🏗️ Simuliert: vor Ort") : L("📍 Using real GPS", "📍 Echtes GPS")); if (loc.on) { stopLoc(); } startLoc(); };
  texts();
})();
