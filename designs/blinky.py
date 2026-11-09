"""Smallest useful board: a 2-pin power header feeding an LED through a resistor."""

from skidl import Net, Part

BOARD = {"width_mm": 30, "height_mm": 20}
PLACEMENT = {  # ref -> (x_mm, y_mm, rotation_deg)
    "J1": (5, 10, 0),
    "R1": (15, 10, 0),
    "D1": (23, 10, 0),
}


def build():
    vcc, gnd, led_a = Net("VCC"), Net("GND"), Net("LED_A")

    j1 = Part("Connector_Generic", "Conn_01x02", ref="J1",
              footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
    r1 = Part("Device", "R", ref="R1", value="330",
              footprint="Resistor_SMD:R_0805_2012Metric")
    d1 = Part("Device", "LED", ref="D1", value="red",
              footprint="LED_SMD:LED_0805_2012Metric")

    vcc += j1[1], r1[1]
    led_a += r1[2], d1["A"]
    gnd += j1[2], d1["K"]
