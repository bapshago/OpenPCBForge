"""Step 2: build a .kicad_pcb from a Design using KiCad's pcbnew Python API.

Placement is deliberately simple: explicit PLACEMENT from the design file
wins, everything else goes on a grid. Smarter placement is the obvious next
thing to improve (see README).
"""

from pathlib import Path

import pcbnew

from . import env
from .netlist import Design

DEFAULT_BOARD = {"width_mm": 50.0, "height_mm": 40.0, "margin_mm": 4.0, "grid_mm": 8.0}
MOUNTING_HOLE = "MountingHole:MountingHole_3.2mm_M3"


def _mm(x: float, y: float) -> "pcbnew.VECTOR2I":
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def _load_footprint(lib_id: str):
    lib, _, name = lib_id.partition(":")
    lib_path = env.footprint_lib_dir(lib)
    if not lib_path.is_dir():
        raise FileNotFoundError(f"Footprint library not found: {lib_path}")
    fp = pcbnew.FootprintLoad(str(lib_path), name)
    if fp is None:
        raise FileNotFoundError(f"Footprint {name!r} not found in {lib_path}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def _add_outline(board, cfg: dict):
    """A rectangle from width/height, or a closed polygon from cfg["outline"] = [(x, y), ...]."""
    w, h = cfg["width_mm"], cfg["height_mm"]
    points = cfg.get("outline") or [(0, 0), (w, 0), (w, h), (0, h)]
    for start, end in zip(points, points[1:] + points[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(_mm(*start))
        seg.SetEnd(_mm(*end))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.1))
        board.Add(seg)


def _add_mounting_holes(board, cfg: dict):
    """cfg["holes"] = [(x, y), ...]; each becomes an M3 mounting-hole footprint H1, H2, ..."""
    for i, (x, y) in enumerate(cfg.get("holes", []), start=1):
        fp = _load_footprint(cfg.get("hole_footprint", MOUNTING_HOLE))
        fp.SetReference(f"H{i}")
        fp.SetPosition(_mm(x, y))
        board.Add(fp)


def _grid_positions(cfg: dict):
    m, g = cfg["margin_mm"], cfg["grid_mm"]
    y = m
    while y <= cfg["height_mm"] - m:
        x = m
        while x <= cfg["width_mm"] - m:
            yield x, y
            x += g
        y += g


def _add_silk_text(board, cfg: dict):
    """cfg["silk"] = [(x, y, text), ...] or (x, y, text, size_mm, rotation_deg): labels on the top silkscreen."""
    for x, y, text, *rest in cfg.get("silk", []):
        size, rot = (list(rest) + [1.0, 0])[:2]
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetPosition(_mm(x, y))
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(_mm(size, size))
        t.SetTextThickness(pcbnew.FromMM(size * 0.15))
        t.SetTextAngleDegrees(rot)
        board.Add(t)


def build_board(design: Design, out_dir: str | Path) -> Path:
    cfg = {**DEFAULT_BOARD, **design.board}
    board = pcbnew.NewBoard(str(Path(out_dir) / f"{design.name}.kicad_pcb"))
    if cfg.get("clearance_mm"):  # copper clearance for every net (DRC and Freerouting); KiCad's default is 0.2 mm
        board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().SetClearance(pcbnew.FromMM(cfg["clearance_mm"]))
    _add_outline(board, cfg)
    _add_mounting_holes(board, cfg)
    _add_silk_text(board, cfg)

    nets = {}
    for name in design.nets:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        nets[name] = net

    free_spots = _grid_positions(cfg)
    for part in design.parts:
        fp = _load_footprint(part.footprint)
        fp.SetReference(part.ref)
        fp.SetValue(part.value)
        if cfg.get("hide_silk_refs"):  # dense boards: refs stay on the Fab layer, off the silkscreen
            fp.Reference().SetVisible(False)
        for key, value in part.fields.items():
            fp.SetField(key, str(value))
            fp.GetFieldByName(key).SetVisible(False)  # data for BOMs, not silkscreen
        if part.ref in design.placement:
            x, y, rot = (list(design.placement[part.ref]) + [0])[:3]
        else:
            try:
                x, y = next(free_spots)
            except StopIteration:
                raise ValueError("Board too small for grid placement; enlarge BOARD or add PLACEMENT") from None
            rot = 0
        fp.SetPosition(_mm(x, y))
        fp.SetOrientationDegrees(rot)
        board.Add(fp)
        for pad in fp.Pads():
            net_name = part.pads.get(pad.GetNumber())
            if net_name:
                pad.SetNet(nets[net_name])

    path = Path(out_dir) / f"{design.name}.kicad_pcb"
    pcbnew.SaveBoard(str(path), board)
    _write_fp_lib_table(design, cfg, Path(out_dir))
    return path


def _write_fp_lib_table(design: Design, cfg: dict, out_dir: Path):
    """Project-local footprint table so DRC (and the KiCad GUI) can find the libraries."""
    lib_ids = [p.footprint for p in design.parts]
    if cfg.get("holes"):
        lib_ids.append(cfg.get("hole_footprint", MOUNTING_HOLE))
    libs = sorted({lib_id.partition(":")[0] for lib_id in lib_ids})
    # Forward slashes: KiCad treats backslashes in these strings as escapes, which breaks Windows paths.
    rows = "\n".join(
        f'  (lib (name "{lib}")(type "KiCad")(uri "{env.footprint_lib_dir(lib).as_posix()}")(options "")(descr ""))'
        for lib in libs
    )
    (out_dir / "fp-lib-table").write_text(f"(fp_lib_table\n  (version 7)\n{rows}\n)\n")
