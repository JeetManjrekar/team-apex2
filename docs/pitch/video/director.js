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
    // use the app's recording path (MediaRecorder → /api/voice → local Whisper), not the browser's cloud speech API
    try { delete window.SpeechRecognition; delete window.webkitSpeechRecognition; } catch {}
    try { window.SpeechRecognition = undefined; window.webkitSpeechRecognition = undefined; } catch {}
    // German app language: the dictation is German (the mic sends this language to Whisper) and documents keep their German names
    try { localStorage.setItem('nw-lang', 'de'); } catch {}
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
  for (const [pid, pos] of Object.entries(CFG.photo_positions || {})) {    // photos onto the plan (what a user does by clicking)
    if (pid.startsWith('_')) continue;
    await page.request.patch(`${BASE}/api/photos/${pid}`, { data: pos });
  }
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

  // ================= 1 · dictation in the AI Manager → draft =================
  // (UI since integrate-all-3 @ 203c829: no Assistant tab; voice + chat live in the AI Manager, drafts open in Documents)
  const lastAi = () => page.evaluate(() => [...document.querySelectorAll('#bbHist .bb-msg.ai')].pop()?.textContent || '');
  const aiCount = () => page.evaluate(() => document.querySelectorAll('#bbHist .bb-msg.ai').length);
  const waitAi = async n0 => {                        // the AI reply after a message (drafting can take ~20-30 s)
    await page.waitForFunction(n => document.querySelectorAll('#bbHist .bb-msg.ai').length > n, n0, { timeout: 240000 });
    await page.waitForFunction(() => !/processing|executing|analysing/i.test(document.querySelector('#bbStateTxt')?.textContent || ''), null, { timeout: 60000 }).catch(() => {});
  };
  await page.evaluate(() => NW.TAB('command'));
  await settle(900);
  mark('assist');
  let n0 = await aiCount();
  if (TYPED) {
    await page.click('#bbInp');
    await page.type('#bbInp', CFG.dictation_text, { delay: 28 });
    mark('dictation_start'); await settle(400);
    await page.click('#bbSend');
  } else {
    await page.click('#bbMic');                        // records (MediaRecorder) → POST /api/voice → local Whisper
    mark('dictation_start');
    await settle(wavSeconds(WAV) * 1000 + 900);
    await page.click('#bbMic');                        // tap again to stop
    mark('dictation_stop');
  }
  await waitAi(n0);
  await settle(600);
  const firstReply = await lastAi();
  mark('draft_ready', { reply: firstReply.slice(0, 240) });
  await settle(CFG.hold.draft);

  // open the draft (the reply's "Open draft" button) → Documents tab
  const openDraft = async beat => {
    const btn = page.locator('#bbHist .bb-msg.ai [data-open]').last();
    await btn.hover(); await settle(400); await btn.click();
    await page.waitForFunction(() => document.querySelector('#docView h2'), null, { timeout: 30000 });
    await settle(900);
    mark(beat, { title: await page.textContent('#docView h2') });
  };
  await openDraft('doc_open');
  const docId = await page.evaluate(() => typeof docsSel !== 'undefined' ? docsSel : null);

  // ================= 2 · proof: open two source quotes =================
  const openSource = async (key, beat) => {        // scroll to a field by key and open its source quote
    const ok = await page.evaluate(k => {
      const f = document.querySelector(`#docView .f[data-k="${k}"]`);
      if (!f || !f.querySelector('[data-q]')) return false;
      f.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(() => f.querySelector('[data-q]').click(), 700);
      return true;
    }, key);
    if (ok) { await settle(800); const box = await page.locator(`#docView .f[data-k="${key}"]`).boundingBox(); mark(beat, { field: key, box }); await settle(CFG.hold.source); }
    else console.log(`  (field ${key} has no source — beat ${beat} skipped)`);
  };
  await openSource(CFG.source_fields.first, 'source_document');
  await openSource(CFG.source_fields.second, 'source_second');

  // ================= 3 · gap → question (AI Manager) → answer =================
  const missingNow = async () => docId ? (await (await page.request.get(`${BASE}/api/docs/${docId}`)).json()).missing || [] : [];
  let missing = await missingNow(), round = 0;
  if (!missing.length) console.log('  (no missing field — gap beat skipped)');
  while (missing.length && round < 3) {
    round++;
    await page.evaluate(() => NW.TAB('command'));
    await settle(800);
    await page.evaluate(() => { const h = document.querySelector('#bbHist'); if (h) h.scrollTop = 1e9; });
    const question = await lastAi();
    const key = missing[0];
    const ans = CFG.answers[key];
    if (!ans) { console.log(`  (no prepared answer for ${key} — add one to director.config.json)`); break; }
    mark(round === 1 ? 'question' : `question_${round}`, { missing, question: question.slice(0, 240) });
    await settle(CFG.hold.question);
    await page.click('#bbInp');
    await page.type('#bbInp', ans, { delay: 30 });
    await settle(300);
    mark(round === 1 ? 'answer_sent' : `answer_sent_${round}`, { field: key, answer: ans });
    n0 = await aiCount();
    await page.click('#bbSend');
    await waitAi(n0);
    await settle(900);
    mark(round === 1 ? 'answer_filled' : `answer_filled_${round}`, { reply: (await lastAi()).slice(0, 200) });
    await settle(CFG.hold.answer);
    missing = await missingNow();
  }

  // ================= 4 · reopen the (now complete) draft → human click =================
  await openDraft('doc_reopen');
  await page.evaluate(() => document.querySelector('#docView')?.scrollIntoView({ block: 'start' }));
  const chk = page.locator('#docView [data-st="checked"]');
  if (await chk.count()) {
    await chk.hover(); await settle(600);
    await chk.click();
    await settle(900);
    mark('checked', { error: (await page.textContent('#derr').catch(() => '')) || undefined });
  } else console.log('  (no "Mark as checked" button)');
  await settle(CFG.hold.checked);

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
  // follow the app's own tour captions so the edit can pick its best beats
  const tEnd = Date.now() + (CFG.hold.twin_max || 60000);
  let last = '';
  while (Date.now() < tEnd) {
    const cap = await page.evaluate(() => {
      const lt = document.querySelector('#lowerThird');
      return lt?.classList.contains('on') ? `${document.querySelector('#ltK')?.textContent}|${document.querySelector('#ltT')?.textContent}` : '';
    });
    if (cap && cap !== last) { last = cap; const [k, t] = cap.split('|'); mark('tour', { kicker: k, title: t }); }
    const touring = await page.evaluate(() => document.querySelector('#twTour')?.classList.contains('on'));
    if (!touring && Date.now() > tEnd - (CFG.hold.twin_max || 60000) + 3000) break;
    await settle(150);
  }
  await settle(800);
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
