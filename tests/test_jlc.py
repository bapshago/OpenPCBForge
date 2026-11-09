"""JLCPCB BOM/CPL formatting; needs no KiCad."""

import csv

import pytest

pytest.importorskip("skidl")
from pcbforge.jlc import JLC_ROTATIONS, write_bom, write_cpl  # noqa: E402
from pcbforge.netlist import Design, PartSpec  # noqa: E402


def test_bom_groups_identical_parts(tmp_path):
    design = Design(
        name="t",
        parts=[
            PartSpec("R10", "10k", "Resistor_SMD:R_0603_1608Metric", fields={"LCSC": "C1"}),
            PartSpec("R2", "10k", "Resistor_SMD:R_0603_1608Metric", fields={"LCSC": "C1"}),
            PartSpec("U1", "LTV-847S", "Package_DIP:SMDIP-16_W9.53mm", fields={"LCSC": "C114599", "MPN": "LTV-847S"}),
        ],
        nets=[], board={}, placement={},
    )
    rows = list(csv.reader(write_bom(design, tmp_path / "bom.csv").open(encoding="utf-8-sig")))
    assert rows[0] == ["Comment", "Designator", "Footprint", "LCSC Part #", "MPN"]
    assert ["10kΩ", "R2,R10", "0603", "C1", ""] in rows
    assert ["LTV-847S", "U1", "SMDIP-16", "C114599", "LTV-847S"] in rows


def test_cpl_from_kicad_pos(tmp_path):
    pos = tmp_path / "pos.csv"
    pos.write_text('Ref,Val,Package,PosX,PosY,Rot,Side\n"R1","10k","R_0603",12.5,-30.25,90.0,top\n')
    rows = list(csv.reader(write_cpl(pos, tmp_path / "cpl.csv").open()))
    assert rows == [["Designator", "Mid X", "Mid Y", "Layer", "Rotation"],
                    ["R1", "12.5000mm", "-30.2500mm", "Top", "90"]]


def test_cpl_rotation_corrections(tmp_path, monkeypatch):
    monkeypatch.setattr("pcbforge.jlc.JLC_ROTATIONS", [("^SOIC-", 270), ("^SOT-23$", 180)])
    pos = tmp_path / "pos.csv"
    pos.write_text("Ref,Val,Package,PosX,PosY,Rot,Side\n"
                   '"U1","x","SOIC-8_3.9x4.9mm_P1.27mm",0,0,0,top\n'
                   '"U2","x","SOIC-8_3.9x4.9mm_P1.27mm",0,0,180,top\n'
                   '"D1","x","SOT-23",0,0,90,top\n'
                   '"D2","x","SOT-23-5",0,0,0,top\n'
                   '"R1","x","R_0603_1608Metric",0,0,90,top\n')
    rows = {r[0]: r[4] for r in csv.reader(write_cpl(pos, tmp_path / "cpl.csv").open())}
    assert rows == {"Designator": "Rotation", "U1": "270", "U2": "90", "D1": "270", "D2": "0", "R1": "90"}

    # a design's own entries take precedence
    rows = {r[0]: r[4] for r in csv.reader(write_cpl(pos, tmp_path / "cpl2.csv", [("^SOIC-8", 90)]).open())}
    assert rows["U1"] == "90" and rows["D1"] == "270"

    # per-designator overrides beat both tables
    rows = {r[0]: r[4] for r in csv.reader(write_cpl(pos, tmp_path / "cpl3.csv", [("^SOIC-8", 90)], {"D1": 180, "U1": 0}).open())}
    assert rows["D1"] == "270" and rows["U1"] == "0" and rows["U2"] == "270"


def test_rotation_table_patterns_compile():
    import re
    for pattern, offset in JLC_ROTATIONS:
        re.compile(pattern)
        assert offset % 90 == 0


@pytest.mark.parametrize("ref,value,expected", [
    ("R4", "4k7", "4.7kΩ"), ("R8", "1k33", "1.33kΩ"), ("R7", "240R", "240Ω"), ("R19", "2R2", "2.2Ω"),
    ("R1", "10k", "10kΩ"), ("R59", "100", "100Ω"), ("R3", "1M", "1MΩ"), ("R41", "2.2k 1%", "2.2kΩ 1%"),
    ("R2", "10kΩ", "10kΩ"), ("C1", "100n", "100nF"), ("C8", "2u2", "2.2uF"), ("C15", "22p", "22pF"),
    ("C3", "1000u", "1000uF"), ("C10", "47u 63V", "47uF 63V"), ("C2", "100nF", "100nF"),
    ("L1", "FB 600R", "FB 600R"), ("D1", "GF1G", "GF1G"), ("R5", "na", "na"), ("U1", "10k", "10k"),
])
def test_jlc_value(ref, value, expected):
    from pcbforge.jlc import jlc_value
    assert jlc_value(ref, value) == expected


def test_bom_is_marked_utf8(tmp_path):
    design = Design(name="t", parts=[PartSpec("R1", "4k7", "Resistor_SMD:R_0603_1608Metric")],
                    nets=[], board={}, placement={})
    raw = write_bom(design, tmp_path / "bom.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and "4.7kΩ".encode() in raw


def test_solder_jumpers_left_out(tmp_path):
    from types import SimpleNamespace as NS
    from pcbforge.jlc import write_bom, write_cpl
    design = NS(parts=[NS(ref="JP1", value="SELFBOOT", footprint="Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm", fields={}),
                       NS(ref="R1", value="10k", footprint="Resistor_SMD:R_0603_1608Metric", fields={"LCSC": "C25804"})])
    bom = write_bom(design, tmp_path / "bom.csv").read_text(encoding="utf-8-sig")
    assert "R1" in bom and "JP1" not in bom
    pos = tmp_path / "pos.csv"
    pos.write_text("Ref,Val,Package,PosX,PosY,Rot,Side\n"
                   "JP1,SELFBOOT,SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm,1,2,0,top\n"
                   "R1,10k,R_0603_1608Metric,3,4,0,top\n")
    cpl = write_cpl(pos, tmp_path / "cpl.csv").read_text()
    assert "R1" in cpl and "JP1" not in cpl


def test_cpl_uses_body_centres_for_through_hole(tmp_path):
    pos = tmp_path / "pos.csv"
    pos.write_text("Ref,Val,Package,PosX,PosY,Rot,Side\n"
                   "J1,Sock,PinSocket_1x22_P2.54mm_Vertical,36,-10,0,top\n"
                   "R1,10k,R_0603_1608Metric,3,4,0,top\n")
    rows = {r[0]: r for r in csv.reader(write_cpl(pos, tmp_path / "cpl.csv", centres={"J1": (36.0, -36.67)}).open())}
    assert rows["J1"][1:3] == ["36.0000mm", "-36.6700mm"] and rows["J1"][4] == "270"   # centre, header turned
    assert rows["R1"][1:3] == ["3.0000mm", "4.0000mm"]


def test_body_centres_on_heater_controller():
    pytest.importorskip("pcbnew")
    from pcbforge.jlc import body_centres
    from pathlib import Path
    c = body_centres(Path(__file__).parent.parent / "fab/heater_controller_928_rev_a/heater_controller_928.kicad_pcb")
    assert abs(c["J10"][1] - (-(14 + 21 * 2.54 / 2))) < 0.1     # 1x22 socket: middle of its pins, not pin 1
    assert abs(c["J4"][1] - (-(12.95 + 5 * 2.5 / 2))) < 0.1     # XH-6 turned -90: middle of its pins
    assert abs(c["JP2"][1] - (-(74.6 + 2.54 / 2))) < 0.1        # 1x2 header
    assert "R21" not in c                                        # SMD parts keep their origin


def test_bom_defaults_to_catalogue_and_lists_the_rest(tmp_path):
    from pcbforge.jlc import write_parts_list
    design = Design(
        name="t",
        parts=[
            PartSpec("R1", "10k", "Resistor_SMD:R_0603_1608Metric"),                         # catalogue: C25804
            PartSpec("R2", "100k", "Resistor_SMD:R_0603_1608Metric"),                        # C25803, not the 100 ohm
            PartSpec("J1", "AIN0", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"),     # by footprint: C2316
            PartSpec("C1", "10u", "Capacitor_SMD:C_0805_2012Metric", fields={"LCSC": "C99"}),  # the design's own wins
            PartSpec("J2", "TEMP", "Connector_JST:JST_XH_B5B-XH-A_1x05_P2.50mm_Vertical"),     # not in the catalogue
        ],
        nets=[], board={}, placement={},
    )
    rows = {r[1]: r for r in csv.reader(write_bom(design, tmp_path / "bom.csv").open(encoding="utf-8-sig"))}
    assert rows["R1"][3] == "C25804" and rows["R2"][3] == "C25803" and rows["J1"][3] == "C2316"
    assert rows["C1"][3] == "C99" and rows["J2"][3] == "" and rows["J2"][2] == "XH-5A 2.5mm"
    md, todo = write_parts_list(design, tmp_path / "parts.md")
    text = md.read_text()
    assert todo == ["J2"]
    assert "https://jlcpcb.com/parts/componentSearch?isSearch=true&searchTxt=XH-5A" in text
    assert "[C25804](https://www.lcsc.com/product-detail/C25804.html)" in text and "catalogue" in text
