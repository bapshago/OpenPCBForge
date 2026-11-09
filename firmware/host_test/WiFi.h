// Fake ESP32 WiFi for the host test: records the access point, connects nowhere.
#pragma once
#include <string>
enum { WIFI_OFF = 0, WIFI_AP = 2, WIFI_AP_STA = 3, WL_CONNECTED = 3, WIFI_POWER_8_5dBm = 34 };
struct FakeIP { std::string s; std::string toString() const { return s; } };
struct FakeWiFi {
  std::string apSsid, apPassword; int stations = 0; bool apOn = false;
  bool softAP(const char *ssid, const char *password) { apSsid = ssid; apPassword = password; apOn = true; return true; }
  bool softAPdisconnect(bool) { apOn = false; return true; }
  int softAPgetStationNum() { return stations; }
  void mode(int) {}
  void begin(const char *, const char *) {}
  void setTxPower(int) {}
  int status() { return 0; }
  FakeIP softAPIP() { return {"192.168.4.1"}; }
  FakeIP localIP() { return {"0.0.0.0"}; }
} WiFi;
