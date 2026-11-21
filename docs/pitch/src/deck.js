// BauBuddy pitch deck builder. Output: docs/pitch/BauBuddy_Pitch.raw.pptx + anim.json (animations injected by fx.py)
const pptxgen = require('pptxgenjs');
const fs = require('fs');
const path = require('path');
const A = n => path.join(__dirname, 'assets', n);
const OUTDIR = path.resolve(__dirname, '..');

const F = 'Helvetica Neue';
const K = { bg: '14161C', ink: 'F2F4F8', mut: '9AA3B3', acc: 'FF7A00', accDark: 'C2410C', glass: '2A2F3A', ok: '3DDC84', warn: 'FFB020', bad: 'FF5A6E', dim: '5D6575' };
const THEME = {
  name: 'BauBuddy Graphite', headFontFace: F, bodyFontFace: F,
  colors: { dk1: '14161C', lt1: 'F2F4F8', dk2: '2A2F3A', lt2: 'E9EEF5', accent1: 'FF7A00', accent2: '3DDC84', accent3: 'FFB020', accent4: 'FF5A6E', accent5: '9AA3B3', accent6: 'C2410C', hlink: 'FF7A00', folHlink: 'C2410C' },
};

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.333 x 7.5
pres.title = 'BauBuddy · Pitch · TUM.ai Construction Hackathon Challenge B';
pres.author = 'Team Apex';
pres.theme = { headFontFace: F, bodyFontFace: F };

pres.defineSlideMaster({
  title: 'BB_DARK',
  background: { color: K.bg },
  objects: [],
});
pres.defineSlideMaster({
  title: 'BB_CONTENT',
  background: { color: K.bg },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: 0.6, y: 1.35, w: 12.1, h: 0.85, fontFace: F, fontSize: 38, bold: true, color: K.ink, valign: 'top', align: 'left', margin: 0 }, text: '' } },
  ],
});

const anim = {}; // slideNo -> [{name, fx, group, delay}]
let slideNo = 0;
let uid = 0;

// ---------- helpers ----------
const _sections = new Set();
function newSlide(master, section) {
  if (!_sections.has(section)) { pres.addSection({ title: section }); _sections.add(section); }
  const s = pres.addSlide({ masterName: master, sectionTitle: section });
  slideNo += 1;
  anim[slideNo] = [];
  s._no = slideNo;
  s.addImage({ path: A('bg.jpg'), x: 0, y: 0, w: 13.333, h: 7.5, objectName: 'bg' });
  return s;
}
function fx(s, name, f, group = 'auto', delay = 0) { anim[s._no].push({ name, fx: f, group, delay }); }
function nm(p) { uid += 1; return `${p}_${uid}`; }

function T(s, text, o) {
  const opts = Object.assign({ fontFace: F, color: K.ink, fontSize: 16, margin: 0, valign: 'top', isTextBox: true }, o);
  if (!opts.objectName) opts.objectName = nm('txt');
  s.addText(text, opts);
  return opts.objectName;
}
function card(s, x, y, w, h, o = {}) {
  const name = o.name || nm('card');
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: o.r ?? 0.22, objectName: name,
    fill: { color: o.fill || K.glass, transparency: o.tr ?? 38 },
    line: { color: o.line || 'FFFFFF', transparency: o.lineTr ?? 86, width: o.lw || 0.75 },
    shadow: { type: 'outer', color: '000000', blur: 20, offset: 6, angle: 90, opacity: 0.45 },
  });
  return name;
}
function img(s, file, x, y, w, h, name) { const n = name || nm('img'); s.addImage({ path: A(file), x, y, w, h, objectName: n }); return n; }
function iconDisc(s, icon, x, y, d, o = {}) {
  const n1 = nm('disc');
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, objectName: n1, fill: { color: o.fill || K.acc, transparency: o.tr ?? 84 }, line: { color: o.line || K.acc, transparency: o.lineTr ?? 55, width: 1 } });
  const p = d * 0.26;
  const n2 = img(s, icon, x + p, y + p, d - 2 * p, d - 2 * p);
  return [n1, n2];
}
function kicker(s, text, x = 0.6, y = 0.95, color = K.acc) {
  return T(s, text.toUpperCase(), { x, y, w: 9, h: 0.3, fontSize: 13, bold: true, color, charSpacing: 3 });
}
function brandSmall(s) {
  img(s, 'logo.png', 0.6, 0.42, 0.42, 0.42, '!!logo');
  T(s, 'BauBuddy', { x: 1.12, y: 0.42, w: 2.4, h: 0.42, fontSize: 17, bold: true, valign: 'middle', objectName: '!!brand' });
}
function glow(s, x, y, d, file = 'glow.png') { s.addImage({ path: A(file), x, y, w: d, h: d, objectName: file === 'glow.png' ? '!!glow' : nm('glowx') }); }
function chip(s, text, x, y, w, o = {}) {
  const n = nm('chip');
  s.addText(text, {
    shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.2, x, y, w, h: o.h || 0.44, objectName: n, isTextBox: true,
    fontFace: F, fontSize: o.fs || 14, bold: !!o.bold, color: o.color || K.ink, align: 'center', valign: 'middle', margin: 0,
    fill: { color: o.fill || K.glass, transparency: o.tr ?? 30 }, line: { color: o.line || 'FFFFFF', transparency: o.lineTr ?? 84, width: 0.75 },
  });
  return n;
}

// =====================================================================
// 1 · TITLE (holding slide)
// =====================================================================
{
  const s = newSlide('BB_DARK', 'Pitch (3 min)');
  glow(s, 3.67, -0.7, 6.0);
  img(s, 'logo.png', 5.67, 1.25, 2.0, 2.0, '!!logo');
  T(s, 'BauBuddy', { x: 0, y: 3.45, w: 13.333, h: 1.15, fontSize: 72, bold: true, align: 'center', valign: 'middle', objectName: '!!brand' });
  const t1 = T(s, [
    { text: 'Evidence in. Notices out. ', options: { color: K.ink } },
    { text: 'On time.', options: { color: K.acc } },
  ], { x: 0, y: 4.7, w: 13.333, h: 0.6, fontSize: 28, align: 'center' });
  const c = chip(s, 'TUM.ai Construction Hackathon  ·  Challenge B', 4.17, 6.35, 5.0, { fs: 13, color: K.mut });
  fx(s, '!!logo', 'zoom', 'auto', 0); fx(s, '!!brand', 'up', 'auto', 350); fx(s, t1, 'up', 'auto', 750); fx(s, c, 'fade', 'auto', 1100);
  s.addNotes(`HOLDING SLIDE, up before the timer starts. Say nothing. When the timer starts: click and go straight into the story.`);
}

// =====================================================================
// 2 · STORY · 11:30 Pfahl 7
// =====================================================================
{
  const s = newSlide('BB_CONTENT', 'Pitch (3 min)');
  glow(s, 6.9, 0.6, 6.5);
  brandSmall(s);
  const k = kicker(s, '11:30 · Bridge site');
  s.addText('Pile 7 hits rock at 4 m', { placeholder: 'title' });

  const X0 = 7.35, X1 = 12.75, G0 = 2.95, M = 0.39;
  const yAt = m => G0 + m * M;
  const sec = [];
  sec.push(img(s, 'drill.png', 9.42, G0 - 0.82, 0.78, 0.78));
  const gl = nm('ground'); s.addShape(pres.shapes.LINE, { x: X0, y: G0, w: X1 - X0, h: 0, objectName: gl, line: { color: K.ink, width: 1.5, transparency: 30 } }); sec.push(gl);
  const sand = nm('sand'); s.addShape(pres.shapes.RECTANGLE, { x: X0, y: G0, w: X1 - X0, h: 4 * M, objectName: sand, fill: { color: 'C9A26B', transparency: 72 }, line: { type: 'none' } }); sec.push(sand);
  const rock = nm('rock'); s.addShape(pres.shapes.RECTANGLE, { x: X0, y: yAt(4), w: X1 - X0, h: 6.95 - yAt(4), objectName: rock, fill: { color: '5A606C', transparency: 25 }, line: { type: 'none' } }); sec.push(rock);
  [[7.7, 5.0, 0.5, 0.25], [8.6, 5.7, 0.6, -0.2], [11.2, 5.1, 0.55, 0.3], [10.6, 6.2, 0.7, -0.25], [12.0, 5.8, 0.45, 0.2]].forEach(([x, y, w, h]) => {
    const n = nm('crack'); s.addShape(pres.shapes.LINE, { x, y, w, h: Math.abs(h), flipV: h < 0, objectName: n, line: { color: '8A919E', width: 1, transparency: 35 } }); sec.push(n);
  });
  sec.push(T(s, 'Sand & gravel', { x: X0 + 0.2, y: G0 + 0.15, w: 2.2, h: 0.3, fontSize: 13, color: 'E8D3AE', bold: true }));
  sec.push(T(s, 'Rock', { x: X0 + 0.2, y: yAt(4) + 0.15, w: 2.2, h: 0.3, fontSize: 13, color: 'C9CED8', bold: true }));
  [[0, '0 m'], [4, '4 m'], [9, '9 m']].forEach(([m, t]) => sec.push(T(s, t, { x: X0 - 0.62, y: yAt(m) - 0.14, w: 0.5, h: 0.28, fontSize: 12, color: K.mut, align: 'right' })));

  const exp = nm('exp'); s.addShape(pres.shapes.LINE, { x: X0, y: yAt(9), w: X1 - X0, h: 0, objectName: exp, line: { color: K.warn, width: 2, dashType: 'dash' } });
  const expBox = nm('expbox'); s.addShape(pres.shapes.RECTANGLE, { x: X0, y: G0, w: X1 - X0, h: 9 * M, objectName: expBox, fill: { type: 'none' }, line: { color: K.warn, width: 1.25, dashType: 'dash', transparency: 35 } });
  const expL = T(s, 'Gutachten p. 14', { x: X1 - 3.0, y: yAt(9) - 0.42, w: 2.85, h: 0.3, fontSize: 13, bold: true, color: K.warn, align: 'right' });
  const pile = nm('pile'); s.addShape(pres.shapes.RECTANGLE, { x: 9.66, y: G0, w: 0.3, h: 4 * M, objectName: pile, fill: { color: K.acc }, line: { type: 'none' } });
  const imp = nm('impact'); s.addImage({ path: A('glow_red.png'), x: 9.81 - 0.8, y: yAt(4) - 0.8, w: 1.6, h: 1.6, objectName: imp });

  const beats = [
    ['filetext.png', 'Report: sand & gravel to 9 m', false],
    ['clock.png', 'Hours of extra drilling', false],
    ['unlink_r.png', 'No proof. No Nachtrag.', true],
  ];
  const groups = [[exp, expBox, expL], [pile], [imp]];
  beats.forEach(([ic, h, bad], i) => {
    const y = 2.85 + i * 1.25;
    const [d1, d2] = iconDisc(s, ic, 0.6, y, 0.78, bad ? { fill: K.bad, line: K.bad } : {});
    const th = T(s, h, { x: 1.6, y, w: 5.4, h: 0.78, fontSize: 24, bold: true, valign: 'middle', color: bad ? K.bad : K.ink });
    [d1, d2, th].forEach(o => fx(s, o, 'up', 'click' + i, 0));
    groups[i].forEach(o => fx(s, o, i === 1 ? 'wipeDown' : 'fade', 'click' + i, i === 1 ? 150 : 250));
  });
  fx(s, k, 'fade', 'auto', 0);
  sec.forEach(o => fx(s, o, 'fade', 'auto', 200));
  s.addNotes(`[0:00–0:20] Christo. 3 clicks. No greeting.
"11:30 on a bridge site. Pile 7 hits rock at four metres."
CLICK "The client's soil report promised sand and gravel down to nine."
CLICK "So every pile takes hours longer. That's extra work the company can claim back."
CLICK "But only with proof, written down today. Nobody has time. No proof, no Nachtrag, money lost."`);
}

// =====================================================================
// 3 · THE GAP
// =====================================================================
{
  const s = newSlide('BB_CONTENT', 'Pitch (3 min)');
  glow(s, 3.9, 1.9, 5.5);
  brandSmall(s);
  s.addText('The evidence never arrives', { placeholder: 'title' });

  const Y = 2.85, H = 3.6;
  card(s, 0.6, Y, 4.1, H, { name: '!!siteCard' });
  const sh = iconDisc(s, 'hardhat.png', 0.9, Y + 0.3, 0.7);
  const st = T(s, 'On site', { x: 1.75, y: Y + 0.3, w: 2.8, h: 0.7, fontSize: 22, bold: true, valign: 'middle' });
  const siteObjs = [...sh, st];
  [['camera_w.png', 'Photos'], ['mic_w.png', 'Voice notes'], ['filetext_w.png', 'Daily reports'], ['mail_w.png', 'Emails']].forEach(([ic, t], i) => {
    const y = Y + 1.35 + i * 0.52;
    siteObjs.push(img(s, ic, 0.95, y + 0.03, 0.32, 0.32));
    siteObjs.push(T(s, t, { x: 1.45, y, w: 3.0, h: 0.38, fontSize: 17, valign: 'middle' }));
  });
  card(s, 8.63, Y, 4.1, H, { name: '!!officeCard' });
  const oh = iconDisc(s, 'briefcase.png', 8.93, Y + 0.3, 0.7);
  const ot = T(s, 'Nachtragsmanager', { x: 9.78, y: Y + 0.3, w: 2.85, h: 0.7, fontSize: 20, bold: true, valign: 'middle' });
  const ob = T(s, [{ text: 'No proof.', options: { breakLine: true } }, { text: 'No money.', options: { color: K.bad } }], { x: 8.93, y: Y + 1.5, w: 3.5, h: 1.5, fontSize: 30, bold: true, valign: 'middle' });
  const by = Y + H / 2;
  s.addShape(pres.shapes.LINE, { x: 4.85, y: by, w: 3.63, h: 0, objectName: '!!bridge', line: { color: K.bad, width: 3, dashType: 'dash' } });
  s.addShape(pres.shapes.OVAL, { x: 6.22, y: by - 0.45, w: 0.9, h: 0.9, objectName: '!!hubbg', fill: { color: K.bg }, line: { color: K.bad, width: 2 } });
  img(s, 'unlink_r.png', 6.45, by - 0.22, 0.44, 0.44, '!!hub');

  siteObjs.forEach(o => fx(s, o, 'fade', 'auto', 300));
  [...oh, ot].forEach(o => fx(s, o, 'fade', 'auto', 700));
  fx(s, ob, 'up', 'auto', 1200);
  s.addNotes(`[0:20–0:30] Christo.
"That's Challenge B: the site has the evidence, photos, voice notes, reports. It never reaches the Nachtragsmanager, the one who turns it into money."`);
}

// =====================================================================
// 4 · SOLUTION
// =====================================================================
{
  const s = newSlide('BB_CONTENT', 'Pitch (3 min)');
  glow(s, 3.85, -1.1, 5.6);
  brandSmall(s);
  s.addText([{ text: 'BauBuddy ', options: { color: K.acc } }, { text: 'closes the gap' }], { placeholder: 'title' });

  const by = 2.85;
  card(s, 0.6, by - 0.36, 2.9, 0.72, { name: '!!siteCard', r: 0.3 });
  const bs1 = img(s, 'hardhat.png', 0.85, by - 0.19, 0.38, 0.38);
  const bs2 = T(s, 'On site', { x: 1.35, y: by - 0.2, w: 2.0, h: 0.4, fontSize: 17, bold: true, valign: 'middle' });
  card(s, 9.83, by - 0.36, 2.9, 0.72, { name: '!!officeCard', r: 0.3 });
  const bo1 = img(s, 'briefcase.png', 10.08, by - 0.19, 0.38, 0.38);
  const bo2 = T(s, 'Nachtragsmanager', { x: 10.55, y: by - 0.2, w: 2.15, h: 0.4, fontSize: 15, bold: true, valign: 'middle' });
  s.addShape(pres.shapes.LINE, { x: 3.6, y: by, w: 6.13, h: 0, objectName: '!!bridge', line: { color: K.acc, width: 3.5 } });
  s.addShape(pres.shapes.OVAL, { x: 6.17, y: by - 0.5, w: 1.0, h: 1.0, objectName: '!!hubbg', fill: { color: K.bg }, line: { color: K.acc, width: 2 } });
  img(s, 'logo.png', 6.35, by - 0.32, 0.64, 0.64, '!!hub');

  [['mic.png', 'Speak or snap'], ['filecheck.png', 'Draft with proof'], ['usercheck.png', 'You decide']].forEach(([ic, h], i) => {
    const y = 3.95 + i * 1.0;
    const d = iconDisc(s, ic, 0.6, y, 0.7);
    const th = T(s, h, { x: 1.55, y, w: 4.5, h: 0.7, fontSize: 24, bold: true, valign: 'middle' });
    [...d, th].forEach(o => fx(s, o, 'up', 'auto', 1100 + i * 260));
  });

  // evidence chain graphic
  const DX = 9.0, DY = 3.75, DW = 3.73, DH = 3.3;
  const doc = card(s, DX, DY, DW, DH, { fill: 'F7F7F5', tr: 0, line: 'FFFFFF', lineTr: 100, r: 0.14 });
  const dt = T(s, 'Nachtragsmeldung', { x: DX + 0.25, y: DY + 0.2, w: 2.6, h: 0.35, fontSize: 16, bold: true, color: '16181D' });
  const fields = [['Location', 'Pile 7', false], ['Found', 'Rock from 4 m', false], ['Expected', 'Sand & gravel to 9 m', false], ['Drilling log', '?  BauBuddy asks', true]];
  const srcs = [['mic_w.png', 'Voice note'], ['camera_w.png', 'Photo'], ['filetext_w.png', 'Gutachten p. 14'], null];
  const chainObjs = [];
  fields.forEach(([l, v, gap], i) => {
    const fy = DY + 0.72 + i * 0.63;
    const fb = nm('field'); s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: DX + 0.2, y: fy, w: DW - 0.4, h: 0.53, rectRadius: 0.08, objectName: fb, fill: { color: gap ? 'FFF1F3' : 'EEF0F3' }, line: gap ? { color: K.bad, width: 1, dashType: 'dash' } : { type: 'none' } });
    const fl = T(s, l, { x: DX + 0.33, y: fy + 0.05, w: 2.0, h: 0.2, fontSize: 9.5, color: '5D6575' });
    const fv = T(s, v, { x: DX + 0.33, y: fy + 0.24, w: DW - 0.6, h: 0.26, fontSize: 13, bold: true, color: gap ? 'D93848' : '16181D' });
    chainObjs.push([fb, fl, fv]);
    if (srcs[i]) {
      const [ic, t] = srcs[i];
      const sx = 6.47, sw = 2.0, cy = fy + 0.265;
      const sc = chip(s, '', sx, cy - 0.22, sw, { h: 0.44, fs: 12 });
      const si = img(s, ic, sx + 0.14, cy - 0.12, 0.24, 0.24);
      const st2 = T(s, t, { x: sx + 0.45, y: cy - 0.22, w: sw - 0.5, h: 0.44, fontSize: 12, bold: true, valign: 'middle' });
      const ln = nm('link'); s.addShape(pres.shapes.LINE, { x: sx + sw, y: cy, w: DX + 0.2 - (sx + sw), h: 0, objectName: ln, line: { color: K.acc, width: 1.75, endArrowType: 'oval' } });
      chainObjs[i].push(sc, si, st2, ln);
    }
  });
  [bs1, bs2, bo1, bo2].forEach(o => fx(s, o, 'fade', 'auto', 900));
  [doc, dt].forEach(o => fx(s, o, 'up', 'auto', 2000));
  chainObjs.forEach((g, i) => g.forEach(o => fx(s, o, 'fade', 'auto', 2300 + i * 300)));
  s.addNotes(`[0:30–0:43] Christo.
"BauBuddy closes that gap. Speak or snap a photo on site, and BauBuddy drafts the formal notice. Every field shows its source. No source? It asks instead of guessing. And nothing leaves without your click."`);
}

// =====================================================================
// 5 · TEAM
// =====================================================================
{
  const s = newSlide('BB_CONTENT', 'Pitch (3 min)');
  glow(s, 3.67, 1.6, 6.0);
  brandSmall(s);
  s.addText([{ text: 'Team Apex', options: { color: K.acc } }], { placeholder: 'title' });
  const team = [['CT', 'Christo Teresof'], ['JM', 'Jeet Manjrekar'], ['KK', 'Karim Keraani'], ['AS', 'Aaditya Salunke']];
  const W = 2.8, G = 0.3, Y = 2.85, H = 3.3;
  team.forEach(([ini, name], i) => {
    const x = 0.6 + i * (W + G);
    const cn = card(s, x, Y, W, H);
    const ring = nm('ring');
    s.addShape(pres.shapes.OVAL, { x: x + (W - 1.5) / 2, y: Y + 0.5, w: 1.5, h: 1.5, objectName: ring, fill: { color: K.acc, transparency: 86 }, line: { color: K.acc, width: 2 } });
    const ii = T(s, ini, { x: x + (W - 1.5) / 2, y: Y + 0.5, w: 1.5, h: 1.5, fontSize: 34, bold: true, color: K.acc, align: 'center', valign: 'middle' });
    const n = T(s, name, { x: x + 0.15, y: Y + 2.35, w: W - 0.3, h: 0.5, fontSize: 20, bold: true, align: 'center', valign: 'middle' });
    [cn, ring, ii, n].forEach(o => fx(s, o, 'up', 'auto', 150 + i * 170));
  });
  s.addNotes(`[0:43–0:50] Christo. [name] is already at the laptop.
"We're Team Apex: Christo, Jeet, Karim and Aaditya. [name], show them."`);
}

// =====================================================================
// 6 · LIVE DEMO
// =====================================================================
{
  const s = newSlide('BB_CONTENT', 'Pitch (3 min)');
  glow(s, -1.6, 0.6, 6.5);
  glow(s, 0.25, 1.23, 1.6, 'glow_red.png');
  brandSmall(s);
  const dot = nm('live'); s.addShape(pres.shapes.OVAL, { x: 0.6, y: 1.83, w: 0.42, h: 0.42, objectName: dot, fill: { color: K.bad }, line: { type: 'none' } });
  const lv = T(s, 'LIVE', { x: 1.2, y: 1.66, w: 4, h: 0.76, fontSize: 44, bold: true, color: K.bad, charSpacing: 5, valign: 'middle' });
  const steps = [['quote.png', 'Every value has a source'], ['question.png', 'Gaps become questions'], ['click.png', 'You make the last click']];
  const W = 3.83, G = 0.3;
  steps.forEach(([ic, h], i) => {
    const x = 0.6 + i * (W + G), y = 3.3;
    const c = card(s, x, y, W, 2.6);
    const d = iconDisc(s, ic, x + 0.35, y + 0.4, 0.95);
    const th = T(s, h, { x: x + 0.35, y: y + 1.55, w: W - 0.7, h: 0.8, fontSize: 22, bold: true, valign: 'middle' });
    [c, ...d, th].forEach(o => fx(s, o, 'up', 'auto', 400 + i * 220));
  });
  fx(s, dot, 'zoom', 'auto', 0); fx(s, lv, 'fade', 'auto', 100);
  s.addNotes(`[0:50–0:55] [name]: "Three things to watch: the source, the question, the click." → switch to the app.
DEMO 0:55–2:25
0:55 Speak "Pfahl 7, ab 4 Meter Fels, Bohrgerät kommt kaum runter" + 2 photos. "I talk like I would on site, in German. BauBuddy spots a possible Nachtrag and pulls in page 14 of the client's soil report."
1:18 Answer the follow-up, tap a source chip. "One detail is missing, so it asks me. It doesn't invent. And every value: one tap, and there's the exact quote."
1:40 Mark as checked → Word. "I check it, I decide. Word export with the photos and an evidence appendix, for the Nachtragsmanager. Same day, instead of never."
1:55 Plan vs actual → Draft Behinderungsanzeige. "It also watches the schedule: piles three days behind, frost before the pour. One click drafts the Behinderungsanzeige. We see the delay on day one, not in month two."
2:20 Back to the deck → next slide (value).
Running late at 1:55: skip plan vs actual. Mic or network fails: type it, or press ▶ Autopilot.`);
}

// =====================================================================
// 7 · VALUE (after the demo)
// =====================================================================
{
  const s = newSlide('BB_CONTENT', 'Pitch (3 min)');
  glow(s, 1.0, 2.2, 6.0);
  brandSmall(s);
  const k = kicker(s, 'Per 10 M€ contract');
  s.addText([{ text: 'What BauBuddy ' }, { text: 'brings back', options: { color: K.acc } }], { placeholder: 'title' });

  // chart card
  const cc = card(s, 0.6, 2.5, 7.4, 4.25);
  const ct = T(s, 'Recovered, if this share of Nachträge was lost for missing proof', { x: 0.9, y: 2.72, w: 6.8, h: 0.35, fontSize: 15, bold: true, color: K.mut });
  const chartName = nm('chart');
  s.addChart(pres.charts.BAR, [{ name: 'Recovered', labels: ['5 % lost', '10 % lost', '20 % lost'], values: [30, 60, 120] }], {
    x: 0.85, y: 3.15, w: 6.9, h: 3.45, objectName: chartName,
    barDir: 'col', barGapWidthPct: 55, chartColors: ['FF7A00'],
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFormatCode: '0" k€"', dataLabelColor: 'F2F4F8', dataLabelFontSize: 20, dataLabelFontBold: true, dataLabelFontFace: '+mn-lt',
    catAxisLabelColor: '9AA3B3', catAxisLabelFontSize: 13, catAxisLabelFontFace: '+mn-lt', catAxisLineShow: true, catAxisLineColor: '3A3F4B',
    valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: 140, valGridLine: { style: 'none' }, catGridLine: { style: 'none' },
    showLegend: false, showTitle: false,
  });

  // stat tiles
  const tiles = [
    ['6 %', 'of building cost is Nachträge on new builds'],
    ['30 %', 'of a manager\'s week goes to reporting'],
    ['48 %', 'of rework comes from poor data & communication'],
  ];
  tiles.forEach(([v, t], i) => {
    const y = 2.5 + i * 1.45;
    const c = card(s, 8.3, y, 4.43, 1.25);
    const tv = T(s, v, { x: 8.55, y, w: 1.55, h: 1.25, fontSize: 34, bold: true, color: K.acc, valign: 'middle' });
    const tt = T(s, t, { x: 9.9, y, w: 2.65, h: 1.25, fontSize: 14, valign: 'middle' });
    [c, tv, tt].forEach(o => fx(s, o, 'up', 'auto', 900 + i * 200));
  });
  const src = T(s, 'Scenario: 10 M€ × 6 % Nachträge × share unfiled (assumption, measured in the pilot). Sources: Rechnungshof BW, Denkschrift 2020 · IW-Kurzbericht 94/2025 · FMI/PlanGrid, Construction Disconnected 2018 (US).',
    { x: 0.6, y: 6.85, w: 12.13, h: 0.35, fontSize: 10, color: K.mut });
  fx(s, k, 'fade', 'auto', 0);
  [cc, ct].forEach(o => fx(s, o, 'up', 'auto', 150));
  fx(s, chartName, 'wipeUp', 'auto', 400);
  fx(s, src, 'fade', 'auto', 1600);
  s.addNotes(`[2:25–2:45] Christo, back from the demo.
"What's it worth? On new builds, about six percent of building cost runs through Nachträge, according to the state audit office. If just ten percent of those get lost for missing proof, that's sixty thousand euros per ten million of contract. And managers spend about thirty percent of their week on reporting."
If asked: the 5/10/20 % unfiled share is an assumption, not a measurement. The pilot measures the real number.
Sources: Rechnungshof Baden-Württemberg, Denkschrift 2020, Beitrag 17 (Nachträge 6 % Neubau, 17 % Sanierung). IW-Kurzbericht 94/2025 (Führungskräfte ~30 % Arbeitszeit für Berichts- und Dokumentationspflichten). FMI/PlanGrid "Construction Disconnected" 2018, US survey of 599 leaders (48 % of rework from miscommunication and poor project data).`);
}

// =====================================================================
// 8 · CLOSING / Q&A
// =====================================================================
{
  const s = newSlide('BB_DARK', 'Pitch (3 min)');
  glow(s, 3.67, -1.7, 6.0);
  img(s, 'logo.png', 6.12, 0.7, 1.1, 1.1, '!!logo');
  T(s, 'BauBuddy', { x: 0, y: 1.87, w: 13.333, h: 0.5, fontSize: 22, bold: true, align: 'center', valign: 'middle', objectName: '!!brand' });
  const q = T(s, 'Questions?', { x: 0, y: 2.6, w: 13.333, h: 1.3, fontSize: 72, bold: true, align: 'center', valign: 'middle' });
  const tg = T(s, [{ text: 'Evidence in. Notices out. ' }, { text: 'On time.', options: { color: K.acc } }], { x: 0, y: 4.0, w: 13.333, h: 0.55, fontSize: 26, align: 'center', color: K.ink });
  const chips = [['filecheck.png', 'Every value sourced'], ['click.png', 'Your click sends'], ['scale.png', 'No legal advice']];
  const W = 3.3, G = 0.3, x0 = (13.333 - (3 * W + 2 * G)) / 2;
  chips.forEach(([ic, t], i) => {
    const x = x0 + i * (W + G), y = 5.05;
    const c = card(s, x, y, W, 0.7, { r: 0.35, tr: 30 });
    const im = img(s, ic, x + 0.28, y + 0.17, 0.36, 0.36);
    const tx = T(s, t, { x: x + 0.78, y, w: W - 0.95, h: 0.7, fontSize: 16, bold: true, valign: 'middle' });
    [c, im, tx].forEach(o => fx(s, o, 'up', 'auto', 700 + i * 160));
  });
  const ac = chip(s, 'Our ask: one live pilot site', 4.42, 6.1, 4.5, { h: 0.6, fs: 17, bold: true, fill: K.acc, tr: 84, line: K.acc, lineTr: 45 });
  fx(s, q, 'zoom', 'auto', 0); fx(s, tg, 'up', 'auto', 350); fx(s, ac, 'up', 'auto', 1300);
  s.addNotes(`[2:45–3:00] Christo. Stays up during the whole Q&A.
"Our ask: one live pilot site, so we measure the real number together. Thank you. Questions?"
Backup slides: 9 How it works · 10 Trust · 11 Beyond notices · 12 Measured · 13 Roadmap & ask`);
}

// =====================================================================
// BACKUP SLIDES
// =====================================================================
function backupHeader(s, kick, title) {
  brandSmall(s);
  const n = T(s, 'Backup', { x: 11.2, y: 0.47, w: 1.53, h: 0.34, fontSize: 12, color: K.mut, align: 'right', valign: 'middle' });
  const k = kicker(s, kick);
  s.addText(title, { placeholder: 'title' });
  fx(s, k, 'fade', 'auto', 0);
  return n;
}

// 8 · HOW IT WORKS
{
  const s = newSlide('BB_CONTENT', 'Backup (Q&A)');
  glow(s, 8.5, 3.6, 6.0);
  backupHeader(s, 'How it works', 'From a voice note to a checked document');
  const nodes = [
    ['mic.png', 'Capture', 'Voice, chat, photo, email'],
    ['layers.png', 'Evidence IDs', 'Each source gets an ID'],
    ['searchcheck.png', 'Extract + gate', 'Only with ID + confidence'],
    ['question.png', 'Follow-up', 'Gaps become questions'],
    ['filedown.png', 'Review + export', 'Checked → Word export'],
  ];
  const W = 2.3, G = 0.15, y = 2.7;
  nodes.forEach(([ic, h, b], i) => {
    const x = 0.6 + i * (W + G);
    const c = card(s, x, y, W, 2.55);
    const d = iconDisc(s, ic, x + 0.25, y + 0.25, 0.66);
    const th = T(s, h, { x: x + 0.25, y: y + 1.05, w: W - 0.45, h: 0.38, fontSize: 17, bold: true });
    const tb = T(s, b, { x: x + 0.25, y: y + 1.45, w: W - 0.45, h: 1.0, fontSize: 12.5, color: K.mut });
    [c, ...d, th, tb].forEach(o => fx(s, o, 'up', 'auto', 200 + i * 170));
  });
  // example field mock
  const fy = 5.65;
  const fc = card(s, 0.6, fy, 7.6, 1.25, { r: 0.16 });
  const f1 = T(s, 'Ort / Bauteil', { x: 0.85, y: fy + 0.16, w: 3, h: 0.28, fontSize: 12, color: K.mut });
  const f2 = T(s, 'Bohrpfahl 7, Achse 10', { x: 0.85, y: fy + 0.45, w: 3.4, h: 0.4, fontSize: 18, bold: true });
  const f3 = chip(s, '      Sprachnotiz 11:32 · conf 90 %', 4.3, fy + 0.42, 3.0, { fs: 12, h: 0.4 });
  const f4 = img(s, 'mic_w.png', 4.42, fy + 0.5, 0.24, 0.24);
  const ex = T(s, [
    { text: 'What the site manager sees', options: { bold: true, color: K.ink, breakLine: true } },
    { text: 'Tap the chip, see the exact quote.', options: { color: K.mut } },
  ], { x: 8.5, y: fy, w: 4.23, h: 1.25, fontSize: 13.5, valign: 'middle' });
  [fc, f1, f2, f3, f4, ex].forEach(o => fx(s, o, 'fade', 'auto', 1200));
  s.addNotes(`Q: "What happens under the hood?"
FastAPI backend, our own LLM package for extraction with evidence-ID and confidence gates, a rule-based fallback under the same field rules when no LLM key is available. Vanilla JS frontend, runs on a laptop and phone browser.`);
}

// 9 · TRUST
{
  const s = newSlide('BB_CONTENT', 'Backup (Q&A)');
  glow(s, -1.5, 3.5, 6.0);
  backupHeader(s, 'Trust by design', 'The site manager stays in charge');
  const items = [
    ['filecheck.png', 'Evidence or empty', 'No source, no value.'],
    ['lock.png', 'Your edits win', 'Locked. AI only proposes.'],
    ['usercheck.png', 'Human-only status', 'Status changes only by click.'],
    ['eyeoff.png', 'Personal data masked', 'Masked before any LLM call.'],
    ['scale.png', 'No legal advice', 'Completeness check only.'],
    ['server.png', 'Works without a key', 'Rule-based fallback.'],
  ];
  const W = 3.83, H = 1.95, G = 0.3;
  items.forEach(([ic, h, b], i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = 0.6 + col * (W + G), y = 2.6 + row * (H + 0.25);
    const c = card(s, x, y, W, H);
    const d = iconDisc(s, ic, x + 0.28, y + 0.3, 0.66);
    const th = T(s, h, { x: x + 1.12, y: y + 0.38, w: W - 1.35, h: 0.5, fontSize: 18, bold: true, valign: 'middle' });
    const tb = T(s, b, { x: x + 0.28, y: y + 1.07, w: W - 0.56, h: 0.8, fontSize: 13.5, color: K.mut });
    [c, ...d, th, tb].forEach(o => fx(s, o, 'up', 'auto', 200 + i * 130));
  });
  s.addNotes(`Q: "Does the AI make things up?" → Evidence or empty: no source ID, no value, it asks.
Q: "Legal?" → No legal advice. We check formal completeness against the template; the site manager and the Nachtragsmanager decide. Footer: "Entwurf mit KI-Unterstützung erstellt, geprüft von …".
Q: "Data protection?" → PII masked before any LLM call. Voice: today Chrome speech recognition; local Whisper is the planned default, cloud speech only opt-in (audio can't be masked).`);
}

// 10 · BEYOND NOTICES
{
  const s = newSlide('BB_CONTENT', 'Backup (Q&A)');
  glow(s, 3.7, 3.2, 6.0);
  backupHeader(s, 'Beyond notices', 'Early warnings instead of a post-mortem');
  const feats = [
    ['snow.png', 'Plan vs actual', 'Schedule + weather warnings.', 'Ends in a draft Behinderungsanzeige'],
    ['filetext.png', 'Daily report', 'From photos, notes and weather.', 'Ends in a Word document'],
    ['pin.png', 'Site twin', 'Photos on the site plan by GPS.', 'Ends in a map of the problems'],
  ];
  const W = 3.83, G = 0.3, y = 2.65;
  feats.forEach(([ic, h, b, e], i) => {
    const x = 0.6 + i * (W + G);
    const c = card(s, x, y, W, 4.1, { r: 0.2 });
    const d = iconDisc(s, ic, x + 0.3, y + 0.32, 0.9);
    const th = T(s, h, { x: x + 0.3, y: y + 1.45, w: W - 0.6, h: 0.42, fontSize: 20, bold: true });
    const tb = T(s, b, { x: x + 0.3, y: y + 1.95, w: W - 0.6, h: 1.35, fontSize: 14, color: K.mut });
    const te = chip(s, e, x + 0.3, y + 3.4, W - 0.6, { fs: 12.5, h: 0.42, fill: K.acc, tr: 85, line: K.acc, lineTr: 60, color: K.ink, bold: true });
    [c, ...d, th, tb, te].forEach(o => fx(s, o, 'up', 'auto', 200 + i * 200));
  });
  s.addNotes(`Q: "What else does it do?"
Plan vs actual against the Bauzeitenplan with weather (Open-Meteo): frost warning for the pile cap pour. Daily report (Bautagesbericht) from photos, notes, schedule and weather. Summaries of minutes and emails with open items. Site twin with geotagged photos and object detection.`);
}

// 11 · MEASURED
{
  const s = newSlide('BB_CONTENT', 'Backup (Q&A)');
  glow(s, 8.0, -1.0, 6.0);
  backupHeader(s, 'Measured, not claimed', 'Every pipeline stage is timed on the prototype');
  const stats = [
    ['timer.png', '[MEASURED · s]', 'Voice note → draft', 'end to end, p50'],
    ['filedown.png', '[MEASURED · s]', 'Draft → Word / PDF', 'export, p50'],
    ['gauge.png', '[MEASURED · €]', 'Cost per document', 'LLM tokens at list price'],
    ['listchecks.png', '[MEASURED · %]', 'Extraction accuracy', 'on our labelled eval set'],
  ];
  const W = 2.8, G = 0.3, y = 2.7;
  stats.forEach(([ic, v, h, b], i) => {
    const x = 0.6 + i * (W + G);
    const c = card(s, x, y, W, 3.1);
    const d = iconDisc(s, ic, x + 0.28, y + 0.3, 0.62);
    const tv = T(s, v, { x: x + 0.28, y: y + 1.15, w: W - 0.5, h: 0.75, fontSize: 19, bold: true, color: K.acc, valign: 'middle' });
    const th = T(s, h, { x: x + 0.28, y: y + 1.98, w: W - 0.5, h: 0.4, fontSize: 17, bold: true });
    const tb = T(s, b, { x: x + 0.28, y: y + 2.4, w: W - 0.5, h: 0.4, fontSize: 13.5, color: K.mut });
    [c, ...d, tv, th, tb].forEach(o => fx(s, o, 'up', 'auto', 200 + i * 160));
  });
  const src = T(s, 'Measured on the prototype. No estimates.', { x: 0.6, y: 6.2, w: 12.1, h: 0.4, fontSize: 13, color: K.mut });
  fx(s, src, 'fade', 'auto', 1000);
  s.addNotes(`Q: "How fast is it? What does it cost?"
Fill the four values from /api/metrics/summary after the 21:00 freeze (live LLM mode, not rules mode). Never estimate. If a value is missing, say "we time every stage; this one we haven't measured in live mode yet" and show the Metrics tab.`);
}

// 12 · ROADMAP & ASK
{
  const s = newSlide('BB_CONTENT', 'Backup (Q&A)');
  glow(s, -1.2, -1.2, 6.0);
  backupHeader(s, 'Roadmap & ask', 'What comes next, honestly');
  const next = [
    ['mic.png', 'Local speech-to-text', 'Whisper on the laptop. Cloud opt-in.'],
    ['mail.png', 'Outlook import', 'Emails and meetings flow in.'],
    ['filedown.png', 'PDF file export', 'Same layout as Word.'],
    ['users.png', 'Crew replanner', 'Machine down? Suggest where the crew helps.'],
  ];
  next.forEach(([ic, h, b], i) => {
    const y = 2.6 + i * 1.08;
    const d = iconDisc(s, ic, 0.6, y, 0.62);
    const th = T(s, h, { x: 1.42, y: y - 0.03, w: 5.6, h: 0.36, fontSize: 17, bold: true });
    const tb = T(s, b, { x: 1.42, y: y + 0.34, w: 5.6, h: 0.62, fontSize: 13.5, color: K.mut });
    [...d, th, tb].forEach(o => fx(s, o, 'up', 'auto', 200 + i * 150));
  });
  const ac = card(s, 7.6, 2.6, 5.13, 3.0, { fill: K.acc, tr: 88, line: K.acc, lineTr: 50 });
  const ai = iconDisc(s, 'handshake.png', 7.9, 2.9, 0.75);
  const at = T(s, 'What we ask from you', { x: 8.85, y: 2.95, w: 3.7, h: 0.65, fontSize: 20, bold: true, valign: 'middle' });
  const al = T(s, [
    { text: 'One live pilot site', options: { bullet: { indent: 18 }, breakLine: true } },
    { text: 'Your Word templates', options: { bullet: { indent: 18 }, breakLine: true } },
    { text: '30 min with a Nachtragsmanager', options: { bullet: { indent: 18 } } },
  ], { x: 7.95, y: 3.85, w: 4.5, h: 1.5, fontSize: 16, color: K.ink, paraSpaceAfter: 10 });
  [ac, ...ai, at, al].forEach(o => fx(s, o, 'up', 'auto', 900));
  s.addNotes(`Q: "What's next?" → Pilot on a live site, measured by Nachträge filed and writing time saved.
Check before the pitch: if any of these landed today (W1 PDF/Outlook, W2 Whisper, W4 replanner), move it from this slide into the demo or slide 10.`);
}

(async () => {
  const raw = path.join(OUTDIR, 'BauBuddy_Pitch.raw.pptx');
  await pres.writeFile({ fileName: raw });
  fs.writeFileSync(path.join(__dirname, 'anim.json'), JSON.stringify(anim, null, 1));
  const { applyTheme } = require('./apply_theme.js');
  await applyTheme(raw, THEME);
  console.log('written', raw, 'slides', slideNo);
})();
