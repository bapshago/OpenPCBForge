# JLCPCB Open API in pcbforge

JLCPCB's business API ("overseas openapi") lets pcbforge check parts against JLCPCB's own
records instead of trusting LCSC numbers typed into a design. It caught nothing new on the
boards so far, but would have caught C723496 (an 01005 resistor on 0402 pads) before JLCPCB
held the heater controller order. **It needs your own JLCPCB API key for the parts
endpoints** (see Setting it up); without one, everything here is switched off.

## What's built

- `pcbforge/jlcapi.py`: a small Python client for the component endpoints (no new dependencies).
- `pcbforge/partcheck.py`: checks every BOM line with an LCSC number:
  - the part exists at JLCPCB;
  - its **package matches the footprint**: chip sizes exactly (C723496 is 01005, on 0402
    pads: error), and pin counts for ICs (an 8-pin part on a SOT-23-5: error);
  - its **value** matches for resistors and capacitors;
  - its maker part number: a different maker's equivalent is noted in the report, not a warning
    (JLCPCB places the part the LCSC number names);
  - **stock** covers the order (`BOARD["order_quantity"]`, default 5 boards): error if
    short, warning under twice the need;
  - whether it's a basic or an extended part (each extended part
    type adds JLCPCB's setup fee).
- `pcbforge parts-check <design.py | bom.csv | board.kicad_pcb> [--boards N]`: runs the check on
  its own (seconds, no routing) and writes `build/<name>/<name>-jlc-check.md`. Exit code 1 on any
  error. A JLCPCB BOM (`fab/.../<name>-bom-jlc.csv`, or the BOM JLCPCB's tool exports) or a
  board file needs no SKiDL, so it works with any KiCad Python install.
- `pcbforge jlc-auth`: checks the keys and the connection without printing the keys.
- `pcbforge jlc-part C... [C...]`: prints JLCPCB's full record for parts.
- `pcbforge build` runs the same check automatically when credentials are set and prints the
  errors under the DRC summary. An API problem never fails a build; it's reported instead.
- Tests: `tests/test_partcheck.py`, against a fake API: C723496's record, C25804 as JLCPCB
  returned it live, the exact signature header, and signing on the server's clock.

## Setting it up

The parts check needs **your own JLCPCB API key for the parts endpoints**. JLCPCB issues it;
pcbforge doesn't come with one, and without it everything here is switched off (builds run
as before). Working since Nov 5, 2026.

**1. Create an app and request the parts APIs** (once, at JLCPCB):

- Sign in at **api.jlcpcb.com** with your JLCPCB account → **Console** → **Manage Apps** →
  create an app (any name, e.g. "PCBForge").
- Under **Permission Packages → Requestable APIs**, request the **Parts** service. Its four
  APIs are all pcbforge needs:
  - Query Component Detail Data Interface (`/overseas/openapi/component/getComponentDetailByCode`), the one the check uses;
  - Component information interface (`getComponentInfos`);
  - Get Component list (`getComponentLibraryList`);
  - Query Private Component Library Interface (`getPrivateComponentLibrary`).
- Wait for JLCPCB to approve them: they move to **Authorized APIs** with status **Enabled**.
  The order, quote and other APIs aren't needed.

**2. Create the key pair:**

- On the app's **App Setting** page, note the **App ID**.
- Click **Create** under **Access Key**. The pop-up shows an **access key** and a **secret
  key**. The secret is **shown only once**: copy both now. Make sure the new key's switch is on.
- Use the access key and the secret that were created **together**. The **Tokenization Key**
  on the same page is for field encryption, not for this.

**3. Store them** (never in the repo, never pasted into a chat):

- On your PC: in `.env` in the pcbforge folder (copy `.env.example`; `.env` is git-ignored):
  ```
  JLC_APP_ID=<App ID>
  JLC_ACCESS_KEY=<access key>
  JLC_SECRET_KEY=<secret key>
  ```
  Variables already set in Windows win over `.env`; `set JLC_` shows any.
- For Claude's cloud sessions: add the same three names as environment variables in the
  cloud environment's settings (session title bar → environment → Edit). New sessions pick
  them up; a session already running doesn't.

**4. Check the connection:**

```
"C:\Program Files\KiCad\9.0\bin\python.exe" -m pcbforge.cli jlc-auth
```

It never prints the keys. It shows each key's length and first two characters, flags spaces,
quotes or line breaks pasted in with them, compares the PC's clock with JLCPCB's server, and
looks up one part. Success ends with `Test call: OK. C25804 = 0603WAF1002T5E 0603, stock ...`.

| JLCPCB's answer | Meaning |
|---|---|
| `application not exists` | `JLC_APP_ID` is wrong. |
| `invalid request accessKey.` | `JLC_ACCESS_KEY` is wrong, swapped with the secret, or switched off. |
| `The request signature verify failed` | App ID and access key are known; the secret doesn't belong to that access key (or was pasted with extra characters). |

Signatures carry a timestamp: pcbforge reads JLCPCB's time before the first call and signs on
it, so a PC clock that's minutes off still works (`jlc-auth` reports the offset).

## Using it

```
REM a JLCPCB BOM (needs no SKiDL): the usual way on Windows
"C:\Program Files\KiCad\9.0\bin\python.exe" -m pcbforge.cli parts-check fab\<board>_rev_a\<board>-bom-jlc.csv

REM a design file (needs SKiDL 3) or a KiCad board, for a different quantity
... -m pcbforge.cli parts-check designs\<board>.py --boards 10
... -m pcbforge.cli parts-check path\to\board.kicad_pcb

REM everything JLCPCB holds for one or more parts
... -m pcbforge.cli jlc-part C25741 C82011
```

`parts-check` prints each problem line and writes `build/<name>/<name>-jlc-check.md`: one row
per BOM line with JLCPCB's package, stock, basic/extended type, unit price at the order
quantity and the result. **Errors** (exit code 1): unknown part, package or pin count that
doesn't fit the footprint, wrong resistor/capacitor value, not enough stock. **Warnings**:
no LCSC number (expected for parts you solder yourself), stock under twice the need.
**Notes**: JLCPCB places another maker's equivalent of the MPN in the design.

Live results, Nov 5, 2026: the heater controller (36 lines) and two research boards (23 and 19
lines) all 0 errors.

## How it works

What JLCPCB returns for a part (from `jlc-part`, Nov 5 2026): componentCode, componentModel
(MPN), componentBrandEn, componentSpecification (package), firstTypeName/secondTypeName
(category), libraryType (`base` = basic, `expand` = extended), description, solderJointCount,
priceRanges (`endQuantity: -1` = and up), stockCount, parameters (e.g. Resistance,
Capacitance), rohsFlag, datasheet links, and `assemblyComponentFlag`, which is false even for
basic parts, so pcbforge doesn't use it.

**Signing is confirmed** against JLCPCB's core library (`jlc-openapi-sdk-core-java` 1.0.0,
read from its class files, Nov 5 2026): HMAC-SHA256 over method, path, timestamp (Unix
seconds), 32-character nonce and body, each followed by a newline, Base64-encoded; header
`Authorization: JOP appid="..",accesskey="..",timestamp="..",nonce="..",signature=".."`.
`tests/test_partcheck.py` pins the exact header.

**The server address is not in the SDK:** the core library requires one (`https://` only) and
has no default. pcbforge uses `https://open.jlcpcb.com` unless `JLC_API_BASE` is set. That host is live: an
unsigned request gets `{"code":400,"success":false,"message":"The request authorization cannot
be empty."}` (checked Nov 5 2026). The core library
also supports other credential types (app code, bearer token, RSA key pair, field encryption);
pcbforge uses the access-key + secret-key (HMAC) kind, the SDK's default.

## What the SDK offers (read from the jar's class files)

| Area | Endpoints | Used by pcbforge |
|---|---|---|
| Components | `getComponentDetailByCode` (details for a list of C-numbers: package, MPN, brand, stock, price breaks, basic/extended, parameters, datasheet, assembly flag); `getComponentInfos` (the whole catalogue, paged by `lastKey`: LCSC number, category, MPN, package, solder joints, manufacturer, basic/extended, description, datasheet, price, stock); `getComponentLibraryList` (JLCPCB's assembly library); `getPrivateComponentLibrary` (your own stock at JLCPCB) | Detail lookup: yes. Private stock: client method only |
| PCB orders | Gerber upload, online price, create order, audit info, order and work-in-progress status, stencil orders | Not yet |
| 3D printing | File upload, price, order | No |
| Account | Balance (`jpay`) | No |

There is **no keyword search endpoint**. Searching for parts ("100k 0402") would mean
downloading the catalogue with `getComponentInfos` into a local database and searching that.

## Next steps, in order of value

1. **Prefer parts you already hold:** use `getPrivateComponentLibrary` to mark BOM lines that
   your JLCPCB stock covers, and to suggest them in `<name>-jlc-parts.md`.
2. **Local part search:** a `pcbforge parts-sync` that pages through `getComponentInfos` into
   SQLite, then ranked suggestions (in stock, basic first, matching package and value) for every
   "to choose" line, and a `search_parts` tool for the design agent.
3. **Quote and order** (the PCB endpoints): upload Gerbers and get a price straight from a
   build; creating orders spends money, so keep a human approval step in front of it.
