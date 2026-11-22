/* BauBuddy · feel layer: soft UI sounds (synthesised with Web Audio, no files), press ripples, success bursts, toasts.
   window.SFX = { tap, tab, send, success, alert, burst(x, y), done(text, el), on }  ·  toggle in the ⋯ menu ("Sounds"). */
(() => {
  "use strict";
  const q = (s, r = document) => r.querySelector(s);
  const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
  let on = store.get("nw-sfx") !== "off";
  let ctx = null, master = null;

  function ac() {
    if (!ctx) {
      const C = window.AudioContext || window.webkitAudioContext; if (!C) return null;
      ctx = new C(); master = ctx.createGain(); master.gain.value = 0.55; master.connect(ctx.destination);
    }
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  }
  // one soft tone: sine/triangle with a fast attack and an exponential tail
  function tone(freq, { at = 0, dur = 0.12, type = "sine", vol = 0.08, to = null } = {}) {
    const c = ac(); if (!c || !on) return;
    const t = c.currentTime + at, o = c.createOscillator(), g = c.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t);
    if (to) o.frequency.exponentialRampToValueAtTime(to, t + dur);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + 0.008); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(master); o.start(t); o.stop(t + dur + 0.02);
  }
  function noise({ dur = 0.18, vol = 0.05, from = 900, to = 2600 } = {}) {
    const c = ac(); if (!c || !on) return;
    const n = Math.floor(c.sampleRate * dur), b = c.createBuffer(1, n, c.sampleRate), d = b.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const s = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain(), t = c.currentTime;
    s.buffer = b; f.type = "bandpass"; f.Q.value = 1.2;
    f.frequency.setValueAtTime(from, t); f.frequency.exponentialRampToValueAtTime(to, t + dur);
    g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    s.connect(f); f.connect(g); g.connect(master); s.start(t);
  }

  const SFX = {
    get on() { return on; },
    set on(v) { on = !!v; store.set("nw-sfx", on ? "on" : "off"); },
    tap() { tone(1250, { dur: 0.05, vol: 0.035, to: 900, type: "triangle" }); },
    tab() { noise({ dur: 0.16, vol: 0.035 }); tone(660, { dur: 0.09, vol: 0.02, at: 0.02 }); },
    send() { tone(520, { dur: 0.09, vol: 0.05, to: 880 }); },
    success() { tone(784, { dur: 0.16, vol: 0.06 }); tone(1047, { dur: 0.22, vol: 0.06, at: 0.09 }); tone(1568, { dur: 0.3, vol: 0.025, at: 0.17 }); },
    alert() { tone(880, { dur: 0.16, vol: 0.06, type: "triangle" }); tone(660, { dur: 0.22, vol: 0.06, at: 0.16, type: "triangle" }); },
    burst, done,
  };

  /* ------------------------------------------------------------------ visuals */
  function burst(x, y, n = 16) {
    if (RM) return;
    const wrap = document.createElement("div"); wrap.className = "fx-burst"; wrap.style.left = x + "px"; wrap.style.top = y + "px";
    for (let i = 0; i < n; i++) {
      const s = document.createElement("i"), a = (i / n) * Math.PI * 2 + Math.random() * 0.4, r = 34 + Math.random() * 30;
      s.style.setProperty("--dx", Math.cos(a) * r + "px"); s.style.setProperty("--dy", Math.sin(a) * r + "px");
      s.style.animationDelay = Math.random() * 60 + "ms";
      if (i % 3 === 0) s.className = "w";
      wrap.appendChild(s);
    }
    document.body.appendChild(wrap);
    setTimeout(() => wrap.remove(), 900);
  }
  // "✓ Draft ready" pill + chime + burst on the element (or screen centre)
  function done(text, el) {
    SFX.success();
    const r = el?.getBoundingClientRect?.();
    burst(r ? r.left + r.width / 2 : innerWidth / 2, r ? r.top + r.height / 2 : innerHeight / 2);
    if (!text) return;
    const t = document.createElement("div"); t.className = "fx-pill"; t.innerHTML = `<b>✓</b>${String(text).replace(/</g, "&lt;")}`;
    document.body.appendChild(t);
    requestAnimationFrame(() => t.classList.add("on"));
    setTimeout(() => { t.classList.remove("on"); setTimeout(() => t.remove(), 400); }, 2200);
  }

  // press ripple + tap sound on every button-like control
  const PRESS = "button,.chip,.bb-chip,[role=button],#nav button,.s,.p,a.gl-chip";
  addEventListener("pointerdown", e => {
    const b = e.target.closest?.(PRESS); if (!b || b.disabled) return;
    if (b.closest("#nav")) SFX.tab(); else SFX.tap();
    if (RM) return;
    const r = b.getBoundingClientRect(), rip = document.createElement("span");
    rip.className = "fx-ripple"; rip.style.left = e.clientX - r.left + "px"; rip.style.top = e.clientY - r.top + "px";
    const cs = getComputedStyle(b);
    if (cs.position === "static") b.style.position = "relative";
    if (cs.overflow !== "hidden") b.style.overflow = "hidden";
    b.appendChild(rip); setTimeout(() => rip.remove(), 600);
  }, { capture: true, passive: true });

  // status changes in a document: Checked / Sent get the full celebration
  addEventListener("click", e => {
    const b = e.target.closest?.("[data-st]"); if (!b) return;
    const st = b.dataset.st;
    setTimeout(() => {
      const ok = !q("#derr")?.textContent;
      if (ok) done(st === "sent" ? "Sent" : "Checked", b); else SFX.alert();
    }, 450);
  }, true);

  // sounds toggle in the ⋯ menu (built by ui-glass.js)
  function addToggle() {
    const pop = q("#glMenuPop"); if (!pop || q("#fxSnd")) return !!pop;
    pop.insertAdjacentHTML("beforeend", `<div class="gl-sep"></div><button type="button" class="s" id="fxSnd">${on ? "🔊 Sounds on" : "🔈 Sounds off"}</button>`);
    q("#fxSnd").onclick = () => { SFX.on = !on; q("#fxSnd").textContent = on ? "🔊 Sounds on" : "🔈 Sounds off"; if (on) SFX.success(); };
    return true;
  }
  if (!addToggle()) addEventListener("load", addToggle);

  // hook the assistant bus once it exists
  let tries = 0;
  const hook = () => {
    if (!window.BB) return ++tries < 50 ? setTimeout(hook, 200) : null;      // the phone page has no assistant bus
    BB.on("incident:new", () => SFX.alert());
    BB.on("report", () => done("Report ready"));
  };
  hook();
  window.SFX = SFX;
})();
