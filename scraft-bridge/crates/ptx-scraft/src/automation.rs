// Version: 0.7.0 (beta) | Date: 2026-11-23
//! Tempo-aware time conversions, key signatures, timecode rates, fade mapping,
//! and Pro Tools fader-taper curve subdivision.

use craft_scraft_format::{
    AutoParam, AutomationLane, AutomationPoint, Fade, FadeShape, fader_db_to_pos, fader_pos_to_db,
};
use craft_scraft_format::soundcraft_time::{FrameRate, SampleRate, Samples, TempoEvent, TempoMap};

use crate::report::{ConversionReport, Fidelity};

/// Pro Tools internal tick resolution: `960_000` sub-ticks per quarter note (`1000 * 960 PPQ`).
pub const PTX_SUBTICKS_PER_CRAFT_TICK: f64 = 1000.0;

/// Maximum acceptable dB deviation when subdividing non-linear volume automation curves.
const VOLUME_CURVE_TOLERANCE_DB: f64 = 0.05;
const MAX_SUBDIV_DEPTH: u8 = 8;

/// Convert Pro Tools raw sub-ticks (`960_000` PPQ) to SoundCraft sample position using `tempo`.
#[must_use]
pub fn ptx_ticks_to_samples(ptx_ticks: u64, tempo: &TempoMap, sr: SampleRate) -> Samples {
    let craft_ticks = ptx_ticks as f64 / PTX_SUBTICKS_PER_CRAFT_TICK;
    let whole = craft_ticks.floor() as i64;
    let frac = craft_ticks - whole as f64;
    if frac <= 1e-6 {
        return tempo.tick_to_samples(whole, sr);
    }
    let s0 = tempo.tick_to_samples(whole, sr) as f64;
    let s1 = tempo.tick_to_samples(whole.saturating_add(1), sr) as f64;
    (s0 + (s1 - s0) * frac).round() as Samples
}

/// Convert SoundCraft sample position back to Pro Tools sub-ticks (`960_000` PPQ).
#[must_use]
pub fn samples_to_ptx_ticks(samples: Samples, tempo: &TempoMap, sr: SampleRate) -> u64 {
    let craft_ticks = tempo.samples_to_ticks_f(samples.max(0), sr);
    (craft_ticks * PTX_SUBTICKS_PER_CRAFT_TICK).round().max(0.0) as u64
}

/// Convert Pro Tools sub-ticks (`960_000` PPQ) to Craft MIDI ticks (`960` PPQ).
#[must_use]
pub fn ptx_ticks_to_craft_ticks(ptx_ticks: u64) -> i64 {
    ((ptx_ticks as f64) / PTX_SUBTICKS_PER_CRAFT_TICK).round() as i64
}

/// Convert Craft MIDI ticks (`960` PPQ) to Pro Tools sub-ticks (`960_000` PPQ).
#[must_use]
pub fn craft_ticks_to_ptx_ticks(craft_ticks: i64) -> u64 {
    u64::try_from(craft_ticks.max(0)).unwrap_or(0).saturating_mul(1000)
}

/// Build a SoundCraft [`TempoMap`] from decoded `.ptx` `tempo_used` and `meter_used`.
#[must_use]
pub fn build_tempo_map_from_ptx(
    ptx: &ptx_format::decode::PtxDocument,
    report: &mut ConversionReport,
) -> TempoMap {
    let mut map = TempoMap::default();
    let tempos = if ptx.tempo_used.is_empty() {
        &ptx.tempo
    } else {
        &ptx.tempo_used
    };
    let mut sorted_tempos: Vec<_> = tempos.iter().collect();
    sorted_tempos.sort_by_key(|t| t.ticks);
    for (idx, t) in sorted_tempos.iter().enumerate() {
        let craft_tick = ptx_ticks_to_craft_ticks(t.ticks);
        let bpm = if t.bpm_exact > 0.0 { t.bpm_exact } else { t.bpm };
        if idx == 0 && craft_tick > 0 {
            let _ = map.set_tempo(0, bpm);
        }
        if map.set_tempo(craft_tick, bpm).is_ok() {
            report.record("tempo", format!("tempo@{craft_tick}={bpm:.3}bpm"), Fidelity::Native, None);
        }
    }

    let meters = if ptx.meter_used.is_empty() {
        &ptx.meter
    } else {
        &ptx.meter_used
    };
    let mut sorted_meters: Vec<_> = meters.iter().collect();
    sorted_meters.sort_by_key(|m| m.ticks);
    for m in sorted_meters {
        let craft_tick = ptx_ticks_to_craft_ticks(m.ticks);
        if map.set_meter(craft_tick, m.numerator.max(1), m.denominator.max(1)).is_ok() {
            report.record(
                "meter",
                format!("{}/{}@{craft_tick}", m.numerator, m.denominator),
                Fidelity::Native,
                None,
            );
        }
    }
    map.sanitize();
    map
}

/// Extract SoundCraft [`TempoEvent`]s as PT `(ticks, bpm)`.
#[must_use]
pub fn tempo_events_to_ptx(tempo: &TempoMap) -> Vec<ptx_format::encode::spec::BuildTempoPoint> {
    let list: Vec<_> = tempo
        .tempos()
        .iter()
        .map(|e: &TempoEvent| ptx_format::encode::spec::BuildTempoPoint {
            ticks: craft_ticks_to_ptx_ticks(e.tick),
            bpm: e.bpm,
        })
        .collect();
    if list.is_empty() {
        vec![ptx_format::encode::spec::BuildTempoPoint { ticks: 0, bpm: 120.0 }]
    } else {
        list
    }
}

/// Convert PT timecode frame rate (`0x204D` / `TimelineInfo`) to SoundCraft [`FrameRate`].
#[must_use]
pub fn ptx_frame_rate_to_sc(tl: &ptx_format::decode::timeline::TimelineInfo) -> FrameRate {
    let drop = tl.drop_frame.unwrap_or(false);
    match tl.timecode_rate_code {
        Some(1) => FrameRate::Fps24,
        Some(2) => FrameRate::Fps25,
        Some(3) => if drop { FrameRate::Fps29_97Drop } else { FrameRate::Fps29_97 },
        Some(5) => FrameRate::Fps29_97Drop,
        Some(7 | 8) => FrameRate::Fps30,
        Some(9) => FrameRate::Fps23_976,
        Some(10) => FrameRate::Fps50,
        Some(11) => if drop { FrameRate::Fps59_94Drop } else { FrameRate::Fps59_94 },
        Some(12) => FrameRate::Fps59_94Drop,
        Some(13 | 14) => FrameRate::Fps60,
        Some(15) => FrameRate::Fps47_952,
        Some(16) => FrameRate::Fps48,
        Some(17) => FrameRate::Fps100,
        Some(18 | 19) => FrameRate::Fps119_88,
        Some(20 | 21) => FrameRate::Fps120,
        _ => match tl.timecode_rate.as_deref().unwrap_or("") {
            "23.976" => FrameRate::Fps23_976,
            "25" => FrameRate::Fps25,
            "29.97" if drop => FrameRate::Fps29_97Drop,
            "29.97" | "29.97 Drop" => {
                if tl.timecode_rate.as_deref() == Some("29.97 Drop") || drop {
                    FrameRate::Fps29_97Drop
                } else {
                    FrameRate::Fps29_97
                }
            }
            "30" | "30 Drop" => FrameRate::Fps30,
            "47.952" => FrameRate::Fps47_952,
            "48" => FrameRate::Fps48,
            "50" => FrameRate::Fps50,
            "59.94" | "59.94 Drop" => {
                if tl.timecode_rate.as_deref() == Some("59.94 Drop") || drop {
                    FrameRate::Fps59_94Drop
                } else {
                    FrameRate::Fps59_94
                }
            }
            "60" | "60 Drop" => FrameRate::Fps60,
            "100" => FrameRate::Fps100,
            "119.88" | "119.88 Drop" => FrameRate::Fps119_88,
            "120" | "120 Drop" => FrameRate::Fps120,
            _ => FrameRate::Fps24,
        },
    }
}

/// True if the Pro Tools timeline uses a drop-frame rate (`30D`/`60D`/`119.88D`/`120D`) not distinguished by SoundCraft's `FrameRate`.
#[must_use]
pub fn ptx_frame_rate_is_unmapped_drop(tl: &ptx_format::decode::timeline::TimelineInfo) -> bool {
    matches!(tl.timecode_rate_code, Some(8 | 14 | 19 | 21))
        || matches!(
            tl.timecode_rate.as_deref(),
            Some("30 Drop" | "60 Drop" | "119.88 Drop" | "120 Drop")
        )
}

/// Parse a `HH:MM:SS:FF` (or `HH:MM:SS;FF`) timecode string into SoundCraft sample count.
#[must_use]
pub fn parse_tc_to_samples(tc: &str, fr: FrameRate, sr: SampleRate) -> Samples {
    let cleaned = tc.replace(';', ":");
    let parts: Vec<i64> = cleaned.split(':').filter_map(|p| p.trim().parse().ok()).collect();
    if parts.len() != 4 {
        return 0;
    }
    let (h, m, s, f) = (parts[0], parts[1], parts[2], parts[3]);
    let nom = fr.nominal().max(1);
    let total_nominal_frames = ((h * 3600 + m * 60 + s) * nom + f).max(0);
    let total_actual_frames = if fr.is_drop() {
        let d_frames = if nom == 60 { 4 } else { 2 };
        let total_min = (h * 60 + m).max(0);
        let dropped = d_frames * (9 * (total_min / 10) + (total_min % 10));
        (total_nominal_frames - dropped).max(0)
    } else {
        total_nominal_frames
    };
    let (num, den) = fr.rational();
    let res = (i128::from(total_actual_frames) * i128::from(den) * i128::from(sr.hz()))
        / i128::from(num.max(1));
    i64::try_from(res).unwrap_or(0)
}

/// Map SoundCraft [`FrameRate`] -> Pro Tools `0x204D` timecode rate code.
#[must_use]
pub const fn sc_frame_rate_to_ptx(fr: FrameRate) -> u8 {
    match fr {
        FrameRate::Fps24 => 1,
        FrameRate::Fps25 => 2,
        FrameRate::Fps29_97 => 3,
        FrameRate::Fps29_97Drop => 5,
        FrameRate::Fps30 => 7,
        FrameRate::Fps23_976 => 9,
        FrameRate::Fps50 => 10,
        FrameRate::Fps59_94 => 11,
        FrameRate::Fps59_94Drop => 12,
        FrameRate::Fps60 => 13,
        FrameRate::Fps47_952 => 15,
        FrameRate::Fps48 => 16,
        FrameRate::Fps100 => 17,
        FrameRate::Fps119_88 => 18,
        FrameRate::Fps120 => 20,
    }
}

/// Format sample position cleanly as `HH:MM:SS:FF` (or `;FF` for drop-frame) for `0x204D`.
#[must_use]
pub fn samples_to_tc_string(samples: Samples, fr: FrameRate, sr: SampleRate) -> String {
    let (num, den) = fr.rational();
    let nom = fr.nominal().max(1);
    let den_tot = i128::from(sr.hz().max(1)) * i128::from(den.max(1));
    let frames = ((i128::from(samples.max(0)) * i128::from(num) + den_tot / 2) / den_tot).max(0) as i64;
    let total_nominal = if fr.is_drop() {
        // Inverse SMPTE 29.97 / 59.94 drop-frame adjustment
        let d_frames = if nom == 60 { 4 } else { 2 };
        let fpm = nom * 60 - d_frames;
        let fp10m = nom * 600 - d_frames * 9;
        let d10 = frames / fp10m;
        let rem = frames % fp10m;
        let extra = if rem < nom * 60 {
            0
        } else {
            1 + (rem - nom * 60) / fpm
        };
        frames + d_frames * (9 * d10 + extra)
    } else {
        frames
    };
    let ff = total_nominal % nom;
    let total_sec = total_nominal / nom;
    let ss = total_sec % 60;
    let mm = (total_sec / 60) % 60;
    let hh = total_sec / 3600;
    let sep = if fr.is_drop() { ';' } else { ':' };
    format!("{hh:02}:{mm:02}:{ss:02}{sep}{ff:02}")
}

/// Convert PT key signature `(major, sharps)` to SoundCraft display key string (`"C major"`, `"A minor"`, ...).
#[must_use]
pub fn ptx_keysig_to_sc(major: bool, sharps: i8) -> String {
    const MAJ_SHARPS: &[&str] = &["C", "G", "D", "A", "E", "B", "F#", "C#"];
    const MAJ_FLATS: &[&str] = &["C", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"];
    const MIN_SHARPS: &[&str] = &["A", "E", "B", "F#", "C#", "G#", "D#", "A#"];
    const MIN_FLATS: &[&str] = &["A", "D", "G", "C", "F", "Bb", "Eb", "Ab"];
    let idx = usize::from(sharps.unsigned_abs()).min(7);
    let root = match (major, sharps >= 0) {
        (true, true) => MAJ_SHARPS[idx],
        (true, false) => MAJ_FLATS[idx],
        (false, true) => MIN_SHARPS[idx],
        (false, false) => MIN_FLATS[idx],
    };
    let mode = if major { "major" } else { "minor" };
    format!("{root} {mode}")
}

/// Convert SoundCraft key string (`"C major"`, `"F# minor"`, ...) back to `(major, sharps)`.
#[must_use]
pub fn sc_keysig_to_ptx(key: &str) -> (bool, i8) {
    let mut parts = key.split_whitespace();
    let root = parts.next().unwrap_or("C");
    let mode = parts.next().unwrap_or("major").to_ascii_lowercase();
    let major = !mode.starts_with("min");
    let sharps: i8 = match (major, root) {
        (true, "C") => 0,
        (true, "G") => 1,
        (true, "D") => 2,
        (true, "A") => 3,
        (true, "E") => 4,
        (true, "B") => 5,
        (true, "F#") => 6,
        (true, "C#") => 7,
        (true, "F") => -1,
        (true, "Bb") => -2,
        (true, "Eb") => -3,
        (true, "Ab") => -4,
        (true, "Db") => -5,
        (true, "Gb") => -6,
        (true, "Cb") => -7,
        (false, "A") => 0,
        (false, "E") => 1,
        (false, "B") => 2,
        (false, "F#") => 3,
        (false, "C#") => 4,
        (false, "G#") => 5,
        (false, "D#") => 6,
        (false, "A#") => 7,
        (false, "D") => -1,
        (false, "G") => -2,
        (false, "C") => -3,
        (false, "F") => -4,
        (false, "Bb") => -5,
        (false, "Eb") => -6,
        (false, "Ab") => -7,
        _ => 0,
    };
    (major, sharps)
}

/// Convert raw tenths-of-dB integer (`-1440` = `-inf`) to bounded float dB for `.scraft`.
#[must_use]
pub fn tenths_to_sc_db(tenths: i16) -> f32 {
    if tenths <= -1440 {
        -144.0
    } else {
        (f64::from(tenths) / 10.0) as f32
    }
}

/// Convert SoundCraft dB float to tenths-of-dB `i16`.
#[must_use]
pub fn sc_db_to_tenths(db: f32) -> i16 {
    if !db.is_finite() || db <= -144.0 {
        -1440
    } else {
        (db * 10.0).round().clamp(-1440.0, 120.0) as i16
    }
}

/// Convert PT pan integer `-100..=100` to SoundCraft pan `-1.0..=1.0`.
#[must_use]
pub fn ptx_pan_to_sc(pan: i16) -> f32 {
    (f32::from(pan) / 100.0).clamp(-1.0, 1.0)
}

/// Convert SoundCraft pan `-1.0..=1.0` to PT pan integer `-100..=100`.
#[must_use]
pub fn sc_pan_to_ptx(pan: f32) -> i16 {
    (pan.clamp(-1.0, 1.0) * 100.0).round() as i16
}

/// Evaluate a volume segment interpolated linearly in fader-position space, returning dB breakpoints
/// within [`VOLUME_CURVE_TOLERANCE_DB`].
fn subdivide_fader_pos_segment(
    t0: Samples,
    db0: f32,
    t1: Samples,
    db1: f32,
    depth: u8,
    out: &mut Vec<AutomationPoint>,
) {
    if depth >= MAX_SUBDIV_DEPTH || t1 <= t0 + 1 {
        out.push(AutomationPoint { at: t1, value: db1 });
        return;
    }
    let p0 = fader_db_to_pos(db0);
    let p1 = fader_db_to_pos(db1);
    let t_mid = t0 + (t1 - t0) / 2;
    let p_mid = 0.5 * (p0 + p1);
    let exact_mid_db = fader_pos_to_db(p_mid);
    let lin_mid_db = 0.5 * (db0 + db1);
    if f64::from((exact_mid_db - lin_mid_db).abs()) <= VOLUME_CURVE_TOLERANCE_DB {
        out.push(AutomationPoint { at: t1, value: db1 });
    } else {
        subdivide_fader_pos_segment(t0, db0, t_mid, exact_mid_db, depth + 1, out);
        subdivide_fader_pos_segment(t_mid, exact_mid_db, t1, db1, depth + 1, out);
    }
}

/// Evaluate a dB-linear SC volume segment back to PT fader-position ramps within tolerance.
fn subdivide_db_segment_for_ptx(
    t0: u64,
    db0: f32,
    t1: u64,
    db1: f32,
    depth: u8,
    out: &mut Vec<(u64, i16)>,
) {
    if depth >= MAX_SUBDIV_DEPTH || t1 <= t0 + 1 {
        out.push((t1, sc_db_to_tenths(db1)));
        return;
    }
    let p0 = fader_db_to_pos(db0);
    let p1 = fader_db_to_pos(db1);
    let pt_mid_db = fader_pos_to_db(0.5 * (p0 + p1));
    let sc_mid_db = 0.5 * (db0 + db1);
    if f64::from((pt_mid_db - sc_mid_db).abs()) <= VOLUME_CURVE_TOLERANCE_DB {
        out.push((t1, sc_db_to_tenths(db1)));
    } else {
        let t_mid = t0 + (t1 - t0) / 2;
        subdivide_db_segment_for_ptx(t0, db0, t_mid, sc_mid_db, depth + 1, out);
        subdivide_db_segment_for_ptx(t_mid, sc_mid_db, t1, db1, depth + 1, out);
    }
}

/// Convert a PT lane `(raw_time, raw_val)` into a SoundCraft [`AutomationLane`].
#[must_use]
pub fn ptx_lane_to_sc(
    param: AutoParam,
    raw_points: &[(u64, i16)],
    is_ticks: bool,
    tempo: &TempoMap,
    sr: SampleRate,
    is_volume: bool,
) -> AutomationLane {
    let mut lane = AutomationLane::new(param.clone());
    if raw_points.is_empty() {
        return lane;
    }
    let convert_time = |t: u64| -> Samples {
        let clean = ptx_format::primitives::plain_ticks(t);
        if is_ticks {
            ptx_ticks_to_samples(clean, tempo, sr)
        } else {
            i64::try_from(clean).unwrap_or(i64::MAX)
        }
    };
    let convert_val = |v: i16| -> f32 {
        if is_volume {
            tenths_to_sc_db(v)
        } else if matches!(param, AutoParam::Pan(_) | AutoParam::SendPan(_)) {
            ptx_pan_to_sc(v)
        } else if v > 0 {
            1.0
        } else {
            0.0
        }
    };

    let mut pts: Vec<AutomationPoint> = Vec::with_capacity(raw_points.len());
    let first_t = convert_time(raw_points[0].0);
    let first_v = convert_val(raw_points[0].1);
    pts.push(AutomationPoint { at: first_t, value: first_v });

    for w in raw_points.windows(2) {
        let prev = pts.last().copied().unwrap_or(AutomationPoint { at: first_t, value: first_v });
        let t1 = convert_time(w[1].0);
        let v1 = convert_val(w[1].1);
        if is_volume && (v1 - prev.value).abs() > 0.1 {
            subdivide_fader_pos_segment(prev.at, prev.value, t1, v1, 0, &mut pts);
        } else {
            pts.push(AutomationPoint { at: t1, value: v1 });
        }
    }
    for p in pts {
        lane.set_point(p.at, p.value);
    }
    lane
}

/// Convert a SoundCraft volume automation lane back into PT `(samples_or_ticks, tenths_db)`.
#[must_use]
pub fn sc_vol_lane_to_ptx(
    lane: &AutomationLane,
    to_ticks: bool,
    tempo: &TempoMap,
    sr: SampleRate,
) -> Vec<(u64, i16)> {
    if lane.points.is_empty() {
        return Vec::new();
    }
    let time_fn = |s: Samples| -> u64 {
        if to_ticks {
            samples_to_ptx_ticks(s, tempo, sr)
        } else {
            u64::try_from(s.max(0)).unwrap_or(0)
        }
    };
    let mut out = Vec::new();
    let t0 = time_fn(lane.points[0].at);
    out.push((t0, sc_db_to_tenths(lane.points[0].value)));
    for w in lane.points.windows(2) {
        let prev_t = out.last().map_or(t0, |x| x.0);
        let t1 = time_fn(w[1].at);
        if (w[1].value - w[0].value).abs() > 0.1 {
            subdivide_db_segment_for_ptx(prev_t, w[0].value, t1, w[1].value, 0, &mut out);
        } else {
            out.push((t1, sc_db_to_tenths(w[1].value)));
        }
    }
    out
}

/// Map PT decoded fade object to SoundCraft [`Fade`].
#[must_use]
pub fn ptx_fade_to_sc(
    fade: &ptx_format::decode::clips::FadeObject,
    report: &mut ConversionReport,
    ctx: &str,
) -> Fade {
    let slope_str = fade.slope.as_str().unwrap_or("equal_power");
    let shape = match slope_str {
        "linear" | "equal_gain" => {
            report.record("fades", format!("{ctx}:slope=linear"), Fidelity::Native, None);
            FadeShape::Linear
        }
        "equal_power" => {
            report.record("fades", format!("{ctx}:slope=equal_power"), Fidelity::Native, None);
            FadeShape::EqualPower
        }
        "s_curve" => {
            report.record("fades", format!("{ctx}:slope=s_curve"), Fidelity::Native, None);
            FadeShape::SCurve
        }
        other => {
            report.record(
                "fades",
                format!("{ctx}:slope={other}"),
                Fidelity::Approx,
                Some("mapped custom PT slope to EqualPower".to_owned()),
            );
            FadeShape::EqualPower
        }
    };
    Fade {
        len: i64::try_from(fade.length).unwrap_or(0),
        shape,
        curvature: fade.curve as f32,
    }
}

fn sc_fade_slope_to_ptx(
    shape: FadeShape,
    report: &mut ConversionReport,
    ctx: &str,
) -> ptx_format::encode::spec::BuildFadeSlope {
    match shape {
        FadeShape::Linear => {
            report.record("fades", format!("{ctx}:Linear"), Fidelity::Native, None);
            ptx_format::encode::spec::BuildFadeSlope::EqualGain
        }
        FadeShape::EqualPower => {
            report.record("fades", format!("{ctx}:EqualPower"), Fidelity::Native, None);
            ptx_format::encode::spec::BuildFadeSlope::EqualPower
        }
        other => {
            report.record(
                "fades",
                format!("{ctx}:{other:?}"),
                Fidelity::Approx,
                Some("SoundCraft custom fade shape mapped to PT EqualPower".to_owned()),
            );
            ptx_format::encode::spec::BuildFadeSlope::EqualPower
        }
    }
}

/// Map SoundCraft [`Fade`] to PT [`ptx_format::encode::spec::BuildFade`].
#[must_use]
pub fn sc_fade_to_ptx(
    fade: Fade,
    is_in: bool,
    report: &mut ConversionReport,
    ctx: &str,
) -> Option<ptx_format::encode::spec::BuildFade> {
    if fade.len <= 0 {
        return None;
    }
    let kind = if is_in {
        ptx_format::encode::spec::BuildFadeKind::FadeIn
    } else {
        ptx_format::encode::spec::BuildFadeKind::FadeOut
    };
    let slope = sc_fade_slope_to_ptx(fade.shape, report, ctx);
    Some(ptx_format::encode::spec::BuildFade {
        kind,
        slope,
        length_samples: u64::try_from(fade.len).unwrap_or(0),
        pre_roll_samples: None,
    })
}

/// Map SoundCraft crossfade boundary [`Fade`] to PT `BuildFadeKind::Crossfade`.
#[must_use]
pub fn sc_crossfade_to_ptx(
    fade: Fade,
    pre_roll_samples: Option<u64>,
    report: &mut ConversionReport,
    ctx: &str,
) -> Option<ptx_format::encode::spec::BuildFade> {
    if fade.len <= 0 {
        return None;
    }
    let slope = sc_fade_slope_to_ptx(fade.shape, report, ctx);
    Some(ptx_format::encode::spec::BuildFade {
        kind: ptx_format::encode::spec::BuildFadeKind::Crossfade,
        slope,
        length_samples: u64::try_from(fade.len).unwrap_or(0),
        pre_roll_samples,
    })
}
