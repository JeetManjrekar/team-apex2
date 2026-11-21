// BauBuddy film autopilot: drives the REAL app end to end in your installed Chrome and records 1080p frames.
// Everything on screen is live (Whisper on a real WAV via Chrome's fake mic, Claude extraction, real clicks).
// Usage:  node director.js <dictation.wav> [--typed] [--base http://127.0.0.1:8000]
// Output: raw/take_<time>/frames/*.jpg, frames.ffconcat (exact timing), markers.json (beat timestamps for the edit)
const { chromium } = require('playwright-core');
const fs = require('fs'), path = require('path');

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const BASE = opt('--base', 'http://127.0.0.1:8000');
const TYPED = args.includes('--typed');               // no WAV: type the dictation text instead (rehearsal only)
const WAV = args.find(a => a.endsWith('.wav')) && path.resolve(args.find(a => a.endsWith('.wav')));
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const CFG = JSON.parse(fs.readFileSync(path.join(__dirname, 'director.config.json'), 'utf8'));
if (!TYPED && !WAV) { console.error('Give a dictation .wav, or --typed for a rehearsal.'); process.exit(1); }

const TAKE = path.join(__dirname, 'raw', 'take_' + new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19));
const FR = path.join(TAKE, 'frames'); fs.mkdirSync(FR, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const wavSeconds = f => {   // walk the RIFF chunks (ffmpeg adds a LIST chunk before "data")
  const b = fs.readFileSync(f); let p = 12, rate = 0;
  while (p + 8 <= b.length) {
    const id = b.toString('ascii', p, p + 4), size = b.readUInt32LE(p + 4);
    if (id === 'fmt ') rate = b.readUInt32LE(p + 16);        // byte rate
    if (id === 'data') return size / rate;
    p += 8 + size + (size % 2);
  }
  throw new Error('no data chunk in ' + f);
};

(async () => {
  const flags = ['--force-device-scale-factor=1', '--autoplay-policy=no-user-gesture-required', '--hide-scrollbars', '--mute-audio'];
  if (WAV) flags.push('--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${WAV}%noloop`);
  const browser = await chromium.launch({ executablePath: CHROME, headless: !process.env.HEADED, args: flags });
  // 1440×810 layout at scale 4/3 = 1920×1080 pixels: the "125 % zoom" look, nothing wasted at the edges
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: 4 / 3, permissions: ['microphone'], locale: 'en-US' });
  await ctx.addInitScript(() => {                     // no spoken TTS in the film; our voiceover carries the sound
    try { window.speechSynthesis.speak = () => {}; } catch {}
  });
  const page = await ctx.newPage();
  page.on('pageerror', e => console.log('[page error]', e.message));

  // ---- clean state ----
  await page.request.post(BASE + '/api/demo/reset', { data: {} });
  await page.request.post(BASE + '/api/demo/load', { data: {} });
  // /api/demo/load restores project, schedule and progress only; the twin needs the seed layout, photos and uploads too
  const DATA = path.resolve(__dirname, CFG.app_data_dir);
  for (const f of ['site_layout.json', 'photos.json']) fs.copyFileSync(path.join(DATA, 'seed', f), path.join(DATA, f));
  fs.mkdirSync(path.join(DATA, 'uploads'), { recursive: true });
  for (const f of fs.readdirSync(path.join(DATA, 'seed', 'uploads'))) fs.copyFileSync(path.join(DATA, 'seed', 'uploads', f), path.join(DATA, 'uploads', f));
  const health = await (await page.request.get(BASE + '/api/config')).json().catch(() => ({}));
  console.log('LLM mode:', JSON.stringify(health.llm || health.extraction || '?'));

  // ---- capture: CDP screencast, every repaint with its timestamp ----
  const cdp = await ctx.newCDPSession(page);
  const frames = []; let t0 = null;
  cdp.on('Page.screencastFrame', f => {
    const ts = f.metadata.timestamp; if (t0 === null) t0 = ts;
    const name = `f${String(frames.length).padStart(6, '0')}.jpg`;
    fs.writeFileSync(path.join(FR, name), Buffer.from(f.data, 'base64'));
    frames.push({ name, ts });
    cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {});
  });
  const markers = [];
  const mark = (beat, extra = {}) => { const t = t0 === null ? 0 : Date.now() / 1000 - t0; markers.push({ beat, t: +t.toFixed(3), ...extra }); console.log(`  ${t.toFixed(1).padStart(6)} s  ${beat}`); };
  const settle = ms => sleep(ms);

  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: 1920, maxHeight: 1080 });
  mark('splash');                                      // the app's own BAUBUDDY boot splash
  await page.waitForFunction(() => document.querySelector('#splash')?.hidden, null, { timeout: 15000 }).catch(() => {});
  await settle(400);

  // ================= 1 · dictation → draft =================
  await page.evaluate(() => NW.TAB('assist'));
  await settle(700);
  await page.evaluate(() => document.querySelector('#chat')?.scrollIntoView({ block: 'end', behavior: 'smooth' }));   // chat + draft fill the frame
  await settle(600);
  mark('assist');
  if (TYPED) {
    await page.click('#inp');
    await page.type('#inp', CFG.dictation_text, { delay: 28 });
    mark('dictation_start'); await settle(400);
    await page.click('#send');
  } else {
    await page.click('#mic');
    mark('dictation_start');
    await settle(wavSeconds(WAV) * 1000 + 1300);         // let the whole sentence play, captions appear live
    mark('dictation_stop');
    await page.click('#vSend');
  }
  await page.waitForFunction(() => document.querySelector('#assistDoc h2'), null, { timeout: 240000 });
  await settle(700);
  mark('draft_ready', { title: await page.textContent('#assistDoc h2') });
  await settle(CFG.hold.draft);

  // ================= 2 · proof: open two source quotes =================
  const openSource = async (re, beat) => {
    const ok = await page.evaluate(src => {
      const r = new RegExp(src, 'i');
      const f = [...document.querySelectorAll('#assistDoc .f')].find(x => r.test(x.querySelector('.src')?.textContent || ''));
      if (!f) return false;
      f.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(() => f.querySelector('[data-q]')?.click(), 700);
      f.dataset.film = '1'; return f.dataset.k;
    }, re);
    if (ok) { await settle(800); const box = await page.locator(`#assistDoc .f[data-k="${ok}"]`).boundingBox(); mark(beat, { field: ok, box }); await settle(CFG.hold.source); }
    else console.log(`  (no source matching /${re}/ — beat ${beat} skipped)`);
  };
  await openSource(CFG.source_patterns.document, 'source_document');
  await openSource(CFG.source_patterns.audio, 'source_audio');

  // ================= 3 · gap → question → answer =================
  const docId = await page.evaluate(() => typeof activeDoc !== 'undefined' ? activeDoc : null);
  const missingNow = async () => docId ? (await (await page.request.get(`${BASE}/api/docs/${docId}`)).json()).missing || [] : [];
  let missing = await missingNow(), round = 0;
  if (!missing.length) console.log('  (no missing field — gap beat skipped)');
  while (missing.length && round < 3) {      // answer what BauBuddy asks, one question at a time, by field key
    round++;
    await page.evaluate(() => { const m = document.querySelector('#msgs'); m.scrollTop = 1e9; });
    const question = await page.evaluate(() => [...document.querySelectorAll('#msgs .m.assistant')].pop()?.textContent || '');
    const key = missing[0];
    const ans = CFG.answers[key];
    if (!ans) { console.log(`  (no prepared answer for ${key} — add one to director.config.json)`); break; }
    mark(round === 1 ? 'question' : `question_${round}`, { missing, question: question.slice(0, 240) });
    await settle(CFG.hold.question);
    await page.click('#inp');
    await page.type('#inp', ans, { delay: 30 });
    await settle(300);
    mark(round === 1 ? 'answer_sent' : `answer_sent_${round}`, { field: key, answer: ans });
    const n0 = await page.evaluate(() => document.querySelectorAll('#msgs .m').length);
    await page.click('#send');
    await page.waitForFunction(n => document.querySelectorAll('#msgs .m').length >= n + 2, n0, { timeout: 120000 }).catch(() => {});
    await settle(1200);
    mark(round === 1 ? 'answer_filled' : `answer_filled_${round}`);
    await settle(CFG.hold.answer);
    missing = await missingNow();
  }

  // ================= 4 · human click → Word =================
  await page.evaluate(() => document.querySelector('#assistDoc')?.scrollTo({ top: 0, behavior: 'smooth' }));
  await settle(700);
  const chk = page.locator('#assistDoc [data-st="checked"]');
  if (await chk.count()) {
    await chk.hover(); await settle(500);
    await chk.click();
    await settle(900);
    mark('checked', { error: (await page.textContent('#derr').catch(() => '')) || undefined });
  }
  await settle(CFG.hold.checked);
  if (docId) {   // the Word file downloads; on screen we show the same document with its evidence appendix (print view)
    mark('word_view');
    await page.goto(`${BASE}/api/docs/${docId}/print`, { waitUntil: 'networkidle' });
    await settle(1500);
    await page.evaluate(() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }));
    await settle(CFG.hold.word);
    mark('word_appendix');
    await settle(1200);
    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => { const s = document.querySelector('#splash'); if (s) s.hidden = true; });
  }

  // ================= 5 · AI site manager + 3D twin =================
  await page.evaluate(() => NW.TAB('command'));
  await settle(1000);
  mark('agent');
  await page.click('#bbInp');
  await page.type('#bbInp', CFG.agent_command, { delay: 26 });
  await page.click('#bbSend');
  await settle(CFG.hold.agent);
  mark('agent_done');
  await page.evaluate(() => NW.TAB('twin'));
  await settle(900);
  mark('twin');
  await page.evaluate(() => { window.SiteTwin?.tour?.(); });
  await settle(CFG.hold.twin);
  await page.evaluate(() => window.SiteTwin?.stopTour?.());
  mark('end');
  await settle(500);

  await cdp.send('Page.stopScreencast');
  await browser.close();

  // exact-timing concat list: each frame lasts until the next one arrived
  const lines = ['ffconcat version 1.0'];
  frames.forEach((f, i) => { const d = i + 1 < frames.length ? frames[i + 1].ts - f.ts : 0.5; lines.push(`file 'frames/${f.name}'`, `duration ${Math.max(0.001, d).toFixed(4)}`); });
  lines.push(`file 'frames/${frames.at(-1).name}'`);
  fs.writeFileSync(path.join(TAKE, 'frames.ffconcat'), lines.join('\n'));
  fs.writeFileSync(path.join(TAKE, 'markers.json'), JSON.stringify({ base: BASE, typed: TYPED, wav: WAV || null, markers }, null, 1));
  console.log(`\n${frames.length} frames · ${(frames.at(-1).ts - frames[0].ts).toFixed(1)} s → ${TAKE}`);
})().catch(e => { console.error(e); process.exit(1); });
