import board
import busio
import displayio
from adafruit_displayio_ssd1306 import SSD1306
from adafruit_display_text import label
import terminalio
import time
import json
import digitalio
import usb_hid
import usb_cdc
import os

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode

# === Globals ===
WIDTH, HEIGHT = 128, 64
DEBOUNCE_TIME = 0.1
PRESS_DISPLAY_TIME = 0.3
last_press_time = 0
pressed_index = None
current_layer = 0
layers = []

# Repeat behavior
REPEAT_DELAY = 0.4   # seconds before repeat starts
REPEAT_RATE = 0.05   # seconds between repeats
repeat_active = [False] * 9
repeat_start = [0] * 9
repeat_last = [0] * 9

# === USB CDC State ===
uart = usb_cdc.console
cdc_buffer = b""
receiving_file = False
file = None
filename = ""

# === Key Maps ===
keycode_map = {
    "CONTROL_C": (Keycode.CONTROL, Keycode.C),
    "CONTROL_V": (Keycode.CONTROL, Keycode.V),
    "CONTROL_Z": (Keycode.CONTROL, Keycode.Z),
    "CONTROL_X": (Keycode.CONTROL, Keycode.X),
    "CONTROL_S": (Keycode.CONTROL, Keycode.S),
    "CONTROL_F": (Keycode.CONTROL, Keycode.F),
    "CONTROL_Y": (Keycode.CONTROL, Keycode.Y),
}

consumer_map = {
    "PLAY_PAUSE": ConsumerControlCode.PLAY_PAUSE,
    "MUTE": ConsumerControlCode.MUTE,
    "VOLUME_DECREMENT": ConsumerControlCode.VOLUME_DECREMENT,
    "VOLUME_INCREMENT": ConsumerControlCode.VOLUME_INCREMENT,
    "SCAN_NEXT_TRACK": ConsumerControlCode.SCAN_NEXT_TRACK,
}

# === I2C Display ===
displayio.release_displays()
i2c = busio.I2C(board.GP17, board.GP16)
while not i2c.try_lock():
    pass
while 0x3C not in i2c.scan():
    print("Waiting for I2C display...")
    time.sleep(1)
i2c.unlock()

display_bus = displayio.I2CDisplay(i2c, device_address=0x3C)
display = SSD1306(display_bus, width=WIDTH, height=HEIGHT)
splash = displayio.Group()
display.root_group = splash

# === HID Devices ===
kbd = Keyboard(usb_hid.devices)
consumer_control = ConsumerControl(usb_hid.devices)

# === Buttons ===
button_pins = [board.GP2, board.GP3, board.GP4,
               board.GP5, board.GP6, board.GP7,
               board.GP8, board.GP9, board.GP10]
buttons = []
button_times = []
for pin in button_pins:
    btn = digitalio.DigitalInOut(pin)
    btn.direction = digitalio.Direction.INPUT
    btn.pull = digitalio.Pull.UP
    buttons.append(btn)
    button_times.append(0)

layer_switch_btn = digitalio.DigitalInOut(board.GP15)
layer_switch_btn.direction = digitalio.Direction.INPUT
layer_switch_btn.pull = digitalio.Pull.UP
last_layer_switch_state = True

# === Load Layers ===
def load_layers():
    global layers
    try:
        with open("layers.json", "r") as f:
            layers = json.load(f)
        if not isinstance(layers, list) or not layers:
            raise ValueError("Invalid format")
    except Exception as e:
        layers = [{"name": "ERROR", "keys": [""] * 9, "labels": ["ERR"] * 9}]
        print("Failed to load layers.json:", e)

# === UI ===
key_labels = []
title_label = None

def init_ui():
    global key_labels, title_label
    splash.pop() if len(splash) else None
    group = displayio.Group()
    title_label = label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=0, y=4)
    group.append(title_label)

    cell_w, cell_h, start_x, start_y = 40, 16, 4, 22
    key_labels = []
    for i in range(9):
        lbl = label.Label(terminalio.FONT, text="", color=0xFFFFFF,
                          x=start_x + (i % 3) * cell_w,
                          y=start_y + (i // 3) * cell_h)
        key_labels.append(lbl)
        group.append(lbl)
    splash.append(group)

def update_ui(layer_index, pressed_idx=None):
    layer = layers[layer_index]
    title_label.text = f"Layer: {layer['name']} ({layer_index+1}/{len(layers)})"
    for i in range(9):
        lbl_text = layer["labels"][i] if i < len(layer["labels"]) else ""
        key_labels[i].text = f"[{lbl_text.center(5) if lbl_text else '     '}]"
        key_labels[i].color = 0x00FF00 if i == pressed_idx else 0xFFFFFF

# === Key Send ===
def send_key(keyname, hold_time=0.05):
    if not keyname:
        return
    try:
        if keyname in keycode_map:
            combo = keycode_map[keyname]
            for k in combo:
                kbd.press(k)
            time.sleep(hold_time)
            for k in combo:
                kbd.release(k)
        elif keyname in consumer_map:
            consumer_control.send(consumer_map[keyname])
            time.sleep(hold_time)
        else:
            kc = getattr(Keycode, keyname, None)
            if kc is None:
                print(f"Unknown key: {keyname}")
                return
            kbd.press(kc)
            time.sleep(hold_time)
            kbd.release(kc)
    except Exception as e:
        print(f"Key send error for {keyname}: {e}")

# === USB CDC File Handling ===
def handle_command(cmd):
    global receiving_file, file, filename
    cmd = cmd.strip()
    if cmd == "LIST":
        uart.write(b"Files:\n")
        for f in os.listdir("/"):
            uart.write(f"{f}\n".encode())
        uart.write(b"<END>\n")
    elif cmd.startswith("DEL "):
        try:
            os.remove("/" + cmd[4:].strip())
            uart.write(b"DELETED\n")
        except Exception as e:
            uart.write(f"ERROR: {e}\n".encode())
    elif cmd.startswith("PUT "):
        try:
            filename = cmd[4:].strip()
            file = open("/" + filename, "wb")
            receiving_file = True
            uart.write(b"READY\n")
        except Exception as e:
            uart.write(f"ERROR: {e}\n".encode())
    elif cmd.startswith("GET "):
        try:
            with open("/" + cmd[4:].strip(), "rb") as f:
                while True:
                    chunk = f.read(512)
                    if not chunk:
                        break
                    uart.write(chunk)
            uart.write(b"<EOF>\n")
        except Exception as e:
            uart.write(f"ERROR: {e}\n".encode())
    elif cmd == "RELOAD":
        load_layers()
        update_ui(current_layer)
        uart.write(b"LAYERS RELOADED\n")
    else:
        uart.write(b"UNKNOWN COMMAND\n")

def process_usb_cdc():
    global cdc_buffer, receiving_file, file, filename
    if receiving_file and uart.in_waiting:
        data = uart.read(uart.in_waiting)
        if b"<EOF>" in data:
            parts = data.split(b"<EOF>")
            if file:
                file.write(parts[0])
                file.close()
                file = None
            receiving_file = False
            uart.write(b"FILE RECEIVED\n")
            if filename.strip() == "layers.json":
                try:
                    load_layers()
                    update_ui(current_layer)
                    uart.write(b"LAYERS RELOADED\n")
                except Exception as e:
                    uart.write(f"ERROR reloading layers: {e}\n".encode())
            cdc_buffer = parts[1] if len(parts) > 1 else b""
        else:
            if file:
                file.write(data)
        return
    if uart.in_waiting:
        char = uart.read(1)
        if char == b'\r':
            return
        if char == b'\n':
            try:
                handle_command(cdc_buffer.decode().strip())
            except Exception as e:
                uart.write(f"ERR: {e}\n".encode())
            cdc_buffer = b""
        else:
            cdc_buffer += char

# === Initialize ===
load_layers()
init_ui()
update_ui(current_layer)

# === Main Loop ===
while True:
    now = time.monotonic()
    process_usb_cdc()

    # Layer switch check
    current_state = layer_switch_btn.value
    if last_layer_switch_state and not current_state:
        current_layer = (current_layer + 1) % len(layers)
        update_ui(current_layer)
        time.sleep(0.2)
    last_layer_switch_state = current_state

    # Key input handling with repeat
    for i, btn in enumerate(buttons):
        state = btn.value
        if not state:
            if (now - button_times[i]) > DEBOUNCE_TIME:
                if not repeat_active[i]:
                    keyname = layers[current_layer]["keys"][i]
                    send_key(keyname)
                    pressed_index = i
                    last_press_time = now
                    repeat_start[i] = now
                    repeat_last[i] = now
                    repeat_active[i] = True
                    update_ui(current_layer, pressed_index)
                else:
                    # check repeat timing
                    if now - repeat_start[i] > REPEAT_DELAY and (now - repeat_last[i]) > REPEAT_RATE:
                        keyname = layers[current_layer]["keys"][i]
                        send_key(keyname)
                        repeat_last[i] = now
                        pressed_index = i
                        update_ui(current_layer, pressed_index)
        else:
            repeat_active[i] = False

    if pressed_index is not None and (now - last_press_time) > PRESS_DISPLAY_TIME:
        pressed_index = None
        update_ui(current_layer)

    time.sleep(0.01)

