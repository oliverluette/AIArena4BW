Prüfe im SAP-BW-System {SYSTEM} mit den bereitgestellten Werkzeugen, ob die folgenden Objekte vorhanden und korrekt sind. Arbeite ausschließlich lesend: nichts anlegen, ändern, aktivieren oder löschen. Transformationen und DTPs findest du über die Verwendungsnachweise (where-used) der aDSOs.

Prüfpunkte:

1. InfoArea `{AREA}` existiert.
2. Die Merkmale `{PREFIX}{RUN}LF` (CHAR 10), `{PREFIX}{RUN}MT` (CHAR 18), `{PREFIX}{RUN}WK` (CHAR 4), `{PREFIX}{RUN}BN` (CHAR 10) und `{PREFIX}{RUN}WB` (CHAR 10) existieren und sind aktiv.
3. Die Kennzahlen `{PREFIX}{RUN}BM` und `{PREFIX}{RUN}WM` (QUAN, feste Einheit ST – in englischer Anzeige PC, beides ist korrekt) sowie `{PREFIX}{RUN}BW` (CURR, feste Währung EUR) existieren und sind aktiv. Ein anderer Datentyp oder eine fehlende feste Einheit bzw. Währung ist FEHLER.
4. Die aDSOs `{PREFIX}{RUN}E1` und `{PREFIX}{RUN}E2` existieren, sind aktiv, enthalten nur Felder ohne InfoObjects mit den Feldnamen aus der Aufgabe und haben die Schlüssel BELNR bzw. WEBEL.
5. Die aDSOs `{PREFIX}{RUN}B1` und `{PREFIX}{RUN}W1` existieren, sind aktiv, enthalten die verlangten InfoObjects einschließlich 0CALDAY und haben die Schlüssel `{PREFIX}{RUN}BN` bzw. `{PREFIX}{RUN}WB`.
6. Eine aktive Transformation von `{PREFIX}{RUN}E1` nach `{PREFIX}{RUN}B1` existiert; alle sieben Felder sind zugeordnet, BUDAT auf 0CALDAY.
7. Eine aktive Transformation von `{PREFIX}{RUN}E2` nach `{PREFIX}{RUN}W1` existiert; alle sechs Felder sind zugeordnet, BUDAT auf 0CALDAY.
8. Ein aktiver DTP von `{PREFIX}{RUN}E1` nach `{PREFIX}{RUN}B1` existiert mit Filter WERKS = 1000.
9. Ein aktiver DTP von `{PREFIX}{RUN}E2` nach `{PREFIX}{RUN}W1` existiert mit Filter BUDAT von 01.01.2026 bis 31.12.2026 (gleichwertig: 20260101 bis 20261231). Eine Selektion ohne Werte („#“) ist FEHLER.
10. Der CompositeProvider `{PREFIX}{RUN}CP` existiert, ist aktiv, ist eine Union aus `{PREFIX}{RUN}B1` und `{PREFIX}{RUN}W1` und stellt Lieferant, Material, Werk, Bestellnummer, 0CALDAY, Bestellmenge, Bestellwert und Wareneingangsmenge bereit.
11. Query `{PREFIX}{RUN}Q1` auf `{PREFIX}{RUN}CP`: Zeilen Lieferant, Spalten Bestellwert und Bestellmenge.
12. Query `{PREFIX}{RUN}Q2` auf `{PREFIX}{RUN}CP`: Zeilen Material, Spalten Bestellmenge und Wareneingangsmenge.
13. Query `{PREFIX}{RUN}Q3` auf `{PREFIX}{RUN}CP`: fester Filter Werk = 1000, Zeilen Material, Spalten Bestellwert.

Ob ein Objekt aktiv ist, entscheidet sein Status (z. B. „Status: active“ bzw. objectStatus). Die Angabe „Version: M“ bezeichnet nur die gelesene Bearbeitungsversion und ist kein Hinweis auf einen inaktiven Zustand. Abweichende Beschreibungstexte sind kein Fehler.

Gib pro Prüfpunkt eine Zeile mit OK oder FEHLER und einer kurzen Begründung aus.

Die letzte Zeile deiner Antwort lautet genau `VERDICT: PASS`, wenn alle 13 Punkte OK sind, sonst genau `VERDICT: FAIL`.
