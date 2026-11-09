# 928 Signal Module firmware

Arduino sketch for the signal module (board rev A). It reads the 16
optocoupler inputs and the dash-dimmer voltage, and sends them on the EV CAN
bus at 500 kbit/s in one frame, **ID 0x31B** by default (changeable from the
settings page). That's next to the 0x31A frame the
[928 Waveshare dash](https://github.com/bapshago/928Wavesharedash) already
reads from the ZombieVerter.

## Arduino IDE setup (once)

1. Install the Arduino IDE 2.x.
2. **File → Preferences → Additional boards manager URLs**, add:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. **Tools → Board → Boards Manager**, search **esp32**, and install
   **"esp32 by Espressif Systems"** (built and tested with 3.3.12).
4. No extra libraries are needed. CAN uses the ESP32's built-in TWAI
   controller; the status page uses the core's WiFi and WebServer libraries.

> **CAN pins:** this board drives the transceiver from **GPIO27 (TX)** and
> **GPIO25 (RX)**. The AngryPixieDash board and `leaf_dash_v9.ino` use the
> reverse (TX 25, RX 27), so don't copy the pin numbers between the two
> sketches. `tests/test_firmware.py` checks the sketch against the board design.

## Upload

1. Open `signal_module_928.ino`. Arduino needs the sketch in a folder of the
   same name, which this one already is.
2. **Tools → Board → esp32 → ESP32 Dev Module.**
3. **Tools → Port:** the ESP32's COM port.
4. Click **Upload**. If it sits at "Connecting...", hold the **BOOT** button on
   the ESP32 board until the upload starts.
5. **Tools → Serial Monitor at 115200 baud.** You get a status line every
   second, plus a line whenever an input (other than the turn signal) changes:

   ```
   Inputs 1-16: 0000 0000 0000 0000  | dimmer 12.6 V | CAN running, sent 812, failed 0, tx errors 0
   CH5  Brake fluid      (1R): ACTIVE
   ```

## Status page over Wi-Fi (no serial cable)

The module runs its own Wi-Fi network, so this works on the bench and in the car:

1. Power the module and wait a few seconds.
2. On a phone or laptop, join **`928-Signal-Module`** (password **`porsche928`**).
3. Open **http://192.168.4.1**. Every channel shows ACTIVE/off (green when
   active) with its cluster pin, GPIO and a count of changes since start-up,
   so a short pulse you missed still shows. The top line has the dimmer
   voltage, the turn-signal flag and the CAN state and counters. It refreshes
   twice a second.

`http://192.168.4.1/status` gives the same data as JSON. Below the channels,
the page lists every CAN ID it hears on the bus, with counts. Orange banners
warn when the Wi-Fi password is still the default, or when CAN isn't sending
and why.

## Settings page

Open **http://192.168.4.1/settings** (link at the bottom of the status page).
Log in as user **`admin`** with the **Wi-Fi password**. Then you can change:

| Setting | Default | Notes |
|---|---|---|
| CAN ID | `0x31B` | 11-bit, 0x001–0x7FF. IDs other 928 EV nodes use (0x188, 0x1DA, 0x1DB, 0x292, 0x31A, 0x31C, 0x31D, 0x31E, 0x390, 0x398, 0x55A, 0x55B) are refused. The dash must be told about a new ID too. |
| Frame period | 100 ms | 20–1000 ms. Changes are also sent straight away (at most every 10 ms). |
| CAN mode | Send | **Send**; **Listen only** (never transmits or acknowledges; use it the first time on a new bus to see which IDs are in use); **Off**. |
| Wi-Fi name | `928-Signal-Module` | 1–32 characters. |
| Wi-Fi password | `porsche928` | 8–63 characters; leave blank to keep the current one. **Change it before the car goes on the road.** It's also the settings login. |
| Wi-Fi auto-off | 0 (never) | Minutes with no phone connected before Wi-Fi switches off until the next power-up. Fewer people can find the module, and it saves about 50 mA. |

**Save and restart** stores the settings in the ESP32's flash. They survive
power cycles and firmware updates. The module restarts about 2 s later.
If you changed the Wi-Fi name or password, join the new network.

**Locked out?** Hold the ESP32's **BOOT** button for **5 seconds** while the
module is running. All settings go back to the defaults above and it restarts.

`HOME_WIFI_SSID` / `HOME_WIFI_PASSWORD` at the top of the sketch make it also
join your home network on the bench; its address is printed on the serial port.

## Firmware update over Wi-Fi

No USB cable needed once the first version is on the board:

1. In the Arduino IDE: **Sketch → Export Compiled Binary**.
2. Open **http://192.168.4.1/update** (same login as the settings).
3. Pick **`signal_module_928.ino.bin`** from the sketch's `build` folder (not
   the `bootloader` or `merged` file) and press **Update**.
4. It takes about 30 s, then the module restarts. Settings are kept.

## Protecting the car's CAN bus

The module is built so it can't upset the bus even when something is wrong:

- **Single-shot frames.** A frame nobody acknowledges is dropped, not
  retransmitted. Normal CAN retries an unacknowledged frame immediately and
  endlessly, which floods the bus (exactly what happened on the bench with a
  faulty receiver).
- **Listens before talking.** For 1 s after start-up it only listens.
- **ID conflict check.** If it hears another node sending its ID, it stops
  sending until restarted and the status page says "ID conflict". (Two
  senders on one ID corrupt each other's frames.)
- **Bus-off back-off.** If errors push it off the bus, it waits 1 s before
  rejoining, then 2, 4 … up to 60 s if it keeps happening, instead of
  rejoining at once.
- **Listen-only and off modes** on the settings page, for a first look at a
  new bus, or to take the module off the bus without unplugging it.
- **No backlog.** At most 2 frames wait to be sent, so stale data never goes
  out in a burst.
- **Watchdog.** If the program ever hangs, the ESP32 restarts by itself.

Wiring still matters: no terminator on the module in the car (JP10 off; the
car's bus has its two), CAN-H to CAN-H, CAN-L to CAN-L, and the grounds joined.

**Power:** with Wi-Fi on, the ESP32 board draws about 100–150 mA at 5 V,
with short peaks up to about 400 mA at boot. That's about 60–70 mA at 12 V on
average. The Pololu D36V6F5 is rated 600 mA, so there's plenty of margin.
Set a bench supply's current limit to **300 mA or more**; a 100 mA limit
can reset the ESP32 when Wi-Fi starts. Transmit power is set low
(8.5 dBm), which is plenty inside the car.

Upload over USB with the module **not** powered from the car (or check
first that your ESP32 board has a diode on its USB 5 V; see the handoff doc).

## CAN frame: ID 0x31B (795), 8 bytes, 500 kbit/s

Sent every 100 ms, and right away when any input changes (at most every
10 ms).

| Byte | Content | Decoding |
|---|---|---|
| 0 | CH1–CH8 | bit 0 = CH1 … bit 7 = CH8; **1 = active** |
| 1 | CH9–CH16 | bit 0 = CH9 … bit 7 = CH16 |
| 2–3 | Dash dimmer voltage (14R) | little-endian, 0.1 V/bit (same as the 12 V value in 0x31A) |
| 4 | Dash dimmer level | 0–100 % of 14.0 V |
| 5 | Rolling counter | +1 per frame; if it stops changing, the module is silent |
| 6 | Flags | bit 0 = turn signal flashing (an edge on CH1 within the last second) |
| 7 | Frame layout version | currently 1 |

| Ch | Bit | Signal | Cluster pin | GPIO |
|---|---|---|---|---|
| CH1 | byte 0 bit 0 | Turn signal (raw; see also the flashing flag) | 13L | 34 |
| CH2 | byte 0 bit 1 | High beam | 1M | 35 |
| CH3 | byte 0 bit 2 | Lights on | 6L | 32 |
| CH4 | byte 0 bit 3 | Central warning | 5M | 33 |
| CH5 | byte 0 bit 4 | Brake fluid | 1R | 26 |
| CH6 | byte 0 bit 5 | Brake pad wear | 12R | 14 |
| CH7 | byte 0 bit 6 | Brake warning | 5R | 13 |
| CH8 | byte 0 bit 7 | Parking brake | 6R | 16 |
| CH9 | byte 1 bit 0 | Washer fluid | 10L | 17 |
| CH10–CH16 | byte 1 bits 1–7 | Spares | – | 18, 19, 21, 22, 23, 4, 36 |

The ID is set on the settings page. If you change the frame layout, bump
`FRAME_VERSION` so the dash can tell.

### Before putting it on the car's bus

- **Check 0x31B is free.** Neither the Leaf nor the ZombieVerter sends 0x31B
  by default, but a custom ZombieVerter TX mapping could. Easiest: set **CAN
  mode → Listen only**, connect the module, and look at the list of IDs heard
  on the status page for a minute. If 0x31B isn't there, switch back to
  **Send**. (Even in Send mode, the module stops if it hears its own ID.)
- **Bench testing:** a CAN controller needs at least one other node to
  acknowledge its frames. On the bench, connect a USB-CAN adapter at
  500 kbit/s and fit the JP10 shunt (and the adapter's terminator). Without a
  second node the status line shows tx errors (and "failed" frames); it
  recovers by itself once a node is connected.
- **No adapter?** A second ESP32 running
  `firmware/can_monitor_928/can_monitor_928.ino` works as the other node. It
  acknowledges the frames and prints the decoded inputs on its serial monitor.
  Easiest is a second signal module board (ESP32 sockets, J1, Pololu and J2
  fitted; jumpers not needed): the sketch's default pins (TX 27, RX 25) match
  it. Fit JP10 on both boards. A WCMCU-230 breakout also works (pins 21/22, see
  the top of the sketch).

## Testing without hardware

`tests/test_firmware.py` compiles the sketch on a PC against a fake Arduino
core and fake CAN, Wi-Fi, web server, settings-storage and update libraries
(`firmware/host_test/`), then checks the debounce, bit mapping, dimmer scaling,
turn-signal flag, send timing, the CAN safety rules (listen first, single
shot, ID conflict, bus-off back-off, listen-only), the status JSON, the
settings login and validation, Wi-Fi auto-off, BOOT-button reset and the
firmware update. It also checks the sketch's GPIOs against
`designs/signal_module_928.py`. The sketch compiles cleanly with esp32 3.3.12
for "ESP32 Dev Module" (about 74 % of the app partition, which leaves room for
updates over Wi-Fi with the default partition scheme).

## Reading it on the dash (suggested)

The dash's decoder lives in `main/core/leaf_can.c` in the 928Wavesharedash
repo. A matching case would look like:

```c
case 0x31B: {  // 928 signal module (pcbforge firmware/signal_module_928)
    uint16_t bits = (uint16_t)d[0] | ((uint16_t)d[1] << 8);
    s->high_beam     = bits & (1u << 1);   // CH2
    s->lights_on     = bits & (1u << 2);   // CH3
    s->central_warn  = bits & (1u << 3);   // CH4
    s->brake_fluid   = bits & (1u << 4);   // CH5
    s->brake_pad     = bits & (1u << 5);   // CH6
    s->brake_warn    = bits & (1u << 6);   // CH7
    s->park_brake    = bits & (1u << 7);   // CH8
    s->washer_fluid  = bits & (1u << 8);   // CH9
    s->turn_flashing = d[6] & 0x01;
    s->dimmer_v      = ((uint16_t)d[2] | ((uint16_t)d[3] << 8)) * 0.1f;
    return true;
}
```

(The field names are placeholders; the dash's `dash_state_t` doesn't have
these fields yet.)
