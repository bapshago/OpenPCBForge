# pcbforge footprint library

`pcbforge.pretty` holds KiCad footprints adapted for JLCPCB's process. Use them as
`pcbforge:<name>` in a design file; pcbforge finds this library before KiCad's own
(`pcbforge/env.py`, `footprint_lib_dir`).

Rules: start from a KiCad library footprint, change only what the fab needs, say what
changed in the footprint's `descr`, and list it here. Never hand-draw new pad geometry.

| Footprint | Based on (KiCad 9) | Change |
|---|---|---|
| `HVQFN-40-1EP_6x6mm_P0.5mm_EP4.1x4.1mm_ThermalVias0.3mm` | `Package_DFN_QFN:HVQFN-40-1EP_6x6mm_P0.5mm_EP4.1x4.1mm_ThermalVias` | 16 thermal vias drilled 0.3 mm instead of 0.2 mm (JLCPCB's 2-layer minimum hole); via pads stay 0.5 mm. Used for the ADAU1772 (ADI CP-40-10). |
