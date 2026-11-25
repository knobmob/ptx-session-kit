// Version: 0.7.0 (beta) | Date: 2026-11-23
//! Bidirectional clean-room `.ptx` <-> `.scraft` (SoundCraft `v0.20.1`) converter and ledger.
#![deny(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::unimplemented,
    clippy::todo,
    clippy::unreachable
)]

pub mod automation;
pub mod error;
pub mod map_ptx_to_sc;
pub mod map_sc_to_ptx;
pub mod media;
pub mod plugins;
pub mod report;

use std::fs;
use std::path::{Path, PathBuf};

use craft_scraft_format::{
    BUNDLE_EXTENSION, DEFAULT_BUNDLE_LIMITS, MAX_SESSION_BYTES, Session, read_bundle, write_bundle,
    write_session,
};
use ptx_format::decode::decode_file;
use ptx_format::encode::encode_ptx;

pub use error::ConvertError;
pub use map_ptx_to_sc::ptx_doc_to_scraft;
pub use map_sc_to_ptx::scraft_to_ptx_spec;
pub use media::MediaMode;
pub use report::{CarrySidecar, ConversionReport, Fidelity};

/// Loop handling policy on conversion.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum LoopHandling {
    /// Unroll PT `0x242B` with shared `loop_id`, and coalesce `loop_id` runs back to `0x242B`.
    #[default]
    Faithful,
    /// Flatten loops into independent clip instances without coalescing.
    Flatten,
}

impl LoopHandling {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Faithful => "faithful",
            Self::Flatten => "flatten",
        }
    }
}

/// Output container format for `.ptx -> .scraft`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ScraftFormat {
    /// Directory containing `<stem>.scraft` + relative `Audio Files/` references.
    #[default]
    File,
    /// Folder bundle `<stem>.scraft.dir/<stem>.scraft` (or explicit output folder).
    Dir,
    /// Compressed/stored ZIP `.scraftz` bundle containing audio assets.
    Bundle,
}

/// Conversion options controlling media, loops, sidecar, and strict fidelity checks.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ConvertOptions {
    pub media_mode: MediaMode,
    pub loop_handling: LoopHandling,
    pub strict: bool,
    pub carry: bool,
    pub scraft_format: ScraftFormat,
    /// Optional external `plugin_map.json` override; uses embedded defaults when `None`.
    pub plugin_config: Option<PathBuf>,
}

impl Default for ConvertOptions {
    fn default() -> Self {
        Self {
            media_mode: MediaMode::Relative,
            loop_handling: LoopHandling::Faithful,
            strict: false,
            carry: true,
            scraft_format: ScraftFormat::File,
            plugin_config: None,
        }
    }
}

/// Companion sidecar path `<stem>.ptxcarry.json` next to `target_path`.
#[must_use]
pub fn sidecar_path_for(target_path: &Path) -> PathBuf {
    let dir = target_path.parent().unwrap_or_else(|| Path::new("."));
    let stem = target_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("session");
    dir.join(format!("{stem}.ptxcarry.json"))
}

/// Ledger report path `<stem>.ptx_convert.json` next to `target_path`.
#[must_use]
pub fn report_path_for(target_path: &Path) -> PathBuf {
    let dir = target_path.parent().unwrap_or_else(|| Path::new("."));
    let stem = target_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("session");
    dir.join(format!("{stem}.ptx_convert.json"))
}

/// Convert `.ptx` file on disk -> `.scraft` (or `.scraftz`), optionally writing output + sidecar + report.
///
/// # Errors
/// Returns `ConvertError` on decode, validation, media, or serialization failures.
pub fn convert_ptx_to_scraft_file(
    ptx_path: &Path,
    out_path: &Path,
    opts: &ConvertOptions,
    write_outputs: bool,
) -> Result<(Session, ConversionReport, Option<CarrySidecar>), ConvertError> {
    let doc = decode_file(ptx_path)?;
    let ptx_dir = ptx_path.parent().unwrap_or_else(|| Path::new("."));
    let actual_out = match opts.scraft_format {
        ScraftFormat::Dir => out_path.join(
            ptx_path
                .file_stem()
                .map(|s| format!("{}.scraft", s.to_string_lossy()))
                .unwrap_or_else(|| "session.scraft".to_owned()),
        ),
        ScraftFormat::File | ScraftFormat::Bundle => out_path.to_path_buf(),
    };
    let out_dir = actual_out.parent().unwrap_or_else(|| Path::new("."));

    let (session, mut report, carry) =
        ptx_doc_to_scraft(&doc, ptx_dir, write_outputs.then_some(out_dir), opts)?;
    report.source_path = ptx_path.display().to_string();
    report.target_path = actual_out.display().to_string();

    if write_outputs {
        if let Some(parent) = actual_out.parent()
            && !parent.as_os_str().is_empty()
        {
            fs::create_dir_all(parent)?;
        }
        let is_bundle = opts.scraft_format == ScraftFormat::Bundle
            || actual_out
                .extension()
                .and_then(|e| e.to_str())
                .is_some_and(|e| e.eq_ignore_ascii_case(BUNDLE_EXTENSION));
        if is_bundle {
            let (bundle_bytes, _) = write_bundle(&session, DEFAULT_BUNDLE_LIMITS)
                .map_err(|e| ConvertError::Audio(e.to_string()))?;
            fs::write(&actual_out, bundle_bytes)?;
        } else {
            let text = write_session(&session, MAX_SESSION_BYTES)
                .map_err(|e| ConvertError::Session(craft_scraft_format::SessionError::Format(e.to_string())))?;
            fs::write(&actual_out, text)?;
        }
        if let Some(ref c) = carry {
            c.write_to(&sidecar_path_for(&actual_out))?;
        }
        report.write_to(&report_path_for(&actual_out))?;
    }

    Ok((session, report, carry))
}

/// Convert `.scraft` (or `.scraftz`) file on disk -> `.ptx`, optionally writing `.ptx` and `.ptx_convert.json`.
///
/// # Errors
/// Returns `ConvertError` on load, strict loss refusal, encode, or write failures.
pub fn convert_scraft_to_ptx_file(
    scraft_path: &Path,
    out_ptx: &Path,
    opts: &ConvertOptions,
    write_outputs: bool,
) -> Result<(Vec<u8>, ConversionReport), ConvertError> {
    let is_bundle = scraft_path
        .extension()
        .and_then(|e| e.to_str())
        .is_some_and(|e| e.eq_ignore_ascii_case(BUNDLE_EXTENSION));
    let session = if is_bundle {
        let raw = fs::read(scraft_path)?;
        let (json_text, _) = read_bundle(&raw, DEFAULT_BUNDLE_LIMITS)
            .map_err(|e| ConvertError::Audio(e.to_string()))?;
        Session::from_json(&json_text)?
    } else {
        let text = fs::read_to_string(scraft_path)?;
        Session::from_json(&text)?
    };

    let scraft_dir = scraft_path.parent().unwrap_or_else(|| Path::new("."));
    let out_dir = out_ptx.parent().unwrap_or_else(|| Path::new("."));
    let carry = if opts.carry {
        CarrySidecar::load_if_exists(&sidecar_path_for(scraft_path))?
    } else {
        None
    };

    let (spec, mut report) =
        scraft_to_ptx_spec(&session, scraft_dir, Some(out_dir), carry.as_ref(), opts)?;
    report.source_path = scraft_path.display().to_string();
    report.target_path = out_ptx.display().to_string();

    let ptx_bytes = encode_ptx(&spec)?;

    if write_outputs {
        if let Some(parent) = out_ptx.parent()
            && !parent.as_os_str().is_empty()
        {
            fs::create_dir_all(parent)?;
        }
        fs::write(out_ptx, &ptx_bytes)?;
        report.write_to(&report_path_for(out_ptx))?;
    }

    Ok((ptx_bytes, report))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    use craft_scraft_format::{AutoParam, fader_db_to_pos, fader_pos_to_db};
    use craft_scraft_format::soundcraft_time::SampleRate;
    use ptx_format::decode::decode_bytes;
    use ptx_format::encode::spec::{
        BuildAudioClip, BuildAudioFile, BuildBus, BuildClipLoop, BuildFade, BuildFadeKind,
        BuildFadeSlope, BuildGroup, BuildInsert, BuildInsertAutoLane, BuildKeySig, BuildMarker,
        BuildMeterPoint, BuildMidiClip, BuildMidiCtrl, BuildMidiNote, BuildParamVal, BuildSend,
        BuildTempoPoint, BuildTimebase, BuildTrack, BuildTrackKind, PtxBuildSpec,
    };

    #[test]
    fn fader_taper_subdivision_matches_pt_ramp_within_0_06_db() {
        let sr = SampleRate::HZ_48000;
        let tempo = craft_scraft_format::soundcraft_time::TempoMap::default();
        let lane = automation::ptx_lane_to_sc(
            AutoParam::Volume,
            &[(0, -1440), (48_000, 0)],
            false,
            &tempo,
            sr,
            true,
        );
        // Should subdivide across the non-linear knee below -24 dB
        assert!(lane.points.len() > 8);
        let mid_t = 24_000i64;
        let p_mid = 0.5 * (fader_db_to_pos(-144.0) + fader_db_to_pos(0.0));
        let expected_db = fader_pos_to_db(p_mid);
        let got_db = lane.value_at(mid_t, 0.0);
        assert!(
            (expected_db - got_db).abs() <= 0.06,
            "expected={expected_db} got={got_db}"
        );
    }

    #[test]
    fn bidirectional_fixpoint_roundtrip_ptx_sc_ptx_sc() -> Result<(), ConvertError> {
        let mut params_eq1 = BTreeMap::new();
        params_eq1.insert("d_gain".to_owned(), BuildParamVal::Float(3.5));
        params_eq1.insert("d_ctrf".to_owned(), BuildParamVal::Float(1250.0));

        let mut params_trim = BTreeMap::new();
        params_trim.insert("gain_db".to_owned(), BuildParamVal::Float(-3.0));
        params_trim.insert("phase_invert".to_owned(), BuildParamVal::Bool(true));

        let spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            is_float: false,
            is_aiff: false,
            tempo: vec![
                BuildTempoPoint { ticks: 0, bpm: 120.0 },
                BuildTempoPoint { ticks: 3_840_000, bpm: 95.0 },
            ],
            meter: vec![
                BuildMeterPoint { ticks: 0, bar: 1, numerator: 4, denominator: 4 },
                BuildMeterPoint { ticks: 3_840_000, bar: 2, numerator: 3, denominator: 4 },
            ],
            key_signatures: vec![
                BuildKeySig { ticks: 0, major: true, sharps: 0 },
                BuildKeySig { ticks: 3_840_000, major: false, sharps: 0 },
            ],
            markers: vec![BuildMarker {
                number: 1,
                name: "Chorus".to_owned(),
                start: 3_840_000,
                end: 3_840_000,
                is_ticks: true,
                is_selection: false,
                comment: "Hook".to_owned(),
            }],
            busses: vec![BuildBus { name: "FX1".to_owned(), stereo: true }],
            audio_files: vec![BuildAudioFile {
                file_name: "tone.wav".to_owned(),
                sample_rate: 48_000,
                channels: 1,
                bit_depth: 24,
                is_float: false,
                is_aiff: false,
                frames: 48_000,
                data_offset: 44,
                filetime: 133_000_000_000_000_000,
                umid_file_id: None,
            }],
            groups: vec![BuildGroup {
                name: "VoxGrp".to_owned(),
                group_type: 2,
                enabled: true,
                member_track_names: vec!["Vox".to_owned()],
            }],
            tracks: vec![
                BuildTrack {
                    name: "FoldB".to_owned(),
                    kind: BuildTrackKind::BasicFolder,
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "Vox".to_owned(),
                    kind: BuildTrackKind::Audio,
                    folder_name: Some("FoldB".to_owned()),
                    volume_tenths_db: -35,
                    solo: true,
                    comment: "Lead".to_owned(),
                    colour: Some(33),
                    inserts: vec![
                        BuildInsert {
                            slot_index: 0,
                            plugin_name: "EQ3 1-Band".to_owned(),
                            bypass: false,
                            active: true,
                            multi_mono: false,
                            params: params_eq1,
                            automation: vec![BuildInsertAutoLane {
                                param_name: "Gain".to_owned(),
                                param_id: "gain".to_owned(),
                                param_index: 1,
                                points: vec![(0, 0.5), (48_000, 0.75)],
                            }],
                        },
                        BuildInsert {
                            slot_index: 1,
                            plugin_name: "Trim".to_owned(),
                            bypass: false,
                            active: true,
                            multi_mono: false,
                            params: params_trim,
                            automation: vec![],
                        },
                    ],
                    sends: vec![BuildSend {
                        slot_index: 0,
                        bus_name: "FX1".to_owned(),
                        level_tenths_db: -60,
                        pan: -25,
                        mute: false,
                        pre_fader: true,
                        active: true,
                        ..BuildSend::default()
                    }],
                    audio_clips: vec![BuildAudioClip {
                        name: "tone".to_owned(),
                        file_indices: vec![0],
                        file_offset: 0,
                        length_samples: 48_000,
                        start_pos: 24_000,
                        pos_in_ticks: false,
                        muted: false,
                        sync_offset: None,
                        clip_gain_points: vec![(0, -4.5)],
                        fade_in: Some(BuildFade {
                            kind: BuildFadeKind::FadeIn,
                            slope: BuildFadeSlope::EqualPower,
                            length_samples: 2400,
                            pre_roll_samples: None,
                        }),
                        fade_out: None,
                        clip_loop: Some(BuildClipLoop {
                            mode: 2,
                            bars: 0,
                            beats: 0,
                            ticks: 0,
                            count: 3,
                            trim: 0,
                            iter: 48_000,
                            is_ticks: false,
                        }),
                        group: None,
                    }],
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "Keys".to_owned(),
                    kind: BuildTrackKind::Midi,
                    timebase: BuildTimebase::Ticks,
                    midi_clips: vec![BuildMidiClip {
                        name: "Keys-01".to_owned(),
                        start_pos: 0,
                        pos_in_ticks: true,
                        length_ticks: 3_840_000,
                        notes: vec![BuildMidiNote {
                            start_ticks: 0,
                            key: 60,
                            length_ticks: 960_000,
                            velocity: 100,
                        }],
                        controllers: vec![BuildMidiCtrl {
                            kind: 2,
                            number: 1,
                            points: vec![(0, 64), (960_000, 127)],
                        }],
                        sysex: vec![(0, vec![0x7e, 0x7f, 0x09, 0x01])],
                        muted: false,
                        clip_loop: None,
                    }],
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "Verb".to_owned(),
                    kind: BuildTrackKind::Aux,
                    stereo: true,
                    input_bus: Some("FX1".to_owned()),
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "Master".to_owned(),
                    kind: BuildTrackKind::Master,
                    stereo: true,
                    ..BuildTrack::default()
                },
            ],
            ..PtxBuildSpec::default()
        };

        let opts = ConvertOptions::default();
        let ptx_raw1 = encode_ptx(&spec)?;
        let doc1 = decode_bytes("roundtrip.ptx", &ptx_raw1)?;
        let (sc1, rep1, carry1) = ptx_doc_to_scraft(&doc1, Path::new("."), None, &opts)?;
        assert_eq!(sc1.tracks.len(), 5);
        assert_eq!(sc1.key_signatures.len(), 2);
        assert_eq!(sc1.markers.len(), 1);
        assert_eq!(sc1.groups.len(), 1);
        // Loop count=3 was unrolled cleanly on Vox playlist with shared loop_id
        assert_eq!(sc1.tracks[1].playlists[0].clips.len(), 3);
        assert!(sc1.tracks[1].playlists[0].clips[0].loop_id.is_some());
        assert_eq!(rep1.summary.absent, 0);

        // JSON serialization & deserialization via SoundCraft's real `Session::from_json`
        let sc_json = craft_scraft_format::write_session(&sc1, craft_scraft_format::MAX_SESSION_BYTES)
            .map_err(|e| ConvertError::Audio(e.to_string()))?;
        let sc1_parsed = Session::from_json(&sc_json)?;

        // SC1 -> PTX2
        let (spec2, _rep2) =
            scraft_to_ptx_spec(&sc1_parsed, Path::new("."), None, carry1.as_ref(), &opts)?;
        assert_eq!(spec2.tracks.len(), 5);
        // BasicFolder kind preserved via carry
        assert_eq!(spec2.tracks[0].kind, BuildTrackKind::BasicFolder);
        // Contiguous loop_id run coalesced back into 1 clip with count=3!
        assert_eq!(spec2.tracks[1].audio_clips.len(), 1);
        assert_eq!(spec2.tracks[1].audio_clips[0].clip_loop.as_ref().map(|l| l.count), Some(3));

        let ptx_raw2 = encode_ptx(&spec2)?;
        let doc2 = decode_bytes("roundtrip2.ptx", &ptx_raw2)?;
        let (sc2, _rep3, _carry2) = ptx_doc_to_scraft(&doc2, Path::new("."), None, &opts)?;
        // Fixpoint: track count, clips, notes, key signatures, markers match sc1 == sc2
        assert_eq!(sc2.tracks.len(), sc1.tracks.len());
        assert_eq!(sc2.tracks[1].playlists[0].clips.len(), 3);
        assert_eq!(sc2.key_signatures, sc1.key_signatures);
        assert_eq!(sc2.markers.len(), sc1.markers.len());
        assert_eq!(sc2.groups.len(), sc1.groups.len());
        Ok(())
    }

    #[test]
    fn embedded_plugin_map_parses_all_plugins_and_trim_knots() {
        let cfg = plugins::default_config();
        assert_eq!(cfg.version, 1);
        assert_eq!(cfg.params.len(), 14);
        assert_eq!(cfg.trim_knots.len(), 6);
        let gain_20k = plugins::pt_norm_to_phys_with(cfg, "eq_1band", "freq", 0.5);
        assert!((gain_20k - (20.0_f64 * 20_000.0).sqrt()).abs() < 0.05);
        let inpt_0db = plugins::pt_norm_to_phys_with(cfg, "eq_7band", "input_gain", 0.769_231);
        assert!(inpt_0db.abs() < 1e-4);
    }

    #[test]
    fn log_frequency_plugin_ramp_subdivides_within_half_percent() -> Result<(), ConvertError> {
        let cfg = plugins::default_config();
        let sr = SampleRate::HZ_48000;
        let tempo = craft_scraft_format::soundcraft_time::TempoMap::default();
        let mut pt_ins = ptx_format::decode::plugins::Insert {
            slot: serde_json::json!(0),
            name: "EQ3 1-Band".to_owned(),
            plugin: Some("EQ3 1-Band".to_owned()),
            vendor_id: "com.digidesign.aax.eq3.1band".to_owned(),
            ids: None,
            state_format: None,
            active: Some(true),
            bypass: Some(false),
            multi_mono: false,
            params: BTreeMap::new(),
            values: None,
            values_i32: None,
            table_index: None,
            settings_index: None,
            settings_file: None,
            preset: None,
            stock: true,
            automation_params: Some(vec![[Some("Freq".to_owned()), Some("ctrf".to_owned())]]),
            automation: vec![vec![(0, 0.0), (48_000, 1.0)]],
        };
        pt_ins.params.insert("l_type".to_owned(), serde_json::json!(3));

        let mut rep = ConversionReport::new("t", "a", "b", "relative", "faithful");
        let (sc_ins_opt, auto_lanes, _) = plugins::ptx_insert_to_sc(
            &plugins::PtxInsertToScArgs {
                slot_idx: 0,
                ins: &pt_ins,
                track_name: "Audio 1",
                track_is_ticks: false,
                tempo: &tempo,
                sr,
                plugin_cfg: cfg,
            },
            &mut rep,
        );
        let sc_ins = sc_ins_opt.ok_or_else(|| ConvertError::Audio("missing eq_1band".to_owned()))?;
        assert_eq!(auto_lanes.len(), 1);
        assert!(auto_lanes[0].points.len() > 8, "expected subdivided log points, got {}", auto_lanes[0].points.len());
        let mid_hz = auto_lanes[0].value_at(24_000, 100.0);
        let true_mid = (20.0_f32 * 20_000.0_f32).sqrt();
        let rel_err = (mid_hz - true_mid).abs() / true_mid;
        assert!(rel_err <= 0.005, "PT->SC rel_err={rel_err} mid_hz={mid_hz}");

        // SC -> PTX linear-Hz sweep must also subdivide normalized curve within 0.5%
        let mut sc_lane = craft_scraft_format::AutomationLane::new(AutoParam::Plugin {
            slot: 0,
            param: "freq".to_owned(),
        });
        sc_lane.set_point(0, 20.0);
        sc_lane.set_point(48_000, 20_000.0);
        let bi = plugins::sc_insert_to_ptx(
            &plugins::ScInsertToPtxArgs {
                slot_idx: 0,
                ins: &sc_ins,
                track_name: "Audio 1",
                track_auto: &[sc_lane],
                tempo: &tempo,
                sr,
                to_ticks: false,
                carry_opt: None,
                plugin_cfg: cfg,
            },
            &mut rep,
        )
        .ok_or_else(|| ConvertError::Audio("missing reverse BuildInsert".to_owned()))?;
        assert!(bi.automation[0].points.len() > 8);
        // Check normalized midpoint u(24000) maps back to ~10010 Hz
        let pts = &bi.automation[0].points;
        let mid_pt = pts.iter().find(|(t, _)| *t == 24_000).ok_or_else(|| ConvertError::Audio("missing t=24000".to_owned()))?;
        let recon_hz = plugins::pt_norm_to_phys_with(cfg, "eq_1band", "freq", mid_pt.1);
        let sc_lin_mid = 10_010.0_f64;
        let rev_err = (recon_hz - sc_lin_mid).abs() / sc_lin_mid;
        assert!(rev_err <= 0.005, "SC->PT rev_err={rev_err} recon_hz={recon_hz}");
        Ok(())
    }

    #[test]
    fn eq7_dynamic_band_enable_composes_into_gain() -> Result<(), ConvertError> {
        let cfg = plugins::default_config();
        let sr = SampleRate::HZ_48000;
        let tempo = craft_scraft_format::soundcraft_time::TempoMap::default();
        let mut pt_ins = ptx_format::decode::plugins::Insert {
            slot: serde_json::json!(0),
            name: "EQ3 7-Band".to_owned(),
            plugin: Some("EQ3 7-Band".to_owned()),
            vendor_id: "com.digidesign.aax.eq3.7band".to_owned(),
            ids: None,
            state_format: None,
            active: Some(true),
            bypass: Some(false),
            multi_mono: false,
            params: BTreeMap::new(),
            values: None,
            values_i32: None,
            table_index: None,
            settings_index: None,
            settings_file: None,
            preset: None,
            stock: true,
            automation_params: Some(vec![[Some("MF In".to_owned()), Some("in 4".to_owned())]]),
            automation: vec![vec![(0, 0.0), (48_000, 1.0), (96_000, 0.0)]],
        };
        pt_ins.params.insert("l_in 4".to_owned(), serde_json::json!(0));
        pt_ins.params.insert("d_gai4".to_owned(), serde_json::json!(6.0));

        let mut rep = ConversionReport::new("t", "a", "b", "relative", "faithful");
        let (_, auto_lanes, _) = plugins::ptx_insert_to_sc(
            &plugins::PtxInsertToScArgs {
                slot_idx: 0,
                ins: &pt_ins,
                track_name: "Audio 1",
                track_is_ticks: false,
                tempo: &tempo,
                sr,
                plugin_cfg: cfg,
            },
            &mut rep,
        );
        let mid_gain_lane = auto_lanes
            .iter()
            .find(|l| matches!(&l.param, AutoParam::Plugin { slot: 0, param } if param == "mid_gain"))
            .ok_or_else(|| ConvertError::Audio("missing composed mid_gain lane".to_owned()))?;
        assert!(mid_gain_lane.value_at(0, 99.0).abs() < 1e-4);
        assert!(mid_gain_lane.value_at(47_999, 99.0).abs() < 1e-4);
        assert!((mid_gain_lane.value_at(48_000, 0.0) - 6.0).abs() < 1e-4);
        assert!((mid_gain_lane.value_at(95_999, 0.0) - 6.0).abs() < 1e-4);
        assert!(mid_gain_lane.value_at(96_000, 99.0).abs() < 1e-4);
        Ok(())
    }

    #[test]
    fn frame_rate_and_timecode_start_roundtrip_ptx_sc_ptx() -> Result<(), ConvertError> {
        let spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            tc_rate_code: Some(2), // 25 fps
            tc_start: Some("01:00:05:10".to_owned()),
            ..PtxBuildSpec::default()
        };
        let ptx_raw1 = encode_ptx(&spec)?;
        let doc1 = decode_bytes("tc_rt1.ptx", &ptx_raw1)?;
        let opts = ConvertOptions::default();
        let (sc1, _, carry1) = ptx_doc_to_scraft(&doc1, Path::new("."), None, &opts)?;
        assert_eq!(
            sc1.frame_rate,
            craft_scraft_format::soundcraft_time::FrameRate::Fps25
        );
        assert_eq!(sc1.timecode_start, (3605 * 25 + 10) * 48_000 / 25);

        let (spec2, _) = scraft_to_ptx_spec(&sc1, Path::new("."), None, carry1.as_ref(), &opts)?;
        let ptx_raw2 = encode_ptx(&spec2)?;
        let doc2 = decode_bytes("tc_rt2.ptx", &ptx_raw2)?;
        assert_eq!(doc2.timeline.timecode_rate_code, Some(2));
        assert_eq!(doc2.timeline.session_start.as_deref(), Some("01:00:05:10"));
        Ok(())
    }

    #[test]
    fn compressed_flac_decodes_to_24bit_bwf_wav_on_sc_to_ptx() -> Result<(), ConvertError> {
        let mut buf = craft_audio::AudioBuffer::new(48_000, 1, 2400);
        for (i, sample) in buf.channels[0].iter_mut().enumerate() {
            *sample = 0.25 * (2.0 * std::f32::consts::PI * 440.0 * (i as f32) / 48_000.0).sin();
        }
        let flac_bytes = craft_audio::encode(
            &buf,
            &craft_audio::EncodeOptions::new(craft_audio::EncodeFormat::Flac),
        )
        .map_err(|e| ConvertError::Audio(e.to_string()))?;

        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_or(0, |d| d.as_nanos());
        let tmp = std::env::temp_dir().join(format!("ptx_scraft_flac_{nanos}"));
        let af_dir = tmp.join("Audio Files");
        fs::create_dir_all(&af_dir)?;
        let flac_path = af_dir.join("synth.flac");
        fs::write(&flac_path, &flac_bytes)?;

        let mut session = Session::new("FlacTest", SampleRate::HZ_48000);
        session.sources.push(craft_scraft_format::Source {
            id: craft_scraft_format::SourceId(1),
            name: "synth".to_owned(),
            path: "Audio Files/synth.flac".to_owned(),
            channels: 1,
            frames: 2400,
            sample_rate: 48_000,
            format: craft_scraft_format::FileFormat::Flac,
            time_reference: 48_000,
            unsaved: false,
        });
        let out_dir = tmp.join("ptx_out");
        fs::create_dir_all(&out_dir)?;
        let (spec, rep) =
            scraft_to_ptx_spec(&session, &tmp, Some(&out_dir), None, &ConvertOptions::default())?;
        assert_eq!(spec.audio_files.len(), 1);
        assert_eq!(spec.audio_files[0].bit_depth, 24);
        assert!(!spec.audio_files[0].is_aiff);
        assert!(out_dir.join("Audio Files/_converted/synth.wav").is_file());
        let insp = media::inspect_audio_file(&out_dir.join("Audio Files/_converted/synth.wav"))?;
        assert_eq!(insp.time_reference, 48_000);
        assert_eq!(insp.bit_depth, 24);
        assert!(rep.summary.approx >= 1);
        let _ = fs::remove_dir_all(&tmp);
        Ok(())
    }

    #[test]
    fn roundtrip_pan2_sendpan_and_monobus() -> Result<(), ConvertError> {
        use ptx_format::encode::spec::BuildAutoLane;
        let spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            busses: vec![
                BuildBus { name: "MBus".to_owned(), stereo: false },
                BuildBus { name: "StBus".to_owned(), stereo: true },
            ],
            tracks: vec![
                BuildTrack {
                    name: "StTrack".to_owned(),
                    kind: BuildTrackKind::Audio,
                    stereo: true,
                    pan: vec![-25, -50],
                    pan_lanes: vec![
                        BuildAutoLane { points: vec![(0, -25), (48_000, 75)] },
                        BuildAutoLane { points: vec![(0, -50), (48_000, 25)] },
                    ],
                    output_bus: Some("MBus".to_owned()),
                    sends: vec![BuildSend {
                        slot_index: 0,
                        bus_name: "StBus".to_owned(),
                        level_tenths_db: 0,
                        pan: -100,
                        pan_points: vec![(0, -100), (48_000, 100)],
                        pre_fader: true,
                        active: true,
                        ..BuildSend::default()
                    }],
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "AuxM".to_owned(),
                    kind: BuildTrackKind::Aux,
                    stereo: false,
                    input_bus: Some("MBus".to_owned()),
                    output_bus: Some("Out 1-2".to_owned()),
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "AuxS".to_owned(),
                    kind: BuildTrackKind::Aux,
                    stereo: true,
                    input_bus: Some("StBus".to_owned()),
                    output_bus: Some("Out 1-2".to_owned()),
                    ..BuildTrack::default()
                },
            ],
            ..PtxBuildSpec::default()
        };
        let bytes1 = encode_ptx(&spec)?;
        let doc1 = decode_bytes("t1.ptx", &bytes1)?;
        let (sc, _, _) = ptx_doc_to_scraft(&doc1, Path::new("."), None, &ConvertOptions::default())?;
        let mbus = sc
            .busses
            .iter()
            .find(|b| b.name == "MBus")
            .ok_or_else(|| ConvertError::Audio("MBus missing".to_owned()))?;
        assert_eq!(mbus.format, craft_scraft_format::ChannelFormat::Mono);
        let st_sc = &sc.tracks[0];
        assert!((st_sc.mixer.pan[0] + 0.25).abs() < 0.02);
        assert!((st_sc.mixer.pan[1] + 0.50).abs() < 0.02);
        assert!(st_sc.automation.iter().any(|l| l.param == AutoParam::Pan(1) && l.points.len() == 2));
        assert!(st_sc.automation.iter().any(|l| l.param == AutoParam::SendPan(0) && l.points.len() == 2));

        let (spec2, _) = scraft_to_ptx_spec(&sc, Path::new("."), None, None, &ConvertOptions::default())?;
        let bytes2 = encode_ptx(&spec2)?;
        let doc2 = decode_bytes("t2.ptx", &bytes2)?;
        assert_eq!(doc2.strips[0].pan2, vec![(0, -50), (48_000, 25)]);
        assert_eq!(doc2.strips[0].sends.as_deref().unwrap_or(&[])[0].pan, vec![(0, -100), (48_000, 100)]);
        assert_eq!(doc2.strips[0].stem_index, Some(0));
        Ok(())
    }

    #[test]
    fn native_fade_out_crossfade_dropframe_and_basicfolder() -> Result<(), ConvertError> {
        use ptx_format::encode::spec::{BuildAudioClip, BuildAudioFile, BuildFade, BuildFadeKind, BuildFadeSlope};

        // 1) Drop-frame parse_tc_to_samples <-> samples_to_tc_string exact inverse + unmapped Drop carry
        let sr = craft_scraft_format::soundcraft_time::SampleRate::HZ_48000;
        let fr29d = craft_scraft_format::soundcraft_time::FrameRate::Fps29_97Drop;
        let smp = automation::parse_tc_to_samples("01:00:00;00", fr29d, sr);
        assert_eq!(automation::samples_to_tc_string(smp, fr29d, sr), "01:00:00;00");

        let spec_df = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            tc_rate_code: Some(8), // 30 Drop
            tc_start: Some("01:00:00;00".to_owned()),
            tracks: vec![BuildTrack {
                name: "BF".to_owned(),
                kind: BuildTrackKind::BasicFolder,
                ..BuildTrack::default()
            }],
            ..PtxBuildSpec::default()
        };
        let raw_df = encode_ptx(&spec_df)?;
        let doc_df = decode_bytes("df30.ptx", &raw_df)?;
        let (sc_df, rep_df, carry_df) = ptx_doc_to_scraft(&doc_df, Path::new("."), None, &ConvertOptions::default())?;
        assert!(rep_df.summary.approx >= 1);
        let (spec_df2, _) = scraft_to_ptx_spec(&sc_df, Path::new("."), None, carry_df.as_ref(), &ConvertOptions::default())?;
        assert_eq!(spec_df2.tc_rate_code, Some(8));
        // Without carry, BasicFolder (Route::None/None) still maps back to BasicFolder
        let (spec_nocarry, _) = scraft_to_ptx_spec(&sc_df, Path::new("."), None, None, &ConvertOptions::default())?;
        assert_eq!(spec_nocarry.tracks[0].kind, BuildTrackKind::BasicFolder);

        // 2) Native fade_out anchored at clip_end + centered 34 B crossfade (v1=120, v2=240)
        let base_spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            audio_files: vec![BuildAudioFile {
                file_name: "a.wav".to_owned(),
                data_offset: 0,
                channels: 1,
                sample_rate: 48_000,
                bit_depth: 24,
                is_aiff: false,
                is_float: false,
                frames: 200_000,
                filetime: 133_000_000_000_000_000,
                umid_file_id: None,
            }],
            tracks: vec![BuildTrack {
                name: "A".to_owned(),
                kind: BuildTrackKind::Audio,
                audio_clips: vec![
                    BuildAudioClip {
                        name: "c1".to_owned(),
                        file_indices: vec![0],
                        file_offset: 0,
                        length_samples: 48_000,
                        start_pos: 0,
                        pos_in_ticks: false,
                        muted: false,
                        sync_offset: None,
                        clip_gain_points: Vec::new(),
                        fade_in: None,
                        fade_out: Some(BuildFade {
                            kind: BuildFadeKind::FadeOut,
                            slope: BuildFadeSlope::EqualPower,
                            length_samples: 1000,
                            pre_roll_samples: None,
                        }),
                        clip_loop: None,
                        group: None,
                    },
                    BuildAudioClip {
                        name: "c2".to_owned(),
                        file_indices: vec![0],
                        file_offset: 0,
                        length_samples: 48_000,
                        start_pos: 100_000,
                        pos_in_ticks: false,
                        muted: false,
                        sync_offset: None,
                        clip_gain_points: Vec::new(),
                        fade_in: Some(BuildFade {
                            kind: BuildFadeKind::Crossfade,
                            slope: BuildFadeSlope::EqualGain,
                            length_samples: 240,
                            pre_roll_samples: None,
                        }),
                        fade_out: None,
                        clip_loop: None,
                        group: None,
                    },
                ],
                ..BuildTrack::default()
            }],
            ..PtxBuildSpec::default()
        };
        let mut doc_f = decode_bytes("fades.ptx", &encode_ptx(&base_spec)?)?;
        // Shift clip 1's fade_out to native clip_end (48_000) and turn clip 2's crossfade into 34B centered (v1=120, v2=240)
        for p in doc_f.audio_playlists.iter_mut().flat_map(|(_, pls)| pls.iter_mut()) {
            if p.kind.as_str() == Some("fade") && p.index == 0 {
                p.samples = Some(48_000);
            } else if p.kind.as_str() == Some("fade") && p.index == 1 {
                p.samples = Some(99_880);
            }
        }
        doc_f.fades[1].size = 34;
        doc_f.fades[1].length = 120;
        doc_f.fades[1].length2 = Some(240);
        let (sc_f, _, _) = ptx_doc_to_scraft(&doc_f, Path::new("."), None, &ConvertOptions::default())?;
        assert_eq!(sc_f.tracks[0].clips()[0].fade_out.len, 1000);
        assert_eq!(sc_f.tracks[0].clips()[1].fade_in.len, 240);
        Ok(())
    }

    #[test]
    fn tier1_sync_crossfade_user_delay_edit_pull_lfe_and_clip_group_roundtrip() -> Result<(), ConvertError> {
        use ptx_format::encode::spec::{
            BuildAudioClip, BuildAudioFile, BuildEditState, BuildFade, BuildFadeKind,
            BuildFadeSlope,
        };
        let mut grp_names = std::collections::BTreeMap::new();
        grp_names.insert(5u64, "Grp_Vocals".to_owned());
        let spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            pull_code: Some(12011), // +0.1%
            edit_state: Some(BuildEditState {
                edit_mode: 0, // Shuffle
                edit_tool: 8, // Pencil
                smart_tool: true,
                loop_playback: true,
                record_mode: 1,
            }),
            clip_group_names: grp_names,
            audio_files: vec![BuildAudioFile {
                file_name: "voc.wav".to_owned(),
                sample_rate: 48_000,
                channels: 1,
                bit_depth: 24,
                is_float: false,
                is_aiff: false,
                frames: 480_000,
                data_offset: 44,
                filetime: 133_000_000_000_000_000,
                umid_file_id: None,
            }],
            tracks: vec![
                BuildTrack {
                    name: "Vox".to_owned(),
                    kind: BuildTrackKind::Audio,
                    user_delay: 137,
                    audio_clips: vec![
                        BuildAudioClip {
                            name: "V1".to_owned(),
                            file_indices: vec![0],
                            file_offset: 0,
                            length_samples: 100_000,
                            start_pos: 0,
                            pos_in_ticks: false,
                            muted: false,
                            sync_offset: Some(10_000),
                            clip_gain_points: Vec::new(),
                            fade_in: None,
                            fade_out: None,
                            clip_loop: None,
                            group: None,
                        },
                        BuildAudioClip {
                            name: "V2".to_owned(),
                            file_indices: vec![0],
                            file_offset: 100_000,
                            length_samples: 100_000,
                            start_pos: 100_000,
                            pos_in_ticks: false,
                            muted: false,
                            sync_offset: Some(15_000),
                            clip_gain_points: Vec::new(),
                            fade_in: Some(BuildFade {
                                kind: BuildFadeKind::Crossfade,
                                slope: BuildFadeSlope::EqualPower,
                                length_samples: 4_800,
                                pre_roll_samples: Some(2_400),
                            }),
                            fade_out: None,
                            clip_loop: None,
                            group: None,
                        },
                    ],
                    ..BuildTrack::default()
                },
                BuildTrack {
                    name: "GrpTrack".to_owned(),
                    kind: BuildTrackKind::Audio,
                    audio_clips: vec![
                        BuildAudioClip {
                            name: "G1".to_owned(),
                            file_indices: vec![0],
                            file_offset: 0,
                            length_samples: 48_000,
                            start_pos: 0,
                            pos_in_ticks: false,
                            muted: false,
                            sync_offset: None,
                            clip_gain_points: Vec::new(),
                            fade_in: None,
                            fade_out: None,
                            clip_loop: None,
                            group: Some(5),
                        },
                        BuildAudioClip {
                            name: "G2".to_owned(),
                            file_indices: vec![0],
                            file_offset: 48_000,
                            length_samples: 48_000,
                            start_pos: 48_000,
                            pos_in_ticks: false,
                            muted: false,
                            sync_offset: None,
                            clip_gain_points: Vec::new(),
                            fade_in: None,
                            fade_out: None,
                            clip_loop: None,
                            group: Some(5),
                        },
                    ],
                    ..BuildTrack::default()
                },
            ],
            ..PtxBuildSpec::default()
        };
        let raw = encode_ptx(&spec)?;
        let mut doc = decode_bytes("tier1.ptx", &raw)?;
        doc.strips[0].lfe_db = Some(-11.2);
        let (sc, rep, carry) = ptx_doc_to_scraft(&doc, Path::new("."), None, &ConvertOptions::default())?;
        assert_eq!(sc.edit.edit_mode, craft_scraft_format::EditMode::Shuffle);
        assert_eq!(sc.edit.tool, craft_scraft_format::Tool::Smart);
        assert!(sc.edit.loop_playback);
        assert!((sc.tracks[0].mixer.surround.as_ref().map_or(-144.0, |s| s.lfe_db) - (-11.2)).abs() < 0.01);
        assert_eq!(sc.tracks[0].clips()[0].sync_point, 10_000);
        assert_eq!(sc.tracks[0].clips()[1].sync_point, 15_000);
        // Without file on disk, clips abut with fade_out/fade_in = 4800
        assert_eq!(sc.tracks[0].clips()[0].fade_out.len, 4_800);
        assert_eq!(sc.tracks[0].clips()[1].fade_in.len, 4_800);
        // ClipGroup expanded into 2 clips sharing a group id
        assert_eq!(sc.tracks[1].clips().len(), 2);
        assert!(sc.tracks[1].clips()[0].group.is_some());
        assert_eq!(sc.tracks[1].clips()[0].group, sc.tracks[1].clips()[1].group);
        assert!(rep.summary.absent == 0);

        // Roundtrip back to PTX with carry AND --no-carry
        for c_opt in [carry.as_ref(), None] {
            let opts = ConvertOptions {
                carry: c_opt.is_some(),
                ..ConvertOptions::default()
            };
            let (spec2, _) = scraft_to_ptx_spec(&sc, Path::new("."), None, c_opt, &opts)?;
            let doc2 = decode_bytes("rt.ptx", &encode_ptx(&spec2)?)?;
            let v1_sync = doc2.regions.iter().find(|r| r.name == "V1").and_then(|r| r.sync_offset);
            let v2_sync = doc2.regions.iter().find(|r| r.name == "V2").and_then(|r| r.sync_offset);
            assert_eq!(v1_sync, Some(10_000));
            assert_eq!(v2_sync, Some(15_000));
            assert!(doc2.fades.iter().any(|f| f.fade_type.as_str() == Some("crossfade") && f.length2 == Some(4_800)));
            assert_eq!(doc2.clip_group_regions.len(), 1);
            if c_opt.is_some() {
                assert_eq!(doc2.tracks[0].user_delay, Some(137));
                assert_eq!(doc2.timeline.pull_code, Some(12011));
                assert_eq!(doc2.clip_group_regions[0].name, "Grp_Vocals");
            }
        }
        Ok(())
    }

    #[test]
    fn mxf_non_pcm_media_emits_carry_diagnostic_and_preserves_extension() -> Result<(), Box<dyn std::error::Error>> {
        let spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            tracks: vec![BuildTrack {
                name: "MXFTrack".to_owned(),
                kind: BuildTrackKind::Audio,
                stereo: false,
                ..BuildTrack::default()
            }],
            ..PtxBuildSpec::default()
        };
        let mut doc = decode_bytes("mxf.ptx", &encode_ptx(&spec)?)?;
        doc.umids.insert("sine".to_owned(), "060a2b34".to_owned());
        doc.audio_file_stems.push("sine".to_owned());
        doc.audio_file_exts.insert("sine".to_owned(), "mxf".to_owned());

        let (sc, rep, carry) = ptx_doc_to_scraft(&doc, Path::new("."), None, &ConvertOptions::default())?;
        assert_eq!(sc.tracks.len(), 1);
        assert_eq!(sc.tracks[0].name, "MXFTrack");
        assert_eq!(sc.sources.len(), 1);
        assert_eq!(sc.sources[0].path, "Audio Files/sine.mxf");
        let carry_ref = carry.as_ref().ok_or("missing carry")?;
        assert_eq!(carry_ref.audio_files[0].file_name, "sine.mxf");
        assert!(rep.summary.carry >= 1);
        assert!(rep.warnings.iter().any(|w| w.contains("sine.mxf")));
        Ok(())
    }

    #[test]
    fn discrete_master_bypass_and_channel_strip_t0_calibration() -> Result<(), Box<dyn std::error::Error>> {
        let spec = PtxBuildSpec {
            sample_rate: 48_000,
            bit_depth: 24,
            tracks: vec![BuildTrack {
                name: "Fold_Rhythm".to_owned(),
                kind: BuildTrackKind::RoutingFolder,
                stereo: true,
                inserts: vec![BuildInsert {
                    slot_index: 0,
                    plugin_name: "Channel Strip".to_owned(),
                    bypass: false,
                    active: true,
                    multi_mono: false,
                    params: BTreeMap::new(),
                    automation: vec![
                        BuildInsertAutoLane {
                            param_name: "Master Bypass".to_owned(),
                            param_id: "MasterBypassID".to_owned(),
                            param_index: 1,
                            points: vec![(0, 0.0), (48_000, 1.0)],
                        },
                        BuildInsertAutoLane {
                            param_name: "Input Trim".to_owned(),
                            param_id: "Input Trim".to_owned(),
                            param_index: 4,
                            points: vec![(0, 0.25), (48_000, 0.5)],
                        },
                        BuildInsertAutoLane {
                            param_name: "Cmp Gain Makeup".to_owned(),
                            param_id: "Cmp Gain Makeup".to_owned(),
                            param_index: 24,
                            points: vec![(0, 0.25), (48_000, 0.5)],
                        },
                        BuildInsertAutoLane {
                            param_name: "EQ Low Frequency".to_owned(),
                            param_id: "EQ Low Frequency".to_owned(),
                            param_index: 45,
                            points: vec![(0, 0.25), (48_000, 0.5)],
                        },
                    ],
                }],
                ..BuildTrack::default()
            }],
            ..PtxBuildSpec::default()
        };
        let ptx_bytes = encode_ptx(&spec)?;
        let doc = decode_bytes("cs_test.ptx", &ptx_bytes)?;
        let pt_ins0 = doc.tracks[0].inserts.as_ref().and_then(|v| v.first()).ok_or("missing pt insert")?;
        let mb_pts = &pt_ins0.automation[0];
        assert_eq!(mb_pts, &vec![(0, 0.0), (48_000, 1.0)]);

        let (sc, _, _) = ptx_doc_to_scraft(&doc, Path::new("."), None, &ConvertOptions::default())?;
        let ins = sc.tracks[0].mixer.inserts[0].as_ref().ok_or("missing sc insert")?;
        assert!(!ins.bypass);
        assert!((ins.params["input_gain"] - (-18.0)).abs() < 0.01);
        assert!((ins.params["comp_makeup"] - 7.5).abs() < 0.01);
        assert!((ins.params["low_freq"] - 113.8485).abs() < 0.05);
        Ok(())
    }
}
