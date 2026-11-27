// Version: 0.7.0 (beta) | Date: 2026-11-27
//! Clean-room `PtxDocument -> SoundCraft Session` converter.

use std::collections::{BTreeMap, HashMap};
use std::path::Path;

use craft_midi::{CtrlEvent, CtrlKind, Note, Sequence};
use craft_scraft_format::{
    AutoParam, AutomationMode, BitDepthSetting, Bus, BusId, ChannelFormat, Clip, ClipId,
    EditMode, Fade, Group, GroupId, MarkerId, MarkerKind, MemoryLocation, OutputPath, Playlist,
    Route, SendSlot, Session, SourceId, SurroundPan, TRACK_COLORS, Tool, Track, TrackHeight,
    TrackId, TrackKind,
};
use craft_scraft_format::soundcraft_time::{Range, SampleRate, Samples, TempoMap, TimeFormat};
use ptx_format::decode::PtxDocument;
use ptx_format::decode::clips::{AudioPlacement, ClipLoop, Region};
use ptx_format::decode::midi::MidiChunk;
use ptx_format::decode::mixer::Strip;
use ptx_format::decode::tracks::TrackPlaylists;

use crate::automation::{
    build_tempo_map_from_ptx, parse_tc_to_samples, ptx_fade_to_sc, ptx_frame_rate_is_unmapped_drop,
    ptx_frame_rate_to_sc, ptx_keysig_to_sc, ptx_lane_to_sc, ptx_pan_to_sc,
    ptx_ticks_to_craft_ticks, ptx_ticks_to_samples,
};
use crate::media::{
    FallbackSourceSpec, InspectedAudio, inspect_audio_file, make_sc_source,
    materialize_media_ref, materialize_split_stereo_wav, resolve_audio_path,
};
use crate::plugins::{PtxInsertToScArgs, load_plugin_config, ptx_insert_to_sc};
use crate::report::{
    CarryAudioFile, CarrySidecar, CarryTrack, ConversionReport, Fidelity,
};
use crate::{ConvertError, ConvertOptions, LoopHandling};

fn map_track_kind(pt_kind: u16, track_type: &str) -> (TrackKind, bool) {
    if track_type == "RoutingFolder" {
        return (TrackKind::Folder, false);
    }
    match pt_kind {
        0 => (TrackKind::Audio, false),
        1 => (TrackKind::Midi, false),
        2 => (TrackKind::Aux, false),
        5 => (TrackKind::Master, false),
        7 => (TrackKind::Instrument, false),
        9 => (TrackKind::Vca, false),
        11 => (TrackKind::Folder, true), // BasicFolder -> Folder + mark carry `ptx_kind: 11`
        _ => (TrackKind::Aux, true),
    }
}

fn map_automation_mode(val: Option<&serde_json::Value>) -> AutomationMode {
    let s = val.and_then(|v| v.as_str()).unwrap_or("read");
    AutomationMode::from_id(s).unwrap_or(AutomationMode::Read)
}

fn map_ptx_height(code: Option<u16>) -> TrackHeight {
    match code.unwrap_or(92) {
        0..=28 => TrackHeight::Micro,
        29..=44 => TrackHeight::Mini,
        45..=72 => TrackHeight::Small,
        73..=115 => TrackHeight::Medium,
        116..=170 => TrackHeight::Large,
        171..=260 => TrackHeight::Jumbo,
        _ => TrackHeight::Extreme,
    }
}

fn map_route_name(
    raw: Option<&str>,
    main_out_names: &std::collections::HashSet<String>,
    aux_input_names: &std::collections::HashSet<String>,
    bus_map: &mut HashMap<String, BusId>,
    busses: &mut Vec<Bus>,
    next_id: &mut u64,
    default_fmt: ChannelFormat,
) -> Route {
    let Some(name) = raw.map(str::trim).filter(|s| !s.is_empty()) else {
        return Route::None;
    };
    let lower = name.to_ascii_lowercase();
    if lower == "none" || lower == "no output" || lower == "no input" {
        return Route::None;
    }
    if main_out_names.contains(name)
        || lower == "out 1-2"
        || lower == "main"
        || lower.starts_with("out 1")
        || lower.contains("main out")
        || (!aux_input_names.contains(name)
            && (lower.contains("speakers")
                || lower.contains("headphones")
                || lower.contains("built-in")
                || lower.contains("aggregate")))
    {
        return Route::Main;
    }
    if let Some(&id) = bus_map.get(name) {
        return Route::Bus(id);
    }
    if !aux_input_names.contains(name)
        && (lower.starts_with("in ") || lower.starts_with("out ") || lower.starts_with("mic") || lower.starts_with("line"))
    {
        return Route::Hardware(name.to_owned());
    }
    *next_id += 1;
    let id = BusId(*next_id);
    bus_map.insert(name.to_owned(), id);
    busses.push(Bus {
        id,
        name: name.to_owned(),
        format: default_fmt,
    });
    Route::Bus(id)
}

/// Match a region name (e.g. `"tone-01"` or `"Kick"`) to a known audio stem in `umids`.
fn match_audio_stem(region_name: &str, stems: &[String]) -> String {
    if stems.iter().any(|s| s == region_name) {
        return region_name.to_owned();
    }
    // Strip Pro Tools take/region suffix `-\d+` and channel tags `.L`/`.R`
    let mut base = region_name;
    if let Some(dot_pos) = base.rfind('.') {
        let suf = &base[dot_pos..];
        if suf == ".L" || suf == ".R" {
            let candidate = base.to_owned();
            if stems.iter().any(|s| s == &candidate) {
                return candidate;
            }
            base = &base[..dot_pos];
        }
    }
    if let Some(hit) = stems.iter().find(|s| s.as_str() == base) {
        return hit.clone();
    }
    if let Some(dash) = base.rfind('-')
        && base[dash + 1..].chars().all(|c| c.is_ascii_digit())
    {
        let stripped = &base[..dash];
        if let Some(hit) = stems.iter().find(|s| s == &stripped) {
            return hit.clone();
        }
        if let Some(hit) = stems.iter().find(|s| s.strip_suffix(".L") == Some(stripped)) {
            return hit.clone();
        }
    }
    stems
        .iter()
        .filter(|s| region_name.starts_with(s.as_str()))
        .max_by_key(|s| s.len())
        .cloned()
        .unwrap_or_else(|| base.to_owned())
}

fn find_audio_by_stem(ptx_dir: &Path, stem: &str) -> Option<(String, std::path::PathBuf)> {
    const EXTS: &[&str] = &[
        "wav", "WAV", "aif", "AIF", "aiff", "AIFF", "flac", "FLAC", "mxf", "MXF", "sd2", "SD2",
    ];
    for ext in EXTS {
        let fname = format!("{stem}.{ext}");
        if let Some(p) = resolve_audio_path(ptx_dir, &fname) {
            return Some((fname, p));
        }
    }
    // Also check exact filename (in case stem already contains extension or custom ext)
    if let Some(p) = resolve_audio_path(ptx_dir, stem) {
        let fname = p.file_name().and_then(|n| n.to_str()).unwrap_or(stem).to_owned();
        return Some((fname, p));
    }
    None
}

fn resolve_loop_iter_samples(
    lp: &ClipLoop,
    clip_start: Samples,
    base_len: Samples,
    tempo: &TempoMap,
    sr: SampleRate,
) -> (Samples, usize) {
    let count = usize::try_from(lp.count.max(1)).unwrap_or(1);
    let iter_smp = if let Some(s) = lp.iter_samples.filter(|&v| v > 0) {
        i64::try_from(s).unwrap_or(base_len)
    } else if let Some(t) = lp.iter_ticks.filter(|&v| v > 0) {
        let t0 = crate::automation::samples_to_ptx_ticks(clip_start, tempo, sr);
        let s1 = ptx_ticks_to_samples(t0.saturating_add(t), tempo, sr);
        (s1 - clip_start).max(1)
    } else if let Some(t) = lp.trim_ticks.filter(|&v| v > 0) {
        let t0 = crate::automation::samples_to_ptx_ticks(clip_start, tempo, sr);
        let s1 = ptx_ticks_to_samples(t0.saturating_add(t), tempo, sr);
        (s1 - clip_start).max(1)
    } else {
        base_len.max(1)
    };
    (iter_smp.max(1), count)
}

fn build_midi_sequence(chunk: &MidiChunk) -> Sequence {
    let mut seq = Sequence::default();
    for &[start, key, len, vel] in &chunk.notes {
        seq.notes.push(Note {
            pitch: key.min(127) as u8,
            velocity: vel.clamp(1, 127) as u8,
            release_velocity: 64,
            channel: 0,
            start: ptx_ticks_to_craft_ticks(start),
            length: ptx_ticks_to_craft_ticks(len).max(1),
        });
    }
    for ctrl in &chunk.controllers {
        let kind_str = ctrl.kind.as_str().unwrap_or("");
        if kind_str == "program"
            && let Some(pbs) = &ctrl.program_banks
            && !pbs.is_empty()
        {
            for pb in pbs {
                let tick = ptx_ticks_to_craft_ticks(pb.ticks);
                seq.ctrls.push(CtrlEvent {
                    tick,
                    channel: 0,
                    kind: CtrlKind::Cc(0),
                    value: i32::try_from(pb.bank_msb.min(127)).unwrap_or(0),
                });
                seq.ctrls.push(CtrlEvent {
                    tick,
                    channel: 0,
                    kind: CtrlKind::Cc(32),
                    value: i32::try_from(pb.bank_lsb.min(127)).unwrap_or(0),
                });
                seq.ctrls.push(CtrlEvent {
                    tick,
                    channel: 0,
                    kind: CtrlKind::Program,
                    value: i32::try_from(pb.program.min(127)).unwrap_or(0),
                });
            }
            continue;
        }
        let kind = match kind_str {
            "pitch_bend" => Some(CtrlKind::PitchBend),
            "controller" => Some(CtrlKind::Cc(ctrl.number.min(127))),
            "program" => Some(CtrlKind::Program),
            "channel_pressure" => Some(CtrlKind::ChannelPressure),
            "poly_pressure" => Some(CtrlKind::PolyPressure(ctrl.number.min(127))),
            _ => None,
        };
        if let Some(k) = kind {
            for &[raw_t, val] in &ctrl.points {
                let tick = ptx_ticks_to_craft_ticks(u64::try_from(raw_t.max(0)).unwrap_or(0));
                seq.ctrls.push(CtrlEvent {
                    tick,
                    channel: 0,
                    kind: k,
                    value: i32::try_from(val).unwrap_or(0),
                });
            }
        }
    }
    for mc in &chunk.mpe_curves {
        let mpe_ch = mc.mpe_channel.saturating_sub(1).min(15);
        for n in &mut seq.notes {
            if n.start == ptx_ticks_to_craft_ticks(mc.note_start) && n.pitch == mc.key.min(127) {
                n.channel = mpe_ch;
            }
        }
        let kind = match mc.kind.as_str().unwrap_or("") {
            "pitch_bend" => Some(CtrlKind::PitchBend),
            "controller" => Some(CtrlKind::Cc(mc.number.min(127))),
            "channel_pressure" => Some(CtrlKind::ChannelPressure),
            "poly_pressure" => Some(CtrlKind::PolyPressure(mc.number.min(127))),
            _ => None,
        };
        if let Some(k) = kind {
            for &[raw_t, val] in &mc.points {
                let tick = ptx_ticks_to_craft_ticks(u64::try_from(raw_t.max(0)).unwrap_or(0));
                seq.ctrls.push(CtrlEvent {
                    tick,
                    channel: mpe_ch,
                    kind: k,
                    value: i32::try_from(val).unwrap_or(0),
                });
            }
        }
    }
    seq.sort();
    seq
}

fn split_mono_base(stem: &str) -> Option<(&str, bool)> {
    if let Some(b) = stem.strip_suffix(".L") {
        Some((b, true))
    } else if let Some(b) = stem.strip_suffix(".R") {
        Some((b, false))
    } else {
        None
    }
}

fn resolve_placement_start_samples(
    p: &AudioPlacement,
    sync_off: i64,
    tempo: &TempoMap,
    sr: SampleRate,
) -> Samples {
    if let Some(cs) = p.clip_start_samples {
        cs
    } else if let Some(s) = p.samples {
        let s_plain = if s >= 1_000_000_000_000 {
            s - 1_000_000_000_000
        } else {
            s
        };
        s_plain - sync_off
    } else if let Some(t) = p.ticks {
        ptx_ticks_to_samples(t, tempo, sr) - sync_off
    } else {
        0
    }
}

fn resolve_fade_pos_samples(p: &AudioPlacement, tempo: &TempoMap, sr: SampleRate) -> Samples {
    if let Some(s) = p.samples {
        if s >= 1_000_000_000_000 {
            s - 1_000_000_000_000
        } else {
            s
        }
    } else if let Some(t) = p.ticks {
        ptx_ticks_to_samples(t, tempo, sr)
    } else {
        0
    }
}

/// Convert a decoded [`PtxDocument`] into a SoundCraft [`Session`], [`ConversionReport`], and [`CarrySidecar`].
///
/// # Errors
/// Returns `ConvertError` on media copy errors or `--strict` loss refusal.
pub fn ptx_doc_to_scraft(
    doc: &PtxDocument,
    ptx_dir: &Path,
    out_dir: Option<&Path>,
    opts: &ConvertOptions,
) -> Result<(Session, ConversionReport, Option<CarrySidecar>), ConvertError> {
    let sr_hz = doc.format.sample_rate.unwrap_or(48_000).max(8_000);
    let sr = SampleRate::new(sr_hz).unwrap_or(SampleRate::HZ_48000);
    let plugin_cfg = load_plugin_config(opts.plugin_config.as_deref())?;
    let target_label = out_dir
        .map(|d| d.display().to_string())
        .unwrap_or_else(|| ptx_dir.display().to_string());
    let mut report = ConversionReport::new(
        "ptx_to_scraft",
        &doc.file,
        &target_label,
        opts.media_mode.as_str(),
        opts.loop_handling.as_str(),
    );

    let session_name = Path::new(&doc.file)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("Converted Session")
        .to_owned();

    let mut session = Session::new(&session_name, sr);
    session.tracks.clear();
    session.busses.clear();
    session.sources.clear();
    session.outputs = vec![OutputPath {
        name: "Main Out".to_owned(),
        first_channel: 0,
        format: ChannelFormat::Stereo,
    }];
    session.bit_depth = match (doc.format.bit_depth.unwrap_or(24), doc.format.is_float.unwrap_or(false)) {
        (16, _) => BitDepthSetting::Int16,
        (32, true) => BitDepthSetting::Float32,
        _ => BitDepthSetting::Int24,
    };
    session.frame_rate = ptx_frame_rate_to_sc(&doc.timeline);
    if ptx_frame_rate_is_unmapped_drop(&doc.timeline) {
        report.record(
            "timeline",
            format!(
                "timecode_rate:{}",
                doc.timeline.timecode_rate.as_deref().unwrap_or("Drop")
            ),
            Fidelity::Approx,
            Some("SoundCraft lacks 30D/60D/119.88D/120D variants; original 0x204D rate code preserved in .ptxcarry.json".to_owned()),
        );
    }
    if let Some(start_tc) = doc.timeline.session_start.as_deref() {
        session.timecode_start = parse_tc_to_samples(start_tc, session.frame_rate, sr);
    }
    if let Some(pf) = doc.timeline.pull_code.filter(|&c| c != 12000) {
        let label = doc.timeline.pull.as_deref().unwrap_or("custom");
        report.record(
            "timeline",
            format!("pull:{label} ({pf})"),
            if opts.carry { Fidelity::Carry } else { Fidelity::Absent },
            Some("audio pull factor preserved in .ptxcarry.json".to_owned()),
        );
    }

    let tempo = build_tempo_map_from_ptx(doc, &mut report);
    session.tempo = tempo.clone();

    // Edit & Transport settings (`0x2024`, `0x2056`, `0x2058`, `0x201F`, `0x2016`)
    {
        let ss = &doc.session_settings;
        let mut mapped_edit = false;
        if let Some(em) = ss.edit_mode.as_deref().or_else(|| {
            ss.edit_mode_code.map(|c| match c {
                0 => "Shuffle",
                1 => "Slip",
                2 => "Spot",
                _ => "Grid",
            })
        }) {
            session.edit.edit_mode = match em {
                "Shuffle" => EditMode::Shuffle,
                "Slip" | "1" => EditMode::Slip,
                "Spot" | "2" => EditMode::Spot,
                _ => EditMode::Grid,
            };
            mapped_edit = true;
        }
        if ss.smart_tool == Some(true) {
            session.edit.tool = Tool::Smart;
            mapped_edit = true;
        } else if let Some(tc) = ss.edit_tool_code {
            session.edit.tool = match tc {
                1 => Tool::Zoom,
                3 => Tool::Trim,
                5 => Tool::Grabber,
                6 => Tool::Scrubber,
                8 => Tool::Pencil,
                _ => Tool::Selector,
            };
            mapped_edit = true;
        }
        if let Some(lp) = ss.loop_playback {
            session.edit.loop_playback = lp;
            mapped_edit = true;
        }
        if let Some(rm) = ss.record_mode.as_ref().and_then(|v| v.as_str()) {
            session.edit.record_mode = rm.to_ascii_lowercase();
            mapped_edit = true;
        }
        if let Some(sc) = ss.sub_counter.as_deref() {
            session.edit.sub_counter = Some(match sc {
                "BarsBeats" => TimeFormat::BarsBeats,
                "Samples" => TimeFormat::Samples,
                _ => TimeFormat::MinSecs,
            });
            mapped_edit = true;
        }
        if let Some([t0, t1]) = ss.timeline_selection_ticks {
            let s0 = ptx_ticks_to_samples(t0, &tempo, sr);
            let s1 = ptx_ticks_to_samples(t1, &tempo, sr).max(s0);
            let rng = Range::new(s0, s1);
            session.edit.selection = rng;
            session.edit.timeline_selection = rng;
            mapped_edit = true;
        }
        if mapped_edit {
            report.record("edit_state", "session_settings", Fidelity::Native, None);
        }
    }

    for ks in &doc.key_signatures {
        let s = ptx_ticks_to_samples(ks.ticks, &tempo, sr);
        let label = ptx_keysig_to_sc(ks.major, ks.sharps);
        session.key_signatures.push((s, label));
        report.record("key_signatures", format!("{s}:{}", ks.key), Fidelity::Native, None);
    }

    let mut next_id: u64 = 10;
    let mut carry = CarrySidecar {
        version: 1,
        xor_seed: 0x5A,
        session_version: doc.version.clone(),
        timeline: Some(doc.timeline.clone()),
        session_settings: Some(doc.session_settings.clone()),
        write_enables: doc.write_enables.clone(),
        ..CarrySidecar::default()
    };

    // 1. Register audio sources from UMID stem table
    let stems: Vec<String> = doc.umids.keys().cloned().collect();
    let mut stem_to_source: HashMap<String, SourceId> = HashMap::new();
    let mut stem_disk_info: HashMap<String, (String, Option<InspectedAudio>)> = HashMap::new();
    let mut source_frames_map: HashMap<SourceId, u64> = HashMap::new();
    for (stem, umid) in &doc.umids {
        next_id += 1;
        let sid = SourceId(next_id);
        let pt_ext = doc.audio_file_exts.get(stem).map(String::as_str);
        let found_disk = find_audio_by_stem(ptx_dir, stem);
        let (fname, found_on_disk, inspected): (String, bool, Option<InspectedAudio>) =
            if let Some((fnm, full_path)) = found_disk {
                let insp = inspect_audio_file(&full_path).ok();
                (fnm, true, insp)
            } else {
                let default_name = pt_ext.map_or_else(|| format!("{stem}.wav"), |ext| format!("{stem}.{ext}"));
                (default_name, false, None)
            };

        let is_non_pcm_legacy = inspected.is_none()
            && matches!(
                Path::new(&fname)
                    .extension()
                    .and_then(|e| e.to_str())
                    .map(str::to_ascii_lowercase)
                    .as_deref(),
                Some("mxf" | "sd2")
            );

        let rel_path = if let Some(ref insp) = inspected {
            materialize_media_ref(&insp.path, ptx_dir, out_dir, &fname, opts.media_mode)?
        } else if is_non_pcm_legacy {
            report.warnings.push(format!(
                "non-PCM/legacy audio container cannot be decoded natively: {fname}"
            ));
            format!("Audio Files/{fname}")
        } else {
            if !found_on_disk {
                report.warnings.push(format!("audio file missing on disk: {fname}"));
            }
            format!("Audio Files/{fname}")
        };

        let src = make_sc_source(
            sid,
            stem.clone(),
            rel_path,
            inspected.as_ref(),
            FallbackSourceSpec {
                sample_rate: sr_hz,
                channels: 1,
                frames: 0,
                is_aiff: doc.format.file_format.as_deref() == Some("AIFF"),
            },
        );
        source_frames_map.insert(sid, src.frames);
        stem_disk_info.insert(stem.clone(), (fname.clone(), inspected.clone()));
        carry.audio_files.push(CarryAudioFile {
            file_name: fname.clone(),
            bit_depth: inspected.as_ref().map_or(24, |i| i.bit_depth),
            is_float: inspected.as_ref().is_some_and(|i| i.is_float),
            is_aiff: inspected.as_ref().is_some_and(|i| i.is_aiff),
            data_offset: inspected.as_ref().map_or(44, |i| i.data_offset),
            filetime: inspected.as_ref().map_or(133_000_000_000_000_000, |i| i.filetime),
            umid: (!umid.is_empty()).then(|| umid.clone()),
        });
        session.sources.push(src);
        stem_to_source.insert(stem.clone(), sid);
        if is_non_pcm_legacy {
            report.record(
                "media",
                fname,
                if opts.carry { Fidelity::Carry } else { Fidelity::Absent },
                Some("non-PCM/legacy audio container (.mxf/.sd2); requires stem render or external decode".to_owned()),
            );
        } else {
            report.record("media", fname, Fidelity::Native, None);
        }
    }
    let mut split_pair_sources: HashMap<(String, String), (SourceId, (String, String))> = HashMap::new();

    // 2. Partition decoded regions into Audio regions and MIDI regions
    let audio_regions: Vec<&Region> = doc.regions.iter().filter(|r| r.list.is_none()).collect();
    let midi_regions: Vec<&Region> = doc.regions.iter().filter(|r| r.list.is_some()).collect();
    let mut playlist_lookup: HashMap<String, Vec<AudioPlacement>> = HashMap::new();
    let mut playlist_ch1_lookup: HashMap<String, Vec<AudioPlacement>> = HashMap::new();
    for (nm, chs) in &doc.audio_channels {
        let mut parsed_chs: Vec<Vec<AudioPlacement>> = chs
            .iter()
            .filter_map(|v| serde_json::from_value::<Vec<AudioPlacement>>(v.clone()).ok())
            .collect();
        if let Some(ch1) = parsed_chs.get(1)
            && !ch1.is_empty()
        {
            playlist_ch1_lookup.insert(nm.clone(), ch1.clone());
        }
        if let Some(mut primary) = parsed_chs.first().cloned() {
            for extra_ch in parsed_chs.drain(..).skip(1) {
                for ent in extra_ch {
                    if ent.kind.as_str() == Some("fade")
                        && !primary.iter().any(|p| {
                            p.kind.as_str() == Some("fade")
                                && p.samples == ent.samples
                                && p.ticks == ent.ticks
                        })
                    {
                        primary.push(ent);
                    }
                }
            }
            if !primary.is_empty() {
                playlist_lookup.insert(nm.clone(), primary);
            }
        }
    }
    for (nm, vec) in &doc.audio_playlists {
        playlist_lookup.entry(nm.clone()).or_insert_with(|| vec.clone());
    }
    for (nm, arr) in &doc.audio_placements {
        let parsed: Vec<AudioPlacement> = arr
            .iter()
            .filter_map(|v| serde_json::from_value::<AudioPlacement>(v.clone()).ok())
            .collect();
        if !parsed.is_empty() {
            if let Some(existing) = playlist_lookup.get_mut(nm) {
                // Attach loop_info decoded onto audio_placements without letting ch1 overwrite ch0 fades/clips
                for p in &parsed {
                    if p.loop_info.is_some()
                        && let Some(target) = existing.iter_mut().find(|e| {
                            e.kind.as_str() == Some("clip") && e.samples == p.samples && e.ticks == p.ticks
                        })
                    {
                        target.loop_info = p.loop_info.clone();
                    }
                }
            } else {
                playlist_lookup.insert(nm.clone(), parsed);
            }
        }
    }

    // Index mixer strips by track index (`Option<usize>`, preserving stereo L/R sub-strips)
    let mut strips_by_track: HashMap<usize, Vec<&Strip>> = HashMap::new();
    for st in &doc.strips {
        if let Some(tidx) = st.track {
            strips_by_track.entry(tidx).or_default().push(st);
        }
    }

    let mut main_out_names: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut aux_input_names: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut bus_formats: HashMap<String, ChannelFormat> = HashMap::new();
    for pt_tr in &doc.tracks {
        if pt_tr.kind == 5
            && let Some(out) = pt_tr.output.as_deref().map(str::trim).filter(|s| !s.is_empty())
        {
            main_out_names.insert(out.to_owned());
        }
        if (pt_tr.kind == 2 || pt_tr.track_type == "RoutingFolder")
            && let Some(inp) = pt_tr.input.as_deref().map(str::trim).filter(|s| !s.is_empty())
        {
            aux_input_names.insert(inp.to_owned());
            let inp_fmt = if pt_tr.stereo {
                ChannelFormat::Stereo
            } else {
                ChannelFormat::Mono
            };
            bus_formats.entry(inp.to_owned()).or_insert(inp_fmt);
        }
    }
    for st in &doc.strips {
        if let Some(out) = st.output.as_deref().map(str::trim).filter(|s| !s.is_empty())
            && !main_out_names.contains(out)
            && let Some(si) = st.stem_index
        {
            let st_fmt = if si == 0 {
                ChannelFormat::Mono
            } else {
                ChannelFormat::Stereo
            };
            bus_formats.entry(out.to_owned()).or_insert(st_fmt);
        }
    }

    let mut bus_map: HashMap<String, BusId> = HashMap::new();
    let mut track_name_to_id: HashMap<String, TrackId> = HashMap::new();

    // Allocate track IDs in advance so folders can resolve parent references regardless of order
    let mut track_ids: Vec<TrackId> = Vec::with_capacity(doc.tracks.len());
    for pt_tr in &doc.tracks {
        next_id += 1;
        let tid = TrackId(next_id);
        track_ids.push(tid);
        track_name_to_id.insert(pt_tr.name.clone(), tid);
    }

    // 3. Map tracks, mixer strips, plugins, and clips
    for (tidx, pt_tr) in doc.tracks.iter().enumerate() {
        let tid = track_ids[tidx];
        let (kind, is_basic_folder) = map_track_kind(pt_tr.kind, &pt_tr.track_type);
        let fmt = if pt_tr.stereo {
            ChannelFormat::Stereo
        } else {
            ChannelFormat::Mono
        };
        let color_idx = pt_tr
            .colour
            .and_then(|c| usize::try_from(c.max(0)).ok())
            .map_or(tidx % TRACK_COLORS.len(), |i| i % TRACK_COLORS.len());
        let mut sc_tr = Track::new(tid, &pt_tr.name, kind, fmt, TRACK_COLORS[color_idx]);
        sc_tr.hidden = pt_tr.hidden.unwrap_or(false);
        sc_tr.inactive = pt_tr.active == Some(false);
        sc_tr.height = map_ptx_height(pt_tr.height_code);
        sc_tr.comments = pt_tr.comment.clone().unwrap_or_default();
        sc_tr.folder = pt_tr.folder.as_deref().and_then(|fnm| track_name_to_id.get(fnm).copied());
        let is_ticks = pt_tr.timebase.as_deref() == Some("ticks") || kind.is_midi();
        sc_tr.mixer.automation_mode = map_automation_mode(pt_tr.automation_mode.as_ref());
        sc_tr.mixer.solo = pt_tr.solo.unwrap_or(false);
        sc_tr.mixer.record_arm = pt_tr.record_enable.unwrap_or(false);
        let in_default_fmt = pt_tr
            .input
            .as_deref()
            .map(str::trim)
            .and_then(|n| bus_formats.get(n).copied())
            .unwrap_or(fmt);
        sc_tr.mixer.input = map_route_name(
            pt_tr.input.as_deref(),
            &main_out_names,
            &aux_input_names,
            &mut bus_map,
            &mut session.busses,
            &mut next_id,
            in_default_fmt,
        );
        let out_default_fmt = pt_tr
            .output
            .as_deref()
            .map(str::trim)
            .and_then(|n| bus_formats.get(n).copied())
            .unwrap_or(ChannelFormat::Stereo);
        sc_tr.mixer.output = if kind == TrackKind::Master {
            Route::Main
        } else {
            map_route_name(
                pt_tr.output.as_deref(),
                &main_out_names,
                &aux_input_names,
                &mut bus_map,
                &mut session.busses,
                &mut next_id,
                out_default_fmt,
            )
        };

        let mut tr_carry = CarryTrack {
            ptx_kind: is_basic_folder.then_some(pt_tr.kind),
            user_delay: pt_tr.user_delay.filter(|&d| d != 0),
            synthesized_user_delay_slot: None,
            colour: pt_tr.colour,
            elastic_mode: pt_tr.elastic_mode.clone(),
            mpe_mode: pt_tr
                .mpe
                .as_deref()
                .filter(|m| matches!(*m, "mono" | "poly"))
                .map(ToOwned::to_owned),
            inserts: Vec::new(),
        };
        if let Some(mpe) = tr_carry.mpe_mode.as_deref() {
            report.record(
                "midi",
                format!("{}:mpe={mpe}", pt_tr.name),
                if opts.carry { Fidelity::Carry } else { Fidelity::Absent },
                Some("MPE mode preserved in .ptxcarry.json".to_owned()),
            );
        }

        // Mixer strip (volume/pan/mute lanes & sends; dual stereo pan when second sub-strip present)
        if let Some(track_strips) = strips_by_track.get(&tidx)
            && let Some(&st) = track_strips.first()
        {
            let strip_ticks = st.lane_time_base.as_deref() == Some("ticks") || is_ticks;
            if let Some(v_db) = st.volume_db {
                sc_tr.mixer.volume_db = if v_db.is_finite() { v_db as f32 } else { -144.0 };
            }
            if !st.volume.is_empty() {
                let lane = ptx_lane_to_sc(AutoParam::Volume, &st.volume, strip_ticks, &tempo, sr, true);
                if lane.points.len() > 1 || (lane.points.len() == 1 && (lane.points[0].value - sc_tr.mixer.volume_db).abs() > 0.05) {
                    sc_tr.automation.push(lane);
                }
            }
            if !st.pan.is_empty() {
                if let Some(&(_, p0)) = st.pan.first() {
                    let pv = ptx_pan_to_sc(p0);
                    if sc_tr.mixer.pan.is_empty() {
                        sc_tr.mixer.pan.push(pv);
                    } else {
                        sc_tr.mixer.pan[0] = pv;
                    }
                }
                if st.pan.len() > 1 {
                    sc_tr.automation.push(ptx_lane_to_sc(
                        AutoParam::Pan(0),
                        &st.pan,
                        strip_ticks,
                        &tempo,
                        sr,
                        false,
                    ));
                }
            }
            let pan2_src = if !st.pan2.is_empty() {
                Some((&st.pan2, strip_ticks))
            } else if track_strips.len() >= 2
                && let Some(&st_r) = track_strips
                    .iter()
                    .find(|s| s.stem_index == Some(2))
                    .or_else(|| track_strips.get(1))
                && !st_r.pan.is_empty()
            {
                let strip_r_ticks = st_r.lane_time_base.as_deref() == Some("ticks") || strip_ticks;
                Some((&st_r.pan, strip_r_ticks))
            } else {
                None
            };
            if sc_tr.format != ChannelFormat::Mono
                && let Some((pan2_pts, pan2_ticks)) = pan2_src
            {
                if let Some(&(_, p1)) = pan2_pts.first() {
                    let pv1 = ptx_pan_to_sc(p1);
                    while sc_tr.mixer.pan.len() < 2 {
                        sc_tr.mixer.pan.push(1.0);
                    }
                    sc_tr.mixer.pan[1] = pv1;
                }
                if pan2_pts.len() > 1 {
                    sc_tr.automation.push(ptx_lane_to_sc(
                        AutoParam::Pan(1),
                        pan2_pts,
                        pan2_ticks,
                        &tempo,
                        sr,
                        false,
                    ));
                }
            }
            if !st.mute.is_empty() {
                sc_tr.mixer.mute = st.mute.first().is_some_and(|x| x.1 > 0);
                if st.mute.len() > 1 {
                    sc_tr.automation.push(ptx_lane_to_sc(
                        AutoParam::Mute,
                        &st.mute,
                        strip_ticks,
                        &tempo,
                        sr,
                        false,
                    ));
                }
            }
            if let Some(lfe_db) = st.lfe_db.filter(|&v| v.is_finite() && v > -140.0) {
                sc_tr
                    .mixer
                    .surround
                    .get_or_insert_with(SurroundPan::default)
                    .lfe_db = (lfe_db as f32).clamp(-144.0, 12.0);
                report.record(
                    "mixer",
                    format!("{}:lfe_db={lfe_db:.1}", pt_tr.name),
                    Fidelity::Native,
                    None,
                );
                if st.lfe.len() > 1 {
                    report.record(
                        "mixer",
                        format!("{}:lfe_lane", pt_tr.name),
                        if opts.carry { Fidelity::Carry } else { Fidelity::Absent },
                        Some("dynamic LFE automation lane not supported natively in SoundCraft".to_owned()),
                    );
                }
            }
            if let Some(sends) = &st.sends {
                for (sidx, snd) in sends.iter().take(10).enumerate() {
                    let snd_default_fmt = snd
                        .output
                        .as_deref()
                        .map(str::trim)
                        .and_then(|n| bus_formats.get(n).copied())
                        .unwrap_or(ChannelFormat::Stereo);
                    let target = map_route_name(
                        snd.output.as_deref(),
                        &main_out_names,
                        &aux_input_names,
                        &mut bus_map,
                        &mut session.busses,
                        &mut next_id,
                        snd_default_fmt,
                    );
                    if target == Route::None {
                        continue;
                    }
                    let level_db = snd
                        .volume_db
                        .map_or(0.0, |v| if v.is_finite() { v as f32 } else { -144.0 });
                    let pan = snd.pan.first().map_or(0.0, |p| ptx_pan_to_sc(p.1));
                    let mute = snd.mute.first().is_some_and(|m| m.1 > 0);
                    if sidx < sc_tr.mixer.sends.len() {
                        sc_tr.mixer.sends[sidx] = Some(SendSlot {
                            target,
                            level_db,
                            pan,
                            mute,
                            pre_fader: snd.post_fader == Some(false),
                            follow_main_pan: false,
                            surround: None,
                        });
                    }
                    let su8 = u8::try_from(sidx).unwrap_or(0);
                    if snd.volume.len() > 1 {
                        sc_tr.automation.push(ptx_lane_to_sc(
                            AutoParam::SendLevel(su8),
                            &snd.volume,
                            strip_ticks,
                            &tempo,
                            sr,
                            true,
                        ));
                    }
                    if snd.pan.len() > 1 {
                        sc_tr.automation.push(ptx_lane_to_sc(
                            AutoParam::SendPan(su8),
                            &snd.pan,
                            strip_ticks,
                            &tempo,
                            sr,
                            false,
                        ));
                    }
                    if snd.mute.len() > 1 {
                        sc_tr.automation.push(ptx_lane_to_sc(
                            AutoParam::SendMute(su8),
                            &snd.mute,
                            strip_ticks,
                            &tempo,
                            sr,
                            false,
                        ));
                    }
                }
            }
        }

        // Inserts + Plugin Automation
        if let Some(inserts) = &pt_tr.inserts {
            for ins in inserts {
                let sidx = match &ins.slot {
                    serde_json::Value::String(ch) => ch
                        .chars()
                        .next()
                        .and_then(|c| c.to_ascii_lowercase().checked_sub_u8_or_idx()),
                    serde_json::Value::Number(n) => n.as_u64().and_then(|u| usize::try_from(u).ok()),
                    _ => None,
                };
                let Some(slot_usize) = sidx.filter(|&i| i < sc_tr.mixer.inserts.len()) else {
                    continue;
                };
                let slot_u8 = u8::try_from(slot_usize).unwrap_or(0);
                let (sc_ins_opt, plugin_lanes, carry_ins) = ptx_insert_to_sc(
                    &PtxInsertToScArgs {
                        slot_idx: slot_u8,
                        ins,
                        track_name: &pt_tr.name,
                        track_is_ticks: is_ticks,
                        tempo: &tempo,
                        sr,
                        plugin_cfg: &plugin_cfg,
                    },
                    &mut report,
                );
                if let Some(sc_ins) = sc_ins_opt {
                    sc_tr.mixer.inserts[slot_usize] = Some(sc_ins);
                }
                sc_tr.automation.extend(plugin_lanes);
                if let Some(ci) = carry_ins {
                    tr_carry.inserts.push(ci);
                }
            }
        }

        // User delay compensation -> inject Time Shift at last open slot if non-zero
        if let Some(d) = pt_tr.user_delay.filter(|&d| d != 0) {
            let mut synth_ok = false;
            if d > 0 {
                let mut params = BTreeMap::new();
                params.insert("delay_samples".to_owned(), d as f32);
                if let Some((sidx, slot)) = sc_tr
                    .mixer
                    .inserts
                    .iter_mut()
                    .enumerate()
                    .rev()
                    .find(|(_, s)| s.is_none())
                {
                    *slot = Some(craft_scraft_format::Insert {
                        plugin: "time_shift".to_owned(),
                        params,
                        bypass: false,
                        active: true,
                        preset: String::new(),
                        state: None,
                        sample: None,
                    });
                    tr_carry.synthesized_user_delay_slot = Some(sidx);
                    synth_ok = true;
                    report.record(
                        "tracks",
                        format!("{}:user_delay={d}", pt_tr.name),
                        Fidelity::Approx,
                        Some("synthesized time_shift insert".to_owned()),
                    );
                }
            }
            if !synth_ok {
                report.record(
                    "tracks",
                    format!("{}:user_delay={d}", pt_tr.name),
                    if opts.carry { Fidelity::Carry } else { Fidelity::Absent },
                    Some("user_delay preserved in .ptxcarry.json".to_owned()),
                );
            }
        }

        // Clips on active & alternate playlists
        let mut sc_clips: Vec<Clip> = Vec::new();
        let mut alt_playlists: Vec<Playlist> = Vec::new();
        match doc.track_playlists.get(&pt_tr.name) {
            Some(TrackPlaylists::Audio { active, alternates, .. }) => {
                let mut pl_names: Vec<(&str, bool)> = Vec::with_capacity(1 + alternates.len());
                pl_names.push((active.as_str(), true));
                for alt in alternates {
                    pl_names.push((alt.name.as_str(), false));
                }
                for (pl_name, is_active) in pl_names {
                    let mut target_clips: Vec<Clip> = Vec::new();
                    let mut clip_xf_infos: Vec<Option<(Samples, &ptx_format::decode::clips::FadeObject, i64, i64)>> = Vec::new();
                    if let Some(raw_placements) = playlist_lookup.get(pl_name).map(Vec::as_slice) {
                        let ch1_raw = playlist_ch1_lookup.get(pl_name).map(Vec::as_slice);
                        let mut expanded: Vec<(AudioPlacement, Option<AudioPlacement>, Option<u64>)> = Vec::new();
                        for (idx_p, p) in raw_placements.iter().enumerate() {
                            if p.kind.as_str() == Some("group")
                                && let Some(cgr) = doc.clip_group_regions.get(usize::from(p.index))
                                && let Some(mpi) = cgr.member_playlist_index.and_then(|u| usize::try_from(u).ok())
                                && let Some(members) = doc.clip_group_playlists.get(mpi)
                            {
                                next_id += 1;
                                let sc_gid = next_id;
                                let clean_grp_name = cgr
                                    .name
                                    .strip_suffix(".L")
                                    .or_else(|| cgr.name.strip_suffix(".R"))
                                    .unwrap_or(&cgr.name)
                                    .to_owned();
                                carry.clip_group_names.insert(sc_gid, clean_grp_name);
                                report.record(
                                    "clip_groups",
                                    format!("{}:{}", pt_tr.name, cgr.name),
                                    Fidelity::Native,
                                    None,
                                );
                                let grp_start_smp = resolve_fade_pos_samples(p, &tempo, sr);
                                let grp_ticks = p.ticks;
                                let ch1_members = ch1_raw
                                    .and_then(|c1| {
                                        c1.iter()
                                            .find(|x| x.kind.as_str() == Some("group") && x.samples == p.samples && x.ticks == p.ticks)
                                            .or_else(|| c1.get(idx_p))
                                    })
                                    .and_then(|g1| doc.clip_group_regions.get(usize::from(g1.index)))
                                    .and_then(|cgr1| cgr1.member_playlist_index)
                                    .and_then(|m1| usize::try_from(m1).ok())
                                    .and_then(|m1| doc.clip_group_playlists.get(m1));
                                for (mi, mp) in members.iter().enumerate() {
                                    let mut m_adj = mp.clone();
                                    if let Some(gt) = grp_ticks
                                        && let Some(mt) = mp.ticks
                                    {
                                        m_adj.ticks = Some(gt.saturating_add(mt));
                                        m_adj.samples = None;
                                    } else {
                                        let rel = resolve_fade_pos_samples(mp, &tempo, sr);
                                        m_adj.samples = Some(grp_start_smp + rel);
                                        m_adj.ticks = None;
                                        if let Some(cs) = mp.clip_start_samples {
                                            let cs_plain = if cs >= 1_000_000_000_000 { cs - 1_000_000_000_000 } else { cs };
                                            m_adj.clip_start_samples = Some(grp_start_smp + cs_plain);
                                        }
                                    }
                                    let m_ch1 = ch1_members.and_then(|v| v.get(mi).cloned());
                                    expanded.push((m_adj, m_ch1, Some(sc_gid)));
                                }
                            } else {
                                let p_ch1 = ch1_raw.and_then(|c1| {
                                    c1.iter()
                                        .find(|x| x.kind == p.kind && x.samples == p.samples && x.ticks == p.ticks)
                                        .cloned()
                                });
                                expanded.push((p.clone(), p_ch1, None));
                            }
                        }

                        let fades_at_pos: Vec<(Samples, &ptx_format::decode::clips::FadeObject, Fade)> = expanded
                            .iter()
                            .filter(|(p, _, _)| p.kind.as_str() == Some("fade"))
                            .filter_map(|(p, _, _)| {
                                let f = doc.fades.get(usize::from(p.index))?;
                                let start = resolve_fade_pos_samples(p, &tempo, sr);
                                Some((start, f, ptx_fade_to_sc(f, &mut report, &pt_tr.name)))
                            })
                            .collect();

                        for (p, p_ch1_opt, grp_id_opt) in &expanded {
                            if p.kind.as_str() != Some("clip") {
                                continue;
                            }
                            let Some(reg) = audio_regions.get(usize::from(p.index)) else {
                                continue;
                            };
                            let stem = reg
                                .file_index
                                .and_then(|fi| doc.audio_file_stems.get(fi))
                                .cloned()
                                .unwrap_or_else(|| match_audio_stem(&reg.name, &stems));

                            let mut split_pair_files: Option<(String, String)> = None;
                            let src_id = if pt_tr.stereo
                                && let Some(p1) = p_ch1_opt
                                && let Some(reg1) = audio_regions.get(usize::from(p1.index))
                                && let Some(stem1) = reg1
                                    .file_index
                                    .and_then(|fi| doc.audio_file_stems.get(fi))
                                    .cloned()
                                    .or_else(|| Some(match_audio_stem(&reg1.name, &stems)))
                                && stem != stem1
                            {
                                let pair_key = (stem.clone(), stem1.clone());
                                if let Some((existing_sid, existing_files)) = split_pair_sources.get(&pair_key) {
                                    split_pair_files = Some(existing_files.clone());
                                    *existing_sid
                                } else {
                                    let base_stem = split_mono_base(&stem)
                                        .map(|(b, _)| b.to_owned())
                                        .unwrap_or_else(|| stem.clone());
                                    let l_info = stem_disk_info.get(&stem).and_then(|(fnm, insp)| insp.as_ref().map(|i| (fnm.clone(), i.clone())));
                                    let r_info = stem_disk_info.get(&stem1).and_then(|(fnm, insp)| insp.as_ref().map(|i| (fnm.clone(), i.clone())));
                                    if let (Some((fn_l, insp_l)), Some((fn_r, insp_r))) = (l_info, r_info) {
                                        next_id += 1;
                                        let sid = SourceId(next_id);
                                        let (rel_path, st_insp) = if let Some(target_dir) = out_dir {
                                            match materialize_split_stereo_wav(&insp_l.path, &insp_r.path, &base_stem, target_dir) {
                                                Ok((_, si)) => (format!("Audio Files/_converted/{base_stem}.stereo.wav"), Some(si)),
                                                Err(_) => (format!("Audio Files/_converted/{base_stem}.stereo.wav"), None),
                                            }
                                        } else {
                                            (format!("Audio Files/_converted/{base_stem}.stereo.wav"), None)
                                        };
                                        let sc_src = if let Some(ref si) = st_insp {
                                            make_sc_source(
                                                sid,
                                                base_stem.clone(),
                                                rel_path,
                                                Some(si),
                                                FallbackSourceSpec {
                                                    sample_rate: sr_hz,
                                                    channels: 2,
                                                    frames: insp_l.frames.min(insp_r.frames),
                                                    is_aiff: false,
                                                },
                                            )
                                        } else {
                                            make_sc_source(
                                                sid,
                                                base_stem.clone(),
                                                rel_path,
                                                None,
                                                FallbackSourceSpec {
                                                    sample_rate: insp_l.sample_rate,
                                                    channels: 2,
                                                    frames: insp_l.frames.min(insp_r.frames),
                                                    is_aiff: false,
                                                },
                                            )
                                        };
                                        source_frames_map.insert(sid, sc_src.frames);
                                        session.sources.push(sc_src);
                                        let files_pair = (fn_l, fn_r);
                                        split_pair_sources.insert(pair_key, (sid, files_pair.clone()));
                                        split_pair_files = Some(files_pair);
                                        report.record("media", format!("split_pair:{base_stem}"), Fidelity::Native, None);
                                        sid
                                    } else {
                                        report.record(
                                            "media",
                                            format!("{stem}+{stem1}"),
                                            Fidelity::Approx,
                                            Some("split-mono .L/.R audio files missing on disk; mapped L channel".to_owned()),
                                        );
                                        *stem_to_source.get(&stem).unwrap_or(&SourceId(0))
                                    }
                                }
                            } else if let Some(&sid) = stem_to_source.get(&stem) {
                                sid
                            } else {
                                next_id += 1;
                                let sid = SourceId(next_id);
                                let frames = reg.start.saturating_add(reg.length);
                                session.sources.push(make_sc_source(
                                    sid,
                                    stem.clone(),
                                    format!("Audio Files/{stem}.wav"),
                                    None,
                                    FallbackSourceSpec {
                                        sample_rate: sr_hz,
                                        channels: if pt_tr.stereo { 2 } else { 1 },
                                        frames,
                                        is_aiff: false,
                                    },
                                ));
                                source_frames_map.insert(sid, frames);
                                stem_to_source.insert(stem.clone(), sid);
                                sid
                            };

                            let sync_off_u64 = reg.sync_offset.unwrap_or(0);
                            let sync_off = i64::try_from(sync_off_u64).unwrap_or(0);
                            let clip_start = resolve_placement_start_samples(p, sync_off, &tempo, sr);
                            let base_len = i64::try_from(reg.length.max(1)).unwrap_or(1);
                            let (gain_db, gain_env) = if let Some(lane_idx) = reg.clip_gain_index.flatten()
                                && let Some(lane) = doc.clip_gain_lanes.get(lane_idx)
                                && !lane.points.is_empty()
                            {
                                let env: Vec<(Samples, f32)> = lane
                                    .points
                                    .iter()
                                    .map(|&(off, db)| (Samples::from(off), db as f32))
                                    .collect();
                                (0.0, env)
                            } else {
                                (reg.clip_gain.unwrap_or(0.0) as f32, Vec::new())
                            };

                            let clip_end = clip_start + base_len;
                            let mut matched_xf_pre: Option<u64> = None;
                            let mut matched_xf_info: Option<(Samples, &ptx_format::decode::clips::FadeObject, i64, i64)> = None;
                            let fade_in = fades_at_pos
                                .iter()
                                .find_map(|(fs, f_obj, sc_f)| {
                                    let kind = f_obj.fade_type.as_str();
                                    let total_len = i64::try_from(f_obj.length2.unwrap_or(f_obj.length)).unwrap_or(sc_f.len);
                                    if kind == Some("fade_in") && *fs == clip_start {
                                        Some(*sc_f)
                                    } else if kind == Some("crossfade") {
                                        let is_centered = f_obj.length2.is_some();
                                        let pre = i64::try_from(f_obj.length).unwrap_or(0);
                                        if *fs == clip_start || (is_centered && *fs + pre == clip_start) {
                                            let mut f = *sc_f;
                                            f.len = total_len;
                                            if is_centered {
                                                matched_xf_pre = Some(f_obj.length);
                                                matched_xf_info = Some((*fs, *f_obj, pre, total_len));
                                            } else {
                                                matched_xf_pre = Some(0);
                                            }
                                            Some(f)
                                        } else {
                                            None
                                        }
                                    } else {
                                        None
                                    }
                                })
                                .unwrap_or_default();
                            let fade_out = fades_at_pos
                                .iter()
                                .find_map(|(fs, f_obj, sc_f)| {
                                    let kind = f_obj.fade_type.as_str();
                                    let total_len = i64::try_from(f_obj.length2.unwrap_or(f_obj.length)).unwrap_or(sc_f.len);
                                    if kind == Some("fade_out") && (*fs + sc_f.len == clip_end || *fs == clip_end) {
                                        Some(*sc_f)
                                    } else if kind == Some("crossfade") {
                                        let is_centered = f_obj.length2.is_some();
                                        let pre = i64::try_from(f_obj.length).unwrap_or(0);
                                        let centered_hit = is_centered
                                            && (*fs + pre == clip_end
                                                || *fs == clip_end
                                                || (clip_end <= *fs
                                                    && *fs - pre < clip_end
                                                    && *fs - pre + total_len > clip_end));
                                        let post_hit = !is_centered
                                            && (*fs == clip_end || *fs + total_len == clip_end);
                                        if centered_hit || post_hit {
                                            let mut f = *sc_f;
                                            f.len = total_len;
                                            Some(f)
                                        } else {
                                            None
                                        }
                                    } else {
                                        None
                                    }
                                })
                                .unwrap_or_default();

                            if sync_off > 0 {
                                report.record(
                                    "sync_points",
                                    format!("{}:{}", pt_tr.name, reg.name),
                                    Fidelity::Native,
                                    None,
                                );
                            }

                            let (iter_smp, count) = if let Some(lp) = &p.loop_info {
                                resolve_loop_iter_samples(lp, clip_start, base_len, &tempo, sr)
                            } else {
                                (base_len, 1)
                            };
                            let loop_group_id = if p.loop_info.is_some() && opts.loop_handling == LoopHandling::Faithful {
                                next_id += 1;
                                Some(next_id)
                            } else {
                                None
                            };
                            for iter_i in 0..count {
                                next_id += 1;
                                let cid = ClipId(next_id);
                                let mut c = Clip::audio(
                                    cid,
                                    &reg.name,
                                    src_id,
                                    i64::try_from(reg.start).unwrap_or(0),
                                    clip_start + i64::try_from(iter_i).unwrap_or(0) * iter_smp,
                                    iter_smp,
                                );
                                c.muted = p.muted;
                                c.gain_db = gain_db;
                                c.gain_env = gain_env.clone();
                                c.sync_point = sync_off;
                                c.group = *grp_id_opt;
                                c.loop_id = loop_group_id;
                                if iter_i == 0 {
                                    c.fade_in = fade_in;
                                }
                                if iter_i + 1 == count {
                                    c.fade_out = fade_out;
                                }
                                c.clamp_fades();
                                target_clips.push(c);
                                clip_xf_infos.push(if iter_i == 0 { matched_xf_info } else { None });
                            }
                            if p.loop_info.is_some() || matched_xf_pre.is_some() || split_pair_files.is_some() {
                                let lp_opt = p.loop_info.as_ref();
                                let cc = carry.clips.entry(reg.name.clone()).or_default();
                                if let Some(lp) = lp_opt {
                                    cc.loop_mode = Some(lp.mode);
                                    cc.loop_bars = Some(lp.bars);
                                    cc.loop_beats = Some(lp.beats);
                                    cc.loop_ticks = Some(lp.ticks);
                                    cc.loop_count = Some(lp.count);
                                    cc.loop_iter_ticks = lp.iter_ticks;
                                    cc.loop_iter_samples = lp.iter_samples;
                                    report.record("loops", format!("{}:{}", pt_tr.name, reg.name), Fidelity::Native, None);
                                }
                                if let Some(pre_u) = matched_xf_pre {
                                    cc.crossfade_pre_roll = Some(pre_u);
                                }
                                if let Some(sp) = split_pair_files {
                                    cc.split_pair = Some(sp);
                                }
                            }
                        }

                        // Extend overlapping SoundCraft crossfade clips when handles exist on both clips
                        for ci in 1..target_clips.len() {
                            if let Some((fs, f_obj, pre, total_len)) = clip_xf_infos.get(ci).and_then(|x| *x)
                                && f_obj.length2.is_some()
                            {
                                let cut = if fs + pre == target_clips[ci].start {
                                    fs + pre
                                } else {
                                    fs
                                };
                                let xf_start = cut - pre;
                                let xf_end = xf_start + total_len;
                                let (left_slice, right_slice) = target_clips.split_at_mut(ci);
                                let c_left = &mut left_slice[ci - 1];
                                let c_right = &mut right_slice[0];
                                if c_left.loop_id.is_none()
                                    && c_right.loop_id.is_none()
                                    && c_left.end() <= c_right.start
                                    && let (
                                        craft_scraft_format::ClipContent::Audio { source: ls, offset: lo },
                                        craft_scraft_format::ClipContent::Audio { offset: ro, .. },
                                    ) = (&c_left.content, &mut c_right.content)
                                {
                                    let ext_l = (xf_end - c_left.end()).max(0);
                                    let ext_r = (c_right.start - xf_start).max(0);
                                    let l_frames = source_frames_map.get(ls).copied().unwrap_or(0);
                                    let l_avail = u64::try_from(*lo + c_left.length + ext_l).is_ok_and(|end| end <= l_frames);
                                    let r_avail = *ro >= ext_r;
                                    if l_avail && r_avail && (ext_l > 0 || ext_r > 0) {
                                        c_left.length += ext_l;
                                        c_right.start -= ext_r;
                                        *ro -= ext_r;
                                        c_right.length += ext_r;
                                        c_left.clamp_fades();
                                        c_right.clamp_fades();
                                    }
                                }
                            }
                        }
                    }
                    if is_active {
                        sc_clips = target_clips;
                    } else if !target_clips.is_empty() {
                        let mut alt_pl = Playlist::new(pl_name);
                        alt_pl.clips = target_clips;
                        alt_pl.sort();
                        alt_playlists.push(alt_pl);
                        report.record("playlists", format!("{}:{pl_name}", pt_tr.name), Fidelity::Native, None);
                    }
                }
            }
            Some(TrackPlaylists::Midi { active_index, .. }) => {
                if let Some(m_places) = doc.placements.get(*active_index) {
                    for mp in m_places {
                        let Some(reg) = midi_regions.get(usize::from(mp.region)) else {
                            continue;
                        };
                        let chunk = reg
                            .list
                            .and_then(|li| usize::try_from(li).ok())
                            .and_then(|i| doc.midi_lists.get(i));
                        let seq = chunk.map_or_else(Sequence::default, build_midi_sequence);
                        let start_ticks = mp.ticks.unwrap_or(0);
                        let clip_start = if let Some(s) = mp.samples {
                            s
                        } else {
                            ptx_ticks_to_samples(start_ticks, &tempo, sr)
                        };
                        let end_smp = ptx_ticks_to_samples(start_ticks.saturating_add(reg.length), &tempo, sr);
                        let base_len = (end_smp - clip_start).max(1);
                        let (iter_smp, count) = if let Some(lp) = &mp.loop_info {
                            resolve_loop_iter_samples(lp, clip_start, base_len, &tempo, sr)
                        } else {
                            (base_len, 1)
                        };
                        let loop_group_id = if mp.loop_info.is_some() && opts.loop_handling == LoopHandling::Faithful {
                            next_id += 1;
                            Some(next_id)
                        } else {
                            None
                        };
                        for iter_i in 0..count {
                            next_id += 1;
                            let mut c = Clip::midi(
                                ClipId(next_id),
                                &reg.name,
                                clip_start + i64::try_from(iter_i).unwrap_or(0) * iter_smp,
                                iter_smp,
                                seq.clone(),
                            );
                            c.muted = mp.muted;
                            c.loop_id = loop_group_id;
                            sc_clips.push(c);
                        }
                        if let Some(ch) = chunk
                            && (!ch.sysex.is_empty() || !ch.mpe_curves.is_empty())
                        {
                            let cc = carry.clips.entry(reg.name.clone()).or_default();
                            if !ch.sysex.is_empty() {
                                cc.sysex = ch.sysex.clone();
                                report.record("midi", format!("{}:{}:sysex", pt_tr.name, reg.name), Fidelity::Carry, None);
                            }
                            if !ch.mpe_curves.is_empty() {
                                cc.mpe_curves = ch.mpe_curves.clone();
                                report.record(
                                    "midi",
                                    format!("{}:{}:mpe_curves", pt_tr.name, reg.name),
                                    if opts.carry { Fidelity::Carry } else { Fidelity::Approx },
                                    Some("per-note MPE curves forwarded to MIDI channels and preserved in .ptxcarry.json".to_owned()),
                                );
                            }
                        }
                    }
                }
            }
            None => {}
        }

        if let Some(pl) = sc_tr.playlists.first_mut() {
            pl.clips = sc_clips;
            pl.sort();
        } else {
            let mut pl = Playlist::new(&pt_tr.name);
            pl.clips = sc_clips;
            pl.sort();
            sc_tr.playlists.push(pl);
        }
        sc_tr.playlists.extend(alt_playlists);

        if tr_carry != CarryTrack::default() {
            carry.tracks.insert(pt_tr.name.clone(), tr_carry);
        }
        report.record("tracks", pt_tr.name.clone(), Fidelity::Native, None);
        session.tracks.push(sc_tr);
    }

    // 4. Memory locations / Markers
    for m in &doc.markers {
        next_id += 1;
        let to_smp = |pos: u64, samples_opt: Option<u64>| -> Samples {
            if m.unit == "samples"
                && let Some(s) = samples_opt
            {
                return i64::try_from(s).unwrap_or(0);
            }
            ptx_ticks_to_samples(pos, &tempo, sr)
        };
        let start = to_smp(m.ticks, m.samples);
        let end = if m.unit == "samples" {
            i64::try_from(m.end).unwrap_or(start).max(start)
        } else if m.end > m.ticks {
            to_smp(m.end, None)
        } else {
            start
        };
        let kind = match m.kind.as_str().unwrap_or("marker") {
            "selection" => MarkerKind::Selection,
            "none" => MarkerKind::None,
            _ => MarkerKind::Marker,
        };
        session.markers.push(MemoryLocation {
            id: MarkerId(next_id),
            number: u32::from(m.number),
            name: m.name.clone(),
            kind,
            start,
            end,
            comments: m.comment.clone().unwrap_or_default(),
            color: None,
            ruler: 1,
            track: None,
        });
        report.record("markers", m.name.clone(), Fidelity::Native, None);
    }

    // 5. Groups (skip synthetic `<ALL>` on SC side or keep user groups with letter 'a'..'z')
    let mut letter_idx = 0u8;
    for gd in &doc.group_details {
        if gd.name == "<ALL>" {
            continue;
        }
        next_id += 1;
        let members: Vec<TrackId> = gd
            .members
            .iter()
            .filter_map(|nm| track_name_to_id.get(nm).copied())
            .collect();
        let letter = char::from(b'a'.saturating_add(letter_idx.min(25)));
        letter_idx = letter_idx.saturating_add(1);
        session.groups.push(Group {
            id: GroupId(next_id),
            name: gd.name.clone(),
            letter,
            members,
            edit: (gd.group_type & 1) != 0,
            mix: (gd.group_type & 2) != 0 || gd.group_type == 0,
            active: gd.enabled,
            color: TRACK_COLORS[usize::from(letter_idx) % TRACK_COLORS.len()],
            attributes: Vec::new(),
        });
        report.record("groups", gd.name.clone(), Fidelity::Native, None);
    }

    session.next_id = next_id + 1;
    session.sanitize();

    if opts.strict && report.has_loss() {
        let msg = report
            .first_loss_message()
            .unwrap_or_else(|| "lossy conversion".to_owned());
        return Err(ConvertError::Strict(msg));
    }

    let carry_out = opts.carry.then_some(carry);
    Ok((session, report, carry_out))
}

trait CharSlotExt {
    fn checked_sub_u8_or_idx(self) -> Option<usize>;
}
impl CharSlotExt for char {
    fn checked_sub_u8_or_idx(self) -> Option<usize> {
        if ('a'..='j').contains(&self) {
            Some(usize::from((self as u8) - b'a'))
        } else {
            None
        }
    }
}
