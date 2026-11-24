// Oberflächentest gegen eine eingerichtete Arena mit Nachbauten (tests/e2e_server.py).
import { expect, test } from '@playwright/test'

test('Rahmen: Marke, Menü und alle Seiten sind erreichbar', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('img', { name: 'AIArena4BW', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { level: 1, name: 'Übersicht' })).toBeVisible()
  // Der Nutzungshinweis steht über jeder Seite, bis er bestätigt ist; vorher startet kein Durchgang.
  const gate = page.getByRole('region', { name: 'Bevor du loslegst' })
  await expect(gate).toContainText('Nur mit Test- und Demosystemen arbeiten')
  await page.goto('/start')
  await expect(gate).toBeVisible()
  await expect(page.getByText('Bitte zuerst den Nutzungshinweis oben auf der Seite bestätigen.')).toBeVisible()
  await gate.getByRole('button', { name: 'Gelesen und verstanden' }).click()
  await expect(gate).toBeHidden()
  await page.reload()
  await expect(page.getByRole('heading', { level: 1, name: 'Durchgang starten' })).toBeVisible()
  await expect(gate).toBeHidden()
  const pages: [string, string][] = [
    ['Durchgang starten', 'Durchgang starten'],
    ['Live', 'Live'],
    ['Auswertung', 'Auswertung'],
    ['Lauf-Detail', 'Lauf-Detail'],
    ['Aufgaben', 'Aufgaben'],
    ['BW bereinigen', 'BW bereinigen'],
    ['Einstellungen', 'Einstellungen'],
  ]
  const menu = page.getByRole('navigation', { name: 'Hauptmenü' })
  for (const [link, heading] of pages) {
    await menu.getByRole('link', { name: link, exact: true }).click()
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
  }
})

test('Farbschema lässt sich umschalten und bleibt erhalten', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: 'Dunkles Schema' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})

test('Einstellungen zeigen BW-System, MCP-Server und Plattformen ohne Geheimnisse', async ({ page }) => {
  await page.goto('/einstellungen/bw')
  await expect(page.getByRole('cell', { name: 'TST' }).first()).toBeVisible()
  await page.goto('/einstellungen/mcp')
  const editor = page.locator('textarea').first()
  await expect(editor).toHaveValue(/"fake"/)
  await expect(editor).toHaveValue(/\$\{BW_PASSWORD\}/)
  // Der Nachbau ist kein coBWeb: Die App sagt, dass sie seine Schreibgrenzen nicht prüfen kann.
  await expect(page.getByText('Zu den Rechten dieses Servers.')).toBeVisible()
  await page.goto('/einstellungen/plattformen')
  await expect(page.getByText('OpenRouter').first()).toBeVisible()
  expect(await page.content()).not.toContain('bw-geheim-123')
  expect(await page.content()).not.toContain('or-key')
})

test('Durchgang in der App starten, live verfolgen, auswerten und im Detail ansehen', async ({ page }) => {
  await page.goto('/start')
  await page.getByRole('checkbox', { name: /Aufgabe „InfoArea und Merkmal“ wählen/ }).check()
  await page.getByRole('searchbox', { name: 'Modell suchen' }).fill('Claude Good')
  await page.getByRole('checkbox', { name: /Claude Good/ }).check()
  const preview = page.getByRole('complementary', { name: 'Vorschau' })
  await expect(preview).toContainText('AAA')
  await preview.getByRole('button', { name: 'Durchgang starten' }).click()

  await expect(page).toHaveURL(/\/live/)
  await expect(page.getByText('AAA', { exact: true }).first()).toBeVisible()
  // Der Runner läuft als eigener Prozess; nach dem Neuladen stimmt der Stand weiter.
  await page.reload()
  await expect(page.getByText('fertig').first()).toBeVisible({ timeout: 60_000 })
  await expect(page.getByRole('row', { name: /AAA01/ })).toContainText('bestanden')

  await page.goto('/auswertung')
  await expect(page.getByRole('heading', { level: 1, name: 'Auswertung' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Good', exact: true }).first()).toBeVisible()
  await expect(page.locator('canvas').first()).toBeVisible()
  // Ein Klick auf die Zeile markiert den Eintrag; die Filterspalte zählt die Läufe je Wert.
  const entry = page.getByRole('row', { name: /Good/ }).first()
  await entry.getByRole('cell', { name: 'Good', exact: true }).click()
  await expect(entry).toHaveClass(/is-sel/)
  await expect(page.getByRole('complementary', { name: 'Filter' })).toContainText('Anbieter')

  await page.getByRole('row', { name: /AAA01/ }).first().click()
  await expect(page).toHaveURL(/\/lauf\/\d+/)
  await expect(page.getByRole('heading', { level: 1, name: /AAA01/ })).toBeVisible()
  await expect(page.getByText('bestanden').first()).toBeVisible()
  await expect(page.getByText('1 InfoArea').first()).toBeVisible()

  await page.goto('/')
  await expect(page.getByText('Rangliste')).toBeVisible()
  await expect(page.getByRole('row', { name: /AAA/ }).first()).toContainText('1 / 1')
})

test('Früheren Durchgang als Vorlage wählen und zurücksetzen', async ({ page }) => {
  await page.goto('/start')
  const model = page.getByRole('checkbox', { name: /Claude Good/ })
  const reset = page.getByRole('button', { name: 'Zurücksetzen' })
  const template = page.getByLabel('Früherer Durchgang')
  await expect(model).not.toBeChecked()
  await expect(reset).toBeDisabled()

  // Der Durchgang AAA aus dem vorigen Test liefert Aufgabe und Modell.
  const option = template.locator('option', { hasText: /^AAA · / })
  await template.selectOption((await option.getAttribute('value')) ?? '')
  await expect(page.getByText('Angaben aus Durchgang AAA übernommen.')).toBeVisible()
  await expect(model).toBeChecked()
  await expect(page.getByRole('checkbox', { name: /Aufgabe „InfoArea und Merkmal“ wählen/ })).toBeChecked()
  await expect(page.getByRole('complementary', { name: 'Vorschau' })).toContainText('AAB')

  await page.getByRole('group', { name: 'Wiederholungen' }).getByRole('button', { name: '2', exact: true }).click()
  await expect(page.getByText('Angaben aus Durchgang AAA übernommen, seither geändert.')).toBeVisible()

  await reset.click()
  await expect(model).not.toBeChecked()
  await expect(page.getByText(/Angaben aus Durchgang AAA/)).toHaveCount(0)
  await expect(template).toHaveValue('')
  await expect(reset).toBeDisabled()
})
