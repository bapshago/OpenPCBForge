"""Step 5: fabrication outputs (Gerbers, drill, pick-and-place) via kicad-cli."""

import shutil
import subprocess
from pathlib import Path

from . import env

# The layers a 2-layer board fab actually needs.
FAB_LAYERS = [
    "F.Cu", "B.Cu", "F.Mask", "B.Mask", "F.Paste", "B.Paste",
    "F.Silkscreen", "B.Silkscreen", "Edge.Cuts",
]


def _cli(*args):
    subprocess.run([env.KICAD_CLI, *map(str, args)], check=True, capture_output=True)


def export_fab(board_path: str | Path, out_dir: str | Path) -> dict:
    board_path, out_dir = Path(board_path), Path(out_dir)
    gerber_dir = out_dir / "gerbers"
    gerber_dir.mkdir(parents=True, exist_ok=True)

    _cli("pcb", "export", "gerbers", "-l", ",".join(FAB_LAYERS), "-o", f"{gerber_dir}/", board_path)
    _cli("pcb", "export", "drill", "-o", f"{gerber_dir}/", board_path)
    pos = out_dir / f"{board_path.stem}-pos.csv"
    _cli("pcb", "export", "pos", "--format", "csv", "--units", "mm", "-o", pos, board_path)

    zip_path = shutil.make_archive(str(out_dir / f"{board_path.stem}-gerbers"), "zip", gerber_dir)
    return {"gerber_dir": str(gerber_dir), "zip": zip_path, "pos": str(pos)}
