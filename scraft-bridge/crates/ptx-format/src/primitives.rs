// Version: 0.7.0 (beta) | Date: 2026-11-27
//! Low-level bounds-checked binary primitives and Pro Tools timebase math.

/// Ticks per quarter note in Pro Tools sessions.
pub const TPQ: f64 = 960_000.0;

/// Integer ticks per quarter note.
pub const TPQ_U64: u64 = 960_000;

/// Stored offset added to tick-based positions/timestamps (`10^12`).
pub const OFFSET_FORM: u64 = 1_000_000_000_000;

/// Windows FILETIME epoch offset relative to Unix epoch (in 100 ns ticks).
pub const FILETIME_UNIX_DIFF: u64 = 116_444_736_000_000_000;

/// Remove `10^12` offset from tick-based values when present.
#[must_use]
pub const fn plain_ticks(v: u64) -> u64 {
    if v >= OFFSET_FORM { v - OFFSET_FORM } else { v }
}

/// Read fixed-size byte array safely.
#[must_use]
pub fn bytes_at<const N: usize>(d: &[u8], at: usize) -> Option<[u8; N]> {
    let end = at.checked_add(N)?;
    d.get(at..end)?.try_into().ok()
}

/// Read little-endian `u16`.
#[must_use]
pub fn u16_at(d: &[u8], at: usize) -> Option<u16> {
    bytes_at::<2>(d, at).map(u16::from_le_bytes)
}

/// Read little-endian `i16`.
#[must_use]
pub fn i16_at(d: &[u8], at: usize) -> Option<i16> {
    bytes_at::<2>(d, at).map(i16::from_le_bytes)
}

/// Read little-endian `u32`.
#[must_use]
pub fn u32_at(d: &[u8], at: usize) -> Option<u32> {
    bytes_at::<4>(d, at).map(u32::from_le_bytes)
}

/// Read little-endian `i32`.
#[must_use]
pub fn i32_at(d: &[u8], at: usize) -> Option<i32> {
    bytes_at::<4>(d, at).map(i32::from_le_bytes)
}

/// Read big-endian `i32`.
#[must_use]
pub fn be_i32_at(d: &[u8], at: usize) -> Option<i32> {
    bytes_at::<4>(d, at).map(i32::from_be_bytes)
}

/// Read big-endian `u32`.
#[must_use]
pub fn be_u32_at(d: &[u8], at: usize) -> Option<u32> {
    bytes_at::<4>(d, at).map(u32::from_be_bytes)
}

/// Read little-endian `u64`.
#[must_use]
pub fn u64_at(d: &[u8], at: usize) -> Option<u64> {
    bytes_at::<8>(d, at).map(u64::from_le_bytes)
}

/// Read little-endian `f32`.
#[must_use]
pub fn f32_at(d: &[u8], at: usize) -> Option<f32> {
    bytes_at::<4>(d, at).map(f32::from_le_bytes)
}

/// Read little-endian `f64`.
#[must_use]
pub fn f64_at(d: &[u8], at: usize) -> Option<f64> {
    bytes_at::<8>(d, at).map(f64::from_le_bytes)
}

/// Read big-endian `f64`.
#[must_use]
pub fn be_f64_at(d: &[u8], at: usize) -> Option<f64> {
    bytes_at::<8>(d, at).map(f64::from_be_bytes)
}

/// Read little-endian unsigned integer of `1..=8` bytes.
#[must_use]
pub fn le_u64(d: &[u8], at: usize, len: usize) -> Option<u64> {
    if len == 0 || len > 8 {
        return None;
    }
    let slice = d.get(at..at.checked_add(len)?)?;
    Some(slice.iter().rev().fold(0u64, |acc, &b| (acc << 8) | u64::from(b)))
}

/// Read little-endian signed integer of `1..=8` bytes (sign-extended).
#[must_use]
pub fn le_i64(d: &[u8], at: usize, len: usize) -> Option<i64> {
    let raw = le_u64(d, at, len)?;
    let bits = len * 8;
    if bits == 64 {
        Some(raw as i64)
    } else {
        let sign = 1u64 << (bits - 1);
        if raw >= sign {
            Some((raw as i64) - ((1u64 << bits) as i64))
        } else {
            Some(raw as i64)
        }
    }
}

/// Read a `u32`-length-prefixed UTF-8 string (`<= max_len` bytes), returning `(string, next_offset)`.
#[must_use]
pub fn lp_str(d: &[u8], at: usize, max_len: usize) -> Option<(String, usize)> {
    let len = usize::try_from(u32_at(d, at)?).ok()?;
    if len > max_len {
        return None;
    }
    let start = at.checked_add(4)?;
    let end = start.checked_add(len)?;
    let s = String::from_utf8_lossy(d.get(start..end)?).into_owned();
    Some((s, end))
}

/// Scan a slice `[start..end)` for valid length-prefixed printable ASCII/UTF-8 strings (mirrors `ptx_probe.lp_strings`).
#[must_use]
pub fn scan_lp_strings(d: &[u8], start: usize, end: usize, min_len: usize, max_len: usize) -> Vec<(usize, String)> {
    let end = end.min(d.len());
    let mut out = Vec::new();
    let mut p = start;
    while p + 4 <= end {
        if let Some(n) = u32_at(d, p).and_then(|v| usize::try_from(v).ok())
            && n >= min_len
            && n <= max_len
            && p + 4 + n <= end
            && let Some(bytes) = d.get(p + 4..p + 4 + n)
            && let Ok(s) = core::str::from_utf8(bytes)
            && s.chars().all(|c| !c.is_control())
        {
            out.push((p, s.to_owned()));
            p += 4 + n;
            continue;
        }
        p += 1;
    }
    out
}

/// Convert tick position to seconds using a sorted constant-tempo map (`[(ticks, bpm)]`).
#[must_use]
pub fn ticks_to_seconds(ticks: f64, tempo_map: &[(u64, f64)]) -> f64 {
    if tempo_map.is_empty() {
        return ticks / TPQ * (60.0 / 120.0);
    }
    let mut sec = 0.0_f64;
    let mut prev_tick = 0.0_f64;
    let mut prev_bpm = tempo_map[0].1.max(1e-6);
    for &(ev_tick, ev_bpm) in tempo_map {
        let t = ev_tick as f64;
        if ticks <= t {
            return sec + (ticks - prev_tick) / TPQ * (60.0 / prev_bpm);
        }
        sec += (t - prev_tick) / TPQ * (60.0 / prev_bpm);
        prev_tick = t;
        prev_bpm = ev_bpm.max(1e-6);
    }
    sec + (ticks - prev_tick) / TPQ * (60.0 / prev_bpm)
}

/// Convert seconds to ticks using a sorted constant-tempo map (`[(ticks, bpm)]`).
#[must_use]
pub fn seconds_to_ticks(seconds: f64, tempo_map: &[(u64, f64)]) -> f64 {
    if tempo_map.is_empty() {
        return seconds * (120.0 / 60.0) * TPQ;
    }
    let mut sec = 0.0_f64;
    let mut prev_tick = 0.0_f64;
    let mut prev_bpm = tempo_map[0].1.max(1e-6);
    for &(ev_tick, ev_bpm) in tempo_map {
        let t = ev_tick as f64;
        let seg_sec = (t - prev_tick) / TPQ * (60.0 / prev_bpm);
        if seconds <= sec + seg_sec {
            return prev_tick + (seconds - sec) * (prev_bpm / 60.0) * TPQ;
        }
        sec += seg_sec;
        prev_tick = t;
        prev_bpm = ev_bpm.max(1e-6);
    }
    prev_tick + (seconds - sec) * (prev_bpm / 60.0) * TPQ
}

/// Round floating-point value to `decimals` decimal places.
#[must_use]
pub fn round_n(val: f64, decimals: i32) -> f64 {
    let scale = 10_f64.powi(decimals);
    (val * scale).round() / scale
}

/// Convert Unix nanoseconds to Windows FILETIME (100 ns since 1601-01-01).
#[must_use]
pub const fn unix_ns_to_filetime(unix_ns: u64) -> u64 {
    (unix_ns / 100).saturating_add(FILETIME_UNIX_DIFF)
}

/// Encode a `u32`-length-prefixed UTF-8 string (`LP`).
#[must_use]
pub fn lp_bytes(s: &str) -> Vec<u8> {
    let b = s.as_bytes();
    let mut out = Vec::with_capacity(4 + b.len());
    out.extend_from_slice(&u32::try_from(b.len()).unwrap_or(0).to_le_bytes());
    out.extend_from_slice(b);
    out
}

/// Search `haystack[from..]` for the first occurrence of `needle`.
#[must_use]
pub fn find_bytes(haystack: &[u8], needle: &[u8], from: usize) -> Option<usize> {
    haystack
        .get(from..)?
        .windows(needle.len())
        .position(|w| w == needle)
        .map(|off| from + off)
}

/// Verified piecewise-linear Pro Tools Trim gain taper knots `(normalized_u, db)` up to `0 dB`.
pub const TRIM_KNOTS: [(f64, f64); 6] = [
    (0.0, -144.0),
    (0.10, -53.10),
    (0.25, -23.40),
    (0.40, -14.60),
    (0.50, -10.40),
    (0.755, 0.0),
];

/// Exact rational frame rate metadata for Pro Tools `0x204D` timecode rate codes:
/// `(rate_code, fps_num, fps_den, is_drop, label)`.
pub const TIMECODE_RATES: [(u32, u64, u64, bool, &str); 19] = [
    (1, 24, 1, false, "24"),
    (2, 25, 1, false, "25"),
    (3, 30_000, 1001, false, "29.97"),
    (5, 30_000, 1001, true, "29.97 Drop"),
    (7, 30, 1, false, "30"),
    (8, 30, 1, true, "30 Drop"),
    (9, 24_000, 1001, false, "23.976"),
    (10, 50, 1, false, "50"),
    (11, 60_000, 1001, false, "59.94"),
    (12, 60_000, 1001, true, "59.94 Drop"),
    (13, 60, 1, false, "60"),
    (14, 60, 1, true, "60 Drop"),
    (15, 48_000, 1001, false, "47.952"),
    (16, 48, 1, false, "48"),
    (17, 100, 1, false, "100"),
    (18, 120_000, 1001, false, "119.88"),
    (19, 120_000, 1001, true, "119.88 Drop"),
    (20, 120, 1, false, "120"),
    (21, 120, 1, true, "120 Drop"),
];

/// Look up exact rational timecode parameters `(fps_num, fps_den, is_drop)` for a `0x204D` rate code.
#[must_use]
pub fn tc_exact_rate(rate_code: u32) -> Option<(u64, u64, bool)> {
    TIMECODE_RATES
        .iter()
        .find(|&&(c, _, _, _, _)| c == rate_code)
        .map(|&(_, num, den, drop, _)| (num, den, drop))
}

const fn round_half_up_u128(num: u128, den: u128) -> u128 {
    (2 * num + den) / (2 * den)
}

/// Convert a SMPTE timecode string (`HH:MM:SS:FF` or `HH:MM:SS;FF`) to exact samples using half-up integer arithmetic.
///
/// Validates frame/minute/second bounds and rejects invalid drop-frame labels (`FF < D` at `SS == 0`, `MM % 10 != 0`).
pub fn timecode_to_samples(tc: &str, rate_code: u32, sample_rate: u32) -> Result<u64, String> {
    if sample_rate == 0 {
        return Err("sample_rate must be > 0".to_owned());
    }
    let (fps_num, fps_den, is_drop) = tc_exact_rate(rate_code)
        .ok_or_else(|| format!("unsupported timecode rate code {rate_code}"))?;
    let parts: Vec<&str> = tc.trim().split([':', ';']).collect();
    if parts.len() != 4 {
        return Err(format!("invalid timecode '{tc}': expected HH:MM:SS:FF"));
    }
    let nums: [u128; 4] = [
        parts[0].parse().map_err(|_| format!("invalid hours in '{tc}'"))?,
        parts[1].parse().map_err(|_| format!("invalid minutes in '{tc}'"))?,
        parts[2].parse().map_err(|_| format!("invalid seconds in '{tc}'"))?,
        parts[3].parse().map_err(|_| format!("invalid frames in '{tc}'"))?,
    ];
    let [hh, mm, ss, ff] = nums;
    let nominal = u128::from(fps_num.div_ceil(fps_den));
    let drop = if is_drop { 2 * (nominal / 30) } else { 0 };
    if mm >= 60 || ss >= 60 || ff >= nominal {
        return Err(format!(
            "out-of-range timecode '{tc}' for nominal {nominal} fps"
        ));
    }
    if is_drop && ss == 0 && (mm % 10) != 0 && ff < drop {
        return Err(format!(
            "invalid drop-frame label '{tc}': dropped frames 0..{drop} at non-10th minute boundary"
        ));
    }
    let total_min = 60 * hh + mm;
    let frames = (60 * total_min + ss) * nominal + ff - drop * (total_min - total_min / 10);
    let samples = round_half_up_u128(
        frames * u128::from(sample_rate) * u128::from(fps_den),
        u128::from(fps_num),
    );
    u64::try_from(samples).map_err(|_| format!("sample count overflow for '{tc}'"))
}

/// Convert an integer sample position to formatted SMPTE timecode (`HH:MM:SS:FF` or `HH:MM:SS;FF`).
///
/// Uses `:` for NDF and `;` for DF; pads frames to 3 digits when nominal fps >= 100 (matching Pro Tools `120 Drop`).
pub fn samples_to_timecode(samples: u64, rate_code: u32, sample_rate: u32) -> Result<String, String> {
    if sample_rate == 0 {
        return Err("sample_rate must be > 0".to_owned());
    }
    let (fps_num, fps_den, is_drop) = tc_exact_rate(rate_code)
        .ok_or_else(|| format!("unsupported timecode rate code {rate_code}"))?;
    let nominal = u128::from(fps_num.div_ceil(fps_den));
    let drop = if is_drop { 2 * (nominal / 30) } else { 0 };
    let mut f = round_half_up_u128(
        u128::from(samples) * u128::from(fps_num),
        u128::from(sample_rate) * u128::from(fps_den),
    );
    if is_drop && drop > 0 {
        let q10 = 600 * nominal - 9 * drop;
        let p1 = 60 * nominal - drop;
        let d10 = f / q10;
        let r10 = f % q10;
        f += 9 * drop * d10
            + if r10 >= drop {
                drop * ((r10 - drop) / p1)
            } else {
                0
            };
    }
    let ff = f % nominal;
    let rem = f / nominal;
    let ss = rem % 60;
    let rem = rem / 60;
    let mm = rem % 60;
    let hh = rem / 60;
    let sep = if is_drop { ';' } else { ':' };
    let width = if nominal > 100 { 3 } else { 2 };
    Ok(format!("{hh:02}:{mm:02}:{ss:02}{sep}{ff:0width$}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rational_timecode_roundtrip_all_19_rates() -> Result<(), Box<dyn std::error::Error>> {
        for &(code, _, _, is_drop, _) in &TIMECODE_RATES {
            for &sample_rate in &[44_100u32, 48_000, 96_000, 192_000] {
                let s0 = timecode_to_samples("01:00:00:00", code, sample_rate)?;
                let tc0 = samples_to_timecode(s0, code, sample_rate)?;
                let expected_sep = if is_drop { ";" } else { ":" };
                assert!(tc0.contains(expected_sep), "code {code}: {tc0}");
                let s1 = timecode_to_samples(&tc0, code, sample_rate)?;
                assert_eq!(s0, s1, "code {code} @ {sample_rate}");

                // Non-trivial dropped boundary at 00:01:00:DD
                if is_drop {
                    assert!(
                        timecode_to_samples("00:01:00;00", code, sample_rate).is_err(),
                        "dropped frame 00 accepted for code {code}"
                    );
                    let valid_s = timecode_to_samples("00:01:00;08", code, sample_rate)?;
                    let rt_tc = samples_to_timecode(valid_s, code, sample_rate)?;
                    assert_eq!(timecode_to_samples(&rt_tc, code, sample_rate)?, valid_s);
                }
            }
        }
        assert_eq!(samples_to_timecode(0, 21, 48_000)?, "00:00:00;000");
        assert_eq!(samples_to_timecode(48_000 * 3600, 2, 48_000)?, "01:00:00:00");
        Ok(())
    }
}
