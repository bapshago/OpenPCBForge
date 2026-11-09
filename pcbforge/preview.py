"""Optional: render the exported Gerbers to SVG with gerbonara, independent of KiCad.

Useful as a sanity check that the fab files themselves (not just the KiCad
board) look right.
"""

from pathlib import Path

from gerbonara import LayerStack


def render_svg(gerber_dir: str | Path, out_svg: str | Path) -> Path:
    stack = LayerStack.open(str(gerber_dir))
    out_svg = Path(out_svg)
    out_svg.write_text(str(stack.to_pretty_svg()))
    return out_svg
