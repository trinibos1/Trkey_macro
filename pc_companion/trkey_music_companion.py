#!/usr/bin/env python3
"""Trkey Music Companion (beta).

Simple optional PC companion app for Arduino firmware.
- Sends now-playing metadata via NP_SET.
- Loads layer by name, e.g. `music` -> MODE music.
- Listens for APP_EVENT lines from firmware.
"""

import argparse
import json
import queue
import sys
import threading
import time

try:
    import serial
    from serial.tools import list_ports
except Exception:
    print("Missing dependency: pyserial. Install with: pip install pyserial")
    sys.exit(1)


def list_serial_ports():
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return
    print("Available ports:")
    for p in ports:
        print(f"- {p.device} ({p.description})")


def send_line(ser, line):
    ser.write((line.strip() + "\n").encode("utf-8"))


def reader_loop(ser, out_queue):
    while True:
        try:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            out_queue.put(line)
        except Exception as exc:
            out_queue.put(f"[reader-error] {exc}")
            return


def handle_incoming(line):
    if line.startswith("APP_EVENT "):
        action = line.split(" ", 1)[1]
        print(f"[APP_EVENT] {action}")
        return
    print(f"[DEVICE] {line}")


def run_cli(port, baud):
    ser = serial.Serial(port=port, baudrate=baud, timeout=0.2)
    print(f"Connected: {port} @ {baud}")
    print("Type 'help' for commands.")

    q = queue.Queue()
    t = threading.Thread(target=reader_loop, args=(ser, q), daemon=True)
    t.start()

    last_pump = time.time()

    try:
        while True:
            # drain incoming lines
            while True:
                try:
                    line = q.get_nowait()
                except queue.Empty:
                    break
                handle_incoming(line)

            # keep prompt responsive
            if time.time() - last_pump > 0.05:
                last_pump = time.time()

            cmd = input("trkey> ").strip()
            if not cmd:
                continue

            if cmd in {"quit", "exit"}:
                break

            if cmd == "help":
                print("Commands:")
                print("  ports                          # list available serial ports")
                print("  music                          # shortcut -> MODE music")
                print("  mode <name-or-index>           # send MODE command")
                print("  modes                          # list layer modes")
                print("  np <title>|<artist>|<p>|<d>|<source>")
                print("  clear                          # NP_CLEAR")
                print("  get                            # NP_GET")
                print("  send <raw-line>                # raw command")
                print("  quit                           # exit")
                continue

            if cmd == "ports":
                list_serial_ports()
                continue

            if cmd == "music":
                send_line(ser, "MODE music")
                continue

            if cmd == "modes":
                send_line(ser, "MODE LIST")
                continue

            if cmd.startswith("mode "):
                send_line(ser, f"MODE {cmd[5:].strip()}")
                continue

            if cmd == "clear":
                send_line(ser, "NP_CLEAR")
                continue

            if cmd == "get":
                send_line(ser, "NP_GET")
                continue

            if cmd.startswith("np "):
                payload_raw = cmd[3:]
                parts = payload_raw.split("|")
                while len(parts) < 5:
                    parts.append("")
                title, artist, pos, dur, source = [p.strip() for p in parts[:5]]
                try:
                    pos_i = int(pos) if pos else 0
                    dur_i = int(dur) if dur else 0
                except ValueError:
                    print("position/duration must be integers (seconds).")
                    continue
                payload = {
                    "title": title,
                    "artist": artist,
                    "position": pos_i,
                    "duration": dur_i,
                    "source": source,
                }
                send_line(ser, "NP_SET " + json.dumps(payload, separators=(",", ":")))
                continue

            if cmd.startswith("send "):
                send_line(ser, cmd[5:])
                continue

            print("Unknown command. Type 'help'.")
    finally:
        ser.close()


def main():
    parser = argparse.ArgumentParser(description="Trkey Music Companion beta")
    parser.add_argument("--port", help="Serial port (e.g. COM5 or /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--list-ports", action="store_true")
    args = parser.parse_args()

    if args.list_ports:
        list_serial_ports()
        return

    if not args.port:
        print("Missing --port. Use --list-ports to discover ports.")
        return

    run_cli(args.port, args.baud)


if __name__ == "__main__":
    main()
