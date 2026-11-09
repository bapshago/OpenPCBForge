"""Run the whole flow: design file -> board -> route -> DRC -> fab outputs."""

import shutil
from pathlib import Path

from .board import DEFAULT_BOARD, build_board
from .drc import run_drc
from .export import export_fab
from .jlc import body_centres, write_bom, write_cpl, write_parts_list
from .jlcapi import JlcApi, JlcApiError
from .partcheck import check_parts, write_check_report
from .netlist import run_design
from .pour import add_ground_pour
from .preview import render_svg
from .route import autoroute, freerouting_available


def build(design_path: str | Path, out_root: str | Path = "build", route: bool = True) -> dict:
    design_path = Path(design_path)
    out_dir = Path(out_root) / design_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    design = run_design(design_path, out_dir)
    board_path = build_board(design, out_dir)

    routed = False
    if route and freerouting_available():
        _route_best_of(design, board_path, out_dir)
        routed = True
    if design.board.get("ground_pour"):
        add_ground_pour(board_path, {**DEFAULT_BOARD, **design.board})

    result = {
        "design": design.name,
        "parts": len(design.parts),
        "nets": len(design.nets),
        "board": str(board_path),
        "netlist": str(design.netlist_path),
        "routed": routed,
        "drc": run_drc(board_path),
        "fab": export_fab(board_path, out_dir),
    }
    result["fab"]["jlc_bom"] = str(write_bom(design, out_dir / f"{design.name}-bom-jlc.csv"))
    parts_md, todo = write_parts_list(design, out_dir / f"{design.name}-jlc-parts.md")
    result["fab"]["jlc_parts"] = str(parts_md)
    result["jlc_parts_to_choose"] = todo
    result["fab"]["jlc_cpl"] = str(write_cpl(result["fab"]["pos"], out_dir / f"{design.name}-cpl-jlc.csv",
                                             design.board.get("jlc_rotations"),
                                             design.board.get("jlc_ref_rotations"),
                                             body_centres(board_path)))
    result["preview_svg"] = str(render_svg(result["fab"]["gerber_dir"], out_dir / f"{design.name}-preview.svg"))
    result["jlc_check"] = _jlc_check(design, out_dir)
    if route and not routed:
        result["note"] = "Freerouting not installed; board is placed but unrouted (see scripts/get_freerouting.sh)."
    return result


def _jlc_check(design, out_dir: Path) -> dict:
    """Check the LCSC numbers against JLCPCB's records when JLC_* API credentials are set.
    Never fails the build: an API problem is reported in the result instead."""
    api = JlcApi.from_env()
    if api is None:
        return {"ran": False, "reason": "JLC_APP_ID / JLC_ACCESS_KEY / JLC_SECRET_KEY not set"}
    boards = design.board.get("order_quantity", 5)
    try:
        rows = check_parts(design, api, boards)
    except JlcApiError as e:
        return {"ran": False, "reason": str(e)}
    report = write_check_report(design, rows, out_dir / f"{design.name}-jlc-check.md", boards)
    return {"ran": True, "report": str(report), "boards": boards,
            "errors": [{"refs": r["refs"], "lcsc": r["lcsc"], "problems": r["problems"]} for r in rows if r["level"] == "error"],
            "warnings": [{"refs": r["refs"], "lcsc": r["lcsc"], "problems": r["problems"]} for r in rows if r["level"] == "warning"]}


def _route_best_of(design, board_path: Path, out_dir: Path) -> None:
    """Freerouting isn't deterministic: on a dense board one run can leave a net or two
    unrouted where the next finishes. Try up to BOARD["route_attempts"] times from an
    unrouted board and keep the run with the fewest unconnected items."""
    attempts = design.board.get("route_attempts", 1)
    best = out_dir / f"{design.name}-best-route.kicad_pcb"
    best_unconnected = None
    for attempt in range(attempts):
        if attempt:
            build_board(design, out_dir)  # start again from the placed, unrouted board
        autoroute(board_path, passes=design.board.get("route_passes", 20))
        if attempts == 1:
            return
        unconnected = run_drc(board_path)["unconnected"]
        if best_unconnected is None or unconnected < best_unconnected:
            best_unconnected = unconnected
            shutil.copyfile(board_path, best)
        if unconnected == 0:
            break
    shutil.copyfile(best, board_path)
    best.unlink()
