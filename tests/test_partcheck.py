"""JLCPCB part check (pcbforge/partcheck.py) and API client (pcbforge/jlcapi.py), against a fake API."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("skidl")
from pcbforge.jlcapi import JlcApi, JlcApiError  # noqa: E402
from pcbforge.netlist import Design, PartSpec  # noqa: E402
from pcbforge.partcheck import check_parts, write_check_report  # noqa: E402

# Shapes follow the SDK's ComponentDetailResponseVO.
DETAILS = {
    "C723496": {"componentCode": "C723496", "componentModel": "RC0100FR-07100KL", "componentSpecification": "01005",
                "description": "100kΩ ±1% 01005 Chip Resistor", "stockCount": 50000, "libraryType": "expand"},
    "C25741": {"componentCode": "C25741", "componentModel": "0402WGF1003TCE", "componentSpecification": "0402",
               "description": "100kΩ ±1% 0402 Chip Resistor", "stockCount": 900000, "libraryType": "base",
               "priceRanges": [{"startQuantity": 1, "endQuantity": 999, "unitPrice": 0.0012}]},
    # C25804 as JLCPCB returned it live (Nov 5 2026, trimmed): assemblyComponentFlag is false on a basic part
    "C25804": {"componentCode": "C25804", "componentModel": "0603WAF1002T5E", "componentBrandEn": "UNI-ROYAL(Uniroyal Elec)",
               "componentSpecification": "0603", "libraryType": "base", "assemblyComponentFlag": False,
               "description": "-55℃~+155℃ 100mW 10kΩ 75V Thick Film Resistor ±1% ±100ppm/℃ 0603 Chip Resistor - Surface Mount ROHS",
               "parameters": [{"parameterName": "Resistance", "parameterValue": "10kΩ"}], "stockCount": 43607955,
               "priceRanges": [{"startQuantity": 1, "endQuantity": 999, "unitPrice": 0.0024},
                               {"startQuantity": 50200, "endQuantity": -1, "unitPrice": 0.0015}]},
    "C7843": {"componentCode": "C7843", "componentModel": "SN74LVC1T45DBVR", "componentSpecification": "SOT-23-6",
              "description": "Level translator", "stockCount": 20, "libraryType": "expand"},
    "C12084": {"componentCode": "C12084", "componentModel": "SN65HVD230DR", "componentSpecification": "SOIC-8",
               "description": "CAN transceiver", "stockCount": 5000, "libraryType": "expand",
               "assemblyComponentFlag": True},
}


class FakeApi:
    def __init__(self):
        self.asked = []

    def component_details(self, codes):
        self.asked += list(codes)
        return {c: DETAILS[c] for c in codes if c in DETAILS}


def design(parts):
    return Design(name="t", parts=parts, nets=[], board={}, placement={})


def rows_by_ref(rows):
    return {r["refs"][0]: r for r in rows}


def test_catches_the_01005_part_on_0402_pads():
    d = design([PartSpec(f"R{i}", "100k", "Resistor_SMD:R_0402_1005Metric",
                         fields={"LCSC": "C723496", "MPN": "0402WGF1003TCE"}) for i in range(21, 33)])
    r = check_parts(d, FakeApi(), boards=5)[0]
    assert r["level"] == "error" and any("01005 doesn't fit the 0402" in p for p in r["problems"])
    assert "the design names 0402WGF1003TCE" in r["notes"][0]          # the other maker's part is noted


def test_good_parts_pass_and_report_stock_and_price():
    d = design([PartSpec("R21", "100k", "Resistor_SMD:R_0402_1005Metric", fields={"LCSC": "C25741", "MPN": "0402WGF1003TCE"}),
                PartSpec("U2", "SN65HVD230DR", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", fields={"LCSC": "C12084", "MPN": "SN65HVD230DR"})])
    rows = rows_by_ref(check_parts(d, FakeApi(), boards=5))
    assert rows["R21"]["level"] == "ok" and rows["R21"]["package"] == "0402" and rows["R21"]["unit_price"] == 0.0012
    assert rows["U2"]["level"] == "ok"


def test_value_stock_pins_unknown_and_missing():
    d = design([
        PartSpec("R1", "4.7k", "Resistor_SMD:R_0603_1608Metric", fields={"LCSC": "C25804"}),       # JLCPCB part is 10k
        PartSpec("U5", "SN74LVC1T45", "Package_TO_SOT_SMD:SOT-23-6", fields={"LCSC": "C7843"}),    # 20 in stock
        PartSpec("U6", "SN74LVC1T45", "Package_TO_SOT_SMD:SOT-23-6", fields={"LCSC": "C7843"}),
        PartSpec("U7", "X", "Package_TO_SOT_SMD:SOT-23-5", fields={"LCSC": "C12084"}),             # SOIC-8 part on 5 pins
        PartSpec("U8", "Y", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", fields={"LCSC": "C999999"}),   # unknown
        PartSpec("C1", "10u", "Capacitor_SMD:C_0805_2012Metric"),                                  # no LCSC, no catalogue match
    ])
    rows = rows_by_ref(check_parts(d, FakeApi(), boards=20))
    assert any("value 4.7k" in p for p in rows["R1"]["problems"]) and rows["R1"]["level"] == "error"
    assert any("only 20 in stock, 40 needed" in p for p in rows["U5"]["problems"])
    assert any("has 8 pins, footprint 5" in p for p in rows["U7"]["problems"])
    assert rows["U8"]["level"] == "error" and "no part C999999" in rows["U8"]["problems"][0]
    assert rows["C1"]["level"] == "error" or rows["C1"]["level"] == "warning"


def test_report(tmp_path):
    d = design([PartSpec("R21", "100k", "Resistor_SMD:R_0402_1005Metric", fields={"LCSC": "C723496"})])
    text = write_check_report(d, check_parts(d, FakeApi(), 5), tmp_path / "check.md", 5).read_text()
    assert "1 errors" in text and "[C723496](https://www.lcsc.com/product-detail/C723496.html)" in text


def test_client_from_env(monkeypatch):
    for k in ("JLC_APP_ID", "JLC_ACCESS_KEY", "JLC_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert JlcApi.from_env() is None
    monkeypatch.setenv("JLC_APP_ID", "a"); monkeypatch.setenv("JLC_ACCESS_KEY", "b"); monkeypatch.setenv("JLC_SECRET_KEY", "c")
    assert JlcApi.from_env().app_id == "a"


@pytest.fixture
def fake_server():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"], seen["auth"] = self.path, self.headers.get("Authorization")
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["body"] = body
            if body.get("componentCodes") == ["C401"]:
                self.send_response(401); self.end_headers(); return
            data = [DETAILS[c] for c in body["componentCodes"] if c in DETAILS]
            out = json.dumps({"code": 200, "data": data}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", seen
    srv.shutdown()


def test_client_request_and_errors(fake_server, monkeypatch):
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(k, raising=False)
    base, seen = fake_server
    api = JlcApi("app", "key", "secret", base_url=base)
    got = api.component_details(["c25741", "C723496"])
    assert set(got) == {"C25741", "C723496"} and got["C723496"]["componentSpecification"] == "01005"
    assert seen["path"] == "/overseas/openapi/component/getComponentDetailByCode"
    assert seen["auth"].startswith('JOP appid="app",accesskey="key"') and 'signature="' in seen["auth"]
    with pytest.raises(JlcApiError, match="not approved yet"):
        api.component_details(["C401"])


def test_pin_counts():
    from pcbforge.partcheck import _pins
    assert [_pins(t) for t in ("SOT-23", "SOT-23-3", "SOT-23-5", "SOT-23-6", "SOIC-8_3.9x4.9mm_P1.27mm",
                               "LFCSP-40(6x6)", "HVQFN-40-1EP_6x6mm")] == [3, 3, 5, 6, 8, 40, None]


def test_signature_matches_the_core_sdk():
    # Expected value computed independently with the core SDK's recipe (HmacSHA256, Base64).
    import base64, hashlib, hmac
    api = JlcApi("APP1", "AK1", "SECRET1")
    header = api._sign("post", "/overseas/openapi/component/getComponentDetailByCode",
                       '{"componentCodes":["C25741"]}', "1730800000", "n" * 32)
    text = 'POST\n/overseas/openapi/component/getComponentDetailByCode\n1730800000\n' + "n" * 32 + '\n{"componentCodes":["C25741"]}\n'
    sig = base64.b64encode(hmac.new(b"SECRET1", text.encode(), hashlib.sha256).digest()).decode()
    assert header == f'JOP appid="APP1",accesskey="AK1",timestamp="1730800000",nonce="{"n" * 32}",signature="{sig}"'


def test_load_dotenv(tmp_path, monkeypatch):
    from pcbforge.env import load_dotenv
    f = tmp_path / ".env"
    f.write_text('# keys\nJLC_APP_ID="app1"\nset JLC_ACCESS_KEY=key1\nJLC_SECRET_KEY=\nJLC_API_BASE=https://x\n', encoding="utf-8")
    for k in ("JLC_APP_ID", "JLC_ACCESS_KEY", "JLC_SECRET_KEY", "JLC_API_BASE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("JLC_API_BASE", "https://already-set")
    load_dotenv(f)
    import os
    assert os.environ["JLC_APP_ID"] == "app1" and os.environ["JLC_ACCESS_KEY"] == "key1"
    assert "JLC_SECRET_KEY" not in os.environ                      # empty values are skipped
    assert os.environ["JLC_API_BASE"] == "https://already-set"     # the environment wins


def test_load_parts_from_bom_and_board():
    from pathlib import Path
    from pcbforge.partcheck import load_parts
    root = Path(__file__).parent.parent / "fab" / "heater_controller_928_rev_a"
    bom = load_parts(root / "heater_controller_928-bom-jlc.csv")
    assert bom.name == "heater_controller_928"
    pulls = [p for p in bom.parts if p.ref in {f"R{n}" for n in range(21, 33)}]
    assert len(pulls) == 12 and all(p.fields["LCSC"] == "C25741" for p in pulls)
    rows = check_parts(bom, FakeApi(), 5)
    assert next(r for r in rows if "R21" in r["refs"])["level"] == "ok"
    pytest.importorskip("pcbnew")
    board = load_parts(root / "heater_controller_928.kicad_pcb")
    refs = {p.ref for p in board.parts}
    assert "R21" in refs and "J4" not in refs      # hand-soldered connectors left out


def test_parts_check_reads_keys_from_dotenv(tmp_path):
    # Regression (Nov 2026): parts-check looked for the keys before anything loaded .env.
    import os, subprocess, sys
    from pathlib import Path
    repo = Path(__file__).parent.parent
    code = ("import os, sys; sys.path.insert(0, %r); "
            "from pcbforge import env; env.load_dotenv(env.Path(%r)); "
            "from pcbforge.jlcapi import JlcApi; print(JlcApi.from_env() is not None)")
    dotenv = tmp_path / ".env"
    dotenv.write_text("JLC_APP_ID=a\nJLC_ACCESS_KEY=b\nJLC_SECRET_KEY=c\n")
    clean = {k: v for k, v in os.environ.items() if not k.startswith("JLC_")}
    out = subprocess.run([sys.executable, "-c", code % (str(repo), str(dotenv))], capture_output=True, text=True, env=clean)
    assert out.stdout.strip().endswith("True")
    # and the import alone loads the repo's own .env path
    import pcbforge.jlcapi as j
    assert "env" in vars(j)


def test_diagnose_never_prints_the_keys(fake_server, monkeypatch):
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(k, raising=False)
    base, _ = fake_server
    api = JlcApi("APPVALUE123", ' "ACCESSVALUE456', "SECRETVALUE789", base_url=base)
    text = "\n".join(api.diagnose())
    assert "APPVALUE123" not in text and "ACCESSVALUE456" not in text and "SECRETVALUE789" not in text
    assert "CONTAINS spaces, quotes" in text
    assert "Test call: OK. C25804 = 0603WAF1002T5E 0603" in text


def test_resigns_on_the_servers_clock(monkeypatch):
    # Nov 2026: a PC clock 339 s fast got "The request signature verify failed".
    import email.utils, time as _time
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(k, raising=False)
    stamps, real = [], _time.time     # the server keeps the true time

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            ts = int(self.headers["Authorization"].split('timestamp="')[1].split('"')[0])
            stamps.append(ts)
            ok = abs(ts - real()) < 60
            self.send_response(200 if ok else 401)
            self.end_headers()
            self.wfile.write(json.dumps({"code": 200, "data": [DETAILS["C25804"]]} if ok else
                                        {"code": 401, "message": "The request signature verify failed"}).encode())

        def date_time_string(self, timestamp=None):   # the Date header, on the true time
            return email.utils.formatdate(real(), usegmt=True)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        import pcbforge.jlcapi as j
        monkeypatch.setattr(j.time, "time", lambda: real() + 339)
        api = JlcApi("a", "b", "c", base_url=f"http://127.0.0.1:{srv.server_address[1]}")
        assert "C25804" in api.component_details(["C25804"])
        assert len(stamps) == 1 and 330 < api.clock_skew_s < 350     # measured before signing
        api._clock_checked, api.clock_skew_s = True, 0.0             # and the 401 retry still works
        assert "C25804" in api.component_details(["C25804"]) and len(stamps) == 3
    finally:
        srv.shutdown()


def test_live_record_shape():
    d = design([PartSpec("R12", "10k", "Resistor_SMD:R_0603_1608Metric", fields={"LCSC": "C25804", "MPN": "RC0603FR-0710KL"})])
    r = check_parts(d, FakeApi(), boards=5)[0]
    assert r["level"] == "ok" and r["library"] == "base" and r["unit_price"] == 0.0024
    assert "UNI-ROYAL" in r["notes"][0]
    from pcbforge.partcheck import _unit_price
    assert _unit_price(DETAILS["C25804"], 60000) == 0.0015       # endQuantity -1 = and up
