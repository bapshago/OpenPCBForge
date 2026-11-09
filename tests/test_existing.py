"""pcbforge jlc on an existing board: checked against the heater controller, whose
CPL and BOM were made by the design pipeline and confirmed in JLCPCB's preview."""

import csv
import shutil

import pytest

pytest.importorskip("pcbnew")
from pcbforge.existing import jlc_from_board  # noqa: E402

FAB = "fab/heater_controller_928_rev_a"


def _rows(path):
    return {r["Designator"]: r for r in csv.DictReader(open(path))}


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    out = tmp_path_factory.mktemp("jlc")
    shutil.copy(f"{FAB}/heater_controller_928.kicad_pcb", out)
    shutil.copy(f"{FAB}/fp-lib-table", out)
    return jlc_from_board(out / "heater_controller_928.kicad_pcb", out, ref_rotations={"U7": 270},
                          gerbers=False)


def test_places_the_same_parts_at_the_same_spots(result):
    ours, ref = _rows(result["cpl"]), _rows(f"{FAB}/heater_controller_928-cpl-jlc.csv")
    smd = {k: v for k, v in ref.items() if not k.startswith("J")}   # pipeline CPL also lists THT parts
    assert set(ours) == set(smd)
    for k, v in smd.items():
        for col in ("Mid X", "Mid Y"):
            assert abs(float(ours[k][col][:-2]) - float(v[col][:-2])) < 0.15, (k, col)
        assert ours[k]["Rotation"] == v["Rotation"], k
        assert ours[k]["Layer"] == v["Layer"]


def test_reports_through_hole_parts(result):
    assert "J10" in result["report"]["through_hole"] and "JP1" in result["report"]["through_hole"]


def test_offset_shifts_every_coordinate(tmp_path):
    shutil.copy(f"{FAB}/heater_controller_928.kicad_pcb", tmp_path)
    r = jlc_from_board(tmp_path / "heater_controller_928.kicad_pcb", tmp_path, offset=(10, -5), gerbers=False)
    base = _rows(f"{FAB}/heater_controller_928-cpl-jlc.csv")
    row = _rows(r["cpl"])["C12"]
    assert abs(float(row["Mid X"][:-2]) - float(base["C12"]["Mid X"][:-2]) - 10) < 0.15
    assert abs(float(row["Mid Y"][:-2]) - float(base["C12"]["Mid Y"][:-2]) + 5) < 0.15


def test_move_shifts_one_part(tmp_path):
    shutil.copy(f"{FAB}/heater_controller_928.kicad_pcb", tmp_path)
    r = jlc_from_board(tmp_path / "heater_controller_928.kicad_pcb", tmp_path, moves={"C12": (1.5, -2.0)},
                       gerbers=False)
    base, rows = _rows(f"{FAB}/heater_controller_928-cpl-jlc.csv"), _rows(r["cpl"])
    assert abs(float(rows["C12"]["Mid X"][:-2]) - float(base["C12"]["Mid X"][:-2]) - 1.5) < 0.15
    assert abs(float(rows["C12"]["Mid Y"][:-2]) - float(base["C12"]["Mid Y"][:-2]) + 2.0) < 0.15
    assert abs(float(rows["C13"]["Mid X"][:-2]) - float(base["C13"]["Mid X"][:-2])) < 0.15   # others unmoved


def test_cli_rotate_fp_turns_every_part_with_that_footprint(tmp_path):
    from pcbforge.cli import main
    shutil.copy(f"{FAB}/heater_controller_928.kicad_pcb", tmp_path)
    assert main(["jlc", str(tmp_path / "heater_controller_928.kicad_pcb"), "--out", str(tmp_path / "o"),
                 "--rotate-fp", "C_0603_1608Metric=270", "--rotate", "C13=90", "--no-gerbers"]) == 0
    rows = _rows(tmp_path / "o" / "heater_controller_928" / "heater_controller_928-cpl-jlc.csv")
    base = _rows(f"{FAB}/heater_controller_928-cpl-jlc.csv")
    assert float(rows["C12"]["Rotation"]) == (float(base["C12"]["Rotation"]) + 270) % 360
    assert float(rows["C13"]["Rotation"]) == (float(base["C13"]["Rotation"]) + 90) % 360    # per-part wins
    assert rows["R12"]["Rotation"] == base["R12"]["Rotation"]                                 # other footprints


def test_set_value_replaces_the_bom_comment(tmp_path):
    shutil.copy(f"{FAB}/heater_controller_928.kicad_pcb", tmp_path)
    r = jlc_from_board(tmp_path / "heater_controller_928.kicad_pcb", tmp_path, values={"U7": "SN74AHCT1G125"},
                       gerbers=False)
    rows = list(csv.reader(open(r["bom"], encoding="utf-8-sig")))
    assert any(row[0] == "SN74AHCT1G125" and row[1] == "U7" for row in rows)
