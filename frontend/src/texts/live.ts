// Texte der Seite „Live“.
export const live = {
  title: 'Live',
  lead: 'Der laufende oder jüngste Durchgang. Die Anzeige folgt dem Lauf ohne Neuladen.',

  pick: {
    label: 'Durchgang',
    none: 'Durchgang wählen',
    option: (code: string, date: string, status: string) => `${code} · ${date} · ${status}`,
  },

  empty: {
    title: 'Noch kein Durchgang',
    text: 'Sobald ein Durchgang läuft, stehen hier Fortschritt, aktueller Schritt und Kosten. Starte den ersten Durchgang, um Modelle zu vergleichen.',
    action: 'Durchgang starten',
  },
  notFound: {
    title: 'Diesen Durchgang gibt es nicht',
    text: 'Vielleicht wurde der Link aus einer anderen Datenbank kopiert. Wähle oben einen anderen Durchgang oder zeige den jüngsten.',
    action: 'Jüngsten Durchgang zeigen',
  },

  connection: {
    lost: (message: string, time: string) => `Keine Verbindung zur App: ${message} Der Stand unten ist von ${time}.`,
    lostEmpty: (message: string) => `Keine Verbindung zur App: ${message}`,
  },

  head: {
    stale: 'Prozess beendet',
    hidden: 'ausgeblendet',
    otherAgent: (agent: string) => `Agent ${agent}`,
    system: 'BW-System',
    server: 'MCP-Server',
    verifier: 'Prüfmodell',
    fallback: 'Ersatzmodell',
    thinking: 'Denkstufen',
    repeats: 'Wiederholungen',
    started: 'Gestartet',
    finished: 'Beendet',
    created: 'Angelegt',
    note: 'Notiz',
    noModel: 'keines',
  },

  notice: {
    cancelRequested: 'Abbruch angefordert. Der laufende Lauf endet in wenigen Sekunden, offene Läufe werden übersprungen.',
    stale:
      'Der Prozess dieses Durchgangs ist beendet, der Durchgang gilt aber noch als laufend – etwa nach einem Absturz oder Neustart des Rechners. Bereinigen setzt den hängenden Lauf auf „abgebrochen“ und die offenen Läufe auf „übersprungen“. Danach lassen sie sich wiederholen.',
    hidden: (reason: string) => `Ausgeblendet: ${reason}. Dieser Durchgang zählt nicht in Übersicht und Auswertung.`,
    otherAgent: (agent: string) =>
      `Dieser Durchgang stammt von einem anderen Agenten (${agent}). Seine Läufe und Prüfungen lassen sich hier nicht wiederholen; für einen neuen Vergleich bitte einen neuen Durchgang starten.`,
    otherRunning: (code: string) => `Läufe und Prüfungen lassen sich erst wiederholen, wenn Durchgang ${code} fertig ist.`,
    selfRunning: 'Läufe und Prüfungen lassen sich wiederholen, sobald der Durchgang fertig ist.',
    planned: 'Dieser Durchgang ist geplant, aber es läuft kein Prozess dafür. „Jetzt ausführen“ startet seine geplanten Läufe sofort im BW-System.',
    plannedBusy: (code: string) => `Dieser Durchgang ist geplant, aber es läuft kein Prozess dafür. Er lässt sich ausführen, sobald Durchgang ${code} fertig ist.`,
  },

  action: {
    cancel: 'Durchgang abbrechen',
    cancelRequested: 'Abbruch angefordert',
    stale: 'Durchgang bereinigen',
    runPlanned: 'Jetzt ausführen',
    hide: 'Durchgang ausblenden',
    unhide: 'Wieder einblenden',
    retry: 'Läufe wiederholen',
    reverify: 'Prüfung wiederholen',
    output: 'Ausgabe des Runners',
  },

  toast: {
    cancel: 'Abbruch angefordert',
    started: 'Durchgang wird ausgeführt',
    stale: (runs: number) =>
      runs === 0 ? 'Durchgang bereinigt' : runs === 1 ? 'Durchgang bereinigt, 1 hängender Lauf abgebrochen' : `Durchgang bereinigt, ${runs} hängende Läufe abgebrochen`,
    hidden: 'Durchgang ausgeblendet',
    unhidden: 'Durchgang wieder eingeblendet',
    retry: (codes: string[]) => `Neu eingeplant: ${codes.join(', ')}`,
    reverify: (n: number) => (n === 1 ? 'Prüfung für 1 Lauf gestartet' : `Prüfung für ${n} Läufe gestartet`),
  },

  progress: {
    title: 'Fortschritt',
    done: 'Läufe erledigt',
    passed: 'bestanden',
    failed: 'nicht bestanden',
    invalid: 'ungültig',
    cost: 'Kosten des Durchgangs, Läufe und Prüfungen',
    ofLimit: (limit: string, share: string) => `${share} des Kostenlimits von ${limit}`,
    noLimit: 'kein Kostenlimit',
    nearLimit: 'Kostenlimit fast erreicht. Ist es erreicht, startet kein weiterer Lauf.',
    reached: 'Kostenlimit erreicht. Es startet kein weiterer Lauf.',
  },

  now: {
    title: 'Aktueller Lauf',
    step: (n: number) => `Schritt ${n}`,
    noStep: 'vor dem ersten Schritt',
    waiting: 'wartet',
    time: 'Laufzeit',
    timeVerify: 'Laufzeit der Prüfung',
    ofLimit: (limit: string) => `von ${limit} Zeitlimit`,
    taskTook: (time: string) => `Aufgabe bearbeitet in ${time}`,
    toolCalls: 'Werkzeugaufrufe',
    toolErrors: 'Werkzeugfehler',
    requirement: 'Anforderung',
    open: 'Lauf-Detail öffnen',
    task: (title: string, id: string, version: number) => (title ? `${title} (${id}, Version ${version})` : `${id}, Version ${version}`),
    reqTitle: 'Anforderungen',
    reqNote: (reached: number, total: number) => `${reached} von ${total} erreicht`,
    reqEmpty: 'Für diese Aufgabe sind keine Anforderungen hinterlegt.',
    reqCol: { name: 'Anforderung', state: 'Stand', calls: 'Aufrufe', errors: 'Fehler' },
    reached: 'erreicht',
    notReached: 'offen',
    latest: 'zuletzt bearbeitet',
    recentTitle: 'Letzte Werkzeugereignisse',
    recentEmpty: 'Noch kein Werkzeugaufruf in diesem Lauf.',
    recentCol: { at: 'Zeitpunkt', phase: 'Phase', step: 'Schritt', tool: 'Werkzeug', requirement: 'Anforderung', took: 'Dauer', result: 'Ergebnis' },
    ok: 'ok',
    error: 'Fehler',
    seconds: (value: string) => `${value} s`,
  },

  runs: {
    title: 'Läufe',
    note: (n: number) => (n === 1 ? '1 Lauf, Klick öffnet das Lauf-Detail' : `${n} Läufe, Klick öffnet das Lauf-Detail`),
    col: {
      code: 'Kennung',
      model: 'Modell',
      thinking: 'Denkstufe',
      task: 'Aufgabe',
      status: 'Status',
      verdict: 'Prüfurteil',
      time: 'Laufzeit',
      steps: 'Schritte',
      cost: 'Kosten',
      remark: 'Vermerk',
    },
    version: (n: number) => `v${n}`,
    verifying: 'Prüfung läuft',
    invalid: 'ungültig',
    retriedAs: (code: string) => `wiederholt als ${code}`,
    retryOf: (code: string) => `Wiederholung von ${code}`,
    costTitle: (source: string, verify: string | null) =>
      [source && `Kosten des Laufs: ${source}`, verify && `Kosten der Prüfung: ${verify}`].filter(Boolean).join(' · '),
  },

  cancel: {
    title: (code: string) => `Durchgang ${code} abbrechen?`,
    text: 'Der laufende Lauf wird abgebrochen und zählt nicht. Offene Läufe werden übersprungen; sie lassen sich später im selben Durchgang wiederholen. Bereits beendete Läufe bleiben erhalten.',
    keep: 'Weiterlaufen lassen',
    confirm: 'Durchgang abbrechen',
  },

  hide: {
    title: (code: string) => `Durchgang ${code} ausblenden`,
    text: 'Ein ausgeblendeter Durchgang zählt nicht in Übersicht und Auswertung. Er bleibt gespeichert und lässt sich jederzeit wieder einblenden.',
    reason: 'Grund',
    reasonPlaceholder: 'z. B. falsche Aufgabenversion, nur ein Test',
    confirm: 'Durchgang ausblenden',
  },

  picker: {
    suggested: 'Vorgeschlagene wählen',
    all: 'Alle wählen',
    none: 'Keine wählen',
    chosen: (n: number, total: number) => `${n} von ${total} gewählt`,
    pick: (code: string) => `Lauf ${code} wählen`,
    suggestedTag: 'vorgeschlagen',
    col: { run: 'Lauf', model: 'Modell', task: 'Aufgabe', status: 'Status', verdict: 'Prüfurteil', remark: 'Vermerk' },
  },

  retry: {
    title: (code: string) => `Läufe von Durchgang ${code} wiederholen`,
    text: 'Die gewählten Läufe laufen im selben Durchgang unter der nächsten freien Laufnummer neu, mit gleicher Aufgabe, gleichem Modell und gleicher Denkstufe. Vorher werden die BW-Objekte des alten Laufs entfernt; der alte Lauf zählt danach nicht mehr. Das Kostenlimit steigt um das bisher Verbrauchte. Vorgeschlagen sind ungültige und übersprungene Läufe.',
    warning: 'Die Läufe starten sofort nach der Bestätigung. Bei echten Plattformen entstehen dabei Kosten.',
    free: (n: number) => (n === 1 ? 'Noch 1 Laufnummer frei (höchstens 99 Läufe je Durchgang).' : `Noch ${n} Laufnummern frei (höchstens 99 Läufe je Durchgang).`),
    tooMany: (n: number) => `Es sind nur noch ${n} Laufnummern frei. Bitte weniger Läufe wählen oder einen neuen Durchgang starten.`,
    empty: 'In diesem Durchgang gibt es keinen abgeschlossenen Lauf, der sich wiederholen lässt.',
    confirm: (n: number) => (n === 1 ? '1 Lauf wiederholen' : `${n} Läufe wiederholen`),
  },

  reverify: {
    title: (code: string) => `Prüfung in Durchgang ${code} wiederholen`,
    text: 'Für die gewählten Läufe läuft nur die Prüfung neu, mit demselben Prüf- und Ersatzmodell, BW-System und MCP-Server. Das alte Prüfprotokoll bleibt erhalten; frühere Prüfkosten werden mitgezählt. Vorgeschlagen sind gültige Läufe ohne eindeutiges Urteil.',
    warning: 'Die Prüfungen starten sofort nach der Bestätigung. Bei echten Plattformen entstehen dabei Kosten.',
    empty: 'In diesem Durchgang gibt es keinen abgeschlossenen Lauf, dessen Prüfung sich wiederholen lässt.',
    confirm: (n: number) => (n === 1 ? 'Prüfung für 1 Lauf wiederholen' : `Prüfung für ${n} Läufe wiederholen`),
  },

  output: {
    title: (code: string) => `Ausgabe des Runners, Durchgang ${code}`,
    text: 'Was der Prozess des Durchgangs ausgibt; angezeigt wird das Ende der Datei.',
    empty: 'Der Runner hat noch nichts ausgegeben. Durchgänge anderer Agenten und nur geplante Durchgänge haben keine Ausgabe.',
    auto: 'Aktualisiert sich alle 3 Sekunden, solange der Durchgang läuft.',
    refresh: 'Ausgabe aktualisieren',
  },
}
