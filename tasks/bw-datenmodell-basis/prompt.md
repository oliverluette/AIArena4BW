Erstelle im SAP-BW-System {SYSTEM} über den MCP-Server {MCP} ein kleines Datenmodell. Arbeite selbstständig bis zum Ende und stelle keine Rückfragen.

Anforderungen:

1. InfoArea `{AREA}` mit der Beschreibung "Benchmark Lauf {RUN} {MODEL}" unter der InfoArea {PARENT_AREA} anlegen.
2. In dieser InfoArea drei InfoObjects:
   - Merkmal `{PREFIX}{RUN}CU` (Kunde, CHAR 10)
   - Merkmal `{PREFIX}{RUN}PR` (Produkt, CHAR 18)
   - Kennzahl `{PREFIX}{RUN}AM` (Betrag: Datentyp CURR mit fester Währung EUR)
3. Ein Standard-aDSO `{PREFIX}{RUN}D1` in derselben InfoArea, das diese drei InfoObjects enthält. Schlüssel: Kunde und Produkt.
4. Alle Objekte aktivieren.
5. Alles als lokales Objekt im Paket `$TMP` anlegen, kein Transportauftrag.

Lege nur Objekte mit genau diesen Namen an und ändere oder lösche keine anderen Objekte im System.

Antworte am Ende mit einer Liste der angelegten Objekte und ihrem Aktivierungsstatus.
