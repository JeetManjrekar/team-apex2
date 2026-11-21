// Screenshot scenes.html at given moments: node preview.js arch:25 close:10 …  → raw/prev_<scene>_<t>.png
const { chromium } = require('playwright-core');
const { pathToFileURL } = require('url');
const path = require('path');
(async () => {
  const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  const url = pathToFileURL(path.join(__dirname, 'scenes.html')).href;
  for (const a of process.argv.slice(2)) {
    const [s, t] = a.split(':');
    await p.goto(`${url}?scene=${s}&t=${t}`);
    await p.screenshot({ path: path.join(__dirname, 'raw', `prev_${s}_${t}.png`) });
  }
  await b.close();
})();
