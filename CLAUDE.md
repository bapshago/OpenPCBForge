# CLAUDE.md: pcbforge

A code-first PCB pipeline: a SKiDL design file goes to a KiCad board, then
Freerouting, then DRC, then Gerbers. `pcbforge/agent.py` adds a Claude agent
that writes design files and iterates on the DRC results. See README.md for
the layout.

**Start here:** `docs/claude_playbook.md` is the working guide: new boards from a
request, JLCPCB ordering (rotation and BOM fixes), JLCPCB files for existing boards,
firmware, bring-up and bench testing, and which docs to keep in sync. It records
how the 928 signal module went from design to a bench-tested board.

## Run / test

- `pytest`: about 1 minute. The blinky board end to end, connection tests for
  each 928 board, the `pcbforge jlc` and JLCPCB-file tests, and the signal
  module firmware compiled and run on the PC (needs g++). KiCad tests need
  KiCad 9's `pcbnew` and `kicad-cli` and skip cleanly without them; routing
  assertions run only when `tools/freerouting.jar` exists.
- `pcbforge build designs/blinky.py` prints a summary and exits 0 only when DRC
  has 0 errors and 0 unconnected items.
- Freerouting 2.4 needs Java 25+. Set `JAVA` if `java` on PATH is older.

## Division of labour

Claude writes circuits (parts, nets, values, rough placement hints) and reads
reports. It must not compute trace geometry; routing belongs to Freerouting
and rule checks to KiCad. Keep new features on that side of the line.

## Conventions

- Each pipeline step is one module with one public function. `pipeline.build()`
  wires them together and returns a JSON-serializable dict. The agent's
  `build_design` tool and `--json` both depend on that shape, so change them
  together.
- Shell out to `kicad-cli` for anything it supports (DRC, exports). Use the
  `pcbnew` API only for board construction and the Specctra round-trip.
- All paths and tool locations go through `pcbforge/env.py`, never hard-coded
  elsewhere.
- Agent tools never guess library names; they look them up. A generated design
  file is executed only after user approval unless `--auto-approve` is set.
- The agent uses `claude-opus-5-5` with adaptive thinking and server-side
  refusal fallbacks (`fallbacks="default"`).

## Hard-won rules (details in the playbook)

- Never guess a pinout, footprint or module dimension: use the datasheet or
  dimension drawing, and check it in a connection test (`tests/test_<board>.py`)
  that re-types the facts independently of the design file.
- A board is ready to order only at DRC 0 errors / 0 warnings / 0 unconnected,
  with its connection tests passing and the preview looked at.
- JLCPCB rotation reports: "90° clockwise" = +270 in the CPL, "counter-clockwise"
  = +90. Put fixes in the design (`jlc_ref_rotations` / `jlc_rotations`).
- Write LCSC numbers chosen in JLCPCB's BOM tool back into the design file and save
  the as-ordered BOM in the board's `fab/` snapshot.
- When a board's status changes, update its doc, its fab README, the README board
  table.
- Commit and push to `main` here after `pytest` passes (and `arduino-cli compile`
  for changed sketches).
