# LEQI Region Changer

Dein Scooter. Dein Setup.

LEQI Region Changer schreibt den regionsabhängigen Präfix einer vorhandenen
Scooter-Seriennummer über UART neu. Die App ersetzt nur die ersten fünf
Ziffern. Der individuelle Rest der Seriennummer bleibt erhalten.

Version: `2.0.0-rc.1`

## Vor dem Start

Dieses Tool greift direkt auf die Identität des Dashboards zu. Ein falsches
Profil, eine falsche Seriennummer oder eine falsche Verdrahtung kann den
Scooter unbrauchbar machen.

- Das Dashboard kann mit `21 V` arbeiten. Diese Spannung darf niemals am
  USB-UART-Adapter oder am PC anliegen.
- Verlasse dich nicht auf Kabelfarben. Prüfe Pinbelegung und Spannung mit
  einem Multimeter.
- Verbinde nur Leitungen, deren Funktion und Pegel du sicher kennst. Prüfe
  auch Jumper und Versorgungsausgänge deines UART-Adapters.
- Schalte den Scooter vor Änderungen an der Verdrahtung aus.
- Änderungen können Garantie, Betriebserlaubnis und Versicherungsschutz
  beeinflussen. Halte die Vorschriften an deinem Einsatzort ein.
- Teste das Ergebnis zuerst auf abgesperrtem Gelände.

Du handelst auf eigenes Risiko. Die App erkennt das angeschlossene Modell
nicht automatisch.

## Unterstützte Profile

| Profil | Datei | Baudrate | DE | EU | US | Trennzeichen auf der Leitung |
| --- | --- | ---: | --- | --- | --- | --- |
| 4 Lite Gen2 DE/IT Version with turn Signals | `4litegen2_itde_with_turn_signal.json` | `115200` | `53777` | `53937` | nicht verfügbar | keines |
| 5 Plus | `5_plus.json` | `19200` | `66232` | `66230` | `66227` | `/` |
| Elite | `elite.json` | `19200` | `60543` | `60545` | `60457` | keines |

Ein Eintrag „nicht verfügbar“ bleibt in der App deaktiviert. Die
Regionsbezeichnungen sind Profilwerte. Daraus folgt keine Aussage darüber, wo ein
Scooter im öffentlichen Verkehr betrieben werden darf.

## Release verwenden

1. Entpacke das Release vollständig. Die EXE enthält alle drei freigegebenen
   Standardprofile und funktioniert deshalb auch allein. Der Ordner `profiles`
   neben der EXE ermöglicht geprüfte Ergänzungen und Overrides.
2. Stelle die geprüfte UART-Verbindung bei ausgeschaltetem Scooter her.
3. Schalte den Scooter ein und starte `LEQI Region Changer.exe`.
4. Wähle das exakte Scooterprofil und den COM-Port.
5. Gib die vollständige vorhandene Seriennummer ein.
6. Wähle die Zielregion. Prüfe die Vorschau.
7. Bestätige Modell, Verdrahtung und Seriennummer.
8. Starte die Übertragung. Trenne nichts, bis die App den Port geschlossen hat.
9. Schalte den Scooter aus. Entferne erst dann die UART-Verbindung.

Die Seriennummer wird nicht automatisch ausgelesen. Übernimm sie exakt vom
Scooter beziehungsweise vom Typenschild.

## Format der Seriennummer

Nach der Normalisierung erwartet die App genau dieses Format:

```text
[0-9]{5}[A-Z0-9]{14}
```

Ein optionaler Slash direkt nach den ersten fünf Ziffern ist bei der Eingabe
zulässig. Buchstaben müssen als Großbuchstaben eingegeben werden. Beispiele:

```text
53777DXAN2F5QD02305
66232/DXAN2F5V101557
```

Der aktuelle Präfix muss im gewählten Profil vorkommen. Danach ersetzt die App
nur diese fünf Ziffern. Ob auf der Leitung ein Slash übertragen wird, legt das
Profil mit `wire_separator` fest.

## Was technisch gesendet wird

Die App baut für jedes Profil eine Transaktion aus zwei Frames:

```text
5A 01 97 LL 01 <Seriennummer als ASCII> CRC_H CRC_L
```

Danach wartet sie `100 ms` und sendet den Commit-Frame:

```text
5A 01 97 01 00 EB B0
```

Die Prüfsumme ist CRC-16/XMODEM. Beide Frames werden vollständig geschrieben
und geflusht. Danach wird der Port geschlossen.

Wichtig: Der Commit-Frame wird von der App gesendet. Er ist kein empfangenes
ACK. Die bekannten Dashboards liefern für diesen Ablauf keine von der App
ausgewertete Bestätigung. „Übertragung abgeschlossen“ bedeutet deshalb nur,
dass beide lokalen Schreibvorgänge, Flush und Schließen ohne Fehler beendet
wurden. Es gibt keinen automatischen Retry und kein Readback.

## Diagnose

Die Diagnose öffnet den gewählten Port strikt lesend und zerlegt den
Datenstrom inkrementell in `0x5A`-Frames, zeigt vollständige Frames als Hex an
und prüft deren CRC-16/XMODEM. Fragmentierte Frames und mehrere Frames pro
Lesevorgang werden unterstützt. Bytes vor einem gültigen Startbyte werden als
Noise verworfen.

Während die Diagnose verbunden ist, bleibt das Schreiben gesperrt. Beende die
Diagnoseverbindung vor einem Regionswechsel. Die Diagnose besitzt keine
Raw-TX-Funktion.

## Profile

Die App bringt freigegebene Basisprofile mit. Zusätzlich liest sie den Ordner
`profiles` neben der EXE. Eine gültige externe Datei mit derselben `id` kann
das eingebettete Profil ersetzen. Ungültige Dateien werden übersprungen und
als Warnung gemeldet.

Schema-Version 1:

```json
{
  "schema_version": 1,
  "id": "4litegen2_itde_with_turn_signal",
  "display_name": "4 Lite Gen2 DE/IT Version with turn Signals",
  "baudrate": 115200,
  "protocol": "leqi_serial_write_v1",
  "wire_separator": "",
  "regions": {
    "DE": "53777",
    "EU": "53937",
    "US": null
  }
}
```

Regeln:

- `schema_version` ist exakt `1`.
- `id` ist eindeutig.
- `baudrate` ist `19200` oder `115200`.
- `protocol` ist exakt `leqi_serial_write_v1`.
- `wire_separator` ist `""` oder `"/"`.
- `regions` enthält `DE`, `EU` und `US`.
- Jeder verfügbare Präfix besteht aus exakt fünf Ziffern. `null` deaktiviert
  die Region.

Profile steuern sicherheitsrelevante Bytes. Verwende nur geprüfte Dateien.
Änderungen werden erst nach einem Neustart der App geladen.

## Aus dem Quellcode starten

Voraussetzungen: Windows x64, CPython 3.12 in AMD64/x64 und ein passender
UART-Treiber.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\pythonw.exe ".\LEQI Region Changer.pyw"
```

Die Laufzeitabhängigkeiten sind fest gepinnt:

- `pyserial==3.5`
- `Pillow==12.3.0`

Auch PyInstaller und sämtliche direkten Buildabhängigkeiten sind in
`requirements-build.txt` versionsgenau festgelegt. Das Buildskript setzt einen
festen Quellzeitpunkt und erzeugt das ZIP in stabiler Dateireihenfolge mit
festen Zeitstempeln.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Die Tests decken Profilvalidierung, Seriennummern-Normalisierung,
Frameaufbau, CRC, Transaktionsreihenfolge, Diagnoseparser und UI-Zustände ab.
Ein realer Scooter-Hardwaretest bleibt für jedes Profil erforderlich.

## Windows-x64-Release bauen

Der Build benötigt Windows x64, CPython 3.12 AMD64/x64 und Internetzugang für
die gepinnten Pakete.

```powershell
.\build.ps1
# oder mit einem expliziten Python-3.12-x64-Pfad:
.\build.ps1 -PythonPath "C:\Pfad\zu\python.exe"
```

Das Skript:

1. entfernt ausschließlich projektinterne Buildausgaben und erstellt
   `.venv-build` neu;
2. installiert `requirements-build.txt`;
3. führt alle `unittest`-Tests aus;
4. baut mit `PyInstaller==6.21.0` eine fensterbasierte Onefile-EXE und prüft
   PE-Architektur, eingebettete Profile, Bilder, Schriften, Imports sowie den
   vollständigen Tcl/Tk-Fensteraufbau;
5. legt EXE, externe Profile, README, Lizenz sowie vollständige
   Drittanbieter-Hinweise und -Lizenztexte in das Release-ZIP;
6. schreibt die SHA-256-Prüfsumme nach `release/SHA256SUMS.txt`.

Ergebnis:

```text
release/LEQI Region Changer.exe
release/LEQI-Region-Changer-V2.0.0-rc.1-win64.zip
release/SHA256SUMS.txt
```

Der Build veröffentlicht und signiert nichts.

### Signatur und SmartScreen

Für diesen Release liegt kein Code-Signing-Zertifikat vor. Die EXE ist deshalb
unsigniert und Windows SmartScreen kann beim ersten Start warnen. Lade sie nur
aus dem offiziellen GitHub-Release und vergleiche vorher die veröffentlichte
SHA-256-Summe. Eine SmartScreen-Warnung ist kein Geräte-ACK und ändert nichts an
den Hardware- und Verdrahtungsrisiken.

## Kontinuität zum bisherigen Tool

Der App-Name lautet ab Version 2 „LEQI Region Changer“. Das bestehende
GitHub-Repository und seine alten Releases bleiben erhalten, damit externe
Links weiter funktionieren:

<https://github.com/Jupoma/Xiaomi-4-Lite-Gen2-25km-h-Patcher/releases>

Vorhandene `V1.1`-Assets dürfen nicht ersetzt oder gelöscht werden. Version 2
wird als neuer Release veröffentlicht.

## Lizenz

Projektlizenz: [MIT](LICENSE). Hinweise zu gebündelten Komponenten und
Schriften stehen in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
