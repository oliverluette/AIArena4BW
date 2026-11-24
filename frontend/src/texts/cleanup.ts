// Texte der Seite „BW bereinigen“.

const objects = (n: number) => `${n} ${n === 1 ? 'Objekt' : 'Objekte'}`
/** Dativ: „aus 2 Läufen“, „von 5 Objekten“. */
const fromRuns = (n: number) => `${n} ${n === 1 ? 'Lauf' : 'Läufen'}`
const ofObjects = (n: number) => `${n} ${n === 1 ? 'Objekt' : 'Objekten'}`

export const cleanup = {
  title: 'BW bereinigen',
  lead: 'Objekte aus Läufen im BW suchen, die Liste prüfen und löschen – ohne Modell, über den MCP-Server. Gelöscht wird nur, was genau der Namenskonvention des BW-Systems und der Laufkennung folgt.',
  objects,

  noSystemTitle: 'Noch kein BW-System eingerichtet',
  noSystemText: 'Bereinigen braucht ein BW-System mit Namenskonvention. Lege es in den Einstellungen an.',
  noSystemAction: 'BW-Systeme einrichten',
  noServerTitle: 'Noch kein MCP-Server eingetragen',
  noServerText: 'Bereinigen läuft über die Werkzeuge bw_search, bw_context und bw_write von coBWeb. Trage den Server in den Einstellungen ein und teste ihn.',
  noServerAction: 'MCP-Server einrichten',

  busy: 'Gerade läuft ein Durchgang. Bereinigen ist erst wieder möglich, wenn er beendet ist, damit sich Läufe und Löschen im BW nicht stören.',
  busyAction: 'Durchgang verfolgen',
  jobRunning: 'Im BW wird gerade bereinigt. Eine neue Suche ist möglich, sobald der Auftrag fertig ist.',

  select: {
    title: 'Auswählen',
    system: 'BW-System',
    server: 'MCP-Server',
    isDefault: 'Standard',
    convention: (area: string, prefix: string, run: string) =>
      `Namenskonvention, am Beispiel des Laufs ${run}: InfoArea ${area}, alle anderen Objekte beginnen mit ${prefix}. Transformationen und DTPs findet die App über die Objekte, an denen sie hängen.`,
    systemNotReady: (id: string, detail: string) =>
      `BW-System ${id} ist nicht bereit${detail ? ` (${detail})` : ''}. Suchen und Löschen werden voraussichtlich scheitern. Bitte zuerst prüfen, ob das System läuft und erreichbar ist.`,
    passwordMissing: (id: string) => `Für das BW-System ${id} ist kein Passwort hinterlegt. Ohne Passwort kann sich der MCP-Server nicht anmelden.`,
    openSystems: 'BW-Systeme öffnen',
    serverUnsupported: (name: string) =>
      `Mit ${name} ist Bereinigen gesperrt: Es braucht die Werkzeuge bw_search, bw_context und bw_write von coBWeb, und mindestens eines davon bietet dieser Server nicht an.`,
    serverUntested: (name: string) =>
      `${name} wurde noch nicht getestet. Teste den Server zuerst in den Einstellungen, damit feststeht, ob er die Werkzeuge bw_search, bw_context und bw_write anbietet.`,
    serverUnsupportedShort: 'nicht geeignet',
    serverUntestedShort: 'ungetestet',
    openServers: 'MCP-Server öffnen',
    batches: 'Durchgänge',
    batchesNote: (system: string) => `Durchgänge, die im BW-System ${system} gelaufen sind. Mehrere lassen sich zusammen bereinigen.`,
    batchesNoteAll: 'Durchgänge aller BW-Systeme. Gesucht wird trotzdem nur im gewählten BW-System.',
    allSystems: 'Durchgänge aller BW-Systeme zeigen',
    noBatches: (system: string) => `Im BW-System ${system} ist noch kein Durchgang gelaufen. Einzelne Läufe lassen sich trotzdem über ihre Kennung suchen.`,
    col: { code: 'Code', date: 'Datum', runs: 'Läufe', system: 'BW-System', server: 'MCP-Server' },
    pick: (code: string) => `Durchgang ${code} wählen`,
    extraCodes: 'Weitere Codes',
    extraCodesHint: 'In den Einstellungen gesperrte Codes ohne Durchgang in der Datenbank, zum Beispiel aus einem anderen Werkzeug.',
    runs: 'Einzelne Läufe',
    runsHint: 'Laufkennungen, durch Komma getrennt, z. B. AAA03, AAB11.',
    runsPlaceholder: 'AAA03',
    runsInvalid: (bad: string[]) =>
      `Keine Laufkennung: ${bad.join(', ')}. Erwartet werden drei Buchstaben und zwei Ziffern (AAA03) oder, bei übernommenen Durchgängen, ein Buchstabe und drei Ziffern (T021).`,
  },

  check: {
    title: 'Prüfen',
    search: 'Objekte im BW suchen',
    needScope: 'Wähle mindestens einen Durchgang oder gib eine Laufkennung ein.',
    fixRuns: 'Bitte zuerst die Laufkennungen in Schritt 1 berichtigen.',
    blockedBusy: 'Gesperrt, solange ein Durchgang läuft.',
    blockedServer: 'Gesperrt: Der gewählte MCP-Server bietet die nötigen Werkzeuge nicht an.',
    hint: 'Die Suche ändert nichts im BW. Gelöscht wird erst in Schritt 3, nach Bestätigung.',
    searching: 'Die App sucht im BW. Bei vielen Läufen kann das eine Weile dauern.',
    emptyTitle: 'Nichts zu bereinigen',
    emptyText: (system: string, scope: string) =>
      `Im BW-System ${system} gibt es keine Objekte, die der Namenskonvention folgen und zu ${scope} gehören. Entweder ist dort schon bereinigt, oder die Objekte tragen andere Namen – die fasst die App nicht an.`,
    found: (n: number, runCount: number, system: string) => `${objects(n)} aus ${fromRuns(runCount)} im BW-System ${system} gefunden.`,
    order: 'Die Liste steht je Lauf in Löschreihenfolge: abhängige Objekte zuerst, InfoAreas zuletzt. Nimm den Haken weg, wenn ein Objekt bleiben soll.',
    selected: (n: number, total: number) => `${n} von ${ofObjects(total)} gewählt`,
    selectAll: 'Alle Objekte wählen',
    selectRun: (run: string) => `Alle Objekte des Laufs ${run} wählen`,
    selectOne: (type: string, name: string) => `${type} ${name} wählen`,
    stale: 'Die Auswahl in Schritt 1 hat sich geändert. Bitte neu suchen.',
  },

  table: {
    type: 'Typ',
    name: 'Name',
    status: 'Status im BW',
    title: 'Titel',
    via: 'über',
    result: 'Ergebnis',
    message: 'Meldung',
    run: (run: string, n: number) => `Lauf ${run} · ${objects(n)}`,
    noRun: (n: number) => `Ohne Laufkennung · ${objects(n)}`,
  },

  types: {
    AREA: 'InfoArea',
    IOBJ: 'InfoObject',
    ADSO: 'aDSO',
    HCPR: 'CompositeProvider',
    TRCS: 'InfoSource',
    TRFN: 'Transformation',
    DTPA: 'DTP',
    RSDS: 'DataSource',
    LSYS: 'Quellsystem',
    RSPC: 'Prozesskette',
    QUERY: 'Query',
    ELEM: 'Query-Element',
    VARIABLE: 'Variable',
    CKF: 'Berechnete Kennzahl',
    RKF: 'Eingeschränkte Kennzahl',
    STRUCTURE: 'Struktur',
    ALVL: 'Aggregationsebene',
    FILTER: 'Filter',
    PLSE: 'Planungsfunktion',
    PLSQ: 'Planungssequenz',
    HIER: 'Hierarchie',
    DEST: 'Open-Hub-Destination',
    ROLE: 'Rolle',
  } as Record<string, string>,

  bwStatus: { active: 'aktiv', inactive: 'inaktiv', unknown: 'unbekannt' } as Record<string, string>,

  result: {
    open: 'offen',
    current: 'wird gelöscht',
    deleted: 'gelöscht',
    error: 'Fehler',
    skipped: 'nicht bearbeitet',
  },

  del: {
    title: 'Löschen',
    waiting: 'Erst suchen und die Liste prüfen. Danach lassen sich die gewählten Objekte hier löschen.',
    none: 'Kein Objekt gewählt. Setze in Schritt 2 mindestens einen Haken.',
    ready: (n: number, system: string) =>
      `${objects(n)} ${n === 1 ? 'wird' : 'werden'} im BW-System ${system} gelöscht. Das lässt sich nicht rückgängig machen.`,
    button: (n: number) => `${objects(n)} löschen`,
    buttonNone: 'Objekte löschen',
    confirmTitle: (n: number, system: string) => `${objects(n)} im BW-System ${system} löschen?`,
    confirmText: (n: number, system: string, server: string) =>
      `Die App löscht ${n === 1 ? 'das gewählte Objekt' : `die ${n} gewählten Objekte`} im BW-System ${system} über den MCP-Server ${server}. Das Löschen lässt sich nicht rückgängig machen: Was weg ist, entsteht nur durch einen neuen Lauf wieder.`,
    confirmScope: 'Umfang',
    confirmTypes: 'Objekte',
    confirm: (n: number) => `${objects(n)} endgültig löschen`,
    started: 'Löschauftrag gestartet',
  },

  job: {
    heading: (id: number, system: string) => `Auftrag ${id} im BW-System ${system}`,
    progress: (done: number, total: number) => `${done} von ${ofObjects(total)} bearbeitet`,
    cancel: 'Löschen abbrechen',
    cancelRequested: 'Abbruch angefordert. Das Objekt, das gerade gelöscht wird, schließt die App noch ab.',
    cancelSent: 'Abbruch angefordert',
    stuck: 'Der Auftrag ist geplant, aber nicht angelaufen.',
    noMessage: { done: 'Alle Objekte gelöscht.', error: 'Der Auftrag endete mit Fehlern.', cancelled: 'Der Auftrag wurde abgebrochen.' } as Record<string, string>,
    restTitle: (n: number) => `Danach noch im BW gefunden: ${objects(n)}`,
    restNote: 'Diese Objekte gehören zum Umfang des Auftrags und sind noch da: nicht gewählt, nicht löschbar oder inzwischen neu angelegt.',
    searchAgain: 'Diesen Umfang erneut suchen',
  },

  jobs: {
    title: 'Frühere Aufträge',
    note: 'Die letzten 20 Löschaufträge mit dem Ergebnis je Objekt.',
    empty: 'Noch kein Löschauftrag. Jeder Auftrag erscheint hier mit dem Ergebnis je Objekt.',
    col: { date: 'Datum', system: 'BW-System', scope: 'Umfang', status: 'Status', message: 'Meldung' },
    show: 'Objekte zeigen',
    hide: 'Objekte ausblenden',
  },

  scope: (codes: string[], runCodes: string[]) =>
    [
      codes.length ? `${codes.length === 1 ? 'Durchgang' : 'Durchgänge'} ${codes.join(', ')}` : '',
      runCodes.length ? `${runCodes.length === 1 ? 'Lauf' : 'Läufe'} ${runCodes.join(', ')}` : '',
    ]
      .filter(Boolean)
      .join(' · ') || '–',
}
