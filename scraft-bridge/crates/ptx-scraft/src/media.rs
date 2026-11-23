// Version: 0.7.0 (beta) | Date: 2026-11-23
//! Zero-move relative media resolution, WAV/AIFF chunk inspection, and FILETIME calculation.

use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

use craft_scraft_format::{FileFormat, Source, SourceId};
use ptx_format::primitives::unix_ns_to_filetime;

use crate::ConvertError;

/// Media placement strategy on conversion.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum MediaMode {
    /// Default: keep zero new copies; resolve `Audio Files/` relative to source/target dir.
    #[default]
    Relative,
    /// Copy referenced audio files into `<out_dir>/Audio Files/`.
    Copy,
    /// Create filesystem links in `<out_dir>/Audio Files/`.
    Link,
}

impl MediaMode {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Relative => "relative",
            Self::Copy => "copy",
            Self::Link => "link",
        }
    }
}

/// Inspected physical metadata of an on-disk audio file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InspectedAudio {
    pub path: PathBuf,
    pub file_name: String,
    pub sample_rate: u32,
    pub channels: u16,
    pub bit_depth: u8,
    pub is_float: bool,
    pub is_aiff: bool,
    pub frames: u64,
    pub data_offset: u16,
    pub time_reference: u64,
    pub filetime: u64,
    pub format: FileFormat,
}

/// Compute Windows FILETIME (`100ns` ticks since 1601-01-01) from a file's mtime.
#[must_use]
pub fn path_filetime(path: &Path) -> u64 {
    let Ok(meta) = fs::metadata(path) else {
        return 133_000_000_000_000_000;
    };
    let Ok(mtime) = meta.modified() else {
        return 133_000_000_000_000_000;
    };
    let Ok(dur) = mtime.duration_since(UNIX_EPOCH) else {
        return 133_000_000_000_000_000;
    };
    unix_ns_to_filetime(u64::try_from(dur.as_nanos()).unwrap_or(u64::MAX))
}

/// Inspect a RIFF/WAVE file header for exact `data_offset`, `bext` time_reference, frames, and bit depth.
fn inspect_wav(path: &Path, file_name: &str) -> Option<InspectedAudio> {
    let mut f = File::open(path).ok()?;
    let mut riff = [0u8; 12];
    f.read_exact(&mut riff).ok()?;
    if &riff[0..4] != b"RIFF" || &riff[8..12] != b"WAVE" {
        return None;
    }

    let mut sample_rate = 0u32;
    let mut channels = 0u16;
    let mut bits_per_sample = 0u16;
    let mut audio_format = 0u16;
    let mut block_align = 0u16;
    let mut data_offset = 0u64;
    let mut data_size = 0u32;
    let mut time_reference = 0u64;
    let mut saw_fmt = false;
    let mut saw_data = false;

    let mut chunk_hdr = [0u8; 8];
    while f.read_exact(&mut chunk_hdr).is_ok() {
        let id = [chunk_hdr[0], chunk_hdr[1], chunk_hdr[2], chunk_hdr[3]];
        let size = u32::from_le_bytes([chunk_hdr[4], chunk_hdr[5], chunk_hdr[6], chunk_hdr[7]]);
        let payload_pos = f.stream_position().ok()?;
        match &id {
            b"fmt " if size >= 16 => {
                let mut buf = [0u8; 40];
                let to_read = usize::try_from(size.min(40)).ok()?;
                f.read_exact(&mut buf[..to_read]).ok()?;
                audio_format = u16::from_le_bytes([buf[0], buf[1]]);
                channels = u16::from_le_bytes([buf[2], buf[3]]);
                sample_rate = u32::from_le_bytes([buf[4], buf[5], buf[6], buf[7]]);
                block_align = u16::from_le_bytes([buf[12], buf[13]]);
                bits_per_sample = u16::from_le_bytes([buf[14], buf[15]]);
                if audio_format == 0xFFFE && to_read >= 26 {
                    // WAVE_FORMAT_EXTENSIBLE subformat first 2 bytes
                    audio_format = u16::from_le_bytes([buf[24], buf[25]]);
                }
                saw_fmt = true;
            }
            b"bext" if size >= 348 => {
                // BWF time_reference is u64 LE at byte offset 338 inside `bext`.
                f.seek(SeekFrom::Current(338)).ok()?;
                let mut tr = [0u8; 8];
                f.read_exact(&mut tr).ok()?;
                time_reference = u64::from_le_bytes(tr);
            }
            b"data" => {
                data_offset = payload_pos;
                data_size = size;
                saw_data = true;
            }
            _ => {}
        }
        let padded = i64::from(size) + i64::from(size & 1);
        let next = payload_pos.checked_add(u64::try_from(padded).ok()?)?;
        f.seek(SeekFrom::Start(next)).ok()?;
        if saw_fmt && saw_data && time_reference > 0 {
            break;
        }
    }

    if !saw_fmt || !saw_data || sample_rate == 0 || channels == 0 || block_align == 0 {
        return None;
    }
    let frames = u64::from(data_size) / u64::from(block_align);
    let is_float = audio_format == 3;
    Some(InspectedAudio {
        path: path.to_path_buf(),
        file_name: file_name.to_owned(),
        sample_rate,
        channels,
        bit_depth: u8::try_from(bits_per_sample).unwrap_or(24),
        is_float,
        is_aiff: false,
        frames,
        data_offset: u16::try_from(data_offset.min(u64::from(u16::MAX))).unwrap_or(44),
        time_reference,
        filetime: path_filetime(path),
        format: FileFormat::Wav,
    })
}

/// Inspect any audio file (fast RIFF WAV parser with `craft_audio::probe` fallback).
///
/// # Errors
/// Returns `ConvertError::Audio` if the file cannot be read or decoded as audio metadata.
pub fn inspect_audio_file(path: &Path) -> Result<InspectedAudio, ConvertError> {
    let file_name = path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("audio.wav")
        .to_owned();
    if let Some(wav) = inspect_wav(path, &file_name) {
        return Ok(wav);
    }
    let raw = fs::read(path)?;
    let ext = path.extension().and_then(|e| e.to_str());
    let info = craft_audio::probe(&raw, ext).map_err(|e| ConvertError::Audio(e.to_string()))?;
    let format = FileFormat::of(&info);
    let is_aiff = format == FileFormat::Aiff;
    let is_float = matches!(info.sample_format, craft_audio::SampleFormat::Float32);
    let bit_depth = match info.sample_format {
        craft_audio::SampleFormat::Int16 => 16,
        craft_audio::SampleFormat::Int24 => 24,
        craft_audio::SampleFormat::Int32 | craft_audio::SampleFormat::Float32 => 32,
        _ => 24,
    };
    Ok(InspectedAudio {
        path: path.to_path_buf(),
        file_name,
        sample_rate: info.sample_rate,
        channels: info.channels,
        bit_depth,
        is_float,
        is_aiff,
        frames: info.frames,
        data_offset: if is_aiff { 54 } else { 44 },
        time_reference: 0,
        filetime: path_filetime(path),
        format,
    })
}

/// Resolve a file name / relative path relative to `session_dir` (`session_dir/<rel>`,
/// `session_dir/Audio Files/<basename>`, or case-insensitive scan of `Audio Files`).
#[must_use]
pub fn resolve_audio_path(session_dir: &Path, raw_ref: &str) -> Option<PathBuf> {
    let cleaned = raw_ref.replace('\\', "/");
    let direct = session_dir.join(&cleaned);
    if direct.is_file() {
        return Some(direct);
    }
    let basename = Path::new(&cleaned)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(raw_ref);
    let audio_dir = session_dir.join("Audio Files");
    let in_af = audio_dir.join(basename);
    if in_af.is_file() {
        return Some(in_af);
    }
    if let Ok(rd) = fs::read_dir(&audio_dir) {
        for entry in rd.flatten() {
            if let Some(nm) = entry.file_name().to_str()
                && nm.eq_ignore_ascii_case(basename)
                && entry.path().is_file()
            {
                return Some(entry.path());
            }
        }
    }
    None
}

/// Apply `MediaMode` and return the path string stored inside the target session.
///
/// # Errors
/// Returns I/O error if copying or linking fails.
pub fn materialize_media_ref(
    resolved: &Path,
    src_dir: &Path,
    dst_dir: Option<&Path>,
    basename: &str,
    mode: MediaMode,
) -> Result<String, ConvertError> {
    let target_dir = dst_dir.unwrap_or(src_dir);
    match mode {
        MediaMode::Relative => {
            // If `target_dir/Audio Files/<basename>` resolves (including via symlink), keep a clean
            // sandbox-safe relative `Audio Files/<basename>` path so SoundCraft loads it cleanly.
            if target_dir.join("Audio Files").join(basename).is_file() {
                return Ok(format!("Audio Files/{basename}"));
            }
            if let Ok(rel) = resolved.strip_prefix(target_dir) {
                return Ok(rel.to_string_lossy().replace('\\', "/"));
            }
            Ok(relative_path_string(target_dir, resolved, basename))
        }
        MediaMode::Copy | MediaMode::Link => {
            let af_dir = target_dir.join("Audio Files");
            fs::create_dir_all(&af_dir)?;
            let dst_file = af_dir.join(basename);
            if dst_file != resolved && !dst_file.exists() {
                if mode == MediaMode::Copy {
                    fs::copy(resolved, &dst_file)?;
                } else if fs::hard_link(resolved, &dst_file).is_err() {
                    #[cfg(unix)]
                    std::os::unix::fs::symlink(resolved, &dst_file)?;
                    #[cfg(not(unix))]
                    fs::copy(resolved, &dst_file)?;
                }
            }
            Ok(format!("Audio Files/{basename}"))
        }
    }
}

/// Compute a portable forward-slash relative path from `base` to `target` (never moving files).
#[must_use]
fn relative_path_string(base: &Path, target: &Path, fallback_basename: &str) -> String {
    let canon_base = fs::canonicalize(base).unwrap_or_else(|_| base.to_path_buf());
    let canon_target = fs::canonicalize(target).unwrap_or_else(|_| target.to_path_buf());
    let b_comps: Vec<_> = canon_base.components().collect();
    let t_comps: Vec<_> = canon_target.components().collect();
    let common = b_comps
        .iter()
        .zip(t_comps.iter())
        .take_while(|(a, b)| a == b)
        .count();
    if common == 0 {
        return format!("Audio Files/{fallback_basename}");
    }
    let mut parts = Vec::new();
    for _ in common..b_comps.len() {
        parts.push("..".to_owned());
    }
    for c in &t_comps[common..] {
        parts.push(c.as_os_str().to_string_lossy().into_owned());
    }
    if parts.is_empty() {
        format!("Audio Files/{fallback_basename}")
    } else {
        parts.join("/")
    }
}

/// Fallback descriptor when the audio file cannot be inspected on disk.
#[derive(Debug, Clone, Copy)]
pub struct FallbackSourceSpec {
    pub sample_rate: u32,
    pub channels: u16,
    pub frames: u64,
    pub is_aiff: bool,
}

/// Build a SoundCraft [`Source`] from an inspected on-disk audio file or PT fallback metadata.
#[must_use]
pub fn make_sc_source(
    id: SourceId,
    name: String,
    rel_path: String,
    inspected: Option<&InspectedAudio>,
    fallback: FallbackSourceSpec,
) -> Source {
    match inspected {
        Some(a) => Source {
            id,
            name,
            path: rel_path,
            channels: a.channels.max(1),
            frames: a.frames,
            sample_rate: a.sample_rate.max(1),
            format: a.format,
            time_reference: a.time_reference,
            unsaved: false,
        },
        None => Source {
            id,
            name,
            path: rel_path,
            channels: fallback.channels.max(1),
            frames: fallback.frames,
            sample_rate: fallback.sample_rate.max(1),
            format: if fallback.is_aiff {
                FileFormat::Aiff
            } else {
                FileFormat::Wav
            },
            time_reference: 0,
            unsaved: false,
        },
    }
}

/// Decode compressed SoundCraft audio (`FLAC`/`MP3`/`OGG`/`AAC`/`ALAC`/`CAF`) into a 24-bit BWF
/// PCM `.wav` inside `<out_dir>/Audio Files/_converted/` when exporting to Pro Tools.
///
/// # Errors
/// Returns `ConvertError` on read, decode, encode, or write failure.
pub fn materialize_ptx_pcm_wav(
    src_path: &Path,
    src: &Source,
    out_dir: &Path,
) -> Result<(PathBuf, InspectedAudio), ConvertError> {
    let raw = fs::read(src_path)?;
    let ext = src_path.extension().and_then(|e| e.to_str());
    let (info, buf) =
        craft_audio::decode(&raw, ext).map_err(|e| ConvertError::Audio(e.to_string()))?;
    let conv_dir = out_dir.join("Audio Files").join("_converted");
    fs::create_dir_all(&conv_dir)?;
    let stem = src_path
        .file_stem()
        .and_then(|s| s.to_str())
        .filter(|s| !s.is_empty())
        .unwrap_or(src.name.as_str());
    let wav_name = format!("{stem}.wav");
    let dst_path = conv_dir.join(&wav_name);
    let mut opts = craft_audio::EncodeOptions::new(craft_audio::EncodeFormat::Wav)
        .with_bit_depth(craft_audio::BitDepth::Int24);
    if src.time_reference > 0 {
        let mut bwf = craft_audio::BwfInfo::default();
        bwf.time_reference = src.time_reference;
        opts = opts.with_bwf(bwf);
    }
    let wav_bytes =
        craft_audio::encode(&buf, &opts).map_err(|e| ConvertError::Audio(e.to_string()))?;
    fs::write(&dst_path, &wav_bytes)?;
    let insp = inspect_audio_file(&dst_path).unwrap_or_else(|_| InspectedAudio {
        path: dst_path.clone(),
        file_name: wav_name,
        sample_rate: info.sample_rate,
        channels: info.channels,
        bit_depth: 24,
        is_float: false,
        is_aiff: false,
        frames: info.frames,
        data_offset: 44,
        time_reference: src.time_reference,
        filetime: path_filetime(&dst_path),
        format: FileFormat::Wav,
    });
    Ok((dst_path, insp))
}

/// Merge split-mono `.L` / `.R` PCM files into an interleaved stereo 24-bit BWF `.wav`
/// inside `<out_dir>/Audio Files/_converted/` for SoundCraft stereo playback.
///
/// # Errors
/// Returns `ConvertError` on read, decode, encode, or write failure.
pub fn materialize_split_stereo_wav(
    left_path: &Path,
    right_path: &Path,
    base_stem: &str,
    out_dir: &Path,
) -> Result<(PathBuf, InspectedAudio), ConvertError> {
    let raw_l = fs::read(left_path)?;
    let raw_r = fs::read(right_path)?;
    let ext_l = left_path.extension().and_then(|e| e.to_str());
    let ext_r = right_path.extension().and_then(|e| e.to_str());
    let (info_l, buf_l) =
        craft_audio::decode(&raw_l, ext_l).map_err(|e| ConvertError::Audio(e.to_string()))?;
    let (_info_r, buf_r) =
        craft_audio::decode(&raw_r, ext_r).map_err(|e| ConvertError::Audio(e.to_string()))?;
    let ch_l = buf_l
        .channels
        .first()
        .cloned()
        .unwrap_or_else(|| vec![0.0; buf_l.frames()]);
    let ch_r = buf_r
        .channels
        .first()
        .cloned()
        .unwrap_or_else(|| vec![0.0; ch_l.len()]);
    let frames = ch_l.len().min(ch_r.len());
    let mut stereo_buf = craft_audio::AudioBuffer::new(info_l.sample_rate.max(1), 2, frames);
    stereo_buf.channels[0].copy_from_slice(&ch_l[..frames]);
    stereo_buf.channels[1].copy_from_slice(&ch_r[..frames]);

    let time_ref = inspect_audio_file(left_path).map_or(0, |i| i.time_reference);
    let conv_dir = out_dir.join("Audio Files").join("_converted");
    fs::create_dir_all(&conv_dir)?;
    let wav_name = format!("{base_stem}.stereo.wav");
    let dst_path = conv_dir.join(&wav_name);
    let mut opts = craft_audio::EncodeOptions::new(craft_audio::EncodeFormat::Wav)
        .with_bit_depth(craft_audio::BitDepth::Int24);
    if time_ref > 0 {
        let mut bwf = craft_audio::BwfInfo::default();
        bwf.time_reference = time_ref;
        opts = opts.with_bwf(bwf);
    }
    let wav_bytes =
        craft_audio::encode(&stereo_buf, &opts).map_err(|e| ConvertError::Audio(e.to_string()))?;
    fs::write(&dst_path, &wav_bytes)?;
    let insp = inspect_audio_file(&dst_path)?;
    Ok((dst_path, insp))
}
