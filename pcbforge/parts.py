"""Parts catalogue: JLCPCB/LCSC parts already ordered or checked on pcbforge boards.

A design can pick a part by name (`part(..., **parts.pick("res_0603_10k"))`), and the
JLCPCB BOM falls back to the catalogue for any part without an LCSC number of its own:
passives and ICs match on footprint + value, connectors and headers on footprint alone
(their value is a label such as "AIN0"). Parts nothing matches get search terms and links
in `<board>-jlc-parts.md`, so they can be looked up on JLCPCB/LCSC without guessing.

Only add parts that were ordered or checked in JLCPCB's BOM tool; say where in `source`.
Never guess an LCSC number.
"""

import re
from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True)
class CatalogPart:
    lcsc: str
    mpn: str
    footprint: str      # KiCad footprint name (no library prefix)
    value: str          # matching value: "10k", "100n", "SN65HVD230DR"; "" = any (connectors)
    source: str         # board / order where it was used or checked


CATALOG: dict[str, CatalogPart] = {
    # Resistors
    "res_0402_10k": CatalogPart("C60490", "RC0402FR-0710KL", "R_0402_1005Metric", "10k", "signal module"),
    "res_0402_100k": CatalogPart("C25741", "0402WGF1003TCE", "R_0402_1005Metric", "100k", "heater controller (C723496, used before Nov 2 2026, is 01005: wrong)"),
    "res_0603_100": CatalogPart("C22775", "0603WAF1000T5E", "R_0603_1608Metric", "100", "heater controller"),
    "res_0603_1k": CatalogPart("C21190", "0603WAF1001T5E", "R_0603_1608Metric", "1k", "heater controller, ANC carrier"),
    "res_0603_2k2": CatalogPart("C2907005", "0603WAF2201T5E", "R_0603_1608Metric", "2.2k", "heater controller, ANC carrier"),
    "res_0603_4k7": CatalogPart("C23162", "0603WAF4701T5E", "R_0603_1608Metric", "4.7k", "heater controller, ANC carrier"),
    "res_0603_10k": CatalogPart("C25804", "0603WAF1002T5E", "R_0603_1608Metric", "10k", "heater controller, ANC carrier"),
    "res_0603_22k": CatalogPart("C31850", "0603WAF2202T5E", "R_0603_1608Metric", "22k", "heater controller"),
    "res_0603_47k": CatalogPart("C25819", "0603WAF4702T5E", "R_0603_1608Metric", "47k", "signal module, heater controller"),
    "res_0603_100k": CatalogPart("C25803", "0603WAF1003T5E", "R_0603_1608Metric", "100k", "heater controller, ANC carrier"),
    "res_0805_120": CatalogPart("C54921099", "HRC0805F1200FNTN", "R_0805_2012Metric", "120", "signal module (CAN terminator)"),
    "res_1206_2k2": CatalogPart("C2930413", "FRC1206F2201TS", "R_1206_3216Metric", "2.2k", "signal module (opto inputs)"),
    # Capacitors
    "cap_0402_10n": CatalogPart("C15195", "CL05B103KB5NNNC", "C_0402_1005Metric", "10n", "signal module"),
    "cap_0603_22p": CatalogPart("C1653", "CC0603JRNPO9BN220", "C_0603_1608Metric", "22p", "heater controller"),
    "cap_0603_1n": CatalogPart("C1588", "CC0603KRX7R9BB102", "C_0603_1608Metric", "1n", "heater controller"),
    "cap_0603_10n": CatalogPart("C57112", "CC0603KRX7R9BB103", "C_0603_1608Metric", "10n", "heater controller"),
    "cap_0603_100n": CatalogPart("C14663", "CC0603KRX7R9BB104", "C_0603_1608Metric", "100n", "all boards"),
    "cap_0805_100n_100v": CatalogPart("C28233", "CL21B104KCFNNNE", "C_0805_2012Metric", "100n", "signal module, heater controller (12 V input)"),
    "cap_0805_10u": CatalogPart("C15850", "CL21A106KAYNNNE", "C_0805_2012Metric", "10u", "ANC carrier (JLCPCB match, Oct 2026)"),
    "cap_elec_47u_63v": CatalogPart("C82011", "RVT1J470M0810", "CP_Elec_8x10.5", "47u", "signal module, heater controller"),
    # Discretes and protection
    "diode_ss34": CatalogPart("C8678", "SS34", "D_SMA", "SS34", "signal module, heater controller"),
    "tvs_smbj24a": CatalogPart("C5178956", "SMBJ24A", "D_SMB", "SMBJ24A", "signal module, heater controller"),
    "diode_1n4148ws": CatalogPart("C2128", "1N4148WS", "D_SOD-323", "1N4148WS", "signal module"),
    "diode_bat54s": CatalogPart("C7420333", "BAT54S", "SOT-23", "BAT54S", "heater controller"),
    "tvs_nup2105l": CatalogPart("C284104", "NUP2105L", "SOT-23", "NUP2105L", "signal module, heater controller (CAN)"),
    "fet_2n7002": CatalogPart("C8545", "2N7002", "SOT-23", "2N7002", "ANC carrier (JLCPCB match, Oct 2026)"),
    "fuse_1206_1a": CatalogPart("C151135", "0466001.NRHF", "Fuse_1206_3216Metric", "1A", "signal module, heater controller"),
    # ICs and crystals
    "can_sn65hvd230": CatalogPart("C12084", "SN65HVD230DR", "SOIC-8_3.9x4.9mm_P1.27mm", "SN65HVD230DR", "signal module, heater controller"),
    "can_mcp2515": CatalogPart("C153782", "MCP2515-I/SO", "SOIC-18W_7.5x11.6mm_P1.27mm", "MCP2515", "heater controller"),
    "driver_tpl7407l": CatalogPart("C139663", "TPL7407LDR", "SOIC-16_3.9x9.9mm_P1.27mm", "TPL7407L", "heater controller"),
    "opto_tlp291_4": CatalogPart("C60900", "TLP291-4(GB-TP,E)", "SOIC-16_4.55x10.3mm_P1.27mm", "TLP291-4", "signal module"),
    "buffer_74ahct1g125": CatalogPart("C52140417", "74AHCT1G125GV,125", "SOT-23-5", "74AHCT1G125", "heater controller"),
    "codec_adau1772": CatalogPart("C578954", "ADAU1772BCPZ-R7", "HVQFN-40-1EP_6x6mm_P0.5mm_EP4.1x4.1mm_ThermalVias0.3mm", "ADAU1772BCPZ", "ANC DSP module"),
    "xtal_8mhz_12pf": CatalogPart("C57131", "1C208000BC0R", "Crystal_SMD_3225-4Pin_3.2x2.5mm", "8MHz", "heater controller (JLCPCB match)"),
    "xtal_12m288_20pf": CatalogPart("C2901655", "SX3B12.288F2010F30", "Crystal_SMD_3225-4Pin_3.2x2.5mm", "12.288MHz", "ANC DSP module"),
    # ANC DSP module (ADAU1772), JLCPCB matched BOM, Oct 30 2026
    "res_0603_33": CatalogPart("C23140", "0603WAF330JT5E", "R_0603_1608Metric", "33", "ANC DSP module"),
    "res_0603_2k0": CatalogPart("C22975", "0603WAF2001T5E", "R_0603_1608Metric", "2.0k", "ANC DSP module"),
    "res_0603_200k": CatalogPart("C25811", "0603WAF2003T5E", "R_0603_1608Metric", "200k", "ANC DSP module"),
    "cap_0603_33p": CatalogPart("C1663", "CL10C330JB8NNNC", "C_0603_1608Metric", "33p", "ANC DSP module"),
    "cap_0603_1u": CatalogPart("C15849", "CL10A105KB8NNNC", "C_0603_1608Metric", "1u", "ANC DSP module"),
    "cap_0603_4u7": CatalogPart("C19666", "CL10A475KO8NNNC", "C_0603_1608Metric", "4.7u", "ANC DSP module"),
    "cap_0603_10u": CatalogPart("C19702", "CL10A106KP8NNNC", "C_0603_1608Metric", "10u", "ANC DSP module (10 V)"),
    "ferrite_0603_220r": CatalogPart("C66810", "GZ1608D221TF", "L_0603_1608Metric", "220R@100MHz", "ANC DSP module"),
    "ldo_tlv70018": CatalogPart("C79924", "TLV70018DDCR", "SOT-23-5", "TLV70018", "ANC DSP module (noisier than LP5907)"),
    "eeprom_24aa256": CatalogPart("C152172", "24AA256T-I/SN", "SOIC-8_3.9x4.9mm_P1.27mm", "24AA256", "ANC DSP module"),
    "i2c_shifter_pca9306": CatalogPart("C5119911", "PCA9306DC1Z", "VSSOP-8_2.3x2mm_P0.5mm", "PCA9306", "ANC DSP module (NXP)"),
    "level_shifter_sn74lvc1t45": CatalogPart("C7843", "SN74LVC1T45DBVR", "SOT-23-6", "SN74LVC1T45", "ANC DSP module"),
    # Connectors and headers (through-hole; JLCPCB fits them when they're in the BOM)
    "xh_2pin": CatalogPart("C2908600", "XH-2A", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", "", "ANC carrier (JLCPCB match, Oct 2026)"),
    "xh_3pin": CatalogPart("C2316", "XH-3A", "JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical", "", "ANC carrier (JLCPCB match, Oct 2026; C2908601 also matched)"),
    "header_1x2": CatalogPart("C5360898", "PZ2.54-1*2", "PinHeader_1x02_P2.54mm_Vertical", "", "ANC carrier (JLCPCB match, Oct 2026)"),
    "header_1x4": CatalogPart("C5116483", "2.54-1*4", "PinHeader_1x04_P2.54mm_Vertical", "", "ANC carrier (JLCPCB match, Oct 2026)"),
    "header_1x6": CatalogPart("C37208", "2.54-1x6P", "PinHeader_1x06_P2.54mm_Vertical", "", "ANC carrier (JLCPCB match, Oct 2026)"),
    "socket_1x22": CatalogPart("C53200741", "XY-PM254-1-22P-Z-8.5", "PinSocket_1x22_P2.54mm_Vertical", "", "ANC carrier (JLCPCB match, Oct 2026)"),
}


def pick(name: str) -> dict:
    """`lcsc` and `mpn` keyword arguments for a design file's part() helper."""
    p = CATALOG[name]
    return {"lcsc": p.lcsc, "mpn": p.mpn}


_UNITS = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6, "": 1.0}
_NUM = re.compile(r"^(\d+(?:\.\d+)?)([pnuµmkM]?)(\d*)(?:F|Ω|R|ohms?|Hz)?$")


def _quantity(value: str):
    """'4k7' / '4.7k' / '4.7kΩ' -> 4700.0; '100n' / '100nF' -> 1e-7; None if it isn't a number."""
    first = value.split()[0] if value.split() else ""
    m = _NUM.match(first.replace("R", "") if re.match(r"^\d+R\d*$", first) else first)
    if not m:
        return None
    whole, unit, frac = m.groups()
    num = float(f"{whole}.{frac}") if frac and "." not in whole else float(whole)
    return num * _UNITS[unit]


def match(footprint: str, value: str):
    """The catalogue part for a footprint (no library prefix) and value, or None."""
    q = _quantity(value)
    for p in CATALOG.values():
        if p.footprint != footprint:
            continue
        if not p.value:                      # connectors and headers: footprint is enough
            return p
        if value.split() and value.split()[0].lower() == p.value.lower():
            return p
        if q is not None and _quantity(p.value) is not None and abs(q - _quantity(p.value)) <= 1e-6 * abs(q):
            return p
    return None


def jlc_package(footprint: str) -> str:
    """KiCad footprint name -> the package name JLCPCB and LCSC list ('0603', 'SOIC-8', ...)."""
    if m := re.match(r"^[RCL]_(\d{4})_\d{4}Metric", footprint):
        return m.group(1)
    if m := re.match(r"^Fuse_(\d{4})_", footprint):
        return m.group(1)
    if m := re.match(r"^(PinHeader|PinSocket)_1x(\d+)_P(2\.54|1\.27)mm", footprint):
        return f"{m.group(3)}mm 1x{int(m.group(2))} {'female header' if m.group(1) == 'PinSocket' else 'pin header'}"
    if m := re.match(r"^JST_XH_B(\d+)B-XH", footprint):
        return f"XH-{int(m.group(1))}A 2.5mm"
    if m := re.match(r"^Crystal_SMD_(\d{4})-4Pin", footprint):
        return f"SMD{m.group(1)}-4P"
    if m := re.match(r"^(?:[A-Z]*)QFN-(\d+)", footprint):
        return f"QFN-{m.group(1)}"
    if m := re.match(r"^D_(SMA|SMB|SMC|SOD-\d+)", footprint):
        return m.group(1)
    if m := re.match(r"^CP_Elec_(\d+(?:\.\d+)?x\d+(?:\.\d+)?)", footprint):
        return f"SMD,D{m.group(1)}mm"
    return re.split(r"_\d|_[A-Z]?\d+(\.\d+)?x", footprint)[0].split("_")[0]


def search_terms(footprint: str, value: str, mpn: str = "") -> str:
    """What to type into JLCPCB's or LCSC's part search for this part."""
    pkg = jlc_package(footprint)
    if re.match(r"^R_", footprint):
        return f"{value.split()[0].rstrip('Ω')} {pkg} resistor"
    if re.match(r"^C_|^CP_", footprint):
        return f"{value.split()[0]}F {pkg} capacitor".replace("FF", "F")
    if m := re.match(r"^JST_XH_B(\d+)B-XH", footprint):
        return f"XH-{int(m.group(1))}A"          # JLCPCB/LCSC list XH parts as XH-2A, XH-3A, ...
    if re.match(r"^(PinHeader|PinSocket)", footprint):
        return pkg
    if mpn and " " not in mpn:
        return mpn
    return f"{value} {pkg}".strip()


def search_links(terms: str) -> tuple[str, str]:
    """JLCPCB parts search and LCSC search URLs for `terms`."""
    q = quote_plus(terms)
    return (f"https://jlcpcb.com/parts/componentSearch?isSearch=true&searchTxt={q}",
            f"https://www.lcsc.com/search?q={q}")


def lcsc_link(lcsc: str) -> str:
    return f"https://www.lcsc.com/product-detail/{lcsc}.html"
