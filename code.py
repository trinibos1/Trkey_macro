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
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS

# === Globals / Config ===
WIDTH, HEIGHT = 128, 64
DEBOUNCE_TIME = 0.1
PRESS_DISPLAY_TIME = 0.3
REPEAT_DELAY = 0.4   # seconds before repeat starts
REPEAT_RATE = 0.05   # seconds between repeats

last_press_time = 0
pressed_index = None

# Layers
current_layer = 0
default_layer = 0
layers = []
grid_size = 3
physical_layout = []
macros = {}  # id -> sequence (string)

# Repeat tracking
repeat_active = [False] * 9
repeat_start = [0] * 9
repeat_last = [0] * 9

# Momentary layer tracking (per key)
mo_active = [False] * 9
mo_prev_layer = [0] * 9
mo_target_for_key = [None] * 9  # if this key is MO(x), store x

# === USB CDC State ===
uart = usb_cdc.console
cdc_buffer = b""
receiving_file = False
file = None
filename = ""
companion_connected = False

# === Optional companion app state ===
SHOW_NOW_PLAYING_TIMEOUT = 10.0
show_now_playing = False
last_now_playing_update = 0.0
now_playing = {
    "title": "",
    "artist": "",
    "position": 0,
    "duration": 0,
    "source": "",
}

# === Known consumer/media codes ===
consumer_map = {
    "PLAY_PAUSE": ConsumerControlCode.PLAY_PAUSE,
    "MUTE": ConsumerControlCode.MUTE,
    "VOLUME_DECREMENT": ConsumerControlCode.VOLUME_DECREMENT,
    "VOLUME_INCREMENT": ConsumerControlCode.VOLUME_INCREMENT,
    "SCAN_NEXT_TRACK": ConsumerControlCode.SCAN_NEXT_TRACK,
    "SCAN_PREVIOUS_TRACK": ConsumerControlCode.SCAN_PREVIOUS_TRACK,
    "STOP": ConsumerControlCode.STOP,
    "RECORD": ConsumerControlCode.RECORD,
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
kbd_layout = KeyboardLayoutUS(kbd)

# === Buttons ===
button_pins = [
    board.GP2, board.GP3, board.GP4,
    board.GP5, board.GP6, board.GP7,
    board.GP8, board.GP9, board.GP10
]
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

# === UI ===
key_labels = []
title_label = None
layer_group = None
now_playing_group = None
np_title_label = None
np_line_1 = None
np_line_2 = None
np_line_3 = None

app_action_fallback = {
    "APP_PLAY_PAUSE": "PLAY_PAUSE",
    "APP_NEXT": "SCAN_NEXT_TRACK",
    "APP_PREV": "SCAN_PREVIOUS_TRACK",
    "APP_MUTE": "MUTE",
    "APP_VOL_UP": "VOLUME_INCREMENT",
    "APP_VOL_DOWN": "VOLUME_DECREMENT",
}


def _fmt_seconds(value):
    try:
        total = max(0, int(value))
    except Exception:
        total = 0
    return f"{total // 60}:{total % 60:02d}"


def _truncate(text, length):
    text = str(text or "")
    if len(text) <= length:
        return text
    return text[: max(0, length - 1)] + "…"


def should_show_now_playing(now=None):
    if not show_now_playing:
        return False
    if now is None:
        now = time.monotonic()
    return (now - last_now_playing_update) <= SHOW_NOW_PLAYING_TIMEOUT


def render_layer_view(layer_index, pressed_idx=None):
    now_playing_group.hidden = True
    layer_group.hidden = False

    lyr = layers[layer_index]
    title_label.text = f"Layer: {lyr.get('name','?')} ({layer_index+1}/{len(layers)})"
    labels = lyr.get("labels", [])
    for i in range(9):
        lbl_text = safe_get(labels, i, "")
        txt = f"[{(lbl_text[:5]).center(5) if lbl_text else '     '}]"
        key_labels[i].text = txt
        key_labels[i].color = 0x00FF00 if i == pressed_idx else 0xFFFFFF


def render_now_playing_view():
    layer_group.hidden = True
    now_playing_group.hidden = False

    np_title_label.text = "Now Playing (Beta)"
    np_line_1.text = _truncate(now_playing.get("title", "No track"), 20)
    np_line_2.text = _truncate(now_playing.get("artist", "Unknown artist"), 20)

    pos = _fmt_seconds(now_playing.get("position", 0))
    dur = _fmt_seconds(now_playing.get("duration", 0))
    src = _truncate(now_playing.get("source", ""), 8)
    np_line_3.text = _truncate(f"{pos}/{dur} {src}".strip(), 20)

def init_ui():
    global key_labels, title_label
    global layer_group, now_playing_group
    global np_title_label, np_line_1, np_line_2, np_line_3
    if len(splash):
        splash.pop()

    layer_group = displayio.Group()
    title_label = label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=0, y=4)
    layer_group.append(title_label)

    cell_w, cell_h, start_x, start_y = 40, 16, 4, 22
    key_labels = []
    for i in range(9):
        lbl = label.Label(
            terminalio.FONT,
            text="",
            color=0xFFFFFF,
            x=start_x + (i % 3) * cell_w,
            y=start_y + (i // 3) * cell_h
        )
        key_labels.append(lbl)
        layer_group.append(lbl)

    now_playing_group = displayio.Group()
    np_title_label = label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=0, y=8)
    np_line_1 = label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=0, y=24)
    np_line_2 = label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=0, y=38)
    np_line_3 = label.Label(terminalio.FONT, text="", color=0x00FF00, x=0, y=52)
    now_playing_group.append(np_title_label)
    now_playing_group.append(np_line_1)
    now_playing_group.append(np_line_2)
    now_playing_group.append(np_line_3)
    now_playing_group.hidden = True

    splash.append(layer_group)
    splash.append(now_playing_group)

def safe_get(arr, idx, default=""):
    try:
        return arr[idx]
    except Exception:
        return default

def update_ui(layer_index, pressed_idx=None):
    if should_show_now_playing():
        render_now_playing_view()
    else:
        render_layer_view(layer_index, pressed_idx=pressed_idx)

# === JSON / Layers loader (per spec) ===
def normalize_keys_or_labels(arr, target_len):
    if not isinstance(arr, list):
        arr = []
    # pad or trim to target_len
    if len(arr) < target_len:
        arr = arr + [""] * (target_len - len(arr))
    elif len(arr) > target_len:
        arr = arr[:target_len]
    return arr

def load_layers():
    global layers, grid_size, physical_layout, macros, default_layer, current_layer
    try:
        with open("layers.json", "r") as f:
            data = json.load(f)

        if not isinstance(data, dict) or "layers" not in data:
            raise ValueError("layers.json must be an object with a 'layers' array")

        grid_size_in = data.get("grid_size", 3)
        # We keep hardware as 3x3, but use grid_size to validate/pad data
        if not isinstance(grid_size_in, int) or grid_size_in < 2 or grid_size_in > 5:
            grid_size_in = 3
        grid_size = grid_size_in

        physical_layout = data.get("physical_layout", [])
        raw_layers = data["layers"]
        if not isinstance(raw_layers, list) or not raw_layers:
            raise ValueError("layers[] is empty")

        target_len = grid_size * grid_size

        # Build layers with normalized keys/labels
        built_layers = []
        for lyr in raw_layers:
            if not isinstance(lyr, dict):
                continue
            name = lyr.get("name", "Layer")
            labels = normalize_keys_or_labels(lyr.get("labels", []), target_len)
            keys = normalize_keys_or_labels(lyr.get("keys", []), target_len)
            built_layers.append({"name": name, "labels": labels, "keys": keys, "macros": lyr.get("macros", [])})

        if not built_layers:
            raise ValueError("No valid layer entries parsed")

        layers = built_layers

        # Load macros from layer 0 (by spec, UI manages them there)
        macros = {}
        if layers and isinstance(layers[0].get("macros", []), list):
            for m in layers[0]["macros"]:
                try:
                    mid = int(m["id"])
                    macros[mid] = str(m.get("sequence", ""))
                except Exception:
                    pass

        # Reset layer indices safely
        default_layer = 0 if default_layer >= len(layers) else default_layer
        current_layer = 0 if current_layer >= len(layers) else current_layer

        print(f"Loaded layers.json: layers={len(layers)} grid={grid_size} keys_per_layer={grid_size*grid_size}")
    except Exception as e:
        print("Failed to load layers.json:", e)
        # Safe fallback: 1 error layer visible on UI
        layers = [{
            "name": "ERROR",
            "keys": [""] * 9,
            "labels": ["ERR"] * 9,
            "macros": []
        }]
        default_layer = 0
        current_layer = 0

# === Key utilities ===
def _to_keycode(name):
    """Map a token (e.g., 'CONTROL', 'ALT', 'A') to Keycode attr; returns None if not found."""
    if not name:
        return None
    n = name.upper()
    # Common synonyms
    if n in ("CTRL", "CONTROL"):
        n = "CONTROL"
    elif n in ("CMD", "GUI", "WIN", "WINDOWS", "COMMAND"):
        n = "GUI"
    elif n in ("SHIFT", "LSHIFT", "RSHIFT"):
        n = "SHIFT"
    elif n in ("ALT", "OPTION"):
        n = "ALT"

    return getattr(Keycode, n, None)

def parse_combo_name(name):
    """
    Parse strings like 'CONTROL_C' or 'LEFT_SHIFT_A' into a tuple of Keycodes.
    Returns tuple() if unknown.
    """
    try:
        parts = [p for p in name.split("_") if p]
        kc_list = []
        for p in parts:
            kc = _to_keycode(p)
            if kc is None:
                # Try direct Keycode attribute (e.g., ENTER, ESCAPE)
                kc = getattr(Keycode, p.upper(), None)
            if kc is None:
                return tuple()
            kc_list.append(kc)
        return tuple(kc_list)
    except Exception:
        return tuple()

def is_noop(val):
    return (val is None) or (val == "") or (val == "NO_OP")

def parse_layer_fn(name):
    """
    Detect layer switching functions and return (fn, target:int) or (None, None).
    Supports MO(x), TO(x), TT(x), DF(x).
    """
    if not isinstance(name, str) or "(" not in name or ")" not in name:
        return (None, None)
    prefix = name.split("(")[0].strip().upper()
    try:
        inside = name[name.index("(") + 1 : name.index(")")]
        target = int(inside)
    except Exception:
        return (None, None)
    if prefix in ("MO", "TO", "TT", "DF"):
        return (prefix, target)
    return (None, None)

# === Sending actions ===
def send_combo(kc_tuple, hold_time=0.05):
    if not kc_tuple:
        return
    try:
        # press all
        for k in kc_tuple:
            kbd.press(k)
        time.sleep(hold_time)
        # release all
        for k in kc_tuple:
            kbd.release(k)
    except Exception as e:
        print("Combo send error:", e)

def send_macro_sequence(seq):
    """
    If the sequence contains '+', treat it as a single combo (e.g., 'control+alt+t').
    Otherwise, type literal text.
    """
    try:
        s = seq.strip()
        if "+" in s:
            tokens = [t.strip().upper() for t in s.split("+") if t.strip()]
            kc_list = []
            for t in tokens:
                kc = _to_keycode(t)
                if kc is None:
                    # allow direct letters/numbers like 'T'
                    kc = getattr(Keycode, t, None)
                if kc is None:
                    print("Unknown token in macro combo:", t)
                    return
                kc_list.append(kc)
            send_combo(tuple(kc_list))
        else:
            # literal typing
            kbd_layout.write(s)
    except Exception as e:
        print("Macro sequence error:", e)


def send_companion_event(event, payload=""):
    if not companion_connected:
        return
    try:
        if payload:
            uart.write(f"{event} {payload}\n".encode())
        else:
            uart.write(f"{event}\n".encode())
    except Exception:
        pass


def handle_app_action(action):
    fallback = app_action_fallback.get(action, "")
    if fallback and fallback in consumer_map:
        try:
            consumer_control.send(consumer_map[fallback])
        except Exception as e:
            print("Companion fallback send error:", e)

    send_companion_event("APP_EVENT", action)


def set_now_playing(payload):
    global show_now_playing, last_now_playing_update
    if not isinstance(payload, dict):
        raise ValueError("NP_SET payload must be a JSON object")

    now_playing["title"] = str(payload.get("title", ""))
    now_playing["artist"] = str(payload.get("artist", ""))
    now_playing["source"] = str(payload.get("source", ""))
    now_playing["position"] = payload.get("position", 0)
    now_playing["duration"] = payload.get("duration", 0)
    last_now_playing_update = time.monotonic()
    show_now_playing = True

def handle_layer_fn(fn, target, key_index=None, on_press=True):
    """Apply layer switching behavior."""
    global current_layer, default_layer

    if fn == "MO":
        # Momentary: switch on press, revert on release
        if on_press:
            if key_index is not None:
                mo_prev_layer[key_index] = current_layer
                mo_active[key_index] = True
                mo_target_for_key[key_index] = target
            current_layer = min(max(target, 0), len(layers) - 1)
            update_ui(current_layer)
        else:
            if key_index is not None and mo_active[key_index]:
                current_layer = mo_prev_layer[key_index]
                mo_active[key_index] = False
                mo_target_for_key[key_index] = None
                update_ui(current_layer)
        return

    if on_press:
        if fn == "TO":
            current_layer = min(max(target, 0), len(layers) - 1)
            update_ui(current_layer)
        elif fn == "TT":
            # Toggle between default_layer and target
            tgt = min(max(target, 0), len(layers) - 1)
            current_layer = tgt if current_layer != tgt else default_layer
            update_ui(current_layer)
        elif fn == "DF":
            default_layer = min(max(target, 0), len(layers) - 1)
            current_layer = default_layer
            update_ui(current_layer)

def send_key_entry(entry, key_index=None, on_press=True, hold_time=0.05):
    """
    entry is a string from keys[].
    on_press=True for press edge; False for release edge (used for MO()).
    """
    if is_noop(entry):
        return

    # Layer functions
    fn, tgt = parse_layer_fn(entry)
    if fn:
        handle_layer_fn(fn, tgt, key_index=key_index, on_press=on_press)
        return

    # Consumer/media
    up = entry.upper()
    if up in consumer_map:
        if on_press:  # only send on initial press
            try:
                consumer_control.send(consumer_map[up])
            except Exception as e:
                print("Consumer send error:", e)
        return

    # Macros: "MACRO_X"
    if up.startswith("MACRO_"):
        if on_press:
            try:
                mid = int(up.split("_", 1)[1])
                seq = macros.get(mid, None)
                if seq:
                    send_macro_sequence(seq)
                else:
                    print(f"Macro id {mid} not found")
            except Exception as e:
                print("Macro parse error:", e)
        return

    # Companion app actions (optional)
    if up.startswith("APP_"):
        if on_press:
            handle_app_action(up)
        return

    # Combos like CONTROL_C or LEFT_SHIFT_A
    kc_tuple = parse_combo_name(up)
    if kc_tuple:
        if on_press:
            send_combo(kc_tuple, hold_time=hold_time)
        return

    # Single keycode (e.g., "A", "ENTER", "F1", etc.)
    try:
        kc = getattr(Keycode, up, None)
        if kc is None:
            print(f"Unknown key entry: {entry}")
            return
        if on_press:
            kbd.press(kc)
            time.sleep(hold_time)
            kbd.release(kc)
    except Exception as e:
        print(f"Key send error for {entry}: {e}")

# === USB CDC File Handling ===
def handle_command(cmd):
    global receiving_file, file, filename, companion_connected, show_now_playing
    cmd = cmd.strip()
    companion_connected = True

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
    elif cmd.startswith("NP_SET "):
        try:
            payload = json.loads(cmd[7:].strip())
            set_now_playing(payload)
            update_ui(current_layer)
            uart.write(b"NP_OK\n")
        except Exception as e:
            uart.write(f"ERROR: {e}\n".encode())
    elif cmd == "NP_CLEAR":
        show_now_playing = False
        update_ui(current_layer)
        uart.write(b"NP_CLEARED\n")
    elif cmd == "NP_GET":
        try:
            uart.write((json.dumps(now_playing) + "\n").encode())
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

    # Physical button to cycle layers (kept from your original)
    current_state = layer_switch_btn.value
    if last_layer_switch_state and not current_state:
        current_layer = (current_layer + 1) % len(layers)
        update_ui(current_layer)
        time.sleep(0.2)
    last_layer_switch_state = current_state

    # Key input handling with repeat + MO()
    for i, btn in enumerate(buttons):
        state = btn.value  # True = released (pull-up), False = pressed
        keyname = layers[current_layer]["keys"][i] if i < len(layers[current_layer]["keys"]) else ""

        if not state:
            # pressed
            if (now - button_times[i]) > DEBOUNCE_TIME:
                if not repeat_active[i]:
                    # First press edge
                    send_key_entry(keyname, key_index=i, on_press=True)
                    pressed_index = i
                    last_press_time = now
                    repeat_start[i] = now
                    repeat_last[i] = now
                    repeat_active[i] = True
                    update_ui(current_layer, pressed_index)
                else:
                    # hold repeat (skip repeats for MO keys)
                    fn, _tgt = parse_layer_fn(keyname)
                    if fn == "MO":
                        # Do nothing on hold; layer remains switched until release
                        pass
                    else:
                        if (now - repeat_start[i]) > REPEAT_DELAY and (now - repeat_last[i]) > REPEAT_RATE:
                            send_key_entry(keyname, key_index=i, on_press=True)
                            repeat_last[i] = now
                            pressed_index = i
                            update_ui(current_layer, pressed_index)
        else:
            # released
            if repeat_active[i]:
                # Release edge for momentary layer
                fn, _tgt = parse_layer_fn(keyname)
                if fn == "MO":
                    send_key_entry(keyname, key_index=i, on_press=False)
            repeat_active[i] = False

    if pressed_index is not None and (now - last_press_time) > PRESS_DISPLAY_TIME:
        pressed_index = None
        update_ui(current_layer)

    if show_now_playing and not should_show_now_playing(now):
        update_ui(current_layer)

    time.sleep(0.01)

