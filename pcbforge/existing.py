"""JLCPCB BOM + CPL (and fresh Gerbers) for a KiCad board that wasn't made with pcbforge.

Reads the .kicad_pcb directly, so it works for boards drawn by hand or imported from
other tools (Altium, PADS, Eagle). Choices that a design file would normally make
are options here:

- which field holds the real value (imported boards often keep it in a custom field,
  e.g. ALTIUM_VALUE, with a placeholder in Value);
- which values mean "not fitted" (na, DNP, ...);
- which parts JLCPCB should place: by default every part whose pads are all SMD;
  parts with both SMD and through-hole pads (dual TO-220/DPAK footprints) are left
  out and reported, and can be added with `include`.

Each placed part is positioned at the centre of its SMD pads, not its footprint
origin: imported footprints don't always put the origin at the part centre (a dual
TO-220/DPAK footprint keeps it at the TO-220 position).
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

import pcbnew

from .export import export_fab
from .jlc import JLC_ROTATIONS, _natural, jlc_value

DNP_VALUES = ("na", "n/a", "dnp", "dnf", "nc", "nf", "nofit", "no fit", "not fitted")
LCSC_FIELDS = ("LCSC", "LCSC Part #", "LCSC Part", "JLCPCB Part #", "JLC")
MPN_FIELDS = ("MPN", "Manufacturer Part Number", "Part Number", "PN")


def jlc_from_board(board_path: str | Path, out_dir: str | Path, *, value_field: str | None = None,
                   dnp_values=DNP_VALUES, include=(), exclude=(), rotations=None, ref_rotations=None,
                   offset: tuple[float, float] = (0.0, 0.0), lcsc: dict[str, str] | None = None,
                   moves: dict[str, tuple[float, float]] | None = None, values: dict[str, str] | None = None,
                   normalize_values: bool = True, gerbers: bool = True) -> dict:
    """`offset` (mm) is added to every CPL coordinate, to match Gerbers made elsewhere whose origin
    differs from the KiCad file's (e.g. a board converted from PADS ordered with its PADS Gerbers).
    `lcsc` maps designators to LCSC numbers, overriding the board's fields (for parts matched by
    hand in JLCPCB's BOM tool). `normalize_values` writes R and C values the way JLCPCB reads them.
    `moves` shifts single parts (mm, CPL frame: +x right, +y up), for footprints whose SMD pads
    don't centre on the real part, e.g. a dual TO-220/DPAK footprint drawn with a long tab pad.
    `values` replaces single parts' values (a substitute part, or a value the board leaves blank)."""
    lcsc = lcsc or {}
    moves = moves or {}
    values = values or {}
    board_path, out_dir = Path(board_path).resolve(), Path(out_dir)
    if not board_path.is_file():
        raise FileNotFoundError(f"No board file at {board_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    board = pcbnew.LoadBoard(str(board_path))
    if board is None:
        raise ValueError(f"KiCad could not open {board_path} (is it a KiCad 6+ .kicad_pcb?)")
    include, exclude = set(include), set(exclude)
    table = [(re.compile(p), off) for p, off in (rotations or []) + JLC_ROTATIONS]
    ref_rotations = ref_rotations or {}
    dnp = {v.lower() for v in dnp_values}

    placed, report = [], {"dnp": [], "through_hole": [], "mixed_smd_tht": [], "no_value": [], "bottom": []}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        fields = {f.GetName(): f.GetText().strip() for f in fp.GetFields()}
        value = values.get(ref) or (fields.get(value_field) if value_field else "") or fp.GetValue().strip()
        pads = list(fp.Pads())
        smd = [p for p in pads if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
        tht = [p for p in pads if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]

        if ref in exclude:
            continue
        if value.lower() in dnp or fp.IsDNP():
            report["dnp"].append(ref)
            continue
        if ref not in include:
            if not smd:
                report["through_hole"].append(ref)
                continue
            if tht:
                report["mixed_smd_tht"].append(ref)
                continue
        if not smd:
            raise ValueError(f"{ref} has no SMD pads to place")
        if not value or "?" in value:
            report["no_value"].append(ref)

        xs, ys = [], []
        for p in smd:
            r = p.GetBoundingBox()
            xs += [r.GetLeft(), r.GetRight()]
            ys += [r.GetTop(), r.GetBottom()]
        footprint = fp.GetFPID().GetLibItemName().wx_str()
        rot_offset = ref_rotations.get(ref)
        if rot_offset is None:
            rot_offset = next((off for rx, off in table if rx.search(footprint)), 0)
        side = "Bottom" if fp.IsFlipped() else "Top"
        if fp.IsFlipped():
            report["bottom"].append(ref)
        placed.append({
            "ref": ref, "value": jlc_value(ref, value) if normalize_values else value, "footprint": footprint,
            "lcsc": lcsc.get(ref) or next((fields[k] for k in LCSC_FIELDS if fields.get(k)), ""),
            "mpn": next((fields[k] for k in MPN_FIELDS if fields.get(k)), ""),
            # same coordinate frame as kicad-cli's position file and Gerbers: mm, y up
            "x": pcbnew.ToMM((min(xs) + max(xs)) / 2) + offset[0] + moves.get(ref, (0, 0))[0],
            "y": -pcbnew.ToMM((min(ys) + max(ys)) / 2) + offset[1] + moves.get(ref, (0, 0))[1],
            "rot": (fp.GetOrientationDegrees() + rot_offset) % 360, "side": side,
        })

    stem = board_path.stem
    bom, cpl = out_dir / f"{stem}-bom-jlc.csv", out_dir / f"{stem}-cpl-jlc.csv"
    groups = defaultdict(list)
    for p in placed:
        groups[(p["value"], p["footprint"], p["lcsc"], p["mpn"])].append(p["ref"])
    with bom.open("w", newline="", encoding="utf-8-sig") as f:   # BOM marks it UTF-8 for JLCPCB (Ω)
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "MPN"])
        for (value, footprint, lcsc, mpn), refs in sorted(groups.items(), key=lambda kv: _natural(kv[1][0])):
            w.writerow([value, ",".join(sorted(refs, key=_natural)), footprint, lcsc, mpn])
    with cpl.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for p in sorted(placed, key=lambda p: _natural(p["ref"])):
            w.writerow([p["ref"], f'{p["x"]:.4f}mm', f'{p["y"]:.4f}mm', p["side"], f'{p["rot"]:g}'])

    result = {"board": str(board_path), "placed": len(placed), "bom": str(bom), "cpl": str(cpl),
              "report": {k: sorted(v, key=_natural) for k, v in report.items()}}
    if gerbers:
        result["fab"] = export_fab(board_path, out_dir)
    return result
