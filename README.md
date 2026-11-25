# ptx-session-kit

**Version:** 0.7.0 (beta) · **Date:** 2026-11-23

Clean-room release of **`ptx-session-kit`** including POC of **`scraft-bridge`**: 

Read, inspect, build, and edit Pro Tools sessions (`.ptx`) and convert bidirectionally between `.ptx` and Artcraft Suite SoundCraft, with:
- **zero** Avid Pro Tools &copy; installation
- **zero** external DAW templates
- **zero** GPL/LGPL parsers
- **zero** proprietary SDKs required (see [`reports/pt_api_assessment.md`](reports/pt_api_assessment.md))

using: 
- Python `3.9+` stdlib (`tools/`)
- Rust `1.95+` (`scraft-bridge/` -> `ptxconv`) and
- `.scraft` / `.scraftz`  file format (as of 0.20.1)


---




---
<img width="1552" height="927" alt="image" src="https://github.com/user-attachments/assets/a1f80384-3755-44cf-8ebd-80bf798c180b" />
<img width="1486" height="861" alt="image" src="https://github.com/user-attachments/assets/548072de-8a66-4646-bc79-7967e3a2b629" />

---

## Capabilities & Possibilities

**Build `.ptx` Sessions From Scratch (Zero Templates / Zero DAW):**
- Programmatically generate complete multi-track Pro Tools sessions (`buildspec` from a single JSON spec, one-call `newsong`
- modular `newbase` subcommands) with Audio, MIDI, Instrument, Aux, Master, and Basic/Routing Folders
  
**Deep Multi-Domain Session Coverage:** 
- Full read/write support across MIDI notes/CCs/Pitch Bend/Program+Bank/SysEx/MPE, multi-width Sync Points, `fade_in` / `fade_out`
- centered & post crossfades, Clip Groups,
- clip loops & clip gain, internal busses,
- pre/post sends, mono/dual-stereo panning (`pan`/`pan2`),
- stock plug-in insert builders + automation curves, tempo/meter/key signatures, markers, and rational SMPTE timecode rates.

**Bidirectional Pro Tools <-> SoundCraft Bridge (`ptxconv`):** 
- Convert `.ptx <-> .scraft` / `.scraftz` with zero-move `Audio Files/` linking
- compressed SoundCraft audio decoding via `craft-audio`/`symphonia` (`.flac`/`.ogg`/`.mp3`/`.m4a`/`.aac`/`.caf` -> 24-bit BWF `.wav`)
- fader-taper & log-frequency curve subdivision, externalizable [`plugin_map.json`](scraft-bridge/crates/ptx-scraft/plugin_map.json), `.mxf`/`.sd2` stem detection, `.ptxcarry.json` lossless sidecars
- machine-readable `.ptx_convert.json` fidelity ledgers (`--dry-run --report`, `--strict`).

---

## Supported Pro Tools Objects, Actions & SoundCraft Conversion

For full Rust codec internals, DSP curve calibration, and `ptxconv` CLI flags, see [`soundcraft-bridge.md`](soundcraft-bridge.md).

### A. Pro Tools Objects & `.ptx -> .scraft` (`ptxconv`) Behavior

| Object / Domain | Supported in Toolkit (`ptx_decode` / `ptx_edit` / `ptx-format`) | Behavior When Converting to SoundCraft (`.scraft`) |
|---|---|---|
| **Tracks & Track Metadata** | Create, reorder/append, remove, hide/show (`setvisible`), folder nest (`setfolder`): Audio, MIDI, Instrument, Aux, Master, Basic/Routing Folders (`VCA` read-only); plus **`comment` (`setcomment`)**, **`colour` (`setcolor`)**, **`user_delay` (`setdelay`)**, `solo`, `record_enable`, `active`, `automation_mode` (`read`/`touch`/`latch`/`trim`/`off`/`write`), `height_code`, `timebase` (`samples`/`ticks`), `elastic_mode`/`elastic_params` | **`Native`** in SC (`Audio`, `Midi`, `Instrument`, `Aux`, `Master`, `Folder`, plus track **`comments`** & `timebase`); `colour`, `elastic_mode` & `BasicFolder` type kept in `.ptxcarry.json` (**`Carry`**); `user_delay` **`Approx`** (`time_shift` insert if free slot, else **`Carry`**); `VCA` flagged **`Absent`** on `SC -> PTX` |
| **Memory Locations (Markers) & Marker Comments** | All three Pro Tools memory location **types** (`marker` `0x01`, `selection` range `0x02`, `none`/view `0x00`), both **timebases** (`ticks` via `OFF12` & `samples`), numbers, `tag=1/2/9` layouts, and **marker `comment` text** (`addmarker`, `setmarkers`, `delmarker`) | Mapped **`Native`** to SoundCraft `MemoryLocation` (preserving **`marker`/`selection`/`none` kind**, start/end positions, number, and **`comments`**) |
| **Audio Media & File Directory** | `.wav`/`.bwf`/`.aif`/`.aiff` + container paths (`0x1004`/`0x103A`/`0x0F3D`), BWF `TimeReference` & 32-B UMID, split-mono `.L`/`.R`, `.mxf`/`.sd2` stem detection (`addclip`, `relinkcheck`) | **`Native`** zero-move relative `Audio Files/`; `.L`/`.R` paired **`Native`** (or **`Approx`** L-only if missing); `.mxf`/`.sd2` preserved with **`Carry`/`Absent`** warning; on **`SC -> PTX`**, `ptxconv` decodes compressed `.flac`/`.ogg`/`.mp3`/`.m4a`/`.aac`/`.caf` -> 24-bit BWF `.wav` (`_converted/`) |
| **Audio Clips, Sync & Playlists** | Clip regions (`0x2629`), sample & `OFF12` tick placements (`0x104F`/`0x1050`), alternate **`playlists`** (`addplaylist`, `anonnames`), **`setsyncpoint`** (`b2 & 0x0F` multi-width), `splitclip`, `moveclip`, `trimclip`, `placeclip`, `deleteclip` | **`Native`** clips, sync points, and alternate `playlists` |
| **Fades, Clip Gain, Loops & Clip Groups** | `fade_in`, `fade_out`, `32 B` post & `34 B` centered crossfades (`addfade`), clip mute (`setclipmute`), static/region clip gain & multi-point **`clip_gain_lanes`** (`setclipgain`, `setclipgainat`), Clip Loops (`setcliploop`), Clip Groups (`addclipgroup`, `dissolvegroup`) | **`Native`** fades, crossfades, static clip gain & clip loops (or `--loop-handling flatten`); Clip Groups expanded cleanly + group IDs carried in `.ptxcarry.json`; multi-point clip-gain lanes **`Carry`/`Approx`** |
| **MIDI, Instrument & MPE** | Notes (`MdNLB`), Pitch Bend, CC `1..119`, Program + 14-bit Bank (`MdPBC`/`MdChun`), Ch/Poly AT, SysEx (`MdTEL`), MPE mode & `MdCDS` curves (`setnotes`, `addnote`, `emptytrack`, `chcheck`) | Notes, PB, CC, Program/Bank & AT mapped **`Native`**; SysEx & MPE mode preserved via `.ptxcarry.json` (**`Carry`**, or **`Approx`/`Absent`** under `--no-carry`) |
| **Mixer, Routing, Sends & Groups** | Volume (`-144..+12 dB`), mute, mono & dual-stereo pan (`pan`/`pan2`), `10` pre/post/mute sends, internal busses (`addbus`, `renamebus`), `<ALL>` & custom **Edit/Mix Groups (`setgroups`)** (`addsend`, `setsendpath`, `setinput`, `setoutput`, `setlane`, `setflag`); track I/O labels (`input`/`input_type`/`output`/`stem_index`) read | **`Native`** internal busses, sends, mute, track groups, fader-taper volume (`<= 0.05 dB` subdivision), `pan`/`pan2` & static LFE; built-in/`Speakers`/`Headphones`/`Out 1-2` -> **`Route::Main`**, `In ...`/`Out ...`/`Mic`/`Line` -> **`Route::Hardware(name)`**; dynamic LFE lane **`Carry`/`Absent`** |
| **Audio Interfaces & Hardware I/O (`0x2600` / `0x1022`)** | **Hardware driver/port matrices (`0x2600`, `0x1021`/`0x1022`) are not decoded/written;** clean-room sessions emit a portable logical `0x2603` I/O table (`Out 1-2` + internal busses with `0` hardware links in `0x2601`), letting Pro Tools auto-bind local interface ports on open | **Not stored in `.ptxcarry.json`** (`CarrySidecar` holds session/track/clip/plug-in data only). `SC -> PTX` rebuilds portable `Out 1-2` + internal busses via `build_2603` without host interface lock-in |
| **Plug-in Inserts (`17` stock) & Automation** | Build/edit/automate (`addplugin`, `setparam`, `addautolane`, `setpluglane`, `setflag`), `.tfx` **`settings_files`/presets** & third-party AAX metadata decode: `EQ3 1-Band`, `EQ3 7-Band`, `Dyn3 Comp/Exp/De-Esser`, `Channel Strip`, `Trim`, `AutoPan`, `Time Adjuster`, `Maxim`, `BF-76`, `D-Verb`, `Mod Delay III`, `Lo-Fi`, `Dither`, `POW-r Dither`, `SansAmp PSA-1`, `Sci-Fi`, `Pitch II`, `Click II` | **`Native`:** `EQ3 1-Band`, `Trim`, `AutoPan`, `Time Adjuster`, `Dither`/`POW-r` · **`Approx` (+ carry):** `EQ3 7-Band` (dynamic band-enable composition), `Dyn3`, `Channel Strip`, `Maxim`, `BF-76`, `D-Verb`, `Mod Delay III`, `Lo-Fi`, `SansAmp`, `Sci-Fi`, `Pitch II` · **`Carry`:** `Click II`, third-party AAX & unmapped params (`.ptxcarry.json`) |
| **Timeline & Session Setup** | Dual `Tempo` & `Meter` maps, `Key Signatures`, **`19/19` SMPTE rates**, Pull Codes (`0x2023`), `EditState`/selection, sample rates (`44.1–192 kHz`, `16`/`24`/`32f`), `write_enables`/`session_settings` (`settimeline`, `setkeysig`) | **`Native`** tempo/meter/keys/markers/`EditState`/rates; `30D`/`60D`/`119.88D`/`120D` timecode **`Approx`** + original code carried; Pull Codes **`Carry`/`Absent`**; log-frequency plug-in curves subdivided `<= 0.5%` |

### B. Supported Toolkit Actions & Entry Points

- **Read & Audit (`tools/ptx_probe.py`, `tools/ptx_decode.py`, `tools/ptx_edit.py`):**
  `census`, `diff`, `strings`, `dump`, `lpstrings`, `annotate`, `cover`, `plugins`, `regions`, `notes`, `fields`, `stats`, `inventory`, `check`, `ptx_decode.py [--only K] [--ticks] [--rate] [--validate]`, `roundtrip`, `dircheck`, `aucheck`, `chcheck`, `diffblocks`, `relinkcheck`, `rebuilddir`.
- **Clean-Room Session Build & Edit (`tools/ptx_edit.py` — non-destructive):**
  `buildspec`, `newsong`, `newbase`, `newsession`, `copy`, `rename`, `renamex`, `patch`, `dropblock`, `addtrack3`/`addtrack4`, `removetrack`, `setfolder`, `setvisible`, `setcolor`, `setcomment`, `setgroups`, `addbus`, `renamebus`, `setinput`, `setoutput`, `addsend`, `setsendpath`, `addclip`, `placeclip`, `splitclip`, `moveclip`, `deleteclip`, `trimclip`, `setsyncpoint`, `addfade`, `setcliploop`, `addclipgroup`, `dissolvegroup`, `setclipgain`, `setclipgainat`, `setclipmute`, `addplaylist`, `anonnames`, `emptytrack`, `setnotes`, `addnote`, `setlane`, `setflag`, `addplugin`, `setparam`, `addautolane`, `setpluglane`, `setdelay`, `settimeline`, `setkeysig`, `addmarker`, `setmarkers`, `delmarker`.
- **Bidirectional Conversion (`ptxconv` in `scraft-bridge/`):**
  `.ptx <-> .scraft` / `.scraftz` / `.scraft_project` (`--sc-format`, `--media`, `--loop-handling`, `--strict`, `--no-carry`, `--dry-run --report`, `--plugin-config`). See [`getting_started.md`](getting_started.md) for the full package layout and tested commands.

### C. What Happens When Unsupported or Non-Native Pro Tools Features Are Exported to SoundCraft (`ptxconv`)

- **Four-level fidelity classification ([`.ptx_convert.json`](soundcraft-bridge.md)):** Every converted session writes a machine-readable `<stem>.ptx_convert.json` ledger (also inspectable without writing files via `--dry-run --report`) classifying every element as **`Native`**, **`Approx`** (e.g. fader/log-frequency curve subdivision, `D-Verb` -> Room Reverb, `user_delay` -> `time_shift`), **`Carry`**, or **`Absent`**.
- **Lossless preservation by default (`<stem>.ptxcarry.json`):** Features that have no direct SoundCraft model (such as third-party AAX plug-in chunks, `Click II`, SysEx/MPE mode, non-PCM `.mxf`/`.sd2` media descriptors, pull codes, dynamic LFE, track `colour`, or `elastic_mode`) are **never silently dropped** — they are stored in `<stem>.ptxcarry.json` so a subsequent `.scraft -> .ptx` pass restores them.
- **Opt-out & strict guardrails:** Passing `--no-carry` skips `.ptxcarry.json`, causing non-native features to be omitted from round-trip recovery and recorded as **`Absent`** (or **`Approx`**) in the ledger. Passing **`--strict`** makes `ptxconv` **abort and refuse conversion** whenever any item is classified as `Carry` or `Absent` (use `--render-opaque-stems` to invoke an optional external `export_stems` script defined in [`config.toml`](config.toml) when opaque items exist).

---

## Core Components

1. **Read & Inspect ([`tools/ptx_decode.py`](tools/ptx_decode.py), [`tools/ptx_probe.py`](tools/ptx_probe.py)):**
Descrambles `.ptx` (`type 1` / `type 5`), inspects `0x5A` block trees (`census`, `diff`, `dump`, `plugins`, `regions`, `notes`, `check`), and decodes full session state to JSON.
2. **Write & Edit ([`tools/ptx_edit.py`](tools/ptx_edit.py)):**
Builds clean-room `.ptx` sessions from fields (`buildspec` / `newsong` / `newbase` + `addtrack4` / `addbus` / `addsend` / `setoutput` / `addclip` / `setnotes` / `addplugin` / `setlane` / `addfade` / `setmarkers` / `setkeysig`), rebuilds `0x0002` directories (`dircheck`), and verifies byte-exact block-tree round-trips (`roundtrip`). Input files are never overwritten.
3. **SoundCraft Bridge ([`soundcraft-bridge.md`](soundcraft-bridge.md), [`scraft-bridge/`](scraft-bridge/Cargo.toml)):**
Converts `.ptx <-> .scraft` / `.scraftz` cleanly (`ptxconv`) with fidelity ledgers, lossless carry sidecars, and configurable DSP mapping ([`plugin_map.json`](scraft-bridge/crates/ptx-scraft/plugin_map.json)).

---

## Quick Verification Using the Included Fixture ([`test/CR_max/`](test/CR_max/CR_max.ptx))

```bash
# 0. Verify release file integrity (Linux: sha256sum -c SHA256SUMS)
shasum -a 256 -c SHA256SUMS

# 1. Verify configuration & tool paths
python3 tools/ptx_kitconfig.py

# 2. Inspect, decode & roundtrip CR_max.ptx
python3 tools/ptx_probe.py census test/CR_max/CR_max.ptx
python3 tools/ptx_decode.py test/CR_max/CR_max.ptx --only tracks,strips,markers,fades
python3 tools/ptx_edit.py roundtrip test/CR_max/CR_max.ptx
python3 tools/ptx_edit.py dircheck test/CR_max/CR_max.ptx

# 3. Test & build Rust scraft-bridge (`ptxconv`) outside synced storage
(cd scraft-bridge && CARGO_TARGET_DIR=/tmp/ptx-scraft-target cargo test --workspace && CARGO_TARGET_DIR=/tmp/ptx-scraft-target cargo build --release -p ptx-convert-cli)
PTXCONV=/tmp/ptx-scraft-target/release/ptxconv

# 4. Inspect or convert test/CR_max/CR_max.ptx <-> .scraft in a scratch directory
"$PTXCONV" test/CR_max/CR_max.ptx --dry-run --report
rm -rf /tmp/CR_max_test && cp -R test/CR_max /tmp/CR_max_test
"$PTXCONV" /tmp/CR_max_test/CR_max.scraft -o /tmp/CR_max_test/CR_max_rt.ptx
```

See [`getting_started.md`](getting_started.md) for `.ptx` creation, modular editing, and `.scraft` conversion examples, [`soundcraft-bridge.md`](soundcraft-bridge.md) for Rust converter details, [`reports/`](reports/pt_api_assessment.md) for benchmarks, and [`config.toml`](config.toml) / [`requirements.txt`](requirements.txt) for configuration and runtime requirements.

---

## Testing Constraints & Scope Limits

**Important: `ptx-session-kit` and `scraft-bridge` (`ptxconv`) are NOT limited to 8 tracks.** The binary decoders, clean-room builders, editors, and `.ptx <-> .scraft` converters are **fully functional for large multi-track sessions** — both large modern sessions (such as the `44`-track *Stratosphere* Atmos demo with `572` regions, Clip Groups, and `VCA`s) and older Pro Tools sessions (`PT 12`–`2026` `.ptx` fixtures) have been tested offline and proven to decode and round-trip cleanly with `.scraft` (see [`reports/pt_api_assessment.md`](reports/pt_api_assessment.md)).

The only constraint concerns **live DAW-side export/re-save verification inside Pro Tools itself**:

- **DAW tier used for live saves:** Live Pro Tools open/save/bounce testing was performed on the free **Avid Pro Tools Intro Edition (`2026.11.0`)** tier (we did not purchase paid Artist, Studio, or Ultimate subscriptions strictly for automated GUI save verification). **Pro Tools Intro Edition itself** cannot save or export sessions exceeding its own DAW track limits (`8` Audio, `8` Instrument, `8` MIDI, `4` Aux/Routing Folders, `1` Master, `0` Video tracks — mirrored only as advisory warnings under `[intro_limits]` in [`config.toml`](config.toml)).
- **Live-save vs. offline scope:** Consequently, paid-tier Pro Tools features (**live DAW re-save verification** of `VCA` masters, >8 audio/MIDI/instrument tracks, surround/Atmos stems > stereo, and proprietary third-party AAX plug-in blobs) depend on Artist/Studio/Ultimate access for live DAW round-tripping, even though the toolkit reads/builds larger sessions offline and `ptxconv` preserves paid-tier state via `.ptxcarry.json`.
- **Audio Interfaces & Hardware I/O:** Hardware-specific CoreAudio/ASIO/HDX interface bindings and full I/O Setup matrices are **out of scope** and are **not** stored in `.ptxcarry.json`. Instead, both `ptx_edit.py` and `ptx-format` deliberately omit machine-specific hardware links and write a portable table (`Out 1-2` + internal busses) so Pro Tools binds outputs cleanly to whichever interface is present on open; on `.ptx -> .scraft`, recognized interface output/input names map to `Route::Main` or `Route::Hardware(name)`.
- **Format boundaries:** Binary write/build targets modern Little-Endian `.ptx` (`PT 12.3`–`2026.x`); pre-PT10 `.pt5`/`.pts`/`.ptf` archival formats (including Big-Endian PowerPC) and proprietary encrypted/third-party plug-in blobs are outside current clean-room round-trip write scope.

---

## Further Steps & Supporting the Project

**Possible Further Steps:**
  - **Legacy Pro Tools archival import (`PT 5`–`PT 9`):** clean-room decoding of `.pt5` / `.pts` / `.ptf` containers across Classic Mac/PowerPC (`be=1`), Windows (`be=0`), and `.sd2`/`.mxf` archival media (see [`reports/pt_api_assessment.md`](reports/pt_api_assessment.md)).
  - **Expanded Studio/Ultimate & Surround verification:** extend live DAW round-trip verification to VCA tracks, surround/Atmos busses, and higher track counts if Pro Tools Artist/Studio/Ultimate test access becomes available.
  - **Hardware DSP taper & stem workflows:** refine plug-in curve calibration beyond the `17` included stock plug-ins ([`plugin_map.json`](scraft-bridge/crates/ptx-scraft/plugin_map.json)) and external stem workflows.

**Sponsoring & Community Support:**  
`ptx-session-kit` and `scraft-bridge` are built clean-room without proprietary SDKs or paywalls, and live DAW verification has so far relied on the free **Pro Tools Intro Edition** tier due to recurring subscription costs.

**If this toolkit saved you time, unblocked an urgent workflow, or rescued creative work that would otherwise have been lost, please consider
  - voluntary sponsorship or
  - contributing clean, non-confidential test `.ptx` fixtures saved in Pro Tools Artist, Studio, or Ultimate**
  - report bugs / inconsistencies / lost objects or data for de- and encoding of .ptx session

Support helps fund e.g.: Higher paid-tier Pro Tools test licenses SaS subscriptions, archival hardware verification and ongoing maintenance of the package.

**Open Collective** 
We configured a voluntary, no-perks project sponsorship via **[Open Collective]([https://opencollective.com/](https://opencollective.com/therealknobmob))** (a transparent project pot for reimbursing Avid test-license invoices directly). Voluntary sponsorship grants no commercial SLA, priority deliverable, or tax-deductible charity receipt.

---

## Message to the [`SoundCraft`](https://github.com/storytold/soundcraft) Team

**You are welcome to integrate `ptx-session-kit` into SoundCraft (a clean room reimplemented Pro Tools clone that inspired us for this work)!**  

Note:
Since ArtCraft Suite SoundCraft is in an early (but impressive) state at time of this writing (0.20.1) and therefore under heavy development at the moment, the implemented "transfer bridge" in this kit is... :

- file/CMD based (by design) and and therefore not directly integrated into file dialogues of SC (but integration is easy once SC dev is in a later phase and interfaces are more stable)
- a proof of concept (POC) for the current dev. level of SC (0.20.1), that can easily be adopted
- not all features of Pro Tools are supported yet by SC, so developing and checking out a strategy for keeping unsupported PT features on the roundtrip
- mainly for automated round trip testing 

The Rust workspace under [`scraft-bridge/`](scraft-bridge/Cargo.toml) (`ptx-format`, `ptx-scraft`, and the `ptxconv` CLI) is written in `#![forbid(unsafe_code)]` Rust (`edition = "2024"`, `MIT OR Apache-2.0`, built directly on [`craft-libs`](https://github.com/storytold/craft-libs), while the ptx session kit itself is [`LICENSE`](LICENSE) MIT) with strict clean-room boundaries ([`Legal Disclaimer.md`](Legal%20Disclaimer.md)) — whether you consume `ptx-format` / `ptx-scraft` as Rust library crates or embed `ptxconv` alongside [`plugin_map.json`](scraft-bridge/crates/ptx-scraft/plugin_map.json). See [`soundcraft-bridge.md`](soundcraft-bridge.md) for the crate architecture and API entry points.

---

## Disclaimer & No Warranty

This software (`ptx-session-kit`, `scraft-bridge`, documentation, and generated or converted `.ptx` / `.scraft` / `.scraftz` / `.wav` / JSON files) is licensed under the [`LICENSE`](LICENSE) (MIT) and provided **"AS IS"**, without warranty of any kind, express or implied, including but not limited to warranties of **merchantability, fitness for a particular purpose, non-infringement, data integrity, or studio production suitability**. In no event shall the authors or contributors be liable for any claim, damaged session, lost audio, missed deadline, or consequential damages arising from the use of these tools. **Always work on copies and keep verified backups before opening or delivering production sessions.** This is an independent clean-room interoperability project and is not affiliated with, endorsed by, or sponsored by Avid Technology, Inc. or SoundCraft — see [`Legal Disclaimer.md`](Legal%20Disclaimer.md) for interoperability & clean-room reverse-engineering notes.

---

## Links & Mentioned Tools

- **DAWs & Session Formats:**
  - [Avid Pro Tools](https://www.avid.com/pro-tools) (`.ptx` target format; live save/bounce checks on Pro Tools Intro Edition `2026.11.0`)
  - [SoundCraft / `craft-libs`](https://github.com/storytold/craft-libs) (`craft-scraft-format`, `craft-audio`, `craft-midi`, `craft-time` — SoundCraft `.scraft`/`.scraftz` bridge dependencies)
- **Runtimes, Libraries & Support Platforms:**
  - [Python 3 (`python.org`)](https://www.python.org/) — standard library only (`tools/`, [`requirements.txt`](requirements.txt))
  - [TOML (`toml.io`)](https://toml.io/) — configuration format for [`config.toml`](config.toml)
  - [Rust (`rust-lang.org`)](https://www.rust-lang.org/) — `scraft-bridge/` workspace (`ptx-format`, `ptx-scraft`, `ptxconv`)
  - [Symphonia (`crates.io`)](https://crates.io/crates/symphonia) — pure-Rust compressed audio decoding (`FLAC`, `MP3`, `Ogg Vorbis`, `AAC`, `ALAC`, `CAF`) inside `ptxconv`
  - [Serde (`serde.rs`)](https://serde.rs/) & [Clap (`crates.io`)](https://crates.io/crates/clap) — JSON ledger/sidecar serialization and CLI argument parsing
  - [GitHub Sponsors](https://github.com/sponsors) & [Open Collective](https://opencollective.com/) — voluntary project sponsorship & transparent license-expense hosting
- **Kit Documentation & Reports:**
  - [`getting_started.md`](getting_started.md) — package layout, `buildspec`/`newsong`/`newbase` creation examples & `ptxconv` walkthrough
  - [`soundcraft-bridge.md`](soundcraft-bridge.md) — clean-room Rust bridge architecture, plug-in mapping & ledger reference
  - [`reports/pt_api_assessment.md`](reports/pt_api_assessment.md) — three-way benchmark & clean-room audit against [`sebedard-creator/pt_api`](https://github.com/sebedard-creator/pt_api) (`v1.6.3`) and [`zamaudio/ptformat`](https://github.com/zamaudio/ptformat)
  - [`reports/panning_law_roundtrip.md`](reports/panning_law_roundtrip.md) — `20`-variant mono/stereo panning-law round-trip verification report
