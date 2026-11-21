/* Team Apex UI layer, additive only.
   Dashboard tab: three questions, read top to bottom (UI_STYLE §7, docs/ui/reference/dashboard_concept.html).
   Kept deliberately sparse: numbers, titles and actions; detail lives one click away.
   Reads only existing endpoints: GET /api/docs, /api/plan, /api/replan/proposals, /api/metrics/summary, /api/metrics.
   Actions call existing endpoints (POST /api/plan/propose, /api/replan/{id}/accept|reject, /api/reports/daily).
   A number that is not available shows "––", never a made-up value. */
(() => {
  "use strict";
  const NW = window.NW; if (!NW) return;
  const q = (s, r = document) => r.querySelector(s);
  const esc = NW.esc;
  const lang = (() => { try { return localStorage.getItem("nw-lang") === "de" ? "de" : "en"; } catch { return "en"; } })();
  const DE = lang === "de", L = (en, de) => (DE ? de : en);
  const ST = DE ? { draft: "Entwurf", checked: "Geprüft", sent: "Weitergegeben" } : { draft: "Draft", checked: "Checked", sent: "Sent" };
  const NT_TYPES = ["nachtragsmeldung", "mehrkostenanzeige"];
  const DASH = "––";
  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  const WD = DE ? ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"] : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const day = s => { const d = new Date(s + "T12:00:00"); return isNaN(d) ? s : `${WD[d.getDay()]} ${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.`; };
  const n1 = x => (Math.round(x * 10) / 10).toLocaleString(DE ? "de-DE" : "en-GB");
  const icon = (eid, type) => window.NWGlass?.iconFor(eid, type) || "🔗";
  const letterName = a => (a.suggest_label || "").replace(/^Draft /, "").replace(/\s*\(.*\)$/, "").replace("Bedenkenanzeige", "Bedenkenanmeldung");

  /* ---------------- section + nav button ---------------- */
  const sec = document.createElement("section");
  sec.id = "dash"; sec.className = "tab";
  sec.innerHTML = `<div class="db" id="db"><div class="db-loading mut">${L("Loading dashboard …", "Dashboard wird geladen …")}</div></div>`;
  const docsSec = q("#docs");
  (docsSec?.parentElement || q("main")).insertBefore(sec, docsSec || null);
  const btn = document.createElement("button");
  btn.dataset.t = "dash"; btn.textContent = "Dashboard";
  btn.onclick = () => NW.TAB("dash");
  q("#nav")?.appendChild(btn);

  /* ---------------- data ---------------- */
  let data = null, loading = false, lastAt = null, showSrc = !!store.get("nw-dash-src");
  async function load() {
    if (loading) return; loading = true;
    const get = u => NW.api(u).catch(e => ({ __err: e.message || String(e) }));
    const [docs, plan, replan, summary, metrics, twin] = await Promise.all([
      get("/api/docs"), get("/api/plan"), get("/api/replan/proposals"), get("/api/metrics/summary"), get("/api/metrics"), get("/api/site/twin")]);
    data = { docs: Array.isArray(docs) ? docs : [], plan: plan.__err ? null : plan, replan: replan.__err ? [] : (replan.proposals || replan || []),
      summary: summary.__err ? {} : summary, metrics: metrics.__err ? null : metrics, zones: twin.__err ? [] : (twin.layout?.zones || []) };
    lastAt = new Date(); loading = false;
    render();
  }
  const dismissed = () => store.get("nw-dash-dismissed") || [];
  const alertKey = a => `${a.kind}:${a.activity}`;
  function reqInfo(d) {
    const req = (d.meta?.fields || []).filter(f => f.required);
    return { req, filled: req.filter(f => d.fields?.[f.key]?.value), missing: req.filter(f => !d.fields?.[f.key]?.value) };
  }
  const where = d => d.fields?.location?.value || d.fields?.subject?.value || d.fields?.date?.value || "";
  const docTitle = d => `${d.title}${where(d) ? " · " + where(d) : ""}`;

  /* ---------------- actions ---------------- */
  function openDoc(id) {
    if (typeof openDocInTab === "function") openDocInTab(id); else NW.TAB("docs");
    window.NWGlass?.openSheet?.("docs");
  }
  function askInChat(id) { NW.TAB("assist"); NW.showAssistDoc(id); window.NWGlass?.openSheet?.("assist"); }
  async function propose(a, b) {
    if (b) b.disabled = true;
    try { const d = await NW.api("/api/plan/propose", { json: { kind: a.kind, activity: a.activity } }); openDoc(d.id); }
    catch (e) { toast(e.message); if (b) b.disabled = false; }
  }
  async function replanAct(p, act, b) {
    if (b) b.disabled = true;
    try { await NW.api(`/api/replan/${encodeURIComponent(p.id)}/${act}`, { json: {} }); load(); }
    catch (e) { toast(e.message); if (b) b.disabled = false; }
  }
  function dismissAlert(a) { store.set("nw-dash-dismissed", [...dismissed(), alertKey(a)]); render(); }
  async function daily(b) {
    if (b) b.disabled = true;
    try { const d = await NW.api("/api/reports/daily", { json: {} }); openDoc(d.id); }
    catch (e) { toast(e.message); if (b) b.disabled = false; }
  }
  function toast(msg) {
    const t = q("#dbToast", sec); if (!t) return;
    t.textContent = msg; t.hidden = false; clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), 4000);
  }

  /* ---------------- project progress (fills by itself as schedule milestones are reached) ---------------- */
  // Progress = schedule activities weighted by their planned duration, each counted by actual / total quantity
  // from GET /api/plan. Milestones = activity completions, ordered by planned end. Sections = site zones that
  // link schedule activities (GET /api/site/twin). Nothing is estimated beyond what those two endpoints report.
  const prevPct = new Map();
  let pMode = store.get("nw-dash-pmode") === "all" ? "all" : "one", pFocus = store.get("nw-dash-pfocus") || "site";
  function progressOf(acts) {
    if (!acts.length) return null;
    const w = a => Math.max(1, (new Date(a.end) - new Date(a.start)) / 864e5 + 1);
    const W = acts.reduce((s, a) => s + w(a), 0);
    let done = 0, planned = 0;
    for (const a of acts) { const t = a.total || 1; done += w(a) * Math.min(1, (a.actual || 0) / t); planned += w(a) * Math.min(1, (a.planned || 0) / t); }
    let c = 0;
    const ms = acts.slice().sort((a, b) => a.end.localeCompare(b.end)).map(a => { c += w(a); return { name: a.name, end: a.end, pos: c / W * 100, hit: (a.actual || 0) >= (a.total || 1) }; });
    return { pct: done / W * 100, plan: planned / W * 100, ms, next: ms.find(m => !m.hit) };
  }
  function projects(plan, zones) {
    const acts = plan?.activities || [];
    const site = (typeof cfg !== "undefined" && cfg?.site?.name) || L("Project", "Projekt");
    const list = [{ id: "site", name: site, acts }];
    for (const z of zones) {
      const a = acts.filter(x => (z.activities || []).includes(x.id));
      if (a.length) list.push({ id: "z:" + z.id, name: z.name, acts: a, section: true });
    }
    return list.filter(p => p.acts.length);
  }
  function barHtml(p, big) {
    const g = progressOf(p.acts), pct = Math.round(g.pct);
    return `<div class="db-pb ${big ? "big" : ""}" data-pid="${esc(p.id)}" data-to="${g.pct.toFixed(2)}">
      <div class="db-pb-top"><b>${esc(p.name)}</b>${p.section ? `<span class="db-pb-sec">${L("section", "Abschnitt")}</span>` : ""}<span class="sp"></span><span class="db-pb-pct">${pct}%</span></div>
      <div class="db-pb-track" title="${L(`Actual ${pct}% · plan today ${Math.round(g.plan)}%`, `Ist ${pct} % · Soll heute ${Math.round(g.plan)} %`)}">
        <div class="db-pb-fill"></div><i class="db-pb-plan" style="left:${g.plan.toFixed(2)}%"></i>
        ${g.ms.map(m => `<span class="db-ms" data-hit="${m.hit ? 1 : 0}" data-pos="${m.pos.toFixed(2)}" style="left:${m.pos.toFixed(2)}%" title="${esc(m.name)} · ${day(m.end)} · ${m.hit ? L("reached", "erreicht") : L("open", "offen")}"></span>`).join("")}
      </div>
      ${big ? `<div class="db-pb-next">${g.next ? `${L("Next milestone", "Nächster Meilenstein")}: <b>${esc(g.next.name)}</b> · ${day(g.next.end)}` : L("All milestones reached", "Alle Meilensteine erreicht")}</div>` : ""}
    </div>`;
  }
  function projHtml(plan, zones) {
    const list = projects(plan, zones);
    if (!list.length) return `<div class="mut">${L("No schedule loaded.", "Kein Bauzeitenplan geladen.")}</div>`;
    let i = Math.max(0, list.findIndex(p => p.id === pFocus));
    if (pMode === "all" && list.length > 1) return `<div class="db-pall">${list.map((p, k) => barHtml(p, k === 0)).join("")}</div>`;
    const multi = list.length > 1;
    return `<div class="db-pone" data-no-swipe>${multi ? `<button class="db-pnav" data-pstep="-1" aria-label="${L("Previous project", "Vorheriges Projekt")}">‹</button>` : ""}
      ${barHtml(list[i], true)}${multi ? `<button class="db-pnav" data-pstep="1" aria-label="${L("Next project", "Nächstes Projekt")}">›</button>` : ""}</div>
      ${multi ? `<div class="db-pdots">${list.map((p, k) => `<i class="${k === i ? "on" : ""}" data-pfocus="${esc(p.id)}" title="${esc(p.name)}"></i>`).join("")}</div>` : ""}`;
  }
  function animateBars(root) {
    const RM = matchMedia("(prefers-reduced-motion: reduce)").matches, DUR = RM ? 0 : 1400;
    root.querySelectorAll(".db-pb").forEach(pb => {
      pb.dataset.anim = 1;
      const id = pb.dataset.pid, to = +pb.dataset.to, from = prevPct.has(id) ? prevPct.get(id) : 0;
      prevPct.set(id, to);
      const fill = pb.querySelector(".db-pb-fill"), num = pb.querySelector(".db-pb-pct");
      fill.style.transition = "none"; fill.style.transform = `scaleX(${from / 100})`;
      pb.querySelectorAll(".db-ms").forEach(m => {
        const pos = +m.dataset.pos, hit = m.dataset.hit === "1";
        const at = to > from ? Math.min(1, Math.max(0, (pos - from) / (to - from))) : 0;
        m.classList.toggle("hit", hit && (pos <= from || to <= from));
        m.style.transitionDelay = hit ? `${Math.round(at * DUR * 0.8)}ms` : "0ms";
      });
      if (to === from || !DUR) { fill.style.transform = `scaleX(${to / 100})`; pb.querySelectorAll('.db-ms[data-hit="1"]').forEach(m => m.classList.add("hit")); return; }
      requestAnimationFrame(() => requestAnimationFrame(() => {
        fill.style.transition = `transform ${DUR}ms cubic-bezier(.22,1,.36,1)`;
        fill.style.transform = `scaleX(${to / 100})`;
        fill.classList.remove("run"); void fill.offsetWidth; fill.classList.add("run");
        pb.querySelectorAll('.db-ms[data-hit="1"]').forEach(m => m.classList.add("hit"));
        const t0 = performance.now(), ease = k => 1 - Math.pow(1 - k, 3);
        const step = now => { const k = Math.min(1, (now - t0) / DUR); num.textContent = Math.round(from + (to - from) * ease(k)) + "%"; if (k < 1) requestAnimationFrame(step); };
        requestAnimationFrame(step);
      }));
    });
  }
  function bindProjSwipe(root) {
    const box = root.querySelector(".db-pone"); if (!box) return;
    let sx = null;
    box.addEventListener("touchstart", e => { sx = e.touches.length === 1 ? e.touches[0].clientX : null; }, { passive: true });
    box.addEventListener("touchend", e => {
      if (sx == null) return; const dx = e.changedTouches[0].clientX - sx; sx = null;
      if (Math.abs(dx) > 50) stepProject(dx < 0 ? 1 : -1);
    }, { passive: true });
  }
  function stepProject(d) {
    const list = projects(data.plan, data.zones); if (list.length < 2) return;
    const i = Math.max(0, list.findIndex(p => p.id === pFocus));
    pFocus = list[(i + d + list.length) % list.length].id; store.set("nw-dash-pfocus", pFocus); prevPct.delete(pFocus); render();
  }

  /* ---------------- render ---------------- */
  const src = s => `<div class="db-src">${L("Source", "Quelle")}: ${esc(s)}</div>`;
  const kpi = (title, value, unit, extra = "", cls = "") =>
    `<div class="card db-kpi ${cls}"><div class="db-kpi-t">${title}</div><div class="db-kpi-v"><b>${value}</b>${unit ? `<span>${unit}</span>` : ""}</div>${extra}</div>`;

  function render() {
    const root = q("#db"); if (!root || !data) return;
    const { docs, plan, replan, summary, metrics } = data;
    const alerts = (plan?.alerts || []).filter(a => !dismissed().includes(alertKey(a)));
    const acts = plan?.activities || [];
    const drafts = docs.filter(d => d.status === "draft"), checked = docs.filter(d => d.status === "checked");
    const props = (Array.isArray(replan) ? replan : []).filter(p => !p.status || /^(open|pending|proposed|new)$/.test(p.status));
    const letters = alerts.filter(a => a.suggest);

    /* ---- 1 · KPI strip ---- */
    const waiting = drafts.length + checked.length + props.length + letters.length;
    const nts = docs.filter(d => NT_TYPES.includes(d.type) && d.status !== "sent").sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    const nt = nts[0], ntInfo = nt ? reqInfo(nt) : null;
    const ntPct = ntInfo && ntInfo.req.length ? Math.round(ntInfo.filled.length / ntInfo.req.length * 100) : 0;
    const worst = acts.filter(a => a.light !== "grey").sort((a, b) => (b.delay_days || 0) - (a.delay_days || 0))[0];
    const saved = [summary.time_saved_min, summary.writing_time_saved_min, summary.saved_minutes_today].find(v => typeof v === "number");
    const kpis = [
      kpi(L("Waiting for you", "Warten auf dich"), waiting, ""),
      kpi(L("Claims in progress", "Nachträge in Vorbereitung"), nts.length, nt ? `${L("evidence", "Belege")} ${ntInfo.filled.length}/${ntInfo.req.length}` : "",
        nt ? `<div class="gl-progress"><i style="width:${ntPct}%"></i></div>` : ""),
      kpi(L("Largest delay", "Größter Verzug"), plan ? (worst && worst.delay_days > 0 ? n1(worst.delay_days) : "0") : DASH, plan ? L("working days", "Arbeitstage") : "",
        "", worst?.light === "red" ? "bad" : worst?.delay_days > 0 ? "warn" : ""),
      kpi(L("Writing time saved", "Schreibzeit gespart"), typeof saved === "number" ? Math.round(saved) : DASH, typeof saved === "number" ? L("min today", "min heute") : "", "", typeof saved === "number" ? "" : "na"),
    ].join("");

    /* ---- 1 · Decide today ---- */
    const rows = [];
    for (const a of letters) rows.push({ u: a.level === "red" ? 0 : 2, cls: a.level === "red" ? "bad" : "warn", ic: "✉️",
      t: `${esc(letterName(a))} · ${L("letter suggested", "Brief vorgeschlagen")}`,
      b: [[L("Accept", "Übernehmen"), "p", el => propose(a, el)], [L("Dismiss", "Verwerfen"), "", () => dismissAlert(a)]] });
    for (const p of props) rows.push({ u: 1, cls: "warn", ic: "👷",
      t: esc(p.title || p.summary || p.text || p.wording || L("Crew reassignment", "Umplanung")),
      b: [[L("Accept", "Übernehmen"), "p", el => replanAct(p, "accept", el)], [L("Dismiss", "Verwerfen"), "", el => replanAct(p, "reject", el)]] });
    for (const d of drafts) { const i = reqInfo(d);
      rows.push({ u: i.missing.length ? 1 : 3, cls: i.missing.length ? "bad" : "", ic: "📄", t: esc(docTitle(d)), tag: `${i.filled.length}/${i.req.length}`,
        b: i.missing.length ? [[L("Open", "Öffnen"), "p", () => openDoc(d.id)], [L("Complete in chat", "Im Chat ergänzen"), "", () => askInChat(d.id)]] : [[L("Review", "Prüfen"), "", () => openDoc(d.id)]] }); }
    for (const d of checked) rows.push({ u: 4, cls: "", ic: "✅", t: esc(docTitle(d)), b: [[L("Open", "Öffnen"), "", () => openDoc(d.id)]] });
    rows.sort((a, b) => a.u - b.u);

    /* ---- 2 · Top warning ---- */
    const top = alerts.find(a => a.level === "red") || alerts[0];
    const frost = (plan?.alerts || []).find(a => a.kind === "frost");
    const w = plan?.weather_today;
    const wx = [];
    if (w) wx.push(`<div class="db-day"><span>${L("Today", "Heute")}</span><b>${Math.round(w.tmin)}–${Math.round(w.tmax)}°</b></div>`);
    if (frost?.weather_date) wx.push(`<div class="db-day frost"><span>${day(frost.weather_date)}</span><b>${n1(frost.tmin)}°</b><small>${L("Frost", "Frost")}</small></div>`);
    const warnHtml = top ? `<div class="db-warn-t">${esc(top.text)}</div>
        ${wx.length ? `<div class="db-days">${wx.join("")}</div>` : ""}
        <div class="db-actions">${top.suggest ? `<button class="p" data-db="letter">${esc(letterName(top))} ${L("as draft", "als Entwurf")}</button><button data-db="dismiss">${L("Dismiss", "Verwerfen")}</button>` : ""}
          <span class="sp"></span>${alerts.length > 1 ? `<button data-db="plan">+${alerts.length - 1}</button>` : ""}</div>`
      : `<div class="mut">${plan ? L("No warnings.", "Keine Warnungen.") : L("No schedule loaded.", "Kein Bauzeitenplan geladen.")}</div>`;

    /* ---- 2 · Schedule ---- */
    let gantt = `<div class="mut">${DASH}</div>`;
    if (acts.length) {
      const t0 = Math.min(...acts.map(a => +new Date(a.start))), t1 = Math.max(...acts.map(a => +new Date(a.end))) + 864e5;
      const pos = s => ((+new Date(s) - t0) / (t1 - t0) * 100);
      const today = plan.as_of ? pos(plan.as_of) : null;
      const ticks = []; for (let t = t0; t < t1; t += 864e5 * Math.max(1, Math.round((t1 - t0) / 864e5 / 5))) ticks.push(t);
      gantt = `<div class="db-gantt">
        <div class="db-g-row db-g-head"><span></span><div class="db-g-track">${ticks.map(t => `<i style="left:${(t - t0) / (t1 - t0) * 100}%">${day(new Date(t).toISOString().slice(0, 10))}</i>`).join("")}</div><span></span></div>
        ${acts.map(a => {
          const l = pos(a.start), r = pos(a.end) + 864e5 / (t1 - t0) * 100, frac = Math.min(1, (a.actual || 0) / (a.total || 1));
          const isFrost = frost && frost.activity === a.id;
          const chip = a.actual >= a.total ? [L("done", "fertig"), "ok"] : a.light === "grey" ? [isFrost ? L("Frost", "Frost") : "–", isFrost ? "bad" : ""]
            : a.delay_days > 0 ? [`+${n1(a.delay_days)} ${L("d", "AT")}`, a.light === "red" ? "bad" : "warn"] : [L("on plan", "im Plan"), "ok"];
          return `<div class="db-g-row"><span class="db-g-name">${esc(a.name)}${isFrost ? " ❄" : ""}</span>
            <div class="db-g-track"><div class="db-g-bar ${a.light}" style="left:${l}%;width:${r - l}%"><i style="width:${frac * 100}%"></i></div>
            ${today != null ? `<u style="left:${today}%" title="${L("today", "heute")}"></u>` : ""}</div><span class="db-chip ${chip[1]}">${chip[0]}</span></div>`;
        }).join("")}</div>`;
    }

    /* ---- 3 · Claim evidence ---- */
    let ev = `<div class="mut">${DASH}</div>`;
    if (nt) {
      const keys = (nt.meta?.fields || []).filter(f => f.required || f.critical || nt.fields?.[f.key]?.source?.evidence_id);
      ev = `<div class="db-ev-h"><b>${esc(docTitle(nt))}</b><span class="pill ${nt.status}">${ST[nt.status]}</span></div>
        <div class="gl-progress"><i style="width:${ntPct}%"></i></div>
        <ul class="db-ev">${keys.slice(0, 8).map(f => {
          const v = nt.fields?.[f.key], s = v?.source;
          if (v?.value) return `<li><span class="ok">✓</span><span class="db-ev-l">${esc(f.label)}</span><span class="db-tag" title="${esc((s?.locator || "") + (s?.evidence_id ? " · " + s.evidence_id : ""))}">${icon(s?.evidence_id, s?.type)}</span></li>`;
          if (f.required) return `<li><span class="bad">!</span><span class="db-ev-l">${esc(f.label)}</span><button class="s" data-db-ask="${nt.id}">${L("Ask", "Nachfragen")}</button></li>`;
          return "";
        }).join("")}</ul>`;
    }

    /* ---- 3 · AI performance ---- */
    const stages = metrics?.stages || [];
    const st = name => stages.find(s => s.stage === name);
    const e2e = summary.e2e_voice_to_draft_p50_ms ?? summary.voice_to_draft_p50_ms ?? st("voice_to_draft_end_to_end")?.p50_ms;
    const acc = summary.extraction_accuracy ?? summary.accuracy;
    const cpd = summary.cost_per_document_eur ?? summary.cost_per_doc_eur;
    const maxMs = Math.max(1, ...stages.map(s => s.avg_ms || 0));
    const ms = v => (v || 0) < 1000 ? Math.round(v || 0) + " ms" : n1(v / 1000) + " s";
    const perf = `<div class="db-perf">
        <div><b>${e2e != null ? n1(e2e / 1000) + " s" : DASH}</b><span>${L("end to end", "Ende zu Ende")}</span></div>
        <div><b>${acc != null ? Math.round(acc * (acc <= 1 ? 100 : 1)) + " %" : DASH}</b><span>${L("fields correct", "Felder korrekt")}</span></div>
        <div><b>${cpd != null ? cpd.toLocaleString(DE ? "de-DE" : "en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 3 }) + " €" : DASH}</b><span>${L("per document", "pro Dokument")}</span></div></div>
      ${stages.length ? `<div class="db-stages">${stages.slice(0, 4).map(s => `<div><span>${esc(s.stage.replace(/_/g, " "))}</span><div class="gl-progress"><i style="width:${(s.avg_ms || 0) / maxMs * 100}%"></i></div><b>${ms(s.avg_ms)}</b></div>`).join("")}</div>` : ""}`;

    /* ---- 3 · History ---- */
    const hist = docs.slice().sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 5);
    const histHtml = hist.length ? `<ul class="db-hist">${hist.map(d => {
        const edits = (d.log || []).filter(e => e.by !== "ai" && e.kind === "edit" && !e.undone).length;
        return `<li data-db-open="${d.id}"><span><b>${esc(docTitle(d))}</b></span>${edits ? `<span class="db-tag" title="${L("corrected", "korrigiert")}">✎ ${edits}</span>` : ""}<span class="pill ${d.status}">${ST[d.status] || esc(d.status)}</span></li>`;
      }).join("")}</ul>` : `<div class="mut">${DASH}</div>`;

    const nProj = projects(plan, data.zones).length;
    root.classList.toggle("show-src", showSrc);
    const html = `
      <div class="card db-head db-proj"><div class="db-proj-h"><span class="gl-logo" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path class="d1" d="M12 17C12 10.4 17.4 6 24 6s12 4.4 12 11M7 17h34M24 6v5" stroke-width="3.4"/><path class="d2" d="M9 22h30a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3H20l-7 6v-6H9a3 3 0 0 1-3-3V25a3 3 0 0 1 3-3z" stroke-width="2.6"/><polyline class="d3" points="17,30 22,34.5 31,26" stroke-width="3.4"/></svg></span><b class="db-proj-title">${L("Project progress", "Projektfortschritt")}</b><span class="sp"></span>
        ${nProj > 1 ? `<div class="db-pmode" role="tablist"><button data-pmode="one" class="${pMode === "one" ? "on" : ""}">${L("One", "Eins")}</button><button data-pmode="all" class="${pMode === "all" ? "on" : ""}">${L("All", "Alle")} ${nProj}</button></div>` : ""}
        <span class="db-pill db-live"><i></i>${lastAt.toLocaleTimeString(DE ? "de-DE" : "en-GB", { hour: "2-digit", minute: "2-digit" })}</span>
        <button class="s" data-db="refresh" title="${L("Refresh", "Aktualisieren")}" aria-label="${L("Refresh", "Aktualisieren")}">↻</button>
        <label class="db-srcsw" title="${L("Show data sources", "Datenquellen anzeigen")}"><input type="checkbox" data-db="src" ${showSrc ? "checked" : ""}> ${L("Sources", "Quellen")}</label></div>
        ${projHtml(plan, data.zones)}
        ${src(L("GET /api/plan (actual / total per activity, weighted by planned duration) · sections from GET /api/site/twin zones",
                "GET /api/plan (Ist / Gesamt je Vorgang, gewichtet nach geplanter Dauer) · Abschnitte aus GET /api/site/twin")) }</div>
      <div class="db-toast" id="dbToast" role="status" hidden></div>

      <h3 class="db-q"><span>1</span>${L("What needs me?", "Was braucht mich?")}</h3>
      <div class="db-kpis">${kpis}</div>
      <div class="card pad db-today"><div class="db-ct"><b>${L("Decide today", "Heute zu entscheiden")}</b>${rows.length ? `<span class="db-count">${rows.length}</span>` : ""}</div>
        ${rows.length ? `<div class="db-rows">${rows.map((r, i) => `<div class="db-row ${r.cls}"><span class="db-ic">${r.ic}</span><div class="db-row-t"><b>${r.t}</b></div>${r.tag ? `<span class="db-tag">${r.tag}</span>` : ""}
          <div class="db-row-b">${r.b.map((b, k) => `<button class="${b[1]}" data-db-row="${i}:${k}">${b[0]}</button>`).join("")}</div></div>`).join("")}</div>`
          : `<div class="mut">${L("Nothing to decide.", "Nichts zu entscheiden.")}</div>`}
        ${src("GET /api/docs · /api/replan/proposals · /api/plan")}</div>

      <h3 class="db-q"><span>2</span>${L("What is the risk?", "Was ist das Risiko?")}</h3>
      <div class="db-grid2">
        <div class="card pad db-warn ${top ? top.level : ""}"><div class="db-ct"><b>⚠ ${L("Top warning", "Wichtigste Warnung")}</b><span class="sp"></span><button class="s" data-db="twin">${L("Site", "Baustelle")} →</button></div>${warnHtml}
          ${src("GET /api/plan · POST /api/plan/propose")}</div>
        <div class="card pad"><div class="db-ct"><b>${L("Schedule · critical activities", "Bauzeitenplan · kritische Vorgänge")}</b></div>${gantt}${src("GET /api/plan")}</div>
      </div>

      <h3 class="db-q"><span>3</span>${L("Is it documented?", "Ist es belegt?")}</h3>
      <div class="db-grid3">
        <div class="card pad"><div class="db-ct"><b>${L("Claim evidence", "Nachtrag · Belege")}</b></div>${ev}${src("GET /api/docs")}</div>
        <div class="card pad"><div class="db-ct"><b>${L("AI performance", "KI-Leistung")}</b></div>${perf}${src("GET /api/metrics/summary · GET /api/metrics")}</div>
        <div class="card pad"><div class="db-ct"><b>${L("History", "Verlauf")}</b></div>${histHtml}
          <button class="db-daily" data-db="daily">${L("Create today's daily report", "Tagesbericht heute erstellen")}</button>${src("GET /api/docs · POST /api/reports/daily")}</div>
      </div>`;
    // only touch the DOM when something changed: no flicker, and the progress bars animate only on real progress
    if (root._html !== html) { root._html = html; root.innerHTML = html; bindProjSwipe(root); if (sec.classList.contains("on")) animateBars(root); }

    root.onclick = e => {
      const pm = e.target.closest("[data-pmode]");
      if (pm) { pMode = pm.dataset.pmode; store.set("nw-dash-pmode", pMode); if (pMode === "all") prevPct.clear(); render(); return; }
      const ps = e.target.closest("[data-pstep]"); if (ps) return stepProject(+ps.dataset.pstep);
      const pf = e.target.closest("[data-pfocus]") || (pMode === "all" ? e.target.closest(".db-pall .db-pb") : null);
      if (pf) { pFocus = pf.dataset.pfocus || pf.dataset.pid; store.set("nw-dash-pfocus", pFocus); pMode = "one"; store.set("nw-dash-pmode", pMode); prevPct.delete(pFocus); render(); return; }
      const b = e.target.closest("[data-db],[data-db-row],[data-db-ask],[data-db-open]"); if (!b) return;
      if (b.dataset.dbRow) { const [i, k] = b.dataset.dbRow.split(":").map(Number); rows[i]?.b[k]?.[2](b); return; }
      if (b.dataset.dbAsk) return askInChat(b.dataset.dbAsk);
      if (b.dataset.dbOpen) return openDoc(b.dataset.dbOpen);
      const a = b.dataset.db;
      if (a === "refresh") load();
      else if (a === "letter") propose(top, b);
      else if (a === "dismiss") dismissAlert(top);
      else if (a === "plan") NW.TAB("plan");
      else if (a === "twin") NW.TAB("twin");
      else if (a === "daily") daily(b);
    };
    root.onchange = e => { if (e.target.dataset.db === "src") { showSrc = e.target.checked; store.set("nw-dash-src", showSrc); root.classList.toggle("show-src", showSrc); } };
  }

  /* ---------------- refresh when shown, every 30 s while visible, after demo actions ---------------- */
  // load only when the tab becomes visible (fx.js also toggles "reveal"/"enter" classes; those must not trigger a reload mid-animation)
  let wasOn = false;
  new MutationObserver(() => { const on = sec.classList.contains("on"); if (on && !wasOn) { const r = q("#db"); if (r && q(".db-pb:not([data-anim])", r)) animateBars(r); load(); } wasOn = on; }).observe(sec, { attributes: true, attributeFilter: ["class"] });
  setTimeout(() => (window.requestIdleCallback || (f => setTimeout(f, 300)))(() => load()), 1200);   // warm cache: the first visit renders instantly
  setInterval(() => { if (sec.classList.contains("on") && !document.hidden) load(); }, 30000);
  ["#demoBtn", "#resetBtn"].forEach(s => q(s)?.addEventListener("click", () => setTimeout(() => sec.classList.contains("on") && load(), 1200)));
  window.NWDash = { load };
})();
