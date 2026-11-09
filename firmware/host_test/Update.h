// Fake Update (OTA) for the host test.
#pragma once
#include <cstddef>
#include <cstdint>
#define UPDATE_SIZE_UNKNOWN 0xFFFFFFFF
struct FakeUpdate {
  size_t written = 0; bool begun = false, finished = false;
  bool begin(size_t) { begun = true; written = 0; finished = false; return true; }
  size_t write(const uint8_t *, size_t n) { written += n; return n; }
  bool end(bool) { finished = begun && written > 0; return finished; }
  void abort() { begun = false; }
  bool hasError() { return !finished; }
  bool isFinished() { return finished; }
} Update;
