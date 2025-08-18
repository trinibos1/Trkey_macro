# Trkey Macropad
## Overview

This is a **compact 3×3 macropad** built with **Raspberry Pi Pico / RP2040**, running **CircuitPython**. It connects via **USB** using the **Adafruit HID library**, allowing you to assign keyboard shortcuts, media keys, and macros. An **OLED display** shows layer and status information for easy feedback.

* **OLED Display:** [Amazon Link](https://a.co/d/afDOQYH)
* **PCB Design:** [OSH Park Project](https://oshpark.com/shared_projects/1jOtq57X)
* **Web Key Mapper:** [trinibos1/Trkey\_web](https://trinibos1.github.io/TRkey_mapper/)

---

## Features

* 3×3 Cherry MX Brown Hyperglide 45g tactile mechanical key matrix
* USB HID support (no Bluetooth)
* OLED display for layer/status feedback
* Tap/Hold functionality for advanced key actions
* Multiple layers for extended shortcut options
* Fast and responsive keypresses
* Simple wiring: switches connect directly to GND
* **All-in-one UF2:** CircuitPython, libraries, and firmware code included

---

## Hardware

| Component       | Details                                                                    |
| --------------- | -------------------------------------------------------------------------- |
| Microcontroller | Raspberry Pi Pico / RP2040                                                 |
| Switches        | 9x Cherry MX Brown Hyperglide 45g tactile                                  |
| Display         | OLED I2C 128x32 ([link](https://a.co/d/afDOQYH))                           |
| PCB             | Custom 3×3 macropad ([link](https://oshpark.com/shared_projects/1jOtq57X)) |
| Power           | USB only                                                                   |

PCB 
![PCB Image](https://via.placeholder.com/300x200.png?text=PCB+Layout)


---

## Firmware

**UF2 Firmware:**
![UF2 Badge](https://img.shields.io/badge/UF2-download-brightgreen)

* `macropad.uf2` — stable, all-in-one with CircuitPython, libraries, and code
* `dev_firmware.uf2` — development version for testing new features

**Key Features:** Tap/Hold, Layers, Media keys

---

## Usage

1. **Flash the UF2** (`macropad.uf2` or `dev_firmware.uf2`) onto your Pico — everything is included, no additional setup needed.
2. **Plug in the macropad** — ready to use.
3. **Use your macropad**:

   * Tap switches for primary actions
   * Hold switches for secondary actions or layer switching
   * OLED displays the current layer and status

---

## Web-Based Key Mapper

Customize your macropad's key bindings using the **web-based key mapper**:

* Full key remapping: Assign single keys or complex shortcuts to any of the 9 keys
* Multi-layer support: Configure multiple layers for extended functionality
* Macro support: Create macros for complex sequences
* Web Serial API: Communicate directly with your macropad via the browser

**Access the key mapper here:** [trinibos1/micropad\_web](https://github.com/trinibos1/micropad_web)

---

## Contributions

Contributions are welcome to **improve the key library**, including:

* Adding new key mappings or shortcuts
* Optimizing tap/hold behavior
* Enhancing multi-layer support
* Improving key response and stability

Submit issues or pull requests to collaborate.

---

## License

MIT License – see [LICENSE](LICENSE) for details.

