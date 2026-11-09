# Making a circuit board with Claude and pcbforge

A practical guide for the person asking for the board. You describe what you need; Claude
designs it with pcbforge, checks it, and hands you files that JLCPCB can make and
assemble. You review, order, solder the plug-in parts, and test with Claude's help.

This is how the 928 signal module was made: from a description to a working board, installed
in the car, in one ordering round.

## What you get

- A **design file** (`designs/<name>.py`): every part, connection and position, in this repo.
- A **picture of the board** and a **board notes document**: connector pin-outs,
  microcontroller pin map, parts you solder yourself, a power-up checklist.
- **Files for JLCPCB**: the Gerber zip (the board itself), a BOM (parts list with JLCPCB
  part numbers) and a CPL (where their machine places each part).
- If there's a microcontroller: **firmware**, tested on a PC before it ever reaches the board.

## What you need

- **Claude Code** with access to this repo (claude.ai/code or the desktop app). Claude
  runs the design tools in its own cloud workspace, so you don't need to install anything
  to get a board designed.
- A **JLCPCB** account for ordering.
- Optional, for the automatic parts check: a **JLCPCB API key for the parts endpoints**,
  created at api.jlcpcb.com (see "Checking parts with JLCPCB" below).
- On your PC: **git** (to `git pull` new files), the **Arduino IDE 2.x** for flashing
  ESP32 boards, and **KiCad 9** if you want to open the board yourself or run pcbforge
  commands locally.
- For building and testing: a soldering iron, a multimeter (DC volts and ohms), and a
  bench power supply with a current limit.

## The process at a glance

| Step | You | Claude |
|---|---|---|
| 1. Describe | Explain the board; share datasheets, photos, parts you own | Asks questions until nothing is guessed |
| 2. Design | Answer questions; decide trade-offs | Writes the design, routes it, checks every connection |
| 3. Review | Look at the picture and notes; check fit and connectors | Fixes anything you find, re-checks |
| 4. Order | Upload files to JLCPCB; report what their preview shows | Corrects rotations and parts; records what was ordered |
| 5. Build | Solder connectors, sockets, modules | Gives a step-by-step bring-up plan |
| 6. Test | Probe and measure; send results and photos | Interprets results, diagnoses faults, writes test firmware |
| 7. Install | Wire it in | Updates the docs to the board's final state |

## 1. Describe the board

Start a Claude Code session on this repo and say what you want. A good first message:

> I need a board that reads 6 switch inputs from the car (12 V when on), drives 4 relays,
> and talks CAN at 500 kbit/s. It runs on the car's 12 V. I have an ESP32 DevKit
> (38-pin) and want JST XH connectors. It must fit a 60 x 90 mm enclosure.

Then expect questions. Answer what you know and say "unknown" for the rest; Claude
will tell you how to find it out (measure it, check the label, find the datasheet).
The things that matter most:

- **Power:** supply voltage, where it comes from, how much current.
- **Every input and output:** what it connects to, voltage, current, active high or low;
  for motors, solenoids, relays and pumps, the current and whether it's on/off or PWM.
- **Modules that plug in** (ESP32 boards, regulators): the exact model. Lookalike boards
  differ in pin order and spacing. A link to the maker's page or a photo of the label helps.
- **Connectors and size:** connector type, which edge, board size, mounting holes,
  enclosure limits.
- **Parts you already own:** Claude designs around them.

**Share real documents:** datasheet links, schematics, photos with a ruler in shot, wiring
diagrams. They prevent wrong guesses, and a wrong guess costs a board order.

## 2. Design

Claude writes the design file, places the parts, runs the autorouter and KiCad's rule
check, and writes tests that compare every connection with the datasheets. Expect it to:

- ask you to decide real trade-offs (relays or MOSFETs, a jumper or a fixed setting,
  a connector or solder pads);
- explain any part it substitutes and why;
- only call the design ready when the rule check reports **0 errors and 0 unconnected**.

Useful requests:

> Show me the board picture and the connector pin-outs.
> Can it fit the same outline as the signal module?
> Add a spare input / move J2 to the bottom edge / use a 2-pin CAN connector.

## 3. Review before ordering

You know the installation; Claude doesn't. Check:

- **Connectors:** right type, right edge, pin 1 where you expect, cables can reach.
- **Module orientation:** the silkscreen shows which way the ESP32 and regulator go.
- **Fit:** size, holes, height of tall parts against the enclosure.
- **Anything you'll solder yourself:** you're happy with the list.

Ask about anything that looks odd. It's cheap now and expensive after ordering.

If you've set up a JLCPCB API key, also run the parts check (next section). It confirms with
JLCPCB that every part number is the right package and value and is in stock.

## Checking parts with JLCPCB

pcbforge can look up every LCSC part number on a board in JLCPCB's own records before you
order: does the part's package fit the footprint, is the value right, is there enough stock,
and is it a basic or an extended part (each extended part type adds a setup fee). It would
have caught the heater controller's 100k resistors that were the wrong size (01005 instead
of 0402) before JLCPCB held the order.

**You need your own JLCPCB API key for the parts endpoints.** Set it up once:

1. Sign in at **api.jlcpcb.com** with your JLCPCB account → **Console** → **Manage Apps**,
   and create an app (any name).
2. Under **Permission Packages → Requestable APIs**, request the **Parts** APIs. Wait until
   JLCPCB approves them: they show under **Authorized APIs** as **Enabled**. You don't need
   the ordering APIs.
3. On the app's settings page, note the **App ID**, then click **Create** under **Access
   Key**. Copy the **access key** and the **secret key** from the pop-up right away: the
   secret is shown only once. Ignore the "Tokenization Key"; it's for something else.
4. Put the three values in the `.env` file in the pcbforge folder (copy `.env.example` if
   you don't have one):
   ```
   JLC_APP_ID=...
   JLC_ACCESS_KEY=...
   JLC_SECRET_KEY=...
   ```
   Never paste them into a chat or commit them. For Claude's cloud sessions to use the key
   too, add the same three names in the cloud environment's settings.
5. Check it works:
   ```
   "C:\Program Files\KiCad\9.0\bin\python.exe" -m pcbforge.cli jlc-auth
   ```
   It never shows the keys. The last line should start with `Test call: OK`. If it doesn't,
   paste the output to Claude: `invalid request accessKey` means the access key is wrong,
   `signature verify failed` means the secret doesn't belong to that access key.

Then, from the pcbforge folder, check a board's BOM:

```
"C:\Program Files\KiCad\9.0\bin\python.exe" -m pcbforge.cli parts-check fab\<board>_rev_a\<board>-bom-jlc.csv
```

It ends with a summary like `36 BOM lines, 0 errors` and writes a full report to
`build\<board>\<board>-jlc-check.md` (package, stock, type and price for every line).
**Errors** must be fixed before ordering; tell Claude which. **Warnings** for "no LCSC
number" are normal for the parts you solder yourself. Add `--boards 10` to check stock for
a bigger order. To see everything JLCPCB knows about a part: `... -m pcbforge.cli jlc-part C25741`.

## 4. Order at JLCPCB

Claude gives you three files in `fab/<name>_rev_a/` (`git pull` to get them):

1. **Upload the Gerber zip.** 2 layers, 1.6 mm. Choose quantity, colour and finish
   (ENIG works well for hand soldering).
2. **Turn on PCB Assembly** (top side) and **upload the BOM and CPL.**
3. **Parts matching:** parts you've ordered before come pre-filled from pcbforge's parts
   catalogue. For anything still unmatched, open `<name>-jlc-parts.md` in the fab folder (on
   GitHub the links are clickable): each line has a JLCPCB and an LCSC search link with terms
   that work there, instead of KiCad footprint names. Send Claude a screenshot if you're unsure.
   Tell Claude every C-number you pick (e.g. "Y1 is C57131"): it goes into the design and the
   catalogue, so the next board gets it automatically.
4. **Placement preview: check every part.** JLCPCB's part models are often turned 90°
   or 180°. Report each fix exactly, for example:
   - "U7 needs to turn 90° clockwise"
   - "Q4 needs to move down about 4 mm"
   - "LED1's + mark is on the wrong end"

   Polarity matters most: diodes, LEDs, electrolytic capacitors, chips (pin 1 dot).
   Claude builds the fix into the files, so a re-order needs no manual fixes.
5. **After ordering**, download the BOM JLCPCB shows after matching and give it to
   Claude. It's saved with the board as the record of what was ordered.

Assembled boards usually arrive in about a week.

## 5. Build

JLCPCB fits the small surface-mount parts. You solder the through-hole parts: connectors,
sockets, jumper headers, plug-in modules. Claude's board notes list them. Tips from the
first boards:

- Solder socket strips **with the ESP32 plugged in**, so they line up.
- Check a regulator module's orientation **twice** before soldering it (backwards can
  put 12 V where it shouldn't go). The silkscreen labels its pins.
- Pads connected to the ground plane need more heat. A dull or lumpy joint there is
  the most likely fault.

## 6. Test (bring-up)

Ask Claude for the bring-up plan for your board. It follows this order; send Claude each
result (numbers, screenshots, photos) and it tells you whether it passes and what next:

1. **Bare board** on the bench supply at 12 V with a **100 mA current limit**. Only a few
   mA should flow.
2. **Regulator fitted:** check 5 V at the microcontroller's 5V pin before plugging it in.
3. **Microcontroller in**, current limit raised to **300 mA**, firmware flashed.
   Claude can give the firmware a **Wi-Fi status page**, so you watch the board from your
   phone instead of a serial cable.
4. **Inputs and outputs one at a time**, with a flying lead or test lamp. Claude tells you
   which pin to touch and what should happen.
5. **Communication** (CAN etc.) against a second device. A second copy of the same board
   with Claude's monitor sketch is a reliable partner.

If something fails, tell Claude exactly what you did and what you saw. On the first
board, "channel 16 works one way but not the other" led straight to one cold solder joint,
and a "repeats" count on the CAN monitor showed a faulty breakout board within minutes.

Before connecting to anything expensive (the car), Claude will list what to measure on the
wiring first.

## 7. Keep the records

Claude updates the board notes, the bench-test log and the project documents as you go.
Ask "make sure the docs are up to date" at the end of a session, and "commit and push"
if you want it saved to GitHub straight away.

## Making JLCPCB files for an existing board

Have a board someone else designed (KiCad, or imported from Altium, PADS, Eagle)? Claude
can make the JLCPCB BOM and CPL from the `.kicad_pcb` without redrawing it, fix the usual
import problems, and help you swap obsolete parts. Share the repo link or the files.
You can run the tool yourself on Windows, from the repo folder, with KiCad's Python:

```
cd C:\path\to\pcbforge
"C:\Program Files\KiCad\9.0\bin\python.exe" -m pcbforge.cli jlc path\to\board.kicad_pcb --out build
```

Claude will give you the exact options for your board (and a `.bat` file for longer ones).

## What to expect, and limits

- **Boards:** two layers, parts on the top side, assembled by JLCPCB. Up to the size and
  complexity of the 928 boards (about 120 parts) is routine.
- **Not suitable:** high-speed or RF traces (USB data, Ethernet, antennas, fast memory).
  Use ready-made modules for those, e.g. an ESP32 dev board for Wi-Fi.
- **Heavy current** (tens of amps) stays off the board: relays in a fused holder, with the
  board switching only their coils.
- **Claude can be wrong.** It checks connections against datasheets and tests, but you are
  the last check before ordering and before power goes on: look at the preview, verify
  polarity, measure before connecting.

## Quick fixes for common snags

| Snag | Fix |
|---|---|
| JLCPCB shows `惟` instead of `Ω` in the BOM | Use the BOM pcbforge writes (UTF-8 with BOM); don't re-save it in Excel. |
| BOM lines unticked with "comment" errors | Values must read like `4.7kΩ`, `100nF`; pcbforge does this. Tell Claude which lines. |
| A part sits rotated or offset in the preview | Report it exactly ("90° clockwise", "down 4 mm"); Claude fixes the CPL and the design. |
| `parts-check` says the API keys aren't set | Check `.env` is in the pcbforge folder and has all three `JLC_` lines; run `jlc-auth`. |
| A part is out of stock or obsolete | Use the search links in `<name>-jlc-parts.md`, or ask Claude for a substitute with the same footprint; check the C-number together. |
| ESP32 won't upload ("Connecting...") | Hold BOOT on the ESP32 until the upload starts. |
| Unsure whether USB and 12 V can be connected together | Ask Claude for the USB-diode check before doing it. |
