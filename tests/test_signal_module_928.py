"""Check designs/signal_module_928.py against the rev 2 schematic, connection by connection.

Runs only the netlist step (SKiDL + KiCad symbol libraries), so it is fast and
needs no routing.
"""

import pytest

from pcbforge import env

if not (env.SYMBOL_DIR / "Isolator.kicad_sym").is_file():
    pytest.skip("KiCad symbol libraries not installed", allow_module_level=True)

from pcbforge.netlist import run_design  # noqa: E402

DESIGN = "designs/signal_module_928.py"

# ESP32 GPIO per channel, and where each GPIO sits on the DevKitC sockets (J7 = DevKitC J2, J8 = J3)
GPIO = {1: 34, 2: 35, 3: 32, 4: 33, 5: 26, 6: 14, 7: 13, 8: 16, 9: 17,
        10: 18, 11: 19, 12: 21, 13: 22, 14: 23, 15: 4, 16: 36}
SOCKET = {36: ("J7", "3"), 39: ("J7", "4"), 34: ("J7", "5"), 35: ("J7", "6"), 32: ("J7", "7"),
          33: ("J7", "8"), 25: ("J7", "9"), 26: ("J7", "10"), 27: ("J7", "11"), 14: ("J7", "12"),
          13: ("J7", "15"), 23: ("J8", "2"), 22: ("J8", "3"), 21: ("J8", "6"), 19: ("J8", "8"),
          18: ("J8", "9"), 17: ("J8", "11"), 16: ("J8", "12"), 4: ("J8", "13")}
HIGH, LOW = {2, 3}, {4, 5, 6, 7, 8, 9}


@pytest.fixture(scope="module")
def net(tmp_path_factory):
    design = run_design(DESIGN, tmp_path_factory.mktemp("sm"))
    parts = {p.ref: p for p in design.parts}

    def lookup(ref, pad):
        return parts[ref].pads.get(str(pad))
    lookup.parts = parts
    return lookup


def test_power_nets_keep_their_names(net):
    assert net("J1", 1) == "+12V_IN" and net("J1", 2) == "GND"
    assert net("F1", 1) == "+12V_IN" and net("F1", 2) == "+12V_FUSED"
    assert net("D10", 2) == "+12V_FUSED" and net("D10", 1) == "+12V_SW"   # Schottky: 1 = K, 2 = A
    assert net("D11", 1) == "+12V_SW" and net("D11", 2) == "GND"          # TVS cathode to +12 V
    assert {net("C10", 1), net("C10", 2)} == {"+12V_SW", "GND"}
    assert [net("J9", i) for i in (1, 2, 3, 4)] == [None, "+12V_SW", "GND", "+5V"]   # SHDN open
    assert net("J7", 1) == "+3V3" and net("J7", 19) == "+5V" and net("J7", 14) == "GND"
    assert net("J8", 1) == "GND" and net("J8", 7) == "GND"


@pytest.mark.parametrize("n", range(1, 17))
def test_channel(net, n):
    opto, unit = f"U{3 + (n - 1) // 4}", (n - 1) % 4 + 1
    gpio_net = f"CH{n}_GPIO{GPIO[n]}"
    led_a, led_k = net(opto, 2 * unit - 1), net(opto, 2 * unit)

    # D1 -> R1 -> LED anode; R2 across the LED; collector to GPIO with R3 pull-up and C1 filter
    assert net(f"D{100 + n}", 1) == net(f"R{100 + n}", 1)            # D1 cathode to R1
    assert net(f"R{100 + n}", 2) == led_a == f"CH{n}_LED_A"
    assert {net(f"R{200 + n}", 1), net(f"R{200 + n}", 2)} == {led_a, led_k}
    assert net(opto, 18 - 2 * unit) == gpio_net
    assert net(opto, 17 - 2 * unit) == "GND"
    assert {net(f"R{300 + n}", 1), net(f"R{300 + n}", 2)} == {"+3V3", gpio_net}
    assert {net(f"C{100 + n}", 1), net(f"C{100 + n}", 2)} == {gpio_net, "GND"}
    sock, pin = SOCKET[GPIO[n]]
    assert net(sock, pin) == gpio_net

    d1_anode = net(f"D{100 + n}", 2)
    if n in HIGH:
        assert (d1_anode, led_k) == (f"CH{n}_IN", "GND")
    elif n in LOW:
        assert (d1_anode, led_k) == ("+12V_SW", f"CH{n}_IN")
    else:  # universal: JP1 = IN | D1 anode | +12V_SW, JP2 = IN | LED cathode | GND
        assert [net(f"JP{100 + n}", i) for i in (1, 2, 3)] == [f"CH{n}_IN", d1_anode, "+12V_SW"]
        assert [net(f"JP{200 + n}", i) for i in (1, 2, 3)] == [f"CH{n}_IN", led_k, "GND"]


def test_input_connectors(net):
    expected = {
        "J3": ["CH1_IN", "CH2_IN", "CH3_IN", "CH4_IN", "CH5_IN"],
        "J4": ["CH6_IN", "CH7_IN", "CH8_IN", "CH9_IN", "DIM_IN"],
        "J5": ["CH10_IN", "CH11_IN", "CH12_IN", "CH13_IN", "CH14_IN"],
        "J6": ["CH15_IN", "CH16_IN", "GND", "GND", "GND"],
    }
    for ref, nets in expected.items():
        assert [net(ref, i) for i in range(1, 6)] == nets, ref


def test_dimmer_and_can(net):
    assert {net("R4", 1), net("R4", 2)} == {"DIM_IN", "DIM_ADC"}
    assert {net("R5", 1), net("R5", 2)} == {"DIM_ADC", "GND"}
    assert [net("D3", i) for i in (1, 2, 3)] == ["GND", "+3V3", "DIM_ADC"]   # BAT54S: A, K, COM
    assert net(*SOCKET[39]) == "DIM_ADC"

    u2 = {pin: net("U2", pin) for pin in range(1, 9)}
    assert u2 == {1: "CAN_TX", 2: "GND", 3: "+3V3", 4: "CAN_RX", 5: None, 6: "CANL", 7: "CANH", 8: "GND"}
    assert net(*SOCKET[27]) == "CAN_TX" and net(*SOCKET[25]) == "CAN_RX"
    assert [net("J2", i) for i in (1, 2, 3)] == ["CANH", "CANL", "GND"]
    assert net("R10", 1) == "CANH" and net("R10", 2) == net("JP10", 1) and net("JP10", 2) == "CANL"
    assert [net("D12", i) for i in (1, 2, 3)] == ["CANH", "CANL", "GND"]


def test_every_part_has_a_footprint_and_jlc_info(net):
    for ref, p in net.parts.items():
        assert ":" in p.footprint, ref
        assert p.fields.get("MPN") or p.fields.get("LCSC"), f"{ref} has no MPN/LCSC"
        if not p.footprint.split(":")[1].startswith(("JST_", "PinSocket_", "PinHeader_")):
            # every part JLCPCB assembles carries the LCSC number it was ordered with
            assert p.fields.get("LCSC", "").startswith("C"), f"{ref} has no LCSC number"
