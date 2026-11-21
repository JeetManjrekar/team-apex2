// voice (W2): real-time Whisper dictation.
// Mic -> AudioWorklet (downsample to 16 kHz PCM16) -> WebSocket /api/voice/stream -> live captions -> draft with audio evidence.
// Fallbacks: MediaRecorder + POST /api/voice when the socket is unavailable; Chrome Web Speech when there is no mic access
// (phones need HTTPS for getUserMedia).
(() => {
  const $ = s => document.querySelector(s);
  const API = window.API_BASE || "";
  const mic = $("#mic");
  if (!mic) return;

  /* ---------- panel UI (self-contained styles, no shared CSS edits) ---------- */
  const css = document.createElement("style");
  css.textContent = `
  #vPanel{position:absolute;left:12px;right:12px;bottom:calc(100% + 10px);z-index:20;display:none;padding:14px 16px 12px;border-radius:16px;
    background:linear-gradient(135deg,rgba(12,18,34,.96),rgba(18,26,48,.94));border:1px solid rgba(255,255,255,.14);
    box-shadow:0 24px 60px -20px rgba(0,0,0,.85),0 0 40px -12px rgba(255,77,31,.45);backdrop-filter:blur(16px);animation:vIn .35s cubic-bezier(.22,1,.36,1)}
  #vPanel.on{display:block}
  @keyframes vIn{from{opacity:0;transform:translateY(10px) scale(.98)}}
  #vPanel .vh{display:flex;align-items:center;gap:10px;font-size:12px;color:#8b94a8}
  #vPanel .vdot{width:9px;height:9px;border-radius:50%;background:#f87171;box-shadow:0 0 0 0 rgba(248,113,113,.7);animation:vPulse 1.3s infinite}
  #vPanel.busy .vdot{background:#22d3ee;animation:none;box-shadow:0 0 10px #22d3ee}
  @keyframes vPulse{70%{box-shadow:0 0 0 9px rgba(248,113,113,0)}100%{box-shadow:0 0 0 0 rgba(248,113,113,0)}}
  #vPanel .vt{font:600 12px ui-monospace,monospace;color:#e9edf5}
  #vPanel .vm{margin-left:auto;font-size:11px;color:#6f8fb8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #vPanel canvas{display:block;width:100%;height:34px;margin:8px 0 6px}
  #vPanel .vtx{min-height:44px;max-height:140px;overflow:auto;font-size:15px;line-height:1.45;color:#e9edf5}
  #vPanel .vtx i{color:#8b94a8;font-style:normal}
  #vPanel .vtx .ph{color:#5d6782}
  #vPanel .vb{display:flex;gap:8px;justify-content:flex-end;margin-top:10px}
  #vPanel .vb button{padding:7px 14px}
  #mic.rec{background:linear-gradient(135deg,#ff7a3d,#ff4d1f)!important;color:#fff;border-color:transparent}
  `;
  document.head.appendChild(css);
  const chat = $("#chat");
  const panel = document.createElement("div");
  panel.id = "vPanel";
  panel.innerHTML = `<div class="vh"><span class="vdot"></span><span class="vt" id="vTime">00:00</span><span id="vState">Listening…</span><span class="vm" id="vModel"></span></div>
    <canvas id="vWave" width="600" height="68"></canvas>
    <div class="vtx" id="vText"><span class="ph">Speak now — text appears live. German construction terms are recognised.</span></div>
    <div class="vb"><button class="s" id="vCancel">Cancel</button><button class="s" id="vEdit" title="Put the text into the input box to edit before sending">Edit first</button><button class="p s" id="vSend">Stop &amp; create draft</button></div>`;
  (chat || document.body).appendChild(panel);
  const inbar = chat?.querySelector(".inbar");
  if (inbar) { inbar.style.position = "relative"; inbar.appendChild(panel); }

  let st = null;   // active session state

  fetch(API + "/api/voice/status").then(r => r.json()).then(s => {
    const where = s.provider === "openai" ? "OpenAI (cloud)" : `offline · ${s.device === "mps" ? "Apple GPU" : "CPU"}`;
    const label = `Whisper ${s.model} · ${where}`;
    mic.title = `Live dictation — ${label}${s.provider === "local" && !s.offline_model_on_disk ? " (model will download on first use)" : ""}`;
    $("#vModel").textContent = label;
  }).catch(() => {});

  /* ---------- helpers ---------- */
  const lang = () => ($("#lang")?.value || "de-DE");
  const fmt = s => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const esc = s => String(s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const setText = (stable, partial) => { $("#vText").innerHTML = (stable || partial) ? `${esc(stable)} <i>${esc(partial)}</i>` : `<span class="ph">Listening…</span>`; $("#vText").scrollTop = 1e6; };
  const state = (t, busy) => { $("#vState").textContent = t; panel.classList.toggle("busy", !!busy); };

  // AudioWorklet: resample to 16 kHz mono, emit ~100 ms PCM16 chunks + RMS level
  const WORKLET = `class P extends AudioWorkletProcessor{constructor(){super();this.r=sampleRate/16000;this.acc=0;this.buf=[];}
    process(i){const ch=i[0]&&i[0][0];if(!ch)return true;let s=0;for(let k=0;k<ch.length;k++)s+=ch[k]*ch[k];
    for(let k=0;k<ch.length;k++){this.acc+=1;if(this.acc>=this.r){this.acc-=this.r;this.buf.push(ch[k]);}}
    if(this.buf.length>=1600){const o=new Int16Array(this.buf.length);for(let k=0;k<o.length;k++){const v=Math.max(-1,Math.min(1,this.buf[k]));o[k]=v<0?v*32768:v*32767;}
    this.port.postMessage({pcm:o.buffer,rms:Math.sqrt(s/ch.length)},[o.buffer]);this.buf=[];}return true;}}registerProcessor("pcm16k",P);`;

  function drawWave() {
    const cv = $("#vWave"), c = cv.getContext("2d"), w = cv.width, h = cv.height;
    c.clearRect(0, 0, w, h);
    const n = st.levels.length, bw = w / 60;
    for (let i = 0; i < n; i++) {
      const v = Math.min(1, st.levels[i] * 9), bh = Math.max(2, v * h);
      const g = c.createLinearGradient(0, h / 2 - bh / 2, 0, h / 2 + bh / 2); g.addColorStop(0, "#ff7a3d"); g.addColorStop(1, "#22d3ee");
      c.fillStyle = g; c.fillRect(w - (n - i) * bw + 1, h / 2 - bh / 2, bw - 2, bh);
    }
  }

  /* ---------- live session ---------- */
  async function start() {
    if (!navigator.mediaDevices?.getUserMedia) return webSpeechFallback("Microphone needs HTTPS (or localhost). Using browser dictation.");
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch (e) { return webSpeechFallback("Microphone permission denied."); }
    st = { stream, levels: [], t0: performance.now(), stable: "", partial: "", mode: "ws", chunks: [] };
    panel.classList.add("on"); mic.classList.add("rec"); setText("", ""); state("Connecting…", true);
    st.timer = setInterval(() => { $("#vTime").textContent = fmt((performance.now() - st.t0) / 1000); }, 250);

    const ctx = st.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") { try { await ctx.resume(); } catch {} }   // Safari / autoplay policies start it paused
    const src = ctx.createMediaStreamSource(stream);
    st.sent = 0;
    const onChunk = (pcm, rms) => {
      st.levels.push(rms); if (st.levels.length > 60) st.levels.shift(); drawWave();
      if (st.mode === "ws" && st.ws?.readyState === 1) { st.ws.send(pcm); st.sent++; }
    };
    try {
      await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" })));
      const node = st.node = new AudioWorkletNode(ctx, "pcm16k");
      node.port.onmessage = e => onChunk(e.data.pcm, e.data.rms);
      src.connect(node);
    } catch {
      // ScriptProcessor fallback (older Safari)
      const sp = st.node = ctx.createScriptProcessor(4096, 1, 1), r = ctx.sampleRate / 16000;
      let acc = 0, buf = [];
      sp.onaudioprocess = e => { const ch = e.inputBuffer.getChannelData(0); let s = 0;
        for (let k = 0; k < ch.length; k++) { s += ch[k] * ch[k]; if (++acc >= r) { acc -= r; buf.push(ch[k]); } }
        if (buf.length >= 1600) { const o = new Int16Array(buf.map(v => Math.max(-1, Math.min(1, v)) * 32767)); onChunk(o.buffer, Math.sqrt(s / ch.length)); buf = []; } };
      src.connect(sp); sp.connect(ctx.destination);
    }

    // socket; if it fails, record with MediaRecorder and upload at the end
    const url = (API || location.origin).replace(/^http/, "ws") + "/api/voice/stream";
    try {
      const ws = st.ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      ws.onopen = () => { ws.send(JSON.stringify({ type: "start", language: lang(), submit: true })); state("Listening…"); };
      ws.onmessage = e => handle(JSON.parse(e.data));
      ws.onerror = () => { if (st && st.mode === "ws" && !st.stopping) toUpload(); };
      ws.onclose = () => { if (st && st.mode === "ws" && !st.done && !st.stopping) toUpload(); };
    } catch { toUpload(); }
  }

  function toUpload() {
    if (!st || st.mode === "upload") return;
    st.mode = "upload";
    state("Recording (live captions unavailable)…");
    if (window.MediaRecorder) {
      const mr = st.mr = new MediaRecorder(st.stream);
      mr.ondataavailable = e => e.data.size && st.chunks.push(e.data);
      mr.start(500);
    }
  }

  function handle(m) {
    if (!st) return;
    if (m.type === "partial") { st.stable = m.stable; st.partial = m.partial; setText(m.stable, m.partial); }
    else if (m.type === "warning") state(m.detail);
    else if (m.type === "error") { finish(); notice("Voice error: " + m.detail); }
    else if (m.type === "final") { st.done = true; done(m); }
  }

  async function stop(mode = "send") {
    if (!st || st.stopping) return;
    st.stopping = true; st.sendMode = mode;
    clearInterval(st.timer);
    state(mode === "edit" ? "Finalising transcript…" : "Transcribing & drafting…", true);
    st.stream.getTracks().forEach(t => t.stop());
    closeAudio();
    if (st.mode === "ws" && st.ws?.readyState === 1) {
      if (mode === "edit") { st.ws.send(JSON.stringify({ type: "start", language: lang(), submit: false })); }
      st.ws.send(JSON.stringify({ type: "stop" }));
      return;   // `final` arrives in handle()
    }
    // upload path
    if (st.mr && st.mr.state !== "inactive") { await new Promise(r => { st.mr.onstop = r; st.mr.stop(); }); }
    const blob = new Blob(st.chunks, { type: st.mr?.mimeType || "audio/webm" });
    if (!blob.size) { finish(); return; }
    const fd = new FormData(); fd.append("audio", blob, "voice" + (blob.type.includes("mp4") ? ".m4a" : ".webm"));
    fd.append("language", lang()); fd.append("submit", mode === "edit" ? "false" : "true");
    try {
      const r = await fetch(API + "/api/voice", { method: "POST", body: fd }); const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.statusText);
      done({ transcript: j.transcript, result: j.result, audio_file: j.audio_file });
    } catch (e) { finish(); notice("Voice upload failed: " + e.message); }
  }

  async function done(m) {
    const text = m.transcript?.text || "";
    const mode = st?.sendMode;
    finish();
    if (m.error && !text) { notice(m.error); return; }
    if (mode === "edit" || !m.result) {
      if (text) { const inp = $("#inp"); inp.value = (inp.value ? inp.value + " " : "") + text; inp.focus(); NW.dictated = true; }
      return;
    }
    await NW.loadMsgs();
    if (m.result?.active) NW.showAssistDoc(m.result.active);
  }

  function closeAudio() {
    try { st.node?.disconnect(); } catch {}
    try { if (st.ctx && st.ctx.state !== "closed") st.ctx.close(); } catch {}
  }

  // short message in the panel instead of a blocking alert
  function notice(text) {
    panel.classList.add("on"); panel.classList.remove("busy");
    $("#vText").innerHTML = `<span class="ph">${esc(text)}</span>`; $("#vState").textContent = "";
    clearTimeout(notice.t); notice.t = setTimeout(() => { if (!st) panel.classList.remove("on"); }, 3200);
  }

  function finish() {
    if (!st) return;
    clearInterval(st.timer);
    try { st.stream.getTracks().forEach(t => t.stop()); } catch {}
    closeAudio();
    try { if (st.ws && st.ws.readyState <= 1 && !st.done) st.ws.send(JSON.stringify({ type: "cancel" })); st.ws?.close(); } catch {}
    st = null;
    panel.classList.remove("on", "busy"); mic.classList.remove("rec");
  }

  /* ---------- Web Speech fallback (Chrome, no mic API / insecure origin) ---------- */
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition; let rec = null;
  function webSpeechFallback(why) {
    if (!SR) { alert(why + " No speech recognition available in this browser."); return; }
    if (rec) { rec.stop(); return; }
    rec = new SR(); rec.lang = lang(); rec.interimResults = true; rec.continuous = true; const base = $("#inp").value;
    rec.onresult = e => { NW.dictated = true; let t = ""; for (const r of e.results) t += r[0].transcript; $("#inp").value = (base ? base + " " : "") + t; };
    rec.onend = () => { rec = null; mic.classList.remove("rec"); }; rec.onerror = () => {}; rec.start(); mic.classList.add("rec");
  }

  /* ---------- wiring ---------- */
  mic.onclick = () => (st ? stop("send") : rec ? rec.stop() : start());
  $("#vSend").onclick = () => stop("send");
  $("#vEdit").onclick = () => stop("edit");
  $("#vCancel").onclick = () => finish();
  addEventListener("keydown", e => { if (st && e.key === "Escape") finish(); });
  window.NWVoice = { start, stop, cancel: finish, debug: () => st && { sent: st.sent, ctx: st.ctx?.state, ws: st.ws?.readyState, mode: st.mode, levels: st.levels.length } };
})();
