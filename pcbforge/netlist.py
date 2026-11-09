"""Step 1: run a SKiDL design file and turn it into a list of parts + nets.

A design file is plain Python that defines:

    def build():            # required: create parts and nets with SKiDL
        ...
    BOARD = {"width_mm": 40, "height_mm": 30}   # optional
    PLACEMENT = {"J1": (5, 15, 90)}             # optional: ref -> (x_mm, y_mm, rot_deg)
"""

import builtins
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

from . import env  # sets KiCad library paths before skidl loads
import skidl

# Match the KiCad major version you have installed (KICAD9 / KICAD10 / ...).
skidl.set_default_tool(getattr(skidl, env.SKIDL_TOOL))


@dataclass
class PartSpec:
    ref: str
    value: str
    footprint: str  # "Library:Footprint"
    pads: dict[str, str] = field(default_factory=dict)  # pad number -> net name
    fields: dict[str, str] = field(default_factory=dict)  # extra fields, e.g. {"LCSC": "C12084", "MPN": ...}


@dataclass
class Design:
    name: str
    parts: list[PartSpec]
    nets: list[str]
    board: dict
    placement: dict
    netlist_path: Path | None = None


def load_design_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "build"):
        raise ValueError(f"{path} must define a build() function")
    return module


def run_design(path: str | Path, out_dir: str | Path) -> Design:
    path, out_dir = Path(path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    skidl.reset()
    module = load_design_module(path)
    module.build()

    circuit = builtins.default_circuit  # SKiDL keeps its default circuit in builtins
    circuit.ERC()
    netlist_path = out_dir / f"{path.stem}.net"
    # Absolute source paths: SKiDL's default makes them relative to the running script's folder,
    # which raises on Windows when that folder is on another drive (e.g. pytest on a network share).
    circuit.generate_netlist(file_=str(netlist_path), track_abs_path=True)

    parts = []
    for part in circuit.parts:
        if not part.footprint:
            raise ValueError(f"{part.ref} has no footprint; set footprint='Lib:Name' on the Part")
        pads = {str(pin.num): pin.net.name for pin in part.pins if pin.net is not None and pin.is_connected()}
        fields = {k: str(v) for k, v in part.fields.items() if v not in (None, "")}
        parts.append(PartSpec(part.ref, str(part.value), part.footprint, pads, fields))

    nets = sorted({n for p in parts for n in p.pads.values()})
    return Design(
        name=path.stem,
        parts=parts,
        nets=nets,
        board=getattr(module, "BOARD", {}),
        placement=getattr(module, "PLACEMENT", {}),
        netlist_path=netlist_path,
    )
