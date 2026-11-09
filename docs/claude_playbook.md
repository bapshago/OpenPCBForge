# pcbforge playbook for Claude

How to use pcbforge when someone asks for a board, a JLCPCB
order, firmware, or help bringing a board up. It records how the first boards were
actually made, ordered and tested, including what went wrong and how it was fixed.
`CLAUDE.md` has the short rules; `README.md` has the command reference. This is the
"how we work" document. `docs/user_guide.md` is the same process from the user's side;
keep the two consistent.

## Track record

| Board | What happened |
|---|---|
| 928 Signal Module rev A (`designs/signal_module_928.py`) | Designed, routed (DRC 0/0/0), ordered (5 boards, JLCPCB assembly), built and **bench tested Oct 28, 2026** (all 16 inputs, dimmer ADC and CAN 0x31B pass; one cold joint, fixed by resoldering; no design errors), and **installed in the '81 928 Nov 1, 2026**, with the firmware working: the first pcbforge board in real use. Log: `docs/signal_module_928_handoff.md` §8. |
| 928 Heater Controller rev A (`designs/heater_controller_928.py`) | Designed on the same outline, ordered Oct 23, 2026 (5 boards, all assembled); in production since Nov 5 after the C25741 fix, and the first live JLCPCB API `parts-check` passed (0 errors). Bring-up not done yet. Notes: `docs/heater_controller_928.md`. |
| A third-party motor controller (GPL-3.0, PADS → Altium → KiCad import) | No redesign: `pcbforge jlc` plus a small Gerber-fix script produced an order-ready BOM, CPL and corrected Gerbers. Ordered after the JLCPCB preview checks. |

The approach works: Claude writes the circuit and placement, KiCad + Freerouting do
the geometry and rule checks, and Claude checks every connection against datasheets
with tests before anything is ordered.

## 1. Environments

**Cloud session (Linux):** needs a Python that can `import pcbnew` (KiCad 9) and has
skidl installed, plus `kicad-cli`, Java 25+ and `tools/freerouting.jar`.
`scripts/setup_ubuntu.sh` sets all of that up (`.venv`); `scripts/get_freerouting.sh`
fetches the jar. Run `pytest` to confirm (about 1 minute; skips cleanly without KiCad).
For firmware, `arduino-cli` with the `esp32:esp32` core 3.3.12:
`arduino-cli compile --fqbn esp32:esp32:esp32 --warnings all firmware/<sketch>`.

**A Windows PC (cmd.exe):** run tools from the repo folder with KiCad's own Python:

```
"C:\Program Files\KiCad\9.0\bin\python.exe" -m pcbforge.cli jlc <board> --out build ...
```

Give Windows commands for cmd.exe (`^` line continuation, `%VAR%`), with full paths.
For anything longer than one command, write a `.bat` in `scripts/` with CRLF line
endings and `|| goto :fail` after each step.
Users flashing ESP32s typically use the Arduino IDE 2.x, and `git pull` to get new files.
Their `.env` (in the repo folder) can hold their JLCPCB API key for `parts-check`; set the
same keys in a cloud environment for Claude sessions there.

## 2. New board from a request

1. **Gather the request.** Use the checklist and template in
   a board request (purpose, power, modules, every input/output, connectors,
   mechanical, parts in hand, ordering). Never guess a pinout, dimension or part
   number: write "unknown" and ask, or find the datasheet. Parts the user already owns
   are designed around (e.g. the Leaf coolant pump, the Pololu D36V6F5).
2. **Pin down plug-in modules from the maker's documents.** Dev-board header spacing
   and pin 1 end differ between lookalike boards; use the dimension drawing
   (ESP32 boards used so far: rows 22.86 mm apart). Record the source in a comment.
3. **Write the design file** `designs/<name>.py`, following the two 928 boards:
   - module docstring: what the board is for, where the system context lives;
   - `BOARD` dict (outline, holes, `route_passes`, `route_attempts`, `ground_pour`,
     `pour_keepouts` for antennas, `hide_silk_refs` on dense boards,
     `jlc_ref_rotations` / `jlc_rotations`);
   - helpers `place(part, x, y, rot)`, `silk(...)`, `part(lib, name, ref, value, fp, lcsc=, mpn=)`;
   - constants for module geometry and a GPIO/channel table at the top, so tests
     and firmware can import them;
   - `build()` creating Parts and Nets, sectioned by function, with a comment
     wherever a choice was deliberate (why a pin, why a value).
   - Put `LCSC` (and `MPN`) on every SMD part you can; leftovers get matched in
     JLCPCB's BOM tool and written back afterwards.
4. **Write a connection test** `tests/test_<name>.py` that runs only the netlist step
   and checks the design against facts typed in **again** from the datasheets: module
   header pin → GPIO tables, forbidden GPIOs (strapping, flash, USB, console), every
   connector pin, every chip pin that matters, LCSC completeness, rotation overrides.
   This is what caught slips before ordering; don't skip it.
5. **Build and iterate:** `pcbforge build designs/<name>.py` until DRC is
   **0 errors, 0 warnings, 0 unconnected**. Fix by moving parts or changing the
   design, never by hand-editing copper. Busy boards: raise `route_passes`,
   `route_attempts: 3`.
6. **Render a preview PNG** for `docs/` and look at it: connector edges, silkscreen
   labels readable, polarity marks, antenna keep-out, mounting holes clear.
7. **Write the board doc** `docs/<name>.md`: what's on it, connector pin-out table
   (pin 1 = square pad), GPIO map, ordering notes, bring-up checks, open questions.
8. **Snapshot for fab:** copy board, Gerber zip, JLCPCB BOM/CPL, DRC report into
   `fab/<name>_rev_a/` with a README listing each file's use. The folder is a
   snapshot, not regenerated; rebuild and re-copy after any design change.
9. **Update** the README "Boards in this repo" table and, for 928 parts, the
   architecture doc (§7).

### Design rules that have held up

- **Vehicle power input:** fuse (1 A), SS34 series reverse-polarity diode, SMBJ24A
  TVS, then a Pololu D36V6F5 (12 V → 5 V, 600 mA) instead of an on-board switcher.
  With Wi-Fi the ESP32 draws ~100–150 mA at 5 V (peaks ~400 mA at start-up).
- **Inputs from 12 V wiring:** optocouplers with a series diode, so a wrong-polarity
  probe does nothing. Fixed high-side or low-side channels where the signal is known;
  "universal" channels with two 1x3 jumper headers where it isn't
  (HS: JP1 1–2 + JP2 2–3; LS: JP1 2–3 + JP2 1–2). Warn users: a shunt across the
  two headers' pin 3s shorts +12 V to GND.
- **Outputs:** low-side drivers (TPL7407L) with clamp diodes and pull-downs so every
  output stays off while the ESP32 boots; relay coils and solenoids are switched,
  heavy loads stay off the board in a fused relay holder.
- **ESP32:** ADC1 only when Wi-Fi is on (ADC2 is unavailable); avoid strapping, flash,
  USB and console pins; keep copper pour away from the antenna (`pour_keepouts`).
  Classic ESP32 GPIO 34–39 have no internal pull-ups, so put pull-ups on the board.
- **CAN:** SN65HVD230, 120 Ω terminator on a jumper (off when the board is a tap on
  an existing bus), NUP2105L protection, 500 kbit/s. Two buses on one board: ESP32
  TWAI + MCP2515 (8 MHz crystal).
- **Connectors:** JST XH by default, pin 1 = square pad at the top/left, silkscreen
  names on the board edge. Through-hole parts are hand-soldered by the user.
- **Silkscreen** every polarity-critical spot (power pins, module orientation such
  as SHDN/VOUT on the Pololu, 3V3/GND/antenna end of the ESP32, jumper meanings).
- **Footprints must exist in KiCad 9.** Library names changed between KiCad versions
  (KiCad 9 has no LFCSP footprints; use QFN/VQFN/HVQFN). A connection test that only
  builds the netlist passes with a footprint that doesn't exist, so tests for fine-pitch
  parts load the footprint (`env.footprint_lib_dir`) and check pitch, pad reach and
  exposed-pad size against the data sheet.
- **Fab limits on footprints:** JLCPCB 2-layer holes are 0.3 mm minimum, but KiCad's
  `ThermalVias` footprints use 0.2 mm. Adapted copies go in `footprints/pcbforge.pretty`
  (used as `pcbforge:Name`, listed in `footprints/README.md`): change only what the fab
  needs, never hand-draw pads. For 0.5 mm-pitch ICs set `BOARD["clearance_mm"] = 0.15`.
- **Fine-pitch escape room:** keep other parts about 2 mm off every edge of a 0.5 mm-pitch
  QFN, and rotate it so each side faces where its signals go. On the ADAU1772 module,
  decoupling caps 0.9 mm from the codec left 2-3 of its pins unrouted on every try; at
  about 2 mm it routed completely. Check placement first with `pcbforge build --no-route`
  (fast; only unconnected items should remain) before a 15-30 minute routed build.
- **Solder jumpers** (`Jumper:SolderJumper*`) are copper only; the JLCPCB BOM and CPL
  leave them out automatically.

## 3. Ordering at JLCPCB

Upload the Gerber zip, enable PCB Assembly (top side), upload BOM and CPL. Then:

- **BOM matching:** JLCPCB's comment check wants values like `4.7kΩ`, `100nF`, `2.2uF`;
  `pcbforge/jlc.py:jlc_value` writes them that way. The BOM must be UTF-8 **with a
  byte-order mark** (utf-8-sig) or `Ω` shows up as `惟`. Both are already handled.
- **Parts catalogue first:** pick parts from `pcbforge/parts.py` (`**parts.pick(name)`); the
  BOM falls back to it by footprint + value for parts without an LCSC number. The build's
  `<name>-jlc-parts.md` lists what's still to choose with JLCPCB/LCSC search links; point the
  user at it. Never invent an LCSC number.
- **Unmatched parts** (e.g. Y1 crystal → C57131): the user picks a part; write the LCSC
  number back into the design file (`lcsc=`) and the fab snapshot, and add it to
  `pcbforge/parts.py` (with `source`) if it will be reused.
- **Placement preview:** the user checks each part's rotation and polarity (pin 1 dot,
  diode/LED marks). Translate their report exactly: **"90° clockwise" = +270 in the CPL;
  "90° counter-clockwise" = +90.** Put the fix in the design (`jlc_ref_rotations` for
  one part, `jlc_rotations` for a footprint pattern) so a re-order needs none.
  Built-in table: `JLC_ROTATIONS` in `pcbforge/jlc.py`.
- **Check each LCSC number's package against the footprint** before ordering: run
  `pcbforge parts-check` on the design or its `fab/.../<name>-bom-jlc.csv` (the CSV needs no
  SKiDL, so it's what works with any KiCad Python on Windows). It needs the user's own JLCPCB API key for the
  parts endpoints in `JLC_APP_ID` / `JLC_ACCESS_KEY` / `JLC_SECRET_KEY` (setup and error
  meanings: `docs/jlcpcb_api.md`); `pcbforge jlc-auth` checks them without printing them.
  Never ask for the key values in chat. Without a key, check the part's LCSC page. The heater controller's 100k pull-downs carried C723496 next to the MPN
  0402WGF1003TCE, but C723496 is an 01005 part; JLCPCB caught it at assembly. The right
  number is C25741. Never take an LCSC number from memory.
- **Through-hole parts placed by JLCPCB** (sockets, headers, JST XH): KiCad's origin for
  these is pin 1, JLCPCB places by body centre. `jlc.body_centres` gives the CPL the courtyard
  centre for every through-hole footprint, and `JLC_ROTATIONS` turns 1xN 2.54 mm headers and
  sockets +270 (JLCPCB's models lie horizontal). Checked on the ANC bench carrier, Oct 2026.
- **After ordering:** save JLCPCB's confirmed BOM as `<name>-bom-as-ordered.csv` and a
  `<name>-not-placed-by-jlc.csv` (connectors, sockets, headers the user solders) in the
  fab folder; note date, quantity, finish and cost in its README.

## 4. Existing board → JLCPCB files (`pcbforge jlc`)

For boards drawn elsewhere. Options are in the README. Lessons from a third-party motor controller
(PADS → Altium → KiCad conversion):

- Real values may live in a custom field (`--value-field ALTIUM_VALUE`); "na"/DNP
  values are skipped automatically.
- Dual TO-220/D²PAK or DPAK "combo" footprints have long SMD tab pads and an origin at
  the TO-220 hole: `--include` them and `--move` them onto the real part centre;
  confirm in JLCPCB's preview.
- If the order uses the original tool's Gerbers, match their origin with `--offset`
  (e.g. −48.501, +200.004 mm).
- Imported Gerber sets can be unusable as-is (no outline, no paste, headerless drill
  file in another origin). The fix: keep the original
  copper/mask/silk, regenerate outline, paste and drill from KiCad in the same frame,
  and **verify every drill hit** against the original before zipping.
- Substitutes for obsolete parts: `--set-value` + `--lcsc` (e.g. RFP40N10 →
  IRL540NS C513158; LM317 D²PAK C173771).
- Check polarity against the copper nets (which pad is on which net), not only the
  silkscreen. Respect the project's license.

## 5. Firmware

- Arduino sketches in `firmware/<name>/<name>.ino` (folder name must match), with a
  README: IDE setup (esp32 core 3.3.12, "ESP32 Dev Module"), upload steps, CAN frame
  layout table, pin map.
- **Host test:** `firmware/host_test/` fakes the Arduino core, TWAI, WiFi and
  WebServer so `tests/test_firmware.py` compiles and runs the sketch with g++ and
  checks debounce, bit mapping, scaling, timing and the status JSON. A second test
  checks the sketch's GPIOs against the design file's channel table. Keep both when
  the sketch changes; compile with `arduino-cli` before pushing.
- **CAN:** 500 kbit/s, 11-bit IDs, IDs and frame layouts recorded in the architecture
  doc (0x31A ZombieVerter→dash, 0x31B signal module, 0x31D/0x31E heater). Include a
  rolling counter and a layout-version byte in every frame.
- **Wi-Fi status page** instead of a serial cable: the module runs its own access point
  (`928-Signal-Module`, http://192.168.4.1), page polls `/status` JSON twice a second,
  low TX power (8.5 dBm). Reuse this pattern on new boards.
- Commercial plans: prefer ESP-IDF (Apache-2.0) over the Arduino core (LGPL) for
  shipped products; bench and prototype firmware is fine in Arduino.

## 6. Bring-up and bench test

Follow this order and log results in the board doc's bench-test table:

1. Visual check; solder through-hole parts (sockets with the module inserted so they
   line up). Check the regulator module's orientation twice before soldering it.
2. Bare board on a bench supply at 12 V, **100 mA limit**: only the input stage draws.
3. Fit the 12→5 V module: 5 V at the ESP32's 5V pin before the ESP32 goes in.
4. Raise the limit to **300 mA** (Wi-Fi start-up resets the ESP32 at 100 mA), fit the
   ESP32, flash with 12 V off.
5. **USB + 12 V together** only if the ESP32 board has a diode between USB 5 V and
   its 5V pin. Check with DC volts: ESP32 alone on USB, VIN reads ~4.6–4.8 V = diode.
6. Inputs one by one with a flying lead (+12 V for high-side, GND for low-side), and
   the reverse (must do nothing). Universal channels: no shunts → nothing; then HS and
   LS. Watch the status page's change counters.
7. Analog: apply a known voltage (12.6 V on the dimmer read 12.6 V).
8. CAN against a second node. **Best partner: a second copy of the same board** running
   `firmware/can_monitor_928` (pins TX 27 / RX 25 match the signal board), JP10 on both
   ends (H–L reads 60 Ω with power off).

### Diagnosis notes from real faults

| Symptom | Cause found |
|---|---|
| One universal channel works low-side but not high-side | The two joints only that path uses; the GND one sat in the ground pour (heat-sinked, cold joint). Reflow with more heat. |
| CAN sender: `tx errors 128`, "failed" climbing, `sent` stuck at the queue size | Nobody acknowledges its frames (error-passive from ACK errors). The fault is at the receiver. |
| Monitor sees the same frame (same counter) thousands of times | Same thing: the sender retransmits because no ACK. |
| Receiver receives but its own frames never go out (bit errors → bus-off, stuck "recovering") | Its transceiver doesn't drive the bus. Here a WCMCU-230 breakout was faulty even with 3.3 V, D high and Rs low; a known-good board fixed it. |
| Dimmer reads ~0.8 V with nothing connected | Normal ESP32 ADC floor × the 5.7 divider. |

`firmware/can_tx_test` holds the transceiver input low/high for 5 s at a time so a
meter can check a transceiver drives the bus (CANH–CANL ~2 V dominant, ~0 V recessive).

## 7. Keep the documentation in sync

When a board's state changes (ordered, built, tested, revised), update all of:

- the board doc (`docs/<name>.md` or the signal module handoff doc) and its fab README;
- `README.md` "Boards in this repo";

Commit and push to `main` in this repo once tests pass (`pytest`, plus `arduino-cli`
compiles for changed sketches).

## 8. Working with the user

- Explain hardware steps in order, with the exact pin (connector-pin and position, e.g.
  "J4-5, the 10th pin from the top") and what the meter or page should show.
- Say what's safe to probe and what isn't; flag shorts and polarity risks before they
  happen.
- When a photo or result contradicts an assumption, trust the board and correct
  yourself plainly.
- Decisions the user has made stay made (e.g. 2-pin CAN connector, Pololu soldered directly);
  record them in the board doc.
