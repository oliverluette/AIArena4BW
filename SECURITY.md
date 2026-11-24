# Sicherheit

## Eine Lücke melden

Bitte melde Sicherheitslücken nicht als öffentliches Issue, sondern über
[„Report a vulnerability“](https://github.com/oliverluette/AIArena4BW/security/advisories/new)
(GitHub Private Vulnerability Reporting). Beschreibe, was passiert, wie es sich nachstellen lässt
und welche Fassung betroffen ist. Du bekommst eine Rückmeldung, sobald die Meldung gesichtet ist;
eine feste Frist kann dieses Projekt nicht zusagen.

Gemeint sind etwa:

- Geheimnisse (Plattform-Schlüssel, BW-Passwort), die in Datenbank, Protokollen, Antworten der
  Schnittstelle oder der Oberfläche erscheinen;
- Wege, die App von einem anderen Rechner oder einer fremden Webseite aus anzusprechen;
- Wege, auf denen ein Modell mehr Werkzeuge oder Rechte bekommt, als die App ihm gibt, etwa das
  Prüfmodell schreibende Werkzeuge.

## Was die App schützt und was nicht

- Die App lauscht nur auf `127.0.0.1`, prüft Host- und Origin-Kopf und verlangt für schreibende
  Anfragen einen eigenen Kopf.
- Schlüssel und Passwörter liegen im Schlüsselbund des Betriebssystems. Protokolle werden vor dem
  Speichern geschwärzt.
- Das Prüfmodell bekommt nur Werkzeuge, die als lesend eingestuft sind.
- **Nicht** geschützt ist das BW-System vor dem, was der MCP-Server und der BW-Benutzer erlauben.
  Die App warnt bei coBWeb, wenn der Server mehr darf als nötig, sperrt aber nichts. Die Grenze
  setzen die Rechte des BW-Benutzers und die Einstellungen des MCP-Servers, siehe
  [Sicher einrichten](README.md#sicher-einrichten).
