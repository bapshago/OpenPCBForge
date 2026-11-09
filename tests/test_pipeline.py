import shutil

import pytest

from pcbforge import env

pcbnew = pytest.importorskip("pcbnew", reason="KiCad's Python module is not importable")
# env.KICAD_CLI is a bare name when found on PATH, or a full path from $KICAD_CLI (usual on Windows).
if not shutil.which(env.KICAD_CLI):
    pytest.skip(f"kicad-cli not found ({env.KICAD_CLI}); add it to PATH or set KICAD_CLI", allow_module_level=True)

from pcbforge.pipeline import build  # noqa: E402
from pcbforge.route import freerouting_available  # noqa: E402


def test_blinky_end_to_end(tmp_path):
    r = build("designs/blinky.py", tmp_path)

    assert r["parts"] == 3
    assert r["nets"] == 3
    gerbers = {p.name.split("-", 1)[-1] for p in (tmp_path / "blinky" / "gerbers").iterdir()}
    for layer in ("F_Cu.gtl", "B_Cu.gbl", "Edge_Cuts.gm1"):
        assert layer in gerbers
    assert (tmp_path / "blinky" / "blinky-gerbers.zip").is_file()
    assert r["drc"]["errors"] == 0
    assert r["drc"]["warnings"] == 0, r["drc"]["violations"]

    if freerouting_available():
        assert r["routed"]
        assert r["drc"]["unconnected"] == 0
    else:
        assert r["drc"]["unconnected"] == 3  # VCC, LED_A, GND left for the router
