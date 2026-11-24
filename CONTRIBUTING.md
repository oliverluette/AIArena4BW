# Mitwirken

Fehlerberichte, Vorschläge und neue Aufgaben sind willkommen, am besten zuerst als Issue.

## Einrichten

```bash
uv sync
npm --prefix frontend install
uv run aiarena4bw demo          # Beispieldaten, ohne BW-System und ohne Schlüssel
```

## Vor einem Pull Request

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
npm --prefix frontend run typecheck && npm --prefix frontend run lint && npm --prefix frontend run test
npm --prefix frontend run build     # die gebaute Oberfläche unter src/aiarena4bw/web/ mit einchecken
npm --prefix frontend run e2e       # Playwright mit installiertem Chrome
```

Alle Tests laufen ohne Netz, ohne BW-System und ohne Schlüssel gegen die Nachbauten in
`tests/fakes/`. Ein Pull Request braucht keinen Echtlauf; wer einen macht, nur gegen ein Test- oder
Demosystem.

## Regeln

- Oberfläche, Meldungen, Dokumentation und Kommentare deutsch; Bezeichner in Code, Datenbank und
  API englisch. Sichtbare Texte stehen in `frontend/src/texts/`, nicht in den Komponenten.
- Gestaltung nach `PRODUCT.md` und `DESIGN.md`: Dichte vor Dekoration, keine Einblend-Animationen.
- Schemaänderungen nur als neue Migration in `src/aiarena4bw/db.py`.
- Keine Geheimnisse, Hostnamen oder echten Laufdaten in Tests, Bildern oder Commits.
- Eine neue Aufgabe ist ein Ordner unter `tasks/` mit `task.yaml`, `prompt.md` und `verify.md`
  (siehe README). Sie legt nur Objekte mit den Platzhalternamen an und endet mit einer Prüfung, die
  jeden Prüfpunkt im BW nachsieht.
