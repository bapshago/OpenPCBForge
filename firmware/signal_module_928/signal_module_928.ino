// 928 Signal Module firmware (board rev A)
//
// Reads the 16 optocoupler inputs and the dash-dimmer voltage from the 1984
// Porsche 928 S cluster plugs and sends them on the EV CAN bus (500 kbit/s),
// one frame on a configurable ID (default 0x31B), next to the ID the 928
// Waveshare dash already uses for the ZombieVerter (0x31A).
//
// Board: AITRIP 38-pin ESP-32S (ESP-WROOM-32). In the Arduino IDE pick
// "ESP32 Dev Module" from the "esp32 by Espressif Systems" board package.
// No extra libraries: CAN uses the ESP32's built-in TWAI controller; the web
// pages, settings storage and firmware update use the core's WiFi, WebServer,
// Preferences and Update libraries.
//
// Web pages: the module runs its own Wi-Fi network. Join it from a phone or
// laptop and open http://192.168.4.1:
//   /          live status of every input, the dimmer and CAN (no login)
//   /settings  CAN ID, frame period, CAN mode, Wi-Fi name and password, Wi-Fi
//              auto-off (login: user "admin", password = the Wi-Fi password)
//   /update    firmware update from a .bin file (same login)
// Settings are kept in flash and survive power cycles and firmware updates.
// Locked out? Hold the ESP32's BOOT button for 5 s: settings go back to the
// defaults below and the module restarts.
//
// CAN bus safety (so this module can't upset the car's bus):
// - Single-shot transmission: a frame nobody acknowledges is dropped, never
//   repeated, so the module can't flood the bus the way an unacknowledged
//   frame does with automatic retransmission.
// - Listens for CAN_LISTEN_FIRST_MS after start-up before sending, and never
//   sends while another node is using the same ID (shown as an ID conflict).
// - After a bus-off it waits before rejoining, doubling the wait each time
//   (1 s up to 60 s), instead of rejoining at once.
// - "Listen only" mode never transmits or acknowledges: use it the first time
//   on a new bus to see which IDs are in use (listed on the status page).
// - IDs used elsewhere in the 928 EV (ZombieVerter, Leaf, heater) are refused.
//
// Hardware notes (see docs/signal_module_928_handoff.md):
// - Every input is active-LOW: the GPIO reads 0 when the 12 V signal is active.
//   That holds for high-side, low-side and universal channels alike; the
//   jumpers on CH1 and CH10-16 only change which wire drives the opto LED.
// - Pull-ups are on the board (10k to 3V3), so GPIO 34-39 (input-only, no
//   internal pull-ups) work fine.
// - Dash dimmer (cluster pin 14R) goes through a 47k / 10k divider to GPIO39.

#include "driver/twai.h"
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <Update.h>

// ----------------------------------------------------------------- CAN frame
// Frame layout (8 bytes, 11-bit ID from the settings, default 0x31B):
//   byte 0   CH1-CH8 active bits   (bit 0 = CH1 ... bit 7 = CH8), 1 = active
//   byte 1   CH9-CH16 active bits  (bit 0 = CH9 ... bit 7 = CH16)
//   byte 2-3 dash dimmer voltage, little-endian, 0.1 V/bit (same scaling the
//            dash already uses for 12 V in 0x31A)
//   byte 4   dash dimmer level, 0-100 % of DIMMER_FULL_SCALE_V
//   byte 5   rolling counter, +1 per frame (lets the dash spot a silent module)
//   byte 6   flags: bit 0 = turn signal flashing (an edge on CH1 within TURN_HOLD_MS)
//   byte 7   frame layout version (FRAME_VERSION)
const uint8_t FRAME_VERSION = 1;

// IDs other 928 EV nodes use or have reserved in the car's
// CAN plan. The settings page refuses them.
const uint16_t RESERVED_IDS[] = {0x188, 0x1DA, 0x1DB, 0x292, 0x31A, 0x31C, 0x31D, 0x31E,
                                 0x390, 0x398, 0x55A, 0x55B};

// ----------------------------------------------------------------- Settings
enum CanMode : uint8_t { CAN_MODE_SEND = 0, CAN_MODE_LISTEN = 1, CAN_MODE_OFF = 2 };
const char *const CAN_MODE_NAMES[] = {"send", "listen only", "off"};

struct Config {
  uint16_t canId;       // 11-bit standard ID
  uint16_t periodMs;    // periodic frame interval
  uint8_t canMode;      // CanMode
  uint16_t wifiOffMin;  // turn Wi-Fi off this long after the last client leaves; 0 = never
  char ssid[33];
  char pass[64];
};
// Defaults, also restored by holding BOOT for 5 s. Change the password from
// the settings page before the car goes on the road.
const Config DEFAULTS = {0x31B, 100, CAN_MODE_SEND, 0, "928-Signal-Module", "porsche928"};
Config cfg = DEFAULTS;

const char *const ADMIN_USER = "admin";
// Optional: also join a home network for bench work (leave "" to skip). The
// address it gets is printed on the serial port at start-up.
const char *const HOME_WIFI_SSID     = "";
const char *const HOME_WIFI_PASSWORD = "";

// ----------------------------------------------------------------- Pins
const int CAN_TX_PIN = 27;   // to SN65HVD230 D
const int CAN_RX_PIN = 25;   // from SN65HVD230 R
const int DIMMER_PIN = 39;   // ADC1 (works with Wi-Fi on)
const int BOOT_BUTTON_PIN   = 0;    // the DevKit's BOOT button; not used by the board

struct Channel {
  uint8_t pin;
  const char *name;
  const char *clusterPin;
  bool rawActive;        // latest reading
  bool active;           // debounced state, sent on CAN
  uint32_t rawChangedMs;
  uint32_t changes;      // debounced changes since start-up (shown on the web page)
};

// Index 0 = CH1. GPIOs match the board: designs/signal_module_928.py.
Channel channels[16] = {
  {34, "Turn signal",     "13L"},
  {35, "High beam",       "1M"},
  {32, "Lights on",       "6L"},
  {33, "Central warning", "5M"},
  {26, "Brake fluid",     "1R"},
  {14, "Brake pad wear",  "12R"},
  {13, "Brake warning",   "5R"},
  {16, "Parking brake",   "6R"},
  {17, "Washer fluid",    "10L"},
  {18, "Spare CH10",      "-"},
  {19, "Spare CH11",      "-"},
  {21, "Spare CH12",      "-"},
  {22, "Spare CH13",      "-"},
  {23, "Spare CH14",      "-"},
  {4,  "Spare CH15",      "-"},
  {36, "Spare CH16",      "-"},
};
const int NUM_CHANNELS = sizeof(channels) / sizeof(channels[0]);
const int TURN_CHANNEL = 0;  // CH1

// ----------------------------------------------------------------- Timing and scaling
const uint32_t DEBOUNCE_MS          = 20;     // input must hold this long to count
const uint32_t MIN_SEND_GAP_MS      = 10;     // cap on-change bursts at 100 frames/s
const uint32_t DIMMER_PERIOD_MS     = 50;
const uint32_t PRINT_PERIOD_MS      = 1000;   // serial status line for bench testing
const uint32_t TURN_HOLD_MS         = 1000;   // flasher is ~1.5 Hz; hold "flashing" between edges
const uint32_t CAN_LISTEN_FIRST_MS  = 1000;   // listen for an ID conflict before sending
const uint32_t BUS_OFF_WAIT_MIN_MS  = 1000;   // first wait before rejoining after bus-off
const uint32_t BUS_OFF_WAIT_MAX_MS  = 60000;
const uint32_t BUS_OFF_CLEAN_MS     = 60000;  // this long without bus-off resets the wait
const uint32_t FACTORY_RESET_MS     = 5000;   // hold BOOT this long
const uint32_t RESTART_DELAY_MS     = 1500;   // lets the "restarting" page reach the browser

const float DIMMER_DIVIDER      = (47.0f + 10.0f) / 10.0f;  // R4 47k over R5 10k
const float DIMMER_FULL_SCALE_V = 14.0f;                    // reads as 100 %

// ----------------------------------------------------------------- State
float dimmerVolts = 0;
uint8_t frameCounter = 0;
uint32_t lastTurnEdgeMs = 0;
bool turnEverSeen = false;
uint32_t lastSendMs = 0, lastDimmerMs = 0, lastPrintMs = 0;
uint32_t framesSent = 0, sendFailures = 0;
bool canRunning = false;
bool pendingChange = false;
uint32_t canStartMs = 0;
bool idConflict = false;           // another node sends our ID: stay silent until restart
uint32_t busOffCount = 0, busOffWaitMs = BUS_OFF_WAIT_MIN_MS, lastBusOffMs = 0;
bool recoveryPending = false;
uint32_t recoverAtMs = 0;

struct SeenId { uint32_t id; bool extd; uint32_t count; uint32_t lastMs; };
const int MAX_SEEN = 24;
SeenId seenIds[MAX_SEEN];
int numSeen = 0;

Preferences prefs;
WebServer server(80);
bool webRunning = false;
uint32_t lastClientMs = 0;
uint32_t restartAtMs = 0;          // 0 = no restart scheduled
uint32_t bootPressedMs = 0;
bool uploadAuthorized = false;

// ----------------------------------------------------------------- Settings storage
bool isReservedId(uint16_t id) {
  for (uint16_t r : RESERVED_IDS) {
    if (r == id) return true;
  }
  return false;
}

bool printableAscii(const char *s) {
  for (; *s; s++) {
    if (*s < 0x20 || *s > 0x7E) return false;
  }
  return true;
}

void loadConfig() {
  cfg = DEFAULTS;
  if (!prefs.begin("sm928", true)) {   // read-only; fails until the first save
    return;
  }
  Config c = DEFAULTS;
  c.canId = prefs.getUShort("canId", DEFAULTS.canId);
  c.periodMs = prefs.getUShort("period", DEFAULTS.periodMs);
  c.canMode = prefs.getUChar("canMode", DEFAULTS.canMode);
  c.wifiOffMin = prefs.getUShort("wifiOff", DEFAULTS.wifiOffMin);
  prefs.getString("ssid", c.ssid, sizeof(c.ssid));
  prefs.getString("pass", c.pass, sizeof(c.pass));
  prefs.end();
  // Anything out of range falls back to the default, field by field.
  if (c.canId >= 1 && c.canId <= 0x7FF) cfg.canId = c.canId;
  if (c.periodMs >= 20 && c.periodMs <= 1000) cfg.periodMs = c.periodMs;
  if (c.canMode <= CAN_MODE_OFF) cfg.canMode = c.canMode;
  if (c.wifiOffMin <= 240) cfg.wifiOffMin = c.wifiOffMin;
  if (c.ssid[0] && strlen(c.ssid) <= 32 && printableAscii(c.ssid)) strcpy(cfg.ssid, c.ssid);
  size_t n = strlen(c.pass);
  if (n >= 8 && n <= 63 && printableAscii(c.pass)) strcpy(cfg.pass, c.pass);
}

void saveConfig(const Config &c) {
  prefs.begin("sm928", false);
  prefs.putUShort("canId", c.canId);
  prefs.putUShort("period", c.periodMs);
  prefs.putUChar("canMode", c.canMode);
  prefs.putUShort("wifiOff", c.wifiOffMin);
  prefs.putString("ssid", c.ssid);
  prefs.putString("pass", c.pass);
  prefs.end();
}

void factoryReset() {
  prefs.begin("sm928", false);
  prefs.clear();
  prefs.end();
  Serial.println("Settings reset to defaults; restarting");
}

// Checks the settings form and fills `out`. Returns an error message, or
// nullptr when everything is valid. Empty password fields keep the current one.
const char *parseSettings(const Config &current, const char *canId, const char *period,
                          const char *mode, const char *ssid, const char *pass,
                          const char *pass2, const char *wifiOff, Config &out) {
  out = current;
  char *end;
  const char *idText = (canId[0] == '0' && (canId[1] == 'x' || canId[1] == 'X')) ? canId + 2 : canId;
  unsigned long id = strtoul(idText, &end, 16);
  if (!idText[0] || *end || id < 1 || id > 0x7FF) {
    return "CAN ID must be a hex number from 0x001 to 0x7FF.";
  }
  if (isReservedId((uint16_t)id)) {
    return "That CAN ID is used by another 928 EV node (ZombieVerter, Leaf or heater).";
  }
  unsigned long ms = strtoul(period, &end, 10);
  if (!period[0] || *end || ms < 20 || ms > 1000) {
    return "Frame period must be 20 to 1000 ms.";
  }
  unsigned long m = strtoul(mode, &end, 10);
  if (!mode[0] || *end || m > CAN_MODE_OFF) {
    return "Unknown CAN mode.";
  }
  unsigned long off = strtoul(wifiOff, &end, 10);
  if (!wifiOff[0] || *end || off > 240) {
    return "Wi-Fi auto-off must be 0 (never) to 240 minutes.";
  }
  size_t ssidLen = strlen(ssid);
  if (ssidLen < 1 || ssidLen > 32 || !printableAscii(ssid)) {
    return "Wi-Fi name must be 1 to 32 plain characters.";
  }
  if (pass[0] || pass2[0]) {
    size_t n = strlen(pass);
    if (n < 8 || n > 63 || !printableAscii(pass)) {
      return "Wi-Fi password must be 8 to 63 plain characters.";
    }
    if (strcmp(pass, pass2) != 0) {
      return "The two passwords don't match.";
    }
    strcpy(out.pass, pass);
  }
  out.canId = (uint16_t)id;
  out.periodMs = (uint16_t)ms;
  out.canMode = (uint8_t)m;
  out.wifiOffMin = (uint16_t)off;
  strcpy(out.ssid, ssid);
  return nullptr;
}

// ----------------------------------------------------------------- CAN
bool canBegin() {
  if (cfg.canMode == CAN_MODE_OFF) {
    Serial.println("CAN: off (settings)");
    return false;
  }
  twai_mode_t mode = cfg.canMode == CAN_MODE_LISTEN ? TWAI_MODE_LISTEN_ONLY : TWAI_MODE_NORMAL;
  twai_general_config_t general =
      TWAI_GENERAL_CONFIG_DEFAULT((gpio_num_t)CAN_TX_PIN, (gpio_num_t)CAN_RX_PIN, mode);
  general.tx_queue_len = 2;    // never build up a backlog of stale frames
  general.rx_queue_len = 16;   // received frames feed the ID list and conflict check
  twai_timing_config_t timing = TWAI_TIMING_CONFIG_500KBITS();
  twai_filter_config_t filter = TWAI_FILTER_CONFIG_ACCEPT_ALL();

  if (twai_driver_install(&general, &timing, &filter) != ESP_OK) {
    Serial.println("CAN: driver install failed");
    return false;
  }
  if (twai_start() != ESP_OK) {
    Serial.println("CAN: start failed");
    return false;
  }
  Serial.printf("CAN: %s at 500 kbit/s, ID 0x%03X\n", CAN_MODE_NAMES[cfg.canMode], (unsigned)cfg.canId);
  return true;
}

void noteSeenId(const twai_message_t &m, uint32_t now) {
  for (int i = 0; i < numSeen; i++) {
    if (seenIds[i].id == m.identifier && seenIds[i].extd == (bool)m.extd) {
      seenIds[i].count++;
      seenIds[i].lastMs = now;
      return;
    }
  }
  if (numSeen < MAX_SEEN) {
    seenIds[numSeen++] = {m.identifier, (bool)m.extd, 1, now};
  }
}

void canReceive(uint32_t now) {
  twai_message_t m;
  for (int n = 0; n < 20 && twai_receive(&m, 0) == ESP_OK; n++) {
    noteSeenId(m, now);
    // The controller doesn't receive its own frames, so our ID here means
    // another node uses it. Stop sending: two senders on one ID corrupt both.
    if (!m.extd && m.identifier == cfg.canId && !idConflict) {
      idConflict = true;
      Serial.printf("CAN: another node sends ID 0x%03X; not sending. Pick a free ID in Settings.\n",
                    (unsigned)cfg.canId);
    }
  }
}

// Bus-off means this node caused many errors. Wait before rejoining, longer
// each time, so a wiring fault or wrong bit rate can't keep disturbing the bus.
void canKeepAlive(uint32_t now) {
  twai_status_info_t status;
  if (twai_get_status_info(&status) != ESP_OK) {
    return;
  }
  if (status.state == TWAI_STATE_BUS_OFF && !recoveryPending) {
    busOffCount++;
    if (busOffCount > 1 && now - lastBusOffMs > BUS_OFF_CLEAN_MS) {
      busOffWaitMs = BUS_OFF_WAIT_MIN_MS;
    }
    lastBusOffMs = now;
    recoveryPending = true;
    recoverAtMs = now + busOffWaitMs;
    Serial.printf("CAN: bus-off #%lu, rejoining in %lu s\n", (unsigned long)busOffCount,
                  (unsigned long)(busOffWaitMs / 1000));
    busOffWaitMs = min(busOffWaitMs * 2, BUS_OFF_WAIT_MAX_MS);
  } else if (status.state == TWAI_STATE_BUS_OFF && (int32_t)(now - recoverAtMs) >= 0) {
    twai_initiate_recovery();
  } else if (status.state == TWAI_STATE_STOPPED) {
    twai_start();  // recovery finished
    recoveryPending = false;
  }
}

// Why the module isn't sending right now, or nullptr when it is.
const char *canHoldReason(uint32_t now) {
  if (cfg.canMode == CAN_MODE_OFF) return "CAN off in settings";
  if (!canRunning) return "CAN failed to start";
  if (cfg.canMode == CAN_MODE_LISTEN) return "listen only: not sending";
  if (idConflict) return "ID conflict: another node sends this ID";
  if (recoveryPending) return "bus-off: waiting to rejoin";
  if (now - canStartMs < CAN_LISTEN_FIRST_MS) return "listening before sending";
  return nullptr;
}

void sendSignals(uint32_t now) {
  lastSendMs = now;
  if (canHoldReason(now)) {
    return;
  }
  uint16_t bits = 0;
  for (int i = 0; i < NUM_CHANNELS; i++) {
    if (channels[i].active) {
      bits |= (1u << i);
    }
  }
  uint16_t dimRaw = (uint16_t)(dimmerVolts * 10.0f + 0.5f);
  float pct = dimmerVolts / DIMMER_FULL_SCALE_V * 100.0f;
  uint8_t dimPct = (uint8_t)constrain((int)(pct + 0.5f), 0, 100);
  bool turnFlashing = turnEverSeen && (now - lastTurnEdgeMs) < TURN_HOLD_MS;

  twai_message_t msg = {};
  msg.identifier = cfg.canId;
  msg.extd = 0;
  msg.ss = 1;   // single shot: an unacknowledged frame is dropped, not repeated
  msg.data_length_code = 8;
  msg.data[0] = bits & 0xFF;
  msg.data[1] = bits >> 8;
  msg.data[2] = dimRaw & 0xFF;
  msg.data[3] = dimRaw >> 8;
  msg.data[4] = dimPct;
  msg.data[5] = frameCounter++;
  msg.data[6] = turnFlashing ? 0x01 : 0x00;
  msg.data[7] = FRAME_VERSION;

  if (twai_transmit(&msg, 0) == ESP_OK) {
    framesSent++;
  } else {
    sendFailures++;
  }
}

// ----------------------------------------------------------------- Inputs
void readInputs(uint32_t now) {
  for (int i = 0; i < NUM_CHANNELS; i++) {
    Channel &ch = channels[i];
    bool reading = (digitalRead(ch.pin) == LOW);  // active-LOW
    if (reading != ch.rawActive) {
      ch.rawActive = reading;
      ch.rawChangedMs = now;
    }
    if (ch.active != ch.rawActive && now - ch.rawChangedMs >= DEBOUNCE_MS) {
      ch.active = ch.rawActive;
      ch.changes++;
      pendingChange = true;
      if (i == TURN_CHANNEL) {
        lastTurnEdgeMs = now;
        turnEverSeen = true;
      } else {
        // The turn signal flashes constantly, so only the others are logged.
        Serial.printf("CH%-2d %-16s (%s): %s\n", i + 1, ch.name, ch.clusterPin,
                      ch.active ? "ACTIVE" : "off");
      }
    }
  }
}

void readDimmer() {
  uint32_t mv = 0;
  for (int i = 0; i < 8; i++) {
    mv += analogReadMilliVolts(DIMMER_PIN);  // factory-calibrated ADC reading
  }
  float adcVolts = mv / 8.0f / 1000.0f;
  float volts = adcVolts * DIMMER_DIVIDER;
  dimmerVolts = dimmerVolts * 0.7f + volts * 0.3f;  // light smoothing
}

const char *canStateName(twai_status_info_t &status) {
  if (!canRunning || twai_get_status_info(&status) != ESP_OK) {
    return "not running";
  }
  switch (status.state) {
    case TWAI_STATE_RUNNING:    return "running";
    case TWAI_STATE_BUS_OFF:    return "BUS-OFF";
    case TWAI_STATE_RECOVERING: return "recovering";
    default:                    return "stopped";
  }
}

void printStatus(uint32_t now) {
  Serial.print("Inputs 1-16: ");
  for (int i = 0; i < NUM_CHANNELS; i++) {
    Serial.print(channels[i].active ? '1' : '0');
    if (i % 4 == 3 && i != NUM_CHANNELS - 1) {
      Serial.print(' ');
    }
  }
  twai_status_info_t status = {};
  const char *state = canStateName(status);
  const char *hold = canHoldReason(now);
  Serial.printf("  | dimmer %.1f V | CAN 0x%03X %s%s%s, sent %lu, failed %lu, tx errors %lu\n",
                dimmerVolts, (unsigned)cfg.canId, state, hold ? " - " : "", hold ? hold : "",
                (unsigned long)framesSent, (unsigned long)sendFailures,
                (unsigned long)status.tx_error_counter);
}

// ----------------------------------------------------------------- Web pages
// The status page is static; it fetches /status (JSON) twice a second and redraws.
const char STATUS_PAGE[] = R"HTML(<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>928 Signal Module</title>
<style>
body{margin:0;padding:12px;font:15px system-ui,sans-serif;background:#111;color:#eee}
h1{font-size:18px;margin:0 0 8px}
a{color:#93c5fd}
#info{color:#aaa;margin-bottom:10px}
#info b{color:#eee}
.warn{background:#7c2d12;border-radius:8px;padding:8px;margin-bottom:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.ch{border:1px solid #333;border-radius:8px;padding:8px;background:#1b1b1b}
.ch.on{background:#14532d;border-color:#22c55e}
.ch .n{font-weight:600}
.ch .s{float:right;font-weight:700}
.ch .m{color:#aaa;font-size:12px;margin-top:4px}
#ids{color:#aaa;font-size:13px;margin-top:12px}
#err{color:#f87171;font-weight:600}
</style></head><body>
<h1>928 Signal Module</h1>
<div id="warn"></div>
<div id="info">Connecting...</div>
<div id="err"></div>
<div class="grid" id="grid"></div>
<div id="ids"></div>
<p><a href="/settings">Settings</a> &middot; <a href="/update">Firmware update</a></p>
<script>
async function tick(){
  try{
    const r = await fetch('/status', {cache:'no-store'});
    const d = await r.json();
    document.getElementById('err').textContent = '';
    let w = '';
    if (d.defaultPassword) w += '<div class="warn">Wi-Fi password is still the default. Change it in <a href="/settings">Settings</a>.</div>';
    if (d.can.hold && d.can.mode == 'send') w += '<div class="warn">CAN not sending: ' + d.can.hold + '</div>';
    document.getElementById('warn').innerHTML = w;
    document.getElementById('info').innerHTML =
      'Dimmer <b>' + d.dimmerV.toFixed(1) + ' V</b> (' + d.dimmerPct + ' %)' +
      ' &middot; Turn signal <b>' + (d.turnFlashing ? 'flashing' : 'off') + '</b>' +
      ' &middot; CAN <b>' + d.can.id + ' ' + d.can.mode + ', ' + d.can.state + '</b>' +
      (d.can.hold ? ' (' + d.can.hold + ')' : '') +
      ', sent ' + d.can.sent + ', failed ' + d.can.failed + ', tx errors ' + d.can.txErrors +
      ', bus-offs ' + d.can.busOffs + ' &middot; up ' + Math.floor(d.uptimeS / 60) + ' min ' + (d.uptimeS % 60) + ' s';
    document.getElementById('grid').innerHTML = d.channels.map((c, i) =>
      '<div class="ch' + (c.active ? ' on' : '') + '"><span class="s">' + (c.active ? 'ACTIVE' : 'off') + '</span>' +
      '<div class="n">CH' + (i + 1) + ' ' + c.name + '</div>' +
      '<div class="m">pin ' + c.clusterPin + ' &middot; GPIO' + c.gpio + ' &middot; ' + c.changes + ' changes</div></div>').join('');
    document.getElementById('ids').innerHTML = d.can.seen.length ?
      'IDs heard on the bus: ' + d.can.seen.map(s => s.id + (s.extd ? ' (ext)' : '') + ' &times;' + s.count +
      (s.ageS > 5 ? ' (' + s.ageS + ' s ago)' : '')).join(', ') : 'No other CAN traffic heard.';
  }catch(e){
    document.getElementById('err').textContent = 'No response from the module';
  }
}
tick(); setInterval(tick, 500);
</script></body></html>)HTML";

const char PAGE_HEAD[] = "<!doctype html><html><head><meta charset=\"utf-8\">"
  "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>928 Signal Module</title>"
  "<style>body{margin:0;padding:12px;font:15px system-ui,sans-serif;background:#111;color:#eee;max-width:520px}"
  "h1{font-size:18px}a{color:#93c5fd}label{display:block;margin-top:12px;color:#aaa}"
  "input,select{width:100%;box-sizing:border-box;padding:8px;font-size:15px;margin-top:4px;background:#1b1b1b;"
  "color:#eee;border:1px solid #444;border-radius:6px}button{margin-top:16px;padding:10px 16px;font-size:15px}"
  ".err{background:#7f1d1d;padding:8px;border-radius:8px}.ok{background:#14532d;padding:8px;border-radius:8px}"
  "small{color:#888}</style></head><body><h1>928 Signal Module</h1>";

bool requireLogin() {
  if (server.authenticate(ADMIN_USER, cfg.pass)) {
    return true;
  }
  server.requestAuthentication();
  return false;
}

// Copies `s` into `out` with HTML special characters escaped.
const char *htmlEscape(const char *s, char *out, size_t size) {
  size_t n = 0;
  for (; *s && n + 7 < size; s++) {
    const char *rep = nullptr;
    switch (*s) {
      case '&': rep = "&amp;"; break;
      case '<': rep = "&lt;"; break;
      case '>': rep = "&gt;"; break;
      case '"': rep = "&quot;"; break;
      case '\'': rep = "&#39;"; break;
    }
    if (rep) {
      n += snprintf(out + n, size - n, "%s", rep);
    } else {
      out[n++] = *s;
    }
  }
  out[n] = 0;
  return out;
}

void sendSettingsPage(const Config &c, const char *message, bool error) {
  static char page[5000];
  char ssid[200];
  htmlEscape(c.ssid, ssid, sizeof(ssid));
  int n = snprintf(page, sizeof(page), "%s<p><a href=\"/\">&larr; Status</a></p>", PAGE_HEAD);
  if (message) {
    n += snprintf(page + n, sizeof(page) - n, "<p class=\"%s\">%s</p>", error ? "err" : "ok", message);
  }
  n += snprintf(page + n, sizeof(page) - n,
      "<form method=\"post\" action=\"/settings\">"
      "<label>CAN ID (hex, 001-7FF)<input name=\"canid\" value=\"0x%03X\"></label>"
      "<small>Check the status page's list of IDs heard on the bus first: pick one nobody else uses.</small>"
      "<label>Frame period, ms (20-1000)<input name=\"period\" value=\"%u\"></label>"
      "<label>CAN mode<select name=\"mode\">"
      "<option value=\"0\"%s>Send (normal)</option>"
      "<option value=\"1\"%s>Listen only (never transmits; for checking a new bus)</option>"
      "<option value=\"2\"%s>Off</option></select></label>"
      "<label>Wi-Fi name<input name=\"ssid\" maxlength=\"32\" value=\"%s\"></label>"
      "<label>New Wi-Fi password (8-63 characters; leave blank to keep)"
      "<input name=\"pass\" type=\"password\" maxlength=\"63\" autocomplete=\"new-password\"></label>"
      "<label>New password again<input name=\"pass2\" type=\"password\" maxlength=\"63\" autocomplete=\"new-password\"></label>"
      "<label>Turn Wi-Fi off after no phone has been connected for (minutes, 0 = never)"
      "<input name=\"wifioff\" value=\"%u\"></label>"
      "<small>Once off, Wi-Fi comes back at the next power-up.</small>"
      "<button type=\"submit\">Save and restart</button></form>"
      "<p><small>The settings login is user <b>admin</b> with the Wi-Fi password. Forgot it? Hold the ESP32's "
      "BOOT button for 5 seconds to restore the defaults.</small></p></body></html>",
      (unsigned)c.canId, (unsigned)c.periodMs, c.canMode == CAN_MODE_SEND ? " selected" : "",
      c.canMode == CAN_MODE_LISTEN ? " selected" : "", c.canMode == CAN_MODE_OFF ? " selected" : "",
      ssid, (unsigned)c.wifiOffMin);
  server.send(error ? 400 : 200, "text/html", page);
}

void handleSettingsGet() {
  if (!requireLogin()) return;
  sendSettingsPage(cfg, nullptr, false);
}

void handleSettingsPost() {
  if (!requireLogin()) return;
  Config next;
  const char *err = parseSettings(cfg, server.arg("canid").c_str(), server.arg("period").c_str(),
                                  server.arg("mode").c_str(), server.arg("ssid").c_str(),
                                  server.arg("pass").c_str(), server.arg("pass2").c_str(),
                                  server.arg("wifioff").c_str(), next);
  if (err) {
    sendSettingsPage(cfg, err, true);
    return;
  }
  bool wifiChanged = strcmp(next.ssid, cfg.ssid) != 0 || strcmp(next.pass, cfg.pass) != 0;
  saveConfig(next);
  static char page[2000];
  char ssid[200];
  int n = snprintf(page, sizeof(page),
                   "%s<p class=\"ok\">Saved. The module restarts in a moment with CAN ID 0x%03X (%s).</p>",
                   PAGE_HEAD, (unsigned)next.canId, CAN_MODE_NAMES[next.canMode]);
  if (wifiChanged) {
    snprintf(page + n, sizeof(page) - n,
             "<p>Wi-Fi changed: join <b>%s</b> with the new password, then open http://192.168.4.1</p></body></html>",
             htmlEscape(next.ssid, ssid, sizeof(ssid)));
  } else {
    snprintf(page + n, sizeof(page) - n, "<p><a href=\"/\">Back to status</a></p></body></html>");
  }
  server.send(200, "text/html", page);
  Serial.println("Settings saved; restarting");
  restartAtMs = millis() + RESTART_DELAY_MS;
  if (!restartAtMs) restartAtMs = 1;
}

void handleUpdateGet() {
  if (!requireLogin()) return;
  static char page[2500];
  snprintf(page, sizeof(page),
           "%s<p><a href=\"/\">&larr; Status</a></p>"
           "<p>Upload a new firmware file. In the Arduino IDE: <b>Sketch &rarr; Export Compiled Binary</b>, then "
           "pick <b>signal_module_928.ino.bin</b> from the sketch's <b>build</b> folder (not the bootloader or "
           "merged file). Settings are kept.</p>"
           "<form method=\"post\" action=\"/update\" enctype=\"multipart/form-data\">"
           "<input type=\"file\" name=\"firmware\" accept=\".bin\"><button type=\"submit\">Update</button></form>"
           "<p><small>Takes about 30 s. Don't power off until the module restarts.</small></p></body></html>",
           PAGE_HEAD);
  server.send(200, "text/html", page);
}

// Called for each chunk of the uploaded file.
void handleUpdateUpload() {
  HTTPUpload &up = server.upload();
  if (up.status == UPLOAD_FILE_START) {
    uploadAuthorized = server.authenticate(ADMIN_USER, cfg.pass);
    if (uploadAuthorized) {
      Serial.printf("Update: receiving %s\n", up.filename.c_str());
      Update.begin(UPDATE_SIZE_UNKNOWN);
    }
  } else if (!uploadAuthorized) {
    return;
  } else if (up.status == UPLOAD_FILE_WRITE) {
    Update.write(up.buf, up.currentSize);
  } else if (up.status == UPLOAD_FILE_END) {
    Update.end(true);
  } else if (up.status == UPLOAD_FILE_ABORTED) {
    Update.abort();
  }
  feedLoopWDT();  // a flash write can take a while; don't let the watchdog fire mid-update
}

void handleUpdateDone() {
  if (!uploadAuthorized) {
    server.requestAuthentication();
    return;
  }
  static char page[1500];
  bool ok = !Update.hasError() && Update.isFinished();
  snprintf(page, sizeof(page), "%s<p class=\"%s\">%s</p><p><a href=\"/\">Back to status</a></p></body></html>",
           PAGE_HEAD, ok ? "ok" : "err",
           ok ? "Update done. Restarting; reconnect in about 10 s." : "Update failed: wrong file? Nothing was changed.");
  server.send(ok ? 200 : 500, "text/html", page);
  if (ok) {
    Serial.println("Update: done, restarting");
    restartAtMs = millis() + RESTART_DELAY_MS;
    if (!restartAtMs) restartAtMs = 1;
  }
}

void handleRoot() {
  server.send(200, "text/html", STATUS_PAGE);
}

// Builds the /status JSON. Channel names are fixed strings in this sketch, so
// no escaping is needed; the user-set Wi-Fi name is not included.
size_t statusJson(char *buf, size_t size) {
  twai_status_info_t status = {};
  const char *state = canStateName(status);
  uint32_t now = millis();
  const char *hold = canHoldReason(now);
  bool turnFlashing = turnEverSeen && (now - lastTurnEdgeMs) < TURN_HOLD_MS;
  float pct = dimmerVolts / DIMMER_FULL_SCALE_V * 100.0f;
  size_t n = snprintf(buf, size,
      "{\"uptimeS\":%lu,\"dimmerV\":%.2f,\"dimmerPct\":%d,\"turnFlashing\":%s,\"defaultPassword\":%s,"
      "\"can\":{\"id\":\"0x%03X\",\"mode\":\"%s\",\"state\":\"%s\",\"hold\":%s%s%s,\"sent\":%lu,\"failed\":%lu,"
      "\"txErrors\":%lu,\"busOffs\":%lu,\"seen\":[",
      (unsigned long)(now / 1000), dimmerVolts, constrain((int)(pct + 0.5f), 0, 100),
      turnFlashing ? "true" : "false", strcmp(cfg.pass, DEFAULTS.pass) == 0 ? "true" : "false",
      (unsigned)cfg.canId, CAN_MODE_NAMES[cfg.canMode], state, hold ? "\"" : "", hold ? hold : "null",
      hold ? "\"" : "", (unsigned long)framesSent, (unsigned long)sendFailures,
      (unsigned long)status.tx_error_counter, (unsigned long)busOffCount);
  for (int i = 0; i < numSeen && n < size; i++) {
    n += snprintf(buf + n, size - n, "%s{\"id\":\"0x%03lX\",\"extd\":%s,\"count\":%lu,\"ageS\":%lu}",
                  i ? "," : "", (unsigned long)seenIds[i].id, seenIds[i].extd ? "true" : "false",
                  (unsigned long)seenIds[i].count, (unsigned long)((now - seenIds[i].lastMs) / 1000));
  }
  if (n < size) {
    n += snprintf(buf + n, size - n, "]},\"channels\":[");
  }
  for (int i = 0; i < NUM_CHANNELS && n < size; i++) {
    const Channel &ch = channels[i];
    n += snprintf(buf + n, size - n,
        "%s{\"name\":\"%s\",\"clusterPin\":\"%s\",\"gpio\":%d,\"active\":%s,\"changes\":%lu}",
        i ? "," : "", ch.name, ch.clusterPin, ch.pin, ch.active ? "true" : "false",
        (unsigned long)ch.changes);
  }
  if (n < size) {
    n += snprintf(buf + n, size - n, "]}");
  }
  return n;
}

void handleStatus() {
  static char json[4096];
  statusJson(json, sizeof(json));
  server.send(200, "application/json", json);
}

void webBegin() {
  if (HOME_WIFI_SSID[0]) {
    WiFi.mode(WIFI_AP_STA);
    WiFi.begin(HOME_WIFI_SSID, HOME_WIFI_PASSWORD);  // connects in the background
  } else {
    WiFi.mode(WIFI_AP);
  }
  if (!WiFi.softAP(cfg.ssid, cfg.pass)) {
    Serial.println("Wi-Fi: access point failed to start");
    return;
  }
  // Low transmit power is plenty inside the car and keeps the 5 V current down.
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/settings", HTTP_GET, handleSettingsGet);
  server.on("/settings", HTTP_POST, handleSettingsPost);
  server.on("/update", HTTP_GET, handleUpdateGet);
  server.on("/update", HTTP_POST, handleUpdateDone, handleUpdateUpload);
  server.begin();
  webRunning = true;
  lastClientMs = millis();
  Serial.printf("Wi-Fi: join \"%s\", then open http://%s\n", cfg.ssid,
                WiFi.softAPIP().toString().c_str());
}

// Prints the home-network address once, turns Wi-Fi off after the auto-off
// time with no phone connected, and serves web requests.
void webKeepAlive(uint32_t now) {
  static bool homeAnnounced = false;
  if (HOME_WIFI_SSID[0] && !homeAnnounced && WiFi.status() == WL_CONNECTED) {
    homeAnnounced = true;
    Serial.printf("Wi-Fi: on \"%s\" as http://%s\n", HOME_WIFI_SSID,
                  WiFi.localIP().toString().c_str());
  }
  if (WiFi.softAPgetStationNum() > 0) {
    lastClientMs = now;
  } else if (cfg.wifiOffMin && now - lastClientMs >= cfg.wifiOffMin * 60000UL) {
    Serial.println("Wi-Fi: no client for the auto-off time; Wi-Fi off until the next power-up");
    server.stop();
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_OFF);
    webRunning = false;
    return;
  }
  server.handleClient();
}

// Hold BOOT for FACTORY_RESET_MS to restore the default settings.
void checkFactoryReset(uint32_t now) {
  if (digitalRead(BOOT_BUTTON_PIN) == LOW) {
    if (!bootPressedMs) {
      bootPressedMs = now ? now : 1;
    } else if (now - bootPressedMs >= FACTORY_RESET_MS && !restartAtMs) {
      factoryReset();
      restartAtMs = now + 100;
    }
  } else {
    bootPressedMs = 0;
  }
}

// ----------------------------------------------------------------- Arduino
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n928 Signal Module, board rev A");

  pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);
  for (int i = 0; i < NUM_CHANNELS; i++) {
    pinMode(channels[i].pin, INPUT);  // external 10k pull-ups on the board
    channels[i].rawActive = channels[i].active = (digitalRead(channels[i].pin) == LOW);
  }
  analogSetPinAttenuation(DIMMER_PIN, ADC_11db);  // 0-3.1 V range; 14.4 V in reads ~2.5 V
  dimmerVolts = analogReadMilliVolts(DIMMER_PIN) / 1000.0f * DIMMER_DIVIDER;  // seed the smoothing

  loadConfig();
  canRunning = canBegin();
  canStartMs = millis();
  webBegin();
  enableLoopWDT();  // restart if loop() ever hangs for more than a few seconds
}

void loop() {
  uint32_t now = millis();

  readInputs(now);

  if (now - lastDimmerMs >= DIMMER_PERIOD_MS) {
    lastDimmerMs = now;
    readDimmer();
  }

  if (canRunning) {
    canReceive(now);
    if (cfg.canMode == CAN_MODE_SEND) {
      canKeepAlive(now);
    }
  }

  bool periodic = now - lastSendMs >= cfg.periodMs;
  bool changed = pendingChange && now - lastSendMs >= MIN_SEND_GAP_MS;
  if (periodic || changed) {
    pendingChange = false;
    sendSignals(now);
  }

  if (webRunning) {
    webKeepAlive(now);
  }
  checkFactoryReset(now);
  if (restartAtMs && (int32_t)(now - restartAtMs) >= 0) {
    ESP.restart();
  }

  if (now - lastPrintMs >= PRINT_PERIOD_MS) {
    lastPrintMs = now;
    printStatus(now);
  }
}
