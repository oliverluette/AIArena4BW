// Texte der Seite „Aufgaben“. Abschnitte in `Backticks` setzt die Seite als Code.
export const tasks = {
  title: 'Aufgaben',
  lead: 'Eine Aufgabe ist ein versionierter Auftrag an das Modell: Aufgabentext, Prüfauftrag und die Anforderungen, an denen die App den Fortschritt abliest.',
  newTask: 'Neue Aufgabe',
  copy: 'Als Kopie anlegen',
  allTasks: 'Alle Aufgaben',

  list: {
    title: 'Vorhandene Aufgaben',
    folder: (path: string) => `Jede Aufgabe ist ein Ordner unter ${path}.`,
    col: {
      id: 'ID',
      title: 'Titel',
      version: 'Version',
      timeout: 'Zeitlimit',
      checkpoints: 'Prüfpunkte',
      requirements: 'Anforderungen',
      runs: 'Läufe mit dieser Version',
    },
    copyOf: (id: string) => `Aufgabe ${id} als Kopie anlegen`,
    emptyTitle: 'Noch keine Aufgabe vorhanden',
    emptyText: 'Lege die erste Aufgabe an: Aufgabentext für das Modell, Prüfauftrag für das Prüfmodell und die Anforderungen für die Fortschrittsanzeige.',
  },

  create: {
    lead: 'Die Aufgabe entsteht als Version 1. Die ID wird zum Ordnernamen und lässt sich später nicht mehr ändern.',
    copyLead: (id: string, version: number) =>
      `Kopie von ${id} (Version ${version}). Die Vorlage und ihre Läufe bleiben unverändert; die Kopie beginnt als Version 1.`,
    copyTitle: (title: string) => `${title} (Kopie)`,
    copyNote: (id: string, version: number) => `Kopie von ${id}, Version ${version}`,
  },

  edit: {
    lead: (version: number, runs: number) =>
      runs > 0 ? `Version ${version}, benutzt in ${runs} ${runs === 1 ? 'Lauf' : 'Läufen'}.` : `Version ${version}, noch in keinem Lauf benutzt.`,
    missingTitle: 'Diese Aufgabe gibt es nicht',
    missingText: (id: string) => `Unter der ID „${id}“ liegt keine Aufgabe. Vielleicht wurde der Ordner umbenannt oder gelöscht.`,
    versionMissing: (version: number) => `Version ${version} ist nicht in der Datenbank gespeichert.`,
  },

  lock: {
    locked: (version: number, runs: number) =>
      `Version ${version} ist gesperrt: Sie wurde schon in ${runs} ${runs === 1 ? 'Lauf' : 'Läufen'} benutzt. Änderungen verfälschen den Vergleich mit diesen Ergebnissen.`,
    advice: 'Empfohlen ist eine Kopie: Sie bekommt eine eigene ID, und die bisherigen Ergebnisse bleiben eindeutig dieser Aufgabe zugeordnet.',
    unlock: 'Trotzdem bearbeiten',
    unlocked: (version: number, next: number) =>
      `Bearbeitung freigegeben. Gespeichert wird als Version ${next}; Version ${version} bleibt für die bisherigen Läufe erhalten.`,
    relock: 'Wieder sperren',
  },

  view: {
    notice: (version: number, current: number, runs: number) =>
      `Version ${version}, benutzt in ${runs} ${runs === 1 ? 'Lauf' : 'Läufen'}: nur zum Ansehen. Aktuell ist Version ${current}.`,
    openCurrent: (current: number) => `Version ${current} öffnen`,
  },

  form: {
    base: 'Stammdaten',
    id: 'ID',
    idHint: 'Kleinbuchstaben, Ziffern und Bindestriche, 3 bis 50 Zeichen.',
    idFixed: 'Die ID entspricht dem Ordnernamen und ist nach dem Anlegen fest.',
    idInvalid: 'Die ID besteht aus Kleinbuchstaben, Ziffern und Bindestrichen (3–50 Zeichen) und beginnt und endet nicht mit einem Bindestrich.',
    idTaken: (id: string) => `Eine Aufgabe „${id}“ gibt es schon.`,
    title: 'Titel',
    titleHint: 'Erscheint in Auswahl, Rangliste und Auswertung.',
    timeout: 'Zeitlimit in Sekunden',
    timeoutHint: (text: string) => `30 bis 14.400 Sekunden. Entspricht ${text}.`,
    timeoutRange: '30 bis 14.400 Sekunden.',
    checkpoints: 'Zahl der Prüfpunkte',
    checkpointsHint: 'So viele Punkte bewertet der Prüfauftrag einzeln. Leer lassen, wenn er keine Punkte zählt.',
    prompt: 'Aufgabentext',
    promptNote: 'Der Auftrag an das getestete Modell. Platzhalter setzt die App je Lauf ein.',
    verify: 'Prüfauftrag',
    verifyNote: 'Der Auftrag an das Prüfmodell, das nur lesend im BW nachsieht. Die letzte Zeile der Antwort soll „VERDICT: PASS“ oder „VERDICT: FAIL“ lauten.',
  },

  req: {
    title: 'Anforderungen',
    note: 'Anforderungen gliedern die Fortschrittsanzeige eines Laufs, auf das Prüfurteil haben sie keinen Einfluss. Ein Werkzeugaufruf zählt zu jeder Anforderung, von der ein Namensteil im Werkzeugnamen vorkommt (Groß- und Kleinschreibung spielen keine Rolle). Bei coBWeb zählt `bw_write` nach Aktion und Objekttyp: Das Anlegen eines aDSO zählt wie ein Werkzeug `bw_create_adso`, dazu passt der Namensteil `create_adso`. Aktiviert der Aufruf, passt außerdem `activate`. Gängige Objekttypen: `infoarea`, `infoobject`, `adso`, `transformation`, `dtp`, `composite_provider`, `query`, `datasource`.',
    no: 'Nr.',
    name: 'Name',
    tools: 'Werkzeug-Namensteile, durch Komma getrennt',
    namePlaceholder: 'z. B. 3 aDSO',
    toolsPlaceholder: 'z. B. create_adso, update_adso',
    nameLabel: (n: number) => `Name der Anforderung ${n}`,
    toolsLabel: (n: number) => `Werkzeug-Namensteile der Anforderung ${n}`,
    up: 'Nach oben',
    down: 'Nach unten',
    remove: 'Entfernen',
    add: 'Anforderung hinzufügen',
    empty: 'Noch keine Anforderung. Ohne Anforderungen zeigt die Live-Seite nur Schritte, keinen Fortschritt je Anforderung.',
    emptyLocked: 'Diese Version hat keine Anforderungen.',
  },

  bar: {
    notCreated: 'Noch nicht angelegt',
    dirty: 'Ungespeicherte Änderungen',
    clean: 'Keine ungespeicherten Änderungen',
    discard: 'Änderungen verwerfen',
    create: 'Aufgabe anlegen',
    save: (version: number) => `Version ${version} speichern`,
    saveAs: (version: number) => `Als Version ${version} speichern`,
  },

  saved: {
    created: (id: string) => `Aufgabe ${id} angelegt`,
    version: (version: number) => `Als Version ${version} gespeichert`,
  },

  versionDialog: {
    title: (version: number) => `Als Version ${version} speichern`,
    text: (version: number, runs: number, next: number) =>
      `Version ${version} bleibt mit ihren ${runs} ${runs === 1 ? 'Lauf' : 'Läufen'} unverändert in der Datenbank. Neue Durchgänge verwenden Version ${next}. Ergebnisse verschiedener Versionen sind nicht direkt vergleichbar.`,
    note: 'Änderungsnotiz',
    noteHint: 'Pflichtangabe: Was hat sich geändert und warum? Die Notiz erscheint in der Änderungshistorie.',
    notePlaceholder: 'z. B. Prüfpunkt 4 verlangt jetzt die feste Währung EUR',
  },

  side: {
    checkTitle: 'Prüfung des Entwurfs',
    errors: 'So lässt sich die Aufgabe nicht speichern:',
    hints: 'Hinweise:',
    ok: 'Keine Einwände gegen den Entwurf.',
    placeholdersTitle: 'Platzhalter',
    placeholdersNote: 'In Aufgabentext und Prüfauftrag verwendbar, in geschweiften Klammern.',
    col: { placeholder: 'Platzhalter', meaning: 'Bedeutung', value: 'In der Vorschau' },
    previewTitle: 'Vorschau',
    previewNote: 'So liest das Modell den Text. Hier stehen Beispielwerte; im Durchgang setzt die App die Werte des jeweiligen Laufs ein.',
    tabPrompt: 'Aufgabentext',
    tabVerify: 'Prüfauftrag',
    previewEmpty: 'Noch kein Text.',
  },

  history: {
    title: 'Änderungshistorie',
    empty: 'Noch keine Einträge.',
    storedOnly: 'Die Historie steht bei der aktuellen Version.',
    col: { version: 'Version', date: 'Datum', note: 'Notiz' },
  },

  versions: {
    title: 'Versionen',
    note: 'Die aktuelle und alle in Läufen benutzten Versionen. Ältere lassen sich nur ansehen.',
    col: { version: 'Version', runs: 'Läufe' },
    current: 'aktuell',
    shown: 'wird angezeigt',
    show: 'Ansehen',
    showLabel: (version: number) => `Version ${version} ansehen`,
  },

  leave: {
    title: 'Ungespeicherte Änderungen verwerfen?',
    text: 'Die Änderungen an dieser Aufgabe sind noch nicht gespeichert. Beim Verlassen der Seite gehen sie verloren.',
    stay: 'Weiter bearbeiten',
    leave: 'Verwerfen und Seite verlassen',
  },
}
