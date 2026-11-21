/* Nachweis · cinematic layer: splash, tab transitions, reflections, count-ups, captions, autopilot.
   Pure presentation: it reads the same data as the app and never changes anything on the server. */
(() => {
  const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const q = s => document.querySelector(s);
  const qa = s => [...document.querySelectorAll(s)];
  const store = { get(k) { try { return sessionStorage.getItem(k); } catch { return null; } }, set(k, v) { try { sessionStorage.setItem(k, v); } catch {} } };

  /* ---------------- nav indicator ---------------- */
  function moveIndicator() {
    const nav = q("#nav"), on = nav?.querySelector("button.on"), ind = nav?.querySelector(".ind");
    if (!on || !ind) return;
    ind.style.left = on.offsetLeft + "px";
    ind.style.width = on.offsetWidth + "px";
    on.scrollIntoView({ block: "nearest", inline: "nearest", behavior: RM ? "auto" : "smooth" });
  }
  addEventListener("resize", moveIndicator);

  /* ---------------- staggered reveal ---------------- */
  const REVEAL = ".card, .pc, tr, .alert, .tw-item, .f, .dl li";
  function stagger(section) {
    if (!section || RM) return;
    const mark = () => section.querySelectorAll(REVEAL).forEach((el, i) => el.style.setProperty("--i", Math.min(i, 12)));
    section.classList.remove("reveal"); void section.offsetWidth;
    mark(); section.classList.add("reveal");
    setTimeout(mark, 350);                       // content that arrives a moment later (API) joins the cascade
    clearTimeout(section._rv); section._rv = setTimeout(() => section.classList.remove("reveal"), 1800);
  }

  /* ---------------- tab transition ---------------- */
  function tab(t, apply) {
    const run = () => { apply(); moveIndicator(); stagger(document.getElementById(t)); };
    if (!RM && document.startViewTransition) {
      const vt = document.startViewTransition(run);
      [vt.ready, vt.finished, vt.updateCallbackDone].forEach(pr => pr?.catch(() => {}));   // aborted transitions (e.g. resize) are harmless
    }
    else { run(); const s = document.getElementById(t); s?.classList.remove("enter"); void s?.offsetWidth; s?.classList.add("enter"); }
  }

  /* ---------------- reflective pointer highlight + tilt ---------------- */
  let raf = 0, last;
  document.addEventListener("pointermove", e => {
    last = e; if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      const el = last.target.closest?.(".card, .pc, .tw-stats div");
      if (!el) return;
      const r = el.getBoundingClientRect(), x = last.clientX - r.left, y = last.clientY - r.top;
      el.style.setProperty("--mx", x + "px"); el.style.setProperty("--my", y + "px");
      if (el.classList.contains("pc") && !RM) {
        el.style.setProperty("--ry", ((x / r.width - 0.5) * 10).toFixed(2) + "deg");
        el.style.setProperty("--rx", ((0.5 - y / r.height) * 10).toFixed(2) + "deg");
      }
    });
  }, { passive: true });
  document.addEventListener("pointerout", e => {
    const el = e.target.closest?.(".pc");
    if (el && !el.contains(e.relatedTarget)) { el.style.setProperty("--rx", "0deg"); el.style.setProperty("--ry", "0deg"); }
  });

  /* ---------------- count-up for [data-count] ---------------- */
  function countUp(el) {
    if (el._counted) return; el._counted = true;
    const to = parseFloat(el.dataset.count), dec = (el.dataset.count.split(".")[1] || "").length, dur = RM ? 0 : 1100, t0 = performance.now();
    const step = now => {
      const k = dur ? Math.min(1, (now - t0) / dur) : 1, e = 1 - Math.pow(1 - k, 4);
      el.textContent = (to * e).toFixed(dec);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  new MutationObserver(() => qa("[data-count]").forEach(countUp)).observe(document.body, { childList: true, subtree: true });

  /* ---------------- keyboard: 1–9 switch tabs ---------------- */
  addEventListener("keydown", e => {
    if (e.metaKey || e.ctrlKey || e.altKey || /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) return;
    const b = qa("#nav button")[+e.key - 1];
    if (b) TAB(b.dataset.t);
  });

  /* ---------------- broadcast lower-third ---------------- */
  let capTimer;
  function caption(kicker, title, text = "", ms = 4000) {
    const lt = q("#lowerThird");
    q("#ltK").textContent = kicker;
    q("#ltT").innerHTML = String(title).split(" ").map((w, i) => `<span class="lt-word" style="animation-delay:${i * 45}ms">${w.replace(/</g, "&lt;")}</span>`).join(" ");
    q("#ltX").textContent = text;
    const bar = q("#ltP"); bar.style.transition = "none"; bar.style.width = "0"; void bar.offsetWidth;
    bar.style.transition = `width ${ms}ms linear`; bar.style.width = "100%";
    lt.classList.add("on");
    clearTimeout(capTimer);
    return sleep(ms);
  }
  function hideCaption() { q("#lowerThird").classList.remove("on"); }

  /* ---------------- splash ---------------- */
  async function splash({ replay = false } = {}) {
    const el = q("#splash");
    if (!el) return;
    const word = "NACHWEIS";
    q("#spWord").innerHTML = [...word].map((c, i) => `<span style="animation-delay:${300 + i * 70}ms">${c}</span>`).join("");
    el.hidden = false; el.classList.remove("out");
    let skip = false; const onSkip = () => { skip = true; };
    el.addEventListener("click", onSkip, { once: true });
    addEventListener("keydown", onSkip, { once: true });
    const bar = q("#spBar"), st = q("#spStatus"), t0 = performance.now();
    const say = (txt, pct) => { st.textContent = txt; bar.style.width = pct + "%"; };
    const wait = async (cond, max) => { const t = performance.now(); while (!skip && !cond() && performance.now() - t < max) await sleep(60); };
    if (!replay) {
      say("CONNECTING TO SITE API", 15);
      await wait(() => typeof cfg !== "undefined" && cfg, 5000);
      say(`SITE · ${(typeof cfg !== "undefined" && cfg?.site?.name || "").toUpperCase()}`, 40);
      await wait(() => typeof photos !== "undefined" && photos.length, 2500);
      const n = typeof photos !== "undefined" ? photos.length : 0, d = n ? photos.reduce((s, p) => s + (p.detections || []).length, 0) : 0;
      if (!skip) { say(`EVIDENCE · ${n} PHOTOS · ${d} AI DETECTIONS`, 70); await sleep(550); }
    }
    if (!skip) { say("DIGITAL TWIN ONLINE", 100); }
    while (!skip && performance.now() - t0 < (replay ? 1700 : 2300)) await sleep(50);
    el.classList.add("out");
    await sleep(RM ? 0 : 850);
    el.hidden = true;
  }

  /* ---------------- autopilot ---------------- */
  const AP = { on: false, token: 0 };
  const stopped = tok => !AP.on || tok !== AP.token;
  function resetAutopilotUI() {
    document.body.classList.remove("autopilot");
    q("#autoBtn").classList.remove("on"); q("#autoBtn").textContent = "▶ Autopilot";
  }
  function stopAutopilot() {
    if (!AP.on) return;
    AP.on = false; AP.token++;
    resetAutopilotUI();
    window.SiteTwin?.stopTour?.();
    caption("Autopilot", "Paused — you have the controls", "", 1600).then(() => { if (!AP.on) hideCaption(); });
  }
  async function autopilot() {
    AP.on = true; const tok = ++AP.token;
    document.body.classList.add("autopilot");
    q("#autoBtn").classList.add("on"); q("#autoBtn").textContent = "■ Stop";
    await splash({ replay: true });
    let plan = null; try { plan = await api("/api/plan"); } catch {}
    const nPh = photos.length, nDet = photos.reduce((s, p) => s + (p.detections || []).length, 0);
    const best = photos.flatMap(p => (p.detections || []).map(d => ({ ...d, p }))).sort((a, b) => b.confidence - a.confidence)[0];
    const alert = plan?.alerts?.find(a => a.level === "red") || plan?.alerts?.[0];
    const steps = [
      ["assist", "Site assistant", "Speak it. It becomes a formal notice.", "Chat or voice turns into Behinderungs- and Mehrkostenanzeigen. Every field cites its evidence.", 5200],
      ["docs", "Documents", "Draft → Checked → Sent, only by your click", `${docsCache.length || "Your"} documents with evidence appendix, edit locks and undo. Export to Word or PDF.`, 4800],
      ["plan", "Plan vs actual", alert ? "Early warning raised" : "Schedule on track", alert ? alert.text : "Planned vs actual quantities per activity, with weather-based frost warnings.", 5600],
      ["photos", "Photo evidence", `${nPh} photos · ${nDet} AI detections`, best ? `Best: ${best.class.replace(/_/g, " ")} at ${(best.confidence * 100).toFixed(1)}% (RF-DETR Small), evidence photo-${best.p.id}.` : "Upload site photos to detect machinery.", 5000],
    ];
    for (const [t, k, title, text, ms] of steps) {
      if (stopped(tok)) return;
      TAB(t);
      await caption(k, title, text, ms);
    }
    if (stopped(tok)) return;
    TAB("twin");
    await sleep(900);
    if (window.SiteTwin?.tour) await window.SiteTwin.tour({ isCancelled: () => stopped(tok) });
    if (stopped(tok)) return;
    TAB("metrics");
    await caption("Metrics", "Measured, not claimed", "Every pipeline stage is timed and costed in llm_metrics.jsonl.", 4200);
    if (stopped(tok)) return;
    await caption("Nachweis", "Evidence in. Notices out. On time.", "Autopilot finished — you have the controls.", 4200);
    AP.on = false; AP.token++; resetAutopilotUI(); hideCaption();
  }
  // a real user interaction (not the autopilot's own clicks) hands control back
  ["pointerdown", "wheel", "keydown"].forEach(ev => addEventListener(ev, e => {
    if (!AP.on || !e.isTrusted || e.target.closest?.("#autoBtn")) return;
    stopAutopilot();
  }, { capture: true, passive: true }));

  q("#autoBtn")?.addEventListener("click", () => (AP.on ? stopAutopilot() : autopilot()));

  window.FX = { tab, caption, hideCaption, splash, stagger, countUp, autopilot, stopAutopilot, get autopilotOn() { return AP.on; } };

  // boot
  requestAnimationFrame(moveIndicator);
  setTimeout(moveIndicator, 400);
  stagger(q(".tab.on"));
  const params = new URLSearchParams(location.search);
  if (!params.has("nosplash") && (params.has("splash") || !store.get("nw-splash"))) { store.set("nw-splash", "1"); splash(); }
})();
