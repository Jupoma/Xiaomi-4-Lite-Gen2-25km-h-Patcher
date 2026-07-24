# LEQI Region Changer 2.0.0-rc.3

Status: Release Candidate für Windows x64.

## Neu in RC.3

- Neues Profil `6 Lite` mit `19200` Baud.
- Neues Profil `6` mit `19200` Baud.
- Beide Profile unterstützen DE, EU und US.
- 6 Lite sendet die Seriennummer ohne Slash.
- 6 sendet die Seriennummer mit Slash nach dem fünfstelligen Regionspräfix.

## Regionspräfixe

| Profil | DE | EU | US | UART-Trenner |
| --- | --- | --- | --- | --- |
| 6 Lite | `72367` | `72365` | `72364` | keiner |
| 6 | `72363` | `72361` | `72359` | `/` |

Der individuelle 14-stellige Seriennummernrest bleibt unverändert.

## Protokoll

Beide Modelle verwenden den bestehenden Ablauf:

```text
5A 01 97 LEN 01 <ASCII-SERIENNUMMER> CRC16-XMODEM
```

Nach `100 ms` folgt einmalig der Commit-Frame:

```text
5A 01 97 01 00 EB B0
```

Es gibt kein belastbares Schreib-ACK und keinen automatischen Retry. Nach der
Übertragung den Scooter vollständig neu starten und die Region prüfen.

## Release-Artefakte

```text
LEQI Region Changer.exe
LEQI-Region-Changer-V2.0.0-rc.3-win64.zip
LEQI-Region-Changer-V2.0.0-rc.3-source.zip
SHA256SUMS.txt
```

Die EXE ist nicht codesigniert. Prüfe vor dem Start die SHA-256-Summe.

## Hardwareabnahme

Die Profile basieren auf den Seriennummern und dem Schreibablauf aus
`LEQI_Tuning_Chip_Mi6Lite` und `LEQI_Tuning_Chip_Mi6`. Die vollständige
Hardwareabnahme für DE, EU und US bleibt vor einem stabilen `2.0.0` erforderlich.
