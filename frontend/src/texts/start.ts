// Texte der Seite „Durchgang starten“.
export const start = {
  title: 'Durchgang starten',
  lead: 'Jede Kombination aus Aufgabe, Modell und Denkstufe läuft nacheinander im BW-System. Danach prüft ein anderes Modell das Ergebnis.',

  missing: {
    title: 'Für einen Durchgang fehlt noch etwas',
    text: 'Ein Durchgang braucht ein BW-System, einen MCP-Server, mindestens ein vorausgewähltes Modell und eine Aufgabe.',
    bw: 'BW-System eingerichtet',
    mcp: 'MCP-Server eingetragen',
    models: 'Modelle einer aktiven Plattform vorausgewählt',
    tasks: 'Aufgabe vorhanden',
    done: 'vorhanden',
    open: 'fehlt',
    settings: 'Einstellungen öffnen',
    tasksAction: 'Aufgaben öffnen',
  },

  template: {
    title: 'Vorlage',
    note: 'Übernimmt alle Angaben eines früheren Durchgangs.',
    label: 'Früherer Durchgang',
    placeholder: 'Durchgang wählen …',
    none: 'Noch kein früherer Durchgang',
    option: (code: string, date: string, tasks: number, models: number, repeats: number, note: string) =>
      [
        code,
        date,
        `${tasks} ${tasks === 1 ? 'Aufgabe' : 'Aufgaben'}, ${models} ${models === 1 ? 'Modell' : 'Modelle'}${repeats > 1 ? `, ${repeats} Wiederholungen` : ''}`,
        note.length > 60 ? `${note.slice(0, 57).trimEnd()} …` : note,
      ]
        .filter(Boolean)
        .join(' · '),
    applied: (code: string) => `Angaben aus Durchgang ${code} übernommen.`,
    appliedChanged: (code: string) => `Angaben aus Durchgang ${code} übernommen, seither geändert.`,
    reset: 'Zurücksetzen',
    resetTitle: 'Setzt alle Angaben, Filter und die Suche auf die Vorgaben zurück',
  },

  env: {
    title: 'Umgebung',
    note: 'Wogegen die Modelle arbeiten.',
    system: 'BW-System',
    server: 'MCP-Server',
    tools: (n: number) => `zuletzt getestet: ${n} Werkzeuge`,
    untested: 'noch nicht getestet',
  },

  tasks: {
    title: 'Aufgaben',
    chosen: (n: number, total: number) => `${n} von ${total} gewählt`,
    pick: (title: string) => `Aufgabe „${title}“ wählen`,
    col: { task: 'Aufgabe', version: 'Version', timeout: 'Zeitlimit', checkpoints: 'Prüfpunkte' },
  },

  models: {
    title: 'Modelle',
    chosen: (n: number, total: number) => `${n} von ${total} gewählt`,
    hidden: (n: number) => `, davon ${n} gerade nicht sichtbar`,
    search: 'Modell suchen',
    searchPlaceholder: 'Name, Anbieter oder Modell-ID',
    platform: 'Plattform',
    vendor: 'Anbieter',
    selectVisible: (n: number) => `Alle ${n} sichtbaren wählen`,
    clearVisible: 'Sichtbare abwählen',
    clearAll: 'Auswahl aufheben',
    pick: (name: string) => `Modell „${name}“ wählen`,
    col: { model: 'Modell', vendor: 'Anbieter', platform: 'Plattform', price: 'Preis je 1 Mio. Tokens (Eingabe / Ausgabe)' },
    free: 'kostenfrei',
    noneVisible: 'Kein Modell passt zu Suche und Filtern.',
    resetFilters: 'Filter zurücksetzen',
    more: 'Weitere Modelle lassen sich in den Einstellungen unter LLM-Plattformen vorauswählen.',
  },

  scope: {
    title: 'Denkstufen und Wiederholungen',
    thinking: 'Denkstufen',
    thinkingHint: 'Jede gewählte Stufe ergibt eigene Läufe. „Ohne Vorgabe“ sendet keine Stufe an die Plattform.',
    repeats: 'Wiederholungen',
    repeatsHint: 'Wie oft jede Kombination läuft. Wiederholungen zeigen, wie stark die Ergebnisse streuen.',
  },

  extra: {
    title: 'Prüfung, Kostenlimit und Notiz',
    note: 'Leer gelassen gelten die Einstellungen.',
    verifier: 'Prüfmodell',
    fallback: 'Ersatzmodell',
    fallbackHint: 'Prüft, wenn das getestete Modell selbst das Prüfmodell ist.',
    asSet: (name: string) => `wie eingestellt: ${name}`,
    notSet: 'keines',
    modelOption: (name: string, platform: string) => `${name} · ${platform}`,
    costLimit: 'Kostenlimit in Dollar',
    costLimitPlaceholder: (value: string) => `Vorgabe: ${value}`,
    costLimitHint: 'Ist die Grenze erreicht, startet kein weiterer Lauf. 0 = kein Limit.',
    costLimitError: 'Bitte eine Zahl ab 0 eintragen, z. B. 25 oder 7,50.',
    noLimit: 'kein Limit',
    noteLabel: 'Notiz',
    notePlaceholder: 'Wozu dient dieser Durchgang?',
  },

  preview: {
    title: 'Vorschau',
    incomplete: 'Wähle mindestens eine Aufgabe und ein Modell. Dann stehen hier Code, Zahl der Läufe und die geschätzten Kosten.',
    code: 'nächster Code',
    runs: (combinations: number, repeats: number) =>
      `Läufe: ${combinations} ${combinations === 1 ? 'Kombination' : 'Kombinationen'} × ${repeats} ${repeats === 1 ? 'Wiederholung' : 'Wiederholungen'}`,
    estimate: (value: string) => `rund ${value}`,
    estimateLabel: (known: number, total: number) =>
      known === total
        ? `Kostenschätzung aus früheren Läufen, Erfahrungswerte für alle ${total} Kombinationen`
        : `Kostenschätzung aus früheren Läufen, Erfahrungswerte für ${known} von ${total} Kombinationen. Die übrigen sind nicht eingerechnet.`,
    noEstimate: 'Keine Kostenschätzung: Für diese Kombinationen gibt es noch keine früheren Läufe.',
    overLimit: 'Die Schätzung liegt über dem Kostenlimit. Der Durchgang hält an, sobald die Grenze erreicht ist.',
    verifier: 'Prüfmodell',
    fallback: 'Ersatzmodell',
    costLimit: 'Kostenlimit',
    thinking: 'Denkstufen',
    updating: 'Vorschau wird aktualisiert …',
    hints: 'Hinweise',
  },

  busy: 'Es läuft schon ein Durchgang. Ein neuer lässt sich erst starten, wenn er fertig ist.',
  busyLink: 'Zur Live-Seite',
  noticeMissing: 'Bitte zuerst den Nutzungshinweis oben auf der Seite bestätigen.',
  startAction: 'Durchgang starten',
  startHint: (runs: number) => `Startet ${runs} ${runs === 1 ? 'Lauf' : 'Läufe'} im BW-System und öffnet die Live-Seite.`,
  started: (code: string) => `Durchgang ${code} gestartet`,
}
