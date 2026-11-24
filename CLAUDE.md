# AIArena4BW

Lokale Web-App, die KI-Modelle bei SAP-BW/4HANA-Modellierungsaufgaben vergleicht: eigene
Agent-Schleife, BW-Zugriff über einen MCP-Server, Prüfung durch ein anderes Modell.

Persönliche Anweisungen, die nicht ins Repository gehören, stehen in `CLAUDE.local.md` (nicht
versioniert). Ändern sich Befehle, wird diese Datei im selben Schritt angepasst.

## Einrichten

```bash
uv sync                               # Python-Abhängigkeiten (Python ≥ 3.12)
npm --prefix frontend install         # nur für die Entwicklung der Oberfläche
```

## Starten

```bash
uv run aiarena4bw                     # App: http://127.0.0.1:8321 (liefert die gebaute Oberfläche aus)
uv run aiarena4bw serve --reload      # Backend mit automatischem Neuladen
npm --prefix frontend run dev         # Oberfläche im Entwicklungsmodus (Vite, leitet /api an :8321)
uv run aiarena4bw demo                # Beispiel-Datenbank erzeugen und App damit starten (ohne BW)
uv run aiarena4bw --help              # Unterbefehle: run, cancel, list, …
```

## Testen

```bash
uv run pytest                         # Backend; ohne Netz, ohne BW, ohne Schlüssel
uv run pytest tests/test_runner.py -k timeout      # einzelner Test
uv run ruff check . && uv run ruff format --check .

npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run test        # Vitest
npm --prefix frontend run build       # baut nach src/aiarena4bw/web/
npm --prefix frontend run e2e         # Playwright (installiertes Chrome) gegen Nachbauten
node frontend/e2e/screenshots.mjs     # README-Bilder aus dem Vorführmodus (vorher: aiarena4bw demo)

uv run aiarena4bw run --tasks … --models …   # Echtlauf: kostet Geld, legt BW-Objekte an
```

Vor jedem Commit müssen `pytest`, `ruff`, `typecheck`, `lint`, `test` und `build` grün sein. Die
gebaute Oberfläche unter `src/aiarena4bw/web/` wird mit eingecheckt; die CI prüft, dass sie zum
Quelltext passt.

## Regeln

- **Geheimnisse** liegen nur im Schlüsselbund. Nie ausgeben, protokollieren, in Dateien, Tests oder
  Commits schreiben. In MCP-Definitionen stehen Platzhalter (`${BW_PASSWORD}`, `${SECRET:name}`).
- **Tests** laufen ohne Netz, ohne BW-System und ohne Schlüssel gegen die Nachbauten in
  `tests/fakes/`. Echtläufe kosten Geld und legen BW-Objekte an; nur gegen Test- und Demosysteme.
- **Privat, nicht im Repository:** `data/` (Datenbank, Protokolle) und `local/`.
- **Sprache:** Oberfläche, Meldungen, Dokumentation und Kommentare deutsch mit Umlauten und ß.
  Bezeichner in Code, Datenbank und API englisch. Sichtbare Texte der Oberfläche stehen in der
  Sprachdatei (`frontend/src/texts/`), nicht im Komponenten-Code.
- **Plattform-APIs** (Anthropic, OpenRouter, SAP AI Core, OpenAI-kompatibel) und das MCP-SDK vor der
  Arbeit an Adaptern in der aktuellen Dokumentation nachlesen, nicht aus dem Gedächtnis umsetzen.
- **Gestaltung:** `PRODUCT.md` (Nutzer, Produktwahrheit) und `DESIGN.md` (Regeln).
- **Datenbank:** Schemaänderungen nur als neue Migration in `db.MIGRATIONS` anhängen; bestehende
  Migrationen nie ändern. Die App sichert die Datei vor jeder Umstellung.
- **Ehrliche Zahlen:** Ein fehlender Preis ist „kein Preis“, nie 0 $. Läufe, die an der Umgebung
  scheiterten, zählen nicht. Einträge mit anderer Denkstufe, anderem MCP-Server oder anderem Agenten
  werden nie gemittelt.
