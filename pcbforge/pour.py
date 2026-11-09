"""Step 3b (optional): ground pour on both copper layers, after routing.

Enabled by BOARD["ground_pour"] = "GND" (the net name). Rectangles listed in
BOARD["pour_keepouts"] = [(x1, y1, x2, y2), ...] stay free of poured copper,
for example under a Wi-Fi antenna.
"""

from pathlib import Path

import pcbnew


def _mm(x: float, y: float) -> "pcbnew.VECTOR2I":
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def _polygon(points) -> "pcbnew.SHAPE_LINE_CHAIN":
    chain = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in points:
        chain.Append(_mm(x, y))
    chain.SetClosed(True)
    return chain


def add_ground_pour(board_path: str | Path, cfg: dict) -> Path:
    board_path = Path(board_path)
    net_name = cfg["ground_pour"]
    board = pcbnew.LoadBoard(str(board_path))
    net = board.FindNet(net_name)
    if net is None:
        raise ValueError(f"ground_pour net {net_name!r} is not on the board")

    w, h = cfg["width_mm"], cfg["height_mm"]
    outline = cfg.get("outline") or [(0, 0), (w, 0), (w, h), (0, h)]
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]

    for layer in layers:
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(net)
        zone.Outline().AddOutline(_polygon(outline))
        zone.SetLocalClearance(pcbnew.FromMM(0.3))
        zone.SetMinThickness(pcbnew.FromMM(0.25))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)  # solid: thermal spokes get starved on dense boards
        zone.SetThermalReliefGap(pcbnew.FromMM(0.4))
        zone.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.4))
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(zone)

    for x1, y1, x2, y2 in cfg.get("pour_keepouts", []):
        keepout = pcbnew.ZONE(board)
        keepout.SetIsRuleArea(True)
        keepout.SetDoNotAllowCopperPour(True)
        keepout.SetDoNotAllowTracks(False)
        keepout.SetDoNotAllowVias(False)
        keepout.SetDoNotAllowPads(False)
        keepout.SetDoNotAllowFootprints(False)
        lset = pcbnew.LSET()
        for layer in layers:
            lset.AddLayer(layer)
        keepout.SetLayerSet(lset)
        keepout.Outline().AddOutline(_polygon([(x1, y1), (x2, y1), (x2, y2), (x1, y2)]))
        board.Add(keepout)

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(board_path), board)
    return board_path
