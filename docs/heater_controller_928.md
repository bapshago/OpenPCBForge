# 928 Heater Controller: board rev A

Cabin heat and defrost controller for the 1984 Porsche 928 S EV conversion.
Design file: `designs/heater_controller_928.py`; fab snapshot: `fab/heater_controller_928_rev_a/`
(routed, DRC 0 errors / 0 unconnected); preview: `heater_controller_928_rev_a.png`; connection tests:
`tests/test_heater_controller_928.py`.

Same 60 × 90 mm outline as the signal module (10 × 10 mm corner notches, M3
holes 79 mm apart on the centre line), so it fits the same enclosure.
The enclosure is the 100 x 68 x 50 mm box in `enclosure_100x68x50.png`
(buy link: https://a.co/d/0giEBknB).

## What's on it

- **ESP32-S3-DevKitC-1** in two 1×22 sockets (J10 = DevKit J1, J11 = DevKit J3),
  antenna end towards the top edge. Rows are 22.86 mm apart, per Espressif's
  dimension drawing.
- **Power** as on the signal module: J1 12 V in, 1 A fuse, SS34 reverse
  protection, SMBJ24A TVS, Pololu D36V6F5 (12 V → 5 V) in a socket. The
  DevKit's own regulator makes 3.3 V.
- **12 low-side outputs** on two TPL7407L drivers (U5, U6) with clamp diodes
  to +12 V and 100k pull-downs, so every output is off while the ESP32-S3 boots.
  Each channel handles the stock HVAC solenoids (about 0.29 A) and relay coils.
- **Two CAN buses:** CAN A (ESP32-S3 TWAI → SN65HVD230, U2) for the Outlander
  heater segment; CAN B (MCP2515 over SPI, U3, 8 MHz crystal → SN65HVD230, U4)
  for body CAN. Each has a 120 Ω terminator on a jumper (JP1 = A, JP2 = B) and
  NUP2105L protection.
- **Coolant pump:** 2 Hz speed command buffered to 5 V (74AHCT1G125, U7) and
  speed-feedback input (4.7k pull-up to 5 V, 10k/22k divider).
- **4 NTC temperature inputs** (2.2k pull-up to 3.3 V, 1k series, 100 nF,
  BAT54S clamp), a **heater feed sense** input (47k/10k divider) that tells the
  firmware the KSD301 cut-out has tripped, and the **defrost button** input.

The blower, pump and heater relays mount off the board (fused relay holder);
the board only switches their coil grounds.

## Connectors (JST XH, pin 1 at the top / left)

| Conn | Pin 1 | Pin 2 | Pin 3 | Pin 4 | Pin 5 | Pin 6 |
| --- | --- | --- | --- | --- | --- | --- |
| J1 power | +12 V | GND | | | | |
| J4 OUT1-6 | Blower master (wire 5) | Blower I | Blower II | Blower III | Blower IV | Pump relay |
| J5 OUT7-12 | Heater safety relay | Coolant valve | Impact wall | Air circulation | Defroster | Footwell |
| J6 TEMP | Coolant outlet | Coolant return | Cabin | Spare | GND | |
| J7 PUMP/BTN | Pump PWM (pump pin 3) | Pump feedback (pump pin 4) | Defrost button | Heater feed sense | GND | |
| J2 CAN | CAN A high | CAN A low | GND | CAN B high | CAN B low | |

Outputs are low-side: wire each relay coil or solenoid between fused +12 V and
its OUT pin.

## GPIO map (ESP32-S3)

| Function | GPIO |
| --- | --- |
| OUT1-6 (blower master, I, II, III, IV, pump relay) | 8, 14, 15, 21, 47, 48 |
| OUT7-12 (heater relay, coolant, impact, recirc, defrost, foot) | 39, 40, 41, 42, 45, 46 |
| Temperatures (outlet, return, cabin, spare), ADC1 | 1, 2, 4, 5 |
| Heater feed sense (ADC1) | 6 |
| Pump feedback (pulse counter) | 7 |
| Pump PWM command | 16 |
| Defrost button | 3 |
| CAN A TWAI TX / RX | 17 / 18 |
| CAN B SPI CS / MOSI / SCK / MISO / INT | 10 / 11 / 12 / 13 / 9 |

Not used: GPIO0 (boot strap), 19/20 (USB), 43/44 (serial console), 35-37
(octal flash/PSRAM), 38 (RGB LED on the DevKit, free for a status light).
GPIO45/46 are strapping pins that must be low at reset; their pull-downs keep
them low, so they drive the two least critical solenoids.

## Ordering notes

- **Nov 5, 2026: in production.** Option A (C25741) accepted. The first live JLCPCB API check
  (`pcbforge parts-check fab/heater_controller_928_rev_a/heater_controller_928-bom-jlc.csv`) passed
  with 0 errors: every package, value and stock level confirmed. C10 (C82011, 47 µF) had only 260
  in stock; check it before a larger order.

- **Nov 2, 2026:** JLCPCB held the order because the 12 pull-downs
  R21-R32 carried LCSC C723496, which is a 100k in **01005**, not 0402. Fix: option A, replace
  with **C25741** (UNI-ROYAL 0402WGF1003TCE, 100k 1 % 0402). The design, parts catalogue and
  `heater_controller_928-bom-jlc.csv` now use C25741; the as-ordered BOM keeps the original
  C723496 line as a record.

- Ordered Oct 23, 2026: 5 boards (green, 1.6 mm, ENIG), all 5 assembled by
  JLCPCB. The re-run from the repo files needed no manual fixes. Every assembled part now carries
  the LCSC number it was ordered with (checked against the as-ordered BOM in
  `fab/heater_controller_928_rev_a/`).
- **Y1, the 8 MHz crystal:** JLCPCB didn't match it automatically; it was added by
  hand as C57131 (1C208000BC0R, 8 MHz, 12 pF load, ±20 ppm, 3225). With the 22 pF
  caps (C15/C16) its load is about 14 pF, so it runs a few ppm slow, far inside
  CAN's timing tolerance; 18 pF caps would be exact on a future revision. Check
  its orientation in JLCPCB's preview (pin 1 to pad 1).
- Connectors, sockets and jumper headers are through-hole and not placed by
  JLCPCB (solder them yourself): see `heater_controller_928-not-placed-by-jlc.csv`.
- U7 (74AHCT1G125, SOT-23-5) needed turning 90° clockwise in JLCPCB's preview.
  That's now in the design (`jlc_ref_rotations = {"U7": 270}`) and in the CPL
  file, so a re-order should need no manual fixes. Still glance at the preview.

## Bring-up checks

1. Power up without the DevKit: 5 V at the Pololu output, nothing hot.
2. DevKit in, USB disconnected from the PC if the car's 12 V is on (the 5 V
   pin back-feeds USB on some DevKits).
3. Each output with a test lamp or relay: on/off from firmware, off during reset.
4. Pump: 24 % command ≈ 1030 rpm; feedback ≈ 34 Hz if it really is 2 pulses
   per revolution (rpm = Hz × 30). Adjust the constant if not.
5. CAN A and B each against a USB-CAN adapter at 500 kbit/s, terminators set to
   match the bus.
6. Still to measure on the car: blower switch position → wire map, whether wire
   5 is +12 V or ground, and the solenoid common wire (expected fused +12 V).
