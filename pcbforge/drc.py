"""Step 4: design rule check through kicad-cli, summarized for humans and Claude."""

import json
import subprocess
from pathlib import Path

from . import env


def run_drc(board_path: str | Path) -> dict:
    board_path = Path(board_path)
    report = board_path.with_name(f"{board_path.stem}-drc.json")
    subprocess.run(
        [env.KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-all",
         "-o", str(report), str(board_path)],
        check=True, capture_output=True,
    )
    data = json.loads(report.read_text())

    def brief(v):
        return {
            "type": v.get("type"),
            "severity": v.get("severity"),
            "description": v.get("description"),
            "items": [i.get("description") for i in v.get("items", [])],
        }

    violations = [brief(v) for v in data.get("violations", [])]
    unconnected = [brief(v) for v in data.get("unconnected_items", [])]
    errors = [v for v in violations if v["severity"] == "error"]
    return {
        "report": str(report),
        "errors": len(errors),
        "warnings": len(violations) - len(errors),
        "unconnected": len(unconnected),
        "violations": violations,
        "unconnected_items": unconnected,
    }
