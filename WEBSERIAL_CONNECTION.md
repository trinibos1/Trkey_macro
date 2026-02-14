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
