"""Claude agent: turn a plain-English board spec into a design file, build it,
read the DRC report, and iterate until the board is clean.

Claude only writes the SKiDL design file (parts, nets, board size, rough
placement). Geometry-heavy work — routing and rule checking — stays with
Freerouting and KiCad, which are good at it.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import anthropic
from anthropic import beta_tool

from . import env

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "designs" / "generated"
EXAMPLE = (ROOT / "designs" / "blinky.py").read_text()

MODEL = "claude-opus-5-5"

SYSTEM = f"""You design simple printed circuit boards by writing SKiDL design files
for the pcbforge pipeline, then building them and fixing what the design rule
check (DRC) reports.

A design file is Python with:
- `def build():` that creates SKiDL `Part`s and `Net`s. Every Part needs
  `footprint="Library:Footprint"` and an explicit `ref=`.
- optional `BOARD = {{"width_mm": .., "height_mm": ..}}` (origin top-left, y grows down).
- optional `PLACEMENT = {{ref: (x_mm, y_mm, rotation_deg)}}`; unplaced parts go on a grid.

Working example:
```python
{EXAMPLE}
```

Workflow:
1. Look up real symbols, their pin names, and footprints with the search tools.
   Never guess a library, symbol, or footprint name.
2. Write the design with write_design, then run build_design.
3. Read the DRC summary. Fix errors and unconnected items, typically by giving
   parts more room (bigger BOARD, spread-out PLACEMENT) or correcting nets, and rebuild.
4. Stop when the build reports 0 errors and 0 unconnected items, or when you
   are stuck. Then summarize the board, what you checked, and anything the
   user must verify by hand (part values, ratings, connector pinout).

Include decoupling capacitors and pull-ups where the parts' datasheets would
call for them, and say which assumptions you made."""


def _safe_name(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", name):
        raise ValueError("name must be lowercase letters, digits, underscores, starting with a letter")
    return name


@beta_tool
def list_libraries(kind: str) -> str:
    """List KiCad library names.

    Args:
        kind: "symbols" or "footprints".
    """
    if kind == "symbols":
        names = sorted(p.stem for p in env.SYMBOL_DIR.glob("*.kicad_sym"))
    elif kind == "footprints":
        names = sorted(p.stem for p in env.FOOTPRINT_DIR.glob("*.pretty"))
    else:
        return "kind must be 'symbols' or 'footprints'"
    return "\n".join(names)


@beta_tool
def search_symbols(library: str, pattern: str) -> str:
    """Find symbol names in a KiCad symbol library (case-insensitive regex). Returns at most 60.

    Args:
        library: Symbol library name, e.g. "Device" or "MCU_Espressif".
        pattern: Regex matched against symbol names, e.g. "^LED" or "ESP32-C3".
    """
    path = env.SYMBOL_DIR / f"{library}.kicad_sym"
    if not path.is_file():
        return f"No symbol library named {library!r}. Use list_libraries('symbols')."
    # Top-level symbols are indented one tab; sub-units like "R_0_1" are deeper.
    names = re.findall(r'^\t\(symbol "([^"]+)"', path.read_text(), flags=re.M)
    rx = re.compile(pattern, re.I)
    hits = [n for n in names if rx.search(n)]
    return "\n".join(hits[:60]) or "No matches."


@beta_tool
def symbol_pins(library: str, symbol: str) -> str:
    """List a symbol's pins as 'number: name' so nets can be wired correctly.

    Args:
        library: Symbol library name, e.g. "Device".
        symbol: Symbol name, e.g. "LED".
    """
    from .netlist import skidl  # configured skidl

    try:
        part = skidl.Part(library, symbol, dest=skidl.TEMPLATE)
    except Exception as e:  # skidl raises a variety of errors for bad names
        return f"Could not load {library}:{symbol}: {e}"
    return "\n".join(f"{p.num}: {p.name}" for p in part.pins)


@beta_tool
def search_footprints(library: str, pattern: str) -> str:
    """Find footprint names in a KiCad footprint library (case-insensitive regex). Returns at most 60.

    Args:
        library: Footprint library name, e.g. "Resistor_SMD" or "Connector_PinHeader_2.54mm".
        pattern: Regex matched against footprint names, e.g. "0805" or "1x04.*Vertical".
    """
    path = env.FOOTPRINT_DIR / f"{library}.pretty"
    if not path.is_dir():
        return f"No footprint library named {library!r}. Use list_libraries('footprints')."
    rx = re.compile(pattern, re.I)
    hits = sorted(p.stem for p in path.glob("*.kicad_mod") if rx.search(p.stem))
    return "\n".join(hits[:60]) or "No matches."


@beta_tool
def write_design(name: str, code: str) -> str:
    """Write (or overwrite) a design file at designs/generated/<name>.py.

    Args:
        name: File stem: lowercase letters, digits, underscores.
        code: Complete Python source of the design file.
    """
    try:
        path = GENERATED / f"{_safe_name(name)}.py"
    except ValueError as e:
        return str(e)
    GENERATED.mkdir(parents=True, exist_ok=True)
    path.write_text(code)
    return f"Wrote {path.relative_to(ROOT)}"


def make_build_tool(auto_approve: bool):
    @beta_tool
    def build_design(name: str) -> str:
        """Build designs/generated/<name>.py: netlist, board, autoroute, DRC, Gerbers.
        Returns a JSON summary including DRC errors and unconnected items.

        Args:
            name: File stem passed to write_design.
        """
        try:
            path = GENERATED / f"{_safe_name(name)}.py"
        except ValueError as e:
            return str(e)
        if not path.is_file():
            return f"{path.relative_to(ROOT)} does not exist; call write_design first."

        # Building executes the generated Python, so a person approves it first.
        if not auto_approve:
            print(f"\n--- {path.relative_to(ROOT)} ---\n{path.read_text()}\n---")
            if input("Run this design file? [y/N] ").strip().lower() != "y":
                return "The user declined to run this design. Ask what to change."

        # Separate process: SKiDL and pcbnew keep global state, and a crash in
        # KiCad's C++ layer should not take the agent down with it.
        proc = subprocess.run(
            [sys.executable, "-m", "pcbforge.cli", "build", str(path), "--json"],
            cwd=ROOT, capture_output=True, text=True, timeout=900,
        )
        if proc.returncode != 0:
            return f"Build failed:\n{proc.stderr[-4000:]}"
        result = json.loads(proc.stdout)
        drc = result["drc"]
        drc["violations"] = drc["violations"][:25]
        drc["unconnected_items"] = drc["unconnected_items"][:25]
        return json.dumps(result, indent=1)

    return build_design


def run_agent(spec: str, auto_approve: bool = False, max_iterations: int = 30) -> None:
    client = anthropic.Anthropic()
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16000,
        max_iterations=max_iterations,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        # On a safety-classifier decline, retry on a fallback model chosen by the API.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        tools=[list_libraries, search_symbols, symbol_pins, search_footprints,
               write_design, make_build_tool(auto_approve)],
        messages=[{"role": "user", "content": spec}],
    )
    for message in runner:
        for block in message.content:
            if block.type == "text" and block.text.strip():
                print(block.text)
            elif block.type == "tool_use":
                print(f"  → {block.name}({', '.join(f'{k}=' + repr(v)[:60] for k, v in block.input.items() if k != 'code')})")
        if message.stop_reason == "refusal":
            print("Claude declined this request.")
            return
