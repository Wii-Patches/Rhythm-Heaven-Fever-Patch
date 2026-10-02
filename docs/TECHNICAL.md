# Technical notes

How the two patches work, where they hook, and how one set of data becomes a
patched `main.dol`, a Gecko code list and a Riivolution patch. For installing and
playing, see the [README](../README.md).

Addresses below are the **USA** `main.dol` (`SOME01`) unless noted; the table at
the end lists the other releases.

## One data set, three outputs

Every patch is a list of operations on one release's `main.dol`. Here every
operation is a **Hook**: replace one instruction with a branch to a routine that
runs the displaced instruction and branches back.

| Output | How a hook is written |
| --- | --- |
| Static (`main.dol`) | branch + trampoline in a new text section at `0x80001820` |
| Gecko | `C2` code |
| Riivolution | `<memory>` writes (branch + trampoline) |

`tools/prebuilt/<feature>_<disc id>.json` holds the hooks, including the retail
word expected at every site. `tools/ops.py` turns them into each format,
`tools/patcher.py` applies them (and refuses a `main.dol` whose sites do not match,
so already-modified or foreign dumps are never touched), and `tools/build.py` writes
`codes/` and `riivolution/`. `tools/check.py` fails if the committed files drift from
the data; `tools/verify.py` checks the data against real retail DOLs for every
combination of patches.

The static build parks the trampolines in one new text section at `0x80001820`.
`0x80001800-0x80003000` is the Wii's boot-time scratch area; the first text section of
the DOL starts at `0x80004000`, and nothing in it reaches back down there. The GameCube
patch keeps its few variables in zeroed padding at `0x80005F00`, which is the same in all
four releases (the first text section is identical across them) and belongs to no hook,
so the Gecko, Riivolution and patched-DOL forms all find it in the same place.

## Classic Controller

Vague Rant's hack (`src/cc/<disc id>.txt`, unchanged apart from the per-release
addresses in his posts). It patches the KPAD library at three places:

| Site | Function | What it does |
| --- | --- | --- |
| `0x8016C4D4` | `read_kpad_button`, `andi. r0,r6,0x9FFF` | Classic Controller buttons are OR-ed into the Wii Remote button word |
| `0x8016E578` | `read_kpad_stick`, the left stick `bctrl` | the left stick becomes D-pad presses (half deflection or more) |
| `0x8016D618` | `calc_dpd_variable` | the right stick moves the IR pointer, using `SCGetAspectRatio` (`0x80124550`) to keep it round |

The game already runs the Classic Controller through KPAD, so nothing else is needed.

## GameCube controller

The pad is made to look like a **Classic Controller** to the game, so Vague Rant's code
does the rest. Rhythm Heaven Fever links the SI library but nothing polls the pads, and a
Wii game with no Wii Remote gets no KPAD sample for the Classic Controller code to read.
Three hooks (`src/gcpad/gcpad.c`, one small blob each, with the register-saving entry
stubs in `hooks.S`) fix that:

| Hook | Site | What it does |
| --- | --- | --- |
| poll | `KPADiRead` entry (`0x8016F500`) | drives the Serial Interface's own auto-polling for port 1, re-probes a replugged pad, acknowledges latched errors, frees `si::` if an unplugged pad leaves its busy flag stuck |
| sample | `KPADiRead`, `lbz r0,0x17B(r21)` (`0x8016F6A4`) | writes the pad into KPAD's sample ring as Classic Controller samples. With a Wii Remote connected, its own samples get the pad as their extension instead |
| probe | `WPADProbe` entry (`0x80129BF0`) | reports a Classic Controller on channel 0 while a pad is plugged in, so the game believes a controller is connected |

The GameCube side follows [Barrel Blast Patch](https://github.com/quatric/Barrel-Blast-Patch)
(tested on a console there): the Serial Interface lives at `0xCD006400` on a Wii (not
`0xCC…`), the result registers are hardware-written (software cannot fake them), and
polling has to be re-asserted because `si::` rewrites `SIPOLL` from its own shadow on every
retrace.

### The KPAD ring in this SDK

This SDK is newer than the one in *Animal Crossing: City Folk*, and the structures differ:

- channel `n`'s KPAD state is at `0x803B3178 + n * 0x688`
- samples are `0x42` bytes (not `0x38`); 16 live inside the state at `+0x180`, and the game
  may give KPAD more at `*(state + 0x5A0)` (count in `+0x5A4`, so the ring is that many slots
  longer than 16)
- `+0x17A` is where the next sample goes, `+0x17B` how many are queued
- in a sample: `+0x28` extension type (2 = Classic), `+0x29` extension error, `+0x2A` Classic
  buttons, `+0x2C…+0x32` the two sticks as signed 16-bit, `+0x34/+0x35` the digital L/R levels,
  `+0x40` the data format (8)
- the Classic sticks are normalised by a routine using an inner radius of 60 and an outer
  radius of 308, so a GameCube stick (about ±100 off centre) is multiplied by 3 and clamped
- the WPAD control block (table at `0x80378410`) holds the channel status at `+0x900` (`-1` =
  nothing connected) and the extension type at `+0x905`

The sample hook writes **two** samples per frame: the game's controller class reads its
buttons and the left stick from the *second* status entry `KPADRead` returns, so one sample
leaves the stick dead. The older one carries the previous frame's buttons, so press and
release edges still land in the newest entry.

### Pad mapping

| GameCube | Classic Controller bit it becomes | Game |
| --- | --- | --- |
| A, X, L (or analog L > 50 %) | A, A, L | main action |
| B, R (or analog R > 50 %) | B, R | secondary action |
| Y | Y | Wii Remote 1 |
| Start | + | pause |
| Z | HOME | HOME Menu |
| D-pad | D-pad | menus |
| control stick | left stick | menus (via the D-pad emulation) |
| C-stick | right stick | HOME Menu pointer |

### Finding the addresses in every release

`src/anchors.py` finds each function by matching a window of USA instructions against the
target DOL with the relocatable bits (branch displacements, address halves, small-data
offsets) masked out; it must match exactly once. Data addresses are read back from the
matched code (the `lis` + `addi` pair), never guessed. The sample hook's position inside
`KPADiRead` is a fixed offset (`+0x1A4`): the code is identical in every release.

## Other releases

| | USA | Europe | Japan | Korea |
| --- | --- | --- | --- | --- |
| `KPADiRead` | `0x8016F500` | `0x80170DF0` | `0x801716F0` | `0x8016F3D0` |
| sample hook site | `0x8016F6A4` | `0x80170F94` | `0x80171894` | `0x8016F574` |
| `WPADProbe` | `0x80129BF0` | `0x8012B4E0` | `0x8012BDE0` | `0x80129AC0` |
| `SIGetType` | `0x80113930` | `0x80115220` | `0x80115B20` | `0x80113800` |
| SI type cache | `0x80306230` | `0x80308290` | `0x8030D770` | `0x80306050` |
| WPAD block table | `0x80378410` | `0x80379B10` | `0x8037F850` | `0x80374290` |
| KPAD channel 0 | `0x803B3178` | `0x803B4878` | `0x803BA5B8` | `0x803AEFF8` |
| `read_kpad_button` site | `0x8016C4D4` | `0x8016DDC4` | `0x8016E6C4` | `0x8016C3A4` |

## How it was tested

Dolphin, with a throwaway user folder per run (`dev/dolphin.py`), the game's own KPAD state
read back over Dolphin's GDB stub:

- `dev/verify.py` patches a copy of each release (Classic Controller + GameCube pad, built
  with the pad's response taken from memory so the run is deterministic), boots it with **no
  Wii Remote**, presses every pad input and asserts the Wii Remote bits and stick values the
  game's KPAD holds, on all four releases
- the real Serial Interface path (Dolphin's emulated pad, driven through its Pipe input) was
  checked on the USA release: every button, the D-pad, both sticks and the pointer reach the
  game exactly as in the table above
- a Classic Controller (Dolphin's emulated extension) takes the title screen to the save-file
  menu with Vague Rant's codes; a GameCube pad alone does the same
- the stick moves the cursor between "No" and "Yes" on a confirm dialog

Dolphin's clock is emulated, so results are consistent run to run, but it is not a Wii: the
Serial Interface in particular is more forgiving than the real one (software writes to the
result registers "work" there). Nothing here has been run on a console.
