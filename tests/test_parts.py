"""The parts catalogue (pcbforge/parts.py): well-formed entries, real KiCad footprints, safe matching."""

import re

import pytest

from pcbforge import env, parts


def test_entries_are_well_formed():
    for name, p in parts.CATALOG.items():
        assert re.fullmatch(r"C\d+", p.lcsc), name
        assert p.mpn and p.footprint and p.source, name
    assert parts.pick("res_0603_10k") == {"lcsc": "C25804", "mpn": "0603WAF1002T5E"}


def test_catalogue_footprints_exist():
    pcbnew = pytest.importorskip("pcbnew")
    libs = ["Resistor_SMD", "Capacitor_SMD", "Inductor_SMD", "Diode_SMD", "Package_TO_SOT_SMD", "Package_SO", "Fuse",
            "Crystal", "Connector_JST", "Connector_PinHeader_2.54mm", "Connector_PinSocket_2.54mm", "pcbforge"]
    for name, p in parts.CATALOG.items():
        found = any(pcbnew.FootprintLoad(str(env.footprint_lib_dir(lib)), p.footprint) is not None
                    for lib in libs if env.footprint_lib_dir(lib).is_dir())
        assert found, f"{name}: footprint {p.footprint} not in KiCad 9 or footprints/pcbforge.pretty"


@pytest.mark.parametrize("footprint, value, lcsc", [
    ("R_0603_1608Metric", "4k7", "C23162"),
    ("R_0603_1608Metric", "4.7kΩ", "C23162"),
    ("R_0603_1608Metric", "100k", "C25803"),     # not the 100 ohm part
    ("R_0603_1608Metric", "100", "C22775"),
    ("R_0603_1608Metric", "2.2k 1%", "C2907005"),
    ("C_0603_1608Metric", "100nF", "C14663"),
    ("C_0603_1608Metric", "0.1u", "C14663"),
    ("JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical", "AIN0", "C2316"),
    ("SOT-23", "2N7002", "C8545"),
    ("SOT-23", "BAT54S", "C7420333"),
    ("R_0603_1608Metric", "2.0k", "C22975"),
    ("C_0603_1608Metric", "10u", "C19702"),
    ("R_0603_1608Metric", "330", None),          # never ordered (and not the 33 ohm): left for JLCPCB's BOM tool
    ("C_0603_1608Metric", "47u", None),
    ("JST_XH_B5B-XH-A_1x05_P2.50mm_Vertical", "TEMP", None),
])
def test_match(footprint, value, lcsc):
    hit = parts.match(footprint, value)
    assert (hit.lcsc if hit else None) == lcsc


def test_search_terms_use_jlcpcb_names():
    assert parts.jlc_package("R_0603_1608Metric") == "0603"
    assert parts.jlc_package("SOIC-8_3.9x4.9mm_P1.27mm") == "SOIC-8"
    assert parts.search_terms("JST_XH_B5B-XH-A_1x05_P2.50mm_Vertical", "TEMP") == "XH-5A"
    assert parts.search_terms("R_0603_1608Metric", "2.0k") == "2.0k 0603 resistor"
    assert parts.search_terms("R_0603_1608Metric", "2.0kΩ") == "2.0k 0603 resistor"
    assert parts.search_terms("PinSocket_1x19_P2.54mm_Vertical", "x") == "2.54mm 1x19 female header"
