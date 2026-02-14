#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_TinyUSB.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <map>
#include <vector>

// ===== Display =====
static constexpr uint8_t OLED_ADDR = 0x3C;
static constexpr int SCREEN_WIDTH = 128;
static constexpr int SCREEN_HEIGHT = 64;
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// ===== Timing =====
static constexpr uint32_t DEBOUNCE_MS = 100;
static constexpr uint32_t PRESS_DISPLAY_MS = 300;
static constexpr uint32_t REPEAT_DELAY_MS = 400;
static constexpr uint32_t REPEAT_RATE_MS = 50;

// ===== Pins (RP2040 Pico wiring from CircuitPython build) =====
const uint8_t keyPins[9] = {2, 3, 4, 5, 6, 7, 8, 9, 10};
const uint8_t layerSwitchPin = 15;

// ===== TinyUSB HID =====
Adafruit_USBD_HID usb_hid;
uint8_t const hidReportDescriptor[] = {
  TUD_HID_REPORT_DESC_KEYBOARD(HID_REPORT_ID(1)),
  TUD_HID_REPORT_DESC_CONSUMER(HID_REPORT_ID(2))
};
static constexpr uint8_t KEYBOARD_REPORT_ID = 1;
static constexpr uint8_t CONSUMER_REPORT_ID = 2;

// ===== Config models =====
struct MacroDef {
  int id = -1;
  String sequence;
};

struct Layer {
  String name;
  String labels[9];
  String keys[9];
};

std::vector<Layer> layers;
std::map<int, String> macros;
int currentLayer = 0;
int defaultLayer = 0;

// ===== Key state =====
bool repeatActive[9] = {false};
uint32_t repeatStart[9] = {0};
uint32_t repeatLast[9] = {0};
uint32_t keyDebounceStart[9] = {0};

bool moActive[9] = {false};
int moPrevLayer[9] = {0};
int moTargetForKey[9] = {0};

int pressedIndex = -1;
uint32_t lastPressMs = 0;
bool lastLayerSwitchState = true;

// ===== CDC file transfer state =====
bool receivingFile = false;
File putFile;
String putFilename;
String serialLineBuffer;
uint8_t eofWindow[5] = {0};
uint8_t eofWindowLen = 0;
bool fsReady = false;
bool discardingUpload = false;

// ===== HID maps =====
std::map<String, uint8_t> keyMap;
std::map<String, uint16_t> consumerMap;

String normalizePathArg(const String& rawArg) {
  String f = rawArg;
  f.trim();
  while (f.startsWith("/")) {
    f.remove(0, 1);
  }
  if (!f.length()) {
    return String("/");
  }
  return String("/") + f;
}


const char* defaultLayersJson() {
  return R"JSON({"grid_size":3,"layers":[{"name":"Layer 0","labels":["A","B","C","D","E","F","G","H","I"],"keys":["A","B","C","D","E","F","G","H","I"]}]})JSON";
}

void writeDefaultLayersFile() {
  if (LittleFS.exists("/layers.json")) {
    return;
  }

  File f = LittleFS.open("/layers.json", "w");
  if (!f) {
    return;
  }

  f.print(defaultLayersJson());
  f.close();
}


void sendLine(const char* msg) {
  Serial.print(msg);
  Serial.print("\n");
  Serial.flush();
}

void sendEOFMarker() {
  Serial.write(reinterpret_cast<const uint8_t*>("<EOF>\n"), 6);
  Serial.flush();
}

void initKeyMaps() {
  keyMap["A"] = HID_KEY_A; keyMap["B"] = HID_KEY_B; keyMap["C"] = HID_KEY_C;
  keyMap["D"] = HID_KEY_D; keyMap["E"] = HID_KEY_E; keyMap["F"] = HID_KEY_F;
  keyMap["G"] = HID_KEY_G; keyMap["H"] = HID_KEY_H; keyMap["I"] = HID_KEY_I;
  keyMap["J"] = HID_KEY_J; keyMap["K"] = HID_KEY_K; keyMap["L"] = HID_KEY_L;
  keyMap["M"] = HID_KEY_M; keyMap["N"] = HID_KEY_N; keyMap["O"] = HID_KEY_O;
  keyMap["P"] = HID_KEY_P; keyMap["Q"] = HID_KEY_Q; keyMap["R"] = HID_KEY_R;
  keyMap["S"] = HID_KEY_S; keyMap["T"] = HID_KEY_T; keyMap["U"] = HID_KEY_U;
  keyMap["V"] = HID_KEY_V; keyMap["W"] = HID_KEY_W; keyMap["X"] = HID_KEY_X;
  keyMap["Y"] = HID_KEY_Y; keyMap["Z"] = HID_KEY_Z;

  keyMap["ONE"] = HID_KEY_1; keyMap["TWO"] = HID_KEY_2; keyMap["THREE"] = HID_KEY_3;
  keyMap["FOUR"] = HID_KEY_4; keyMap["FIVE"] = HID_KEY_5; keyMap["SIX"] = HID_KEY_6;
  keyMap["SEVEN"] = HID_KEY_7; keyMap["EIGHT"] = HID_KEY_8; keyMap["NINE"] = HID_KEY_9;
  keyMap["ZERO"] = HID_KEY_0;

  keyMap["ENTER"] = HID_KEY_ENTER;
  keyMap["ESCAPE"] = HID_KEY_ESCAPE;
  keyMap["TAB"] = HID_KEY_TAB;
  keyMap["SPACE"] = HID_KEY_SPACE;
  keyMap["MINUS"] = HID_KEY_MINUS;
  keyMap["EQUAL"] = HID_KEY_EQUAL;
  keyMap["BACKSPACE"] = HID_KEY_BACKSPACE;

  keyMap["CONTROL"] = HID_KEY_CONTROL_LEFT;
  keyMap["CTRL"] = HID_KEY_CONTROL_LEFT;
  keyMap["SHIFT"] = HID_KEY_SHIFT_LEFT;
  keyMap["ALT"] = HID_KEY_ALT_LEFT;
  keyMap["GUI"] = HID_KEY_GUI_LEFT;

  consumerMap["PLAY_PAUSE"] = HID_USAGE_CONSUMER_PLAY_PAUSE;
  consumerMap["MUTE"] = HID_USAGE_CONSUMER_MUTE;
  consumerMap["VOLUME_INCREMENT"] = HID_USAGE_CONSUMER_VOLUME_INCREMENT;
  consumerMap["VOLUME_DECREMENT"] = HID_USAGE_CONSUMER_VOLUME_DECREMENT;
#if defined(HID_USAGE_CONSUMER_SCAN_NEXT)
  consumerMap["SCAN_NEXT_TRACK"] = HID_USAGE_CONSUMER_SCAN_NEXT;
#elif defined(HID_USAGE_CONSUMER_SCAN_NEXT_TRACK)
  consumerMap["SCAN_NEXT_TRACK"] = HID_USAGE_CONSUMER_SCAN_NEXT_TRACK;
#endif
#if defined(HID_USAGE_CONSUMER_SCAN_PREVIOUS)
  consumerMap["SCAN_PREVIOUS_TRACK"] = HID_USAGE_CONSUMER_SCAN_PREVIOUS;
#elif defined(HID_USAGE_CONSUMER_SCAN_PREVIOUS_TRACK)
  consumerMap["SCAN_PREVIOUS_TRACK"] = HID_USAGE_CONSUMER_SCAN_PREVIOUS_TRACK;
#endif
  consumerMap["STOP"] = HID_USAGE_CONSUMER_STOP;
}

bool isNoop(const String& s) {
  return s.length() == 0 || s == "NO_OP";
}

void drawUI(int layerIdx, int activeIdx = -1) {
  if (layers.empty()) return;

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);

  display.setCursor(0, 0);
  display.print("Layer: ");
  display.print(layers[layerIdx].name);
  display.print(" ");
  display.print(layerIdx + 1);
  display.print("/");
  display.print(layers.size());

  // improved UI: cell outlines + centered short labels
  const int startX = 2;
  const int startY = 14;
  const int cellW = 41;
  const int cellH = 16;

  for (int i = 0; i < 9; i++) {
    int x = startX + (i % 3) * cellW;
    int y = startY + (i / 3) * cellH;

    display.drawRect(x, y, 39, 14, SSD1306_WHITE);
    if (i == activeIdx) {
      display.fillRect(x + 1, y + 1, 37, 12, SSD1306_WHITE);
      display.setTextColor(SSD1306_BLACK);
    } else {
      display.setTextColor(SSD1306_WHITE);
    }

    String txt = layers[layerIdx].labels[i];
    if (txt.length() > 5) txt = txt.substring(0, 5);
    int cursorX = x + 2;
    int cursorY = y + 4;
    display.setCursor(cursorX, cursorY);
    display.print(txt);
  }

  display.display();
}

void sendKeyboardReport(uint8_t modifiers, uint8_t keys[6]) {
  usb_hid.keyboardReport(KEYBOARD_REPORT_ID, modifiers, keys);
}

void tapKey(uint8_t keycode) {
  uint8_t keys[6] = {keycode, 0, 0, 0, 0, 0};
  sendKeyboardReport(0, keys);
  delay(50);
  uint8_t empty[6] = {0, 0, 0, 0, 0, 0};
  sendKeyboardReport(0, empty);
}

bool parseLayerFn(const String& in, String& fn, int& target) {
  int p1 = in.indexOf('(');
  int p2 = in.indexOf(')');
  if (p1 < 0 || p2 < 0 || p2 <= p1 + 1) return false;

  fn = in.substring(0, p1);
  fn.toUpperCase();
  target = in.substring(p1 + 1, p2).toInt();
  return fn == "MO" || fn == "TO" || fn == "TT" || fn == "DF";
}

void typeText(const String& text) {
  for (size_t i = 0; i < text.length(); i++) {
    char c = text[i];
    // Lightweight ASCII typing fallback
    if (c >= 'a' && c <= 'z') tapKey(HID_KEY_A + (c - 'a'));
    else if (c >= 'A' && c <= 'Z') {
      uint8_t keys[6] = {static_cast<uint8_t>(HID_KEY_A + (c - 'A')), 0, 0, 0, 0, 0};
      sendKeyboardReport(KEYBOARD_MODIFIER_LEFTSHIFT, keys);
      delay(50);
      uint8_t empty[6] = {0, 0, 0, 0, 0, 0};
      sendKeyboardReport(0, empty);
    }
    else if (c == ' ') tapKey(HID_KEY_SPACE);
    else if (c == '\n') tapKey(HID_KEY_ENTER);
    else if (c >= '0' && c <= '9') tapKey(HID_KEY_0 + (c - '0'));
    delay(5);
  }
}

void sendCombo(const std::vector<uint8_t>& combo) {
  uint8_t modifiers = 0;
  uint8_t keys[6] = {0, 0, 0, 0, 0, 0};
  int keySlot = 0;

  for (uint8_t kc : combo) {
    switch (kc) {
      case HID_KEY_CONTROL_LEFT: modifiers |= KEYBOARD_MODIFIER_LEFTCTRL; break;
      case HID_KEY_SHIFT_LEFT: modifiers |= KEYBOARD_MODIFIER_LEFTSHIFT; break;
      case HID_KEY_ALT_LEFT: modifiers |= KEYBOARD_MODIFIER_LEFTALT; break;
      case HID_KEY_GUI_LEFT: modifiers |= KEYBOARD_MODIFIER_LEFTGUI; break;
      default:
        if (keySlot < 6) keys[keySlot++] = kc;
        break;
    }
  }

  sendKeyboardReport(modifiers, keys);
  delay(50);
  uint8_t empty[6] = {0, 0, 0, 0, 0, 0};
  sendKeyboardReport(0, empty);
}

void sendMacroSequence(const String& seq) {
  if (seq.indexOf('+') >= 0) {
    std::vector<uint8_t> combo;
    int start = 0;
    while (start < seq.length()) {
      int plus = seq.indexOf('+', start);
      String part = plus < 0 ? seq.substring(start) : seq.substring(start, plus);
      part.trim();
      part.toUpperCase();
      if (keyMap.count(part)) combo.push_back(keyMap[part]);
      start = plus < 0 ? seq.length() : plus + 1;
    }
    if (!combo.empty()) sendCombo(combo);
  } else {
    typeText(seq);
  }
}

void handleLayerFn(const String& fn, int target, int keyIndex, bool onPress) {
  target = constrain(target, 0, static_cast<int>(layers.size()) - 1);

  if (fn == "MO") {
    if (onPress) {
      moPrevLayer[keyIndex] = currentLayer;
      moActive[keyIndex] = true;
      moTargetForKey[keyIndex] = target;
      currentLayer = target;
      drawUI(currentLayer);
    } else if (moActive[keyIndex]) {
      currentLayer = moPrevLayer[keyIndex];
      moActive[keyIndex] = false;
      moTargetForKey[keyIndex] = 0;
      drawUI(currentLayer);
    }
    return;
  }

  if (!onPress) return;

  if (fn == "TO") {
    currentLayer = target;
  } else if (fn == "TT") {
    currentLayer = currentLayer == target ? defaultLayer : target;
  } else if (fn == "DF") {
    defaultLayer = target;
    currentLayer = target;
  }
  drawUI(currentLayer);
}

void sendKeyEntry(const String& rawEntry, int keyIndex, bool onPress) {
  String entry = rawEntry;
  entry.trim();
  if (isNoop(entry)) return;

  String fn;
  int target = 0;
  if (parseLayerFn(entry, fn, target)) {
    handleLayerFn(fn, target, keyIndex, onPress);
    return;
  }

  String up = entry;
  up.toUpperCase();

  if (consumerMap.count(up)) {
    if (onPress) usb_hid.sendReport16(CONSUMER_REPORT_ID, consumerMap[up]);
    delay(5);
    usb_hid.sendReport16(CONSUMER_REPORT_ID, 0);
    return;
  }

  if (up.startsWith("MACRO_")) {
    if (onPress) {
      int id = up.substring(6).toInt();
      if (macros.count(id)) sendMacroSequence(macros[id]);
    }
    return;
  }

  // combos like CONTROL_C
  if (up.indexOf('_') >= 0) {
    std::vector<uint8_t> combo;
    int start = 0;
    while (start < up.length()) {
      int sep = up.indexOf('_', start);
      String tok = sep < 0 ? up.substring(start) : up.substring(start, sep);
      tok.trim();
      if (keyMap.count(tok)) combo.push_back(keyMap[tok]);
      else {
        combo.clear();
        break;
      }
      start = sep < 0 ? up.length() : sep + 1;
    }

    if (onPress && !combo.empty()) sendCombo(combo);
    return;
  }

  if (onPress && keyMap.count(up)) tapKey(keyMap[up]);
}

void loadHardcodedSafeLayer() {
  layers.clear();
  Layer safe;
  safe.name = "Layer 0";

  const char* defaults[9] = {"A", "B", "C", "D", "E", "F", "G", "H", "I"};
  for (int i = 0; i < 9; i++) {
    safe.labels[i] = defaults[i];
    safe.keys[i] = defaults[i];
  }

  layers.push_back(safe);
  macros.clear();
  currentLayer = 0;
  defaultLayer = 0;
}

int parseMacroId(JsonObject mo) {
  if (!mo["id"].isNull()) {
    int id = mo["id"].as<int>();
    if (id >= 0) return id;
  }

  const char* macroName = mo["name"] | "";
  if (macroName && macroName[0]) {
    String name = String(macroName);
    name.trim();
    name.toUpperCase();
    if (name.startsWith("MACRO ")) {
      int parsed = name.substring(6).toInt();
      if (parsed > 0) {
        return parsed;
      }
    }
  }

  return -1;
}

void parseLayerArray(JsonArray arr) {
  layers.clear();
  for (JsonVariant v : arr) {
    if (!v.is<JsonObject>()) continue;
    JsonObject obj = v.as<JsonObject>();

    Layer l;
    l.name = obj["name"] | "Layer";

    JsonArray labels = obj["labels"].as<JsonArray>();
    JsonArray keys = obj["keys"].as<JsonArray>();
    for (int i = 0; i < 9; i++) {
      l.labels[i] = labels.isNull() || i >= labels.size() ? "" : String((const char*)labels[i]);
      l.keys[i] = keys.isNull() || i >= keys.size() ? "" : String((const char*)keys[i]);
    }

    if (layers.empty()) {
      JsonArray mArr = obj["macros"].as<JsonArray>();
      if (!mArr.isNull()) {
        for (JsonVariant m : mArr) {
          if (!m.is<JsonObject>()) continue;
          JsonObject mo = m.as<JsonObject>();
          int id = parseMacroId(mo);
          if (id < 0) continue;
          macros[id] = String((const char*)(mo["sequence"] | ""));
        }
      }
    }

    layers.push_back(l);
  }
}


bool loadLayersFromJsonDocument(DynamicJsonDocument& doc) {
  macros.clear();

  if (doc.is<JsonArray>()) {
    parseLayerArray(doc.as<JsonArray>());
  } else if (doc.is<JsonObject>() && doc["layers"].is<JsonArray>()) {
    parseLayerArray(doc["layers"].as<JsonArray>());
  }

  if (layers.empty()) {
    return false;
  }

  currentLayer = constrain(currentLayer, 0, static_cast<int>(layers.size()) - 1);
  defaultLayer = constrain(defaultLayer, 0, static_cast<int>(layers.size()) - 1);
  return true;
}

bool loadBuiltinDefaultLayers() {
  DynamicJsonDocument doc(2048);
  auto err = deserializeJson(doc, defaultLayersJson());
  if (err) {
    return false;
  }
  return loadLayersFromJsonDocument(doc);
}

void loadLayers() {
  macros.clear();

  if (!fsReady) {
    if (!loadBuiltinDefaultLayers()) {
      loadHardcodedSafeLayer();
    }
    return;
  }

  if (!LittleFS.exists("/layers.json")) {
    writeDefaultLayersFile();
  }

  File f = LittleFS.open("/layers.json", "r");
  if (!f) {
    if (!loadBuiltinDefaultLayers()) {
      loadHardcodedSafeLayer();
    }
    return;
  }

  DynamicJsonDocument doc(16384);
  auto err = deserializeJson(doc, f);
  f.close();

  if (err || !loadLayersFromJsonDocument(doc)) {
    Serial.println("layers.json parse failed; loading safe defaults");
    // Keep firmware usable and UI readable even if uploaded JSON is malformed.
    if (!loadBuiltinDefaultLayers()) {
      loadHardcodedSafeLayer();
    }
  }
}

void handleCommand(const String& cmdRaw) {
  String cmd = cmdRaw;
  cmd.trim();

  if (discardingUpload) {
    return;
  }

  if (cmd == "LIST") {
    sendLine("Files:");
    if (!fsReady) {
      sendLine("layers.json");
      sendLine("<END>");
      return;
    }
    File root = LittleFS.open("/", "r");
    if (!root) {
      sendLine("layers.json");
      sendLine("<END>");
      return;
    }
    File f = root.openNextFile();
    while (f) {
      Serial.println(f.name());
      f = root.openNextFile();
    }
    sendLine("<END>");
    return;
  }

  if (cmd.startsWith("DEL ")) {
    String fn = normalizePathArg(cmd.substring(4));
    if (!fsReady) {
      sendLine("ERROR");
      return;
    }
    sendLine(LittleFS.remove(fn) ? "DELETED" : "ERROR");
    return;
  }

  if (cmd.startsWith("GET ")) {
    String fn = normalizePathArg(cmd.substring(4));

    if (!fsReady) {
      if (fn == "/layers.json") {
        Serial.print(defaultLayersJson());
      }
      sendEOFMarker();
      return;
    }

    File f = LittleFS.open(fn, "r");
    if (!f) {
      if (fn == "/layers.json") {
        writeDefaultLayersFile();
        f = LittleFS.open(fn, "r");
      }
      if (!f) {
        if (fn == "/layers.json") {
          Serial.print(defaultLayersJson());
        }
        sendEOFMarker();
        return;
      }
    }
    while (f.available()) {
      uint8_t buf[256];
      size_t n = f.read(buf, sizeof(buf));
      Serial.write(buf, n);
    }
    f.close();
    sendEOFMarker();
    return;
  }

  if (cmd.startsWith("PUT ")) {
    putFilename = normalizePathArg(cmd.substring(4));
    if (fsReady) {
      putFile = LittleFS.open(putFilename, "w");
    }
    if (!putFile) {
      // Stay protocol-compatible: accept upload stream and discard it, then ACK.
      discardingUpload = true;
      receivingFile = true;
      eofWindowLen = 0;
      sendLine("READY");
      return;
    }
    receivingFile = true;
    eofWindowLen = 0;
    sendLine("READY");
    return;
  }

  if (cmd == "RELOAD") {
    loadLayers();
    drawUI(currentLayer);
    sendLine("LAYERS RELOADED");
    return;
  }

  sendLine("UNKNOWN COMMAND");
}

void processSerial() {
  while (Serial.available()) {
    uint8_t b = static_cast<uint8_t>(Serial.read());

    if (receivingFile) {
      // Windowed EOF detector for binary-safe streaming writes.
      eofWindow[eofWindowLen++] = b;
      if (eofWindowLen < 5) {
        continue;
      }

      if (eofWindow[0] == '<' && eofWindow[1] == 'E' && eofWindow[2] == 'O' && eofWindow[3] == 'F' && eofWindow[4] == '>') {
        if (putFile) {
          putFile.close();
        }
        receivingFile = false;
        eofWindowLen = 0;

        sendLine("FILE RECEIVED");
        if (discardingUpload) {
          discardingUpload = false;
          continue;
        }
        if (putFilename == "/layers.json") {
          loadLayers();
          drawUI(currentLayer);
          sendLine("LAYERS RELOADED");
        }
        continue;
      }

      // Not EOF marker: write oldest byte, keep last 4 for boundary matching.
      if (putFile) {
        putFile.write(eofWindow[0]);
      }
      for (uint8_t i = 1; i < 5; i++) {
        eofWindow[i - 1] = eofWindow[i];
      }
      eofWindowLen = 4;
      continue;
    }

    if (b == '\r') {
      continue;
    }

    if (b == '\n') {
      String cmd = serialLineBuffer;
      serialLineBuffer = "";
      cmd.trim();
      if (cmd.length()) {
        handleCommand(cmd);
      }
      continue;
    }

    serialLineBuffer += static_cast<char>(b);
  }
}


void setup() {
  Serial.begin(115200);

  initKeyMaps();

  for (int i = 0; i < 9; i++) {
    pinMode(keyPins[i], INPUT_PULLUP);
  }
  pinMode(layerSwitchPin, INPUT_PULLUP);

  Wire.setSDA(16);
  Wire.setSCL(17);
  Wire.begin();

  display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);

  // RP2040 Arduino core initializes TinyUSB; do not call tusb_init()/TinyUSBDevice.begin() here.
  usb_hid.setPollInterval(2);
  usb_hid.setReportDescriptor(hidReportDescriptor, sizeof(hidReportDescriptor));
  usb_hid.begin();

  if (!LittleFS.begin()) {
    LittleFS.format();
    fsReady = LittleFS.begin();
  } else {
    fsReady = true;
  }

  if (!fsReady) {
    loadHardcodedSafeLayer();
  } else {
    writeDefaultLayersFile();
    loadLayers();
  }
  drawUI(currentLayer);
}

void loop() {
  uint32_t now = millis();
  processSerial();

  bool layerState = digitalRead(layerSwitchPin);
  if (lastLayerSwitchState && !layerState && !layers.empty()) {
    currentLayer = (currentLayer + 1) % layers.size();
    drawUI(currentLayer);
    delay(200);
  }
  lastLayerSwitchState = layerState;

  for (int i = 0; i < 9; i++) {
    bool released = digitalRead(keyPins[i]);
    String keyname = layers.empty() ? "" : layers[currentLayer].keys[i];

    if (!released) {
      if (now - keyDebounceStart[i] > DEBOUNCE_MS) {
        if (!repeatActive[i]) {
          sendKeyEntry(keyname, i, true);
          repeatActive[i] = true;
          repeatStart[i] = now;
          repeatLast[i] = now;
          pressedIndex = i;
          lastPressMs = now;
          drawUI(currentLayer, pressedIndex);
        } else {
          String fn;
          int target;
          bool isLayerFn = parseLayerFn(keyname, fn, target);
          if (!(isLayerFn && fn == "MO") &&
              (now - repeatStart[i] > REPEAT_DELAY_MS) &&
              (now - repeatLast[i] > REPEAT_RATE_MS)) {
            sendKeyEntry(keyname, i, true);
            repeatLast[i] = now;
            pressedIndex = i;
            lastPressMs = now;
            drawUI(currentLayer, pressedIndex);
          }
        }
      }
    } else {
      if (repeatActive[i]) {
        String fn;
        int target;
        if (parseLayerFn(keyname, fn, target) && fn == "MO") {
          sendKeyEntry(keyname, i, false);
        }
      }
      repeatActive[i] = false;
      keyDebounceStart[i] = now;
    }
  }

  if (pressedIndex >= 0 && now - lastPressMs > PRESS_DISPLAY_MS) {
    pressedIndex = -1;
    drawUI(currentLayer);
  }

  delay(10);
}
