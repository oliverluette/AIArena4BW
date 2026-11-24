import { defineConfig } from '@playwright/test'

// Oberflächentest gegen eine eingerichtete Arena mit nachgebauter Plattform und nachgebautem
// MCP-Server (tests/e2e_server.py): kein Netz, kein BW-System, keine Schlüssel.
const port = 8399

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    channel: 'chrome', // nutzt das installierte Chrome; kein Browser-Download nötig
    viewport: { width: 1440, height: 900 },
    locale: 'de-DE',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `uv run python -m tests.e2e_server --port ${port}`,
    cwd: '..',
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
