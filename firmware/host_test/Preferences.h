// Fake Preferences (NVS) for the host test: one in-memory store that survives
// "restarts" of the sketch within a test run.
#pragma once
#include <map>
#include <string>
#include <cstring>
#include <cstdint>
static std::map<std::string, std::string> g_nvs;
struct Preferences {
  bool open = false;
  bool begin(const char *, bool readOnly) { if (readOnly && g_nvs.empty()) return false; open = true; return true; }
  void end() { open = false; }
  void clear() { g_nvs.clear(); }
  uint16_t getUShort(const char *k, uint16_t d) { auto it = g_nvs.find(k); return it == g_nvs.end() ? d : (uint16_t)std::stoul(it->second); }
  uint8_t getUChar(const char *k, uint8_t d) { auto it = g_nvs.find(k); return it == g_nvs.end() ? d : (uint8_t)std::stoul(it->second); }
  size_t getString(const char *k, char *out, size_t max) { auto it = g_nvs.find(k); if (it == g_nvs.end() || it->second.size() >= max) return 0; strcpy(out, it->second.c_str()); return it->second.size(); }
  void putUShort(const char *k, uint16_t v) { g_nvs[k] = std::to_string(v); }
  void putUChar(const char *k, uint8_t v) { g_nvs[k] = std::to_string(v); }
  void putString(const char *k, const char *v) { g_nvs[k] = v; }
};
