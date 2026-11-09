"""928 Signal Module, board rev A (from schematic rev 2).

1984 Porsche 928 S cluster-plug signals -> 16 optocoupler inputs + dash-dimmer
ADC -> ESP32-DevKitC -> SN65HVD230 -> EV CAN bus (500 kbit/s).

Source documents: "928 Signal Module Schematic rev 2.pdf" (3 sheets) and
"1984 928 S Cluster Plug Signal Map rev 2.docx". Deliberate changes from the
schematic are listed in docs/signal_module_928_handoff.md; search this file
for "REV A CHANGE" to find them.

Board: 60 x 90 mm with 10 x 10 mm corner notches, M3 holes on the centre line
79 mm apart, to fit the 100 x 68 x 50 mm enclosure. Coordinates are mm from
the top-left of the bounding box, y pointing down. Parts are placed on the top
side only (JLCPCB assembly).
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
    "hide_silk_refs": True,  # too dense for readable designators; JLCPCB places from the CPL file
    "route_passes": 60,      # Freerouting can need 20+ passes on this board
    "route_attempts": 3,     # and sometimes a second try (it isn't deterministic)
    "ground_pour": "GND",    # both layers, after routing
}

# The ESP32 board (AITRIP 38-pin "ESP-32S", same pinout as Espressif's DevKitC V4)
# plugs into two 1x19 sockets. Pin 1 of each header (3V3 / GND) is at the antenna
# end; the USB connector is at the pin-19 end. Its header rows are 22.86 mm (0.9")
# apart on a 25.4 mm wide board, per the seller's drawing.
DEVKIT_ROW_SPACING = 22.86
DEVKIT_X_RIGHT = 57.5                                  # DevKitC header J3 (GND ... CLK), at the board edge
DEVKIT_X_LEFT = DEVKIT_X_RIGHT - DEVKIT_ROW_SPACING    # DevKitC header J2 (3V3 ... 5V)
DEVKIT_Y_PIN1 = 22.0
# The module's antenna starts about 1 mm before pin 1 and runs ~6 mm past it.
# Keep poured copper (and parts) out from under it so Wi-Fi/BT still work.
BOARD["pour_keepouts"] = [(DEVKIT_X_LEFT - 1.5, 10.0, DEVKIT_X_RIGHT + 1.5, DEVKIT_Y_PIN1 + 7.0)]

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
FP_R0603 = "Resistor_SMD:R_0603_1608Metric"
FP_R0805 = "Resistor_SMD:R_0805_2012Metric"
FP_R1206 = "Resistor_SMD:R_1206_3216Metric"
FP_C0603 = "Capacitor_SMD:C_0603_1608Metric"
FP_R0402 = "Resistor_SMD:R_0402_1005Metric"
FP_C0402 = "Capacitor_SMD:C_0402_1005Metric"
FP_C0805 = "Capacitor_SMD:C_0805_2012Metric"
FP_SOD323 = "Diode_SMD:D_SOD-323"
FP_XH = "Connector_JST:JST_XH_B{n}B-XH-A_1x0{n}_P2.50mm_Vertical"
FP_HDR3 = "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical"
FP_HDR2 = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"

# Cluster-plug channels: (signal, cluster pin, input type, ESP32 GPIO)
CHANNELS = {
    1: ("Turn signal", "13L", "universal", 34),
    2: ("High beam", "1M", "high", 35),
    3: ("Lights on", "6L", "high", 32),
    4: ("Central warning", "5M", "low", 33),
    5: ("Brake fluid", "1R", "low", 26),
    6: ("Brake pad wear", "12R", "low", 14),
    7: ("Brake warning", "5R", "low", 13),
    8: ("Parking brake", "6R", "low", 16),
    9: ("Washer fluid", "10L", "low", 17),
    10: ("Spare", "-", "universal", 18),
    11: ("Spare", "-", "universal", 19),
    12: ("Spare", "-", "universal", 21),
    13: ("Spare", "-", "universal", 22),
    14: ("Spare", "-", "universal", 23),
    15: ("Spare", "-", "universal", 4),
    16: ("Spare", "-", "universal", 36),
}


def build():
    gnd = Net("GND")  # car ground (9R) and ESP32 ground are one net (tied through the 5 V supply)
    v12_in, v12_fused, v12 = Net("+12V_IN"), Net("+12V_FUSED"), Net("+12V_SW")
    v5, v3 = Net("+5V"), Net("+3V3")
    can_tx, can_rx, canh, canl = Net("CAN_TX"), Net("CAN_RX"), Net("CANH"), Net("CANL")
    dim_in, dim_adc = Net("DIM_IN"), Net("DIM_ADC")
    ch_in = {n: Net(f"CH{n}_IN") for n in CHANNELS}
    ch_gpio = {n: Net(f"CH{n}_GPIO{gpio}") for n, (_, _, _, gpio) in CHANNELS.items()}

    # ------------------------------------------------------------ power (sheet 1)
    j1 = place(part("Connector_Generic", "Conn_01x02", "J1", "PWR 3R/9R", FP_XH.format(n=2),
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

    # REV A CHANGE: drawn bidirectional on the schematic; the BOM part (SMBJ24A) is unidirectional.
    d11 = place(part("Device", "D_Zener", "D11", "SMBJ24A", "Diode_SMD:D_SMB", lcsc="C5178956", mpn="SMBJ24A"), 19.6, 24.6)
    d11["K"] += v12
    d11["A"] += gnd

    # REV A CHANGE: 100 uF 63 V is a 10 mm can; 47 uF 63 V fits 8 x 10.5 mm and still meets
    # Pololu's ">= 33 uF across VIN when above 28 V" requirement.
    c10 = place(part("Device", "C_Polarized", "C10", "47u 63V", "Capacitor_SMD:CP_Elec_8x10.5",
                     lcsc="C82011", mpn="RVT1J470M0810"), 19.2, 16.0)
    c10[1] += v12
    c10[2] += gnd

    c11 = place(part("Device", "C", "C11", "100n 100V", FP_C0805, lcsc="C28233", mpn="CL21B104KCFNNNE"), 26.9, 24.6)
    c11[1, 2] += v12, gnd

    # REV A CHANGE: U10 is the Pololu D36V6F5 module (agreed), plugged into a 1x4 socket.
    # Socket pins follow Pololu's order SHDN, VIN, GND, VOUT; check against the labels on your module.
    j9 = place(part("Connector_Generic", "Conn_01x04", "J9", "Pololu D36V6F5",
                    "Connector_PinSocket_2.54mm:PinSocket_1x04_P2.54mm_Vertical",
                    mpn="1x4 2.54 mm female header (module: Pololu D36V6F5)"), 9.8, 12.6)
    j9[2] += v12   # VIN
    j9[3] += gnd   # GND
    j9[4] += v5    # VOUT; pin 1 (SHDN) left open = always on
    # The module fits either way round; backwards puts 12 V on its GND pin. Label both ends
    # to match the SHDN / VOUT printing on the back of the Pololu board.
    silk(12.35, 12.6, "SHDN", 0.8, 270)
    silk(12.35, 20.2, "VOUT", 0.8, 270)

    # ------------------------------------------------------------ ESP32-DevKitC (U1)
    j7 = place(part("Connector_Generic", "Conn_01x19", "J7", "DevKitC J2",
                    "Connector_PinSocket_2.54mm:PinSocket_1x19_P2.54mm_Vertical",
                    mpn="1x19 2.54 mm female header"), DEVKIT_X_LEFT, DEVKIT_Y_PIN1)
    j8 = place(part("Connector_Generic", "Conn_01x19", "J8", "DevKitC J3",
                    "Connector_PinSocket_2.54mm:PinSocket_1x19_P2.54mm_Vertical",
                    mpn="1x19 2.54 mm female header"), DEVKIT_X_RIGHT, DEVKIT_Y_PIN1)
    gpio_pin = {  # GPIO -> (socket, pin) per the Espressif DevKitC V4 user guide
        36: (j7, 3), 39: (j7, 4), 34: (j7, 5), 35: (j7, 6), 32: (j7, 7), 33: (j7, 8),
        25: (j7, 9), 26: (j7, 10), 27: (j7, 11), 14: (j7, 12), 13: (j7, 15),
        23: (j8, 2), 22: (j8, 3), 21: (j8, 6), 19: (j8, 8), 18: (j8, 9),
        17: (j8, 11), 16: (j8, 12), 4: (j8, 13),
    }
    j7[1] += v3      # 3V3 out of the DevKitC's own regulator: pull-ups and CAN transceiver
    j7[14] += gnd
    j7[19] += v5     # 5V in from the Pololu
    j8[1] += gnd
    j8[7] += gnd
    for n, (_, _, _, gpio) in CHANNELS.items():
        sock, pin = gpio_pin[gpio]
        sock[pin] += ch_gpio[n]
    sock, pin = gpio_pin[39]
    sock[pin] += dim_adc
    sock, pin = gpio_pin[25]
    sock[pin] += can_rx
    sock, pin = gpio_pin[27]
    sock[pin] += can_tx
    silk(DEVKIT_X_LEFT, DEVKIT_Y_PIN1 - 3.0, "3V3", 0.8)
    silk(DEVKIT_X_RIGHT, DEVKIT_Y_PIN1 - 3.0, "GND", 0.8)
    silk((DEVKIT_X_LEFT + DEVKIT_X_RIGHT) / 2, DEVKIT_Y_PIN1 - 3.0, "ESP32 antenna end", 0.8)
    silk(DEVKIT_X_LEFT, DEVKIT_Y_PIN1 + 48.6, "5V", 0.8)

    # ------------------------------------------------------------ CAN (sheet 1)
    # REV A CHANGE: bare SN65HVD230 chip instead of the WCMCU-230 breakout (no hidden 120 R terminator).
    u2 = place(part("Interface_CAN_LIN", "SN65HVD230", "U2", "SN65HVD230DR", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                    lcsc="C12084", mpn="SN65HVD230DR"), 38.0, 76.6)
    u2["D"] += can_tx
    u2["R"] += can_rx
    u2["VCC"] += v3
    u2["GND"] += gnd
    u2["Rs"] += gnd      # Rs to GND = high-speed mode
    u2["CANH"] += canh
    u2["CANL"] += canl   # Vref (pin 5) left open

    c12 = place(part("Device", "C", "C12", "100n", FP_C0603, lcsc="C14663", mpn="CC0603KRX7R9BB104"), 37.5, 71.6)
    c12[1, 2] += v3, gnd

    term = Net("CAN_TERM")
    r10 = place(part("Device", "R", "R10", "120", FP_R0805, lcsc="C54921099", mpn="HRC0805F1200FNTN"), 45.6, 75.4)
    r10[1, 2] += canh, term
    jp10 = place(part("Jumper", "Jumper_2_Open", "JP10", "TERM", FP_HDR2,
                      mpn="1x2 2.54 mm header + shunt"), 48.0, 82.6)
    jp10[1, 2] += term, canl
    silk(48.0, 88.2, "TERM", 0.8)

    # REV A ADDITION: dual-line CAN ESD/transient protection at the connector.
    d12 = place(part("Power_Protection", "NUP2105L", "D12", "NUP2105L", "Package_TO_SOT_SMD:SOT-23",
                     lcsc="C284104", mpn="NUP2105L"), 46.4, 78.3)
    d12[1] += canh
    d12[2] += canl
    d12["A"] += gnd

    j2 = place(part("Connector_Generic", "Conn_01x03", "J2", "CAN", FP_XH.format(n=3),
                    mpn="B3B-XH-A(LF)(SN)"), 37.0, 85.6)
    j2[1] += canh
    j2[2] += canl
    j2[3] += gnd     # shield drain; ground it at this end only if the other end is not grounded
    silk(39.5, 81.3, "H  L  SHLD", 0.8)

    # ------------------------------------------------------------ dash dimmer (sheet 2 D)
    j4_dim = dim_in  # lands on J4 pin 5 below
    r4 = place(part("Device", "R", "R4", "47k", FP_R0603, lcsc="C25819", mpn="0603WAF4702T5E"), 27.3, 16.4, 90)
    r4[1, 2] += j4_dim, dim_adc
    r5 = place(part("Device", "R", "R5", "10k", FP_R0603, lcsc="C25804", mpn="0603WAF1002T5E"), 29.2, 16.4, 90)
    r5[1, 2] += dim_adc, gnd
    c2 = place(part("Device", "C", "C2", "100n", FP_C0603, lcsc="C14663", mpn="CC0603KRX7R9BB104"), 28.2, 20.3)
    c2[1, 2] += dim_adc, gnd
    d3 = place(part("Diode", "BAT54S", "D3", "BAT54S", "Package_TO_SOT_SMD:SOT-23", lcsc="C7420333", mpn="BAT54S"), 28.0, 12.6)
    d3["A"] += gnd
    d3["K"] += v3
    d3["COM"] += dim_adc

    # ------------------------------------------------------------ input connectors (agreed: 4 x JST XH 5-pin)
    # J3: CH1-5, J4: CH6-9 + DIM, J5: CH10-14, J6: CH15, CH16, GND x3
    conn_nets = {
        "J3": [ch_in[1], ch_in[2], ch_in[3], ch_in[4], ch_in[5]],
        "J4": [ch_in[6], ch_in[7], ch_in[8], ch_in[9], dim_in],
        "J5": [ch_in[10], ch_in[11], ch_in[12], ch_in[13], ch_in[14]],
        "J6": [ch_in[15], ch_in[16], gnd, gnd, gnd],
    }
    labels = {"J3": "CH1-5", "J4": "CH6-9,DIM", "J5": "CH10-14", "J6": "CH15,16,GND"}
    for i, (ref, nets) in enumerate(conn_nets.items()):
        y = 14.6 + i * 16.3
        j = place(part("Connector_Generic", "Conn_01x05", ref, f"Inputs {labels[ref]}", FP_XH.format(n=5),
                       mpn="B5B-XH-A(LF)(SN)"), 4.2, y, 270)
        for pin, net in enumerate(nets, start=1):
            j[pin] += net
        silk(2.4, y + 5.0, labels[ref], 0.8, 90)   # inside the connector body, between wall and pins

    # ------------------------------------------------------------ 16 opto channels (sheet 2 A/B/C)
    # REV A CHANGE: TLP291-4 (SOP-16) instead of PC847 (DIP-16). Same 4-channel phototransistor
    # pinout; the DIP-size part doesn't fit between the ESP32 board's 22.86 mm header rows.
    # Optos U3-U6 sit in one column under the ESP32 board, below the antenna: LED pins (1-8)
    # face the input side on the left, transistor pins (9-16) face a column of R3/C1 on the right.
    # (A 2 x 2 grid left a 1.4 mm gap that every LED and GPIO net had to squeeze through.)
    optos, opto_y = {}, [35.0, 46.0, 57.0, 68.0]
    for k in range(4):
        optos[k] = place(part("Isolator", "TLP291-4", f"U{3 + k}", "TLP291-4", "Package_SO:SOIC-16_4.55x10.3mm_P1.27mm",
                              lcsc="C60900", mpn="TLP291-4(GB-TP,E)"), 44.6, opto_y[k])
    # Universal-channel jumper headers for the spares, three channels per row, JP1 then JP2.
    spare_header_x = [9.3 + p * 8.2 + j * 3.8 for p in range(3) for j in range(2)]
    for n, (_, _, kind, _) in CHANNELS.items():
        opto, unit = optos[(n - 1) // 4], (n - 1) % 4 + 1
        # Pick each node's net up front. (Merging two named SKiDL nets keeps an arbitrary name,
        # which once renamed GND to "CH2_LED_K".)
        led_a = Net(f"CH{n}_LED_A")
        if kind == "high":        # +12 V when active: IN feeds D1, LED cathode to ground
            top, led_k = ch_in[n], gnd
        elif kind == "low":       # pulled to ground when active: +12V_SW feeds D1, LED cathode to IN
            top, led_k = v12, ch_in[n]
        else:                     # universal: JP1 picks IN/+12V for D1, JP2 picks GND/IN for the cathode
            top, led_k = Net(f"CH{n}_D1_A"), Net(f"CH{n}_LED_K")
        opto[2 * unit - 1] += led_a
        opto[2 * unit] += led_k
        opto[18 - 2 * unit] += ch_gpio[n]   # collector
        opto[17 - 2 * unit] += gnd          # emitter

        # Input side: two columns of 8 rows (CH1-8 left, CH9-16 right) beside the input connectors.
        col, row = (n - 1) // 8, (n - 1) % 8
        x0, y = 9.5 + col * 12.5, 29.4 + row * 2.4
        d1 = place(part("Device", "D", f"D{100 + n}", "1N4148WS", FP_SOD323, lcsc="C2128", mpn="1N4148WS"), x0, y)
        r1 = place(part("Device", "R", f"R{100 + n}", "2.2k", FP_R1206, lcsc="C2930413", mpn="FRC1206F2201TS"), x0 + 4.1, y)
        r2 = place(part("Device", "R", f"R{200 + n}", "10k", FP_R0603, lcsc="C25804", mpn="0603WAF1002T5E"), x0 + 8.1, y)
        # GPIO side: R3 and C1 level with this channel's collector pin (pin 18 - 2 * unit).
        # REV A CHANGE: 0402 instead of 0603 so they fit beside the opto column.
        gy = opto_y[(n - 1) // 4] + (-4.45, -1.91, 0.64, 3.18)[unit - 1]
        r3 = place(part("Device", "R", f"R{300 + n}", "10k", FP_R0402, lcsc="C60490", mpn="RC0402FR-0710KL"), 50.6, gy, 90)
        c1 = place(part("Device", "C", f"C{100 + n}", "10n", FP_C0402, lcsc="C15195", mpn="CL05B103KB5NNNC"), 52.4, gy, 90)

        d1["A"] += top
        d1["K"] += r1[1]
        r1[2] += led_a
        r2[1, 2] += led_a, led_k            # LED shunt / pull-down
        r3[1, 2] += v3, ch_gpio[n]          # GPIO pull-up
        c1[1, 2] += ch_gpio[n], gnd         # GPIO filter

        if kind == "universal":
            if n == 1:
                # CH1 (turn signal, polarity still to be metered) keeps header + shunt jumpers.
                jp1 = place(part("Jumper", "Jumper_3_Open", "JP101", "CH1 JP1", FP_HDR3,
                                 mpn="1x3 2.54 mm header + shunt"), 37.0, 2.4)
                jp2 = place(part("Jumper", "Jumper_3_Open", "JP201", "CH1 JP2", FP_HDR3,
                                 mpn="1x3 2.54 mm header + shunt"), 41.2, 2.4)
                silk(46.9, 3.0, "CH1", 0.8)
                silk(46.9, 5.4, "HS 12/23", 0.8)
                silk(46.9, 7.4, "LS 23/12", 0.8)
            else:
                i = n - 10                                  # CH10-16 -> 0-6
                hx1, hx2 = spare_header_x[(i % 3) * 2], spare_header_x[(i % 3) * 2 + 1]
                hy = 51.0 + (i // 3) * 10.0
                jp1 = place(part("Jumper", "Jumper_3_Open", f"JP{100 + n}", f"CH{n} JP1", FP_HDR3,
                                 mpn="1x3 2.54 mm header + shunt"), hx1, hy)
                jp2 = place(part("Jumper", "Jumper_3_Open", f"JP{200 + n}", f"CH{n} JP2", FP_HDR3,
                                 mpn="1x3 2.54 mm header + shunt"), hx2, hy)
                silk((hx1 + hx2) / 2, hy - 2.5, f"CH{n}", 0.8)
            jp1[1] += ch_in[n]
            jp1[2] += top
            jp1[3] += v12
            jp2[1] += ch_in[n]
            jp2[2] += led_k
            jp2[3] += gnd
