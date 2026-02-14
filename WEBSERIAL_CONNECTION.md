# Trkey WebSerial + USB Connection Guide

This document explains how Trkey firmware communicates with the web app over USB Serial, how uploads are acknowledged, and how USB naming works.

## 1) USB Modes Used by Firmware

The firmware exposes:

- **USB HID** (keyboard + consumer/media reports)
- **USB CDC Serial** (line-based command channel used by Trkey Mapper)

At startup, firmware sets USB descriptor strings to:

- Manufacturer: `Trkey`
- Product: `Trkey`
- Serial: `TRKEY`

> Note: some OS UIs still show a generic serial path (`COMx`, `/dev/ttyACM*`, `/dev/cu.usbmodem*`) even when product/manufacturer strings are set correctly.

## 2) WebSerial Command Protocol

All commands are newline-terminated text lines.

### `LIST`

**Send:**

`LIST`

**Reply:**

- `Files:`
- one filename per line
- `<END>`

If LittleFS is unavailable, firmware still reports:
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

### `GET <file>`

**Send:**

`GET layers.json`

**Reply:**

- raw file bytes
- `<EOF>` marker (`<EOF>\n`)

When filesystem is unavailable:

- returns RAM-backed `layers.json` (if uploaded in this runtime), otherwise
- returns built-in default JSON.

### `PUT <file>`

**Send:**

`PUT layers.json`

**Immediate reply:**

`READY`

Then app sends file bytes and terminates stream with:

`<EOF>`

**Completion replies:**

- `FILE RECEIVED`
- for `layers.json`: `LAYERS RELOADED`

### `RELOAD`

**Send:**

`RELOAD`

**Reply:**

`LAYERS RELOADED`

### `DEL <file>`

Deletes a file from LittleFS. If FS is unavailable, returns `ERROR`.

## 3) Expected Upload Handshake

Recommended app flow:

1. Send `PUT layers.json`
2. Wait for `READY`
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

If `READY` appears as an "unexpected line" while waiting for `FILE RECEIVED`, that usually means your app state machine consumed lines out of phase. The firmware sequence above is expected.

## 4) Persistence Behavior

- **LittleFS available:** upload is persisted to flash.
- **LittleFS unavailable:** upload is stored in RAM for this runtime session.

RAM-backed config supports `GET layers.json` + `RELOAD`, but it is not power-cycle persistent.

## 5) JSON Compatibility Notes

Firmware accepts both:

- top-level array of layers, or
- object with a `layers` array (recommended)

It supports numeric key tokens (`"1".."0"`) and word aliases (`"ONE".."ZERO"`).

## 6) Troubleshooting

- `UNKNOWN COMMAND`: command is malformed or not newline-terminated.
- `FILE RECEIVED` never arrives: app did not send `<EOF>` marker correctly.
- Config reloads but seems unchanged: verify uploaded JSON parses and layer keys are valid tokens.
- Device name not updated: reflash and unplug/replug to force USB re-enumeration.
## Troubleshooting

- If the device returns `UNKNOWN COMMAND`, verify each command is newline-terminated.
- If upload appears successful but config is unchanged, ensure app waits for `READY` before sending file bytes.
- If filesystem is unavailable, behavior is session-persistent only (RAM), not power-cycle persistent.
