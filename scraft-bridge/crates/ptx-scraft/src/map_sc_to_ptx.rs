// Version: 0.7.0 (beta) | Date: 2026-11-27
//! Clean-room `SoundCraft Session -> PtxBuildSpec` converter.

use std::collections::{BTreeMap, HashMap};
use std::path::Path;

use craft_midi::CtrlKind;
use craft_scraft_format::{
    AutoParam, AutomationLane, AutomationMode, BitDepthSetting, ChannelFormat, Clip, ClipContent,
    EditMode, FileFormat, MarkerKind, Route, Session, SourceId, Tool, TrackKind,
};
use craft_scraft_format::soundcraft_time::SampleRate;
use ptx_format::encode::spec::{
    BuildAudioClip, BuildAudioFile, BuildAutoLane, BuildBus, BuildClipLoop, BuildEditState,
    BuildGroup, BuildInsert, BuildInsertAutoLane, BuildKeySig, BuildMarker, BuildMeterPoint,
    BuildMidiClip, BuildMidiCtrl, BuildMidiNote, BuildParamVal, BuildSend, BuildTimebase,
    BuildTrack, BuildTrackKind, PtxBuildSpec,
};

use crate::automation::{
    craft_ticks_to_ptx_ticks, samples_to_ptx_ticks, samples_to_tc_string, sc_crossfade_to_ptx,
    sc_db_to_tenths, sc_fade_to_ptx, sc_frame_rate_to_ptx, sc_keysig_to_ptx, sc_pan_to_ptx,
    sc_vol_lane_to_ptx, tempo_events_to_ptx,
};
use crate::media::{
    inspect_audio_file, materialize_media_ref, materialize_ptx_pcm_wav, resolve_audio_path,
};
use crate::plugins::{
    ScInsertToPtxArgs, carry_insert_to_ptx, load_plugin_config, sc_insert_to_ptx,
    sc_phys_to_pt_norm_with,
};
use crate::report::{CarryClip, CarrySidecar, ConversionReport, Fidelity};
use crate::{ConvertError, ConvertOptions, LoopHandling};

fn route_to_ptx_name(
    route: &Route,
    bus_lookup: &HashMap<craft_scraft_format::BusId, String>,
) -> Option<String> {
    match route {
        Route::Main => Some("Out 1-2".to_owned()),
        Route::Bus(id) => bus_lookup.get(id).cloned(),
        Route::Hardware(s) => Some(s.clone()),
        Route::None => None,
    }
}

fn build_clip_loop(
    carry_opt: Option<&CarryClip>,
    count: usize,
    iter_samples: u64,
    is_ticks: bool,
    iter_ticks: u64,
) -> BuildClipLoop {
    if let Some(c) = carry_opt {
        BuildClipLoop {
            mode: c.loop_mode.unwrap_or(2),
            bars: c.loop_bars.unwrap_or(0),
            beats: c.loop_beats.unwrap_or(0),
            ticks: c.loop_ticks.unwrap_or(0),
            count: u32::try_from(count).unwrap_or(1),
            trim: 0,
            iter: if is_ticks {
                c.loop_iter_ticks.unwrap_or(iter_ticks)
            } else {
                c.loop_iter_samples.unwrap_or(iter_samples)
            },
            is_ticks,
        }
    } else {
        BuildClipLoop {
            mode: 2,
            bars: 0,
            beats: 0,
            ticks: 0,
            count: u32::try_from(count).unwrap_or(1),
            trim: 0,
            iter: if is_ticks { iter_ticks } else { iter_samples },
            is_ticks,
        }
    }
}

fn group_midi_ctrls(seq: &craft_midi::Sequence) -> Vec<BuildMidiCtrl> {
    let mut grouped: BTreeMap<(u8, u8), Vec<(u64, i32)>> = BTreeMap::new();
    for ev in &seq.ctrls {
        let key = match ev.kind {
            CtrlKind::PitchBend => (1, 0),
            CtrlKind::Cc(cc) => (2, cc),
            CtrlKind::Program => (3, 0),
            CtrlKind::ChannelPressure => (4, 0),
            CtrlKind::PolyPressure(k) => (5, k),
        };
        grouped
            .entry(key)
            .or_default()
            .push((craft_ticks_to_ptx_ticks(ev.tick), ev.value));
    }
    grouped
        .into_iter()
        .map(|((kind, number), points)| BuildMidiCtrl {
            kind,
            number,
            points,
        })
        .collect()
}

fn decode_hex_bytes(hex: &str) -> Vec<u8> {
    let bytes = hex.as_bytes();
    let mut out = Vec::with_capacity(bytes.len() / 2);
    let (pairs, _) = bytes.as_chunks::<2>();
    for pair in pairs {
        if let Ok(s) = std::str::from_utf8(pair)
            && let Ok(v) = u8::from_str_radix(s, 16)
        {
            out.push(v);
        }
    }
    out
}

/// Convert a SoundCraft [`Session`] (+ optional [`CarrySidecar`]) into a [`PtxBuildSpec`].
///
/// # Errors
/// Returns `ConvertError` on media copy errors or `--strict` loss refusal.
pub fn scraft_to_ptx_spec(
    session: &Session,
    scraft_dir: &Path,
    out_dir: Option<&Path>,
    carry_opt: Option<&CarrySidecar>,
    opts: &ConvertOptions,
) -> Result<(PtxBuildSpec, ConversionReport), ConvertError> {
    let sr_hz = session.sample_rate.hz().max(8_000);
    let sr = SampleRate::new(sr_hz).unwrap_or(SampleRate::HZ_48000);
    let plugin_cfg = load_plugin_config(opts.plugin_config.as_deref())?;
    let target_label = out_dir
        .map(|d| d.display().to_string())
        .unwrap_or_else(|| scraft_dir.display().to_string());
    let mut report = ConversionReport::new(
        "scraft_to_ptx",
        &session.name,
        &target_label,
        opts.media_mode.as_str(),
        opts.loop_handling.as_str(),
    );

    let (bit_depth, is_float) = match session.bit_depth {
        BitDepthSetting::Int16 => (16, false),
        BitDepthSetting::Int24 => (24, false),
        BitDepthSetting::Float32 => (32, true),
    };
    let is_aiff = session
        .sources
        .first()
        .is_some_and(|s| s.format == FileFormat::Aiff);

    let carry = carry_opt.filter(|_| opts.carry);

    let tempo_pts = tempo_events_to_ptx(&session.tempo);
    for t in &tempo_pts {
        report.record("tempo", format!("tempo@{}={:.3}", t.ticks, t.bpm), Fidelity::Native, None);
    }

    let meter_pts: Vec<BuildMeterPoint> = session
        .tempo
        .meters()
        .iter()
        .map(|m| {
            let bar = u32::try_from(session.tempo.bar_beat_at_tick(m.tick).bar.max(1)).unwrap_or(1);
            report.record("meter", format!("{}/{}@{bar}", m.numerator, m.denominator), Fidelity::Native, None);
            BuildMeterPoint {
                ticks: craft_ticks_to_ptx_ticks(m.tick),
                bar,
                numerator: m.numerator.max(1),
                denominator: m.denominator.max(1),
            }
        })
        .collect();

    let key_signatures: Vec<BuildKeySig> = session
        .key_signatures
        .iter()
        .map(|(at, label)| {
            let (major, sharps) = sc_keysig_to_ptx(label);
            report.record("key_signatures", format!("{at}:{label}"), Fidelity::Native, None);
            BuildKeySig {
                ticks: samples_to_ptx_ticks(*at, &session.tempo, sr),
                major,
                sharps,
            }
        })
        .collect();

    // Audio files
    let mut source_to_file_idx: HashMap<SourceId, usize> = HashMap::new();
    let mut file_name_to_idx: HashMap<String, usize> = HashMap::new();
    let mut audio_files = Vec::with_capacity(session.sources.len());
    for src in &session.sources {
        let resolved = scraft_dir.join(src.path.replace('\\', "/"));
        let disk_path = if resolved.is_file() {
            Some(resolved)
        } else {
            resolve_audio_path(scraft_dir, &src.path)
        };
        let mut inspected = disk_path.as_deref().and_then(|p| inspect_audio_file(p).ok());
        let mut file_name = Path::new(&src.path.replace('\\', "/"))
            .file_name()
            .and_then(|n| n.to_str())
            .filter(|n| !n.is_empty())
            .map(ToOwned::to_owned)
            .unwrap_or_else(|| format!("{}.wav", src.name));

        let mut converted_compressed = false;
        if let Some(ref full) = disk_path {
            let ext_is_pcm = full
                .extension()
                .and_then(|e| e.to_str())
                .is_some_and(|e| matches!(e.to_ascii_lowercase().as_str(), "wav" | "aif" | "aiff"));
            let fmt_is_pcm = matches!(src.format, FileFormat::Wav | FileFormat::Aiff) && ext_is_pcm;
            if !fmt_is_pcm {
                let target_root = out_dir.unwrap_or(scraft_dir);
                let (_wav_path, conv_insp) = materialize_ptx_pcm_wav(full, src, target_root)?;
                file_name = conv_insp.file_name.clone();
                inspected = Some(conv_insp);
                converted_compressed = true;
            } else {
                let _ = materialize_media_ref(full, scraft_dir, out_dir, &file_name, opts.media_mode)?;
            }
        }

        let carry_af = carry.and_then(|c| c.audio_files.iter().find(|a| a.file_name == file_name));
        let umid_file_id = carry_af
            .and_then(|a| a.umid.as_deref())
            .map(decode_hex_bytes)
            .filter(|b| b.len() >= 8)
            .and_then(|b| {
                let slice = if b.len() == 32 {
                    &b[16..24]
                } else {
                    &b[b.len() - 8..]
                };
                slice.try_into().ok()
            });

        let af = match inspected {
            Some(ref a) => BuildAudioFile {
                file_name: file_name.clone(),
                sample_rate: a.sample_rate,
                channels: u8::try_from(a.channels).unwrap_or(1),
                bit_depth: a.bit_depth,
                is_float: a.is_float,
                is_aiff: a.is_aiff,
                frames: a.frames,
                data_offset: a.data_offset,
                filetime: carry_af.map_or(a.filetime, |c| c.filetime),
                umid_file_id,
            },
            None => BuildAudioFile {
                file_name: file_name.clone(),
                sample_rate: src.sample_rate.max(8_000),
                channels: u8::try_from(src.channels.max(1)).unwrap_or(1),
                bit_depth: carry_af.map_or(bit_depth, |c| c.bit_depth),
                is_float: carry_af.map_or(is_float, |c| c.is_float),
                is_aiff: carry_af.map_or(src.format == FileFormat::Aiff, |c| c.is_aiff),
                frames: src.frames,
                data_offset: carry_af.map_or(44, |c| c.data_offset),
                filetime: carry_af.map_or(133_000_000_000_000_000, |c| c.filetime),
                umid_file_id,
            },
        };
        let idx = audio_files.len();
        source_to_file_idx.insert(src.id, idx);
        file_name_to_idx.insert(file_name.clone(), idx);
        audio_files.push(af);
        if converted_compressed {
            report.record(
                "media",
                file_name,
                Fidelity::Approx,
                Some("decoded compressed SoundCraft audio to 24-bit BWF WAV".to_owned()),
            );
        } else {
            report.record("media", file_name, Fidelity::Native, None);
        }
    }

    // Busses & Track ID lookup
    let bus_lookup: HashMap<_, _> = session
        .busses
        .iter()
        .map(|b| (b.id, b.name.clone()))
        .collect();
    let busses: Vec<BuildBus> = session
        .busses
        .iter()
        .map(|b| BuildBus {
            name: b.name.clone(),
            stereo: b.format != ChannelFormat::Mono,
        })
        .collect();

    let track_id_to_name: HashMap<_, _> = session
        .tracks
        .iter()
        .map(|t| (t.id, t.name.clone()))
        .collect();

    // Tracks
    let mut tracks = Vec::with_capacity(session.tracks.len());
    for (tidx, sc_tr) in session.tracks.iter().enumerate() {
        let tr_carry = carry.and_then(|c| c.tracks.get(&sc_tr.name));
        let kind = match sc_tr.kind {
            TrackKind::Audio => BuildTrackKind::Audio,
            TrackKind::Aux => BuildTrackKind::Aux,
            TrackKind::Master => BuildTrackKind::Master,
            TrackKind::Midi => BuildTrackKind::Midi,
            TrackKind::Instrument => BuildTrackKind::Instrument,
            TrackKind::Folder => {
                if tr_carry.is_some_and(|c| c.ptx_kind == Some(11))
                    || (tr_carry.and_then(|c| c.ptx_kind).is_none()
                        && matches!(sc_tr.mixer.input, Route::None)
                        && matches!(sc_tr.mixer.output, Route::None))
                {
                    BuildTrackKind::BasicFolder
                } else {
                    BuildTrackKind::RoutingFolder
                }
            }
            TrackKind::Vca | TrackKind::Video => {
                report.record(
                    "tracks",
                    format!("{}:{:?}", sc_tr.name, sc_tr.kind),
                    Fidelity::Absent,
                    Some("Pro Tools Intro does not support VCA or Video tracks".to_owned()),
                );
                continue;
            }
        };

        let to_ticks = kind == BuildTrackKind::Midi || kind == BuildTrackKind::Instrument;
        let folder_name = sc_tr
            .folder
            .and_then(|id| track_id_to_name.get(&id).cloned());
        let input_bus = route_to_ptx_name(&sc_tr.mixer.input, &bus_lookup)
            .filter(|n| n != "Out 1-2");
        let output_bus = route_to_ptx_name(&sc_tr.mixer.output, &bus_lookup)
            .unwrap_or_else(|| "Out 1-2".to_owned());

        let mut volume_lane = Vec::new();
        let mut pan_lane = Vec::new();
        let mut pan_lane_r = Vec::new();
        let mut mute_lane = Vec::new();
        let mut send_vol_lanes: BTreeMap<usize, Vec<(u64, i16)>> = BTreeMap::new();
        let mut send_pan_lanes: BTreeMap<usize, Vec<(u64, i16)>> = BTreeMap::new();
        let mut send_mute_lanes: BTreeMap<usize, Vec<(u64, i16)>> = BTreeMap::new();
        for lane in &sc_tr.automation {
            let map_pan = |l: &AutomationLane| -> Vec<(u64, i16)> {
                l.points
                    .iter()
                    .map(|pt| {
                        let t = if to_ticks {
                            samples_to_ptx_ticks(pt.at, &session.tempo, sr)
                        } else {
                            u64::try_from(pt.at.max(0)).unwrap_or(0)
                        };
                        (t, sc_pan_to_ptx(pt.value))
                    })
                    .collect()
            };
            let map_mute = |l: &AutomationLane| -> Vec<(u64, i16)> {
                l.points
                    .iter()
                    .map(|pt| {
                        let t = if to_ticks {
                            samples_to_ptx_ticks(pt.at, &session.tempo, sr)
                        } else {
                            u64::try_from(pt.at.max(0)).unwrap_or(0)
                        };
                        (t, i16::from(pt.value >= 0.5))
                    })
                    .collect()
            };
            match &lane.param {
                AutoParam::Volume => {
                    volume_lane = sc_vol_lane_to_ptx(lane, to_ticks, &session.tempo, sr);
                }
                AutoParam::Pan(0) => {
                    pan_lane = map_pan(lane);
                }
                AutoParam::Pan(1) => {
                    pan_lane_r = map_pan(lane);
                }
                AutoParam::Mute => {
                    mute_lane = map_mute(lane);
                }
                AutoParam::SendLevel(slot) => {
                    send_vol_lanes.insert(
                        usize::from(*slot),
                        sc_vol_lane_to_ptx(lane, to_ticks, &session.tempo, sr),
                    );
                }
                AutoParam::SendPan(slot) => {
                    send_pan_lanes.insert(usize::from(*slot), map_pan(lane));
                }
                AutoParam::SendMute(slot) => {
                    send_mute_lanes.insert(usize::from(*slot), map_mute(lane));
                }
                _ => {}
            }
        }

        // Software instrument reporting (TrackKind::Instrument)
        if sc_tr.kind == TrackKind::Instrument
            && let Some(inst) = &sc_tr.instrument
        {
            report.record(
                "plugins",
                format!("{}:instrument:{}", sc_tr.name, inst.plugin),
                Fidelity::Absent,
                Some("SoundCraft software instrument requires --render-opaque-stems audio bounce".to_owned()),
            );
        }

        // Inserts (mapped SC slots + carry-only PT slots like Click II) + Mixer Trim/Phase synthesis if needed
        let mut inserts = Vec::new();
        let max_slots = sc_tr.mixer.inserts.len().max(
            tr_carry
                .and_then(|tc| tc.inserts.iter().map(|ci| ci.slot_index + 1).max())
                .unwrap_or(0),
        );
        for slot_idx in 0..max_slots {
            let carry_ins = tr_carry
                .and_then(|tc| tc.inserts.iter().find(|ci| ci.slot_index == slot_idx));
            let Some(sc_ins) = sc_tr.mixer.inserts.get(slot_idx).and_then(Option::as_ref) else {
                if let Some(ci) = carry_ins
                    && let Some(bi) = carry_insert_to_ptx(slot_idx, &sc_tr.name, ci, &mut report)
                {
                    inserts.push(bi);
                }
                continue;
            };
            if tr_carry.is_some_and(|tc| tc.synthesized_user_delay_slot == Some(slot_idx))
                && sc_ins.plugin == "time_shift"
            {
                continue;
            }
            if let Some(bi) = sc_insert_to_ptx(
                &ScInsertToPtxArgs {
                    slot_idx,
                    ins: sc_ins,
                    track_name: &sc_tr.name,
                    track_auto: &sc_tr.automation,
                    tempo: &session.tempo,
                    sr,
                    to_ticks,
                    carry_opt: carry_ins,
                    plugin_cfg: &plugin_cfg,
                },
                &mut report,
            ) {
                inserts.push(bi);
            }
        }

        // Synthesize Trim insert when Mixer.trim_db != 0 or phase_invert or u8::MAX trim lane is active
        let trim_auto_lane: Option<&AutomationLane> = sc_tr.automation.iter().find(|l| {
            matches!(&l.param, AutoParam::Plugin { slot, param } if *slot == u8::MAX && param == "trim")
        });
        let needs_trim = sc_tr.mixer.trim_db.abs() > 0.01
            || sc_tr.mixer.phase_invert
            || trim_auto_lane.is_some();
        if needs_trim && let Some(open_slot) = (0..10).find(|s| inserts.iter().all(|i| i.slot_index != *s)) {
            let mut params = BTreeMap::new();
            params.insert("gain_db".to_owned(), BuildParamVal::Float(f64::from(sc_tr.mixer.trim_db)));
            params.insert("phase_invert".to_owned(), BuildParamVal::Bool(sc_tr.mixer.phase_invert));
            let mut auto = Vec::new();
            if let Some(tl) = trim_auto_lane {
                let pts = tl
                    .points
                    .iter()
                    .map(|p| {
                        let t = if to_ticks {
                            samples_to_ptx_ticks(p.at, &session.tempo, sr)
                        } else {
                            u64::try_from(p.at.max(0)).unwrap_or(0)
                        };
                        (
                            t,
                            sc_phys_to_pt_norm_with(&plugin_cfg, "trim", "gain", f64::from(p.value)),
                        )
                    })
                    .collect();
                auto.push(BuildInsertAutoLane {
                    param_name: "Gain".to_owned(),
                    param_id: "gain".to_owned(),
                    param_index: 0,
                    points: pts,
                });
            }
            inserts.push(BuildInsert {
                slot_index: open_slot,
                plugin_name: "Trim".to_owned(),
                bypass: false,
                active: true,
                multi_mono: false,
                params,
                automation: auto,
            });
            report.record("mixer", format!("{}:trim_synth", sc_tr.name), Fidelity::Native, None);
        }

        if let Some(sp) = &sc_tr.mixer.surround
            && sp.lfe_db > -140.0
        {
            report.record(
                "mixer",
                format!("{}:lfe_db={:.1}", sc_tr.name, sp.lfe_db),
                Fidelity::Carry,
                Some("LFE surround send requires Pro Tools multichannel bed".to_owned()),
            );
        }

        // Sends
        let mut sends = Vec::new();
        for (sidx, send_opt) in sc_tr.mixer.sends.iter().enumerate() {
            let Some(snd) = send_opt else {
                continue;
            };
            let Some(dest_name) = route_to_ptx_name(&snd.target, &bus_lookup) else {
                continue;
            };
            sends.push(BuildSend {
                slot_index: sidx,
                bus_name: dest_name,
                level_tenths_db: sc_db_to_tenths(snd.level_db),
                pan: sc_pan_to_ptx(snd.pan),
                mute: snd.mute,
                pre_fader: snd.pre_fader,
                active: true,
                volume_points: send_vol_lanes.remove(&sidx).unwrap_or_default(),
                mute_points: send_mute_lanes.remove(&sidx).unwrap_or_default(),
                pan_points: send_pan_lanes.remove(&sidx).unwrap_or_default(),
            });
        }

        // Clips on active playlist (coalescing contiguous `loop_id` runs when `Faithful`)
        let mut audio_clips = Vec::new();
        let mut midi_clips = Vec::new();
        if let Some(pl) = sc_tr.playlist() {
            let clips: &[Clip] = &pl.clips;
            let mut suppress_fade_out = vec![false; clips.len()];
            let mut trim_end_override: Vec<Option<i64>> = vec![None; clips.len()];
            let mut xfade_in_override: Vec<Option<(i64, i64, Option<u64>)>> = vec![None; clips.len()];
            for idx_c in 0..clips.len().saturating_sub(1) {
                let ca = &clips[idx_c];
                let cb = &clips[idx_c + 1];
                if ca.loop_id.is_some() || cb.loop_id.is_some() {
                    continue;
                }
                if !matches!(ca.content, ClipContent::Audio { .. })
                    || !matches!(cb.content, ClipContent::Audio { .. })
                {
                    continue;
                }
                if ca.fade_out.len <= 0 || cb.fade_in.len <= 0 {
                    continue;
                }
                let cb_carry_pre = carry
                    .and_then(|c| c.clips.get(&cb.name))
                    .and_then(|cc| cc.crossfade_pre_roll);
                if ca.end() > cb.start {
                    let overlap = ca.end() - cb.start;
                    let pre = cb_carry_pre
                        .map(|u| i64::try_from(u).unwrap_or(overlap / 2))
                        .unwrap_or(overlap / 2)
                        .clamp(1, overlap);
                    let cut = cb.start + pre;
                    if cut > ca.start && cut < cb.end() {
                        suppress_fade_out[idx_c] = true;
                        trim_end_override[idx_c] = Some(cut);
                        xfade_in_override[idx_c + 1] =
                            Some((cut, pre, u64::try_from(pre).ok().filter(|&p| p > 0)));
                    }
                } else {
                    let gap = cb.start - ca.end();
                    if gap < cb.fade_in.len
                        && (ca.fade_out.len == cb.fade_in.len || cb_carry_pre.is_some())
                    {
                        let pre_opt = match cb_carry_pre {
                            Some(0) => None,
                            Some(p) => Some(p),
                            None => Some(u64::try_from((cb.fade_in.len / 2).max(1)).unwrap_or(1)),
                        };
                        suppress_fade_out[idx_c] = true;
                        xfade_in_override[idx_c + 1] = Some((cb.start, 0, pre_opt));
                    }
                }
            }

            let mut i = 0usize;
            while i < clips.len() {
                let c0 = &clips[i];
                let mut run_len = 1usize;
                if opts.loop_handling == LoopHandling::Faithful
                    && let Some(lid) = c0.loop_id
                {
                    while i + run_len < clips.len() {
                        let nxt = &clips[i + run_len];
                        if nxt.loop_id == Some(lid)
                            && nxt.name == c0.name
                            && nxt.length == c0.length
                            && nxt.start == c0.start + i64::try_from(run_len).unwrap_or(0) * c0.length
                        {
                            run_len += 1;
                        } else {
                            break;
                        }
                    }
                }
                let clip_carry = carry.and_then(|c| c.clips.get(&c0.name));

                match &c0.content {
                    ClipContent::Audio { source, offset } => {
                        if (c0.stretch - 1.0).abs() > 1e-4 {
                            report.record(
                                "clips",
                                format!("{}:{}:stretch={:.3}", sc_tr.name, c0.name, c0.stretch),
                                Fidelity::Approx,
                                Some("clip time-stretch not written to PT Elastic Audio".to_owned()),
                            );
                        }
                        if let Some(&file_idx) = source_to_file_idx.get(source) {
                            let mut file_indices = vec![file_idx];
                            if sc_tr.format != ChannelFormat::Mono
                                && let Some((fl, fr)) = clip_carry.and_then(|cc| cc.split_pair.as_ref())
                                && let (Some(&il), Some(&ir)) = (file_name_to_idx.get(fl), file_name_to_idx.get(fr))
                            {
                                file_indices = vec![il, ir];
                            } else if sc_tr.format != ChannelFormat::Mono
                                && let Some(src_obj) = session.source(*source)
                            {
                                let base = src_obj.name.strip_suffix(".stereo").unwrap_or(&src_obj.name);
                                let fl = format!("{base}.L.wav");
                                let fr = format!("{base}.R.wav");
                                if let (Some(&il), Some(&ir)) = (file_name_to_idx.get(&fl), file_name_to_idx.get(&fr)) {
                                    file_indices = vec![il, ir];
                                }
                            }

                            let clip_gain_points = if !c0.gain_env.is_empty() {
                                c0.gain_env
                                    .iter()
                                    .map(|&(at, db)| (u32::try_from(at.max(0)).unwrap_or(0), db + c0.gain_db))
                                    .collect()
                            } else if c0.gain_db.abs() > 0.005 {
                                vec![(0, c0.gain_db)]
                            } else {
                                Vec::new()
                            };
                            let (eff_start, eff_offset, eff_len_base) =
                                if let Some((cut, off_shift, _)) = xfade_in_override[i] {
                                    (cut, *offset + off_shift, (c0.end() - cut).max(1))
                                } else if let Some(cut_end) = trim_end_override[i] {
                                    (c0.start, *offset, (cut_end - c0.start).max(1))
                                } else {
                                    (c0.start, *offset, c0.length.max(1))
                                };
                            let fade_in = if let Some((_, _, pre)) = xfade_in_override[i] {
                                sc_crossfade_to_ptx(c0.fade_in, pre, &mut report, &c0.name)
                            } else {
                                sc_fade_to_ptx(c0.fade_in, true, &mut report, &c0.name)
                            };
                            let fade_out = if suppress_fade_out[i + run_len - 1] {
                                None
                            } else {
                                sc_fade_to_ptx(
                                    clips[i + run_len - 1].fade_out,
                                    false,
                                    &mut report,
                                    &c0.name,
                                )
                            };
                            let start_pos = if to_ticks {
                                samples_to_ptx_ticks(eff_start, &session.tempo, sr)
                            } else {
                                u64::try_from(eff_start.max(0)).unwrap_or(0)
                            };
                            let iter_smp = u64::try_from(eff_len_base.max(1)).unwrap_or(1);
                            let sync_offset = (c0.sync_point > 0)
                                .then(|| u64::try_from(c0.sync_point).unwrap_or(0));
                            if sync_offset.is_some() {
                                report.record(
                                    "sync_points",
                                    format!("{}:{}", sc_tr.name, c0.name),
                                    Fidelity::Native,
                                    None,
                                );
                            }
                            let clip_loop = (run_len > 1 || (opts.loop_handling == LoopHandling::Faithful && c0.loop_id.is_some())).then(|| {
                                build_clip_loop(clip_carry, run_len, iter_smp, to_ticks, 0)
                            });
                            audio_clips.push(BuildAudioClip {
                                name: c0.name.clone(),
                                file_indices,
                                file_offset: u64::try_from(eff_offset.max(0)).unwrap_or(0),
                                length_samples: iter_smp,
                                start_pos,
                                pos_in_ticks: to_ticks,
                                muted: c0.muted,
                                sync_offset,
                                clip_gain_points,
                                fade_in,
                                fade_out,
                                clip_loop,
                                group: c0.group,
                            });
                        }
                    }
                    ClipContent::Midi { sequence } => {
                        let start_ticks = samples_to_ptx_ticks(c0.start, &session.tempo, sr);
                        let end_ticks = samples_to_ptx_ticks(c0.end(), &session.tempo, sr);
                        let len_ticks = end_ticks.saturating_sub(start_ticks).max(1_000);
                        let notes: Vec<BuildMidiNote> = sequence
                            .notes
                            .iter()
                            .map(|n| BuildMidiNote {
                                start_ticks: craft_ticks_to_ptx_ticks(n.start),
                                key: n.pitch.min(127),
                                length_ticks: craft_ticks_to_ptx_ticks(n.length).max(1),
                                velocity: n.velocity.clamp(1, 127),
                            })
                            .collect();
                        let controllers = group_midi_ctrls(sequence);
                        let sysex = clip_carry
                            .map(|cc| {
                                cc.sysex
                                    .iter()
                                    .map(|(t, hx)| (*t, decode_hex_bytes(hx)))
                                    .collect()
                            })
                            .unwrap_or_default();
                        let clip_loop = (run_len > 1 || (opts.loop_handling == LoopHandling::Faithful && c0.loop_id.is_some())).then(|| {
                            build_clip_loop(clip_carry, run_len, 0, true, len_ticks)
                        });
                        midi_clips.push(BuildMidiClip {
                            name: c0.name.clone(),
                            start_pos: start_ticks,
                            pos_in_ticks: true,
                            length_ticks: len_ticks,
                            notes,
                            controllers,
                            sysex,
                            muted: c0.muted,
                            clip_loop,
                        });
                    }
                    ClipContent::Video { .. } => {
                        report.record("clips", c0.name.clone(), Fidelity::Absent, Some("video clip omitted".to_owned()));
                    }
                }
                i += run_len;
            }
        }

        let colour = tr_carry
            .and_then(|tc| tc.colour)
            .or_else(|| Some(i16::try_from(tidx % 24).unwrap_or(0)));
        let pan = if sc_tr.format != ChannelFormat::Mono && sc_tr.mixer.pan.len() >= 2 {
            vec![
                sc_pan_to_ptx(sc_tr.mixer.pan[0]),
                sc_pan_to_ptx(sc_tr.mixer.pan[1]),
            ]
        } else {
            vec![sc_tr.mixer.pan.first().copied().map_or(0, sc_pan_to_ptx)]
        };
        let mut pan_lanes = Vec::new();
        if !pan_lane.is_empty() {
            pan_lanes.push(BuildAutoLane { points: pan_lane });
        }
        if sc_tr.format != ChannelFormat::Mono && !pan_lane_r.is_empty() {
            if pan_lanes.is_empty() {
                pan_lanes.push(BuildAutoLane { points: Vec::new() });
            }
            pan_lanes.push(BuildAutoLane { points: pan_lane_r });
        }
        let automation_mode = match sc_tr.mixer.automation_mode {
            AutomationMode::Off => 0,
            AutomationMode::Read => 1,
            AutomationMode::Touch => 2,
            AutomationMode::Latch | AutomationMode::TouchLatch => 3,
            AutomationMode::Write => 4,
            AutomationMode::Trim => 1,
        };

        let user_delay = tr_carry.and_then(|tc| tc.user_delay).unwrap_or(0);
        tracks.push(BuildTrack {
            name: sc_tr.name.clone(),
            kind,
            stereo: sc_tr.format != ChannelFormat::Mono,
            folder_name,
            timebase: if to_ticks {
                BuildTimebase::Ticks
            } else {
                BuildTimebase::Samples
            },
            input_bus,
            output_bus: Some(output_bus),
            volume_tenths_db: sc_db_to_tenths(sc_tr.mixer.volume_db),
            pan,
            solo: sc_tr.mixer.solo,
            mute: sc_tr.mixer.mute,
            record_enable: sc_tr.mixer.record_arm,
            inactive: sc_tr.inactive,
            hidden: sc_tr.hidden,
            automation_mode,
            user_delay,
            comment: sc_tr.comments.clone(),
            colour,
            inserts,
            sends,
            audio_clips,
            midi_clips,
            volume_lane: BuildAutoLane { points: volume_lane },
            pan_lanes,
            mute_lane: BuildAutoLane { points: mute_lane },
        });
        report.record("tracks", sc_tr.name.clone(), Fidelity::Native, None);
    }

    // Markers
    let markers: Vec<BuildMarker> = session
        .markers
        .iter()
        .map(|m| {
            let start = samples_to_ptx_ticks(m.start, &session.tempo, sr);
            let end = samples_to_ptx_ticks(m.end.max(m.start), &session.tempo, sr);
            report.record("markers", m.name.clone(), Fidelity::Native, None);
            BuildMarker {
                number: u16::try_from(m.number).unwrap_or(1),
                name: m.name.clone(),
                start,
                end,
                is_ticks: true,
                is_selection: m.kind == MarkerKind::Selection,
                comment: m.comments.clone(),
            }
        })
        .collect();

    // Groups
    let groups: Vec<BuildGroup> = session
        .groups
        .iter()
        .map(|g| {
            let member_track_names = g
                .members
                .iter()
                .filter_map(|id| track_id_to_name.get(id).cloned())
                .collect();
            let gtype = match (g.edit, g.mix) {
                (true, false) => 1,
                (false, true) => 2,
                _ => 3,
            };
            report.record("groups", g.name.clone(), Fidelity::Native, None);
            BuildGroup {
                name: g.name.clone(),
                group_type: gtype,
                enabled: g.active,
                member_track_names,
            }
        })
        .collect();

    if opts.strict && report.has_loss() {
        let msg = report
            .first_loss_message()
            .unwrap_or_else(|| "lossy conversion".to_owned());
        return Err(ConvertError::Strict(msg));
    }

    let base_rate = sc_frame_rate_to_ptx(session.frame_rate);
    let tc_rate_code = match carry
        .and_then(|c| c.timeline.as_ref())
        .and_then(|t| t.timecode_rate_code)
    {
        Some(orig)
            if matches!(
                (orig, base_rate),
                (8, 7) | (14, 13) | (19, 18) | (21, 20)
            ) =>
        {
            orig
        }
        _ => base_rate,
    };
    let pull_code = carry
        .and_then(|c| c.timeline.as_ref())
        .and_then(|t| t.pull_code)
        .filter(|&c| c != 12000);
    let edit_state = {
        let es = &session.edit;
        let has_carry_ss = carry
            .and_then(|c| c.session_settings.as_ref())
            .is_some_and(|ss| {
                ss.edit_mode.is_some()
                    || ss.edit_tool_code.is_some()
                    || ss.smart_tool.is_some()
                    || ss.loop_playback.is_some()
                    || ss.record_mode.is_some()
            });
        let non_default = es.edit_mode != EditMode::Slip
            || es.tool != Tool::Smart
            || es.loop_playback
            || es.record_mode != "normal";
        (has_carry_ss || non_default).then(|| {
            let edit_mode = match es.edit_mode {
                EditMode::Shuffle => 0,
                EditMode::Slip => 1,
                EditMode::Spot => 2,
                EditMode::Grid | EditMode::GridRelative => 3,
            };
            let (smart_tool, edit_tool) = match es.tool {
                Tool::Smart => (true, 4),
                Tool::Zoom => (false, 1),
                Tool::Trim => (false, 3),
                Tool::Selector => (false, 4),
                Tool::Grabber => (false, 5),
                Tool::Scrubber => (false, 6),
                Tool::Pencil => (false, 8),
            };
            let record_mode = match es.record_mode.to_ascii_lowercase().as_str() {
                "loop" => 1,
                "destructive" => 2,
                "quickpunch" => 3,
                "trackpunch" => 4,
                "destructivepunch" => 5,
                _ => 0,
            };
            BuildEditState {
                edit_mode,
                edit_tool,
                smart_tool,
                loop_playback: es.loop_playback,
                record_mode,
            }
        })
    };
    let clip_group_names = carry
        .map(|c| c.clip_group_names.clone())
        .unwrap_or_default();

    let target_dir = out_dir.unwrap_or(scraft_dir);
    let abs_dir = if target_dir.is_absolute() {
        target_dir.to_path_buf()
    } else {
        std::fs::canonicalize(target_dir).unwrap_or_else(|_| target_dir.to_path_buf())
    };
    let mut audio_folder_chain: Vec<String> = if abs_dir.is_absolute() {
        abs_dir
            .components()
            .filter_map(|c| match c {
                std::path::Component::Normal(os) => os.to_str().map(ToOwned::to_owned),
                _ => None,
            })
            .collect()
    } else {
        Vec::new()
    };
    let volume_name = if audio_folder_chain.len() >= 2 && audio_folder_chain[0] == "Volumes" {
        let vol = audio_folder_chain.remove(1);
        audio_folder_chain.remove(0);
        vol
    } else {
        "Macintosh HD".to_owned()
    };

    let spec = PtxBuildSpec {
        sample_rate: sr_hz,
        bit_depth,
        is_float,
        is_aiff,
        xor_seed: carry.map_or(0x5A, |c| c.xor_seed),
        tc_rate_code: Some(tc_rate_code),
        tc_start: Some(samples_to_tc_string(
            session.timecode_start,
            session.frame_rate,
            sr,
        )),
        pull_code,
        edit_state,
        clip_group_names,
        main_out_name: "Out 1-2".to_owned(),
        volume_name,
        audio_folder_chain,
        tempo: tempo_pts,
        meter: meter_pts,
        key_signatures,
        markers,
        groups,
        busses,
        audio_files,
        tracks,
    };
    Ok((spec, report))
}
