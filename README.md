# VULCAN ROTARY — six-barrel rotary gate and stutter for the Akai MPC

**Lumina Aerospace LLC.** Hangar mate to F4 Phantom (and so to GR-4 Ground).
An insert effect for MPC OS 3.10.1+ with External plugins enabled.

## What it is

A rotor of six barrels turns, every barrel fires one shot (a pulse of your signal), and the barrels spool up from rest and
wind back down. It is a rotary gate, a tempo-synced stutter, and a machine-gun roll in one effect.

```
in -> Heat (soft saturation) -> Tone (SVF, cutoff stepped per barrel) -> rotary gate (Depth / Duty / Spread)
   -> Scatter (each barrel at its own pan) -> + Report (a crack at every shot) -> Mix with dry -> Output -> soft limiter
```

The wet path only engages while the motor turns; at rest the audio passes through untouched.

## Lineage

*Facts below are from the Wikipedia history the author supplied; the M61's 6,000 rpm service rate is added from general knowledge.*

- **1946** — the US Army gives General Electric a contract for "Project Vulcan", a six-barrel weapon capable of **7,200 rounds per minute**.
- **1947** — the Air Force becomes a separate service and formally asks for a new aircraft gun. WWII had shown that fighters with centre-line weapons could hit from long range; American .50-calibre fighters (P-51, P-47) had to close in, and the 20 mm Hispano of the P-38 and P-61 fired too slowly for the jet age.
- GE's Armament Division resurrected the multi-barrel **Gatling**. It had fallen out of favour because it needs an **external power source** to turn the barrels, but turbojet fighters now had electric power to spare, and electric drive was more reliable than gas operation.
- **1949** — the first GE prototype, the 0.60-inch (15 mm) **T45**, is ground-fired at **2,500 rpm**; by **1950** it reaches **4,000 rpm**.
- Korean War experience pushes the Air Force to test 20 mm and 27 mm variants (T171 and T150, from 1952); the 20x102 mm round wins. The result is the **M61 Vulcan**, which the F-4E carries (F4 Phantom's VULCAN section is its hangar-mate cousin). The M61's service rate is **6,000 rpm**.

### How the history became the design

| History | Plugin |
|---|---|
| The Gatling needs an external power source | **Mode**: *Free* (the motor is always on), *Input* (your signal is the power supply: audio above Threshold spools the barrels up, silence winds them down), *Fire* (the Fire switch is the trigger; record it as automation to play bursts) |
| Barrels spool up from rest | **Spin Up** / **Wind Down** (ms) |
| Rates in rounds per minute | **Rate** is in **rpm**, 120 .. 7,200. One shot = one round = one barrel step; six steps = one turn of the rotor, so 6,000 rpm is 1,000 rotor revolutions a minute |
| T45 1949, T45 1950, M61, Project Vulcan | **Gun** selector snaps Rate to **2,500 / 4,000 / 6,000 / 7,200 rpm** (Manual uses the Rate knob) |
| Six barrels, each slightly different | **Spread** (barrels fall short of each other unevenly, so it ratchets), **Scatter** (each barrel sits at its own pan), **Barrel Tone** (each barrel has its own filter cutoff) |
| The muzzle report | **Report**: a ~4 ms noise crack at every shot, following the input level so an idle insert stays silent |

## Controls

| Param | Range | Default | Notes |
|---|---|---|---|
| Output | -24 .. 12 dB | 0 | parameter 0 (host-nudged on load; harmless) |
| Mix | 0 .. 100 % | 100 | wet/dry |
| Mode | Free / Input / Fire | Free | the power source |
| Fire | Off / On | Off | the trigger in Fire mode (automatable) |
| Threshold | -60 .. 0 dB | -30 | Input mode: level that powers the motor |
| Sync | Off / On | Off | lock the shot rate to song tempo |
| Rate | 120 .. 7,200 rpm | 3,000 | shots per minute (Sync Off) |
| Division | 1/64 .. 2/1 | 1/16 | shot length in song time (Sync On) |
| Spin Up | 0 .. 3000 ms | 400 | barrels from rest to full speed |
| Wind Down | 0 .. 3000 ms | 600 | and back to rest |
| Depth | 0 .. 100 % | 100 | how hard the gate cuts between shots |
| Duty | 10 .. 90 % | 45 | how long each shot lasts within its barrel step |
| Spread | 0 .. 100 % | 35 | how unevenly the six barrels fire |
| Scatter | 0 .. 100 % | 0 | each barrel at its own pan |
| Tone Mode | Off / LP / BP / HP | Off | per-shot filter |
| Tone | 200 .. 12,000 Hz | 3,000 | cutoff |
| Reso | 0 .. 100 % | 25 | |
| Barrel Tone | 0 .. 100 % | 0 | how far each barrel's cutoff departs from Tone (up to about an octave) |
| Report | 0 .. 100 % | 0 | muzzle crack |
| Heat | 0 .. 100 % | 0 | soft saturation before the gate |
| Gun | Manual / T45 1949 / T45 1950 / M61 / Project Vulcan | Manual | historical rate presets (appended parameter) |

## Built-in programs (13)

Init 50 Hz, M61 6000, Gun Run, Strafing Pass (Input mode: a burst for every hit), Hangar Stutter (plain 1/16 gate),
Triplet Roll, Barrel Tone, Phantom Report, Wind Down, T45 1949, T45 1950, Project Vulcan 7200, Sidewinder (hard scatter).

## UI

Two pages (GUN / BARRELS) in the Lumina Space Black style with Latimer Amber accent. Faders are the Lumina **Electron
Tube Slider** as film strips (`tools/make_es_fader.py --accent FFB020`): the MPC is a touchscreen, so a large bead is the
handle and the whole strip takes the drag. The decal is `assets/Vulcan Rotary decal.svg`.

### Pizzazz: the logo and a rotor you can spin

`skins/` is a hand-tuned copy of the generated screen (`tools/make_skin.py` builds it; the pipeline is in the script's header).
The decal sits faintly behind every page, and the **Rate** control is the rotor itself: six barrels turn three full turns across
120 .. 7,200 rpm while an amber arc fills and the glow rises, with one marked barrel so the spin reads at a glance.
It turns because **you** turn it. The MPC screen format has no meter or animation channel, and a plugin pushing a parameter
from the audio thread (`notifyHostParameterChanged`) would flood project automation, so there is deliberately no live
animation. If ui.json changes, rerun the pipeline (delete `skins/`, build, `make_skin.py`, build).

## Notes

- `uid` ("Lgyw") is permanent once users have projects. Append new parameters at the end; never reorder or remove.
- Soft limiter on the output; no allocation, locks or I/O in `process()`; no denormals (checked by the simulator).
- Verified with the SDK's `host_sim`: 20 of 20 checks on every program, and the measured shot rate on a test signal matches
  the Gun figures (2,498 / 3,998 / 6,000 / 7,200 rpm). Not yet heard on a real MPC.
- Build: `python tools/build.py "<path>\Vulcan Rotary"` from the SDK root. Package: `python tools/package.py ...`.

## License

MIT.

## Contact

owner@luminousworksllc.com (Lumina Aerospace LLC). Reports of what works and what does not on your MPC are welcome: device, MPC OS version, what happened.
