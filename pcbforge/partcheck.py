"""Check a design's LCSC part numbers against JLCPCB's own records (pcbforge/jlcapi.py).

For every BOM line with an LCSC number: does JLCPCB know the part, does its package match
the footprint (C723496 was a 100k in 01005 sitting on 0402 pads), does its value match, is
there stock for the boards being ordered, and is it a basic or an extended part (each
extended part type adds a setup fee at JLCPCB). Writes `<name>-jlc-check.md`.
"""

import csv
import re
from pathlib import Path
from types import SimpleNamespace

from . import parts
from .jlc import bom_lines

SIZES = ("01005", "0201", "0402", "0603", "0805", "1206", "1210", "1812", "2010", "2512")
_SIZE = re.compile(r"(?<!\d)(" + "|".join(SIZES) + r")(?!\d)")


def _size(text: str) -> str | None:
    m = _SIZE.search(text or "")
    return m.group(1) if m else None


def _pins(text: str) -> int | None:
    """Pin count from a package name: the number ending its name part ("SOT-23-5" -> 5,
    "SOIC-8_3.9x4.9mm" -> 8, "LFCSP-40(6x6)" -> 40)."""
    if re.match(r"^SOT-23(?:[_(]|$)", text or ""):   # plain SOT-23 is the 3-pin package
        return 3
    found = re.findall(r"-(\d+)(?=[_(]|$)", text or "")
    return int(found[-1]) if found else None


def _detail_value(detail: dict) -> float | None:
    """Resistance or capacitance from JLCPCB's parameters or description, as a number."""
    texts = [p.get("parameterValue", "") for p in detail.get("parameters") or []
             if re.search(r"resist|capacit", p.get("parameterName", ""), re.I)]
    texts.append(detail.get("description") or "")
    for t in texts:
        for tok in re.findall(r"\d+(?:\.\d+)?\s*[pnuµmkM]?(?:Ω|F|ohm)", t):
            q = parts._quantity(tok.replace(" ", "").replace("ohm", "Ω"))
            if q is not None:
                return q
    return None


def _unit_price(detail: dict, qty: int):
    for r in detail.get("priceRanges") or []:
        lo, hi = r.get("startQuantity") or 0, r.get("endQuantity") or 10**12
        if lo <= qty <= hi or (hi in (0, -1) and qty >= lo):
            return r.get("unitPrice")
    return None


def check_parts(design, api, boards: int = 5) -> list[dict]:
    """One row per BOM line: refs, lcsc, level ("ok", "warning", "error"), problems, and what
    JLCPCB reports (package, mpn, stock, libraryType, unit price at the order quantity)."""
    lines = bom_lines(design)
    details = api.component_details([x["lcsc"] for x in lines if x["lcsc"]])
    rows = []
    for x in lines:
        row = {"refs": x["refs"], "value": x["value"], "footprint": x["footprint"], "lcsc": x["lcsc"],
               "problems": [], "level": "ok"}
        rows.append(row)
        if not x["lcsc"]:
            row.update(level="warning", problems=["no LCSC number: choose one in JLCPCB's BOM tool"])
            continue
        d = details.get(x["lcsc"].upper())
        if d is None:
            row.update(level="error", problems=[f"JLCPCB has no part {x['lcsc']}"])
            continue
        need = len(x["refs"]) * boards
        row.update(package=d.get("componentSpecification"), mpn=d.get("componentModel"),
                   brand=d.get("componentBrandEn"), stock=d.get("stockCount"),
                   library=d.get("libraryType"), unit_price=_unit_price(d, need), need=need)
        errors, warnings = [], []
        # Package against footprint: chip sizes must match exactly; pin counts must match
        fp_size, part_size = _size(parts.jlc_package(x["footprint"])), _size(d.get("componentSpecification"))
        if fp_size and part_size and fp_size != part_size:
            errors.append(f"package {part_size} doesn't fit the {fp_size} footprint")
        fp_pins, part_pins = _pins(x["footprint"]), _pins(d.get("componentSpecification"))
        if not fp_size and fp_pins and part_pins and fp_pins != part_pins:
            errors.append(f"package {d.get('componentSpecification')} has {part_pins} pins, footprint {fp_pins}")
        # Value (resistors and capacitors)
        if re.match(r"^[RC]_|^CP_", x["footprint"]) or re.match(r"^[RC]\d", x["refs"][0]):
            want, have = parts._quantity(x["value"].split()[0]), _detail_value(d)
            if want and have and abs(want - have) > 1e-6 * want:
                errors.append(f"value {x['value']} but JLCPCB's part is {d.get('description') or have}")
        # Maker part number: JLCPCB places its own part (the LCSC number decides), so a different
        # maker's equivalent is only a note once package and value have been checked above.
        mpn = (x["mpn"] or "").upper().replace(" ", "")
        jlc_mpn = (d.get("componentModel") or "").upper().replace(" ", "")
        if mpn and jlc_mpn and " " not in (x["mpn"] or "") and not (mpn.startswith(jlc_mpn[:6]) or jlc_mpn.startswith(mpn[:6])):
            row["notes"] = [f"JLCPCB places {d.get('componentModel')} ({d.get('componentBrandEn') or 'maker not given'}); "
                            f"the design names {x['mpn']}"]
        # Stock and assembly
        stock = d.get("stockCount")
        if stock is not None and stock < need:
            errors.append(f"only {stock} in stock, {need} needed for {boards} boards")
        elif stock is not None and stock < 2 * need:
            warnings.append(f"low stock: {stock} for {need} needed")
        # assemblyComponentFlag is not "JLCPCB can assemble it": it is false for basic parts such as
        # C25804 (live check, Nov 5 2026), so it isn't used.
        if errors or warnings:
            row.update(level="error" if errors else "warning", problems=errors + warnings)
    return rows


def load_parts(path, out_dir=None):
    """The parts to check, from a design file (.py, needs SKiDL 3), a JLCPCB BOM (.csv, as
    pcbforge writes it or as JLCPCB's BOM tool exports it) or a KiCad board (.kicad_pcb).
    Returns an object with .name, .parts (ref, value, footprint "lib:name", fields) and .board."""
    path = Path(path)
    if path.suffix == ".py":
        from .netlist import run_design
        out = Path(out_dir or "build") / path.stem
        out.mkdir(parents=True, exist_ok=True)
        return run_design(path, out)
    name = re.sub(r"-bom-(jlc|as-ordered).*$", "", path.stem)
    part_list = []
    if path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
                lcsc = next((row[k] for k in ("LCSC Part #", "JLCPCB Part #", "LCSC", "LCSC Part") if row.get(k)), "")
                footprint = row.get("Footprint", "")
                for ref in re.split(r"[,\s]+", row.get("Designator", "")):
                    if ref:
                        part_list.append(SimpleNamespace(
                            ref=ref, value=row.get("Comment") or row.get("Value", ""),
                            footprint=footprint if ":" in footprint else f"bom:{footprint}",
                            fields={k: v for k, v in (("LCSC", lcsc), ("MPN", row.get("MPN", ""))) if v}))
    elif path.suffix == ".kicad_pcb":
        import pcbnew
        board = pcbnew.LoadBoard(str(path))
        for fp in board.GetFootprints():
            fields = {f.GetName(): f.GetText().strip() for f in fp.GetFields()}
            if not any(p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD for p in fp.Pads()) and not fields.get("LCSC"):
                continue      # hand-soldered through-hole parts without an LCSC number
            fpid = fp.GetFPID()
            part_list.append(SimpleNamespace(
                ref=fp.GetReference(), value=fp.GetValue(),
                footprint=f"{fpid.GetLibNickname().wx_str()}:{fpid.GetLibItemName().wx_str()}",
                fields={k: fields[k] for k in ("LCSC", "MPN") if fields.get(k)}))
    else:
        raise ValueError(f"{path}: give a design (.py), a JLCPCB BOM (.csv) or a board (.kicad_pcb)")
    return SimpleNamespace(name=name, parts=part_list, board={})


def write_check_report(design, rows: list[dict], path, boards: int) -> Path:
    errors = [r for r in rows if r["level"] == "error"]
    warns = [r for r in rows if r["level"] == "warning"]
    extended = [r for r in rows if r.get("library") and "base" not in str(r["library"]).lower()
                and "basic" not in str(r["library"]).lower()]
    out = [f"# {design.name}: JLCPCB part check ({boards} boards)", "",
           f"{len(rows)} BOM lines: {len(errors)} errors, {len(warns)} warnings, "
           f"{len(extended)} extended part types (each adds JLCPCB's extended-part setup fee).", "",
           "| Designators | Value | LCSC | JLCPCB package | Stock | Type | Unit price | Result |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        result = "ok" if r["level"] == "ok" else f"**{r['level']}**: " + "; ".join(r["problems"])
        if r.get("notes"):
            result += " (" + "; ".join(r["notes"]) + ")"
        lcsc = f"[{r['lcsc']}]({parts.lcsc_link(r['lcsc'])})" if r["lcsc"] else "-"
        out.append(f"| {', '.join(r['refs'])} | {r['value']} | {lcsc} | {r.get('package', '-')} | "
                   f"{r.get('stock', '-')} | {r.get('library', '-')} | {r.get('unit_price', '-')} | {result} |")
    path = Path(path)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path
