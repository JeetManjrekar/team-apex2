/* BauBuddy · AI Site Manager (command centre).
   The one assistant interface (voice, chat, photo/file upload, command palette): one command -> backend orchestrator (POST /api/agent) -> real tools
   (plan, twin, photos, detections, incidents) -> evidence cards + 2D plan + 3D twin actions -> spoken answer.
   Drafting commands (rock at pile 7, excavator idle, ...) are handed to the existing chat pipeline (/api/chat).

   Shared state + event bus: window.BB. Other modules can listen:
     BB.on("agent:result", r => …)  BB.on("incident:new", list => …)  BB.on("state", s => …)
   States shown by the core: idle · listening · processing · analysing · executing · responding. Each one is set by a
   real event (mic open, request in flight, backend steps, UI actions, speech synthesis), never by a timer on its own. */
(() => {
  "use strict";
  const NW = window.NW; if (!NW) return;
  const API = window.API_BASE || "";
  const q = (s, r = document) => r.querySelector(s), qa = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = NW.esc;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
  const api = NW.api;

  /* ------------------------------------------------------------------ shared state + bus */
  const bus = new EventTarget();
  const BB = window.BB = {
    state: { ai: "idle", ctx: {}, incidents: [], highlights: [], focusZone: null, twin: null, last: null, lang: store.get("nw-lang") === "de" ? "de" : "en" },
    on(ev, fn) { bus.addEventListener(ev, e => fn(e.detail)); },
    emit(ev, detail) { bus.dispatchEvent(new CustomEvent(ev, { detail })); },
  };
  const S = BB.state;
  const L = (en, de) => (S.lang === "de" ? de : en);

  /* ------------------------------------------------------------------ view */
  const ICON = {
    mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
    stop: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    spk: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/></svg>',
    mute: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9l5 6M22 9l-5 6"/></svg>',
    grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/></svg>',
    camera: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>',
    clip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11.5l-8 8a5 5 0 0 1-7-7l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7L9.7 17.2a1.7 1.7 0 0 1-2.4-2.4L15 7"/></svg>',
    core: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="9" stroke-dasharray="3 3"/></svg>',
  };
  const STATES = [["idle", L("Idle", "Bereit")], ["listening", L("Listening", "Hört zu")], ["processing", L("Processing", "Verarbeitet")],
    ["analysing", L("Analysing evidence", "Analysiert Belege")], ["executing", L("Executing", "Führt aus")], ["responding", L("Responding", "Antwortet")]];
  const CHIPS = [
    [L("Today's progress", "Fortschritt heute"), L("Give me today's construction progress.", "Wie ist der Baufortschritt heute?")],
    [L("Safety check", "Sicherheitscheck"), L("Identify safety violations on this site.", "Gibt es Sicherheitsverstöße auf der Baustelle?")],
    [L("Plan vs actual", "Soll-Ist"), L("Compare planned progress with actual progress.", "Vergleiche Soll und Ist im Bauzeitenplan.")],
    [L("Latest incidents", "Letzte Vorfälle"), L("Show me the latest detected incidents.", "Zeig mir die zuletzt erkannten Vorfälle.")],
    [L("Helmets?", "Helme?"), L("Are there any workers without safety helmets?", "Gibt es Arbeiter ohne Schutzhelm?")],
    [L("Restricted zones", "Sperrbereiche"), L("Identify equipment operating in restricted zones.", "Gibt es Geräte in Sperrbereichen?")],
    [L("Since yesterday", "Seit gestern"), L("Show me what has changed since yesterday.", "Was hat sich seit gestern geändert?")],
    [L("Inspect excavation", "Aushub prüfen"), L("Show me the excavation area in the 3D model.", "Zeig mir den Aushub im 3D-Modell.")],
    [L("Inspection report", "Prüfbericht"), L("Generate today's site inspection report.", "Erstelle den Baustellen-Prüfbericht für heute.")],
  ];

  const nav = q("#nav"), main = q("main");
  const navBtn = document.createElement("button");
  navBtn.dataset.t = "command"; navBtn.className = "on bb-navbtn";
  navBtn.innerHTML = `<span class="gl-ic">${ICON.core}</span><span>${L("AI Manager", "KI-Bauleiter")}</span>`;
  navBtn.onclick = () => NW.TAB("command");
  nav.insertBefore(navBtn, nav.querySelector("button"));
  qa("#nav button").forEach(b => b !== navBtn && b.classList.remove("on"));
  qa("section.tab").forEach(s => s.classList.remove("on"));

  const sec = document.createElement("section");
  sec.id = "command"; sec.className = "tab on";
  sec.innerHTML = `
  <div class="bb-grid">
    <div class="bb-core card">
      <div class="bb-orb-wrap"><canvas id="bbOrb" width="560" height="560" aria-hidden="true"></canvas>
        <div class="bb-orb-label"><b id="bbStateTxt">${L("Idle", "Bereit")}</b><span id="bbStateSub">${L("AI Site Manager", "KI-Bauleiter")}</span></div></div>
      <ol class="bb-rail" id="bbRail">${STATES.map(([k, t]) => `<li data-s="${k}"><i></i>${esc(t)}</li>`).join("")}</ol>
      <div class="bb-hist"><div id="bbHist" class="bb-histlist" aria-live="polite"></div></div>
      <div class="bb-live" id="bbLive" hidden></div>
      <div class="bb-compose">
        <div class="bb-tray" id="bbTray" hidden></div>
        <div class="bb-pal" id="bbPal" role="menu" hidden>${CHIPS.map(([l, t]) => `<button class="bb-chip" role="menuitem" data-cmd="${esc(t)}">${esc(l)}</button>`).join("")}</div>
        <div class="bb-in">
          <button class="bb-mic" id="bbMic" title="${L("Speak a command", "Befehl sprechen")}" aria-label="${L("Speak a command", "Befehl sprechen")}">${ICON.mic}<span class="bb-ring"></span><span class="bb-ring r2"></span></button>
          <div class="bb-field"><input id="bbInp" autocomplete="off" placeholder="${L("Ask or command…", "Frage oder Befehl …")}">
            <button class="bb-send" id="bbSend" aria-label="${L("Send", "Senden")}">${ICON.send}</button></div>
        </div>
        <div class="bb-tools">
          <button class="bb-tool" id="bbPalBtn" aria-expanded="false" aria-controls="bbPal" title="${L("Commands", "Befehle")}">${ICON.grid}<span>${L("Commands", "Befehle")}</span></button>
          <button class="bb-tool" id="bbPhotoBtn" title="${L("Upload photos", "Fotos hochladen")}">${ICON.camera}<span>${L("Photos", "Fotos")}</span></button>
          <button class="bb-tool" id="bbFileBtn" title="${L("Upload files", "Dateien hochladen")}">${ICON.clip}<span>${L("Files", "Dateien")}</span></button>
        </div>
        <input type="file" id="bbPhotoIn" accept="image/*" multiple hidden>
        <input type="file" id="bbFileIn" accept=".eml,.ics,.pdf,.docx,.xlsx,.csv,.geojson,.json,audio/*,.m4a,.mp3,.wav,.ogg,.oga,.opus,.webm,.flac,.aac,.amr" multiple hidden>
      </div>
    </div>
    <div class="bb-work"><div id="bbCards" class="bb-cards"></div></div>
    <div class="bb-side">
      <div class="card bb-plan"><div class="bb-h"><b>${L("Site plan", "Lageplan")}</b><button class="s" id="bbTo3d">${L("Open 3D twin", "3D-Zwilling öffnen")}</button></div>
        <div id="bbPlan" class="bb-plansvg"><div class="mut pad">${L("Loading plan…", "Plan wird geladen …")}</div></div>
        <div class="bb-legend"><span><i class="r"></i>${L("incident / critical", "Vorfall / kritisch")}</span><span><i class="a"></i>${L("behind plan / check", "Verzug / prüfen")}</span><span><i class="p"></i>${L("photo", "Foto")}</span></div></div>
      <div class="card bb-feed"><div class="bb-h"><b>${L("Incident feed", "Vorfälle")}</b><span class="bb-livedot" title="${L("Polling every 5 s", "Abfrage alle 5 s")}"></span></div><div id="bbFeed"></div></div>
    </div>
  </div>`;
  main.insertBefore(sec, main.firstElementChild);

  // dock: the assistant stays reachable on every other tab and narrates what it is doing there
  const dock = document.createElement("div");
  dock.id = "bbDock"; dock.innerHTML = `<button class="bb-dorb" title="${L("Back to AI Manager", "Zurück zum KI-Bauleiter")}"><span></span></button><div class="bb-dtxt" id="bbDockTxt"></div>`;
  document.body.appendChild(dock);
  q(".bb-dorb", dock).onclick = () => NW.TAB("command");

  const modal = document.createElement("div");
  modal.id = "bbModal"; modal.hidden = true; document.body.appendChild(modal);
  const toasts = document.createElement("div"); toasts.id = "bbToasts"; document.body.appendChild(toasts);

  /* ------------------------------------------------------------------ state machine */
  const SUB = { idle: L("Ready for your command", "Bereit für Ihren Befehl"), listening: L("Speak now", "Sprechen Sie jetzt"), processing: L("Understanding the request", "Anfrage wird verstanden"),
    analysing: L("Reading site evidence", "Baustellenbelege werden gelesen"), executing: L("Updating views", "Ansichten werden aktualisiert"), responding: L("Answering", "Antwort") };
  function setState(s, sub) {
    S.ai = s; document.body.dataset.ai = s;
    q("#bbStateTxt").textContent = (STATES.find(x => x[0] === s) || [, s])[1];
    q("#bbStateSub").textContent = sub || SUB[s] || "";
    qa("#bbRail li").forEach(li => { li.classList.toggle("on", li.dataset.s === s); });
    dockSay(s === "idle" ? "" : (sub || SUB[s]));
    BB.emit("state", s);
    orbKick();
  }
  function dockSay(t) { q("#bbDockTxt").textContent = t || ""; dock.classList.toggle("talk", !!t); }
  const showDock = () => dock.classList.toggle("on", !sec.classList.contains("on"));
  new MutationObserver(() => { showDock(); orbKick(); }).observe(sec, { attributes: true, attributeFilter: ["class"] });

  /* ------------------------------------------------------------------ orb (canvas; only animates while visible) */
  const cv = q("#bbOrb"), cx = cv.getContext("2d");
  const COL = { idle: [255, 122, 0], listening: [56, 189, 248], processing: [167, 139, 250], analysing: [34, 211, 238], executing: [255, 154, 31], responding: [61, 220, 132] };
  let level = 0, target = 0, spoke = 0, orbOn = false, col = [255, 122, 0];
  function orbKick() { if (!orbOn && sec.classList.contains("on") && !document.hidden) { orbOn = true; requestAnimationFrame(orb); } }
  document.addEventListener("visibilitychange", orbKick);
  function orb(ts) {
    if (!sec.classList.contains("on") || document.hidden) { orbOn = false; return; }
    const t = ts / 1000, W = cv.width, H = cv.height, c = W / 2, s = S.ai;
    const tc = COL[s] || COL.idle; col = col.map((v, i) => v + (tc[i] - v) * 0.08);
    const [r, g, b] = col.map(Math.round), rgba = a => `rgba(${r},${g},${b},${a})`;
    if (s === "responding") target = Math.max(0.15, Math.exp(-(performance.now() - spoke) / 260) * 0.9);
    else if (s !== "listening") target = s === "idle" ? 0.05 : 0.22;
    level += (target - level) * 0.18;
    cx.clearRect(0, 0, W, H);
    const R = W * 0.24;
    const glow = cx.createRadialGradient(c, c, R * 0.2, c, c, R * 2);
    glow.addColorStop(0, rgba(0.38 + level * 0.3)); glow.addColorStop(0.45, rgba(0.08)); glow.addColorStop(1, rgba(0));
    cx.fillStyle = glow; cx.fillRect(0, 0, W, H);
    // waveform ring
    cx.lineWidth = 3; cx.strokeStyle = rgba(0.95); cx.beginPath();
    for (let i = 0; i <= 160; i++) {
      const a = (i / 160) * Math.PI * 2;
      const n = Math.sin(a * 6 + t * 3.1) * 0.5 + Math.sin(a * 11 - t * 4.3) * 0.3 + Math.sin(a * 3 + t * 1.7) * 0.2;
      const rr = R * (1 + n * (0.03 + level * 0.32));
      const x = c + Math.cos(a) * rr, y = c + Math.sin(a) * rr; i ? cx.lineTo(x, y) : cx.moveTo(x, y);
    }
    cx.closePath(); cx.stroke();
    cx.fillStyle = rgba(0.10); cx.fill();
    // inner core
    const core = cx.createRadialGradient(c - R * 0.2, c - R * 0.25, 2, c, c, R * 0.62);
    core.addColorStop(0, "rgba(255,255,255,.95)"); core.addColorStop(0.35, rgba(0.9)); core.addColorStop(1, rgba(0.05));
    cx.fillStyle = core; cx.beginPath(); cx.arc(c, c, R * (0.5 + level * 0.12), 0, Math.PI * 2); cx.fill();
    // orbit arcs: spin while the system works
    const busy = s === "processing" || s === "analysing" || s === "executing";
    for (let k = 0; k < 3; k++) {
      const rr = R * (1.32 + k * 0.17), sp = (busy ? 1.6 : 0.25) * (k % 2 ? -1 : 1);
      cx.strokeStyle = rgba(busy ? 0.75 - k * 0.18 : 0.22 - k * 0.05); cx.lineWidth = busy ? 3 - k * 0.6 : 1.5;
      cx.beginPath(); cx.arc(c, c, rr, t * sp + k, t * sp + k + (busy ? 1.6 : Math.PI * 1.6)); cx.stroke();
    }
    // analysing: radar sweep
    if (s === "analysing") {
      const a = t * 2.6, gr = cx.createConicGradient ? cx.createConicGradient(a, c, c) : null;
      if (gr) { gr.addColorStop(0, rgba(0.35)); gr.addColorStop(0.12, rgba(0)); gr.addColorStop(1, rgba(0)); cx.fillStyle = gr; cx.beginPath(); cx.arc(c, c, R * 1.85, 0, Math.PI * 2); cx.fill(); }
    }
    // tick marks
    cx.strokeStyle = rgba(0.25); cx.lineWidth = 2;
    for (let i = 0; i < 60; i++) { const a = i / 60 * Math.PI * 2 + (busy ? t * 0.3 : 0), r1 = R * 1.95, r2 = R * (i % 5 ? 2.0 : 2.06);
      cx.beginPath(); cx.moveTo(c + Math.cos(a) * r1, c + Math.sin(a) * r1); cx.lineTo(c + Math.cos(a) * r2, c + Math.sin(a) * r2); cx.stroke(); }
    requestAnimationFrame(orb);
  }

  /* ------------------------------------------------------------------ text to speech */
  let ttsOn = store.get("bb-tts") !== "0";
  const ttsLabel = () => (ttsOn ? "🗣️ " + L("Voice answers on", "Sprachausgabe an") : "🔇 " + L("Voice answers off", "Sprachausgabe aus"));
  function addTtsToggle() {
    const pop = q("#glMenuPop"); if (!pop || q("#bbTtsItem")) return !!pop;
    pop.insertAdjacentHTML("beforeend", `<button type="button" class="s" id="bbTtsItem">${ttsLabel()}</button>`);
    q("#bbTtsItem").onclick = () => { ttsOn = !ttsOn; store.set("bb-tts", ttsOn ? "1" : "0"); q("#bbTtsItem").textContent = ttsLabel(); if (!ttsOn) speechSynthesis?.cancel(); };
    return true;
  }
  if (!addTtsToggle()) addEventListener("load", () => setTimeout(addTtsToggle, 200));
  function pickVoice(lang) {
    const vs = speechSynthesis.getVoices(), pre = lang === "de" ? "de" : "en";
    return vs.find(v => v.lang?.toLowerCase().startsWith(pre) && /natural|neural|premium|enhanced|google/i.test(v.name)) || vs.find(v => v.lang?.toLowerCase().startsWith(pre));
  }
  // short spoken form of a reply: people read the details, the voice only confirms
  function brief(t) {
    const x = String(t || ""), de = S.lang === "de", n = re => +((x.match(re) || [])[1] || 0);
    const R = [
      [/^(good (morning|afternoon|evening)|guten (morgen|tag|abend)|hello|hallo)/i, () => de ? "Guten Morgen." : "Good morning."],
      [/attention|achtung/i, () => de ? "Sicherheitshinweis." : "Safety alert."],
      [/draft ready|entwurf fertig|added to|ergänzt/i, () => de ? "Entwurf fertig." : "Draft ready."],
      [/all filled|alles ausgefüllt/i, () => de ? "Alles erledigt." : "All set."],
      [/^✓/, () => de ? "Verstanden." : "Got it."],
      [/compiling the report|bericht wird erstellt|erstelle den bericht/i, () => de ? "Bin dran." : "On it."],
      [/failed|fehlgeschlagen|sorry/i, () => de ? "Das hat nicht geklappt." : "That didn't work."],
      [/behind plan|hinter plan|on plan|im plan|safety issue|sicherheitsbefund|photos checked|fotos geprüft/i, () => {
        const late = /behind plan|hinter plan/i.test(x), iss = n(/(\d+) (?:safety issue|sicherheitsbefund)/i);
        const a = late ? (de ? "Ein Verzug" : "One delay") : (de ? "Im Plan" : "On track");
        const b = iss ? (de ? `${iss} Befund` : `${iss} issue${iss > 1 ? "s" : ""}`) : "";
        return [a, b].filter(Boolean).join(", ") + ".";
      }],
      [/\?\s*(\(.*\))?\s*$/, () => de ? "Eine Frage." : "Quick question."],
    ];
    for (const [rx, f] of R) if (rx.test(x)) return f();
    return de ? "Erledigt." : "Done.";
  }
  function speak(text, lang) {
    if (!ttsOn || !("speechSynthesis" in window) || !text) { setState("idle"); return Promise.resolve(); }
    text = brief(text);                                      // the assistant speaks in two or three words; details stay on screen
    return new Promise(res => {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text.replace(/[„“”]/g, "")), v = pickVoice(lang || S.lang);
      if (v) u.voice = v; u.lang = v?.lang || (lang === "de" ? "de-DE" : "en-US"); u.rate = 1.03;
      u.onstart = () => { setState("responding"); spoke = performance.now(); };
      u.onboundary = () => { spoke = performance.now(); };          // the orb pulses on real word boundaries
      u.onend = u.onerror = () => { if (S.ai === "responding") setState("idle"); res(); };
      speechSynthesis.speak(u);
      setTimeout(() => { if (!speechSynthesis.speaking && S.ai !== "idle") { setState("idle"); res(); } }, 1500);
    });
  }
  if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = () => {};

  /* ------------------------------------------------------------------ speech to text */
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null, media = null, audioCtx = null, levelRaf = 0, mrec = null, chunks = [];
  const micBtn = q("#bbMic"), live = q("#bbLive");
  async function meter() {
    try {
      media = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const an = audioCtx.createAnalyser(); an.fftSize = 512; audioCtx.createMediaStreamSource(media).connect(an);
      const buf = new Uint8Array(an.fftSize);
      const tick = () => { an.getByteTimeDomainData(buf); let m = 0; for (const v of buf) m = Math.max(m, Math.abs(v - 128)); target = Math.min(1, m / 60); levelRaf = requestAnimationFrame(tick); };
      tick();
      return media;
    } catch (e) { return null; }
  }
  function stopMeter() { cancelAnimationFrame(levelRaf); media?.getTracks().forEach(t => t.stop()); media = null; audioCtx?.close().catch(() => {}); audioCtx = null; }
  async function listen() {
    if (S.ai === "listening") return stopListen(true);
    speechSynthesis?.cancel();
    setState("listening");
    micBtn.classList.add("rec"); micBtn.innerHTML = ICON.stop + '<span class="bb-ring"></span><span class="bb-ring r2"></span>';
    live.hidden = false; live.innerHTML = `<span class="ph">${L("Listening…", "Ich höre zu …")}</span>`;
    const stream = await meter();
    if (SR) {
      rec = new SR(); rec.lang = S.lang === "de" ? "de-DE" : "en-US"; rec.interimResults = true; rec.continuous = false;
      let finalTxt = "";
      rec.onresult = e => { let interim = ""; for (let i = e.resultIndex; i < e.results.length; i++) { const r = e.results[i]; if (r.isFinal) finalTxt += r[0].transcript; else interim += r[0].transcript; }
        live.innerHTML = `${esc(finalTxt)}<i>${esc(interim)}</i>`; };
      rec.onerror = e => { if (e.error === "not-allowed") toast(L("Microphone permission denied. Type your command instead.", "Mikrofon nicht erlaubt. Bitte Befehl tippen."), "bad"); };
      rec.onend = () => { const t = finalTxt.trim(); resetMic(); if (t) command(t, { voice: true }); else if (S.ai === "listening") setState("idle"); };
      try { rec.start(); } catch { resetMic(); setState("idle"); }
      return;
    }
    if (!stream || !window.MediaRecorder) { resetMic(); setState("idle"); toast(L("Voice input is not available in this browser (or permission was denied). Type your command.", "Spracheingabe nicht verfügbar. Bitte tippen."), "bad"); return; }
    // fallback: record, then transcribe with the backend Whisper (POST /api/voice, submit=false)
    chunks = []; mrec = new MediaRecorder(stream); mrec.ondataavailable = e => chunks.push(e.data);
    mrec.onstop = async () => {
      const blob = new Blob(chunks, { type: mrec.mimeType || "audio/webm" }); resetMic();
      setState("processing", L("Transcribing with Whisper", "Transkription mit Whisper"));
      const fd = new FormData(); fd.append("audio", blob, "cmd.webm"); fd.append("submit", "false"); fd.append("language", S.lang);
      try { const r = await api("/api/voice", { method: "POST", body: fd }); const t = (r.transcript?.text || "").trim(); if (t) command(t, { voice: true }); else setState("idle"); }
      catch (e) { setState("idle"); toast(e.message, "bad"); }
    };
    mrec.start(); live.innerHTML = `<span class="ph">${L("Recording… tap again to stop.", "Aufnahme … zum Beenden erneut tippen.")}</span>`;
  }
  function stopListen() { if (rec) { try { rec.stop(); } catch {} } else if (mrec && mrec.state !== "inactive") mrec.stop(); else { resetMic(); setState("idle"); } }
  function resetMic() { stopMeter(); rec = null; micBtn.classList.remove("rec"); micBtn.innerHTML = ICON.mic + '<span class="bb-ring"></span><span class="bb-ring r2"></span>'; setTimeout(() => { if (S.ai !== "listening") live.hidden = true; }, 1200); }
  micBtn.onclick = listen;
  addEventListener("keydown", e => { if (e.code === "Space" && e.ctrlKey && sec.classList.contains("on")) { e.preventDefault(); listen(); } });

  /* ------------------------------------------------------------------ helpers */
  function toast(text, kind = "", ms = 4200) {
    const t = document.createElement("div"); t.className = "bb-toast " + kind; t.textContent = text; toasts.appendChild(t);
    setTimeout(() => t.classList.add("out"), ms); setTimeout(() => t.remove(), ms + 400);
  }
  const zoneName = id => S.twin?.layout.zones.find(z => z.id === id)?.name || id;
  const sevTxt = s => ({ high: L("High", "Hoch"), medium: L("Medium", "Mittel"), low: L("Low", "Niedrig") }[s] || s);
  const pct = c => c == null ? "—" : Math.round(c * 100) + "%";
  const cls = c => (c || "").replace(/_/g, " ");
  let pendingPhotos = [];                                   // photo ids added in the chat, sent with the next drafting message
  let staged = [];                                          // attachments waiting in the composer tray until Send: {id, file, kind, url?}
  function hist(role, text, o = {}) {
    const el = document.createElement("div"); el.className = "bb-msg " + role;
    const docs = (o.docs || []).concat(o.doc ? [{ id: o.doc }] : []);
    const btns = docs.map(d => `<button class="s" data-open="${esc(d.id)}">${L("Open draft", "Entwurf öffnen")}${d.title ? ": " + esc(d.title) : ""}</button>`)
      .concat((o.actions || []).map(a => `<button class="s" data-act='${esc(JSON.stringify(a))}'>${esc(a.label)}</button>`)).join("");
    const atts = (o.attach || []).map(a => a.url ? `<img src="${esc(a.url)}" alt="${esc(a.name)}" title="${esc(a.name)}">` : `<b>${ICON.clip}${esc(a.name)}</b>`).join("");
    el.innerHTML = `${text ? `<div>${esc(text)}</div>` : ""}${atts ? `<div class="bb-atts">${atts}</div>` : ""}${btns ? `<div class="bb-macts">${btns}</div>` : ""}${o.masked?.length ? `<small class="bb-mask">${L("Masked before AI", "Vor KI-Aufruf maskiert")}: ${esc(o.masked.join(", "))}</small>` : ""}<span>${esc((o.at || "").slice(11, 16) || new Date().toTimeString().slice(0, 5))}</span>`;
    qa("[data-open]", el).forEach(b => b.onclick = () => NW.openDocInTab(b.dataset.open));
    if (o.buttons?.length) {                               // client-side buttons (e.g. "Generate site layout")
      let box = q(".bb-macts", el);
      if (!box) { box = document.createElement("div"); box.className = "bb-macts"; el.insertBefore(box, el.querySelector("span:last-child")); }
      o.buttons.forEach(x => { const b = document.createElement("button"); b.className = "s"; b.textContent = x.label; b.onclick = () => x.run(b); box.appendChild(b); });
    }
    qa("[data-act]", el).forEach(b => b.onclick = async () => {
      const a = JSON.parse(b.dataset.act); b.disabled = true;
      try { const d = await api("/api/docs", { json: { type: a.type, text: a.text, source: "message" } }); NW.openDocInTab(d.id); } catch (e) { b.disabled = false; toast(e.message, "bad"); }
    });
    const list = q("#bbHist"); list.appendChild(el); list.scrollTop = list.scrollHeight;
  }
  async function loadHistory() {                            // the same conversation the document pipeline keeps on the server
    try {
      const r = await api("/api/messages"); q("#bbHist").innerHTML = "";
      r.messages.forEach(m => hist(m.role === "user" ? "user" : "ai", m.text, { doc: m.doc, actions: m.actions, masked: m.masked, at: m.at }));
    } catch {}
    if (!q("#bbHist").children.length && greetText) hist("ai", greetText);
  }
  NW.loadMsgs = loadHistory;

  async function loadTwin() { try { S.twin = await api("/api/site/twin"); renderPlan(); } catch (e) { q("#bbPlan").innerHTML = `<div class="mut pad">${esc(e.message)}</div>`; } }

  /* ------------------------------------------------------------------ 2D plan (same layout, zones and photo positions as the 3D twin) */
  function renderPlan() {
    const tw = S.twin; if (!tw) return;
    const Ly = tw.layout;
    // bounds: boundary, else zone corners, else placed photos; with nothing at all show how to create a layout
    const pts = Ly.boundary.length >= 3 ? Ly.boundary : Ly.zones.flatMap(z => z.polygon).concat(tw.photos.filter(p => p.plan_xy).map(p => p.plan_xy));
    if (pts.length < 2) {
      q("#bbPlan").innerHTML = `<div class="mut pad">${L("No site layout yet. Open the 3D twin → Layout and use “Suggest layout from data” (site documents with coordinates or geotagged photos), or enter one by hand.",
        "Noch kein Lageplan. Im 3D-Zwilling → Layout „Suggest layout from data“ nutzen (Dokumente mit Koordinaten oder Fotos mit GPS) oder den Plan von Hand eingeben.")}</div>`;
      return;
    }
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]), pad = 8;
    const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
    const P = p => `${(p[0] - x0).toFixed(1)},${(y1 - p[1]).toFixed(1)}`;
    const hl = Object.fromEntries((S.highlights || []).map(h => [h.id, h.level]));
    const zones = Ly.zones.map(z => {
      const c = z.polygon.reduce((a, p) => [a[0] + p[0] / z.polygon.length, a[1] + p[1] / z.polygon.length], [0, 0]);
      const lvl = hl[z.id];
      return `<g class="bbz ${lvl ? "hl-" + lvl : ""} ${S.focusZone === z.id ? "focus" : ""}" data-zone="${esc(z.id)}"><polygon points="${z.polygon.map(P).join(" ")}" style="--zc:${esc(z.color || "#888")}"/>
        <text x="${P(c).split(",")[0]}" y="${P(c).split(",")[1]}">${esc(z.name)}</text></g>`;
    }).join("");
    const photos = tw.photos.filter(p => p.plan_xy).map(p => `<circle class="bbp" cx="${P(p.plan_xy).split(",")[0]}" cy="${P(p.plan_xy).split(",")[1]}" r="2.2"><title>${esc(p.original_name || p.id)}</title></circle>`).join("");
    const unplaced = tw.photos.filter(p => !p.plan_xy).length;
    q("#bbPlan").innerHTML = `<svg viewBox="0 0 ${(x1 - x0).toFixed(1)} ${(y1 - y0).toFixed(1)}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${L("Site plan", "Lageplan")}">
      ${Ly.boundary.length >= 3 ? `<polygon class="bbb" points="${Ly.boundary.map(P).join(" ")}"/>` : ""}${zones}${photos}</svg>
      ${unplaced ? `<div class="bb-note">${unplaced} ${L("photos have no plan position yet (place them in the 3D twin)", "Fotos noch ohne Planposition (im 3D-Zwilling verorten)")}</div>` : ""}`;
    qa("[data-zone]", q("#bbPlan")).forEach(g => g.onclick = () => command(L(`Show me ${zoneName(g.dataset.zone)}`, `Zeig mir ${zoneName(g.dataset.zone)}`)));
  }
  async function planSnapshot() {
    const svg = q("#bbPlan svg"); if (!svg) return null;
    const clone = svg.cloneNode(true);
    const css = `polygon{stroke:#333;stroke-width:.4}.bbb{fill:#f2f2f2;stroke:#111;stroke-width:.8}.bbz polygon{fill:#ccd;fill-opacity:.35}.hl-red polygon{fill:#ff3b30;fill-opacity:.55}.hl-amber polygon{fill:#ffa500;fill-opacity:.5}text{font:3px sans-serif;fill:#111;text-anchor:middle}.bbp{fill:#ff6a00}`;
    clone.insertAdjacentHTML("afterbegin", `<style>${css}</style>`);
    const vb = svg.viewBox.baseVal, scale = 8, url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(clone));
    const img = new Image(); img.src = url; await img.decode().catch(() => null);
    const c = document.createElement("canvas"); c.width = vb.width * scale; c.height = vb.height * scale;
    const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height);
    try { g.drawImage(img, 0, 0, c.width, c.height); return c.toDataURL("image/png"); } catch { return null; }
  }

  /* ------------------------------------------------------------------ result cards */
  function photoTile(p) {
    const dets = (p.detections || []).map(d => `${cls(d.class)} ${pct(d.confidence)}`).join(", ") || L("no detections", "keine Erkennungen");
    return `<figure class="bb-ph" data-photo="${esc(p.id)}"><img loading="lazy" src="${API}/data/${esc(p.ann_file || p.file)}" alt="">
      <figcaption><b>${esc((p.taken_at || "").replace("T", " ").slice(5, 16))}</b> · ${esc(p.zone ? zoneName(p.zone) : L("no plan position", "ohne Planposition"))}<br>${esc(dets)}<small>${esc(p.detector || "")} · photo:${esc(p.id)}</small></figcaption></figure>`;
  }
  function incidentRow(i) {
    return `<div class="bb-inc sev-${i.severity}" data-inc="${esc(i.id)}"><span class="bb-sev">${sevTxt(i.severity)}</span>
      <div><b>${esc(i["title_" + S.lang] || i.title_en)}</b><small>${esc(i.zone ? zoneName(i.zone) : L("location unknown", "Ort unbekannt"))} · ${esc((i.taken_at || i.created_at || "").replace("T", " ").slice(5, 16))}
      ${i.objects?.length ? " · " + esc(i.objects.map(o => `${cls(o.class)} ${pct(o.confidence)}`).join(", ")) : ""}</small></div><button class="s">${L("Open", "Öffnen")}</button></div>`;
  }
  function card(c) {
    if (c.kind === "progress") {
      const rows = c.rows.filter(r => r.light !== "grey");
      return `<div class="card bb-card"><div class="bb-h"><b>${L("Planned vs actual", "Soll-Ist")}</b><span class="mut">${L("as of", "Stand")} ${esc(c.as_of)}${c.weather ? ` · ${Math.round(c.weather.tmin)}…${Math.round(c.weather.tmax)} °C` : ""}</span></div>
        ${rows.map(r => `<div class="bb-prog ${r.light}" data-zone="${esc(r.zone || "")}"><div class="bb-pl"><span>${esc(r.name)}</span><b>${r.actual} / ${r.planned} ${esc(r.unit)}${r.delay_days >= 0.5 ? ` · <em>${r.delay_days} ${L("d behind", "T Verzug")}</em>` : ""}</b></div>
          <div class="bb-bar"><i style="--w:${Math.min(100, r.pct_actual)}%"></i><u style="left:${Math.min(100, r.pct_planned)}%" title="${L("planned", "Soll")}"></u></div><small>${esc(r.evidence)}${r.zone ? " · " + esc(zoneName(r.zone)) : ""}</small></div>`).join("") || `<p class="mut">${L("No activity running on this day.", "Heute läuft kein Vorgang.")}</p>`}
        ${c.alerts.length ? `<div class="bb-alerts">${c.alerts.map(a => `<div class="bb-al ${a.level}">${esc(a.text)}</div>`).join("")}</div>` : ""}</div>`;
    }
    if (c.kind === "incidents") {
      return `<div class="card bb-card"><div class="bb-h"><b>${L("Safety findings", "Sicherheitsbefunde")}</b><span class="mut">${c.checked_photos != null ? `${c.checked_photos} ${L("photos", "Fotos")} · ${c.checked_detections} ${L("detections checked", "Erkennungen geprüft")}` : ""}</span></div>
        ${c.items.length ? c.items.map(incidentRow).join("") : `<p class="mut">${L("No rule-based finding.", "Kein regelbasierter Befund.")}</p>`}
        <p class="bb-fine">${L("Rules on stored detector output; detections below 50 % ignored. Findings need a person's confirmation.", "Regeln auf gespeicherter Detektorausgabe, Erkennungen unter 50 % ignoriert. Befunde brauchen eine Bestätigung durch eine Person.")}</p></div>`;
    }
    if (c.kind === "photos") return c.items.length ? `<div class="card bb-card"><div class="bb-h"><b>${L("Photo evidence", "Fotobelege")}</b><span class="mut">${c.items.length}</span></div><div class="bb-phs">${c.items.map(photoTile).join("")}</div></div>` : "";
    if (c.kind === "changes") return `<div class="card bb-card"><div class="bb-h"><b>${L("Changes since", "Änderungen seit")} ${esc(c.since)}</b></div>${c.items.map(i => `<div class="bb-ch ${i.kind}"><span>${esc(i.kind)}</span><div>${esc(i.text)}<small>${esc((i.date || "").replace("T", " ").slice(0, 16))} · ${esc(i.evidence)}</small></div></div>`).join("") || `<p class="mut">${L("Nothing new.", "Nichts Neues.")}</p>`}</div>`;
    if (c.kind === "zone") return `<div class="card bb-card"><div class="bb-h"><b>${esc(c.name)}</b><button class="s" data-fly="${esc(c.id)}">${L("Fly there in 3D", "Im 3D anfliegen")}</button></div>
      ${c.activities.map(a => `<div class="bb-prog ${a.light}"><div class="bb-pl"><span>${esc(a.name)}</span><b>${a.actual}/${a.total} ${esc(a.unit)}</b></div><div class="bb-bar"><i style="--w:${a.total ? Math.min(100, a.actual / a.total * 100) : 0}%"></i></div></div>`).join("") || `<p class="mut">${L("No scheduled activity in this zone.", "Kein geplanter Vorgang in dieser Zone.")}</p>`}
      ${c.machinery.length ? `<p>${L("Detected", "Erkannt")}: ${c.machinery.map(m => `${m.count}× ${esc(cls(m.class))} (${L("max", "max.")} ${pct(m.max_confidence)})`).join(", ")}</p>` : ""}</div>`;
    if (c.kind === "layout") {
      const r = c.report, li = a => a.length ? `<ul>${a.join("")}</ul>` : "";
      return `<div class="card bb-card bb-layout"><div class="bb-h"><b>${L("Site layout draft", "Lageplan-Entwurf")}</b><span class="mut">${L("not saved", "nicht gespeichert")}</span></div>
        <p class="bb-fine">${L("Origin", "Ursprung")}: ${esc(r.origin_source)}${r.boundary_source ? ` · ${L("Boundary", "Grenze")}: ${esc(r.boundary_source)}` : ""}</p>
        ${li(r.zones.map(z => `<li><b>${esc(z.name)}</b> <span class="mut">${esc(z.source)}${z.activities.length ? " · " + esc(z.activities.join(", ")) : ""}</span></li>`))}
        ${r.structures.length ? `<p>${L("Markers", "Markierungen")}: ${esc(r.structures.map(s => s.name).join(", "))}</p>` : ""}
        ${r.outliers.length ? `<p class="bb-warn">${L("Left out (too far away)", "Ausgelassen (zu weit entfernt)")}: ${esc(r.outliers.map(o => `${o.label} (${Math.round(o.distance_m / 1000).toLocaleString()} km)`).join(", "))}</p>` : ""}
        ${r.unmatched_activities.length ? `<p class="mut">${L("Schedule ids without a zone", "Vorgänge ohne Zone")}: ${esc(r.unmatched_activities.join(", "))}</p>` : ""}
        ${li(r.warnings.map(w => `<li class="bb-warn">${esc(w)}</li>`))}
        <div class="bb-acts"><button class="p s" data-lay="save">${L("Save layout", "Lageplan speichern")}</button><button class="s" data-lay="edit">${L("Review in 3D editor", "Im 3D-Editor prüfen")}</button></div></div>`;
    }
    if (c.kind === "notice") return `<div class="card bb-card bb-notice">${esc(c.text)}</div>`;
    if (c.kind === "report") return `<div class="card bb-card bb-report"><div class="bb-h"><b>${esc(c.title)}</b><span class="mut">${c.incidents} ${L("findings", "Befunde")} · ${c.photos} ${L("photos", "Fotos")}</span></div>
      <p>${L("Built from live site data: plan, 3D view, photos.", "Aus Live-Daten der Baustelle: Plan, 3D-Ansicht, Fotos.")}</p>
      <div class="bb-acts">${c.pdf_url ? `<a class="p s bb-btn" href="${API}${esc(c.pdf_url)}" target="_blank" rel="noopener">PDF</a>` : ""}
      ${c.docx_url ? `<a class="s bb-btn" href="${API}${esc(c.docx_url)}" download>Word</a>` : ""}
      <a class="s bb-btn" href="${API}${esc(c.url)}" target="_blank" rel="noopener">${L("View", "Ansehen")}</a></div></div>`;
    return "";
  }
  function layoutButton() {
    return { label: L("Generate site layout", "Lageplan erstellen"), run: b => { b.disabled = true; command(L("Generate the site layout from the uploaded documents", "Erstelle den Lageplan aus den hochgeladenen Dokumenten")); } };
  }
  async function saveLayoutDraft(btn) {
    const d = S.layoutDraft; if (!d) return;
    btn.disabled = true;
    try {
      await api("/api/site/layout", { method: "PUT", json: d.layout });
      await loadTwin(); await window.SiteTwin?.reload?.();
      toast(L(`Site layout saved: ${d.report.zones.length} zones.`, `Lageplan gespeichert: ${d.report.zones.length} Zonen.`));
      btn.textContent = L("Saved ✓", "Gespeichert ✓");
    } catch (e) { btn.disabled = false; toast(e.message, "bad"); }
  }
  function bindCards(root) {
    qa("[data-lay]", root).forEach(b => b.onclick = async () => {
      if (b.dataset.lay === "save") return saveLayoutDraft(b);
      NW.TAB("twin");
      for (let i = 0; i < 60 && !window.SiteTwin?.openLayoutDraft; i++) await sleep(100);
      window.SiteTwin?.openLayoutDraft(S.layoutDraft.layout, S.layoutDraft.report);
    });
    qa("[data-inc]", root).forEach(el => el.onclick = () => openIncident(el.dataset.inc));
    qa("[data-fly]", root).forEach(b => b.onclick = () => flyZone(b.dataset.fly));
    qa("[data-photo]", root).forEach(f => f.onclick = () => openPhoto(f.dataset.photo));
    qa(".bb-prog[data-zone]", root).forEach(r => r.dataset.zone && (r.onclick = () => flyZone(r.dataset.zone)));
  }
  function openPhoto(id) {
    const p = S.twin?.photos.find(x => x.id === id);
    if (p?.plan_xy) return flyZone(null, id);
    window.open(API + "/data/" + (p?.ann_file || p?.file || ""), "_blank", "noopener");
  }

  /* ------------------------------------------------------------------ twin actions */
  async function flyZone(zone, photoId) {
    setState("executing", zone ? L(`Flying to ${zoneName(zone)}`, `Fliege zu ${zoneName(zone)}`) : L("Showing photo position", "Zeige Fotoposition"));
    NW.TAB("twin");
    for (let i = 0; i < 60 && !window.SiteTwin; i++) await sleep(100);
    window.SiteTwin?.highlight(S.highlights);
    if (photoId) await window.SiteTwin?.focusPhoto(photoId);
    else if (zone) await window.SiteTwin?.focusZone(zone);
    dockSay(zone ? L(`Showing ${zoneName(zone)} in the 3D twin`, `${zoneName(zone)} im 3D-Zwilling`) : "");
    setTimeout(() => { if (S.ai === "executing") setState("idle"); }, 400);
  }
  function applyHighlights(list) {
    S.highlights = list || []; renderPlan(); window.SiteTwin?.highlight(S.highlights);
  }
  q("#bbTo3d").onclick = () => flyZone(S.focusZone);

  /* ------------------------------------------------------------------ report */
  async function makeReport(scope, incident) {
    setState("executing", L("Compiling report", "Bericht wird erstellt"));
    const snapshot = window.SiteTwin?.ready ? window.SiteTwin.snapshot() : null;
    const plan_snapshot = await planSnapshot();
    try {
      const r = await api("/api/agent/report", { json: { scope, incident, snapshot, plan_snapshot, lang: S.lang } });
      const html = card({ kind: "report", ...r });
      q("#bbCards").insertAdjacentHTML("afterbegin", html);
      hist("ai", `${r.title}: ${r.url}`);
      const w = window.open(API + (r.pdf_url || r.url), "_blank", "noopener");
      if (!w) toast(L("Report ready: use the “Open report” button (pop-up blocked).", "Bericht fertig: Button „Bericht öffnen“ nutzen (Pop-up blockiert)."));
      BB.emit("report", r);
      return r;
    } catch (e) { toast(e.message, "bad"); } finally { if (S.ai === "executing") setState("idle"); }
  }

  /* ------------------------------------------------------------------ incidents: popup, feed, polling */
  function feed() {
    const list = S.incidents;
    q("#bbFeed").innerHTML = list.length ? list.slice(0, 8).map(incidentRow).join("") : `<p class="mut">${L("No open incidents.", "Keine offenen Vorfälle.")}</p>`;
    bindCards(q("#bbFeed"));
    navBtn.dataset.badge = list.filter(i => i.severity === "high").length || "";
  }
  async function openIncident(id, { auto = false } = {}) {
    let inc = S.incidents.find(i => i.id === id);
    if (!inc) { try { inc = (await api("/api/agent/incidents?all=true")).find(i => i.id === id); } catch {} }
    if (!inc) return;
    S.ctx.incident = inc.id;
    const title = inc["title_" + S.lang] || inc.title_en, detail = inc["detail_" + S.lang] || inc.detail_en, rec = inc["recommendation_" + S.lang] || inc.recommendation_en;
    modal.innerHTML = `<div class="bb-mbox sev-${inc.severity}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <div class="bb-mhead"><span class="bb-sev">${sevTxt(inc.severity)}</span><b>${auto ? L("New incident detected", "Neuer Vorfall erkannt") + " · " : ""}${esc(title)}</b><button class="bb-x" aria-label="close">×</button></div>
      <div class="bb-mbody">
        ${inc.file ? `<img src="${API}/data/${esc(inc.ann_file || inc.file)}" alt="">` : `<div class="bb-noimg">${L("No image yet. Add a photo or open the live camera to capture evidence.", "Noch kein Bild. Foto hinzufügen oder Live-Kamera öffnen, um Belege zu erfassen.")}</div>`}
        <dl><dt>${L("What", "Was")}</dt><dd>${esc(detail)}</dd>
          ${inc.objects?.length ? `<dt>${L("Objects (model confidence)", "Objekte (Modellkonfidenz)")}</dt><dd>${esc(inc.objects.map(o => `${cls(o.class)} ${pct(o.confidence)}`).join(", "))}</dd>` : ""}
          <dt>${L("Where", "Wo")}</dt><dd>${esc(inc.zone ? zoneName(inc.zone) : L("Not placed on the plan yet", "Noch nicht im Plan verortet"))}</dd>
          <dt>${L("When", "Wann")}</dt><dd>${esc((inc.taken_at || inc.created_at || "").replace("T", " ").slice(0, 16))}</dd>
          <dt>${L("Source", "Quelle")}</dt><dd>${esc(inc.source === "user" ? L("Reported by the site team", "Vom Bauteam gemeldet") : `${L("Rule", "Regel")} ${inc.rule}${inc.detector ? " · " + inc.detector : ""}`)} · <code>${esc(inc.evidence.join(", "))}</code></dd>
          <dt>${L("Recommendation (AI, not verified)", "Empfehlung (KI, nicht geprüft)")}</dt><dd>${esc(rec)}</dd></dl>
      </div>
      <div class="bb-mfoot">
        ${inc.zone ? `<button class="s" data-m="fly">${L("Show in 3D twin", "Im 3D-Zwilling zeigen")}</button>` : inc.photo ? `<button class="s" data-m="place">${L("Place photo on plan", "Foto im Plan verorten")}</button>` : ""}
        <button class="s" data-m="cam">${L("Open live camera", "Live-Kamera öffnen")}</button>
        <button class="s" data-m="ok">${L("Mark resolved", "Erledigt")}</button><button class="s" data-m="dismiss">${L("Dismiss", "Verwerfen")}</button>
        <button class="p s" data-m="report">${L("Generate incident report", "Vorfallbericht erstellen")}</button></div></div>`;
    modal.hidden = false; requestAnimationFrame(() => modal.classList.add("on"));
    const close = () => { modal.classList.remove("on"); setTimeout(() => (modal.hidden = true), 250); };
    q(".bb-x", modal).onclick = close; modal.onclick = e => { if (e.target === modal) close(); };
    qa("[data-m]", modal).forEach(b => b.onclick = async () => {
      const m = b.dataset.m;
      if (m === "fly") { close(); applyHighlights([...S.highlights.filter(h => h.id !== inc.zone), { id: inc.zone, level: inc.severity === "high" ? "red" : "amber" }]); flyZone(inc.zone); }
      if (m === "place") { close(); flyZone(null, inc.photo); }
      if (m === "cam") { close(); NW.TAB("live"); dockSay(L("Press “Start camera” and allow camera access to stream frames to the detector.", "„Start camera“ drücken und Kamerazugriff erlauben.")); q("#camBtn")?.focus(); q("#camBtn")?.classList.add("bb-pulse"); }
      if (m === "ok" || m === "dismiss") { await api(`/api/agent/incidents/${inc.id}/status`, { json: { status: m === "ok" ? "resolved" : "dismissed" } }); close(); poll(true); }
      if (m === "report") { close(); NW.TAB("command"); makeReport("incident", inc.id); }
    });
    if (auto) speak(L(`Attention. ${title}. ${inc.zone ? "Location: " + zoneName(inc.zone) + "." : ""} ${rec}`, `Achtung. ${title}. ${inc.zone ? "Ort: " + zoneName(inc.zone) + "." : ""} ${rec}`));
  }
  addEventListener("keydown", e => { if (e.key === "Escape" && !modal.hidden) q(".bb-x", modal)?.click(); });

  let since = null, polling = false, primed = false;
  async function poll(force) {
    if (polling || (document.hidden && !force)) return; polling = true;
    try {
      const r = await api("/api/agent/events" + (since && primed ? "?since=" + encodeURIComponent(since) : ""));
      const fresh = primed ? r.incidents : [];
      if (!primed || force || fresh.length) S.incidents = await api("/api/agent/incidents");
      since = r.now; primed = true; feed();
      if (fresh.length) {
        BB.emit("incident:new", fresh);
        fresh.forEach(i => toast(`${sevTxt(i.severity)}: ${i["title_" + S.lang] || i.title_en}`, i.severity === "high" ? "bad" : ""));
        const hi = fresh.find(i => i.severity === "high") || fresh[0];
        if (hi.zone) applyHighlights([...S.highlights, { id: hi.zone, level: hi.severity === "high" ? "red" : "amber" }]);
        loadTwin();
        openIncident(hi.id, { auto: true });
      }
    } catch {} finally { polling = false; }
  }
  setInterval(poll, 5000);

  // live camera: the same proximity rule runs on streamed detections; saving the frame turns it into evidence
  let liveWarned = 0;
  document.addEventListener("bb:live-detections", e => {
    const d = (e.detail?.detections || []).filter(x => x.confidence >= 0.5);
    const ppl = d.filter(x => x.class === "person"), mach = d.filter(x => ["excavator", "dump_truck", "bulldozer", "tractor", "truck"].includes(x.class));
    const close = ppl.some(p => mach.some(m => Math.abs(p.x - m.x) < (p.width + m.width) / 2 * 1.15 && Math.abs(p.y - m.y) < (p.height + m.height) / 2 * 1.15));
    if (close && Date.now() - liveWarned > 15000) {
      liveWarned = Date.now();
      toast(L("Live: person close to machinery. Press “Save frame to inbox” to record it as evidence.", "Live: Person nahe an Maschine. „Save frame to inbox“ speichert den Beleg."), "bad", 7000);
      dockSay(L("Live camera: person close to machinery", "Live-Kamera: Person nahe Maschine"));
      q("#snap")?.classList.add("bb-pulse");
    }
  });
  q("#snap")?.addEventListener("click", () => { q("#snap").classList.remove("bb-pulse"); setTimeout(() => poll(true), 2500); });

  /* ------------------------------------------------------------------ the workflow */
  async function command(text, { voice = false, silent = false, echo = true } = {}) {
    text = (text || "").trim(); if (!text) return;
    speechSynthesis?.cancel();
    closePal();
    q("#bbInp").value = ""; if (!silent && echo) { hist("user", text); window.SFX?.send(); }
    setState("processing");
    let r;
    try { r = await api("/api/agent", { json: { text, ctx: S.ctx, lang: S.lang } }); }
    catch (e) { setState("idle"); const m = L("Sorry, the request failed: ", "Die Anfrage ist fehlgeschlagen: ") + e.message; if (!silent) hist("ai", m); return speak(m); }
    const lang = r.lang || S.lang;

    if (r.handoff === "chat") {                         // drafting / diary: the existing evidence-gated document pipeline
      setState("executing", L("Drafting the document", "Dokument-Entwurf wird erstellt"));
      await showSteps(r.steps);
      try {
        const photo_ids = pendingPhotos; pendingPhotos = [];
        const c = await api("/api/chat", { json: { text, voice, photo_ids, lang: S.lang } });
        const replies = (c.replies || []).filter(m => m.role === "assistant");
        const doc = c.active || replies.find(m => m.doc)?.doc;
        replies.forEach((m, i) => hist("ai", m.text, { doc: m.doc || (i === replies.length - 1 ? doc : null), actions: m.actions, masked: m.masked, at: m.at }));
        const made = replies.find(m => /^✓ (Draft ready|Added to|Entwurf fertig|Ergänzt)/.test(m.text || ""));
        if (made) window.SFX?.done(made.text.replace(/^✓\s*/, "").split(".")[0], q("#bbHist")?.lastElementChild);
        else if (replies.some(m => /^✓/.test(m.text || ""))) window.SFX?.success();
        const say = replies.map(m => m.text).join(" ");
        return speak(say.length > 420 ? say.slice(0, 400) + " …" : say, lang);
      } catch (e) { setState("idle"); hist("ai", e.message); return speak(e.message); }
    }

    setState("analysing");
    S.ctx = r.ctx || S.ctx;
    const stepsDone = showSteps(r.steps);
    const lc = (r.cards || []).find(c => c.kind === "layout");
    if (lc) S.layoutDraft = { layout: lc.layout, report: lc.report };
    q("#bbCards").innerHTML = (r.cards || []).map(card).join("");
    bindCards(q("#bbCards"));
    await stepsDone;

    setState("executing");
    S.last = r; BB.emit("agent:result", r);
    const wants3d = /3d|twin|zwilling|modell|model|fly|navigate/i.test(text);
    let reportAction = null, openInc = null;
    for (const a of r.actions || []) {
      if (a.type === "twin.highlight") applyHighlights(a.zones);
      if (a.type === "twin.focus") { S.focusZone = a.zone; renderPlan(); }
      if (a.type === "report.generate") reportAction = a;
      if (a.type === "incident.open") openInc = a.id;
    }
    poll(true);                                        // the feed reflects new / user-reported incidents right away
    if (!(r.actions || []).some(a => a.type === "twin.highlight") && !r.intents.includes("focus")) applyHighlights(S.highlights);
    const offer = (r.actions || []).some(a => a.type === "offer.report");
    const extras = [];
    if (S.focusZone && (r.actions || []).some(a => a.type === "twin.focus")) extras.push(`<button class="s" data-x="fly">${L("Show in 3D twin", "Im 3D-Zwilling zeigen")}</button>`);
    if (offer) extras.push(`<button class="s" data-x="report">${L("Generate PDF report", "PDF-Bericht erstellen")}</button>`);
    if ((r.actions || []).some(a => a.type === "camera.offer")) extras.push(`<button class="s" data-x="cam">${L("Open live camera", "Live-Kamera öffnen")}</button>`);
    if (extras.length) {
      q("#bbCards").insertAdjacentHTML("afterbegin", `<div class="bb-acts">${extras.join("")}</div>`);
      qa("[data-x]", q("#bbCards")).forEach(b => b.onclick = () => {
        if (b.dataset.x === "fly") flyZone(S.focusZone);
        if (b.dataset.x === "report") makeReport(S.ctx.incident && /incident|vorfall/i.test(text) ? "incident" : "site", S.ctx.incident);
        if (b.dataset.x === "cam") { NW.TAB("live"); q("#camBtn")?.classList.add("bb-pulse"); }
      });
    }
    if (silent) { setState("idle"); return; }
    hist("ai", r.speech || "");
    if (wants3d && S.focusZone) flyZone(S.focusZone);
    if (reportAction) await makeReport(reportAction.scope, reportAction.incident);
    const spoken = speak(r.speech, lang);
    if (openInc && !reportAction) setTimeout(() => openIncident(openInc), wants3d ? 1800 : 600);
    return spoken;
  }
  async function showSteps(steps) {                      // the real backend steps, shown in the orb label as they complete
    for (const st of steps || []) {
      q("#bbStateSub").textContent = st.label;
      if (!RM) await sleep(110);
    }
  }

  /* ------------------------------------------------------------------ command palette */
  const pal = q("#bbPal"), palBtn = q("#bbPalBtn");
  function openPal(on) { pal.hidden = !on; palBtn.setAttribute("aria-expanded", on); palBtn.classList.toggle("on", on); if (on) q(".bb-chip", pal)?.focus(); }
  function closePal() { if (!pal.hidden) openPal(false); }
  palBtn.onclick = e => { e.stopPropagation(); openPal(pal.hidden); };
  pal.onclick = e => { const b = e.target.closest("[data-cmd]"); if (b) command(b.dataset.cmd); };
  document.addEventListener("click", e => { if (!pal.hidden && !e.target.closest("#bbPal,#bbPalBtn")) closePal(); });
  addEventListener("keydown", e => { if (e.key === "Escape" && !pal.hidden) { closePal(); palBtn.focus(); } });

  /* ------------------------------------------------------------------ uploads: photos (evidence for drafts) and files (e-mail, calendar, documents) */
  const photoIn = q("#bbPhotoIn"), fileIn = q("#bbFileIn");
  q("#bbPhotoBtn").onclick = () => photoIn.click();
  q("#bbFileBtn").onclick = () => fileIn.click();
  // picked files wait in the composer tray (removable) and go out together with the typed message on Send
  const MAX_STAGED = 10, tray = q("#bbTray");
  function stage(files, kind) {
    for (const f of files) {
      if (staged.length >= MAX_STAGED) { toast(L(`At most ${MAX_STAGED} attachments per message.`, `Höchstens ${MAX_STAGED} Anhänge pro Nachricht.`), "bad"); break; }
      const k = isAudio(f) ? "audio" : kind || (f.type.startsWith("image/") ? "photo" : "file");
      staged.push({ id: Math.random().toString(36).slice(2), file: f, kind: k, url: k === "photo" ? URL.createObjectURL(f) : null });
    }
    renderTray(); q("#bbInp").focus();
  }
  function isAudio(f) { return (f.type || "").startsWith("audio/") || /\.(m4a|mp3|wav|ogg|oga|opus|webm|flac|aac|amr)$/i.test(f.name || ""); }
  function renderTray() {
    tray.hidden = !staged.length;
    tray.innerHTML = staged.map(a => `<div class="bb-att${a.url ? " img" : ""}" title="${esc(a.file.name)}">
      ${a.url ? `<img src="${esc(a.url)}" alt="${esc(a.file.name)}">` : `${a.kind === "audio" ? ICON.mic : ICON.clip}<b>${esc(a.file.name)}</b>`}
      <button data-rm="${a.id}" aria-label="${L("Remove", "Entfernen")}" title="${L("Remove", "Entfernen")}">×</button></div>`).join("");
    qa("[data-rm]", tray).forEach(b => b.onclick = () => {
      const a = staged.find(x => x.id === b.dataset.rm); if (a?.url) URL.revokeObjectURL(a.url);
      staged = staged.filter(x => x !== a); renderTray(); q("#bbInp").focus();
    });
  }
  // audio recordings: speech to text (/api/voice), then the transcript runs through the assistant like a spoken command
  async function transcribeAudio(a) {
    const fd = new FormData();
    fd.append("audio", a.file, a.file.name || "recording");
    fd.append("submit", "false");
    fd.append("language", S.lang);
    const r = await api("/api/voice", { method: "POST", body: fd });
    const text = (r.transcript?.text || "").trim();
    if (!text) throw new Error(L("No speech found in ", "Keine Sprache gefunden in ") + a.file.name);
    return { text, secs: r.transcript?.duration_s, model: r.transcript?.model };
  }
  photoIn.onchange = () => { stage([...photoIn.files], "photo"); photoIn.value = ""; };
  fileIn.onchange = () => { stage([...fileIn.files], "file"); fileIn.value = ""; };
  q("#bbInp").addEventListener("paste", e => {
    const imgs = [...(e.clipboardData?.files || [])].filter(f => f.type.startsWith("image/"));
    if (imgs.length) { e.preventDefault(); stage(imgs, "photo"); }
  });
  const compose = q(".bb-compose");
  compose.addEventListener("dragover", e => { if (e.dataTransfer?.types.includes("Files")) { e.preventDefault(); compose.classList.add("drop"); } });
  compose.addEventListener("dragleave", e => { if (!compose.contains(e.relatedTarget)) compose.classList.remove("drop"); });
  compose.addEventListener("drop", e => { e.preventDefault(); compose.classList.remove("drop"); if (e.dataTransfer?.files.length) stage([...e.dataTransfer.files]); });

  async function uploadPhotos(files) {
    const fd = new FormData(); files.forEach(f => fd.append("files", f));
    const r = await api("/api/photos", { method: "POST", body: fd });
    pendingPhotos.push(...r.map(p => p.id));
    window.loadPhotos?.(); loadTwin();
    const what = r.map(p => p.category + (p.detections?.length ? " (" + p.detections.map(d => d.class).join(", ") + ")" : "")).join("; ");
    const gps = r.filter(p => p.location_source === "exif").length;
    if (gps && !(S.twin?.layout?.zones || []).length) {
      const t = L(`Added ${r.length} photo(s): ${what}. ${gps} of them carry GPS, and there is no site layout yet – I can draft one from the photo positions and any site documents.`,
        `${r.length} Foto(s) hinzugefügt: ${what}. ${gps} davon haben GPS, und es gibt noch keinen Lageplan – ich kann aus den Fotopositionen und Baustellendokumenten einen Entwurf erstellen.`);
      return { text: t, buttons: [layoutButton()] };
    }
    return L(`Added ${r.length} photo(s): ${what}. They will be attached to matching drafts and today's daily report.`, `${r.length} Foto(s) hinzugefügt: ${what}. Sie werden passenden Entwürfen und dem Tagesbericht beigefügt.`);
  }
  async function importFiles(files) {
    const fd = new FormData(); files.forEach(f => fd.append("files", f));
    const r = await api("/api/inbox/import", { method: "POST", body: fd });
    const items = [...(r.emails || []), ...(r.documents || [])], docs = new Map();
    items.forEach(m => (m.drafts || []).forEach(d => docs.set(d.id, { id: d.id, title: d.title })));
    const lines = items.map(m => `• ${m.subject || m.file}${m.duplicate ? " (" + L("already imported", "bereits importiert") + ")" : ""}${(m.open_items || []).length ? " · " + m.open_items.length + " " + L("open items", "offene Punkte") : ""}`)
      .concat((r.reminders || []).map(x => "• " + x.message), (r.skipped || []).map(x => `• ${x.file}: ${x.reason}`));
    const site = r.site || {}, buttons = [];
    const geoFiles = [...(site.new_files || []), ...(site.known_files || [])];
    if (geoFiles.length) {
      const n = site.files_with_coordinates.filter(f => geoFiles.includes(f.file)).reduce((a, f) => a + f.points, 0);
      lines.push(L(`• Site coordinates: ${n} found in ${geoFiles.length} file(s) (${geoFiles.join(", ")}).`, `• Baustellenkoordinaten: ${n} in ${geoFiles.length} Datei(en) gefunden (${geoFiles.join(", ")}).`));
      buttons.push(layoutButton());
    }
    return { text: lines.join("\n") || L("Nothing imported.", "Nichts importiert."), docs: [...docs.values()], buttons };
  }

  let sending = false;
  async function send() {
    const inp = q("#bbInp"), text = inp.value.trim();
    if (sending || (!text && !staged.length)) return;
    if (!staged.length) return command(text);
    sending = true;
    const batch = staged; staged = []; renderTray(); inp.value = "";
    hist("user", text, { attach: batch.map(a => ({ name: a.file.name, url: a.url })) });
    setState("processing", L("Uploading attachments", "Anhänge werden hochgeladen"));
    const photos = batch.filter(a => a.kind === "photo"), files = batch.filter(a => a.kind === "file"), audios = batch.filter(a => a.kind === "audio");
    const [p, f] = await Promise.allSettled([photos.length ? uploadPhotos(photos.map(a => a.file)) : null, files.length ? importFiles(files.map(a => a.file)) : null]);
    poll(true);
    const failed = [...(p.status === "rejected" ? photos : []), ...(f.status === "rejected" ? files : [])];
    if (failed.length) {                                    // put what did not go out back into the tray, keep the typed text
      const err = (p.reason || f.reason)?.message || "";
      toast(L("Upload failed: ", "Hochladen fehlgeschlagen: ") + err, "bad");
      staged = failed.concat(staged); renderTray();
      if (text) inp.value = text;
    }
    if (f.status === "fulfilled" && f.value) hist("ai", f.value.text, { docs: f.value.docs, buttons: f.value.buttons });
    sending = false;
    if (failed.length) return setState("idle");
    for (const a of audios) {                                // one recording after the other, each as its own command
      setState("processing", L(`Transcribing ${a.file.name}`, `Transkribiere ${a.file.name}`));
      try {
        const t = await transcribeAudio(a);
        hist("ai", `🎙 ${a.file.name}${t.secs ? ` (${Math.round(t.secs)} s)` : ""}: “${t.text}”`);
        await command(t.text, { voice: true, echo: false });
      } catch (e) { toast(e.message, "bad"); hist("ai", "⚠ " + e.message); }
    }
    if (audios.length && !text) return setState("idle");
    if (text) return command(text, { echo: false });
    if (p.value) typeof p.value === "string" ? hist("ai", p.value) : hist("ai", p.value.text, { buttons: p.value.buttons });
    setState("idle");
  }
  q("#bbSend").onclick = send;
  q("#bbInp").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); send(); } };
  BB.command = command; BB.report = makeReport; BB.openIncident = openIncident; BB.flyZone = flyZone;

  /* ------------------------------------------------------------------ boot */
  let greeted = false, greetText = "";
  async function boot() {
    setState("idle");
    loadTwin(); poll(true);
    try { const g = await api("/api/agent/greeting?lang=" + S.lang); greetText = g.text; } catch {}
    await loadHistory();
    // ?ask=… runs a command on load (demo links); otherwise a silent briefing fills the work area with real data
    const ask = new URLSearchParams(location.search).get("ask");
    if (ask) { greeted = true; command(ask); }
    else command(L("Check today's progress and safety", "Fortschritt und Sicherheit heute prüfen"), { silent: true }).catch(() => {});
    // browsers allow speech only after a user gesture: greet on the first interaction
    const once = () => { if (greeted) return; greeted = true; if (greetText && sec.classList.contains("on") && S.ai === "idle") speak(greetText); };
    addEventListener("pointerdown", e => { if (!e.target.closest("#bbMic,.bb-compose")) once(); else greeted = true; }, { once: true, capture: true });
  }
  showDock(); orbKick();
  boot();
})();
