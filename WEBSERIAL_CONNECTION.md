# Trkey WebSerial Connection Guide

This document explains how the Trkey firmware connects to the web app (Trkey Mapper) over USB Serial and which command flow is expected.

## Overview

The Arduino firmware exposes a simple line-based protocol on USB CDC Serial (`Serial`) so the browser app can:

- list files
- read `layers.json`
- upload `layers.json`
- reload layers in runtime

The command handler is in `arduino/Trkey_macro.ino` (`handleCommand()` + `processSerial()`).

## Serial Protocol

All commands are newline-terminated text lines.

### 1) LIST

**App sends**

`LIST`

**Firmware replies**

- `Files:`
- one file per line
- `<END>`

If LittleFS is unavailable, firmware still returns:

- `layers.json`
- `<END>`

### 2) GET <file>

**App sends**

`GET layers.json`

**Firmware replies**

- raw file bytes
- `<EOF>` marker (sent as `<EOF>\n`)

If filesystem is unavailable:

- returns RAM-backed `layers.json` if one was uploaded in this session
- otherwise returns firmware default JSON

### 3) PUT <file>

**App sends**

`PUT layers.json`

**Firmware replies first**

`READY`

Then app streams file contents and terminates with:

`<EOF>`

**Firmware replies after EOF**

- `FILE RECEIVED`
- for `layers.json`, it then reloads and sends `LAYERS RELOADED`

### 4) RELOAD

**App sends**

`RELOAD`

**Firmware replies**

`LAYERS RELOADED`

## Why you may see "READY" + "FILE RECEIVED"

This is expected behavior for `PUT`:

1. firmware acknowledges upload start with `READY`
2. app sends bytes + `<EOF>`
3. firmware confirms write with `FILE RECEIVED`
4. firmware reloads config and emits `LAYERS RELOADED`

If the web app is currently waiting only for `FILE RECEIVED`, a delayed `READY` line can appear as an "unexpected line" in logs even though the flow is healthy.

## Persistence Behavior

- If LittleFS is available: uploaded `layers.json` is written to flash.
- If LittleFS is unavailable: uploaded `layers.json` is stored in RAM (`ramLayersJson`) for this runtime session.

That RAM-backed path allows `GET layers.json` and `RELOAD` to keep using the uploaded config even without filesystem access.

## Minimal App Upload Sequence (recommended)

1. Send `PUT layers.json`
2. Wait until `READY`
3. Send JSON bytes
4. Send `<EOF>`
5. Wait for `FILE RECEIVED`
6. Optionally wait for `LAYERS RELOADED`

## Troubleshooting

- If the device returns `UNKNOWN COMMAND`, verify each command is newline-terminated.
- If upload appears successful but config is unchanged, ensure app waits for `READY` before sending file bytes.
- If filesystem is unavailable, behavior is session-persistent only (RAM), not power-cycle persistent.
