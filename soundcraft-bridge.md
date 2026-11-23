# `scraft-bridge` Documentation

**Version:** 0.7.0 (beta) · **Date:** 2026-11-23

**Clean-room, bidirectional Rust `.ptx` <-> `.scraft` / `.scraftz` (SoundCraft `v0.20.1`) session converter.**

Zero proprietary session templates, `#![forbid(unsafe_code)]`, and workspace-wide `#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]`.

## Workspace Layout

```text
scraft-bridge/
├── Cargo.toml                  # Workspace manifest (Rust 1.95+, edition 2024)
├── Cargo.lock
├── crates/ptx-format/          # Standalone clean-room .ptx codec (decode/ + encode/)
│   ├── src/scramble.rs         # 4 KiB page XOR descramble / scramble
│   ├── src/tree.rs             # Bounded 0x5A block tree parser & exact 0x0002 directory builder
│   ├── src/primitives.rs       # OFF12 ticks, FILETIME, UMID, nibble-packed ints, BE/LE helpers, Trim knots
│   ├── src/decode/             # Canonical PtxDocument extractor
│   └── src/encode/             # Clean-room PtxBuildSpec -> .ptx binary builder (17 stock plug-ins)
├── crates/ptx-scraft/          # Bidirectional PTX <-> craft-scraft-format mapper + ledger + sidecar
│   ├── plugin_map.json         # Embedded default DSP parameter scaling, log tapers & Trim knots
│   ├── src/plugins.rs          # Externalizable DSP mapping, log curve subdivision, EQ7 band-enable composition
│   ├── src/automation.rs       # TempoMap ticks<->samples, SMPTE timecode/rates, fader-taper subdivision, fades
│   ├── src/media.rs            # Zero-move relative Audio Files/ resolver & compressed->24-bit BWF WAV decode
│   ├── src/map_ptx_to_sc.rs    # PtxDocument -> SoundCraft Session + CarrySidecar + ConversionReport
│   ├── src/map_sc_to_ptx.rs    # SoundCraft Session (+ CarrySidecar) -> PtxBuildSpec + ConversionReport
│   └── src/report.rs           # <stem>.ptx_convert.json ledger & <stem>.ptxcarry.json sidecar
└── apps/ptx-convert-cli/       # Standalone drop-in CLI (`ptxconv`)
```

## Plug-in Automation & Scaling Configuration

All continuous plug-in parameter ranges, tapers (`linear`, `log`, `toggle`), `EQ3 7-Band` asymmetric gain `0 dB` pivots (`zero_db_norm = 0.769231`), and Pro Tools `Trim` piecewise curve knots are externalized in JSON:

- **Default embedded config:** [`plugin_map.json`](scraft-bridge/crates/ptx-scraft/plugin_map.json) (`version: 1`, compiled in via `include_str!("../plugin_map.json")`, covering `eq_1band`, `eq_7band`, `compressor`, `expander_gate`, `de_esser`, `maximizer`, `channel_strip`, `auto_pan`, `trim`, `time_shift`, `room_reverb`, `plate_reverb`, `mod_delay`, `lofi`, plus `trim_knots`).
- **Runtime override:** pass `--plugin-config <PATH>` on the `ptxconv` CLI (or `ConvertOptions::plugin_config` in Rust) to load custom ranges/tapers without recompiling.
- **Curve subdivision & Pro Tools parity logic:** [`plugins.rs`](scraft-bridge/crates/ptx-scraft/src/plugins.rs) (`load_plugin_config`, `pt_norm_to_phys_with`, `sc_phys_to_pt_norm_with`, `ParamTaper::Log` bidirectional curve subdivision `<= 0.5%`, and `EQ3 7-Band` dynamic `l_in 2..6` enable composition into `*_gain`).
- **Pro Tools binary AAX stock chunks & `Trim` curve knots:** [`plugins_data.rs`](scraft-bridge/crates/ptx-format/src/encode/plugins_data.rs) (`STOCK_PLUGINS`, `default_elck_list`, `default_all_values`, `trim_db_to_norm`) and [`plugins.rs`](scraft-bridge/crates/ptx-format/src/decode/plugins.rs) (`trim_norm_to_db`, `All ` / `MD_3` / `PiII` / `elck` decoders).
- **Fader taper curve subdivision:** [`automation.rs`](scraft-bridge/crates/ptx-scraft/src/automation.rs) (`VOLUME_CURVE_TOLERANCE_DB = 0.05`, using `craft_scraft_format::{fader_db_to_pos, fader_pos_to_db}`).

## Building & Running `ptxconv`

> Pass `CARGO_TARGET_DIR=/tmp/ptx-scraft-target` if building inside a cloud-synced folder so build outputs stay outside synced storage.

```bash
cd scraft-bridge

# 1. Run unit & round-trip tests + strict clippy lints
CARGO_TARGET_DIR=/tmp/ptx-scraft-target cargo test --workspace
CARGO_TARGET_DIR=/tmp/ptx-scraft-target cargo clippy --workspace --all-targets -- -D warnings

# 2. Build the standalone CLI
CARGO_TARGET_DIR=/tmp/ptx-scraft-target cargo build --release -p ptx-convert-cli
PTXCONV=/tmp/ptx-scraft-target/release/ptxconv

# 3. Inspect or convert test/CR_max/CR_max.ptx <-> .scraft (from the kit root on a scratch copy)
cd ..
"$PTXCONV" test/CR_max/CR_max.ptx --dry-run --report
rm -rf /tmp/CR_max_sc && cp -R test/CR_max /tmp/CR_max_sc
"$PTXCONV" /tmp/CR_max_sc/CR_max.ptx -o /tmp/CR_max_sc/CR_max_conv.scraft
"$PTXCONV" /tmp/CR_max_sc/CR_max.scraft -o /tmp/CR_max_sc/CR_max_rt.ptx

# Optional flags:
#   --sc-format file|dir|bundle   (.scraft file, project folder, or .scraftz ZIP)
#   --media relative|copy|link    (default: zero-move relative)
#   --loop-handling faithful|flatten
#   --strict                      (fail if any item is Carry or Absent)
#   --no-carry                    (skip <stem>.ptxcarry.json sidecar)
#   --plugin-config <PATH>        (override embedded scraft-bridge/crates/ptx-scraft/plugin_map.json)
```

## Supported Features

- **`.ptx` codec (`ptx-format`):** Reads/writes `type 1` & `type 5` `.ptx` binaries cleanly (`0x0002` byte-identical directory, `17` stock plug-in builders, MIDI `0x2000`/`0x1057`, audio clips/regions/fades/crossfades/sync points/clip groups/loops/clip gain, `user_delay`, pull codes, `EditState`, SMPTE timecode/rates, memory locations, and `.mxf`/`.sd2` stem/extension detection).
- **SoundCraft mapper (`ptx-scraft`):** Bidirectional `.ptx <-> .scraft`/`.scraftz` mapping with relative zero-move `Audio Files/` resolution, compressed audio decoding to 24-bit BWF `.wav`, fader-taper & log-frequency curve subdivision, dynamic 7-band EQ enable composition, externalizable [`plugin_map.json`](scraft-bridge/crates/ptx-scraft/plugin_map.json) (`--plugin-config`), `.ptxcarry.json` sidecar, and `.ptx_convert.json` ledger (`--dry-run --report`, `--strict`, `--no-carry`).

See also [`README.md`](README.md) and [`getting_started.md`](getting_started.md).
