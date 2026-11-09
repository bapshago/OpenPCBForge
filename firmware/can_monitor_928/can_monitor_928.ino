// 928 CAN monitor: a second ESP32 on the bench bus, either plugged into a
// second signal module board (default pins) or wired to a WCMCU-230.
//
// Listens at 500 kbit/s, acknowledges every frame (so the signal module stops
// counting "failed"), and decodes the signal module's frame (ID 0x31B) on the
// serial monitor at 115200 baud: a line whenever an input changes, and a
// summary every second (frame rate, dropped frames, other IDs seen).
//
// Board: any ESP32 dev board, "ESP32 Dev Module". No extra libraries.
//
// On a second signal module board: the ESP32 in its sockets uses the board's
// own transceiver (GPIO27 TX, GPIO25 RX). Join the two boards' J2 (H to H,
// L to L) and grounds, and fit JP10 on both (H to L reads ~60 ohm, power off).
//
// With a WCMCU-230 instead: 3V3 -> 3V3, GND -> GND, CTX -> GPIO21,
// CRX -> GPIO22, and change the two pins below to 21 / 22. Its 120 ohm
// terminator is on the module, so fit JP10 only on the signal module.

#include "driver/twai.h"

const int CAN_TX_PIN = 27;   // signal module board (WCMCU-230: 21, to CTX)
const int CAN_RX_PIN = 25;   // signal module board (WCMCU-230: 22, from CRX)
const uint32_t CAN_ID_SIGNALS = 0x31B;
// Once a second the monitor sends its own test frame. The signal module
// acknowledges it, so "test frames ok" climbing proves this side's transmitter
// (GPIO21 -> CTX -> WCMCU-230) can drive the bus. Set to 0 to stay silent.
const uint32_t CAN_ID_MONITOR_TEST = 0x7F0;

const char *const NAMES[16] = {
  "CH1 Turn signal", "CH2 High beam", "CH3 Lights on", "CH4 Central warning",
  "CH5 Brake fluid", "CH6 Brake pad wear", "CH7 Brake warning", "CH8 Parking brake",
  "CH9 Washer fluid", "CH10 Spare", "CH11 Spare", "CH12 Spare",
  "CH13 Spare", "CH14 Spare", "CH15 Spare", "CH16 Spare",
};

uint16_t lastBits = 0;
bool haveFrame = false;
uint8_t lastCounter = 0;
uint32_t framesThisSecond = 0, dropped = 0, repeats = 0, repeatsThisSecond = 0, otherIds = 0, lastSummaryMs = 0;
uint32_t testSent = 0, testFailed = 0;
uint8_t lastDimPct = 0, lastFlags = 0;
float lastDimV = 0;

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n928 CAN monitor, 500 kbit/s, decoding 0x31B");

  twai_general_config_t general =
      TWAI_GENERAL_CONFIG_DEFAULT((gpio_num_t)CAN_TX_PIN, (gpio_num_t)CAN_RX_PIN, TWAI_MODE_NORMAL);
  general.rx_queue_len = 32;
  general.alerts_enabled = TWAI_ALERT_TX_SUCCESS | TWAI_ALERT_TX_FAILED;
  twai_timing_config_t timing = TWAI_TIMING_CONFIG_500KBITS();
  twai_filter_config_t filter = TWAI_FILTER_CONFIG_ACCEPT_ALL();
  if (twai_driver_install(&general, &timing, &filter) != ESP_OK || twai_start() != ESP_OK) {
    Serial.println("CAN: failed to start (check the CTX/CRX pins)");
    while (true) delay(1000);
  }
}

void decode(const twai_message_t &m) {
  uint16_t bits = m.data[0] | (m.data[1] << 8);
  float dimV = (m.data[2] | (m.data[3] << 8)) * 0.1f;
  uint8_t counter = m.data[5];
  if (haveFrame && counter == lastCounter) {
    // Same frame again: the module is retransmitting because no node acknowledged it.
    repeats++;
    repeatsThisSecond++;
    return;
  }
  if (haveFrame && counter != (uint8_t)(lastCounter + 1)) {
    dropped += (uint8_t)(counter - lastCounter - 1);
  }
  lastCounter = counter;

  uint16_t changed = haveFrame ? (bits ^ lastBits) : bits;
  for (int i = 0; i < 16; i++) {
    if (changed & (1u << i)) {
      Serial.printf("%-20s %s\n", NAMES[i], (bits & (1u << i)) ? "ACTIVE" : "off");
    }
  }
  if (haveFrame && (m.data[6] & 1) != (lastFlags & 1)) {
    Serial.printf("Turn signal %s\n", (m.data[6] & 1) ? "FLASHING" : "stopped");
  }
  if (m.data[7] != 1 && !haveFrame) {
    Serial.printf("Note: frame layout version %u (this monitor decodes version 1)\n", m.data[7]);
  }
  lastBits = bits;
  lastDimV = dimV;
  lastDimPct = m.data[4];
  lastFlags = m.data[6];
  haveFrame = true;
}

void loop() {
  // At most 100 frames per pass, so a flooded bus (a node resending without
  // an ACK sends thousands a second) can't starve the summary below.
  twai_message_t m;
  for (int n = 0; n < 100 && twai_receive(&m, n ? 0 : pdMS_TO_TICKS(10)) == ESP_OK; n++) {
    if (m.identifier == CAN_ID_SIGNALS && !m.extd && m.data_length_code == 8) {
      bool repeat = haveFrame && m.data[5] == lastCounter;
      if (!repeat) {
        framesThisSecond++;
      }
      decode(m);
    } else {
      otherIds++;
    }
  }

  uint32_t alerts;
  if (twai_read_alerts(&alerts, 0) == ESP_OK) {
    if (alerts & TWAI_ALERT_TX_SUCCESS) testSent++;
    if (alerts & TWAI_ALERT_TX_FAILED) testFailed++;
  }

  uint32_t now = millis();
  if (now - lastSummaryMs >= 1000) {
    lastSummaryMs = now;
    twai_status_info_t s = {};
    twai_get_status_info(&s);
    if (s.state == TWAI_STATE_BUS_OFF) {
      twai_initiate_recovery();
    } else if (s.state == TWAI_STATE_STOPPED) {
      twai_start();
    } else if (CAN_ID_MONITOR_TEST && s.msgs_to_tx == 0) {
      twai_message_t t = {};
      t.identifier = CAN_ID_MONITOR_TEST;
      t.data_length_code = 1;
      t.data[0] = (uint8_t)(now / 1000);
      twai_transmit(&t, 0);
    }
    const char *state = s.state == TWAI_STATE_RUNNING      ? "running"
                        : s.state == TWAI_STATE_BUS_OFF    ? "BUS-OFF"
                        : s.state == TWAI_STATE_RECOVERING ? "recovering" : "stopped";
    Serial.printf("[monitor CAN %s, rx queue %lu, missed %lu] ", state,
                  (unsigned long)s.msgs_to_rx, (unsigned long)s.rx_missed_count);
    Serial.print("0x31B ");
    Serial.print(framesThisSecond);
    Serial.print("/s | inputs ");
    for (int i = 0; i < 16; i++) {
      Serial.print((lastBits & (1u << i)) ? '1' : '0');
      if (i % 4 == 3 && i != 15) Serial.print(' ');
    }
    Serial.printf(" | dimmer %.1f V (%u %%) | dropped %lu | repeats %lu | other IDs %lu | rx err %lu, tx err %lu"
                  " | test frames ok %lu, failed %lu, waiting %lu\n",
                  lastDimV, lastDimPct, (unsigned long)dropped, (unsigned long)repeats,
                  (unsigned long)otherIds, (unsigned long)s.rx_error_counter,
                  (unsigned long)s.tx_error_counter, (unsigned long)testSent,
                  (unsigned long)testFailed, (unsigned long)s.msgs_to_tx);
    if (repeatsThisSecond > 50) {
      Serial.println("  module is repeating frames = it gets no ACK from this monitor: check the monitor's TX pin and its transceiver's"
                     " 3V3/GND");
    } else if (framesThisSecond == 0) {
      Serial.println("  no 0x31B frames: check H/L wiring, the grounds, JP10, the monitor's RX pin, and that the module is powered");
    }
    framesThisSecond = 0;
    repeatsThisSecond = 0;
  }
}
