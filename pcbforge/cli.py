"""Command line entry point.

    pcbforge build designs/blinky.py            # run the pipeline on a design file
    pcbforge agent "USB-C powered LED board"    # let Claude write and iterate on a design
    pcbforge jlc board.kicad_pcb                # JLCPCB BOM + CPL + Gerbers for an existing board
    pcbforge parts-check designs/blinky.py      # check LCSC numbers against JLCPCB (needs JLC_* API keys);
                                                # also takes a JLCPCB BOM .csv or a .kicad_pcb
"""

import argparse
import json
import sys


def _print_summary(r: dict) -> None:
    d = r["drc"]
    print(f"{r['design']}: {r['parts']} parts, {r['nets']} nets, routed={r['routed']}")
    print(f"DRC: {d['errors']} errors, {d['warnings']} warnings, {d['unconnected']} unconnected")
    for v in d["violations"] + d["unconnected_items"]:
        print(f"  [{v['severity']}] {v['description']}: {'; '.join(v['items'])}")
    print(f"Board:   {r['board']}")
    print(f"Gerbers: {r['fab']['zip']}")
    todo = r.get("jlc_parts_to_choose", [])
    print(f"JLCPCB parts: {r['fab']['jlc_parts']}" + (f" ({len(todo)} to choose: {', '.join(todo)})" if todo else " (all chosen)"))
    print(f"Preview: {r['preview_svg']}")
    jc = r.get("jlc_check", {})
    if jc.get("ran"):
        print(f"JLCPCB check: {len(jc['errors'])} errors, {len(jc['warnings'])} warnings -> {jc['report']}")
        for e in jc["errors"]:
            print(f"  [error] {','.join(e['refs'])} {e['lcsc']}: {'; '.join(e['problems'])}")
    elif jc:
        print(f"JLCPCB check skipped: {jc['reason']}")
    if "note" in r:
        print(f"Note: {r['note']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pcbforge")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="design file -> routed board, DRC, Gerbers")
    b.add_argument("design")
    b.add_argument("--out", default="build")
    b.add_argument("--no-route", action="store_true")
    b.add_argument("--json", action="store_true", help="print the result as JSON on stdout")

    a = sub.add_parser("agent", help="have Claude design a board from a text spec")
    a.add_argument("spec")
    a.add_argument("--auto-approve", action="store_true",
                   help="run generated design files without asking (they are executed as Python)")
    a.add_argument("--max-iterations", type=int, default=30)

    j = sub.add_parser("jlc", help="existing .kicad_pcb -> JLCPCB BOM + CPL (+ Gerbers)")
    j.add_argument("board")
    j.add_argument("--out", default="build")
    j.add_argument("--value-field", help="footprint field holding the real value (e.g. ALTIUM_VALUE)")
    j.add_argument("--include", default="", help="comma-separated refs to place even if they have through-hole pads")
    j.add_argument("--exclude", default="", help="comma-separated refs to leave out")
    j.add_argument("--rotate", action="append", default=[], metavar="REF=DEG",
                   help="per-part JLCPCB rotation fix in degrees, e.g. U7=270 (repeatable)")
    j.add_argument("--offset", default="0,0", metavar="DX,DY",
                   help="mm added to every CPL coordinate, to match Gerbers made in another tool")
    j.add_argument("--lcsc", action="append", default=[], metavar="REFS=CNUMBER",
                   help="LCSC number for parts, e.g. L1=C130293 or R1,R2=C17414 (repeatable)")
    j.add_argument("--rotate-fp", action="append", default=[], metavar="FOOTPRINT=DEG",
                   help="rotation fix for every part with this exact footprint name, e.g. 0805=270 (repeatable; "
                        "--rotate wins for a single part)")
    j.add_argument("--move", action="append", default=[], metavar="REF=DX,DY",
                   help="shift parts' CPL positions in mm (+x right, +y up), e.g. Q4=0,-5 or Q2,Q3=0,-1.5 (repeatable)")
    j.add_argument("--set-value", action="append", default=[], metavar="REFS=VALUE",
                   help="replace parts' values, e.g. Q2,Q3=IRL540NS for a substitute (repeatable)")
    j.add_argument("--raw-values", action="store_true",
                   help="keep values as written (default: 4k7 -> 4.7kΩ, 100n -> 100nF for JLCPCB's check)")
    j.add_argument("--no-gerbers", action="store_true")
    j.add_argument("--json", action="store_true")

    pc = sub.add_parser("parts-check", help="check LCSC numbers against JLCPCB (package, value, stock)")
    pc.add_argument("design", help="design file (.py), JLCPCB BOM (.csv) or KiCad board (.kicad_pcb)")
    pc.add_argument("--boards", type=int, default=None, help="boards to order (default: BOARD['order_quantity'] or 5)")
    pc.add_argument("--out", default="build")

    sub.add_parser("jlc-auth", help="check the JLCPCB API keys and connection (never prints the keys)")
    jp = sub.add_parser("jlc-part", help="print JLCPCB's full record for LCSC part numbers")
    jp.add_argument("codes", nargs="+")

    args = ap.parse_args(argv)

    if args.cmd == "jlc":
        from contextlib import redirect_stdout
        from pathlib import Path

        from .existing import jlc_from_board

        split = lambda s: [x.strip() for x in s.split(",") if x.strip()]  # noqa: E731
        import re

        rot = {r.split("=")[0]: float(r.split("=")[1]) for r in args.rotate}
        fp_rot = [(f"^{re.escape(r.rpartition('=')[0])}$", float(r.rpartition("=")[2])) for r in args.rotate_fp]
        moves = {ref: tuple(float(v) for v in d.split(","))
                 for spec in args.move for refs, _, d in [spec.partition("=")] for ref in split(refs)}
        values = {ref: v.strip() for spec in args.set_value for refs, _, v in [spec.partition("=")] for ref in split(refs)}
        lcsc = {ref: c.strip() for spec in args.lcsc for refs, _, c in [spec.partition("=")] for ref in split(refs)}
        try:
            with redirect_stdout(sys.stderr):
                result = jlc_from_board(args.board, Path(args.out) / Path(args.board).stem,
                                        value_field=args.value_field, include=split(args.include),
                                        exclude=split(args.exclude), ref_rotations=rot, rotations=fp_rot,
                                        offset=tuple(float(v) for v in args.offset.split(",")),
                                        lcsc=lcsc, moves=moves, values=values,
                                        normalize_values=not args.raw_values,
                                        gerbers=not args.no_gerbers)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result))
            return 0
        print(f"{result['placed']} parts for JLCPCB to place")
        print(f"BOM: {result['bom']}")
        print(f"CPL: {result['cpl']}")
        if "fab" in result:
            print(f"Gerbers: {result['fab']['zip']}")
        labels = {"dnp": "Not fitted (value marks DNP)", "through_hole": "Through-hole, not placed",
                  "mixed_smd_tht": "SMD + through-hole pads, not placed (add with --include)",
                  "no_value": "Placed but value missing or unknown: fix before ordering",
                  "bottom": "On the bottom side"}
        for k, refs in result["report"].items():
            if refs:
                print(f"{labels[k]}: {', '.join(refs)}")
        return 0

    if args.cmd == "jlc-part":
        import json as _json
        from .jlcapi import JlcApi

        api = JlcApi.from_env()
        if api is None:
            print("JLC_APP_ID, JLC_ACCESS_KEY and JLC_SECRET_KEY aren't all set (.env or environment).", file=sys.stderr)
            return 2
        got = api.component_details(args.codes)
        print(_json.dumps(got, indent=2, ensure_ascii=False))
        return 0 if got else 1

    if args.cmd == "jlc-auth":
        from .jlcapi import JlcApi

        api = JlcApi.from_env()
        if api is None:
            print("JLC_APP_ID, JLC_ACCESS_KEY and JLC_SECRET_KEY aren't all set (.env or environment).", file=sys.stderr)
            return 2
        lines = api.diagnose()
        print("\n".join(lines))
        return 0 if lines[-1].startswith("Test call: OK") else 1

    if args.cmd == "parts-check":
        from contextlib import redirect_stdout
        from pathlib import Path

        from .jlcapi import JlcApi, JlcApiError
        from .partcheck import check_parts, load_parts, write_check_report

        api = JlcApi.from_env()
        if api is None:
            import os

            from . import env
            names = ("JLC_APP_ID", "JLC_ACCESS_KEY", "JLC_SECRET_KEY")
            found = [n for n in names if os.environ.get(n, "").strip()]
            near = sorted(p.name for p in env.DOTENV.parent.glob(".env*") if p.name != ".env.example")
            print("JLCPCB API keys not found. Set JLC_APP_ID, JLC_ACCESS_KEY and JLC_SECRET_KEY in", file=sys.stderr)
            print(f"  {env.DOTENV}  (exists: {'yes' if env.DOTENV.is_file() else 'no'})", file=sys.stderr)
            print(f"  Found: {', '.join(found) or 'none'}. Missing: {', '.join(n for n in names if n not in found)}.", file=sys.stderr)
            if near and ".env" not in near:
                print(f"  Files there: {', '.join(near)}. Rename the right one to exactly .env "
                      f"(Notepad may have saved it as .env.txt).", file=sys.stderr)
            return 2
        try:
            with redirect_stdout(sys.stderr):
                design = load_parts(args.design, args.out)
        except (ValueError, FileNotFoundError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        out_dir = Path(args.out) / design.name
        out_dir.mkdir(parents=True, exist_ok=True)
        boards = args.boards or design.board.get("order_quantity", 5)
        try:
            rows = check_parts(design, api, boards)
        except JlcApiError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        report = write_check_report(design, rows, out_dir / f"{design.name}-jlc-check.md", boards)
        for r in rows:
            if r["level"] != "ok":
                print(f"[{r['level']}] {','.join(r['refs'])} {r['lcsc'] or '-'}: {'; '.join(r['problems'])}")
        bad = sum(r["level"] == "error" for r in rows)
        print(f"{len(rows)} BOM lines, {bad} errors -> {report}")
        return 1 if bad else 0

    if args.cmd == "build":
        from contextlib import redirect_stdout

        from .pipeline import build

        # SKiDL and KiCad chatter on stdout; keep stdout clean for --json.
        with redirect_stdout(sys.stderr):
            result = build(args.design, args.out, route=not args.no_route)
        if args.json:
            print(json.dumps(result))
        else:
            _print_summary(result)
        return 0 if result["drc"]["errors"] == 0 and result["drc"]["unconnected"] == 0 else 1

    if args.cmd == "agent":
        import anthropic

        from .agent import run_agent

        try:
            run_agent(args.spec, auto_approve=args.auto_approve, max_iterations=args.max_iterations)
        except anthropic.AuthenticationError:
            print("No valid Anthropic credentials: set ANTHROPIC_API_KEY or run `ant auth login`.", file=sys.stderr)
            return 2
        except anthropic.RateLimitError as e:
            print(f"Rate limited by the API; try again shortly. ({e})", file=sys.stderr)
            return 2
        except anthropic.APIStatusError as e:
            print(f"API error {e.status_code}: {e.message}", file=sys.stderr)
            return 2
        except anthropic.APIConnectionError as e:
            print(f"Could not reach the Anthropic API: {e}", file=sys.stderr)
            return 2
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
