# Getting Started with `ptx-session-kit`

**Version:** 0.7.0 (beta) · **Date:** 2026-11-23

Clean-room Python stdlib tooling (`tools/`) and Rust `.ptx <-> .scraft`/`.scraftz` bridge (`scraft-bridge/`) for reading, building, editing, and converting Pro Tools `.ptx` sessions without Pro Tools.

---

## 1. Package Layout

```text
ptx-session-kit/
├── README.md                      # Overview, supported objects/actions & quick verification
├── getting_started.md             # Step-by-step zero-PT tutorial & verified examples
├── soundcraft-bridge.md           # Clean-room Rust .ptx <-> .scraft bridge reference
├── config.toml                    # Runtime paths, binary format defaults & tool registry
├── requirements.txt               # Zero external PyPI dependencies (Python >= 3.9 stdlib)
├── SHA256SUMS                     # File integrity manifest (shasum -a 256 -c SHA256SUMS)
├── tools/
│   ├── ptx_kitconfig.py           # TOML config loader & path self-check
│   ├── ptx_probe.py               # XOR descrambler & 0x5A block-tree inspector
│   ├── ptx_decode.py              # Canonical JSON session decoder
│   └── ptx_edit.py                # Clean-room .ptx builder, editor, dircheck & roundtrip
├── scraft-bridge/                 # Bidirectional clean-room Rust workspace
│   ├── Cargo.toml
│   ├── Cargo.lock
│   ├── crates/ptx-format/         # .ptx binary codec (decode/ + encode/)
│   ├── crates/ptx-scraft/         # Bidirectional PTX <-> SoundCraft mapper & reports
│   └── apps/ptx-convert-cli/      # Standalone CLI binary (`ptxconv`)
├── reports/
│   ├── pt_api_assessment.md       # Three-way format toolbox benchmark & architecture audit
│   └── panning_law_roundtrip.*    # 20-variant panning-law round-trip report, PDF & plots
└── test/
    ├── CR_max3/                   # Example session (.ptx, .scraft, sidecars & Audio Files/)
    └── example_session.json       # Complete single-file JSON spec for `ptx_edit.py buildspec`
```

---

## 2. Requirements & Integrity Check

- **Python:** `3.9+` standard library only — zero third-party packages required ([`requirements.txt`](requirements.txt)).
- **Rust:** `1.95+` (`Cargo` edition `2024`, see [`scraft-bridge/Cargo.toml`](scraft-bridge/Cargo.toml)) to build `ptxconv`.
- **Verify file integrity (from the kit root):**
  ```bash
  # macOS (Linux: sha256sum -c SHA256SUMS)
  shasum -a 256 -c SHA256SUMS
  ```
- **Check kit layout:**
  ```bash
  python3 tools/ptx_kitconfig.py
  ```
  All `[format]` defaults (`default_volume`, `default_folder`, `ppq`, `xor_type`, `xor_value`, sample rate, bit depth) and `[paths]` live in [`config.toml`](config.toml). Pass `PTX_CONFIG=/path/to/config.toml` when running tools outside the kit root.

> Note for cloud-synced folders: set `CARGO_TARGET_DIR=/tmp/ptx-scraft-target` when running `cargo build` or `cargo test` so build artifacts stay outside synced storage.

---

## 3. Reading & Auditing `.ptx` Sessions

```bash
# High-level block census & tree inspection
python3 tools/ptx_probe.py census test/CR_max3/CR_max3.ptx

# Full or filtered JSON session decode (tracks, strips, sends, plugins, midi_lists, markers, fades, ...)
python3 tools/ptx_decode.py test/CR_max3/CR_max3.ptx --only tracks,strips,inserts,markers

# Verify block-tree roundtrip & 0x0002 directory parity without modifying the input file
python3 tools/ptx_edit.py roundtrip test/CR_max3/CR_max3.ptx
python3 tools/ptx_edit.py dircheck test/CR_max3/CR_max3.ptx
```

---

## 4. Creating & Editing `.ptx` Sessions Clean-Room

Every `ptx_edit.py` write command creates a new output `.ptx` and never overwrites existing files.

### Option A — Single Parameter File (`buildspec`)
Use `buildspec` to build a complete clean-room `.ptx` in **one command** from one declarative JSON specification — including busses, folder nesting, audio clips, fades, MIDI notes, sends, stock plug-ins, mixer automation lanes, timecode/key signatures, markers, and track groups. See the ready-to-run parameter file [`test/example_session.json`](test/example_session.json):

```bash
rm -rf /tmp/ptx_spec_demo && python3 tools/ptx_edit.py buildspec /tmp/ptx_spec_demo/ExampleSong.ptx test/example_session.json
```

**JSON Parameter Sections (`test/example_session.json`):**
| Key | Purpose |
|---|---|
| `rate`, `bits`, `io` | Session sample rate (`44100`–`192000`), bit depth (`16`/`24`/`32`), default main out (`1`/`0`) |
| `tempo`, `bpm`, `meter`, `keysig` | Maps starting at tick `0` (`{"ticks": 0, "bpm": 120.0}` or `"bpm": 120.0`, `{"ticks": 0, "bar": 1, "num": 4, "den": 4}`, `{"ticks": 0, "key": "C"}`) |
| `timeline` | `tc_rate`, `tc_start`, `pull`, `record_mode` |
| `busses` | Internal mono/stereo busses created before tracks (`{"name": "FX", "stereo": true}`) |
| `tracks` | Track list (`name`, `kind`: `audio`/`midi`/`instrument`/`aux`/`master`/`folder`/`rfolder`, optional `stereo`, `mono` for `master`/`rfolder`, `ticks` for `audio`, `in` folder, `input`, `output`, `colour` on `audio` tracks, `comment`, `delay`) |
| `folders` | Optional explicit `[{"track": ..., "folder": ...}]` nesting list (alternative to inline `tracks[].in`) |
| `clips`, `fades`, `notes` | WAV clips auto-copied into `Audio Files/` beside the output `.ptx` (`at`, optional `name`/`start`/`length`/`sync`, split `.L`/`.R`), fades (`fade_in`/`fade_out`/`crossfade`, `slope`, `center`, `pre`), and MIDI `setnotes` specs (or `@file`) |
| `sends`, `plugins`, `lanes`, `plugin_lanes` | Track sends (`level`, `pan`, `pre`, `mute`, `active`, `slot`), stock AAX inserts (`slot`, `plugin`, `params`, `bypass`, `active`, `multi`, `delay`), mixer lanes (`volume`/`pan`/`mute`), and plug-in automation lanes (`addautolane`/`setpluglane`) |
| `markers`, `groups` | Memory location rulers and Edit/Mix track groups |

### Option B — One-Command CLI (`newsong` with Optional JSON/Text Files)
`newsong` still works cleanly for quick command-line builds without writing a full JSON spec, and can also read `markers=@markers.json`, `groups=@groups.json`, folder routing (`rfolder` / `in:<Folder>`), and multi-key `keysig=` directly:

```bash
OUT=/tmp/ptx_demo
rm -rf "$OUT" && mkdir -p "$OUT"
cat > "$OUT/markers.json" <<'EOF'
[
  {"name": "Intro", "start": 0, "unit": "ticks", "kind": "marker"},
  {"name": "Chorus", "start": 3840000, "end": 7680000, "unit": "ticks", "kind": "selection"}
]
EOF
cat > "$OUT/groups.json" <<'EOF'
[{"name": "G_Rhythm", "members": ["Bass", "Drums"]}]
EOF

python3 tools/ptx_edit.py newsong "$OUT/DemoSong.ptx" \
  rate=48000 bits=24 bpm=120 keysig="0:C;3840000:Am" \
  markers=@"$OUT/markers.json" groups=@"$OUT/groups.json" \
  MixBus=rfolder,stereo \
  "Drums=audio,stereo,in:MixBus|test/CR_max3/Audio Files/drums_st.wav@0" \
  "Bass=audio,in:MixBus|test/CR_max3/Audio Files/bass_m.wav@0" \
  "Chords=midi|chords:C,Am,F,G7:4:96"
```

*(Note: `newsong` covers tracks, folders, clips, MIDI, tempo/meter/keysig, markers, and groups in one call; for busses, sends, fades, plug-ins, and automation lanes use Option A `buildspec` or Option C below.)*

### Option C — Incremental Modular Build (`newbase` -> steps)
```bash
OUT=/tmp/ptx_demo_mod
rm -rf "$OUT" && mkdir -p "$OUT/Audio Files"
cp test/CR_max3/"Audio Files"/vox_m.wav "$OUT/Audio Files/"
ptxedit() { python3 tools/ptx_edit.py "$@"; }

ptxedit newbase "$OUT/m00.ptx" rate=48000 bits=24 io=1
ptxedit addbus "$OUT/m00.ptx" "$OUT/m01.ptx" FX stereo=1
ptxedit addtrack4 "$OUT/m01.ptx" "$OUT/m02.ptx" kind=audio name=Lead
ptxedit addtrack4 "$OUT/m02.ptx" "$OUT/m03.ptx" kind=aux stereo=1 name=AuxFX
ptxedit setinput "$OUT/m03.ptx" "$OUT/m04.ptx" AuxFX FX
ptxedit addclip "$OUT/m04.ptx" "$OUT/m05.ptx" Lead "$OUT/Audio Files/vox_m.wav" at=0
ptxedit addsend "$OUT/m05.ptx" "$OUT/m06.ptx" Lead FX level=-6 pan=-30 pre=1
ptxedit addplugin "$OUT/m06.ptx" "$OUT/m07.ptx" Lead a "EQ3 1-Band" param.d_gain=3.0
ptxedit setlane "$OUT/m07.ptx" "$OUT/m08.ptx" Lead volume 0:0,48000:-30 Lead pan 0:-50
```

Run `python3 tools/ptx_edit.py` with no arguments for the CLI command synopsis, or read the top header of [`tools/ptx_edit.py`](tools/ptx_edit.py) for full command syntax and examples.

---

## 5. Bidirectional Conversion (`.ptx <-> .scraft` / `.scraftz`) via `ptxconv`

```bash
(cd scraft-bridge && CARGO_TARGET_DIR=/tmp/ptx-scraft-target cargo test --workspace && CARGO_TARGET_DIR=/tmp/ptx-scraft-target cargo build --release -p ptx-convert-cli)

PTXCONV=/tmp/ptx-scraft-target/release/ptxconv

# Dry-run conversion ledger (JSON summary on stdout, writes no files)
"$PTXCONV" test/CR_max3/CR_max3.ptx --dry-run --report

# Copy the example session folder to scratch before running file conversion round-trips
rm -rf /tmp/CR_max3_demo && cp -R test/CR_max3 /tmp/CR_max3_demo
"$PTXCONV" /tmp/CR_max3_demo/CR_max3.ptx -o /tmp/CR_max3_demo/CR_max3_conv.scraft
"$PTXCONV" /tmp/CR_max3_demo/CR_max3.scraft -o /tmp/CR_max3_demo/CR_max3_rt.ptx
```

### Supported Media & Conversion Fidelity
- Native `.wav` / `.aif` / `.aiff` / `.bwf` media links zero-move relative to `Audio Files/` (on `.scraft -> .ptx`, the Rust `ptxconv` binary decodes compressed `.flac` / `.ogg` (Vorbis) / `.mp3` / `.m4a` (`AAC`/`ALAC`) / `.caf` SoundCraft audio into 24-bit BWF `.wav` in `_converted/` via `craft-audio` + `symphonia` — no `ffmpeg` or external Python packages required).
- Non-PCM containers such as `.mxf` / `.sd2` preserve original filenames and extensions with explicit `Carry` (or `Absent` under `--no-carry`) conversion diagnostics in `.ptx_convert.json`.
- `.scraft` (file), directory bundles (`--sc-format dir`), and `.scraftz` archives (`--sc-format bundle`) are supported; pass `--plugin-config <PATH>` to override the built-in [`plugin_map.json`](scraft-bridge/crates/ptx-scraft/plugin_map.json). For full details, see [`soundcraft-bridge.md`](soundcraft-bridge.md).
