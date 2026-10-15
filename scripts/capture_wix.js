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
      try {
      // Wix ne devient jamais « networkidle » (statistiques) : on attend le chargement puis un délai
      await page.goto(`${BASE}/${slug}`, { waitUntil: 'load', timeout: 90000 });
      await page.waitForTimeout(4000);
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
      } catch (e) {
        console.log('échec', name, e.message.split('\n')[0]);
      }
      await page.close();
    }
  }
  fs.writeFileSync(`${OUT}/styles.json`, JSON.stringify(styles, null, 1));

  // Diaporama de l'accueil : seules 3 diapos sont dans le HTML, on les fait défiler une à une
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(`${BASE}/`, { waitUntil: 'load', timeout: 90000 });
  await page.waitForTimeout(4000);
  const current = () => page.evaluate(() => {
    const it = document.querySelector('[data-testid="slide-show-gallery-items"] [data-testid="gallery-item-item"]');
    const info = it && it.querySelector('wow-image') && JSON.parse(it.querySelector('wow-image').dataset.imageInfo);
    const a = it && it.querySelector('a');
    const counter = document.querySelector('[data-testid="gallery-counter"]');
    return { titre: it ? it.innerText.trim() : '', lien: a ? a.href : '', uri: info ? info.imageData.uri : '',
             w: info ? info.imageData.width : 0, h: info ? info.imageData.height : 0, compteur: counter ? counter.innerText : '' };
  });
  const first = await current();
  await page.waitForTimeout(7000);
  const auto = (await current()).compteur !== first.compteur;
  const slides = [];
  for (let i = 0; i < 20; i++) {
    const c = await current();
    if (slides.some(s => s.compteur === c.compteur)) break;
    slides.push(c);
    await page.click('[data-testid="gallery-nextButton"]');
    await page.waitForTimeout(1500);
  }
  fs.writeFileSync(`${OUT}/diaporama.json`, JSON.stringify({ defilement_auto: auto, slides }, null, 1));
  console.log('diaporama', slides.length, 'auto', auto);
  await browser.close();
})();
