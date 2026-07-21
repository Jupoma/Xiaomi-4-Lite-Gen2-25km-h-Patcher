# LEQI Region Changer 2.0.0-rc.1

Status: Release Candidate für Windows x64.

Diese Version ersetzt die Einmodell-Oberfläche des bisherigen Xiaomi 4 Lite
Gen2 Region Changers. Der Name der App lautet jetzt „LEQI Region Changer“.
Das bestehende GitHub-Repository bleibt aus Kompatibilitätsgründen erhalten.

## Neu

- Jupoma-Oberfläche in deutscher Du-Form mit neuem Logo und aktuellem
  Paper/Ink/Amber-Farbsystem.
- Auswahl mehrerer Scooterprofile aus versionierten JSON-Dateien.
- Profile für 4 Lite Gen2 DE/IT mit Blinkern, 5 Plus und Elite.
- Profilabhängige Baudrate, Regionspräfixe und Slash-Behandlung.
- Manuelle Eingabe und strikte Prüfung der vorhandenen Seriennummer.
- Erhalt der individuellen 14 Zeichen hinter dem Regionspräfix.
- CRC-16/XMODEM-Frameaufbau aus strukturierten Daten statt hartcodierter
  Komplettframes.
- Verbindliche Transaktion: Seriennummernframe, `100 ms` Pause, Commit-Frame.
- Passiver Diagnosemodus mit inkrementellem Frameparser und CRC-Anzeige.
- Thread-sichere UI-Zustände. Schreiben und Diagnose schließen einander aus.
- Reproduzierbarer Windows-x64-Build mit gepinnten Abhängigkeiten, Tests,
  Onefile-EXE, Release-ZIP und SHA-256-Datei.

## Freigegebene Profile

| Modell | Baudrate | DE | EU | US | Wire-Separator |
| --- | ---: | --- | --- | --- | --- |
| 4 Lite Gen2 DE/IT Version with turn Signals | `115200` | `53777` | `53937` | nicht verfügbar | keiner |
| 5 Plus | `19200` | `66232` | `66230` | `66227` | `/` |
| Elite | `19200` | `60543` | `60545` | `60457` | keiner |

## Geänderter Bedienablauf

Version 1 schrieb vollständige, fest hinterlegte Seriennummern. Version 2
verlangt die vorhandene Seriennummer und ersetzt ausschließlich deren erste
fünf Ziffern. Der aktuelle Präfix muss zum gewählten Profil gehören.

Vor dem Schreiben musst du Profil, COM-Port, Seriennummer, Zielregion und die
Sicherheitsbestätigung prüfen. Eine nicht verfügbare Region kann nicht gewählt
werden.

## Protokoll

Die Schreibtransaktion verwendet:

```text
5A 01 97 LL 01 <Seriennummer als ASCII> CRC_H CRC_L
100 ms Pause
5A 01 97 01 00 EB B0
```

Der zweite Frame wird gesendet. Er ist kein Geräte-ACK.

## Bekannte Grenzen

- Die App liest die Seriennummer nicht automatisch aus.
- Das angeschlossene Modell wird nicht automatisch erkannt.
- Es wird kein Geräte-ACK gelesen oder validiert.
- Es gibt keinen automatischen Retry und kein Readback.
- Eine Erfolgsmeldung bestätigt lokale Writes, Flush und Portschließung, nicht
  die dauerhafte Übernahme durch das Dashboard.
- Änderungen an Dashboard oder Firmware können das Verhalten beeinflussen.
- Jedes Profil benötigt vor einer stabilen Freigabe einen Test am realen
  Scooter.

## Sicherheit und Recht

Das Dashboard kann mit `21 V` arbeiten. Falsche Verdrahtung kann Adapter,
Scooter und PC beschädigen und zu Verletzungen führen. Prüfe Pinbelegung,
Spannung, Pegel und Jumper mit geeigneten Messmitteln. Verbinde niemals die
Dashboard-Versorgung mit dem USB-UART-Adapter oder PC.

Ein Regionswechsel kann zulässige Geschwindigkeit, Betriebserlaubnis,
Versicherung und Garantie beeinflussen. Du bist für den legalen und sicheren
Einsatz verantwortlich.

## Release-Artefakte

```text
LEQI-Region-Changer-V2.0.0-rc.1-win64.zip
SHA256SUMS.txt
```

Das ZIP enthält:

- `LEQI Region Changer.exe`
- `profiles/`
- `README.md`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `THIRD_PARTY_LICENSES/`

Prüfe die SHA-256-Summe vor der Weitergabe. Der Buildprozess signiert und
veröffentlicht keine Dateien.

Für diesen Release steht kein Code-Signing-Zertifikat bereit. Die EXE ist
unsigniert; Windows SmartScreen kann deshalb beim ersten Start warnen. Lade sie
nur aus dem offiziellen GitHub-Release und gleiche die SHA-256-Summe ab.

## Upgrade von V1.1

- Entpacke Version 2 in einen neuen Ordner.
- Übernimm keine alten PNG-Dateien oder hartcodierten HEX-Frames.
- Lass den neuen Ordner `profiles` neben der EXE liegen.
- Verwende die vollständige vorhandene Seriennummer deines Scooters.
- Behalte den bisherigen `V1.1`-Release unverändert. Direkte Download-Links
  und bestehende externe Quellen funktionieren dadurch weiter.
