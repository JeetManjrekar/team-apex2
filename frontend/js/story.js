/* BauBuddy · "A day in the life of a site manager" — story mode.
   One button loads a clean demo state (POST /api/demo/full) and replays a working day from 07:00 to 17:00.
   Every scene drives the real app: the AI Manager (BB.command), speech to text (/api/voice), the document
   pipeline, plan alerts, the daily report and the PDF export. Nothing in a scene is pre-rendered.
   Keys while running: Space = pause/resume, → = next scene, Esc = stop.
   Manual-time figures are team estimates (backend/data/demo/README.md) and are labelled as such on screen. */
(() => {
  "use strict";
  const NW = window.NW; if (!NW) return;
  const API = window.API_BASE || "";
  const q = (s, r = document) => r.querySelector(s), qa = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = NW.esc, api = NW.api;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const de = (() => { try { return localStorage.getItem("nw-lang") === "de"; } catch { return false; } })();
  const L = (en, d) => (de ? d : en);

  const ST = { on: false, paused: false, skip: false, idx: 0, saved: 0, aiSec: 0, log: [], docs: {} };

  /* ------------------------------------------------------------------ chrome */
  const hud = document.createElement("div");
  hud.className = "st-hud"; hud.setAttribute("role", "status");
  hud.innerHTML = `<div class="st-clock" id="stClock">07:00</div>
    <div class="st-meta"><b id="stTitle"></b><div class="st-dots" id="stDots"></div></div>
    <div class="st-saved"><span>${L("time saved (est.)", "Zeit gespart (geschätzt)")}</span><b id="stSaved">0 min</b></div>
    <button class="st-btn" id="stPause" title="${L("Pause (Space)", "Pause (Leertaste)")}">❚❚</button>
    <button class="st-btn" id="stNext" title="${L("Next scene (→)", "Nächste Szene (→)")}">▶▶</button>
    <button class="st-btn" id="stExit" title="${L("Stop (Esc)", "Beenden (Esc)")}">✕</button>`;
  const chap = document.createElement("div"); chap.className = "st-chapter";
  chap.innerHTML = `<div class="st-chap"><div class="t" id="stCt"></div><h2 id="stCh"></h2><p id="stCp"></p></div>`;
  const take = document.createElement("div"); take.className = "st-take"; take.setAttribute("aria-live", "polite");
  take.innerHTML = `<div class="k">✓</div><div><b id="stTk"></b><span id="stTx"></span></div>`;
  const voice = document.createElement("div"); voice.className = "st-voice";
  voice.innerHTML = `<div class="hd"><i></i><span id="stVh">${L("Voice note · site manager", "Sprachnotiz · Bauleiter")}</span></div>
    <div class="bars" id="stBars">${"<span></span>".repeat(36)}</div><div class="tr" id="stVt"><em>${L("Listening…", "Hört zu…")}</em></div>`;
  const pdf = document.createElement("div"); pdf.className = "st-pdf"; pdf.innerHTML = `<iframe title="PDF"></iframe>`;
  const fin = document.createElement("div"); fin.className = "st-final";
  const phoneBox = document.createElement("div"); phoneBox.className = "st-phonebox";
  const costBox = document.createElement("div"); costBox.className = "st-costs";
  document.body.append(costBox);
  const pip = document.createElement("div"); pip.className = "st-pip";
  pip.innerHTML = `<div class="st-pip-host"></div><div class="st-pip-tag"><i></i>${L("LIVE 3D", "LIVE 3D")}</div><div class="st-pip-cap"></div>`;
  document.body.append(hud, chap, take, voice, pdf, fin, phoneBox, pip);

  // the live 3D twin stays on screen for the whole preview and follows each scene
  async function pipOn() {
    for (let i = 0; i < 60 && !window.SiteTwin?.pin; i++) await sleep(100);
    if (!window.SiteTwin?.pin) return;
    pip.classList.add("on");
    try { await window.SiteTwin.pin(q(".st-pip-host", pip)); } catch (e) { console.warn(e); }
  }
  function pipOff() { try { window.SiteTwin?.unpin?.(); } catch {} pip.classList.remove("on", "big"); }
  async function look(zoneName, caption, big = false) {
    if (!pip.classList.contains("on")) return;
    q(".st-pip-cap", pip).textContent = caption || "";
    if (pip.classList.contains("big") !== big) await resizePip(big);
    const T = window.SiteTwin, id = zoneName ? (T?.zoneIdByName?.(zoneName) || zoneName) : null;
    try { if (id && T?.focusZone) await T.focusZone(id); else await T?.overview?.(); } catch {}
  }
  // fade out, jump to the new size, fade in: resizing a WebGL canvas frame by frame flickers black
  async function resizePip(big) {
    pip.classList.add("swap");
    await sleep(RM ? 0 : 230);
    pip.classList.toggle("big", big);
    await sleep(80);
    pip.classList.remove("swap");
  }
  const small = () => { if (pip.classList.contains("big")) resizePip(false); };

  // animated "scan -> talk -> live" phone, next to the real QR code (reused by the ⋯ menu's phone window)
  function phoneCard(info) {
    const steps = [["📷", L("Scan the code", "Code scannen")], ["🎙️", L("Hold & talk", "Halten & sprechen")], ["🏗️", L("Live in the 3D twin", "Live im 3D-Zwilling")]];
    return `<div class="st-pbox">
      <div class="st-phone" aria-hidden="true"><div class="scr">
        <div class="s1"><div class="qrf"><i></i><i></i><i></i><i></i><b></b></div><span>${L("Scanning…", "Scannt…")}</span></div>
        <div class="s2"><div class="bub">“${L("Truck tipped over at Axis 2", "Lkw an Achse 2 umgekippt")}”</div><div class="mic"><span></span></div><span>${L("Hold to talk", "Halten zum Sprechen")}</span></div>
        <div class="s3"><div class="ok">✓</div><b>${L("Sent to the site manager", "An die Bauleitung gesendet")}</b><span>📱 ${L("visible in 3D", "sichtbar in 3D")}</span></div>
      </div><div class="notch"></div></div>
      <div class="st-pside">
        <h2>${L("Try it on your phone", "Probier es auf dem Handy")}</h2>
        <ol>${steps.map(([e, t], i) => `<li style="animation-delay:${i * 2.4}s"><span>${e}</span>${t}</li>`).join("")}</ol>
        ${info && info.qr ? `<img class="qr" src="${info.qr}" alt="QR code"><small>${esc(info.url)}</small>`
          : `<div class="noqr">${L("Start the phone link on the laptop:", "Handy-Link am Laptop starten:")}<code>./scripts/phone_tunnel.sh</code></div>`}
      </div></div>`;
  }

  const btn = document.createElement("button");
  btn.className = "s"; btn.id = "storyBtn"; btn.textContent = L("▶ Real Time Preview", "▶ Echtzeit-Vorschau");
  btn.title = L("Live demo: a site manager's day from 07:00 to 17:00, driven through the real app", "Live-Demo: ein Arbeitstag von 07:00 bis 17:00, durch die echte App");
  const anchor = q("#autoBtn");
  anchor ? anchor.before(btn) : q("header")?.append(btn);

  /* ------------------------------------------------------------------ helpers */
  const eurK = x => (x == null ? "––" : x >= 10000 ? `${Math.round(x / 1000)} k€` : `${new Intl.NumberFormat(de ? "de-DE" : "en-GB").format(Math.round(x))} €`);
  const fmtMin = m => (m >= 60 ? `${Math.floor(m / 60)} h ${String(Math.round(m % 60)).padStart(2, "0")} min` : `${Math.round(m)} min`);
  function setClock(t) { q("#stClock").textContent = t; }
  function addSaved(min) {
    const from = ST.saved, to = ST.saved + min, t0 = performance.now();
    ST.saved = to;
    const step = now => { const k = Math.min(1, (now - t0) / 900); q("#stSaved").textContent = fmtMin(from + (to - from) * k); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  async function wait(ms) {                    // pausable, skippable
    const end = performance.now() + ms;
    while (ST.on && !ST.skip && (ST.paused || performance.now() < end)) await sleep(80);
  }
  async function chapter(time, title, text) {
    setClock(time);
    q("#stCt").textContent = time; q("#stCh").textContent = title; q("#stCp").textContent = text;
    chap.classList.add("on");
    await wait(RM ? 900 : 1600);
    chap.classList.remove("on");
    await sleep(250);
  }
  function takeaway(title, text) {
    q("#stTk").textContent = title; q("#stTx").textContent = text;
    take.classList.add("on");
  }
  function hideTake() { take.classList.remove("on"); }
  async function typeInto(text) {
    const inp = q("#bbInp"); if (!inp) return;
    inp.focus({ preventScroll: true }); inp.value = "";
    for (const ch of text) { if (!ST.on) return; inp.value += ch; await sleep(RM ? 0 : 10); }
    await sleep(200);
  }
  async function cmd(text, opts) {             // the real AI Manager pipeline; timed for the AI-seconds figure
    const t0 = performance.now();
    await typeInto(text);
    const r = window.BB.command(text, opts);
    // speech output is part of the experience but should not stall the story forever
    await Promise.race([r, sleep(12000)]);
    ST.aiSec += (performance.now() - t0) / 1000;
  }
  async function latestDoc(type) {
    const all = await api("/api/docs");
    return all.filter(d => d.type === type).sort((a, b) => (b.created_at || b.id).localeCompare(a.created_at || a.id))[0]
      || all.filter(d => d.type === type).slice(-1)[0];
  }
  async function showDoc(id, peekField) {
    NW.openDocInTab(id);
    await sleep(700);
    if (peekField) {
      const f = q(`#docView .f[data-k="${peekField}"]`);
      if (f) {
        f.scrollIntoView({ behavior: RM ? "auto" : "smooth", block: "center", inline: "nearest" });
        await sleep(400);
        f.querySelector("[data-q]")?.click();
        f.style.transition = "box-shadow .4s"; f.style.boxShadow = "0 0 0 2px var(--acc)";
        setTimeout(() => (f.style.boxShadow = ""), 5000);
      }
    }
  }
  function log(time, text, minutes) { ST.log.push({ time, text, minutes }); }

  /* ------------------------------------------------------------------ voice note */
  async function voiceNote(url, lang) {
    voice.classList.add("on");
    q("#stVt").innerHTML = `<em>${L("Listening…", "Hört zu…")}</em>`;
    const blob = await (await fetch(url)).blob();
    const audio = new Audio(URL.createObjectURL(blob));
    const bars = qa("#stBars span");
    let ctx, an, raf;
    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      const src = ctx.createMediaElementSource(audio); an = ctx.createAnalyser(); an.fftSize = 128;
      src.connect(an); an.connect(ctx.destination);
      const data = new Uint8Array(an.frequencyBinCount);
      const draw = () => { an.getByteFrequencyData(data); bars.forEach((b, i) => (b.style.height = Math.max(6, data[(i * 2) % data.length] / 2.55) + "%")); raf = requestAnimationFrame(draw); };
      draw();
    } catch { /* no analyser: bars stay flat */ }
    const t0 = performance.now();
    const fd = new FormData(); fd.append("audio", blob, "voice.m4a"); fd.append("submit", "false"); if (lang) fd.append("language", lang);
    const trP = fetch(API + "/api/voice", { method: "POST", body: fd }).then(r => r.json());
    const played = new Promise(res => { audio.onended = res; audio.onerror = res; });
    try { await audio.play(); } catch { /* autoplay refused: transcript still arrives */ }
    const [tr] = await Promise.all([trP, Promise.race([played, sleep(15000)])]);
    cancelAnimationFrame(raf); ctx?.close().catch(() => {});
    const text = tr?.transcript?.text || "";
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    q("#stVt").innerHTML = `“${esc(text)}”<br><em>${esc(L(`Transcribed by ${tr?.transcript?.model || "Whisper"} · ${tr?.transcript?.provider || ""}`, `Transkribiert von ${tr?.transcript?.model || "Whisper"}`))}</em>`;
    await wait(1500);
    voice.classList.remove("on");
    return { text, secs };
  }

  /* ------------------------------------------------------------------ scenes */
  const SCENES = [
    {
      time: "07:00", title: L("Morning briefing", "Morgenbriefing"),
      intro: L("One question. The whole site.", "Eine Frage. Die ganze Baustelle."),
      async run() {
        NW.TAB("command");
        await cmd(L("Good morning. Check today's progress and safety.", "Guten Morgen. Prüfe Fortschritt und Sicherheit für heute."));
        const tw = window.BB.state.twin;
        const nPh = tw?.photos?.length || 0, nDet = (tw?.photos || []).reduce((s, p) => s + (p.detections || []).length, 0);
        takeaway(L("Morning check done", "Morgencheck fertig"), L(`${nPh} photos · ${nDet} detections · weather`, `${nPh} Fotos · ${nDet} Erkennungen · Wetter`));
        addSaved(20); log("07:00", L("Morning status: schedule, safety, weather", "Morgenstatus: Termine, Sicherheit, Wetter"), 20);
      },
    },
    {
      time: "07:25", title: L("Safety finding on the photos", "Sicherheitsbefund auf den Fotos"),
      intro: L("An excavator where it shouldn't be.", "Ein Bagger am falschen Ort."),
      async run() {
        const inc = (await api("/api/agent/incidents"))[0];
        if (!inc) { takeaway(L("No open incidents", "Keine offenen Vorfälle"), ""); return; }
        await window.BB.openIncident(inc.id);
        window.SFX?.alert();
        await wait(2600);
        q(".bb-x")?.click();                                    // close the popup, the big 3D window takes over
        await look(inc.zone, L("⚠ Safety finding · ", "⚠ Sicherheitsbefund · ") + ((de ? inc.title_de : inc.title_en) || inc.title_en || ""), true);
        await wait(8000);
        takeaway(L("Spotted on a photo", "Auf einem Foto erkannt"), L("You confirm. The AI never decides alone.", "Du bestätigst. Die KI entscheidet nie allein."));
        setTimeout(small, 2500);
        addSaved(15); log("07:25", L("Photo safety review, finding located in 3D twin", "Foto-Sicherheitsprüfung, Befund im 3D-Zwilling"), 15);
      },
    },
    {
      time: "10:05", title: L("The excavator breaks down", "Der Bagger fällt aus"),
      intro: L("Hydraulic failure. One sentence.", "Hydraulikschaden. Ein Satz."),
      async run() {
        NW.TAB("command");
        look("w1", L("Abutment 1 · excavator down", "Widerlager 1 · Bagger steht"));
        await cmd(L("Excavator idle since 10 am due to hydraulic failure, excavation at Abutment 1 stopped, crew of 4 waiting",
                    "Bagger steht seit 10 Uhr wegen Hydraulikschaden, Aushub am Widerlager 1 gestoppt, 4 Mann warten"));
        await wait(400);
        await cmd(L("about 2 days", "etwa 2 Tage"));
        const d = await latestDoc("behinderungsanzeige"); ST.docs.beh = d?.id;
        const n = d ? Object.values(d.fields).filter(f => f.value).length : 0;
        takeaway(L("Delay notice ready", "Behinderungsanzeige fertig"), L(`${n} fields, each with a source`, `${n} Felder, jedes mit Quelle`));
        addSaved(30); log("10:05", L("Delay notice", "Behinderungsanzeige"), 30);
        if (d) { await wait(800); await showDoc(d.id, "cause"); }
      },
    },
    {
      time: "11:20", title: L("Rock at pile 7 — by voice", "Fels bei Pfahl 7 — per Sprache"),
      intro: L("Rock at 4 m instead of 9 m. He just speaks.", "Fels bei 4 m statt 9 m. Er spricht einfach."),
      async run() {
        NW.TAB("command");
        look("w1", L("Pile 7 · drilling", "Pfahl 7 · Bohrung"));
        const v = await voiceNote(de ? "demo/rock_pile7_de.m4a" : "demo/rock_pile7.m4a", de ? "de" : "en");
        if (!v.text) { takeaway(L("Speech recognition unavailable", "Spracherkennung nicht verfügbar"), ""); return; }
        const t0 = performance.now();
        await Promise.race([window.BB.command(v.text, { voice: true }), sleep(15000)]);
        await sleep(300);
        ST.aiSec += (performance.now() - t0) / 1000 + Number(v.secs);
        const d = await latestDoc("nachtragsmeldung"); ST.docs.nach = d?.id;
        const n = d ? Object.values(d.fields).filter(f => f.value).length : 0;
        takeaway(L("Change order ready", "Nachtrag fertig"), L(`${n} fields · soil report · drilling list`, `${n} Felder · Gutachten · Bohrliste`));
        if (d) { await wait(500); await showDoc(d.id, "expected_ground"); }
        addSaved(90); log("11:20", L("Change order notice from a voice note", "Nachtragsmeldung aus Sprachnotiz"), 90);
      },
    },
    {
      time: "14:30", title: L("A deviation, caught early", "Eine Abweichung, früh erkannt"),
      intro: L("Concreting on Monday. Forecast −3 °C.", "Betonieren am Montag. Prognose −3 °C."),
      async run() {
        NW.TAB("plan");
        await sleep(700);
        const al = q('#alerts [data-k="frost"], #alerts button');
        if (al) { al.scrollIntoView({ behavior: RM ? "auto" : "smooth", block: "center", inline: "nearest" }); al.style.boxShadow = "0 0 0 2px var(--acc)"; }
        await wait(1000);
        const t0 = performance.now();
        const plan = await api("/api/plan");
        const a = plan.alerts.find(x => x.suggest) || null;
        if (!a) { takeaway(L("No critical deviation today", "Heute keine kritische Abweichung"), ""); return; }
        const d = await api("/api/plan/propose", { json: { kind: a.kind, activity: a.activity } });
        ST.aiSec += (performance.now() - t0) / 1000;
        ST.docs.alert = d.id;
        await showDoc(d.id, "concern_description");
        window.SFX?.done(L("Letter drafted", "Schreiben entworfen"));
        takeaway(L("Letter drafted, not sent", "Schreiben entworfen, nicht versendet"), L(`${d.title} · waits for you`, `${d.title} · wartet auf dich`));
        addSaved(30); log("14:30", L(`${d.title} from a schedule/weather alert`, `${d.title} aus Termin-/Wetterwarnung`), 30);
      },
    },
    {
      time: "15:30", title: L("What it costs", "Was es kostet"),
      intro: L("Money lost in silence, made visible.", "Stilles Geld, sichtbar gemacht."),
      async run() {
        const c = await window.Costs?.refresh(costBox);
        if (!c) { takeaway(L("Cost model unavailable", "Kostenmodell nicht verfügbar"), ""); return; }
        costBox.classList.add("on");
        await wait(2500);
        const rows = qa(".cm-row", costBox);
        for (const r of rows) { r.classList.add("open"); r.scrollIntoView({ block: "nearest", behavior: RM ? "auto" : "smooth" }); await wait(2100); r.classList.remove("open"); }
        const btnIdle = q('.cm-act[data-act^="idle:"]', costBox);
        if (btnIdle) { btnIdle.style.boxShadow = "0 0 0 3px var(--acc)"; await wait(900); btnIdle.click(); await wait(2600); }
        const x = window.Costs.last;
        takeaway(L("Measured hours × internal rates, ranked", "Gemessene Stunden × interne Sätze, sortiert"),
          L(`Change order ~${eurK(x?.nachtrag_documented?.expected_eur || x?.nachtrag_open?.expected_eur)} · delay risk ~${eurK(x?.delay_open?.expected_eur)} · never in outgoing letters`,
            `Nachtrag ~${eurK(x?.nachtrag_documented?.expected_eur || x?.nachtrag_open?.expected_eur)} · Terminrisiko ~${eurK(x?.delay_open?.expected_eur)} · nie in ausgehenden Schreiben`));
        await wait(1500);
        costBox.classList.remove("on");
      },
    },
    {
      time: "16:30", title: L("The daily report writes itself", "Der Bautagesbericht schreibt sich selbst"),
      intro: L("Usually 45 minutes. Now one click.", "Sonst 45 Minuten. Jetzt ein Klick."),
      async run() {
        const t0 = performance.now();
        look(null, L("Whole site · today", "Ganze Baustelle · heute"));
        const d = await api("/api/reports/daily", { json: {} });
        ST.aiSec += (performance.now() - t0) / 1000;
        ST.docs.daily = d.id;
        await showDoc(d.id, "work_done");
        window.SFX?.done(L("Daily report ready", "Tagesbericht fertig"));
        takeaway(L("Daily report ready", "Tagesbericht fertig"), L("Weather · progress · photos · notices", "Wetter · Fortschritt · Fotos · Meldungen"));
        addSaved(45); log("16:30", L("Daily site report", "Bautagesbericht"), 45);
      },
    },
    {
      time: "16:50", title: L("Review, sign off, export", "Prüfen, freigeben, exportieren"),
      intro: L("He checks. He decides.", "Er prüft. Er entscheidet."),
      async run() {
        const id = ST.docs.beh || ST.docs.daily || ST.docs.nach;    // the complete draft; the change order still has open questions
        if (!id) return;
        await showDoc(id);
        const b = q('#docView [data-st="checked"]');
        if (b) { b.style.boxShadow = "0 0 0 2px var(--acc)"; await sleep(600); b.click(); await sleep(700); }
        const r = await fetch(`${API}/api/docs/${id}/pdf`);
        const ok = r.ok && /pdf/i.test(r.headers.get("content-type") || "");
        q("iframe", pdf).src = ok ? URL.createObjectURL(await r.blob()) : `${API}/api/docs/${id}/print`;
        pdf.classList.add("on");
        await wait(3500);
        pdf.classList.remove("on");
        takeaway(L("Approved & exported", "Freigegeben & exportiert"), L("PDF with a source for every field", "PDF mit Quelle für jedes Feld"));
      },
    },
    {
      time: "16:53", title: L("The day in 3D", "Der Tag in 3D"),
      intro: L("Every marker has a photo behind it.", "Hinter jedem Marker steckt ein Foto."),
      async run() {
        const c = window.Costs?.last;
        const money = c ? ` · Nachtrag ~${eurK(c.nachtrag_documented?.expected_eur || c.nachtrag_open?.expected_eur)} · ${L("delay risk", "Terminrisiko")} ~${eurK(c.delay_open?.expected_eur)}` : "";
        await look(null, L("End of day · every marker traces back to evidence", "Feierabend · jeder Marker hat einen Beleg"), true);
        await wait(3500);
        await look("w1", L("Abutment 1", "Widerlager 1") + money, true);
        await wait(4000);
        await look(null, L("Bridge BW 12 · ready for tomorrow", "Brücke BW 12 · bereit für morgen"), true);
        await wait(2000);
        small();
      },
    },
    {
      time: "16:55", title: L("Your turn: on your phone", "Jetzt du: auf dem Handy"),
      intro: L("Scan. Talk. It appears live.", "Scannen. Sprechen. Erscheint live."),
      async run() {
        let info = {};
        try { info = await api("/api/site/phone"); } catch {}
        phoneBox.innerHTML = phoneCard(info);
        phoneBox.classList.add("on");
        takeaway(L("No install, no login", "Keine Installation, kein Login"), L("Voice, photos and live location from the site", "Sprache, Fotos und Live-Standort von der Baustelle"));
        await wait(info.qr ? 5500 : 4000);
        phoneBox.classList.remove("on");
      },
    },
  ];

  /* ------------------------------------------------------------------ finale */
  async function finale() {
    setClock("17:00");
    pipOff();
    let docs = [];
    try { docs = await api("/api/docs"); } catch {}
    const fields = docs.reduce((s, d) => s + Object.values(d.fields || {}).filter(f => f.value).length, 0);
    const cited = docs.reduce((s, d) => s + Object.values(d.fields || {}).filter(f => f.value && f.source && (f.source.evidence_id || f.source.type)).length, 0);
    const ai = Math.max(1, Math.round(ST.aiSec));
    let money = null;
    try { money = await api("/api/costs"); } catch {}
    fin.innerHTML = `<div class="st-fbox" role="dialog" aria-modal="true" aria-label="${L("End of the day", "Feierabend")}">
      <h2>${L("17:00 — Markus goes home on time.", "17:00 — Markus hat pünktlich Feierabend.")}</h2>
      <p>${L("Today, measured live:", "Heute, live gemessen:")}</p>
      <div class="st-kpis">
        <div class="st-kpi"><b>${docs.length}</b><span>${L("documents drafted", "Dokumente entworfen")}</span></div>
        <div class="st-kpi"><b>${fields}</b><span>${L("fields filled", "Felder gefüllt")}</span></div>
        <div class="st-kpi"><b>${cited}</b><span>${L("with a cited source", "mit Quellenangabe")}</span></div>
        <div class="st-kpi"><b>0</b><span>${L("sent without his click", "ohne seinen Klick versendet")}</span></div>
      </div>
      ${money ? `<div class="st-cmp st-money">
        <div><b>${eurK(money.nachtrag_documented.expected_eur || money.nachtrag_open.expected_eur)}</b><span>${L("change order potential, documented the same day", "Nachtrag-Potenzial, am selben Tag dokumentiert")}</span></div>
        <div><b>${eurK(money.idle_avoided.expected_eur || money.idle_avoidable.expected_eur)}</b><span>${money.idle_avoided.count ? L("idle cost avoided by reassigning the crew", "Stillstand vermieden durch Umsetzung") : L("idle cost avoidable", "Stillstand vermeidbar")}</span></div>
        <div><b>${money.delay_open ? eurK(money.delay_open.expected_eur) : "––"}</b><span>${L("delay risk made visible before it happens", "Terminrisiko sichtbar, bevor es passiert")}</span></div>
      </div>` : ""}
      <div class="st-cmp">
        <div><b>${fmtMin(ST.saved)}</b><span>${L("by hand (team estimate per document)", "von Hand (Team-Schätzung je Dokument)")}</span></div>
        <div><b>${ai < 120 ? ai + " s" : fmtMin(ai / 60)}</b><span>${L("AI processing time, measured in this run", "KI-Verarbeitungszeit, in diesem Durchlauf gemessen")}</span></div>
      </div>
      <ul class="st-list">${ST.log.map(l => `<li><em>${l.time}</em><span style="flex:1">${esc(l.text)}</span><span class="mut">≈ ${l.minutes} min</span></li>`).join("")}</ul>
      <div class="st-note">${L("Money figures: internal estimates (measured hours × internal rates, with ranges), never in outgoing documents. Manual times are team estimates. Drafting help only, no legal advice.", "Geldwerte: Schätzung, intern (gemessene Stunden × interne Sätze, mit Spanne), nie in ausgehenden Dokumenten. Handzeiten sind Team-Schätzungen. Nur Entwurfshilfe, keine Rechtsberatung.")}</div>
      <div class="st-facts"><button class="p" id="stDocs">${L("Open the documents", "Dokumente öffnen")}</button><button class="s" id="stTwin">${L("Explore the 3D twin", "3D-Zwilling erkunden")}</button><button class="s" id="stClose">${L("Close", "Schließen")}</button></div>
    </div>`;
    fin.classList.add("on");
    const close = t => { fin.classList.remove("on"); stop(true); if (t) NW.TAB(t); };
    q("#stDocs", fin).onclick = () => close("docs");
    q("#stTwin", fin).onclick = () => close("twin");
    q("#stClose", fin).onclick = () => close();
  }

  /* ------------------------------------------------------------------ control */
  function renderDots() {
    q("#stDots").innerHTML = SCENES.map((_, i) => `<i class="${i < ST.idx ? "done" : i === ST.idx ? "cur" : ""}"></i>`).join("");
  }
  async function run() {
    ST.on = true; ST.idx = 0; ST.saved = 0; ST.aiSec = 0; ST.log = []; ST.docs = {};
    window.FX?.stopAutopilot?.();
    hud.classList.add("on"); q("#stSaved").textContent = "0 min";
    await pipOn();
    look(null, L("Bridge BW 12 · live site", "Brücke BW 12 · Live-Baustelle"));
    for (; ST.idx < SCENES.length && ST.on; ST.idx++) {
      const s = SCENES[ST.idx];
      ST.skip = false; renderDots(); q("#stTitle").textContent = s.title; hideTake();
      await chapter(s.time, s.title, s.intro);
      if (!ST.on) break;
      ST.skip = false;
      try { await s.run(); }
      catch (e) { console.error(e); takeaway(L("This step failed", "Dieser Schritt ist fehlgeschlagen"), e.message || String(e)); }
      if (!ST.on) break;
      ST.skip = false;
      await wait(3000);
    }
    hideTake();
    if (ST.on) { ST.idx = SCENES.length; renderDots(); await finale(); }
  }
  function stop(quiet) {
    ST.on = false; ST.paused = false;
    hud.classList.remove("on"); chap.classList.remove("on"); hideTake(); voice.classList.remove("on"); pdf.classList.remove("on"); phoneBox.classList.remove("on"); costBox.classList.remove("on");
    pipOff();
    if (!quiet) fin.classList.remove("on");
    speechSynthesis?.cancel();
  }
  q("#stPause").onclick = () => { ST.paused = !ST.paused; q("#stPause").textContent = ST.paused ? "▶" : "❚❚"; };
  q("#stNext").onclick = () => { ST.skip = true; };
  q("#stExit").onclick = () => stop();
  addEventListener("keydown", e => {
    if (!ST.on || e.target.matches?.("input,textarea,select")) return;
    if (e.key === " ") { e.preventDefault(); q("#stPause").click(); }
    if (e.key === "ArrowRight") { e.preventDefault(); ST.skip = true; }
    if (e.key === "Escape") stop();
  });

  // start: fresh demo state, reload (all views pick it up), then a start card whose click unlocks audio + speech
  btn.onclick = async () => {
    btn.disabled = true; btn.textContent = L("Preparing the site…", "Baustelle wird vorbereitet…");
    try { await api("/api/demo/full", { json: {} }); } catch (e) { btn.disabled = false; btn.textContent = L("▶ Real Time Preview", "▶ Echtzeit-Vorschau"); return; }
    location.href = location.pathname + "?story=1";
  };
  if (new URLSearchParams(location.search).get("story") === "1") {
    history.replaceState(null, "", location.pathname);
    q("#stCt").textContent = "07:00";
    q("#stCh").textContent = L("A day in the life of a site manager", "Ein Tag im Leben eines Bauleiters");
    q("#stCp").innerHTML = esc(L("Bridge BW 12 · everything runs live", "Brücke BW 12 · alles läuft live"))
      + `<br><br><button class="p" id="stGo" style="pointer-events:auto;font-size:16px;padding:12px 22px">${L("▶ Start the day", "▶ Den Tag starten")}</button>`;
    chap.classList.add("on");
    q("#stGo").onclick = () => { chap.classList.remove("on"); setTimeout(run, 400); };
  }
  window.Story = { run, stop, phoneCard, get active() { return ST.on; } };
})();
