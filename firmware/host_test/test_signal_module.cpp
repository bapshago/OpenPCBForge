// Runs the signal module sketch on a PC against a fake Arduino core and fake
// TWAI (CAN), WiFi, WebServer, Preferences and Update libraries, and checks
// debounce, bit mapping, dimmer scaling, the turn-signal flag, send timing,
// the CAN safety rules (listen first, single shot, ID conflict, bus-off
// back-off, listen-only), the status JSON, the settings page and login,
// Wi-Fi auto-off, factory reset and firmware update. Built and run by
// tests/test_firmware.py.
#include <cstdio>
#include <cstdarg>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <vector>
#include <deque>
#include <string>
#include <cassert>
#include <algorithm>
using std::min;
// --- fake Arduino ---
#define LOW 0
#define HIGH 1
#define INPUT 0
#define INPUT_PULLUP 2
#define ADC_11db 3
static uint32_t g_ms = 0; static int g_pin[40]; static int g_mv = 0; static bool g_restarted = false;
uint32_t millis(){ return g_ms; } void delay(int){}
void pinMode(int,int){} int digitalRead(int p){ return g_pin[p]; }
uint32_t analogReadMilliVolts(int){ return g_mv; } void analogSetPinAttenuation(int,int){}
void enableLoopWDT(){} void feedLoopWDT(){}
struct { void restart(){ g_restarted = true; } } ESP;
template<class T> T constrain(T v,T a,T b){ return v<a?a:(v>b?b:v); }
struct FakeSerial { void begin(int){} void print(char){} void print(const char*){}
  void println(const char*){} void printf(const char*, ...){} } Serial;
#include "driver/twai.h"
#include "WiFi.h"
#include "WebServer.h"
#include "Preferences.h"
#include "Update.h"
static std::vector<twai_message_t> sent;
static std::deque<twai_message_t> rxq;
static twai_status_info_t g_bus = {TWAI_STATE_RUNNING, 0};
static twai_mode_t g_mode; static int g_recoveries = 0, g_starts = 0;
esp_err_t twai_driver_install(const twai_general_config_t* g, const twai_timing_config_t*, const twai_filter_config_t*){ g_mode = g->mode; return 0; }
esp_err_t twai_start(){ g_starts++; g_bus.state = TWAI_STATE_RUNNING; return 0; }
esp_err_t twai_initiate_recovery(){ g_recoveries++; g_bus.state = TWAI_STATE_RECOVERING; return 0; }
esp_err_t twai_get_status_info(twai_status_info_t* s){ *s = g_bus; return 0; }
esp_err_t twai_transmit(const twai_message_t* m, int){ sent.push_back(*m); return 0; }
esp_err_t twai_receive(twai_message_t* m, int){ if (rxq.empty()) return ESP_FAIL; *m = rxq.front(); rxq.pop_front(); return 0; }
#include SKETCH
void run(uint32_t ms){ for(uint32_t i=0;i<ms;i++){ g_ms++; loop(); } }
bool has(const std::string &s, const char *x){ return s.find(x) != std::string::npos; }
twai_message_t frame(uint32_t id){ twai_message_t m = {}; m.identifier = id; m.data_length_code = 8; return m; }
void login(const char *u, const char *p){ server.user = u; server.pass = p; }
void post(std::map<std::string, std::string> a){ server.args = a; server.request("/settings", HTTP_POST); }

int main(){
  const int gpio[16]={34,35,32,33,26,14,13,16,17,18,19,21,22,23,4,36};
  for(int i=0;i<40;i++) g_pin[i]=HIGH;            // all inactive (pulled up), BOOT released
  g_mv = 2526;                                     // 2.526 V at ADC -> 14.4 V at 14R
  setup();
  assert(cfg.canId == 0x31B && g_mode == TWAI_MODE_NORMAL);   // defaults with empty flash
  assert(WiFi.apSsid == "928-Signal-Module" && WiFi.apPassword == "porsche928");

  // listens for CAN_LISTEN_FIRST_MS before sending anything
  run(990); assert(sent.empty());
  run(1010);
  auto &m = sent.back();
  assert(m.identifier==0x31B && m.extd==0 && m.ss==1 && m.data_length_code==8);  // single shot
  assert(m.data[0]==0 && m.data[1]==0 && m.data[7]==1);
  int dim = m.data[2] | (m.data[3]<<8);
  printf("idle: dimmer raw %d (expect ~144), pct %d\n", dim, m.data[4]);
  assert(dim>=142 && dim<=146 && m.data[4]==100);   // 14.4 V clamps to 100 %
  size_t n0 = sent.size(); run(1000); size_t n = sent.size() - n0;
  printf("periodic: %zu frames in 1 s\n", n); assert(n>=9 && n<=11);

  // a 10 ms glitch on CH5 must not count
  size_t mark = sent.size();
  g_pin[gpio[4]] = LOW; run(10); g_pin[gpio[4]] = HIGH; run(50);
  for(size_t i=mark;i<sent.size();i++) assert(!(sent[i].data[0] & 0x10));
  // a real activation on CH5 shows up within debounce + min gap, on byte 0 bit 4
  size_t before = sent.size(); g_pin[gpio[4]] = LOW; run(31);
  assert(sent.size()>before && (sent.back().data[0] & 0x10));
  printf("CH5 activation sent after <=31 ms\n");
  // every channel maps to its own bit
  g_pin[gpio[4]] = HIGH; run(100);
  for(int ch=0; ch<16; ch++){ g_pin[gpio[ch]]=LOW; run(40);
    uint16_t bits = sent.back().data[0] | (sent.back().data[1]<<8);
    assert(bits == (1u<<ch)); g_pin[gpio[ch]]=HIGH; run(40); }
  printf("all 16 channels map to bits 0-15\n");
  // turn signal flashing flag: 1.5 Hz flasher sets it, it drops 1 s after flashing stops
  for(int k=0;k<6;k++){ g_pin[34]=LOW; run(333); g_pin[34]=HIGH; run(333); }
  assert(sent.back().data[6]==1); run(1100); assert(sent.back().data[6]==0);
  printf("turn flashing flag ok\n");
  // counter increments by 1 per frame
  for(size_t i=1;i<sent.size();i++) assert((uint8_t)(sent[i-1].data[5]+1)==sent[i].data[5]);
  // dimmer at 7.2 V reads ~72 raw / ~51 %
  g_mv = 1263; run(1000); dim = sent.back().data[2] | (sent.back().data[3]<<8);
  printf("dimmer 7.2 V -> raw %d, %d %%\n", dim, sent.back().data[4]); assert(dim>=70&&dim<=74);

  // ---- status page (no login needed)
  login("", "");
  assert(server.request("/") && server.code == 200 && server.type == "text/html");
  assert(has(server.body, "fetch('/status'") && has(server.body, "href=\"/settings\""));
  g_pin[gpio[6]] = LOW; run(40);                    // CH7 brake warning on
  rxq.push_back(frame(0x31A)); rxq.push_back(frame(0x31A)); run(5);   // other traffic is listed
  assert(server.request("/status") && server.type == "application/json");
  std::string j = server.body;
  printf("status: %.160s...\n", j.c_str());
  assert(j.front() == '{' && j.back() == '}');
  assert(has(j, "\"id\":\"0x31B\",\"mode\":\"send\",\"state\":\"running\",\"hold\":null"));
  assert(has(j, "\"defaultPassword\":true"));
  assert(has(j, "\"seen\":[{\"id\":\"0x31A\",\"extd\":false,\"count\":2"));
  assert(has(j, "{\"name\":\"Brake warning\",\"clusterPin\":\"5R\",\"gpio\":13,\"active\":true"));
  assert(has(j, "{\"name\":\"High beam\",\"clusterPin\":\"1M\",\"gpio\":35,\"active\":false,\"changes\":2}"));
  assert(has(j, "\"dimmerPct\":51"));
  assert(std::count(j.begin(), j.end(), '{') == std::count(j.begin(), j.end(), '}'));
  assert(std::count(j.begin(), j.end(), '[') == std::count(j.begin(), j.end(), ']'));
  printf("status page ok (%zu bytes of JSON)\n", j.size());

  // ---- settings: login required, validation, save, restart
  login("", "");
  assert(server.request("/settings") && server.authRequested && server.code == 401);
  login("admin", "wrong"); assert(server.request("/settings") && server.authRequested);
  post({{"canid","0x400"}}); assert(server.authRequested && g_nvs.empty());   // POST needs login too
  login("admin", "porsche928");
  assert(server.request("/settings") && server.code == 200 && has(server.body, "value=\"0x31B\""));
  std::map<std::string, std::string> f = {{"canid","0x31A"},{"period","100"},{"mode","0"},
      {"ssid","928-Signal-Module"},{"pass",""},{"pass2",""},{"wifioff","0"}};
  post(f); assert(server.code == 400 && has(server.body, "used by another 928 EV node") && g_nvs.empty());
  f["canid"] = "800"; post(f); assert(server.code == 400 && has(server.body, "0x001 to 0x7FF"));
  f["canid"] = "0x320"; f["period"] = "5"; post(f); assert(server.code == 400 && has(server.body, "20 to 1000"));
  f["period"] = "50"; f["pass"] = "short"; f["pass2"] = "short"; post(f); assert(server.code == 400 && has(server.body, "8 to 63"));
  f["pass"] = "a-better-pass"; f["pass2"] = "a-better-pasz"; post(f); assert(server.code == 400 && has(server.body, "don't match"));
  f["ssid"] = ""; f["pass2"] = "a-better-pass"; post(f); assert(server.code == 400 && has(server.body, "1 to 32"));
  assert(g_nvs.empty() && !restartAtMs);
  f["ssid"] = "My <928>"; f["wifioff"] = "10";
  post(f);
  assert(server.code == 200 && has(server.body, "0x320") && has(server.body, "My &lt;928&gt;"));
  assert(restartAtMs && !g_restarted); run(RESTART_DELAY_MS + 5); assert(g_restarted);
  printf("settings: login enforced, bad values refused, good values saved\n");

  // "restart": the new settings load from flash and take effect
  g_restarted = false; restartAtMs = 0;
  loadConfig();
  assert(cfg.canId == 0x320 && cfg.periodMs == 50 && cfg.wifiOffMin == 10);
  assert(!strcmp(cfg.ssid, "My <928>") && !strcmp(cfg.pass, "a-better-pass"));
  webBegin(); assert(WiFi.apSsid == "My <928>" && WiFi.apPassword == "a-better-pass");
  canStartMs = g_ms; run(1100);
  assert(sent.back().identifier == 0x320);
  n0 = sent.size(); run(1000); n = sent.size() - n0; assert(n >= 19 && n <= 21);   // 50 ms period
  login("admin", "porsche928"); assert(server.request("/settings") && server.authRequested);   // old password gone
  login("admin", "a-better-pass"); assert(server.request("/settings") && server.code == 200);
  assert(has(server.body, "My &lt;928&gt;"));
  // a blank password keeps the current one
  Config c; assert(parseSettings(cfg, "320", "50", "1", "x", "", "", "0", c) == nullptr);
  assert(!strcmp(c.pass, "a-better-pass") && c.canMode == CAN_MODE_LISTEN && c.canId == 0x320);
  server.request("/status"); assert(has(server.body, "\"defaultPassword\":false"));
  printf("new CAN ID, period and Wi-Fi settings in effect after restart\n");

  // ---- ID conflict: another node sends our ID -> stop sending
  rxq.push_back(frame(0x320)); run(5);
  n0 = sent.size(); run(500); assert(sent.size() == n0 && idConflict);
  server.request("/status"); assert(has(server.body, "\"hold\":\"ID conflict"));
  idConflict = false;
  printf("ID conflict stops transmission\n");

  // ---- bus-off: wait 1 s, then 2 s, before rejoining; no frames meanwhile
  g_bus.state = TWAI_STATE_BUS_OFF; g_recoveries = 0;
  n0 = sent.size(); run(900); assert(g_recoveries == 0 && sent.size() == n0);
  run(200); assert(g_recoveries == 1);
  g_bus.state = TWAI_STATE_STOPPED; run(5); assert(g_bus.state == TWAI_STATE_RUNNING && !recoveryPending);
  run(100); assert(sent.size() > n0);
  g_bus.state = TWAI_STATE_BUS_OFF; g_recoveries = 0;
  run(1900); assert(g_recoveries == 0); run(200); assert(g_recoveries == 1);
  g_bus.state = TWAI_STATE_STOPPED; run(5);
  assert(busOffCount == 2);
  printf("bus-off back-off: 1 s, then 2 s\n");

  // ---- listen-only: installs in listen-only mode and never transmits
  cfg.canMode = CAN_MODE_LISTEN; canRunning = canBegin(); canStartMs = g_ms;
  assert(g_mode == TWAI_MODE_LISTEN_ONLY);
  n0 = sent.size(); run(2000); assert(sent.size() == n0);
  rxq.push_back(frame(0x123)); run(5);
  server.request("/status"); assert(has(server.body, "\"id\":\"0x123\"") && has(server.body, "listen only"));
  cfg.canMode = CAN_MODE_SEND;
  printf("listen-only mode sends nothing and lists bus IDs\n");

  // ---- firmware update: login checked at upload start
  login("", "");
  server.up = {UPLOAD_FILE_START, "fw.bin", {}, 0}; handleUpdateUpload();
  assert(!Update.begun);
  server.request("/update", HTTP_POST); assert(server.authRequested && !restartAtMs);
  login("admin", "a-better-pass");
  assert(server.request("/update") && has(server.body, "multipart/form-data"));
  server.up = {UPLOAD_FILE_START, "fw.bin", {}, 0}; handleUpdateUpload();
  server.up.status = UPLOAD_FILE_WRITE; server.up.currentSize = 64; handleUpdateUpload(); handleUpdateUpload();
  server.up.status = UPLOAD_FILE_END; handleUpdateUpload();
  assert(Update.begun && Update.written == 128 && Update.isFinished());
  server.request("/update", HTTP_POST); assert(server.code == 200 && has(server.body, "Update done"));
  run(RESTART_DELAY_MS + 5); assert(g_restarted); g_restarted = false; restartAtMs = 0;
  printf("firmware update needs login, then restarts\n");

  // ---- Wi-Fi auto-off after 10 min with no client; stays on while one is connected
  WiFi.stations = 1; run(5); WiFi.stations = 0;
  run(9 * 60000); assert(webRunning && WiFi.apOn);
  run(60000 + 10); assert(!webRunning && !WiFi.apOn && !server.running);
  printf("Wi-Fi turns off after the auto-off time\n");

  // ---- factory reset: hold BOOT 5 s -> defaults, restart
  g_pin[0] = LOW; run(4900); assert(!g_restarted && !g_nvs.empty());
  run(300); assert(g_nvs.empty()); g_pin[0] = HIGH; run(200); assert(g_restarted);
  loadConfig(); assert(cfg.canId == 0x31B && !strcmp(cfg.pass, "porsche928"));
  printf("BOOT held 5 s restores defaults\n");

  printf("ALL OK (%zu frames)\n", sent.size());
}
