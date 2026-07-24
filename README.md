# LEQI Region Changer

**Your scooter. Your setup.**

Windows application for changing the five-digit region prefix of a supported
LEQI scooter serial number over UART. The individual 14-character serial suffix
is retained.

Current release: `2.0.0-rc.3`

App languages: `English` · `Deutsch` · `Italiano`

<p align="center">
  <img width="310" height="299" alt="Xiaomi 4 Lite Gen2 and region changer adapter" src="https://github.com/user-attachments/assets/f915855c-0402-415e-b324-46e709b6f3c0" />
</p>

https://github.com/user-attachments/assets/55039d4c-e917-4b10-b543-8c1bfe126adb

## Contents

- [Important notice](#important-notice)
- [Supported scooters](#supported-scooters)
- [Download](#download)
- [Hardware requirements](#hardware-requirements)
- [Adapter assembly](#adapter-assembly)
- [Use the Windows application](#use-the-windows-application)
- [Run from Python source](#run-from-python-source)
- [Serial-number handling](#serial-number-handling)
- [Diagnostics and protocol](#diagnostics-and-protocol)
- [Known limitations](#known-limitations)
- [Development and release build](#development-and-release-build)
- [License](#license)

## Important notice

This project is provided for educational and research purposes. It helps users
understand LEQI dashboard communication and region-dependent serial-number
prefixes. It is not an approval to operate a modified vehicle on public roads.

Changing a scooter region can affect road approval, permitted speed, insurance
and warranty. You are responsible for complying with all laws and technical
requirements that apply where the scooter is used.

Firmware or hardware modifications may introduce serious hazards, including
reduced braking performance, unstable handling, electrical failure, fire,
equipment damage or personal injury. The software is supplied without warranty.
Use it only if you understand the risks and accept responsibility for the
result.

> **SAFETY**
>
> Check the adapter pinout. Changing the region may affect road approval and
> warranty.

The dashboard wiring may carry approximately `21 V`. Never connect the dashboard
supply voltage to a USB-UART adapter or PC. Incorrect wiring can damage the
adapter, scooter and computer.

- Switch the scooter off before changing any wiring.
- Do not rely on cable colours.
- Identify every pin with a multimeter and continuity test.
- Check the UART adapter documentation, voltage selection and jumpers.
- Connect only lines whose function and electrical level are known.
- Select the exact scooter profile in the application. The model is not
  detected automatically.

This repository does not define a universal adapter pin table. Cable colours and
adapter layouts differ between manufacturers. The assembly images below are
reference material, not a substitute for measurement.

## Supported scooters

| Profile | UART | DE | EU | US | Wire separator |
| --- | ---: | --- | --- | --- | --- |
| Xiaomi 4 Lite Gen2 DE/IT version with turn signals | `115200` | `53777` | `53937` | Not available | None |
| Xiaomi 5 Plus | `19200` | `66232` | `66230` | `66227` | `/` |
| Xiaomi Electric Scooter 6 Lite | `19200` | `72367` | `72365` | `72364` | None |
| Xiaomi Electric Scooter 6 | `19200` | `72363` | `72361` | `72359` | `/` |
| Xiaomi Electric Scooter Elite | `19200` | `60543` | `60545` | `60457` | None |

The Xiaomi 4 Lite Gen2 remains the primary model documented in this repository.
An unavailable target has no confirmed prefix and stays disabled. Region labels
do not state where a scooter may legally be used.

The earlier V1 guide described the Xiaomi 4 Lite Gen2 region change as switching
between the German `20 km/h` setup and an EU setup commonly associated with
`25 km/h`. Actual behaviour depends on the original dashboard/controller
firmware. Version 2 therefore displays profile regions instead of promising a
specific speed.

## Download

Open the [GitHub Releases page](https://github.com/Jupoma/Xiaomi-4-Lite-Gen2-25km-h-Patcher/releases)
and download the assets for the same version.

| File | Purpose |
| --- | --- |
| `LEQI Region Changer.exe` | Standalone Windows application |
| `LEQI-Region-Changer-V2.0.0-rc.3-win64.zip` | EXE, profiles and license files |
| `LEQI-Region-Changer-V2.0.0-rc.3-source.zip` | Python source, tests, profiles, assets and build files |
| `SHA256SUMS.txt` | SHA-256 checksums for all three release assets |

Verify the checksum before starting the application:

```powershell
certutil -hashfile ".\LEQI Region Changer.exe" SHA256
```

Compare the result with `SHA256SUMS.txt`. The EXE is currently not code-signed,
so Windows SmartScreen may show a warning. A SmartScreen warning is not a
scooter response and does not confirm successful installation.

## Hardware requirements

- M8 5-pin male and female Juliet cables

  <img width="256" height="278" alt="M8 five-pin Juliet cables" src="https://github.com/user-attachments/assets/78916305-70db-42ce-a1c3-27727b477e10" />

- USB-C data cable, not a charge-only cable

  <img width="256" height="278" alt="USB-C data cable" src="https://github.com/user-attachments/assets/e0afd01d-6e9c-4b6e-a427-abf5ab463e31" />

- FT232RL or another suitable USB-UART adapter with documented electrical
  levels

  <img width="256" height="256" alt="FT232RL USB-to-UART adapter" src="https://github.com/user-attachments/assets/8c67be20-a4bb-4850-bbb7-dc3439205a92" />

### Tools

- Soldering iron and solder
- Multimeter with continuity mode
- Insulation and strain relief suitable for the cable
- Windows x64 PC
- Installed driver for the selected USB-UART adapter

## Adapter assembly

Do not assemble the adapter while it is connected to the scooter or PC.

1. Obtain the male and female M8 cables. Ordering both from one manufacturer may
   make their colour coding consistent, but never assume that it is correct.
2. Use continuity mode to identify pins `1` through `5` on both connectors.
3. Write down the measured colour-to-pin assignment for each cable.
4. Compare the result with the scooter harness and the documentation for the
   exact USB-UART adapter.
5. Keep the dashboard supply isolated from USB and UART logic.
6. Check every connection for shorts before connecting the PC.
7. Provide insulation and strain relief before using the adapter.

The required jumper configuration depends on the exact FT232RL board and wiring
design. Do not copy a jumper position from a photograph without checking the
board documentation. Diagnostic mode is read-only; a region write actively
transmits the serial-number and commit frames.

### Assembly reference images

<img width="1000" height="1875" alt="Adapter assembly reference overview" src="https://github.com/user-attachments/assets/4470429f-e0cb-47e2-941b-678d224de079" />

![Adapter cable continuity and connector reference](https://github.com/user-attachments/assets/7101d513-b023-4cbd-b63a-3253a9c50926)

<img width="1000" height="1575" alt="USB-UART adapter wiring reference" src="https://github.com/user-attachments/assets/77f7ce29-6f4d-4bef-96f0-bcd6dcd7600b" />

<img width="1000" height="3300" alt="Completed adapter assembly reference" src="https://github.com/user-attachments/assets/445a9ce4-297d-481d-8008-34eca8ef4ed2" />

## Use the Windows application

1. Download `LEQI Region Changer.exe` or extract the complete Windows ZIP.
2. Build and verify the adapter while the scooter and PC are disconnected.
3. Connect the verified adapter and switch on the scooter.
4. Start `LEQI Region Changer.exe`.
5. Choose `English`, `Deutsch` or `Italiano` in the header. A fresh installation
   starts in English.
6. Select the exact scooter profile.
7. Select the COM port assigned to the USB-UART adapter. It may be `COM3`, but
   the number depends on the PC.
8. Enter the complete current serial number.
9. Select a configured target region. The current region remains selectable and
   may deliberately be written again.
10. Check the preview, adapter pinout and serial number.
11. Confirm the safety checkbox and start the write.
12. Do not disconnect anything until the application reports that the COM port
    has been closed.
13. Switch the scooter off completely, restart it and verify the result.

The application does not read the existing serial number automatically. Copy it
exactly from a reliable source. A successful application message confirms local
write, flush and port-close operations only; the scooter does not provide a
reliable write acknowledgement for this procedure.

### Language setting

The chosen language is stored as `en`, `de` or `it` in:

```text
%LOCALAPPDATA%\Jupoma\LEQI Region Changer\settings.json
```

Missing, damaged or unreadable settings fall back to English. Changing the
language updates the application immediately and resets the safety confirmation.

## Run from Python source

Requirements:

- Windows x64
- CPython `3.12` AMD64/x64
- Driver for the selected USB-UART adapter

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\pythonw.exe ".\LEQI Region Changer.pyw"
```

Runtime dependencies are pinned:

- `pyserial==3.5`
- `Pillow==12.3.0`

## Serial-number handling

The accepted input format is:

```text
[0-9]{5}[A-Z0-9]{14}
```

One optional slash is allowed immediately after the first five digits:

```text
53777DXAN2F5QD02305
66232/DXAN2F5V101557
```

Version 2 replaces only the first five digits. The individual 14-character
suffix is retained byte-for-byte. A syntactically valid current prefix may be
unknown or already equal to the target prefix. Only target prefixes configured
in the selected profile can be written.

The two V1 limitations listed in the old guide no longer describe this release:

- The serial number is not intentionally cleared.
- The last serial character is included in the generated frame and covered by
  byte-exact golden-frame tests.

A changed region prefix remains traceable. It may affect approval and warranty.

## Diagnostics and protocol

The Diagnostics window opens the selected COM port in read-only mode. It parses
fragmented and combined `0x5A` frames, displays received bytes and validates
CRC-16/XMODEM. Diagnostics and writing use the same exclusive port lock and
cannot run at the same time.

A region change sends exactly one data frame:

```text
5A 01 97 LL 01 <serial number as ASCII> CRC_H CRC_L
```

After `100 ms`, it sends the commit frame exactly once:

```text
5A 01 97 01 00 EB B0
```

Both frames are written completely, flushed and followed by a port close. There
is no automatic retry and no readback. The commit frame is transmitted by the
application; it is not a received acknowledgement.

## Profile format

The application contains validated baseline profiles and can load approved JSON
overrides from a `profiles` folder beside the EXE.

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

Profile rules:

- `schema_version` is exactly `1`.
- `baudrate` is `19200` or `115200`.
- `protocol` is exactly `leqi_serial_write_v1`.
- `wire_separator` is `""` or `"/"`.
- `regions` contains exactly `DE`, `EU` and `US`.
- A supported prefix contains exactly five digits.
- `null` disables the target region.

Profile data controls safety-relevant transmitted bytes. Use only reviewed
files. Overrides are loaded after restarting the application.

## Known limitations

- The application does not detect the connected scooter model.
- The current serial number is not read automatically.
- The scooter does not provide a reliable write acknowledgement or readback.
- A local success message cannot prove permanent adoption by the dashboard.
- Dashboard or controller firmware changes may alter the result.
- Every profile still requires testing on the corresponding real scooter.
- The Windows EXE is not code-signed.

## Development and release build

Run the complete test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Build the reproducible Windows release:

```powershell
.\build.ps1

# Or specify CPython 3.12 AMD64/x64 explicitly:
.\build.ps1 -PythonPath "C:\Path\To\python.exe"
```

The build performs the unit tests, creates an AMD64 one-file EXE, runs the
embedded self-test and multilingual UI smoke test, and writes:

```text
release/LEQI Region Changer.exe
release/LEQI-Region-Changer-V2.0.0-rc.3-win64.zip
release/LEQI-Region-Changer-V2.0.0-rc.3-source.zip
release/SHA256SUMS.txt
```

The source archive contains the Python/PYW files, tests, profiles, required
assets, dependency lists, licenses and complete build recipe. It excludes local
settings, virtual environments, build output, Git metadata, bytecode and legacy
untracked files.

## Project history

Version 2 replaces the earlier single-model interface while keeping the existing
repository and V1 releases available for external links:

- [All releases](https://github.com/Jupoma/Xiaomi-4-Lite-Gen2-25km-h-Patcher/releases)
- [Full commit history](https://github.com/Jupoma/Xiaomi-4-Lite-Gen2-25km-h-Patcher/commits)

Do not overwrite or delete the existing V1.1 release assets when publishing
Version 2.

## License

Project source: [MIT License](LICENSE).

Bundled runtime components, libraries and fonts retain their respective
licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[`THIRD_PARTY_LICENSES`](THIRD_PARTY_LICENSES/).
