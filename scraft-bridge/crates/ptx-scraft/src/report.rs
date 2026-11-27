// Version: 0.7.0 (beta) | Date: 2026-11-27
//! Loss-classification ledger (`<stem>.ptx_convert.json`) and sidecar (`<stem>.ptxcarry.json`).

use std::collections::BTreeMap;
use std::path::Path;

use ptx_format::decode::timeline::{SessionSettings, TimelineInfo};
use serde::{Deserialize, Serialize};

/// Fidelity level assigned to every converted element in the conversion ledger.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Fidelity {
    /// Exact representation in both formats.
    Native,
    /// Represented with documented scaling, subdivision, or stock-DSP substitution.
    Approx,
    /// Unrepresentable in SoundCraft natively; preserved in `<stem>.ptxcarry.json` for round-trip.
    Carry,
    /// Dropped / absent in target format (only counted when non-zero data could not be mapped or carried).
    Absent,
}

/// Summary counts by fidelity class.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct ReportCounts {
    pub native: usize,
    pub approx: usize,
    pub carry: usize,
    pub absent: usize,
}

/// One line item in the conversion ledger.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LedgerEntry {
    pub domain: String,
    pub item: String,
    pub fidelity: Fidelity,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

/// Structured `<stem>.ptx_convert.json` report emitted alongside every conversion.
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct ConversionReport {
    pub version: u32,
    pub direction: String,
    pub source_path: String,
    pub target_path: String,
    pub media_mode: String,
    pub loop_handling: String,
    pub summary: ReportCounts,
    pub warnings: Vec<String>,
    pub entries: Vec<LedgerEntry>,
}

impl ConversionReport {
    /// Create a new report for a conversion pass.
    #[must_use]
    pub fn new(
        direction: &str,
        source_path: &str,
        target_path: &str,
        media_mode: &str,
        loop_handling: &str,
    ) -> Self {
        Self {
            version: 1,
            direction: direction.to_owned(),
            source_path: source_path.to_owned(),
            target_path: target_path.to_owned(),
            media_mode: media_mode.to_owned(),
            loop_handling: loop_handling.to_owned(),
            summary: ReportCounts::default(),
            warnings: Vec::new(),
            entries: Vec::new(),
        }
    }

    /// Append a classified ledger entry and increment the matching summary counter.
    pub fn record(
        &mut self,
        domain: impl Into<String>,
        item: impl Into<String>,
        fidelity: Fidelity,
        note: Option<String>,
    ) {
        match fidelity {
            Fidelity::Native => self.summary.native += 1,
            Fidelity::Approx => self.summary.approx += 1,
            Fidelity::Carry => self.summary.carry += 1,
            Fidelity::Absent => self.summary.absent += 1,
        }
        self.entries.push(LedgerEntry {
            domain: domain.into(),
            item: item.into(),
            fidelity,
            note,
        });
    }

    /// True if any item was classified `Carry` or `Absent`.
    #[must_use]
    pub fn has_loss(&self) -> bool {
        self.summary.carry > 0 || self.summary.absent > 0
    }

    /// First non-native loss description for `--strict` mode.
    #[must_use]
    pub fn first_loss_message(&self) -> Option<String> {
        self.entries
            .iter()
            .find(|e| matches!(e.fidelity, Fidelity::Carry | Fidelity::Absent))
            .map(|e| format!("{}/{} ({:?})", e.domain, e.item, e.fidelity))
    }

    /// Write pretty JSON to `path`.
    ///
    /// # Errors
    /// Returns serialization or I/O errors.
    pub fn write_to(&self, path: &Path) -> Result<(), crate::ConvertError> {
        let json = serde_json::to_string_pretty(self)?;
        std::fs::write(path, json)?;
        Ok(())
    }
}

/// Carried audio file metadata not natively represented in `.scraft` `Source`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CarryAudioFile {
    pub file_name: String,
    pub bit_depth: u8,
    pub is_float: bool,
    pub is_aiff: bool,
    pub data_offset: u16,
    pub filetime: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub umid: Option<String>,
}

/// Carried plug-in instance state for slots without exact SoundCraft native equivalence.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CarryInsert {
    pub slot_index: usize,
    pub plugin_name: String,
    pub vendor_id: String,
    pub bypass: bool,
    pub active: bool,
    pub multi_mono: bool,
    #[serde(default)]
    pub params: BTreeMap<String, serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub values_i32: Option<Vec<i32>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub settings_file: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub preset: Option<String>,
}

/// Carried per-track metadata (`user_delay`, `colour`, raw inserts, elastic audio, MIDI MPE).
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
pub struct CarryTrack {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ptx_kind: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_delay: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub synthesized_user_delay_slot: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub colour: Option<i16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub elastic_mode: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mpe_mode: Option<String>,
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    pub inserts: Vec<CarryInsert>,
}

/// Carried clip metadata (original clip loop descriptor, crossfade pre-roll, split-mono `.L`/`.R`, MPE, MIDI SysEx).
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct CarryClip {
    pub loop_mode: Option<u8>,
    pub loop_bars: Option<u32>,
    pub loop_beats: Option<u32>,
    pub loop_ticks: Option<u32>,
    pub loop_count: Option<u32>,
    pub loop_iter_ticks: Option<u64>,
    pub loop_iter_samples: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub crossfade_pre_roll: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub split_pair: Option<(String, String)>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub mpe_curves: Vec<ptx_format::decode::midi::MpeCurve>,
    pub sysex: Vec<(u64, String)>,
}

/// `<stem>.ptxcarry.json` lossless round-trip sidecar.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
pub struct CarrySidecar {
    pub version: u32,
    pub xor_seed: u8,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_version: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timeline: Option<TimelineInfo>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_settings: Option<SessionSettings>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub write_enables: Option<Vec<u8>>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub audio_files: Vec<CarryAudioFile>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub tracks: BTreeMap<String, CarryTrack>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub clips: BTreeMap<String, CarryClip>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub clip_group_names: BTreeMap<u64, String>,
}

impl CarrySidecar {
    /// Load sidecar JSON if the file exists.
    ///
    /// # Errors
    /// Returns I/O or JSON parse error when the file exists but cannot be read/parsed.
    pub fn load_if_exists(path: &Path) -> Result<Option<Self>, crate::ConvertError> {
        if !path.exists() {
            return Ok(None);
        }
        let txt = std::fs::read_to_string(path)?;
        let parsed: Self = serde_json::from_str(&txt)?;
        Ok(Some(parsed))
    }

    /// Write sidecar JSON to `path`.
    ///
    /// # Errors
    /// Returns I/O or JSON serialization error.
    pub fn write_to(&self, path: &Path) -> Result<(), crate::ConvertError> {
        let txt = serde_json::to_string_pretty(self)?;
        std::fs::write(path, txt)?;
        Ok(())
    }
}
