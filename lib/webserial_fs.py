# usb_file_server.py

import os
import usb_cdc

class USBFileServer:
    def __init__(self, uart=None):
        # Use usb_cdc.data if available, otherwise fallback to console
        self.uart = uart if uart else (usb_cdc.data if usb_cdc.data else usb_cdc.console)
        self.buffer = b""
        self.receiving_file = False
        self.file = None
        self.filename = ""

    def poll(self):
        """Call this repeatedly inside your main loop."""
        if self.receiving_file:
            self._receive_file_data()
        else:
            self._read_command()

    def _read_command(self):
        while self.uart.in_waiting:
            char = self.uart.read(1)
            if char == b'\r':
                continue
            if char == b'\n':
                try:
                    cmd = self.buffer.decode().strip()
                    if cmd:
                        self._handle_command(cmd)
                except Exception as e:
                    self.uart.write(b"ERR: " + str(e).encode() + b"\n")
                self.buffer = b""
            else:
                self.buffer += char

    def _receive_file_data(self):
        if self.uart.in_waiting:
            data = self.uart.read(self.uart.in_waiting)
            self.buffer += data

            if b"<EOF>" in self.buffer:
                # split only once so leftover commands are preserved
                parts = self.buffer.split(b"<EOF>", 1)
                if self.file:
                    self.file.write(parts[0])
                    self.file.close()
                    self.file = None
                self.receiving_file = False
                self.uart.write(b"FILE RECEIVED\n")
                self.buffer = parts[1]

                # process any leftover command immediately
                if self.buffer.strip():
                    try:
                        self._handle_command(self.buffer.decode().strip())
                    except Exception as e:
                        self.uart.write(b"ERR: " + str(e).encode() + b"\n")
                    self.buffer = b""
            else:
                if self.file:
                    self.file.write(self.buffer)
                    self.buffer = b""  # flush after writing

    def _handle_command(self, cmd):
        if cmd == "LIST":
            try:
                self.uart.write(b"Files:\n")
                for f in os.listdir("/"):
                    self.uart.write((f + "\n").encode())
                self.uart.write(b"<END>\n")
            except Exception as e:
                self.uart.write(b"ERROR: " + str(e).encode() + b"\n")

        elif cmd.startswith("DEL "):
            fname = cmd[4:].strip()
            try:
                os.remove("/" + fname)
                self.uart.write(b"DELETED\n")
            except Exception as e:
                self.uart.write(b"ERROR: " + str(e).encode() + b"\n")

        elif cmd.startswith("PUT "):
            self.filename = cmd[4:].strip()
            try:
                self.file = open("/" + self.filename, "wb")
                self.receiving_file = True
                self.buffer = b""  # reset buffer for file data
                self.uart.write(b"READY\n")
            except Exception as e:
                self.uart.write(b"ERROR: " + str(e).encode() + b"\n")

        elif cmd.startswith("GET "):
            fname = cmd[4:].strip()
            try:
                with open("/" + fname, "rb") as f:
                    while True:
                        chunk = f.read(512)
                        if not chunk:
                            break
                        self.uart.write(chunk)
                self.uart.write(b"<EOF>\n")
            except Exception as e:
                self.uart.write(b"ERROR: " + str(e).encode() + b"\n")

        else:
            self.uart.write(b"UNKNOWN COMMAND\n")

