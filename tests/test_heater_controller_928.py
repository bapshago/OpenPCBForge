"""Check designs/heater_controller_928.py connection by connection.

Runs only the netlist step (SKiDL + KiCad symbol libraries), so it is fast and
needs no routing.
"""

import importlib.util

import pytest

from pcbforge import env

if not (env.SYMBOL_DIR / "Transistor_Array.kicad_sym").is_file():
    pytest.skip("KiCad symbol libraries not installed", allow_module_level=True)

from pcbforge.netlist import run_design  # noqa: E402

DESIGN = "designs/heater_controller_928.py"

# ESP32-S3-DevKitC-1 v1.1 header pin -> GPIO, typed in again from Espressif's user guide
# so a slip in the design's own table shows up here.
# J10 = DevKit J1 (3V3 ... 5V, G), J11 = DevKit J3 (G, TX, RX ... G).
S3_J1 = {4: 4, 5: 5, 6: 6, 7: 7, 8: 15, 9: 16, 10: 17, 11: 18, 12: 8, 13: 3, 14: 46,
         15: 9, 16: 10, 17: 11, 18: 12, 19: 13, 20: 14}
S3_J3 = {2: 43, 3: 44, 4: 1, 5: 2, 6: 42, 7: 41, 8: 40, 9: 39, 10: 38, 11: 37, 12: 36,
         13: 35, 14: 0, 15: 45, 16: 48, 17: 47, 18: 21, 19: 20, 20: 19}
SOCKET = {g: ("J10", p) for p, g in S3_J1.items()} | {g: ("J11", p) for p, g in S3_J3.items()}

# GPIOs the board must not use: GPIO0 (boot strap, must be high), 19/20 (USB),
# 43/44 (UART0 console), 35-37 (octal flash/PSRAM), 38 (on-board RGB LED)
FORBIDDEN = {0, 19, 20, 35, 36, 37, 38, 43, 44}


def _load_design_module():
    spec = importlib.util.spec_from_file_location("heater_controller_928", DESIGN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DESIGN_MOD = _load_design_module()


@pytest.fixture(scope="module")
def net(tmp_path_factory):
    design = run_design(DESIGN, tmp_path_factory.mktemp("hc"))
    parts = {p.ref: p for p in design.parts}

    def lookup(ref, pad):
        return parts[ref].pads.get(str(pad))
    lookup.parts = parts
    return lookup


def gpio_net(net, g):
    ref, pin = SOCKET[g]
    return net(ref, pin)


def test_devkit_table_matches_espressif():
    assert DESIGN_MOD.DEVKIT_J1 == S3_J1
    assert DESIGN_MOD.DEVKIT_J3 == S3_J3


def test_power(net):
    assert net("J1", 1) == "+12V_IN" and net("J1", 2) == "GND"
    assert net("F1", 1) == "+12V_IN" and net("F1", 2) == "+12V_FUSED"
    assert net("D10", 2) == "+12V_FUSED" and net("D10", 1) == "+12V_SW"   # Schottky: 1 = K, 2 = A
    assert net("D11", 1) == "+12V_SW" and net("D11", 2) == "GND"
    assert [net("J9", i) for i in (1, 2, 3, 4)] == [None, "+12V_SW", "GND", "+5V"]   # Pololu, SHDN open
    assert net("J10", 1) == "+3V3" and net("J10", 21) == "+5V" and net("J10", 22) == "GND"
    assert all(net("J11", p) == "GND" for p in (1, 21, 22))


def test_no_forbidden_or_shared_gpios(net):
    used = [g for g in SOCKET if gpio_net(net, g)]
    assert not FORBIDDEN & set(used)
    names = [gpio_net(net, g) for g in used]
    assert len(names) == len(set(names))                 # one net per GPIO, no two GPIOs shorted
    assert all(n.endswith(f"_GPIO{g}") for g, n in zip(used, names))


@pytest.mark.parametrize("i", range(12))
def test_output_channel(net, i):
    name, g, cref, cpin = DESIGN_MOD.OUTPUTS[i]
    u, ch = ("U5", i + 1) if i < 7 else ("U6", i - 6)
    gin = gpio_net(net, g)
    assert gin == f"{name}_GPIO{g}"
    assert net(u, ch) == gin                               # IN1-7 = pins 1-7
    assert net(u, 17 - ch) == name                         # OUT1 = pin 16 ... OUT7 = pin 10
    assert net(cref, cpin) == name
    assert {net(f"R{21 + i}", 1), net(f"R{21 + i}", 2)} == {gin, "GND"}   # 100k pull-down


def test_driver_supply_and_spares(net):
    for u in ("U5", "U6"):
        assert net(u, 8) == "GND" and net(u, 9) == "+12V_SW"   # COM clamps to +12 V
    assert net("U6", 6) == "GND" and net("U6", 7) == "GND"     # spare inputs grounded
    assert net("U6", 11) is None and net("U6", 10) is None     # spare outputs open


def test_strapping_outputs_have_pulldowns(net):
    # GPIO45 and 46 must be low at reset; their outputs carry 100k pull-downs
    for g in (45, 46):
        i = next(k for k, o in enumerate(DESIGN_MOD.OUTPUTS) if o[1] == g)
        assert DESIGN_MOD.OUTPUTS[i][0].startswith("SOL_")
        assert net(f"R{21 + i}", 2) == "GND"


@pytest.mark.parametrize("k", range(4))
def test_temperature_input(net, k):
    name, g = DESIGN_MOD.TEMPS[k]
    adc = gpio_net(net, g)
    assert g <= 10                                          # ADC1 (works with Wi-Fi on)
    assert net("J6", k + 1) == f"{name}_IN"
    assert {net(f"R{41 + 2 * k}", 1), net(f"R{41 + 2 * k}", 2)} == {"+3V3", f"{name}_IN"}
    assert {net(f"R{42 + 2 * k}", 1), net(f"R{42 + 2 * k}", 2)} == {f"{name}_IN", adc}
    assert {net(f"C{41 + k}", 1), net(f"C{41 + k}", 2)} == {adc, "GND"}
    assert net(f"D{41 + k}", 3) == adc                      # BAT54S common to the ADC pin
    assert net("J6", 5) == "GND"


def test_heater_sense_and_button(net):
    sense, btn = gpio_net(net, 6), gpio_net(net, 3)
    assert net("J7", 4) == "HTR_SENSE_IN"
    assert {net("R51", 1), net("R51", 2)} == {"HTR_SENSE_IN", sense}
    assert {net("R52", 1), net("R52", 2)} == {sense, "GND"}
    assert net("J7", 3) == "BTN_IN"
    assert {net("R56", 1), net("R56", 2)} == {"+3V3", "BTN_IN"}
    assert {net("R57", 1), net("R57", 2)} == {"BTN_IN", btn}
    assert net("J7", 5) == "GND"


def test_pump_command_and_feedback(net):
    pwm, fb = gpio_net(net, 16), gpio_net(net, 7)
    # GPIO16 -> 74AHCT1G125 (A = 2, Y = 4, ~OE = 1 grounded, VCC 5 V) -> 100 R -> J7 pin 1
    assert net("U7", 2) == pwm and net("U7", 1) == "GND" and net("U7", 5) == "+5V"
    assert {net("R59", 1), net("R59", 2)} == {net("U7", 4), "PUMP_PWM_OUT"}
    assert net("J7", 1) == "PUMP_PWM_OUT"
    # feedback: 4.7k to 5 V, 10k / 22k divider into GPIO7
    assert net("J7", 2) == "PUMP_FB_IN"
    assert {net("R53", 1), net("R53", 2)} == {"+5V", "PUMP_FB_IN"}
    assert {net("R54", 1), net("R54", 2)} == {"PUMP_FB_IN", fb}
    assert {net("R55", 1), net("R55", 2)} == {fb, "GND"}


def test_can_a_twai(net):
    assert net("U2", 1) == gpio_net(net, 17)   # D  <- TWAI TX
    assert net("U2", 4) == gpio_net(net, 18)   # R  -> TWAI RX
    assert net("U2", 7) == "CANA_H" and net("U2", 6) == "CANA_L"
    assert net("U2", 3) == "+3V3" and net("U2", 2) == "GND" and net("U2", 8) == "GND"
    assert [net("J2", p) for p in range(1, 6)] == ["CANA_H", "CANA_L", "GND", "CANB_H", "CANB_L"]


def test_can_b_mcp2515(net):
    pins = {"SCK": (13, 12), "SI": (14, 11), "SO": (15, 13), "CS": (16, 10), "INT": (12, 9)}
    for _, (pad, g) in pins.items():
        assert net("U3", pad) == gpio_net(net, g)
    assert net("U3", 18) == "+3V3" and net("U3", 9) == "GND"
    assert net("U3", 1) == net("U4", 1) == "CANB_TX"       # TXCAN -> transceiver D
    assert net("U3", 2) == net("U4", 4) == "CANB_RX"       # RXCAN <- transceiver R
    assert net("U4", 7) == "CANB_H" and net("U4", 6) == "CANB_L"
    assert net("Y1", 1) == net("U3", 8) and net("Y1", 3) == net("U3", 7)   # crystal on OSC1/OSC2


def test_can_termination_jumpers(net):
    for r, jp, h, l in (("R10", "JP1", "CANA_H", "CANA_L"), ("R11", "JP2", "CANB_H", "CANB_L")):
        assert net(r, 1) == h and net(r, 2) == net(jp, 1)
        assert net(jp, 2) == l


def test_jlc_rotation_fix_for_u7():
    # confirmed in JLCPCB's preview on the first order: SOT-23-5 model turned 90 deg clockwise
    assert DESIGN_MOD.BOARD["jlc_ref_rotations"] == {"U7": 270}


def test_every_smd_part_has_an_lcsc_number(net):
    smd = [p for ref, p in net.parts.items() if not ref.startswith(("J", "JP"))]
    assert smd and all(p.fields.get("LCSC") for p in smd), [p.ref for p in smd if not p.fields.get("LCSC")]


def test_pulldowns_are_0402(net):
    # JLCPCB rejected the first order (Nov 2026): C723496 is a 100k in 01005, not 0402.
    # C25741 is UNI-ROYAL 0402WGF1003TCE, 100k 1 % 0402, matching the R_0402 footprint.
    pulls = [p for ref, p in net.parts.items() if ref in {f"R{n}" for n in range(21, 33)}]
    assert len(pulls) == 12
    assert all(p.fields["LCSC"] == "C25741" and "0402" in p.footprint for p in pulls)
