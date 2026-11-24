Prüfe im SAP-BW-System {SYSTEM} mit den bereitgestellten Werkzeugen, ob die folgenden Objekte vorhanden und korrekt sind. Arbeite ausschließlich lesend: nichts anlegen, ändern, aktivieren oder löschen.

Prüfpunkte:

1. InfoArea `{AREA}` existiert.
2. Merkmal `{PREFIX}{RUN}CU` existiert, ist aktiv, Typ CHAR 10.
3. Merkmal `{PREFIX}{RUN}PR` existiert, ist aktiv, Typ CHAR 18.
4. Kennzahl `{PREFIX}{RUN}AM` existiert, ist aktiv, ist ein Betrag mit Datentyp CURR und fester Währung EUR. Eine Kennzahl mit anderem Datentyp (z. B. DEC) oder ohne feste Währung EUR ist FEHLER.
5. aDSO `{PREFIX}{RUN}D1` existiert, ist aktiv, liegt in der InfoArea `{AREA}`.
6. Das aDSO enthält alle drei InfoObjects, Schlüsselfelder sind Kunde und Produkt.

Ob ein Objekt aktiv ist, entscheidet sein Status (z. B. „Status: active“ bzw. objectStatus). Die Angabe „Version: M“ bezeichnet nur die gelesene Bearbeitungsversion und ist kein Hinweis auf einen inaktiven Zustand.

Gib pro Prüfpunkt eine Zeile mit OK oder FEHLER und einer kurzen Begründung aus.

Die letzte Zeile deiner Antwort lautet genau `VERDICT: PASS`, wenn alle sechs Punkte OK sind, sonst genau `VERDICT: FAIL`.
