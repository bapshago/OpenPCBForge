"""JLCPCB assembly files: a BOM grouped by part, and a CPL (placement) file.

LCSC part numbers come from each part's "LCSC" field in the design file.
Parts without one are still listed so JLCPCB's BOM tool can match them by
value and footprint (or flag them for you to choose).
"""

import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from . import parts

if TYPE_CHECKING:  # importing netlist loads SKiDL, which `pcbforge jlc` doesn't need
    from .netlist import Design

# JLCPCB's part models don't always use KiCad's zero orientation, so some packages show up
# turned in their placement preview. Each entry is (footprint-name regex, degrees added to
# the KiCad rotation); the first match wins. Values come from checking JLCPCB's preview, and
# a design can add or override entries with BOARD["jlc_rotations"].
JLC_ROTATIONS: list[tuple[str, float]] = [
    # Checked by hand in JLCPCB's preview on the 928 signal module's first order (Oct 2026).
    # JLCKicadTools' published table agrees on SOIC but says -90 for SOT-23 and 180 for CP_Elec_*;
    # the preview needed 180 for both SOT-23 parts and 0 for C10 (CP_Elec_8x10.5, C82011).
    (r"^SOIC-", 270),     # U2 SOIC-8, U3-U6 SOIC-16: one 90 deg turn clockwise
    (r"^SOT-23$", 180),   # D3 BAT54S (C7420333), D12 NUP2105L (C284104): two turns clockwise
    # ANC bench carrier, Oct 2026, the first order with JLCPCB fitting the through-hole parts:
    # their 1xN header and socket models lie horizontal at 0 deg, KiCad's vertical footprints
    # stand upright (J1/J2/J10/J11 sockets C53200741, J12/J13 C37208, J14 C5116483, JP1-JP4
    # C5360898). JST XH needed no turn, only the centre fix (body_centres below).
    (r"^Pin(Header|Socket)_1x\d+_P2\.54mm_Vertical$", 270),
]


_RKM = re.compile(r"^(\d+)([RrKkMm])(\d*)$")          # 4k7, 1k33, 240R, 2R2, 1M
_PLAIN_R = re.compile(r"^(\d+(?:\.\d+)?)\s*([kKmM]?)(?:\s*(?:ohms?|Ω|R))?$")   # 10k, 100, 4.7k, 10 kohm
_CAP_CODE = re.compile(r"^(\d+)([pnuµ])(\d*)$")         # 100n, 2u2, 4n7, 22p
_PLAIN_C = re.compile(r"^(\d+(?:\.\d+)?)\s*([pnuµ])F?$")  # 100nF, 4.7u


def jlc_value(ref: str, value: str) -> str:
    """Write a resistor or capacitor value the way JLCPCB's BOM check reads it: 4k7 -> 4.7kΩ,
    240R -> 240Ω, 100n -> 100nF, 2u2 -> 2.2uF. Only the first word changes ("47u 63V" ->
    "47uF 63V", "2.2k 1%" -> "2.2kΩ 1%"); other parts and values it doesn't recognise are kept."""
    first, sep, rest = value.strip().partition(" ")
    kind = ref.rstrip("0123456789").upper()
    out = None
    if kind in ("R", "RN", "RV"):
        if m := _RKM.match(first):
            whole, unit, frac = m.groups()
            prefix = {"r": "", "k": "k", "m": "M"}[unit.lower()]
            out = f"{whole}.{frac}{prefix}Ω" if frac else f"{whole}{prefix}Ω"
        elif m := _PLAIN_R.match(first):
            out = f"{m.group(1)}{m.group(2).replace('K', 'k').replace('m', 'M')}Ω"
    elif kind == "C":
        if m := _CAP_CODE.match(first):
            whole, unit, frac = m.groups()
            unit = "u" if unit == "µ" else unit
            out = f"{whole}.{frac}{unit}F" if frac else f"{whole}{unit}F"
        elif m := _PLAIN_C.match(first):
            out = f"{m.group(1)}{'u' if m.group(2) == 'µ' else m.group(2)}F"
    return (out + sep + rest) if out else value


# Footprints that are only copper on the board, with nothing for JLCPCB to place (solder jumpers).
NOT_ASSEMBLED = re.compile(r"^SolderJumper")


def bom_lines(design: "Design") -> list[dict]:
    """One line per distinct part. A part without an LCSC number of its own gets the catalogue's
    part for its footprint and value (pcbforge/parts.py); `source` says which: "design",
    "catalogue" or "" (still to choose in JLCPCB's BOM tool)."""
    groups = defaultdict(list)
    for p in design.parts:
        footprint = p.footprint.partition(":")[2]
        if NOT_ASSEMBLED.search(footprint):
            continue
        lcsc, mpn, source = p.fields.get("LCSC", ""), p.fields.get("MPN", ""), "design"
        if not lcsc:
            hit = parts.match(footprint, p.value)
            lcsc, mpn, source = (hit.lcsc, mpn or hit.mpn, "catalogue") if hit else ("", mpn, "")
        groups[(jlc_value(p.ref, p.value), footprint, lcsc, mpn, source)].append(p.ref)
    return [{"value": value, "refs": sorted(refs, key=_natural), "footprint": footprint, "lcsc": lcsc,
             "mpn": mpn, "source": source}
            for (value, footprint, lcsc, mpn, source), refs in sorted(groups.items(), key=lambda kv: _natural(kv[1][0]))]


def write_bom(design: "Design", path: str | Path) -> Path:
    """JLCPCB BOM. The Footprint column carries the package name JLCPCB lists ('0603', 'SOIC-8',
    'XH-3A 2.5mm'), which its matcher and search understand; KiCad footprint names find nothing."""
    path = Path(path)
    # utf-8-sig: the byte-order mark tells JLCPCB's uploader (and Excel) the file is UTF-8; without
    # it, "Ω" was read as GBK and showed up as "惟".
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "MPN"])
        for line in bom_lines(design):
            w.writerow([line["value"], ",".join(line["refs"]), parts.jlc_package(line["footprint"]),
                        line["lcsc"], line["mpn"]])
    return path


def write_parts_list(design: "Design", path: str | Path) -> tuple[Path, list[str]]:
    """Markdown list of every BOM line for ordering: the LCSC part (link) and where it came from,
    or, for parts still to choose, search terms with JLCPCB and LCSC search links. Returns the
    path and the designators still without a part."""
    lines = bom_lines(design)
    todo = [ref for line in lines if not line["lcsc"] for ref in line["refs"]]
    out = [f"# {design.name}: JLCPCB parts", "",
           f"{len(lines)} BOM lines; {sum(1 for x in lines if x['source'] == 'catalogue')} filled from the parts "
           f"catalogue (pcbforge/parts.py); {sum(1 for x in lines if not x['lcsc'])} still to choose.", "",
           "| Designators | Value | Package | LCSC part | Source | Search |", "|---|---|---|---|---|---|"]
    for x in lines:
        terms = parts.search_terms(x["footprint"], x["value"], x["mpn"])
        jlc, lcsc_search = parts.search_links(terms)
        part = f"[{x['lcsc']}]({parts.lcsc_link(x['lcsc'])})" if x["lcsc"] else "**to choose**"
        search = f"[JLCPCB]({jlc}) / [LCSC]({lcsc_search}): `{terms}`"
        out.append(f"| {', '.join(x['refs'])} | {x['value']} | {parts.jlc_package(x['footprint'])} | {part} | "
                   f"{x['source'] or '-'} | {search} |")
    out += ["", "Chose a part for a line marked **to choose**? Put its number on the part in the design file "
            "(`lcsc=`), and if it's a part you'll reuse, add it to `pcbforge/parts.py`."]
    path = Path(path)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path, todo


def body_centres(board_path: str | Path) -> dict[str, tuple[float, float]]:
    """Body centre (courtyard centre) of each footprint with through-hole pads, in the CPL frame
    (mm, y up). KiCad puts header and connector origins on pin 1, but JLCPCB places a part by its
    body centre, so through-hole parts sat shifted by half their length in JLCPCB's preview.
    SMD footprints already have their origin at the body centre."""
    import pcbnew   # here, not at the top: write_bom/write_cpl don't need KiCad

    board = pcbnew.LoadBoard(str(board_path))
    centres = {}
    for fp in board.GetFootprints():
        if not any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in fp.Pads()):
            continue
        box = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
        if box.GetWidth() == 0:
            box = fp.GetBoundingBox(False)
        c = box.GetCenter()
        centres[fp.GetReference()] = (pcbnew.ToMM(c.x), -pcbnew.ToMM(c.y))
    return centres


def write_cpl(pos_csv: str | Path, path: str | Path, rotations: list[tuple[str, float]] | None = None,
              ref_rotations: dict[str, float] | None = None,
              centres: dict[str, tuple[float, float]] | None = None) -> Path:
    """Convert kicad-cli's position CSV (Ref,Val,Package,PosX,PosY,Rot,Side) to JLCPCB's CPL columns,
    applying rotation corrections: `ref_rotations` per designator first (JLCPCB's models differ
    between part numbers in the same package), then design-specific `rotations`, then JLC_ROTATIONS.
    `centres` (see body_centres) replaces kicad-cli's footprint origin for the parts it lists."""
    centres = centres or {}
    table = [(re.compile(pattern), offset) for pattern, offset in (rotations or []) + JLC_ROTATIONS]
    ref_rotations = ref_rotations or {}
    path = Path(path)
    with open(pos_csv, newline="", encoding="utf-8") as src, path.open("w", newline="", encoding="utf-8") as dst:
        w = csv.writer(dst)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for row in csv.DictReader(src):
            if NOT_ASSEMBLED.search(row["Package"]):
                continue
            offset = ref_rotations.get(row["Ref"])
            if offset is None:
                offset = next((off for rx, off in table if rx.search(row["Package"])), 0)
            rot = (float(row["Rot"]) + offset) % 360
            x, y = centres.get(row["Ref"], (float(row["PosX"]), float(row["PosY"])))
            w.writerow([row["Ref"], f'{x:.4f}mm', f'{y:.4f}mm',
                        "Top" if row["Side"].lower() == "top" else "Bottom", f'{rot:g}'])
    return path


def _natural(ref: str):
    """Sort R2 before R10."""
    head = ref.rstrip("0123456789")
    tail = ref[len(head):]
    return head, int(tail) if tail else 0
