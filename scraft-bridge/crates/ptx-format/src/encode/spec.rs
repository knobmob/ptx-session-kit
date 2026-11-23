// Version: 0.7.0 (beta) | Date: 2026-11-23
//! Clean-room field specification types for building a complete `.ptx` binary session.

use std::collections::BTreeMap;

/// Clean-room track kinds.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BuildTrackKind {
    Audio,
    Aux,
    Master,
    Midi,
    Instrument,
    BasicFolder,
    RoutingFolder,
}

impl BuildTrackKind {
    /// Pro Tools track-kind numeric code (`0x2519`, `0x210B`).
    #[must_use]
    pub const fn code(self) -> u16 {
        match self {
            Self::Audio => 0,
            Self::Midi => 1,
            Self::Aux | Self::RoutingFolder => 2,
            Self::Master => 5,
            Self::Instrument => 7,
            Self::BasicFolder => 11,
        }
    }

    /// True if track is a folder (`BasicFolder` or `RoutingFolder`).
    #[must_use]
    pub const fn is_folder(self) -> bool {
        matches!(self, Self::BasicFolder | Self::RoutingFolder)
    }

    /// True if track carries audio (`Audio`, `Aux`, `Master`, `Instrument`, `RoutingFolder`).
    #[must_use]
    pub const fn has_strip(self) -> bool {
        !matches!(self, Self::Midi | Self::BasicFolder)
    }
}

/// Timebase for tracks and clips.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum BuildTimebase {
    #[default]
    Samples,
    Ticks,
}

/// Audio file descriptor specification for `0x1004`/`0x1003`/`0x103A`.
#[derive(Debug, Clone, PartialEq)]
pub struct BuildAudioFile {
    pub file_name: String,
    pub sample_rate: u32,
    pub channels: u8,
    pub bit_depth: u8,
    pub is_float: bool,
    pub is_aiff: bool,
    pub frames: u64,
    /// Offset in bytes of the sample data chunk inside the file (`< 65536`).
    pub data_offset: u16,
    /// Windows FILETIME (`st_mtime_ns / 100 + 116444736000000000`).
    pub filetime: u64,
    /// Optional 16-byte SMPTE material UMID tail/id; generated when `None`.
    pub umid_file_id: Option<[u8; 8]>,
}

/// Fade slope shape.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum BuildFadeSlope {
    #[default]
    EqualPower,
    EqualGain,
}

/// Fade kind on a clip placement.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BuildFadeKind {
    FadeIn,
    FadeOut,
    Crossfade,
}

/// Fade specification attached to an audio clip placement.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BuildFade {
    pub kind: BuildFadeKind,
    pub slope: BuildFadeSlope,
    pub length_samples: u64,
    /// Optional pre-roll samples before cut for centered `Crossfade` (`34 B` native layout).
    pub pre_roll_samples: Option<u64>,
}

/// Loop metadata (`0x242B`) attached to an audio or MIDI placement.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BuildClipLoop {
    pub mode: u8,
    pub bars: u32,
    pub beats: u32,
    pub ticks: u32,
    pub count: u32,
    pub trim: u64,
    pub iter: u64,
    pub is_ticks: bool,
}

/// Audio clip placement on a track playlist (`0x1050 > 0x104F` + `0x2629 > 0x2628`).
#[derive(Debug, Clone, PartialEq)]
pub struct BuildAudioClip {
    pub name: String,
    /// Indices into `PtxBuildSpec.audio_files` (`[mono_or_stereo_idx]` or `[left_idx, right_idx]` for split-mono stereo).
    pub file_indices: Vec<usize>,
    /// Source offset in samples within the audio file(s).
    pub file_offset: u64,
    /// Clip length in samples.
    pub length_samples: u64,
    /// Placement start position (in track timebase units: samples or ticks).
    pub start_pos: u64,
    /// True if `start_pos` is in ticks (`0x40`); false for samples (`0x00`).
    pub pos_in_ticks: bool,
    pub muted: bool,
    /// Optional sync-point offset from `start_pos` in samples (when non-zero).
    pub sync_offset: Option<u64>,
    /// Clip gain lane breakpoints (`[(offset_samples, db)]`); empty = default `0.0 dB` (no pool entry).
    pub clip_gain_points: Vec<(u32, f32)>,
    pub fade_in: Option<BuildFade>,
    pub fade_out: Option<BuildFade>,
    pub clip_loop: Option<BuildClipLoop>,
    /// Optional clip-group identifier (`0x262C`/`0x2428` bundling); contiguous clips sharing an ID form one clip group.
    pub group: Option<u64>,
}

/// MIDI note `[start_ticks_rel_to_clip, key, length_ticks, velocity]`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BuildMidiNote {
    pub start_ticks: u64,
    pub key: u8,
    pub length_ticks: u64,
    pub velocity: u8,
}

/// MIDI controller / pitch bend / program / pressure curve.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BuildMidiCtrl {
    /// `1` pitch_bend, `2` controller, `3` program, `4` channel_pressure, `5` poly_pressure.
    pub kind: u8,
    pub number: u8,
    /// Points as `(ticks_rel, signed_val)`.
    pub points: Vec<(u64, i32)>,
}

/// MIDI clip placed on a MIDI or Instrument track.
#[derive(Debug, Clone, PartialEq)]
pub struct BuildMidiClip {
    pub name: String,
    pub start_pos: u64,
    pub pos_in_ticks: bool,
    pub length_ticks: u64,
    pub notes: Vec<BuildMidiNote>,
    pub controllers: Vec<BuildMidiCtrl>,
    /// SysEx events `(ticks_rel, payload_bytes)`.
    pub sysex: Vec<(u64, Vec<u8>)>,
    pub muted: bool,
    pub clip_loop: Option<BuildClipLoop>,
}

/// Automated parameter lane inside an insert slot (`0x260F > 0x260B`).
#[derive(Debug, Clone, PartialEq)]
pub struct BuildInsertAutoLane {
    pub param_name: String,
    pub param_id: String,
    pub param_index: u32,
    pub points: Vec<(u64, f64)>,
}

/// Stock plug-in parameter value override (`f64` for `d_`, `i32` for `l_` or `All `, normalized `[0..1]` for `norm`).
#[derive(Debug, Clone, PartialEq)]
pub enum BuildParamVal {
    Float(f64),
    Int(i32),
    Bool(bool),
    Norm(f64),
}

/// Insert slot (`a`..`j`, slot index `0..10`) on an audio-carrying track.
#[derive(Debug, Clone, PartialEq)]
pub struct BuildInsert {
    pub slot_index: usize,
    /// Stock plug-in display name (e.g. `"EQ3 7-Band"`, `"Trim"`, `"Dyn3 Compressor/Limiter"`).
    pub plugin_name: String,
    pub bypass: bool,
    pub active: bool,
    pub multi_mono: bool,
    pub params: BTreeMap<String, BuildParamVal>,
    pub automation: Vec<BuildInsertAutoLane>,
}

/// Send slot (`a`..`j`, slot index `0..10`) on an audio-carrying track.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct BuildSend {
    pub slot_index: usize,
    /// Target internal bus name (must match an entry in `PtxBuildSpec.busses`).
    pub bus_name: String,
    /// Level in tenths of a dB (`-1440..=120`).
    pub level_tenths_db: i16,
    /// Pan (`-100..=100`).
    pub pan: i16,
    pub mute: bool,
    pub pre_fader: bool,
    pub active: bool,
    /// Optional volume automation lane `(pos, tenths_db)`.
    pub volume_points: Vec<(u64, i16)>,
    /// Optional mute automation lane `(pos, 0_or_1)`.
    pub mute_points: Vec<(u64, i16)>,
    /// Optional pan automation lane `(pos, -100..=100)`.
    pub pan_points: Vec<(u64, i16)>,
}

/// Mixer automation lane (`0x260A`).
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct BuildAutoLane {
    /// Breakpoints `(pos, tenths_db | pan_pct | 0_or_1)`.
    pub points: Vec<(u64, i16)>,
}

/// Track definition in `PtxBuildSpec`.
#[derive(Debug, Clone, PartialEq)]
pub struct BuildTrack {
    pub name: String,
    pub kind: BuildTrackKind,
    pub stereo: bool,
    pub timebase: BuildTimebase,
    pub volume_tenths_db: i16,
    /// Mono `[pan]` (`-100..=100`) or stereo `[left, right]` (`-100..=100`).
    pub pan: Vec<i16>,
    pub mute: bool,
    pub solo: bool,
    pub hidden: bool,
    pub inactive: bool,
    pub record_enable: bool,
    /// `0` off, `1` read, `2` touch, `3` latch, `4` write.
    pub automation_mode: u8,
    /// User delay compensation in samples (`0x261B` / `0x2621`).
    pub user_delay: i32,
    pub comment: String,
    /// Track colour index (`-2` default, `25..=93` palette).
    pub colour: Option<i16>,
    /// Output destination: `None` / `"Out 1-2"` / internal bus name.
    pub output_bus: Option<String>,
    /// Input internal bus name (Aux / Audio / RoutingFolder).
    pub input_bus: Option<String>,
    /// Optional parent folder track name (`BasicFolder` or `RoutingFolder`).
    pub folder_name: Option<String>,
    pub volume_lane: BuildAutoLane,
    pub pan_lanes: Vec<BuildAutoLane>,
    pub mute_lane: BuildAutoLane,
    pub inserts: Vec<BuildInsert>,
    pub sends: Vec<BuildSend>,
    pub audio_clips: Vec<BuildAudioClip>,
    pub midi_clips: Vec<BuildMidiClip>,
}

impl Default for BuildTrack {
    fn default() -> Self {
        Self {
            name: "Audio 1".to_owned(),
            kind: BuildTrackKind::Audio,
            stereo: false,
            timebase: BuildTimebase::Samples,
            volume_tenths_db: 0,
            pan: vec![0],
            mute: false,
            solo: false,
            hidden: false,
            inactive: false,
            record_enable: false,
            automation_mode: 1,
            user_delay: 0,
            comment: String::new(),
            colour: None,
            output_bus: None,
            input_bus: None,
            folder_name: None,
            volume_lane: BuildAutoLane::default(),
            pan_lanes: Vec::new(),
            mute_lane: BuildAutoLane::default(),
            inserts: Vec::new(),
            sends: Vec::new(),
            audio_clips: Vec::new(),
            midi_clips: Vec::new(),
        }
    }
}

/// Internal mix bus path (`0x2602`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BuildBus {
    pub name: String,
    pub stereo: bool,
}

/// Memory location (`0x2077`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BuildMarker {
    pub number: u16,
    pub name: String,
    pub start: u64,
    pub end: u64,
    pub is_ticks: bool,
    pub is_selection: bool,
    pub comment: String,
}

/// Track group (`0x202A`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BuildGroup {
    pub name: String,
    /// `1` Edit, `2` Mix, `3` Mix/Edit (matches `tools/ptx_edit.py`).
    pub group_type: u8,
    pub enabled: bool,
    pub member_track_names: Vec<String>,
}

/// Constant tempo event (`0x2028`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BuildTempoPoint {
    pub ticks: u64,
    pub bpm: f64,
}

/// Meter event (`0x2029`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BuildMeterPoint {
    pub ticks: u64,
    pub bar: u32,
    pub numerator: u32,
    pub denominator: u32,
}

/// Key signature event (`0x2432`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BuildKeySig {
    pub ticks: u64,
    pub major: bool,
    /// Signed sharps (`-7..=+7`).
    pub sharps: i8,
}

/// Transport, edit mode, and tool state (`0x2024`, `0x2056`, `0x2058`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BuildEditState {
    /// `0` Shuffle, `1` Slip, `2` Spot, `3` Grid.
    pub edit_mode: u16,
    /// `1` Zoom, `3` Trim, `4` Selector, `5` Grabber, `6` Scrubber, `8` Pencil.
    pub edit_tool: u8,
    pub smart_tool: bool,
    pub loop_playback: bool,
    /// `0` Normal, `1` Loop, `2` Destructive, `3` QuickPunch.
    pub record_mode: u8,
}

impl Default for BuildEditState {
    fn default() -> Self {
        Self {
            edit_mode: 3,
            edit_tool: 4,
            smart_tool: false,
            loop_playback: false,
            record_mode: 0,
        }
    }
}

/// Complete clean-room `.ptx` session build specification.
#[derive(Debug, Clone, PartialEq)]
pub struct PtxBuildSpec {
    pub sample_rate: u32,
    pub bit_depth: u8,
    pub is_float: bool,
    pub is_aiff: bool,
    pub tc_rate_code: Option<u8>,
    pub tc_start: Option<String>,
    /// Optional audio pull factor (`0x2023`: `12000` None, `12011` +0.1%, `11988` -0.1%, etc.).
    pub pull_code: Option<u16>,
    /// Optional transport / edit-mode / tool state (`0x2024`, `0x2056`, `0x2058`).
    pub edit_state: Option<BuildEditState>,
    /// Optional display names for clip groups (`BuildAudioClip::group` -> `0x262C`/`0x2424`).
    pub clip_group_names: BTreeMap<u64, String>,
    pub xor_seed: u8,
    pub main_out_name: String,
    pub volume_name: String,
    pub audio_folder_chain: Vec<String>,
    pub tempo: Vec<BuildTempoPoint>,
    pub meter: Vec<BuildMeterPoint>,
    pub key_signatures: Vec<BuildKeySig>,
    pub markers: Vec<BuildMarker>,
    pub groups: Vec<BuildGroup>,
    pub busses: Vec<BuildBus>,
    pub audio_files: Vec<BuildAudioFile>,
    pub tracks: Vec<BuildTrack>,
}

impl Default for PtxBuildSpec {
    fn default() -> Self {
        Self {
            sample_rate: 48_000,
            bit_depth: 24,
            is_float: false,
            is_aiff: false,
            tc_rate_code: None,
            tc_start: None,
            pull_code: None,
            edit_state: None,
            clip_group_names: BTreeMap::new(),
            xor_seed: 0x5c,
            main_out_name: "Out 1-2".to_owned(),
            volume_name: "Macintosh HD".to_owned(),
            audio_folder_chain: vec!["Users".to_owned(), "Shared".to_owned()],
            tempo: vec![BuildTempoPoint { ticks: 0, bpm: 120.0 }],
            meter: vec![BuildMeterPoint {
                ticks: 0,
                bar: 1,
                numerator: 4,
                denominator: 4,
            }],
            key_signatures: Vec::new(),
            markers: Vec::new(),
            groups: Vec::new(),
            busses: Vec::new(),
            audio_files: Vec::new(),
            tracks: Vec::new(),
        }
    }
}
