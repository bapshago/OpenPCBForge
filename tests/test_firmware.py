"""Host test for the signal module Arduino sketch (needs a C++ compiler, no hardware)."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKETCH = ROOT / "firmware" / "signal_module_928" / "signal_module_928.ino"
HOST = ROOT / "firmware" / "host_test"


@pytest.mark.skipif(not shutil.which("g++"), reason="g++ not installed")
def test_signal_module_sketch(tmp_path):
    exe = tmp_path / "host_test"
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Werror", f"-I{HOST}", f'-DSKETCH="{SKETCH}"',
         "-x", "c++", str(HOST / "test_signal_module.cpp"), "-o", str(exe)],
        check=True,
    )
    out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout
    assert "ALL OK" in out


def test_sketch_pins_match_the_board_design():
    import importlib.util
    import re

    spec = importlib.util.spec_from_file_location("sm928", ROOT / "designs" / "signal_module_928.py")
    design = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(design)

    src = SKETCH.read_text()
    table = src[src.index("Channel channels[16]"):src.index("};", src.index("Channel channels[16]"))]
    sketch_gpios = [int(g) for g in re.findall(r"\{(\d+),", table)]
    assert sketch_gpios == [design.CHANNELS[n][3] for n in range(1, 17)]

    # The board routes GPIO27 to the transceiver's D (TX) pin and GPIO25 to R (RX),
    # the reverse of the AngryPixieDash board, so don't copy pins between sketches.
    assert re.search(r"CAN_TX_PIN\s*=\s*27\b", src) and re.search(r"CAN_RX_PIN\s*=\s*25\b", src)
    assert re.search(r"DIMMER_PIN\s*=\s*39\b", src)
