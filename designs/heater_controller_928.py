"""928 Heater Controller, board rev A.

1984 Porsche 928 S cabin heat and defrost for the EV conversion: Outlander PHEV
coolant heater over CAN, Nissan Leaf coolant pump (2 Hz PWM + speed feedback),
the stock 4-speed blower (relays on the stock resistor group), five stock
vacuum solenoid valves, and coolant / cabin temperature sensors.
Board notes: docs/heater_controller_928.md.

Board: same 60 x 90 mm outline, corner notches and M3 holes as the signal
module (designs/signal_module_928.py), so both fit the same enclosure.
Coordinates are mm from the top-left of the bounding box, y pointing down.
Parts are placed on the top side only (JLCPCB assembly).

Parts new to this board (TPL7407L, MCP2515, 74AHCT1G125, crystal and some
passives) carry an MPN but no LCSC number yet: match them in JLCPCB's BOM tool
when ordering, as was done for the signal module.
"""

from skidl import Net, Part

# ---------------------------------------------------------------- board shape
W, H, NOTCH = 60.0, 90.0, 10.0
BOARD = {
    "width_mm": W,
    "height_mm": H,
    "outline": [
        (NOTCH, 0), (W - NOTCH, 0), (W - NOTCH, NOTCH), (W, NOTCH),
        (W, H - NOTCH), (W - NOTCH, H - NOTCH), (W - NOTCH, H), (NOTCH, H),
        (NOTCH, H - NOTCH), (0, H - NOTCH), (0, NOTCH), (NOTCH, NOTCH),
    ],
    "holes": [(W / 2, (H - 79) / 2), (W / 2, (H + 79) / 2)],  # M3, 79 mm apart on centre
    "silk": [],
    "hide_silk_refs": True,
    "route_passes": 60,
    "route_attempts": 3,
    "ground_pour": "GND",
    # JLCPCB's SOT-23-5 model for U7 (74AHCT1G125) needed turning 90 deg clockwise in their
    # preview on the first order (Oct 2026): +270 in the CPL. SOIC parts use the built-in table.
    "jlc_ref_rotations": {"U7": 270},
}

# ESP32-S3-DevKitC-1 v1.1 plugs into two 1x22 sockets. Per Espressif's dimension
# drawing (DXF_ESP32-S3-DevKitC-1_V1.1_20220429) the board is 25.4 mm wide with the
# pins 1.27 mm in from each edge, so the rows are 22.86 mm apart, the same as the
# signal module's ESP32 board. Pin 1 of J1 (3V3) and J3 (G) is at the antenna end;
# the module's antenna overhangs the DevKit about 6.5 mm past pin 1, and the two
# USB connectors stick out about 9.5 mm past pin 22.
DEVKIT_ROW_SPACING = 22.86
DEVKIT_X_RIGHT = 57.5                                  # DevKit J3 (G, TX, RX, 1, 2, 42 ...)
DEVKIT_X_LEFT = DEVKIT_X_RIGHT - DEVKIT_ROW_SPACING    # DevKit J1 (3V3, 3V3, RST, 4, 5 ...)
DEVKIT_Y_PIN1 = 14.0
BOARD["pour_keepouts"] = [(DEVKIT_X_LEFT - 1.5, 0.0, DEVKIT_X_RIGHT + 1.5, DEVKIT_Y_PIN1 + 2.0)]

PLACEMENT = {}


def place(part, x, y, rot=0):
    PLACEMENT[part.ref] = (x, y, rot)
    return part


def silk(x, y, text, size=0.8, rot=0):
    BOARD["silk"].append((x, y, text, size, rot))


def part(lib, name, ref, value, footprint, lcsc="", mpn=""):
    p = Part(lib, name, ref=ref, value=value, footprint=footprint)
    if lcsc:
        p.fields["LCSC"] = lcsc
    if mpn:
        p.fields["MPN"] = mpn
    return p


# Footprints
FP_R0402 = "Resistor_SMD:R_0402_1005Metric"
FP_R0603 = "Resistor_SMD:R_0603_1608Metric"
FP_R0805 = "Resistor_SMD:R_0805_2012Metric"
FP_C0603 = "Capacitor_SMD:C_0603_1608Metric"
FP_C0805 = "Capacitor_SMD:C_0805_2012Metric"
FP_SOT23 = "Package_TO_SOT_SMD:SOT-23"
FP_XH = "Connector_JST:JST_XH_B{n}B-XH-A_1x0{n}_P2.50mm_Vertical"
FP_HDR2 = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"
FP_SOCK22 = "Connector_PinSocket_2.54mm:PinSocket_1x22_P2.54mm_Vertical"

# DevKit header pin -> GPIO, per the ESP32-S3-DevKitC-1 v1.1 user guide.
# Not used: GPIO0, 45/46 at boot (strapping, see OUTPUTS), 19/20 (USB), 43/44 (UART0
# console), 35-37 (octal flash/PSRAM on N8R8 modules), 38 (on-board RGB LED).
DEVKIT_J1 = {4: 4, 5: 5, 6: 6, 7: 7, 8: 15, 9: 16, 10: 17, 11: 18, 12: 8, 13: 3, 14: 46,
             15: 9, 16: 10, 17: 11, 18: 12, 19: 13, 20: 14}
DEVKIT_J3 = {2: 43, 3: 44, 4: 1, 5: 2, 6: 42, 7: 41, 8: 40, 9: 39, 10: 38, 11: 37, 12: 36,
             13: 35, 14: 0, 15: 45, 16: 48, 17: 47, 18: 21, 19: 20, 20: 19}

# Low-side outputs: (net name, GPIO, connector, connector pin). OUT1-7 on U5, OUT8-12 on U6.
# GPIO45/46 are strapping pins that must be low at reset; their 100k pull-downs keep them
# low, so they drive two solenoids (an output that is briefly undefined at boot is harmless).
OUTPUTS = [
    ("BLW_MASTER", 8, "J4", 1),   # blower wire 5 (master relay)
    ("BLW_I", 14, "J4", 2),       # blower speed I tap relay
    ("BLW_II", 15, "J4", 3),
    ("BLW_III", 21, "J4", 4),
    ("BLW_IV", 47, "J4", 5),      # top speed, bypasses the resistors
    ("PUMP_RLY", 48, "J4", 6),    # coolant pump main power relay
    ("HTR_RLY", 39, "J5", 1),     # heater safety relay (KSD301 in series with its coil)
    ("SOL_COOLANT", 40, "J5", 2),
    ("SOL_IMPACT", 41, "J5", 3),
    ("SOL_RECIRC", 42, "J5", 4),
    ("SOL_DEFROST", 45, "J5", 5),
    ("SOL_FOOT", 46, "J5", 6),
]
TEMPS = [("T_OUTLET", 1), ("T_RETURN", 2), ("T_CABIN", 4), ("T_SPARE", 5)]  # (name, ADC1 GPIO) on J6 pins 1-4
GPIO_HTR_SENSE, GPIO_PUMP_FB, GPIO_BTN, GPIO_PUMP_PWM = 6, 7, 3, 16
GPIO_CANA_TX, GPIO_CANA_RX = 17, 18
GPIO_SPI_CS, GPIO_SPI_MOSI, GPIO_SPI_SCK, GPIO_SPI_MISO, GPIO_CANB_INT = 10, 11, 12, 13, 9


def build():
    gnd = Net("GND")
    v12_in, v12_fused, v12 = Net("+12V_IN"), Net("+12V_FUSED"), Net("+12V_SW")
    v5, v3 = Net("+5V"), Net("+3V3")
    gpio = {}

    def gnet(n, name):
        gpio[n] = Net(f"{name}_GPIO{n}")
        return gpio[n]

    # ------------------------------------------------------------ power (as the signal module)
    j1 = place(part("Connector_Generic", "Conn_01x02", "J1", "PWR", FP_XH.format(n=2),
                    mpn="B2B-XH-A(LF)(SN)"), 14.0, 5.0)
    j1[1] += v12_in
    j1[2] += gnd
    silk(14.0, 1.2, "12V GND", 0.8)

    f1 = place(part("Device", "Fuse", "F1", "1A", "Fuse:Fuse_1206_3216Metric",
                    lcsc="C151135", mpn="0466001.NRHF"), 23.5, 5.0, 90)
    f1[1, 2] += v12_in, v12_fused

    d10 = place(part("Device", "D_Schottky", "D10", "SS34", "Diode_SMD:D_SMA", lcsc="C8678", mpn="SS34"), 12.0, 24.6)
    d10["A"] += v12_fused
    d10["K"] += v12

    d11 = place(part("Device", "D_Zener", "D11", "SMBJ24A", "Diode_SMD:D_SMB", lcsc="C5178956", mpn="SMBJ24A"), 19.6, 24.6)
    d11["K"] += v12
    d11["A"] += gnd

    c10 = place(part("Device", "C_Polarized", "C10", "47u 63V", "Capacitor_SMD:CP_Elec_8x10.5",
                     lcsc="C82011", mpn="RVT1J470M0810"), 19.2, 16.0)
    c10[1] += v12
    c10[2] += gnd

    c11 = place(part("Device", "C", "C11", "100n 100V", FP_C0805, lcsc="C28233", mpn="CL21B104KCFNNNE"), 26.9, 24.6)
    c11[1, 2] += v12, gnd

    # Pololu D36V6F5 in a 1x4 socket: SHDN, VIN, GND, VOUT.
    j9 = place(part("Connector_Generic", "Conn_01x04", "J9", "Pololu D36V6F5",
                    "Connector_PinSocket_2.54mm:PinSocket_1x04_P2.54mm_Vertical",
                    mpn="1x4 2.54 mm female header (module: Pololu D36V6F5)"), 9.8, 12.6)
    j9[2] += v12
    j9[3] += gnd
    j9[4] += v5
    silk(12.35, 12.6, "SHDN", 0.8, 270)
    silk(12.35, 20.2, "VOUT", 0.8, 270)

    # ------------------------------------------------------------ ESP32-S3-DevKitC-1 (J10 = DevKit J1, J11 = DevKit J3)
    j10 = place(part("Connector_Generic", "Conn_01x22", "J10", "DevKit J1", FP_SOCK22,
                     mpn="1x22 2.54 mm female header"), DEVKIT_X_LEFT, DEVKIT_Y_PIN1)
    j11 = place(part("Connector_Generic", "Conn_01x22", "J11", "DevKit J3", FP_SOCK22,
                     mpn="1x22 2.54 mm female header"), DEVKIT_X_RIGHT, DEVKIT_Y_PIN1)
    socket = {g: (j10, p) for p, g in DEVKIT_J1.items()}
    socket.update({g: (j11, p) for p, g in DEVKIT_J3.items()})
    j10[1] += v3      # 3V3 from the DevKit's own regulator: pull-ups, MCP2515, CAN transceivers
    j10[21] += v5     # 5V in from the Pololu
    j10[22] += gnd
    for p in (1, 21, 22):
        j11[p] += gnd
    silk(DEVKIT_X_LEFT, DEVKIT_Y_PIN1 - 3.0, "3V3", 0.8)
    silk(DEVKIT_X_RIGHT, DEVKIT_Y_PIN1 + 56.8, "G", 0.8)
    silk((DEVKIT_X_LEFT + DEVKIT_X_RIGHT) / 2, DEVKIT_Y_PIN1 + 56.8, "ESP32-S3 USB end", 0.8)

    def to_gpio(n, name):
        sock, pin = socket[n]
        net = gnet(n, name)
        sock[pin] += net
        return net

    # ------------------------------------------------------------ left-edge connectors
    # Pin-1 y positions; the bodies (with courtyards) run edge to edge between the notches.
    conn = {
        "J4": (6, 12.95, "OUT1-6"),     # blower master, speeds I-IV, pump relay
        "J5": (6, 31.35, "OUT7-12"),    # heater relay, 5 solenoids
        "J6": (5, 49.75, "TEMP"),       # 4 NTC sensors + GND
        "J7": (5, 65.65, "PUMP/BTN"),   # pump PWM, pump feedback, defrost button, heater sense, GND
    }
    jc = {}
    for ref, (n, y, label) in conn.items():
        jc[ref] = place(part("Connector_Generic", f"Conn_01x0{n}", ref, label, FP_XH.format(n=n),
                             mpn=f"B{n}B-XH-A(LF)(SN)"), 4.2, y, 270)
        silk(2.4, y + (n - 1) * 1.25, label, 0.8, 90)

    # ------------------------------------------------------------ low-side outputs: 2 x TPL7407L
    # rot 180 puts OUT1-7 on the left (towards the connectors) and IN1-7 on the right.
    drivers = {}
    for k, (ref, y) in enumerate((("U5", 34.0), ("U6", 47.0))):
        u = place(part("Transistor_Array", "TPL7407LAD", ref, "TPL7407L", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
                       lcsc="C139663", mpn="TPL7407LDR"), 16.0, y, 180)
        u["GND"] += gnd
        u["COM"] += v12    # clamp diodes to +12 V (relay coils and solenoids run from the car's 12 V)
        c = place(part("Device", "C", f"C{20 + k}", "100n", FP_C0603, lcsc="C14663", mpn="CC0603KRX7R9BB104"),
                  16.0, y + 6.6)
        c[1, 2] += v12, gnd
        drivers[ref] = (u, y)

    out_nets = {}
    for i, (name, g, cref, cpin) in enumerate(OUTPUTS):
        ref = "U5" if i < 7 else "U6"
        u, uy = drivers[ref]
        ch = i + 1 if i < 7 else i - 6
        out = Net(name)
        out_nets[name] = out
        u[f"OUT{ch}"] += out
        jc[cref][cpin] += out
        gin = to_gpio(g, name)
        u[f"IN{ch}"] += gin
        # 100k pull-down beside each input pin: outputs stay off while the ESP32-S3 boots or resets
        r = place(part("Device", "R", f"R{20 + i + 1}", "100k", FP_R0402, lcsc="C25741", mpn="0402WGF1003TCE"),
                  21.6, uy + 4.445 - (ch - 1) * 1.27)
        r[1, 2] += gin, gnd
    u6 = drivers["U6"][0]
    u6["IN6"] += gnd   # spare channels: inputs grounded, outputs open
    u6["IN7"] += gnd

    # ------------------------------------------------------------ input conditioning (under the DevKit)
    def clamp(ref, x, y, node):
        d = place(part("Diode", "BAT54S", ref, "BAT54S", FP_SOT23, lcsc="C7420333", mpn="BAT54S"), x, y)
        d["A"] += gnd
        d["K"] += v3
        d["COM"] += node

    row_y = [19.0 + 3.4 * k for k in range(7)]
    X_R1, X_R2, X_C, X_D = 39.0, 42.4, 45.8, 50.6

    # NTC inputs: 2.2k pull-up to the ADC's own 3.3 V at the connector side, 1k series, 100n + clamp at the pin
    for k, (name, g) in enumerate(TEMPS):
        y = row_y[k]
        node_in = Net(f"{name}_IN")
        jc["J6"][k + 1] += node_in
        adc = to_gpio(g, name)
        r1 = place(part("Device", "R", f"R{41 + 2 * k}", "2.2k 1%", FP_R0603, lcsc="C2907005", mpn="0603WAF2201T5E"), X_R1, y)
        r1[1, 2] += v3, node_in
        r2 = place(part("Device", "R", f"R{42 + 2 * k}", "1k", FP_R0603, lcsc="C21190", mpn="0603WAF1001T5E"), X_R2, y)
        r2[1, 2] += node_in, adc
        c = place(part("Device", "C", f"C{41 + k}", "100n", FP_C0603, lcsc="C14663", mpn="CC0603KRX7R9BB104"), X_C, y)
        c[1, 2] += adc, gnd
        clamp(f"D{41 + k}", X_D, y, adc)
    jc["J6"][5] += gnd

    # Heater feed sense: 12 V after the heater safety relay, 47k/10k divider (as the dimmer input)
    y = row_y[4]
    sense_in = Net("HTR_SENSE_IN")
    jc["J7"][4] += sense_in
    sense = to_gpio(GPIO_HTR_SENSE, "HTR_SENSE")
    r = place(part("Device", "R", "R51", "47k", FP_R0603, lcsc="C25819", mpn="0603WAF4702T5E"), X_R1, y)
    r[1, 2] += sense_in, sense
    r = place(part("Device", "R", "R52", "10k", FP_R0603, lcsc="C25804", mpn="0603WAF1002T5E"), X_R2, y)
    r[1, 2] += sense, gnd
    c = place(part("Device", "C", "C51", "100n", FP_C0603, lcsc="C14663", mpn="CC0603KRX7R9BB104"), X_C, y)
    c[1, 2] += sense, gnd
    clamp("D51", X_D, y, sense)

    # Pump speed feedback (open-drain, reportedly 2 pulses/rev): 4.7k pull-up to 5 V,
    # 10k/22k divider -> about 3.0 V high at the GPIO (3.4 V if the pump drives 5 V push-pull)
    y = row_y[5]
    fb_in = Net("PUMP_FB_IN")
    jc["J7"][2] += fb_in
    fb = to_gpio(GPIO_PUMP_FB, "PUMP_FB")
    r = place(part("Device", "R", "R53", "4.7k", FP_R0603, lcsc="C23162", mpn="0603WAF4701T5E"), X_D + 3.6, y, 90)
    r[1, 2] += v5, fb_in
    r = place(part("Device", "R", "R54", "10k", FP_R0603, lcsc="C25804", mpn="0603WAF1002T5E"), X_R1, y)
    r[1, 2] += fb_in, fb
    r = place(part("Device", "R", "R55", "22k", FP_R0603, lcsc="C31850", mpn="0603WAF2202T5E"), X_R2, y)
    r[1, 2] += fb, gnd
    c = place(part("Device", "C", "C52", "1n", FP_C0603, lcsc="C1588", mpn="CC0603KRX7R9BB102"), X_C, y)
    c[1, 2] += fb, gnd
    clamp("D52", X_D, y, fb)

    # Defrost button to GND: 10k pull-up, 1k series, 10n
    y = row_y[6]
    btn_in = Net("BTN_IN")
    jc["J7"][3] += btn_in
    btn = to_gpio(GPIO_BTN, "BTN")
    r = place(part("Device", "R", "R56", "10k", FP_R0603, lcsc="C25804", mpn="0603WAF1002T5E"), X_R1, y)
    r[1, 2] += v3, btn_in
    r = place(part("Device", "R", "R57", "1k", FP_R0603, lcsc="C21190", mpn="0603WAF1001T5E"), X_R2, y)
    r[1, 2] += btn_in, btn
    c = place(part("Device", "C", "C53", "10n", FP_C0603, lcsc="C57112", mpn="CC0603KRX7R9BB103"), X_C, y)
    c[1, 2] += btn, gnd
    clamp("D53", X_D, y, btn)
    jc["J7"][5] += gnd

    # Pump speed command: 2 Hz PWM, 3.3 V GPIO -> 5 V through a 74AHCT1G125 (TTL-level input)
    pwm = to_gpio(GPIO_PUMP_PWM, "PUMP_PWM")
    pwm_buf, pwm_out = Net("PUMP_PWM_5V"), Net("PUMP_PWM_OUT")
    u7 = place(part("74xGxx", "74AHCT1G125", "U7", "74AHCT1G125", "Package_TO_SOT_SMD:SOT-23-5",
                    lcsc="C52140417", mpn="74AHCT1G125GV,125"), 27.0, 58.0)
    u7[1] += gnd       # ~OE: always enabled
    u7[2] += pwm
    u7[3] += gnd
    u7[4] += pwm_buf
    u7[5] += v5
    c = place(part("Device", "C", "C54", "100n", FP_C0603, lcsc="C14663", mpn="CC0603KRX7R9BB104"), 27.0, 54.8)
    c[1, 2] += v5, gnd
    r = place(part("Device", "R", "R58", "100k", FP_R0603, lcsc="C25803", mpn="0603WAF1003T5E"), 23.4, 58.0, 90)
    r[1, 2] += pwm, gnd   # pump command low while the ESP32-S3 boots
    r = place(part("Device", "R", "R59", "100", FP_R0603, lcsc="C22775", mpn="0603WAF1000T5E"), 27.0, 61.6)
    r[1, 2] += pwm_buf, pwm_out
    jc["J7"][1] += pwm_out

    # ------------------------------------------------------------ CAN A: ESP32-S3 TWAI -> SN65HVD230 (heater segment)
    # ------------------------------------------------------------ CAN B: MCP2515 over SPI -> SN65HVD230 (body CAN)
    j2 = place(part("Connector_Generic", "Conn_01x05", "J2", "CAN A/B", FP_XH.format(n=5),
                    mpn="B5B-XH-A(LF)(SN)"), 13.5, 85.6)

    def transceiver(ref, x, y, tx, rx, h, l, cref, rref, jpref, dref, jpx, jpy, rx_, ry_, dx, dy):
        u = place(part("Interface_CAN_LIN", "SN65HVD230", ref, "SN65HVD230DR", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                       lcsc="C12084", mpn="SN65HVD230DR"), x, y)
        u["D"] += tx
        u["R"] += rx
        u["VCC"] += v3
        u["GND"] += gnd
        u["Rs"] += gnd
        u["CANH"] += h
        u["CANL"] += l
        c = place(part("Device", "C", cref, "100n", FP_C0603, lcsc="C14663", mpn="CC0603KRX7R9BB104"), x, y - 4.4)
        c[1, 2] += v3, gnd
        term = Net(f"{h.name}_TERM")
        r = place(part("Device", "R", rref, "120", FP_R0805, lcsc="C54921099", mpn="HRC0805F1200FNTN"), rx_, ry_)
        r[1, 2] += h, term
        jp = place(part("Jumper", "Jumper_2_Open", jpref, "TERM", FP_HDR2, mpn="1x2 2.54 mm header + shunt"), jpx, jpy)
        jp[1, 2] += term, l
        d = place(part("Power_Protection", "NUP2105L", dref, "NUP2105L", FP_SOT23, lcsc="C284104", mpn="NUP2105L"), dx, dy)
        d[1] += h
        d[2] += l
        d["A"] += gnd

    cana_h, cana_l, canb_h, canb_l = Net("CANA_H"), Net("CANA_L"), Net("CANB_H"), Net("CANB_L")
    j2[1] += cana_h
    j2[2] += cana_l
    j2[3] += gnd
    j2[4] += canb_h
    j2[5] += canb_l
    transceiver("U2", 15.5, 75.0, to_gpio(GPIO_CANA_TX, "CANA_TX"), to_gpio(GPIO_CANA_RX, "CANA_RX"),
                cana_h, cana_l, "C12", "R10", "JP1", "D20", 31.0, 68.4, 12.3, 70.6, 14.5, 80.6)
    canb_tx, canb_rx = Net("CANB_TX"), Net("CANB_RX")
    transceiver("U4", 24.5, 75.0, canb_tx, canb_rx,
                canb_h, canb_l, "C13", "R11", "JP2", "D21", 31.0, 74.6, 21.0, 70.6, 23.0, 80.6)
    # CAN A = heater segment, CAN B = body CAN; J2 pins: 1 A-H, 2 A-L, 3 GND, 4 B-H, 5 B-L
    silk(33.9, 69.7, "A", 0.8, 90)
    silk(33.9, 73.1, "TERM", 0.8, 90)
    silk(33.9, 75.9, "B", 0.8, 90)

    # MCP2515 under the DevKit, SPI pins facing the DevKit's J1 row (rot 180)
    u3 = place(part("Interface_CAN_LIN", "MCP2515-xSO", "U3", "MCP2515", "Package_SO:SOIC-18W_7.5x11.6mm_P1.27mm",
                    lcsc="C153782", mpn="MCP2515-I/SO"), 45.0, 54.0, 180)
    u3["VDD"] += v3
    u3["VSS"] += gnd
    u3["SCK"] += to_gpio(GPIO_SPI_SCK, "SPI_SCK")
    u3["SI"] += to_gpio(GPIO_SPI_MOSI, "SPI_MOSI")
    u3["SO"] += to_gpio(GPIO_SPI_MISO, "SPI_MISO")
    u3["~{CS}"] += to_gpio(GPIO_SPI_CS, "SPI_CS")
    u3["~{INT}"] += to_gpio(GPIO_CANB_INT, "CANB_INT")
    u3["TXCAN"] += canb_tx
    u3["RXCAN"] += canb_rx
    rst = Net("CANB_RESET")
    u3["~{RESET}"] += rst
    r = place(part("Device", "R", "R12", "10k", FP_R0603, lcsc="C25804", mpn="0603WAF1002T5E"), 39.0, 45.6)
    r[1, 2] += v3, rst
    c = place(part("Device", "C", "C14", "100n", FP_C0603, lcsc="C14663", mpn="CC0603KRX7R9BB104"), 42.4, 45.6)
    c[1, 2] += v3, gnd
    osc1, osc2 = Net("CANB_OSC1"), Net("CANB_OSC2")
    u3["OSC1"] += osc1
    u3["OSC2"] += osc2
    y1 = place(part("Device", "Crystal_GND24", "Y1", "8MHz 12pF", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
                    lcsc="C57131", mpn="1C208000BC0R"), 53.0, 50.6, 90)
    y1[1] += osc1
    y1[3] += osc2
    y1[2] += gnd
    y1[4] += gnd
    # 22 pF with about 3 pF of stray puts the crystal's load near 14 pF, a little above Y1's
    # 12 pF: it runs a few ppm slow, far inside CAN's timing tolerance. 18 pF would be exact.
    for ref, yy, node in (("C15", 46.8, osc1), ("C16", 54.4, osc2)):
        c = place(part("Device", "C", ref, "22p", FP_C0603, lcsc="C1653", mpn="CC0603JRNPO9BN220"), 53.0, yy)
        c[1, 2] += node, gnd
