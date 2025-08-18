from adafruit_hid.keycode import Keycode
from adafruit_hid.consumer_control_code import ConsumerControlCode

# Simple + combo key mappings
keycode_map = {
    "A": Keycode.A,
    "B": Keycode.B,
    "C": Keycode.C,
    "ENTER": Keycode.ENTER,
    "ESCAPE": Keycode.ESCAPE,
    "TAB": Keycode.TAB,
    "SPACE": Keycode.SPACE,
    "UP": Keycode.UP_ARROW,
    "DOWN": Keycode.DOWN_ARROW,
    "LEFT": Keycode.LEFT_ARROW,
    "RIGHT": Keycode.RIGHT_ARROW,
    "VOLUME_UP": ConsumerControlCode.VOLUME_INCREMENT,
    "VOLUME_DOWN": ConsumerControlCode.VOLUME_DECREMENT,
    "MUTE": ConsumerControlCode.MUTE,
    "PLAY_PAUSE": ConsumerControlCode.PLAY_PAUSE,

    # Combos
    "CTRL_C": (Keycode.CONTROL, Keycode.C),
    "CTRL_V": (Keycode.CONTROL, Keycode.V),
    "CTRL_Z": (Keycode.CONTROL, Keycode.Z),
    "CTRL_X": (Keycode.CONTROL, Keycode.X),
    "CTRL_S": (Keycode.CONTROL, Keycode.S),
    "ALT_TAB": (Keycode.ALT, Keycode.TAB),
    "WIN_D": (Keycode.WINDOWS, Keycode.D),
    "CTRL_SHIFT_ESC": (Keycode.CONTROL, Keycode.SHIFT, Keycode.ESCAPE),
}
