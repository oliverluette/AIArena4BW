# Product

<!-- impeccable:product-schema 1 -->

Produktwahrheit für Gestaltungsarbeit: was jede Gestaltungsentscheidung wissen muss. Die Regeln
selbst stehen in `DESIGN.md`.

## Platform

web

## Users

Technisch versierte SAP-BW-Developer, die **selbst messen**: Sie klonen das Projekt, richten ihr
BW/4HANA-Testsystem, einen BW-MCP-Server und LLM-Plattformen ein, fahren eigene Durchgänge und
werten sie aus. Sie nutzen alle Seiten, von den Einstellungen bis zum Bereinigen.

Sie kennen BW-Objekte und deren technische Namen (InfoArea, InfoObject, aDSO, Transformation, DTP),
lesen Protokolle und Tabellen routiniert und arbeiten täglich in dichten Entwicklungswerkzeugen.
Fachbegriffe müssen nicht erklärt werden; technische Kennungen (Modell-ID, Laufkennung,
Objektname) sind für sie Information, kein Rauschen.

Die App läuft lokal auf dem eigenen Rechner, ein Nutzer, keine Anmeldung, nutzbar ab 1280 px Breite.

## Product Purpose

AIArena4BW lässt KI-Modelle dieselbe Modellierungsaufgabe in einem SAP-BW/4HANA-System lösen und
misst Erfolg, Laufzeit, Tokens und Kosten. Ein anderes Modell prüft jedes Ergebnis im BW nach.

Die App soll beantworten:

- Welche Modelle lösen BW-Aufgaben zuverlässig?
- Was kostet ein erfolgreicher Lauf, und wie lange dauert er?
- Wie stark streuen Ergebnisse bei Wiederholung?
- Was bewirken Änderungen an Aufgabe, MCP-Server, Plattform oder Denkstufe?

Erfolg heißt: Ein BW-Developer kann nach einem Durchgang begründet sagen, welches Modell er für
welche BW-Arbeit einsetzt, und jede Zahl bis zum einzelnen Werkzeugaufruf zurückverfolgen.

## Positioning

Gemessen wird am echten System, nicht an Textaufgaben: Das Modell legt über einen MCP-Server
tatsächlich BW-Objekte an, und ein zweites Modell prüft sie im BW nach. Jedes Ergebnis ist Aufgabe
und Version, Modell, Denkstufe, BW-System, MCP-Server, Agent-Version und Prüfmodell zugeordnet.
Läufe, die nicht am Modell scheiterten (Guthaben, Ratenlimit, Netz, BW-Ausfall), zählen nicht.

## Operating Context

Die Hauptarbeit, in dieser Reihenfolge:

1. **Modelle vergleichen** (Auswertung, Übersicht): Vergleichsdiagramm, Modelltabelle, Filter,
   Rangliste. Welches Modell, zu welchem Preis, wie zuverlässig.
2. **Durchgänge fahren** (Durchgang starten, Live): planen, Kosten schätzen, Fortschritt verfolgen,
   abbrechen, wiederholen, bereinigen.

Daneben: Läufe im Detail nachvollziehen (Zeitleiste, Werkzeugaufrufe, Prüfpunkte, Protokoll),
Aufgaben pflegen, BW bereinigen, Einstellungen (BW-Systeme, MCP-Server, Plattformen, Modelle,
Prüfung, Vorgaben).

Seiten: Übersicht, Durchgang starten, Live, Auswertung, Lauf-Detail, Aufgaben, BW bereinigen,
Einstellungen. Daneben gibt es eine Kommandozeile (`aiarena4bw run`, `cancel`, `list`).

Ein Durchgang läuft Minuten bis Stunden in einem eigenen Prozess; die Live-Seite wird zwischendurch
geöffnet und wieder verlassen. Ausgewertet wird über viele Durchgänge hinweg, mit bis zu 99 Läufen
je Durchgang und mehreren Dutzend Modelleinträgen.

## Capabilities and Constraints

- Technik: React + TypeScript (Vite), ECharts, FastAPI, SQLite. Die gebaute Oberfläche liegt im
  Repository.
- **Nur lokal:** Zur Laufzeit wird nichts von fremden Servern geladen. Schriften und Skripte
  liegen der App bei.
- **Sprache:** Oberfläche deutsch mit Umlauten und ß. Sichtbare Texte stehen in der Sprachdatei
  (`frontend/src/texts/`), nicht im Komponenten-Code. Bezeichner englisch.
- **Begriffe** sind fest: Aufgabe, Durchgang, Lauf, Laufkennung (`AAA01`),
  Plattform, Anbieter, Modell (`plattform:modell-id`), Denkstufe, Prüfmodell, Ersatzmodell,
  Umgebung.
- **Zustände, die sichtbar sein müssen:** Laufstatus (geplant, läuft, beendet, Fehler, Zeitlimit,
  Schrittlimit, abgebrochen, übersprungen), Prüfurteil (bestanden, nicht bestanden, unklar,
  ungültig, nicht geprüft, Fehler), Gültigkeit (ungültig, wiederholt als …), Kostenherkunft
  (abgerechnet, berechnet, kein Preis), BW-Status (bereit, Rechner erreichbar aber BW nicht bereit,
  nicht erreichbar, unbekannt).
- **Ehrliche Zahlen:** Ein fehlender Preis erscheint als „kein Preis“, nie als 0 $. Einträge mit
  eigener Denkstufe, anderem MCP-Server oder anderem Agenten werden nie gemittelt.
- Helles Schema als Standard, dunkles umschaltbar.
- Vorführmodus (`aiarena4bw demo`) mit erfundenen Beispieldaten für Bilder und Vorführungen.

Die Gestaltungsregeln stehen in `DESIGN.md` (Richtung „Tabellenstand“).

## Brand Commitments

Verbindlich:

- Name **AIArena4BW**.
- Claim: „Modelle im direkten Vergleich. Auf echten BW-Aufgaben.“
- Bildmarke „Rangliste“: drei waagerechte Balken abnehmender Länge an einer senkrechten Linie;
  als kleines Symbol ohne Linie.

Frei für die neue Gestaltung: Farben, Schriften, Schreibweise der Wortmarke, Aufbau, Dichte,
Bedienelemente.

Die frühere Gestaltung (große kursive Serifen-Überschriften, weite Abstände, blaugraue Flächen)
passte nach Einschätzung des Nutzers nicht zum Userkreis und ist ersetzt. Ausgeschlossen bleiben:
Magazin-Wirkung, mehrere oder verspielte Schriften, schwacher Kontrast, ein Kostüm als SAP GUI oder
Terminal, Verspieltes und Werbliches.

## Evidence on Hand

- Vorführmodus mit Beispiel-Datenbank; Bilder der Oberfläche in `docs/`.
- Zwei mitgelieferte Aufgaben: `bw-datenmodell-basis`, `bw-einkauf-datenfluss` (`tasks/`).
- Plattformtypen: OpenRouter im Echtbetrieb geprüft; Anthropic, SAP AI Core und OpenAI-kompatibel
  gegen Nachbauten.
- Echte Messergebnisse liegen privat in `data/` und gehören nicht in versionierte Dateien. Für
  Entwürfe, Bilder und README nur Daten des Vorführmodus verwenden und als Beispiel kennzeichnen.
- Keine Nutzerstimmen, keine veröffentlichten Benchmarks: nichts davon erfinden.

## Product Principles

1. **Vergleich zuerst.** Die Antwort auf „welches Modell, zu welchem Preis, wie zuverlässig“ ist
   ohne Scrollen und ohne Erklärung lesbar.
2. **Jede Zahl ist rückverfolgbar.** Von der Kennzahl zum Lauf, vom Lauf zum Werkzeugaufruf und zum
   Protokoll; Bedingungen (Aufgabenversion, Denkstufe, MCP-Server, Agent) stehen immer dabei.
3. **Nichts beschönigen.** Ungültig, ungeprüft, kein Preis und Streuung sind eigene, sichtbare
   Zustände, nie Lücken oder Nullen.
4. **Für Fachleute.** Technische Kennungen und BW-Begriffe unverkürzt und präzise; Dichte vor
   Dekoration.
5. **Lange Vorgänge im Griff.** Was läuft, was es bisher kostet und wie man es anhält, ist von
   jeder Seite aus erkennbar.

## Accessibility & Inclusion

Ergebnisse sind nie nur durch Farbe unterscheidbar, sondern zusätzlich durch Form oder Text.
Ausreichender Kontrast in beiden Farbschemata. BW-Status mit Zeichen und Erklärung.
