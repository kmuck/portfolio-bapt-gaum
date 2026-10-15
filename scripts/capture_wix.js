// Captures d'écran et styles calculés du site Wix d'origine, pour reproduire son design.
// Sorties : import/captures/<page>-<largeur>.jpg et import/captures/styles.json
const { chromium } = require('playwright');
const fs = require('fs');

const BASE = 'https://baptistegmtc.wixsite.com/website';
const PAGES = ['', 'projets', 'ecrits-recherches', 'a-propos-de-moi', 'tisser-la-ville', 'silo-bernouilli', 'bibliotheque'];
const OUT = 'import/captures';

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const styles = {};
  for (const width of [1280, 390]) {
    for (const slug of PAGES) {
      const name = (slug || 'accueil') + '-' + width;
      const page = await browser.newPage({ viewport: { width, height: width > 500 ? 800 : 844 } });
      await page.goto(`${BASE}/${slug}`, { waitUntil: 'networkidle', timeout: 90000 });
      // Fait défiler pour charger les images paresseuses
      await page.evaluate(async () => {
        for (let y = 0; y < document.body.scrollHeight; y += 600) {
          window.scrollTo(0, y);
          await new Promise(r => setTimeout(r, 120));
        }
        window.scrollTo(0, 0);
      });
      await page.waitForTimeout(1500);
      await page.screenshot({ path: `${OUT}/${name}-haut.jpg`, type: 'jpeg', quality: 75 });
      await page.screenshot({ path: `${OUT}/${name}.jpg`, type: 'jpeg', quality: 60, fullPage: true });
      if (width === 1280) {
        styles[name] = await page.evaluate(() => {
          const pick = el => {
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return {
              tag: el.tagName, id: el.id, text: (el.innerText || '').trim().slice(0, 80),
              x: Math.round(r.x), y: Math.round(r.y + window.scrollY), w: Math.round(r.width), h: Math.round(r.height),
              color: cs.color, bg: cs.backgroundColor, font: cs.fontFamily, size: cs.fontSize,
              weight: cs.fontWeight, lh: cs.lineHeight, ls: cs.letterSpacing, transform: cs.textTransform,
              align: cs.textAlign,
            };
          };
          const out = { body: pick(document.body), texts: [], blocks: [] };
          document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,a,li,button').forEach(el => {
            if ((el.innerText || '').trim() && el.getBoundingClientRect().height > 0 && out.texts.length < 120) out.texts.push(pick(el));
          });
          document.querySelectorAll('[id^="comp-"], header, footer, section').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.height > 30 && r.width > 100 && out.blocks.length < 200) {
              const b = pick(el);
              b.cls = el.className && el.className.baseVal === undefined ? String(el.className).slice(0, 80) : '';
              b.bgImage = getComputedStyle(el).backgroundImage.slice(0, 120);
              b.border = getComputedStyle(el).border;
              out.blocks.push(b);
            }
          });
          return out;
        });
      }
      console.log('ok', name);
      await page.close();
    }
  }
  fs.writeFileSync(`${OUT}/styles.json`, JSON.stringify(styles, null, 1));
  await browser.close();
})();
