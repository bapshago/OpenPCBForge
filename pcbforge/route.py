"""Step 3: autoroute with Freerouting via the Specctra DSN/SES round-trip."""

import subprocess
from pathlib import Path

import pcbnew

from . import env


def freerouting_available() -> bool:
    return Path(env.FREEROUTING_JAR).is_file()


def autoroute(board_path: str | Path, passes: int = 20, timeout_s: int = 1800) -> Path:
    board_path = Path(board_path)
    if not freerouting_available():
        raise FileNotFoundError(
            f"Freerouting jar not found at {env.FREEROUTING_JAR}. "
            "Run scripts/get_freerouting.sh or set FREEROUTING_JAR."
        )
    dsn = board_path.with_suffix(".dsn")
    ses = board_path.with_suffix(".ses")

    board = pcbnew.LoadBoard(str(board_path))
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise RuntimeError("Specctra DSN export failed")

    proc = subprocess.run(
        [env.JAVA, "-jar", env.FREEROUTING_JAR, "-de", str(dsn), "-do", str(ses),
         "-mp", str(passes), "--gui.enabled=false"],
        capture_output=True, text=True, timeout=timeout_s,
    )
    if proc.returncode != 0 or not ses.is_file():
        raise RuntimeError(f"Freerouting failed (exit {proc.returncode}):\n{proc.stderr[-2000:]}")

    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise RuntimeError("Specctra SES import failed")
    pcbnew.SaveBoard(str(board_path), board)
    return board_path
