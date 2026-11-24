---
name: AIArena4BW
description: Modelle im direkten Vergleich. Auf echten BW-Aufgaben.
colors:
  head: "#0e3b2a"
  head-ink: "#ffffff"
  head-ink-2: "#e9f2ec"
  head-line: "#2c5a45"
  head-deep: "#06241a"
  head-ok: "#6be3a4"
  head-fail: "#ff9a9a"
  head-warn: "#ffd27a"
  pass: "#0a7d45"
  fail: "#c8102e"
  warn: "#8a5a00"
  sel: "#ffe24a"
  sel-ink: "#101612"
  bg: "#f5f6f2"
  bg-deep: "#eceee8"
  surface: "#ffffff"
  surface-3: "#e6e9e3"
  line: "#dde1da"
  line-strong: "#9aa39c"
  text: "#101612"
  text-2: "#47524b"
  text-3: "#5e6761"
  pass-soft: "#e3f3ea"
  fail-soft: "#fbe6e9"
  warn-soft: "#f8eed6"
  info-soft: "#e8efea"
  chart-grid: "#e1e4de"
  series-1: "#1f5fbf"
  series-2: "#7a3fb8"
  series-3: "#b8750a"
  series-4: "#0e8c8c"
  series-5: "#c2478a"
  series-6: "#6b4f2a"
  series-7: "#d2691e"
  series-8: "#4f5d75"
  series-other: "#7c857f"
  dark-head: "#0b2e21"
  dark-bg: "#0e1411"
  dark-surface: "#151c18"
  dark-surface-3: "#232d28"
  dark-line: "#27322c"
  dark-line-strong: "#5c6b63"
  dark-text: "#eef2ee"
  dark-text-2: "#b9c4bd"
  dark-text-3: "#94a199"
  dark-accent: "#7fd3a6"
  dark-pass: "#4cc98a"
  dark-fail: "#ff7a7a"
  dark-warn: "#e8b455"
typography:
  display:
    fontFamily: "'Archivo Variable', 'Helvetica Neue', Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.15
    fontVariation: "'wdth' 88"
  headline:
    fontFamily: "'Archivo Variable', 'Helvetica Neue', Arial, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.15
    fontVariation: "'wdth' 88"
  title:
    fontFamily: "'Archivo Variable', 'Helvetica Neue', Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    lineHeight: 1.2
    fontVariation: "'wdth' 88"
  body:
    fontFamily: "'Archivo Variable', 'Helvetica Neue', Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.4
    fontFeature: "'tnum'"
  table:
    fontFamily: "'Archivo Variable', 'Helvetica Neue', Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
    fontFeature: "'tnum'"
    fontVariation: "'wdth' 85"
  label:
    fontFamily: "'Archivo Variable', 'Helvetica Neue', Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.4
  code:
    fontFamily: "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  none: "0px"
  radius: "3px"
spacing:
  sp-1: "4px"
  sp-2: "8px"
  sp-3: "12px"
  sp-4: "16px"
  sp-5: "20px"
  sp-6: "24px"
  sp-7: "32px"
components:
  bar:
    backgroundColor: "{colors.head}"
    textColor: "{colors.head-ink}"
    height: "46px"
    padding: "0 20px"
  bar-link:
    textColor: "{colors.head-ink-2}"
    padding: "0 10px"
  bar-link-hover:
    backgroundColor: "{colors.head-line}"
    textColor: "{colors.head-ink}"
  bar-link-active:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
  button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.radius}"
    height: "30px"
    padding: "0 12px"
  button-hover:
    backgroundColor: "{colors.surface-3}"
  button-primary:
    backgroundColor: "{colors.head}"
    textColor: "{colors.head-ink}"
    rounded: "{rounded.radius}"
    height: "30px"
    padding: "0 12px"
  button-primary-hover:
    backgroundColor: "{colors.text}"
    textColor: "{colors.bg}"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.fail}"
    rounded: "{rounded.radius}"
  button-danger-hover:
    backgroundColor: "{colors.fail-soft}"
  button-small:
    height: "26px"
    padding: "0 10px"
  chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.radius}"
    height: "26px"
    padding: "0 9px"
  chip-pressed:
    backgroundColor: "{colors.text}"
    textColor: "{colors.bg}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.radius}"
    height: "30px"
    padding: "4px 9px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.none}"
    padding: "16px"
  table-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.table}"
    height: "28px"
    padding: "3px 8px"
  table-row-selected:
    backgroundColor: "{colors.sel}"
    textColor: "{colors.sel-ink}"
  tag:
    backgroundColor: "{colors.surface-3}"
    textColor: "{colors.text}"
    rounded: "{rounded.radius}"
    height: "20px"
    padding: "0 7px"
  facets:
    backgroundColor: "{colors.surface}"
    width: "232px"
    padding: "14px 16px 20px"
---

# Design System: AIArena4BW

## Overview

**Creative North Star: "Tabellenstand"**

Die Oberfläche liest sich wie der Tabellenstand einer Liga: Rang, Bilanz, Quote, Formkurve. Ein BW-Developer sieht in Sekunden, welches Modell zuverlässig und günstig ist, markiert es und folgt ihm bis zum einzelnen Lauf. Alles ist auf diesen Blick hin gebaut: dichte Tabellen mit Haarlinien, eine dunkelgrüne Kopfleiste als einzige große Farbfläche, darunter heller Grund mit weißen Flächen und fast schwarzer Schrift.

Farbe ist hier Auskunft, nie Schmuck. Grün und Rot sprechen das Urteil aus, Gelb zeigt allein, was gewählt ist, und jede dieser Aussagen steht zusätzlich in einer Form (gefülltes oder hohles Quadrat, Rahmen mit Punkt oder Strich), damit sie auch ohne Farbe lesbar bleibt. Es gibt eine einzige Schriftfamilie; Überschriften, Tabellen und die Filterspalte setzen sie schmal, damit viele Spalten nebeneinander passen. Tiefe entsteht durch Linien und Flächentöne, nicht durch Schatten.

Das helle Schema ist der Standard, das dunkle lässt sich in der Fußzeile umschalten und ist aus dem hellen abgeleitet. Verweigert sind Kennzahl-Kacheln über einem Diagramm, der frühere Magazin-Auftritt, ein SAP-GUI- oder Terminal-Kostüm sowie alles Verspielte oder Werbliche. Unterstützt wird ab 1280 px Breite.

**Key Characteristics:**
- Dichte vor Dekoration: Tabellenzeilen von 28 px, Filterzeilen von 22 px, Haarlinien von 1 px.
- Eine Schriftfamilie (Archivo Variable), schmal gesetzt in Überschriften (88 %), Tabellen und Filterspalte (85 %); Tabellenziffern überall.
- Farbe mit festen Aufgaben: Dunkelgrün für die Kopfleiste, Grün und Rot für das Urteil, Gelb für die Auswahl.
- Die Form trägt das Urteil, nicht nur die Farbe.
- Flach und eckig: Ecken höchstens 3 px, Flächen und Tabellen ganz ohne Rundung, Schatten nur über schwebenden Ebenen.
- Keine Dauerbewegung, keine Einblendungen; nur kurze Farbwechsel von 120 ms.

## Colors

Eine nüchterne, leicht grünstichige Neutralpalette, über der drei Signalfarben und ein dunkles Grün je genau eine Aufgabe haben.

### Primary
- **Kopfleisten-Grün** (`head`, im hellen Schema zugleich `--accent` und `--focus`): Grund der Kopfleiste; außerdem Hauptschaltfläche, Fokusrahmen (2 px), Ankreuzfelder und der Zustand „läuft“. Schrift darauf ist `head-ink`, zurückgenommen `head-ink-2`; `head-line` ist der Hover-Ton der Menüpunkte, `head-deep` der Grund des Kostenstreifens, `head-ok` das Zeichen „bereit“ auf Dunkelgrün, `head-fail` und `head-warn` die Zeichen „nicht erreichbar“ und „nicht bereit“. Im dunklen Schema bleibt die Kopfleiste dunkelgrün (`dark-head`), der Akzent im Inhalt wird ein helles Grün (`dark-accent`).

### Secondary
- **Urteils-Grün** (`pass`): bestanden. Gefülltes Quadrat, Zonenquadrat für volle Quote, Zustandstexte wie „erreicht“ und „in Ordnung“, Rahmen der Erfolgsmeldung auf `pass-soft`.
- **Urteils-Rot** (`fail`): nicht bestanden. Hohles Quadrat, Zonenquadrat für Quoten unter 50 %, Fehlermeldungen auf `fail-soft`, Feldfehler, die gefährliche Schaltfläche und das Fehlerbanner.
- **Warn-Ocker** (`warn`): technische Störung ohne Urteil (Fehler, Zeitlimit, Schrittlimit, unklar), Hinweis auf `warn-soft`, Messbalken über dem Limit.

### Tertiary
- **Auswahl-Gelb** (`sel` mit Schrift `sel-ink`): der markierte Eintrag, in beiden Schemata derselbe Wert. Auch die Textmarkierung des Browsers ist gelb.

### Neutral
- **Grund** (`bg`) und **tiefer Grund** (`bg-deep`): Seitenfläche; der tiefere Ton trägt Protokoll- und Codeblöcke.
- **Fläche** (`surface`): weiße Tafeln, Tabellen, Filterspalte, Eingabefelder. `surface-3` ist Hover-Ton der Schaltflächen, Grund der Marken (Tags), Messbalken und Platzhalter.
- **Linie** (`line`) und **starke Linie** (`line-strong`): Haarlinien zwischen Zeilen und um Flächen; die starke Linie umrandet Bedienelemente. Die Linie unter einem Tabellenkopf und unter der Reiterleiste ist Tinte (`text`).
- **Tinte** (`text`), **zweite Tinte** (`text-2`), **dritte Tinte** (`text-3`): Text, Benennungen und Spaltenköpfe, Hinweise und Fußzeile. Tinte ist auch die Farbe gewählter Chips und Reiter sowie des Tooltips.
- **Diagrammreihen** (`series-1` bis `series-8`, `series-other`): kategorisch in fester Reihenfolge, nach Namen vergeben, nie nach Rang; ab der neunten Ausprägung „übrige“. Große Anbieter haben feste Plätze. Gitterlinien in `chart-grid`.
- **Dunkles Schema** (`dark-*`): dieselben Rollen auf dunklem, grünstichigem Grund; Urteilsfarben aufgehellt, Gelb unverändert.

### Named Rules
**Die Urteils-Regel.** Grün und Rot sagen immer „gut“ oder „schlecht“ über ein Ergebnis oder einen Zustand: Prüfurteil, Zone, erreichte Anforderung, Erreichbarkeit des BW, Meldung, gefährliche Aktion. Sie sind nie Schmuck, nie Kategorie und nie Diagrammreihe.

**Die Ein-Gelb-Regel.** Gelb hat genau eine Aufgabe: die Auswahl. Keine Warnung, keine Hervorhebung, kein Hover ist gelb.

**Die Tinte-auf-Gelb-Regel.** Auf Gelb gelten in beiden Schemata die dunklen Töne des hellen Schemas; eine markierte Zeile setzt Text, Urteilsfarben und Akzent dafür lokal zurück.

**Die Reihenfarben-Regel.** Diagrammreihen unterscheiden sich in Farbe und Form (Kreis, Quadrat, Dreieck, Raute, Kreuz, Plus) und folgen dem Namen der Ausprägung. Urteils-Grün und Urteils-Rot kommen in den Reihen nicht vor; färbt ein Diagramm nach Prüfurteil, trägt es die Urteilsfarben mit den Urteilsformen.

## Typography

**Display Font:** Archivo Variable mit Breitenachse, der App beigelegt (Ersatz: Helvetica Neue, Arial, sans-serif)
**Body Font:** Archivo Variable (dieselbe Familie, volle Breite)
**Label/Mono Font:** Für Benennungen dieselbe Familie. Technische Kennungen, JSON und Protokollausgaben stehen in der Festbreitenschrift des Systems (ui-monospace, SF Mono, Menlo, Consolas).

**Character:** Eine Grotesk in zwei Breiten statt zweier Schriften: fett und schmal für alles, was benennt und ordnet, normal und schmaler für alles, was Zahlen in Spalten trägt. Die Hierarchie entsteht aus Gewicht und Breite, kaum aus Größe; die ganze Skala reicht von 12 bis 24 px.

### Hierarchy
- **Display** (700, 22 px, Zeilenhöhe 1,15, Breite 88 %): Seitentitel, einmal je Seite. Die Kennung des laufenden Durchgangs auf der Live-Seite steht in 24 px bei gleichem Schnitt.
- **Headline** (700, 20 px, Zeilenhöhe 1,15, Breite 88 %): Wert einer Kennzahl in einer Kennzahlenzeile. Mit 17 px: Dialogtitel, Titel einer leeren Fläche, aktuelle Aktion auf der Live-Seite, Wortmarke.
- **Title** (700, 15 px, Zeilenhöhe 1,2, Breite 88 %): Abschnittstitel; mit 14 px die Gruppentitel der Filterspalte.
- **Body** (400, 14 px, Zeilenhöhe 1,4): Fließtext und Zusammenfassungen. Bedienelemente, Hinweise und Notizen stehen in 13 px; erklärende Absätze höchstens 72 bis 110 Zeichen breit.
- **Table** (400, 13 px, Breite 85 %, Tabellenziffern): Tabellenzellen und Filterspalte. Der Name eines Eintrags ist fett.
- **Label** (600, 12 px): Spaltenköpfe in `text-2`; mit Gewicht 400 bis 500 auch Feldbenennungen, Marken, Chips, Legenden und die Fußzeile. Keine Versalien, keine Sperrung.
- **Code** (400, 12 px, Zeilenhöhe 1,5, Festbreite): Modell-ID, Werkzeugaufrufe, JSON, Protokoll.

### Named Rules
**Die Eine-Familie-Regel.** Alle Oberflächentexte sind Archivo; Unterschiede entstehen durch Gewicht (400, 500, 600, 700) und Breite (100 %, 88 %, 85 %). Festbreite ist kein Gestaltungsmittel, sondern kennzeichnet wörtliche technische Inhalte.

**Die Zwölf-Pixel-Regel.** Keine Schrift ist kleiner als 12 px, auch nicht in Diagrammachsen, Legenden und Fußzeilen.

**Die Tabellenziffern-Regel.** Ziffern stehen überall in gleicher Breite (`tabular-nums` am Dokument); Zahlenspalten sind rechtsbündig und brechen nicht um.

## Layout

Der Rahmen ist eine Spalte: oben klebt die Kopfleiste (46 px hoch, volle Breite) mit Bildmarke, Wortmarke, Menü und rechts dem laufenden Durchgang samt Kostenstreifen (90 × 8 px) und BW-Status; unten schließt eine Fußzeile mit Claim, Schemawechsel und Version. Dazwischen liegt die Seite mit 14 px Abstand oben, 20 px seitlich und 32 px unten. Seiten mit Filtern stellen links eine klebende Filterspalte von 232 px daneben, die unter der Kopfleiste eigenständig rollt.

Inhalte füllen die Breite; es gibt keinen zentrierten Container mit Höchstbreite. Eine Seite beginnt mit einer Titelzeile (Titel links, Aktionen daneben, eine Angabe am rechten Rand), darauf folgen Abschnitte im Abstand von 20 px, jeder mit Titel und einer erklärenden Notiz auf derselben Grundlinie. Die Leitseite Auswertung stapelt: Vergleichsdiagramm über die volle Breite mit Steuerspalte von 196 px, darunter die Modelltabelle, dann die Läufe, dann die Diagramme je Modell. Raster sind zwei- oder dreispaltig mit 16 px Abstand, oder Inhalt mit einer Seitenspalte von 360 px.

Die Abstände folgen einer 4-px-Skala (4, 8, 12, 16, 20, 24, 32). Innerhalb dichter Bereiche sind die Schritte klein (Zellen 3 × 8 px, in der dichten Modelltabelle 5 px seitlich), zwischen Abschnitten größer; gleiche Polster überall gibt es nicht.

Gebaut ist für 1280 px und breiter. Unter 1400 px treten nachrangige Spalten der Modelltabelle zurück, unter 1340 px weicht der Kostenbetrag in der Kopfleiste dem Streifen (der Betrag steht dann im Tooltip). Unter 1180 px wandert die Filterspalte über den Inhalt und mehrspaltige Raster werden einspaltig; unter 760 px bricht die Kopfleiste um. Diese schmalen Stufen halten die App benutzbar, sind aber nicht das Ziel.

## Elevation & Depth

Das System ist flach. Tiefe entsteht durch Flächentöne (Grund, weiße Fläche, tiefer Grund für Code) und durch Haarlinien von 1 px; die Hierarchie von Linien ist Linie, starke Linie, Tinte. Schatten gibt es nur dort, wo etwas wirklich über der Seite schwebt.

### Shadow Vocabulary
- **Schwebende Ebene** (`box-shadow: 0 12px 32px rgba(16, 22, 18, 0.18)`, dunkel `0 12px 32px rgba(0, 0, 0, 0.5)`): Dialog und Kurzmeldung (Toast). Der Dialog liegt auf einem Schleier (`rgba(16, 22, 18, 0.5)`).
- **Kopflinie beim Rollen** (`box-shadow: inset 0 -1px 0` in `line-strong`): klebender Tabellenkopf in einer rollenden Liste; ersetzt die Linie, die beim Kleben verloren ginge.

### Named Rules
**Die Flach-Regel.** Tafeln, Tabellen, Schaltflächen und Eingabefelder haben keinen Schatten, auch nicht bei Hover. Ein Schatten bedeutet: liegt über der Seite und verdeckt sie.

## Shapes

Die Formensprache ist rechtwinklig. Bedienelemente (Schaltflächen, Felder, Chips, Marken) haben leicht gebrochene Ecken (3 px); Tafeln, Tabellen, Meldungen, Dialoge, Messbalken und der Kostenstreifen haben gar keine Rundung. Umschalter aus zwei Chips sitzen ohne Rundung und ohne Lücke aneinander. Nichts ist pillenförmig.

Das Quadrat ist die wiederkehrende Figur: als Urteilszeichen (12 px), als Kästchen der Formkurve (10 px, Abstand 3 px), als Zonenquadrat in der Rangspalte (8 px) und als Legendenzeichen der Diagramme (12 px). Die Bildmarke besteht aus drei waagerechten Balken abnehmender Länge an einer senkrechten Achse; klein steht sie ohne Achse.

Zustandszeichen sind einfarbige, geometrische Vektorformen in der Farbe des Textes daneben:
- gefülltes Quadrat: bestanden, bereit, erreicht
- hohles Quadrat (Rahmen 2 px): nicht bestanden, nicht erreichbar
- Rahmen mit Punkt: ohne Urteil, unklar
- Rahmen mit Strich: ungültig
- gefülltes Dreieck: technische Störung (Fehler, Zeitlimit, Schrittlimit)
- Ring: läuft
- Strich: übersprungen, abgebrochen
- Punkt: neutral (geplant, beendet)

## Components

Bedienelemente sind niedrig, eckig und leise; sie treten hinter die Daten zurück. Zustandswechsel sind Farbwechsel von 120 ms mit der Kurve `cubic-bezier(0.2, 0.7, 0.2, 1)`. Der Fokus ist überall ein Rahmen von 2 px in Akzentfarbe mit 2 px Abstand, in der Kopfleiste weiß und nach innen gesetzt.

### Buttons
- **Shape:** leicht gebrochene Ecken (3 px), Höhe 30 px, klein 26 px; Schrift 13 px, Gewicht 500.
- **Standard:** weiße Fläche mit starker Linie und Tinte; Polster 0 × 12 px.
- **Primary:** Kopfleisten-Grün gefüllt, weiße Schrift, Gewicht 600. Höchstens eine je Ansicht.
- **Hover / Focus:** Standard wechselt auf `surface-3` mit dunklerem Rahmen; Primary wechselt auf Tinte. Keine Bewegung, kein Schatten.
- **Danger / Quiet:** Die gefährliche Aktion hat roten Rahmen und rote Schrift, bei Hover `fail-soft`. Die stille Variante hat weder Rahmen noch Fläche und steht in `text-2`.
- **Disabled:** dritte Tinte auf blasser Linie; Primary auf `surface-3`.

### Chips
- **Style:** Höhe 26 px, Ecken 3 px, weiße Fläche mit starker Linie, Schrift 12 px mit Gewicht 500. Alle Werte bleiben sichtbar.
- **State:** Gewählt ist in Tinte gefüllt mit heller Schrift (`aria-pressed`). Als Umschalter (zum Beispiel „je Lauf“ gegen „je Modell“) sitzen zwei Chips ohne Rundung und ohne Lücke nebeneinander.
- **Reiter:** dieselbe Logik in einer Leiste mit Tintenlinie darunter; der aktive Reiter ist in Tinte gefüllt.
- **Marke (Tag):** Höhe 20 px, `surface-3`, nicht bedienbar; kennzeichnet zum Beispiel Werkzeugnamen oder den Vorführmodus.

### Cards / Containers
- **Corner Style:** keine Rundung.
- **Background:** weiße Fläche auf hellem Grund; Diagramme stehen auf einer eigenen Diagrammfläche mit derselben Farbe.
- **Shadow Strategy:** keine, siehe Elevation & Depth.
- **Border:** Haarlinie (1 px, `line`).
- **Internal Padding:** 16 px; Tafeln, die eine Tabelle oder ein Diagramm mit Steuerspalte tragen, haben kein Polster.
- **Kennzahlen:** stehen als Zeile aus Wert (20 px, fett, schmal) und Benennung (12 px) ohne eigene Fläche, mit 32 px Abstand untereinander. Kacheln gibt es nicht.
- **Meldung:** Zeichen und Text in einer Zeile, getönte Fläche mit Rahmen in der Farbe der Aussage (neutral, Ocker, Rot, Grün).

### Inputs / Fields
- **Style:** Mindesthöhe 30 px, weiße Fläche, starke Linie, Ecken 3 px, Schrift 13 px. Die Benennung steht in 12 px über dem Feld, Hinweis und Fehler darunter. Die Auswahlliste zeichnet ihren Pfeil selbst und setzt den Wert in Gewicht 500.
- **Hover / Focus:** Rahmen wechselt auf `text-2`; Fokus ist der allgemeine Rahmen von 2 px.
- **Ankreuzfelder:** 14 px, in Akzentfarbe.
- **Error / Disabled:** Fehlertext in Rot unter dem Feld.

### Navigation
- **Kopfleiste:** Menüpunkte füllen die volle Höhe von 46 px, Schrift 14 px in `head-ink-2`, Polster 0 × 10 px. Hover ist `head-line`. Der aktive Punkt nimmt die Farbe der Seite an (`bg`, Tinte, Gewicht 600): Die Leiste öffnet sich zum Inhalt.
- **Status rechts:** laufender Durchgang als Ring mit Kennung und Fortschritt, daneben der Kostenstreifen (gefüllter Anteil in `head-ink-2` auf `head-deep`) und der Betrag gegen das Limit; ganz rechts der BW-Status mit Zustandszeichen. Beide führen per Klick zur zuständigen Seite.
- **Fußzeile:** Claim links, rechts der Schemawechsel als kleine Schaltfläche und die Version, 12 px in dritter Tinte.

### Tabelle
Die Tabelle ist der Hauptbaustein. Kopf in 12 px mit Gewicht 600 und `text-2` über einer Tintenlinie; Zeilen 28 px hoch mit Haarlinie, die letzte ohne. Hover tönt die Zeile kaum merklich (5 % Tinte). Sortierbare Köpfe sind Schaltflächen mit einem kleinen Dreieck für die Richtung. Spaltengruppen (Bilanz, Kosten und Laufzeit, Form) trennt eine senkrechte Haarlinie; eine Zonenlinie in Tinte trennt nach Rang die Einträge mit voller Quote, das Mittelfeld und die unter 50 %. Ausgeblendete oder ungültige Zeilen stehen in dritter Tinte. Anklickbare Zeilen zeigen den Zeiger.

### Formkurve und Zonenquadrat
Die Formkurve zeigt je Lauf ein Kästchen von 10 px: gefüllt grün, hohl mit rotem Rahmen, Rahmen mit Punkt, Rahmen mit Strich. Das Zonenquadrat (8 px) vor dem Rang ist grün bei voller Quote und rot unter 50 %; das Mittelfeld trägt keines. Eine Legende in 12 px erklärt beide unter der Tabelle.

### Filterspalte
Ankreuzlisten je Merkmal mit fettem, schmalem Gruppentitel (14 px), Zeilen von 22 px und der Zahl der Läufe rechtsbündig in `text-2`. Beim Darüberfahren oder bei Tastaturfokus erscheint je Zeile „nur“, das allein diesen Wert zeigt. Merkmale mit einem einzigen Wert stehen als eine Zeile aus Benennung, Wert und Zahl. Lange Listen werden über eine Auswahlliste ergänzt; gewählte Werte stehen ausgeschrieben und einzeln entfernbar darunter.

### Markierter Eintrag
Die kennzeichnende Bedienung: Ein Klick auf ein Modell markiert es auf der ganzen Seite, und die Markierung bleibt stehen. In der Modelltabelle und in den Läufen ist die Zeile gelb gefüllt mit dunkler Schrift; im Vergleichsdiagramm liegt ein gelber Hof mit Tintenrand unter dem Punkt, der Punkt wird über allen anderen noch einmal gezeichnet und seine Beschriftung ist fett; in den Diagrammen je Modell ist die Achsenbeschriftung gelb hinterlegt und fett.

### Diagramme
Diagramme stehen auf einer weißen Diagrammfläche mit Haarlinie. Achsen in starker Linie ohne Teilstriche, Gitter in `chart-grid`, Beschriftungen 12 px in Tinte, Achsentitel in `text-2`. Legendenzeichen sind Quadrate von 12 px. Der Tooltip ist in Tinte gefüllt mit heller Schrift (13 px, Ecken 3 px, Tabellenziffern). Unter dem Diagramm steht eine Zeile in 12 px, die sagt, was gezeichnet ist und was fehlt; daneben „Zoom zurücksetzen“ und „Als Bild speichern“.

### Messbalken
Balken von 8 px Höhe ohne Rundung auf `surface-3`, Füllung in Tinte, über dem Limit in Ocker. Der Kostenstreifen der Kopfleiste ist dieselbe Figur auf Dunkelgrün.

## Do's and Don'ts

### Do:
- **Do** neue Inhalte zuerst als Tabelle denken: Kopf 12 px über Tintenlinie, Zeilen 28 px, Haarlinien, Zahlen rechtsbündig mit Tabellenziffern.
- **Do** jeden Zustand mit Zeichen und Wort zeigen; die Form muss die Aussage auch ohne Farbe tragen (gefülltes Quadrat, hohles Quadrat, Rahmen mit Punkt, Rahmen mit Strich).
- **Do** die Auswahl überall gelb führen, wo derselbe Eintrag wieder erscheint, und auf Gelb die dunklen Töne des hellen Schemas verwenden.
- **Do** Überschriften und Kennzahlwerte fett und schmal (700, 88 %), Tabellen und Filterspalte schmaler (85 %) setzen.
- **Do** Diagrammfarben aus `series-1` bis `series-8` in fester Reihenfolge nach Namen vergeben und jede Reihe zusätzlich durch ihre Form unterscheiden.
- **Do** Zustandswechsel als Farbwechsel von 120 ms ausführen und `prefers-reduced-motion` achten.
- **Do** beide Schemata prüfen; hell ist der Standard, dunkel folgt denselben Rollen.
- **Do** für 1280 px und breiter bauen und prüfen, dass die wichtigen Spalten ohne waagerechtes Rollen sichtbar bleiben.

### Don't:
- **Don't** Gelb für Warnungen, Hervorhebungen oder Hover verwenden; Gelb ist allein die Auswahl.
- **Don't** Grün oder Rot als Reihenfarbe, Kategorie oder Schmuck einsetzen.
- **Don't** Kennzahl-Kacheln über ein Diagramm stellen; Kennzahlen stehen als Zeile ohne eigene Fläche.
- **Don't** eine zweite Schriftfamilie, kursive Serifen-Überschriften oder Versalien mit Sperrung einführen; der frühere Magazin-Auftritt gilt nicht mehr.
- **Don't** Schrift unter 12 px setzen.
- **Don't** Ecken über 3 px runden, Tafeln oder Tabellen runden oder pillenförmige Elemente bauen.
- **Don't** Schatten auf Tafeln, Schaltflächen oder bei Hover setzen; Schatten gehört nur zu Dialog, Kurzmeldung und Tooltip.
- **Don't** Verläufe als Flächenschmuck, Einblend-Animationen oder Dauerbewegung (Pulsieren, Laufbänder, drehende Zeichen) verwenden; dass ein Lauf lebt, zeigen Laufzeit und wechselnder Schritt.
- **Don't** die Oberfläche als SAP-GUI oder Terminal verkleiden oder werblich aufladen.
