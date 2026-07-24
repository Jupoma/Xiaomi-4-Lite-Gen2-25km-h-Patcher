# LEQI Region Changer 2.0.0-rc.2

Status: Release Candidate für Windows x64.

## Neu in RC.2

- Freie Regionswahl für jede syntaktisch gültige Ausgangsseriennummer mit
  fünfstelligem Präfix.
- Unbekannte Ausgangspräfixe werden akzeptiert und durch den gewählten
  Profilpräfix ersetzt.
- Eine bereits vorhandene Region bleibt als `CURRENT`, `AKTUELL` oder
  `ATTUALE` markiert und kann bewusst erneut geschrieben werden.
- Der individuelle 14-stellige Seriennummernrest bleibt unverändert.
- Englisch ist die Erstsprache; Deutsch und Italienisch sind im Kopfbereich
  auswählbar.
- Sprachwechsel wirken sofort in Hauptfenster, Sicherheitshinweis,
  Statusmeldungen, Validierung, Dialogen, Diagnosefenster und Fehlermeldungen.
- Die Sprache wird unter
  `%LOCALAPPDATA%\Jupoma\LEQI Region Changer\settings.json` gespeichert.
  Fehlende oder defekte Einstellungen fallen ohne Startabbruch auf Englisch
  zurück.
- Die Sicherheitsbestätigung wird bei jedem tatsächlichen Sprachwechsel
  zurückgesetzt.

## Sicherheitstext

- English: “Check the adapter pinout. Changing the region may affect road
  approval and warranty.”
- Deutsch: „Prüfe die Pinbelegung vom Adapter. Eine Regionsänderung kann die
  Zulassung und Garantie betreffen.“
- Italiano: „Controlla la piedinatura dell’adattatore. La modifica della regione
  può influire sull’omologazione e sulla garanzia.“

Es wird keine konkrete Pin-Tabelle angezeigt, weil im Projekt keine bestätigte
Adapter-Pinbelegung hinterlegt ist.

## Unverändert

- Es sind nur die im gewählten Profil konfigurierten Zielregionen schreibbar.
  Ziele ohne Präfix bleiben deaktiviert.
- Baudrate, optionaler Slash, Frameaufbau, CRC-16/XMODEM, `100 ms` Pause,
  Commitframe, Einmalübertragung und Port-Sperren sind unverändert.
- Die App liest die Seriennummer nicht automatisch aus und erhält kein
  belastbares Schreib-ACK vom Scooter.

## Release-Artefakte

```text
LEQI Region Changer.exe
LEQI-Region-Changer-V2.0.0-rc.2-win64.zip
LEQI-Region-Changer-V2.0.0-rc.2-source.zip
SHA256SUMS.txt
```

Das Source-ZIP enthält die Python-/PYW-Dateien, Tests, Profile, Assets,
Lizenztexte und das reproduzierbare Windows-Buildrezept. Lokale Einstellungen,
Buildumgebungen und ungetrackte Altdateien sind ausgeschlossen.

Die EXE ist nicht codesigniert. Der Buildprozess veröffentlicht keine Dateien.
