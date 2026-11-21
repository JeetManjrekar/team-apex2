// Renders the time-driven scenes in scenes.html to frame-exact 30 fps MP4s (raw/scene_<name>.mp4).
// Usage: node scenes.js [arch] [close]   (default: both)
const { chromium } = require('playwright-core');
const { spawn } = require('child_process');
const path = require('path'), fs = require('fs');
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const FPS = 30;
const which = process.argv.slice(2).length ? process.argv.slice(2) : ['arch', 'close'];

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--force-device-scale-factor=1', '--hide-scrollbars'] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto('file:///' + path.join(__dirname, 'scenes.html').replace(/\\/g, '/'));
  fs.mkdirSync(path.join(__dirname, 'raw'), { recursive: true });
  for (const name of which) {
    const dur = await page.evaluate(n => setScene(n), name);
    const out = path.join(__dirname, 'raw', `scene_${name}.mp4`);
    // frames are piped straight into ffmpeg as JPEGs
    const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p', out], { stdio: ['pipe', 'inherit', 'inherit'] });
    const n = Math.round(dur * FPS);
    for (let i = 0; i < n; i++) {
      await page.evaluate(t => render(t), i / FPS);
      const buf = await page.screenshot({ type: 'jpeg', quality: 95 });
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    }
    ff.stdin.end();
    await new Promise(r => ff.on('close', r));
    console.log(`${name}: ${n} frames → ${out}`);
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
