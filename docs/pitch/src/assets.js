// Generates raster assets (no app screenshots: the deck complements the demo) for the deck: background, glow, logo, icons, rounded screenshots.
const sharp = require('sharp');
const fs = require('fs');
const path = require('path');
const React = require('react');
const RDS = require('react-dom/server');
const L = require('react-icons/lu');

const BRAND = path.join(__dirname, 'brand'); // logo SVGs copied from frontend/img (w3_frontend)
const OUT = path.join(__dirname, 'assets');
fs.mkdirSync(OUT, { recursive: true });

async function bg() {
  const W = 2666, H = 1500;
  let grid = '';
  for (let x = 0; x <= W; x += 66) grid += `<line x1="${x}" y1="0" x2="${x}" y2="${H}" stroke="#ffffff" stroke-opacity="${x % 330 === 0 ? 0.045 : 0.018}" stroke-width="2"/>`;
  for (let y = 0; y <= H; y += 66) grid += `<line x1="0" y1="${y}" x2="${W}" y2="${y}" stroke="#ffffff" stroke-opacity="${y % 330 === 0 ? 0.045 : 0.018}" stroke-width="2"/>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
  <defs><radialGradient id="g" cx="15%" cy="0%" r="110%"><stop offset="0" stop-color="#2a2f3a"/><stop offset=".55" stop-color="#14161c"/><stop offset="1" stop-color="#0b0c10"/></radialGradient>
  <radialGradient id="v" cx="50%" cy="50%" r="75%"><stop offset=".6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".55"/></radialGradient>
  <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity=".25"/></linearGradient>
  <mask id="m"><rect width="${W}" height="${H}" fill="url(#fade)"/></mask></defs>
  <rect width="${W}" height="${H}" fill="url(#g)"/><g mask="url(#m)">${grid}</g><rect width="${W}" height="${H}" fill="url(#v)"/></svg>`;
  await sharp(Buffer.from(svg)).jpeg({ quality: 92 }).toFile(OUT + '/bg.jpg');
}

async function glow(name, color, op) {
  const S = 1200;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${S}" height="${S}"><defs><radialGradient id="r"><stop offset="0" stop-color="${color}" stop-opacity="${op}"/><stop offset=".45" stop-color="${color}" stop-opacity="${op * 0.35}"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></radialGradient></defs><circle cx="${S / 2}" cy="${S / 2}" r="${S / 2}" fill="url(#r)"/></svg>`;
  await sharp(Buffer.from(svg)).png().toFile(`${OUT}/${name}.png`);
}

async function logo() {
  const svg = fs.readFileSync(path.join(BRAND, 'logo.svg'));
  await sharp(svg, { density: 1600 }).resize(1024, 1024).png().toFile(OUT + '/logo.png');
  const wm = fs.readFileSync(path.join(BRAND, 'logo-wordmark-dark.svg'));
  await sharp(wm, { density: 1200 }).png().toFile(OUT + '/wordmark.png');
}

async function icon(name, color, file) {
  const C = L[name];
  if (!C) throw new Error('missing icon ' + name);
  const svg = RDS.renderToStaticMarkup(React.createElement(C, { size: 256, color, strokeWidth: 1.75 }));
  await sharp(Buffer.from(svg), { density: 600 }).resize(256, 256).png().toFile(`${OUT}/${file}.png`);
}

async function rounded(src, dst, crop, radius) {
  let img = sharp(src);
  if (crop) img = img.extract(crop);
  const buf = await img.png().toBuffer();
  const { width, height } = await sharp(buf).metadata();
  const mask = Buffer.from(`<svg width="${width}" height="${height}"><rect width="${width}" height="${height}" rx="${radius}" ry="${radius}"/></svg>`);
  await sharp(buf).composite([{ input: mask, blend: 'dest-in' }]).png().toFile(dst);
}

(async () => {
  await bg();
  await glow('glow', '#ff7a00', 0.55);
  await glow('glow_red', '#ff3d5a', 0.5);
  await logo();
  const icons = {
    LuMic: 'mic', LuCamera: 'camera', LuFileCheck: 'filecheck', LuShieldCheck: 'shield', LuLock: 'lock', LuEyeOff: 'eyeoff',
    LuUserCheck: 'usercheck', LuScale: 'scale', LuFileText: 'filetext', LuMail: 'mail', LuCalendar: 'calendar',
    LuTriangleAlert: 'alert', LuMap: 'map', LuHardHat: 'hardhat', LuBuilding2: 'building', LuMessageSquare: 'msg',
    LuQuote: 'quote', LuSend: 'send', LuCheck: 'check', LuSparkles: 'sparkles', LuFileDown: 'filedown',
    LuSnowflake: 'snow', LuGauge: 'gauge', LuTimer: 'timer', LuDrill: 'drill', LuListChecks: 'listchecks',
    LuMessageCircleQuestion: 'question', LuMapPin: 'pin', LuServer: 'server', LuMousePointerClick: 'click',
    LuHandshake: 'handshake', LuRocket: 'rocket', LuLink: 'link', LuUnlink: 'unlink', LuLayers: 'layers', LuPlay: 'play',
    LuSearchCheck: 'searchcheck', LuUsers: 'users', LuClock: 'clock', LuBriefcase: 'briefcase',
  };
  for (const [n, f] of Object.entries(icons)) {
    await icon(n, '#ff7a00', f);
    await icon(n, '#f2f4f8', f + '_w');
    await icon(n, '#1b1b1b', f + '_k');
  }
  await icon('LuTriangleAlert', '#ff5a6e', 'alert_r');
  await icon('LuUnlink', '#ff5a6e', 'unlink_r');
  console.log('assets ok');
})().catch(e => { console.error(e); process.exit(1); });
