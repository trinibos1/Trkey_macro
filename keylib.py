import time
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode
from adafruit_hid.mouse import Mouse

class KeyLib:
    def __init__(self, keyboard: Keyboard, consumer: ConsumerControl, mouse: Mouse):
        self.kbd = keyboard
        self.consumer = consumer
        self.mouse = mouse

        self.aliases = {
            "CTRL": "CONTROL",
            "CONTROL": "CONTROL",
            "GUI": "GUI",
            "WIN": "GUI",
            "SHIFT": "SHIFT",
            "ALT": "ALT",
        }

        self.modifier_keys = {
            "CONTROL": Keycode.CONTROL,
            "SHIFT": Keycode.SHIFT,
            "ALT": Keycode.ALT,
            "GUI": Keycode.GUI,
        }

        self.keycode_map = {
            "CONTROL_C": (Keycode.CONTROL, Keycode.C),
            "CONTROL_V": (Keycode.CONTROL, Keycode.V),
            "CONTROL_Z": (Keycode.CONTROL, Keycode.Z),
            "CONTROL_X": (Keycode.CONTROL, Keycode.X),
            "CONTROL_S": (Keycode.CONTROL, Keycode.S),
            "CONTROL_F": (Keycode.CONTROL, Keycode.F),
            "CONTROL_Y": (Keycode.CONTROL, Keycode.Y),
        }

        self.consumer_map = {
            "PLAY_PAUSE": ConsumerControlCode.PLAY_PAUSE,
            "MUTE": ConsumerControlCode.MUTE,
            "VOLUME_DECREMENT": ConsumerControlCode.VOLUME_DECREMENT,
            "VOLUME_INCREMENT": ConsumerControlCode.VOLUME_INCREMENT,
            "SCAN_NEXT_TRACK": ConsumerControlCode.SCAN_NEXT_TRACK,
            "SCAN_PREVIOUS_TRACK": ConsumerControlCode.SCAN_PREVIOUS_TRACK,
        }

        self.mouse_actions = {
            "MOUSE_LEFT_CLICK": self.mouse_click_left,
            "MOUSE_RIGHT_CLICK": self.mouse_click_right,
            "MOUSE_MIDDLE_CLICK": self.mouse_click_middle,
        }

    def mouse_click_left(self):
        self.mouse.click(Mouse.LEFT_BUTTON)

    def mouse_click_right(self):
        self.mouse.click(Mouse.RIGHT_BUTTON)

    def mouse_click_middle(self):
        self.mouse.click(Mouse.MIDDLE_BUTTON)

    def mouse_move(self, x, y):
        self.mouse.move(x, y)

    def mouse_scroll(self, x, y):
        self.mouse.move(wheel=x, v=y)

    def send_key(self, keyname):
        if not keyname:
            return

        # Mouse commands
        if keyname in self.mouse_actions:
            self.mouse_actions[keyname]()
            return

        if keyname.startswith("MOUSE_MOVE_"):
            try:
                parts = keyname.split("_")
                x = int(parts[2])
                y = int(parts[3])
                self.mouse_move(x, y)
                return
            except Exception as e:
                print("Error parsing mouse move:", e)
                return

        if keyname.startswith("MOUSE_SCROLL_"):
            try:
                parts = keyname.split("_")
                x = int(parts[2])
                y = int(parts[3])
                self.mouse_scroll(x, y)
                return
            except Exception as e:
                print("Error parsing mouse scroll:", e)
                return

        # Consumer media keys
        if keyname in self.consumer_map:
            self.consumer.send(self.consumer_map[keyname])
            return

        # Keycode combos predefined
        if keyname in self.keycode_map:
            combo = self.keycode_map[keyname]
            for k in combo:
                self.kbd.press(k)
            self.kbd.release_all()
            return

        # Modifier combos like "CONTROL+X"
        if "+" in keyname:
            parts = keyname.split("+")
            try:
                keys = [self.aliases.get(k.upper(), k.upper()) for k in parts]
                codes = []
                for k in keys:
                    if k in self.modifier_keys:
                        codes.append(self.modifier_keys[k])
                    else:
                        kc = getattr(Keycode, k)
                        codes.append(kc)
                for code in codes:
                    self.kbd.press(code)
                self.kbd.release_all()
                return
            except Exception as e:
                print("Error sending combo:", e)
                return

        # Try as normal Keycode
        try:
            kc = getattr(Keycode, keyname.upper())
            self.kbd.press(kc)
            self.kbd.release_all()
        except AttributeError:
            self.type_string(keyname)

    def type_string(self, text, delay=0.02):
        for char in text:
            kc = self.char_to_keycode(char)
            if kc:
                self.kbd.press(kc)
                self.kbd.release_all()
                time.sleep(delay)
            else:
                if char == ' ':
                    self.kbd.press(Keycode.SPACE)
                    self.kbd.release_all()
                    time.sleep(delay)
                elif char == '\n':
                    self.kbd.press(Keycode.ENTER)
                    self.kbd.release_all()
                    time.sleep(delay)
                else:
                    print(f"Unsupported char '{char}' in typing.")

    def char_to_keycode(self, char):
        lookup = {
            'a': Keycode.A, 'b': Keycode.B, 'c': Keycode.C, 'd': Keycode.D,
            'e': Keycode.E, 'f': Keycode.F, 'g': Keycode.G, 'h': Keycode.H,
            'i': Keycode.I, 'j': Keycode.J, 'k': Keycode.K, 'l': Keycode.L,
            'm': Keycode.M, 'n': Keycode.N, 'o': Keycode.O, 'p': Keycode.P,
            'q': Keycode.Q, 'r': Keycode.R, 's': Keycode.S, 't': Keycode.T,
            'u': Keycode.U, 'v': Keycode.V, 'w': Keycode.W, 'x': Keycode.X,
            'y': Keycode.Y, 'z': Keycode.Z,
            '0': Keycode.ZERO, '1': Keycode.ONE, '2': Keycode.TWO, '3': Keycode.THREE,
            '4': Keycode.FOUR, '5': Keycode.FIVE, '6': Keycode.SIX, '7': Keycode.SEVEN,
            '8': Keycode.EIGHT, '9': Keycode.NINE,
            '.': Keycode.PERIOD, ',': Keycode.COMMA, '!': Keycode.ONE,
            '?': Keycode.SLASH, '-': Keycode.MINUS, '_': Keycode.MINUS,
            '@': Keycode.TWO, '#': Keycode.THREE, '$': Keycode.FOUR,
            '%': Keycode.FIVE, '^': Keycode.SIX, '&': Keycode.SEVEN,
            '*': Keycode.EIGHT, '(': Keycode.NINE, ')': Keycode.ZERO,
        }
        return lookup.get(char.lower(), None)

    def send_macro(self, macro_steps):
        for step in macro_steps:
            if isinstance(step, str) and step.startswith("DELAY_"):
                try:
                    ms = int(step.split("_")[1])
                    time.sleep(ms / 1000)
                except Exception as e:
                    print("Invalid delay in macro:", e)
            elif isinstance(step, str):
                self.send_key(step)
            elif isinstance(step, list):
                self.send_macro(step)
            else:
                print("Unknown macro step:", step)
