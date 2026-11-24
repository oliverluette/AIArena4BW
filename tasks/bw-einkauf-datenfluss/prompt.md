Baue im SAP-BW-System {SYSTEM} über den MCP-Server {MCP} einen kleinen Datenfluss für Einkaufsdaten auf: Bestellungen und Wareneingänge von der Eingangsschicht bis zur Auswertung. Arbeite selbstständig bis zum Ende und stelle keine Rückfragen.

Alle Objekte gehören in die InfoArea `{AREA}` und werden als lokale Objekte im Paket `$TMP` angelegt, ohne Transportauftrag. Lade keine Daten und führe keine DTPs aus.

Anforderungen:

1. InfoArea `{AREA}` mit der Beschreibung "Benchmark Einkauf {RUN} {MODEL}" unter der InfoArea {PARENT_AREA}.

2. InfoObjects:
   - Merkmal `{PREFIX}{RUN}LF` (Lieferant, CHAR 10)
   - Merkmal `{PREFIX}{RUN}MT` (Material, CHAR 18)
   - Merkmal `{PREFIX}{RUN}WK` (Werk, CHAR 4)
   - Merkmal `{PREFIX}{RUN}BN` (Bestellnummer, CHAR 10)
   - Merkmal `{PREFIX}{RUN}WB` (Wareneingangsbeleg, CHAR 10)
   - Kennzahl `{PREFIX}{RUN}BM` (Bestellmenge: Datentyp QUAN mit fester Einheit ST)
   - Kennzahl `{PREFIX}{RUN}BW` (Bestellwert: Datentyp CURR mit fester Währung EUR)
   - Kennzahl `{PREFIX}{RUN}WM` (Wareneingangsmenge: Datentyp QUAN mit fester Einheit ST)

3. aDSOs:
   - `{PREFIX}{RUN}E1` "Bestellungen Eingang": Standard-aDSO nur mit Feldern, ohne InfoObjects. Felder BELNR (CHAR 10), LIFNR (CHAR 10), MATNR (CHAR 18), WERKS (CHAR 4), BUDAT (DATS), MENGE (DEC 13,3), NETWR (DEC 15,2). Schlüssel: BELNR.
   - `{PREFIX}{RUN}E2` "Wareneingänge Eingang": Standard-aDSO nur mit Feldern, ohne InfoObjects. Felder WEBEL (CHAR 10), BELNR (CHAR 10), MATNR (CHAR 18), WERKS (CHAR 4), BUDAT (DATS), MENGE (DEC 13,3). Schlüssel: WEBEL.
   - `{PREFIX}{RUN}B1` "Bestellungen": Standard-aDSO mit den InfoObjects `{PREFIX}{RUN}BN`, `{PREFIX}{RUN}LF`, `{PREFIX}{RUN}MT`, `{PREFIX}{RUN}WK`, `0CALDAY`, `{PREFIX}{RUN}BM`, `{PREFIX}{RUN}BW`. Schlüssel: `{PREFIX}{RUN}BN`.
   - `{PREFIX}{RUN}W1` "Wareneingänge": Standard-aDSO mit den InfoObjects `{PREFIX}{RUN}WB`, `{PREFIX}{RUN}BN`, `{PREFIX}{RUN}MT`, `{PREFIX}{RUN}WK`, `0CALDAY`, `{PREFIX}{RUN}WM`. Schlüssel: `{PREFIX}{RUN}WB`.

4. Transformationen:
   - von `{PREFIX}{RUN}E1` nach `{PREFIX}{RUN}B1`: BELNR → Bestellnummer, LIFNR → Lieferant, MATNR → Material, WERKS → Werk, BUDAT → 0CALDAY, MENGE → Bestellmenge, NETWR → Bestellwert.
   - von `{PREFIX}{RUN}E2` nach `{PREFIX}{RUN}W1`: WEBEL → Wareneingangsbeleg, BELNR → Bestellnummer, MATNR → Material, WERKS → Werk, BUDAT → 0CALDAY, MENGE → Wareneingangsmenge.

5. DTPs:
   - von `{PREFIX}{RUN}E1` nach `{PREFIX}{RUN}B1` mit Filter WERKS = 1000.
   - von `{PREFIX}{RUN}E2` nach `{PREFIX}{RUN}W1` mit Filter BUDAT von 01.01.2026 bis 31.12.2026. Datumswerte im DTP-Filter im Format TT.MM.JJJJ angeben; das interne Format JJJJMMTT verwirft das System ohne Fehlermeldung.

6. CompositeProvider `{PREFIX}{RUN}CP` "Einkauf Bestellungen und Wareneingänge": Union aus `{PREFIX}{RUN}B1` und `{PREFIX}{RUN}W1`. Bestellnummer, Material, Werk und 0CALDAY aus beiden Quellen zuordnen, Lieferant aus `{PREFIX}{RUN}B1`, die Kennzahlen Bestellmenge und Bestellwert aus `{PREFIX}{RUN}B1`, Wareneingangsmenge aus `{PREFIX}{RUN}W1`.

7. Queries auf `{PREFIX}{RUN}CP`:
   - `{PREFIX}{RUN}Q1` "Einkaufsvolumen je Lieferant": Zeilen Lieferant, Spalten Bestellwert und Bestellmenge.
   - `{PREFIX}{RUN}Q2` "Bestellt und geliefert je Material": Zeilen Material, Spalten Bestellmenge und Wareneingangsmenge.
   - `{PREFIX}{RUN}Q3` "Einkauf Werk 1000": fester Filter Werk = 1000, Zeilen Material, Spalten Bestellwert.

8. Alle Objekte aktivieren.

Lege nur Objekte mit genau diesen Namen an (Transformationen und DTPs erhalten ihre Namen vom System) und ändere oder lösche keine anderen Objekte im System.

Antworte am Ende mit einer Liste der angelegten Objekte und ihrem Aktivierungsstatus, für Transformationen und DTPs mit ihren technischen Namen.
