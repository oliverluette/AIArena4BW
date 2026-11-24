// Bildschirmfotos für das README aus dem Vorführmodus:
//   uv run aiarena4bw demo --no-browser   (in einem zweiten Terminal)
//   node frontend/e2e/screenshots.mjs
import { chromium } from '@playwright/test'

const base = process.env.AIARENA_URL ?? 'http://127.0.0.1:8321'
const shots = [
  ['uebersicht', '/', 1100],
  ['auswertung', '/auswertung', 900],
  ['lauf-detail', '/lauf/1', 1250],
  ['live', '/live?durchgang=3', 980],
  ['durchgang-starten', '/start', 1000],
  ['einstellungen', '/einstellungen/mcp', 1000],
]

const browser = await chromium.launch({ channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, locale: 'de-DE' })
for (const [name, path, height] of shots) {
  await page.setViewportSize({ width: 1440, height })
  await page.goto(base + path)
  await page.waitForTimeout(1800)
  await page.screenshot({ path: `docs/${name}.png` })
  console.log(`docs/${name}.png`)
}
await browser.close()
