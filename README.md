# pcbforge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A code-first PCB pipeline with Claude on top. You describe a circuit in
Python (or in plain English, and Claude writes the Python), and pcbforge turns
it into a routed, DRC-checked board plus fab-ready Gerbers.

```
design.py (SKiDL)  ──▶ netlist ──▶ .kicad_pcb (pcbnew API: footprints, outline, placement)
                   ──▶ Freerouting (autoroute via Specctra DSN/SES)
                   ──▶ kicad-cli DRC (JSON) ──▶ Claude reads it and fixes the design
                   ──▶ kicad-cli Gerbers + drill + pick-and-place ──▶ zip
                   ──▶ gerbonara SVG preview of the Gerbers
```

KiCad does the hard geometry: footprints, routing and rule checks. Claude does
what it's good at: turning a spec into a correct circuit, choosing parts,
reading DRC reports and iterating.

**New here?** [`docs/user_guide.md`](docs/user_guide.md) explains, step by step, how to get a
board designed, ordered, built and tested by working with Claude. No setup needed for that.

## Setup

**Ubuntu 24.04:** `./scripts/setup_ubuntu.sh` installs KiCad 9, its libraries,
Java 25 and Freerouting, and creates `.venv`.

**macOS / Windows:** install KiCad 9 from kicad.org and Java 25+ (for
example Temurin), then:

```bash
./scripts/get_freerouting.sh
# Use KiCad's bundled Python so `import pcbnew` works:
#   macOS:   /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
#   Windows: "C:\Program Files\KiCad\9.0\bin\python.exe"
<kicad-python> -m venv --system-site-packages .venv
.venv/bin/pip install -e '.[dev]'
```

Check that it works: `pytest` runs the blinky board through the full pipeline.

## Usage

```bash
# Build a design file by hand
pcbforge build designs/blinky.py
#   blinky: 3 parts, 3 nets, routed=True
#   DRC: 0 errors, 0 warnings, 0 unconnected
#   Gerbers: build/blinky/blinky-gerbers.zip

# Let Claude design one (needs ANTHROPIC_API_KEY or `ant auth login`)
pcbforge agent "A 30x20mm board: 2-pin header for 5V in, a power LED with a resistor, \
and a tactile button that pulls a 3-pin header's signal pin to ground"
```

Open `build/<name>/<name>.kicad_pcb` in KiCad to inspect or hand-tune the
board. Upload `build/<name>/<name>-gerbers.zip` to your fab (JLCPCB, PCBWay,
OSH Park, and so on). For JLCPCB assembly, also upload `<name>-bom-jlc.csv`
and `<name>-cpl-jlc.csv`.

The agent shows each generated design file and asks before running it,
because a design file is Python that gets executed. `--auto-approve` skips
the prompt.

## JLCPCB files for an existing board

`pcbforge jlc` makes a JLCPCB BOM and CPL (and fresh Gerbers) straight from any
`.kicad_pcb`, including boards drawn by hand or imported from Altium, PADS or Eagle:

```bash
pcbforge jlc path/to/board.kicad_pcb --out build \
    --value-field ALTIUM_VALUE   # field holding the real value, if Value is a placeholder
    --include Q4                 # place a part that also has through-hole pads (e.g. TO-220/DPAK)
    --exclude R99                # leave a part out
    --rotate U7=270              # per-part JLCPCB rotation fix (repeatable)
    --rotate-fp 0805=270         # rotation fix for every part with that footprint name (repeatable)
    --offset=-48.5,200.0         # shift the CPL to match Gerbers made in another tool
    --lcsc L1=C130293            # LCSC number for parts matched by hand (repeatable; R1,R2=C17414 works)
    --move Q4=0,-4.4             # shift one part in the CPL (mm, +y up), e.g. a TO-220/DPAK combo footprint
    --set-value Q2,Q3=IRL540NS   # replace a value (a substitute part, or one the board leaves blank)
    --no-gerbers
```

Resistor and capacitor values are written the way JLCPCB's BOM check reads them
(`4k7` -> `4.7kΩ`, `240R` -> `240Ω`, `100n` -> `100nF`, `2u2` -> `2.2uF`); `--raw-values`
keeps them as drawn. Design-file BOMs from `pcbforge build` get the same treatment.

It places every part whose pads are all SMD, at the centre of its SMD pads (imported
footprints don't always put the origin there), skips values that mean "not fitted"
(na, DNP, ...), and prints what it left out and why: through-hole parts, mixed
SMD/through-hole footprints, and parts with a missing or unknown value.

## JLCPCB parts check

With your own **JLCPCB API key for the parts endpoints** (created at api.jlcpcb.com:
Console → Manage Apps → an app with the Parts APIs approved → Access Key → Create), pcbforge
checks every LCSC number against JLCPCB's records: package against footprint, value, stock
and basic/extended type. Put `JLC_APP_ID`, `JLC_ACCESS_KEY` and `JLC_SECRET_KEY` in `.env`, then:

```bash
pcbforge jlc-auth                                   # check the keys (never prints them)
pcbforge parts-check fab/<board>_rev_a/<board>-bom-jlc.csv [--boards N]
pcbforge jlc-part C25741                            # JLCPCB's full record for a part
```

`pcbforge build` runs the same check when the keys are set. Details and troubleshooting:
`docs/jlcpcb_api.md`.

## Writing a design file

See `designs/blinky.py` for the minimum and `designs/signal_module_928.py`
for a full board. A design file defines:

| Name | Required | Meaning |
|---|---|---|
| `build()` | yes | Creates SKiDL `Part`s (each with `ref=` and `footprint="Lib:Name"`) and connects `Net`s |
| `BOARD` | no | Board settings, below; the origin is top-left with y pointing down |
| `PLACEMENT` | no | `{ref: (x_mm, y_mm, rotation_deg)}`; parts without an entry go on a grid |

`BOARD` keys:

| Key | Meaning |
|---|---|
| `width_mm`, `height_mm` | Board size (a rectangle unless `outline` is given) |
| `outline` | `[(x, y), ...]` closed polygon for a custom shape |
| `holes` | `[(x, y), ...]` M3 mounting holes (`hole_footprint` to change) |
| `silk` | `[(x, y, text, size_mm, rotation), ...]` silkscreen labels |
| `hide_silk_refs` | `True` hides reference designators on the silkscreen (dense boards) |
| `route_passes` | Freerouting passes (default 20; busy boards need more) |
| `clearance_mm` | Copper clearance for every net, default 0.2 mm. 0.15 suits 0.5 mm-pitch ICs (JLCPCB's 2-layer minimum is about 0.127 mm) |
| `route_attempts` | Fresh routing tries, keeping the most complete (default 1) |
| `ground_pour` | Net name, e.g. `"GND"`, to pour on both layers after routing |
| `pour_keepouts` | `[(x1, y1, x2, y2), ...]` areas kept free of poured copper (antennas) |
| `jlc_rotations` | `[(footprint_regex, degrees), ...]` extra JLCPCB placement-rotation fixes, checked before the built-in table in `pcbforge/jlc.py` |
| `jlc_ref_rotations` | `{ref: degrees}` per-part JLCPCB rotation fixes, for parts whose model differs from others in the same package |

Footprints are KiCad 9 library names (`Lib:Name`). `footprints/pcbforge.pretty` holds KiCad
footprints adapted for JLCPCB (for example thermal vias opened to 0.3 mm); use them as
`pcbforge:Name`. See `footprints/README.md`.

Put `part.fields["LCSC"] = "C12084"` (and optionally `"MPN"`) on a part to
carry its LCSC number into the JLCPCB BOM.

**Parts catalogue** (`pcbforge/parts.py`): every part already ordered or checked at JLCPCB,
with its LCSC number. A design can pick one by name (`part(..., **parts.pick("res_0603_10k"))`),
and any part without an LCSC number of its own gets the catalogue's part for its footprint and
value automatically. Each build also writes `<name>-jlc-parts.md`: every BOM line with its LCSC
link, and for parts still to choose, search terms plus JLCPCB and LCSC search links. The BOM's
Footprint column uses JLCPCB's package names (`0603`, `SOIC-8`, `XH-3A 2.5mm`), not KiCad's.

Working on this repo as Claude? Read `docs/claude_playbook.md` first: how boards get
designed, ordered, brought up and documented here, with lessons from the first boards.

## Boards in this repo

| Board | Design | Fab snapshot | Notes |
|---|---|---|---|
| 928 Signal Module rev A (**installed in the '81**, Nov 1 2026) | `designs/signal_module_928.py` | `fab/signal_module_928_rev_a/` | `docs/signal_module_928_handoff.md`, firmware in `firmware/signal_module_928/` |
| 928 Heater Controller rev A (in production) | `designs/heater_controller_928.py` | `fab/heater_controller_928_rev_a/` | `docs/heater_controller_928.md` |
| `designs/blinky.py` | the smallest example: 3 parts | built by `pytest` | |

The two 928 boards were made for a 1981 Porsche 928 converted to a Nissan Leaf drivetrain, and
share a 60 x 90 mm outline and mounting holes. They're real, ordered boards, included as
worked examples: a design file, the exact files sent to JLCPCB, and a connection test
(`tests/test_<board>.py`) that checks every pin against the datasheets. The signal module's
hardware and firmware are also published on their own at
[bapshago/928-Signal-Board](https://github.com/bapshago/928-Signal-Board).

## Layout

| Path | Role |
|---|---|
| `pcbforge/netlist.py` | Runs the design file with SKiDL, then ERC and netlist |
| `pcbforge/board.py` | Builds the `.kicad_pcb` with pcbnew: outline, nets, footprints, placement |
| `pcbforge/route.py` | Freerouting round-trip |
| `pcbforge/pour.py` | Optional ground pour with keepouts |
| `pcbforge/drc.py` | `kicad-cli pcb drc`, summarized |
| `pcbforge/export.py` | Gerbers, drill file, pick-and-place, zip |
| `pcbforge/jlc.py` | JLCPCB BOM, CPL and parts list |
| `pcbforge/parts.py` | Parts catalogue: parts already ordered at JLCPCB, used by default |
| `pcbforge/jlcapi.py`, `pcbforge/partcheck.py` | JLCPCB Open API client and part check: package, value and stock of every LCSC number (`pcbforge parts-check`; see `docs/jlcpcb_api.md`) |
| `pcbforge/preview.py` | Renders the Gerbers to SVG with gerbonara |
| `pcbforge/pipeline.py` | Runs all of the above in order |
| `pcbforge/agent.py` | Claude tool-use agent (symbol/footprint lookup, write design, build) |
| `pcbforge/env.py` | KiCad paths and tool locations, each overridable by env var |

## Good next steps

1. **Smarter placement.** Group parts by net connectivity (force-directed
   placement or simulated annealing) so routes are short. Have Claude supply
   the constraints ("decoupling caps next to U1's VDD pins", "connectors on
   the edge") rather than coordinates.
2. **Schematic output.** SKiDL can generate KiCad schematics, which makes
   human review much easier.
3. **Net classes.** Wider traces for power nets (design settings) before routing.
4. **Part search for the agent.** The JLCPCB parts check is done (`docs/jlcpcb_api.md`);
   next, a local copy of JLCPCB's catalogue so the agent can search it for parts.
5. **Fab-specific DRC.** Load your fab's design rules (`.kicad_dru`) so DRC
   matches what they can manufacture.

## Gotchas

- **Java version:** Freerouting 2.4 needs Java 25+. Set `JAVA=/path/to/java25`
  if the default `java` is older.
- **SKiDL tool version:** SKiDL defaults to KiCad 10 libraries. pcbforge pins
  KiCad 9; change `SKIDL_TOOL` when you upgrade.
- **`pcbnew` import errors:** the venv must use the same Python that KiCad was
  built against, with `--system-site-packages`.

## Contributing

pcbforge was written for one person's projects and shared in case it's useful to others.
Issues and pull requests are welcome: bug reports with the design file and the build output,
new parts for the catalogue (with their LCSC numbers and where they were checked), JLCPCB
rotation fixes confirmed in their placement preview, and the "Good next steps" above.
Run `pytest` before sending a change; it needs KiCad 9 for the board tests (they skip
without it).

## License

MIT, see [LICENSE](LICENSE). The example board designs and fab files are covered too.
pcbforge drives KiCad, Freerouting and SKiDL, which have their own licenses (GPL-3.0,
GPL-3.0 and MIT); install them separately.
