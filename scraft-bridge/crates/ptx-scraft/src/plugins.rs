// Version: 0.7.0 (beta) | Date: 2026-11-23
//! Bidirectional stock DSP plugin parameter & automation mapping (`PTX <-> SoundCraft v0.20.1`).

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::sync::LazyLock;

use craft_scraft_format::{AutoParam, AutomationLane, Insert as ScInsert};
use craft_scraft_format::soundcraft_time::{SampleRate, Samples, TempoMap};
use ptx_format::decode::plugins::Insert as PtxInsert;
use ptx_format::decode::plugins::trim_norm_to_db;
use ptx_format::encode::plugins_data::{STOCK_PLUGINS, lookup_stock_plugin, trim_db_to_norm};
use ptx_format::encode::spec::{BuildInsert, BuildInsertAutoLane, BuildParamVal};
use ptx_format::primitives::plain_ticks;
use serde::{Deserialize, Serialize};

use crate::automation::{ptx_ticks_to_samples, samples_to_ptx_ticks};
use crate::error::ConvertError;
use crate::report::{CarryInsert, ConversionReport, Fidelity};

const DEFAULT_PLUGIN_MAP_JSON: &str = include_str!("../plugin_map.json");
const LOG_SUBDIV_REL_TOL: f64 = 0.005;
const LOG_SUBDIV_MAX_DEPTH: u8 = 7;

/// SoundCraft DSP parameter taper kind for continuous `0x260F <-> AutoParam::Plugin` curves.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ParamTaper {
    Linear,
    Log,
    Toggle,
}

/// Externalized per-parameter physical range and taper specification (`plugin_map.json`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParamRangeSpec {
    pub sc_key: String,
    pub min: f64,
    pub max: f64,
    pub taper: ParamTaper,
    #[serde(default)]
    pub zero_db_norm: Option<f64>,
}

/// Externalized stock DSP parameter & trim curve configuration (`plugin_map.json`).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PluginMapConfig {
    #[serde(default)]
    pub version: u32,
    #[serde(default)]
    pub params: BTreeMap<String, Vec<ParamRangeSpec>>,
    #[serde(default)]
    pub trim_knots: Vec<[f64; 2]>,
}

static DEFAULT_PLUGIN_MAP: LazyLock<PluginMapConfig> =
    LazyLock::new(|| serde_json::from_str(DEFAULT_PLUGIN_MAP_JSON).unwrap_or_default());

/// Return the embedded default [`PluginMapConfig`] parsed from `plugin_map.json`.
#[must_use]
pub fn default_config() -> &'static PluginMapConfig {
    &DEFAULT_PLUGIN_MAP
}

/// Load a custom [`PluginMapConfig`] from `path`, or clone the embedded default when `None`.
pub fn load_plugin_config(path: Option<&Path>) -> Result<PluginMapConfig, ConvertError> {
    match path {
        Some(p) => {
            let text = fs::read_to_string(p)?;
            Ok(serde_json::from_str(&text)?)
        }
        None => Ok(default_config().clone()),
    }
}

/// Resolve canonical Pro Tools display plugin name from a decoded [`PtxInsert`].
#[must_use]
pub fn resolve_ptx_plugin_name(ins: &PtxInsert) -> String {
    if !ins.vendor_id.is_empty() {
        if let Some(canon) = STOCK_PLUGINS
            .iter()
            .find_map(|s| (s.vid == ins.vendor_id).then_some(s.name))
        {
            return canon.to_owned();
        }
        match ins.vendor_id.as_str() {
            "com.avid.aax.dyn3.Expander" => return "Dyn3 Expander/Gate".to_owned(),
            "com.avid.aax.dyn3.DeEsser" => return "Dyn3 De-Esser".to_owned(),
            "com.avid.aax.maxim" | "com.digidesign.aax.maxim" => return "Maxim".to_owned(),
            _ => {}
        }
    }
    if let Some(p) = &ins.plugin
        && lookup_stock_plugin(p).is_some()
    {
        return p.clone();
    }
    if lookup_stock_plugin(&ins.name).is_some() {
        return ins.name.clone();
    }
    ins.plugin.clone().unwrap_or_else(|| ins.name.clone())
}

fn json_f64(map: &BTreeMap<String, serde_json::Value>, key: &str) -> Option<f64> {
    let v = map.get(key)?;
    if let Some(f) = v.as_f64() {
        return Some(f);
    }
    v.as_i64().map(|i| i as f64)
}

fn json_i64(map: &BTreeMap<String, serde_json::Value>, key: &str) -> Option<i64> {
    let v = map.get(key)?;
    if let Some(i) = v.as_i64() {
        return Some(i);
    }
    v.as_f64().map(|f| f.round() as i64)
}

fn set_param(out: &mut BTreeMap<String, f32>, key: &str, val: f64, min: f64, max: f64) {
    if val.is_finite() {
        out.insert(key.to_owned(), val.clamp(min, max) as f32);
    }
}

fn eq1_pt_type_to_sc(pt_type: i64) -> f64 {
    // PT EQ3 1-Band `l_type`: 0=HPF, 1=LPF, 2=Notch, 3=Peak, 4=LowShelf, 5=HighShelf
    // SC `eq_1band` `type`: 0=Peak, 1=Low Shelf, 2=High Shelf, 3=High Pass, 4=Low Pass, 5=Notch, 6=Band Pass
    match pt_type {
        0 => 3.0,
        1 => 4.0,
        2 => 5.0,
        3 => 0.0,
        4 => 1.0,
        5 => 2.0,
        _ => 0.0,
    }
}

fn eq1_sc_type_to_pt(sc_type: f64) -> i32 {
    match sc_type.round() as i32 {
        0 => 3, // Peak
        1 => 4, // Low Shelf
        2 => 5, // High Shelf
        3 => 0, // HPF
        4 => 1, // LPF
        5 => 2, // Notch
        _ => 3,
    }
}

fn hz_log_norm(hz: f64, min_hz: f64, max_hz: f64) -> f64 {
    if hz <= min_hz {
        return 0.0;
    }
    if hz >= max_hz {
        return 1.0;
    }
    (hz / min_hz).ln() / (max_hz / min_hz).ln()
}

fn norm_to_hz_log(u: f64, min_hz: f64, max_hz: f64) -> f64 {
    min_hz * (max_hz / min_hz).powf(u.clamp(0.0, 1.0))
}

fn param_spec<'a>(cfg: &'a PluginMapConfig, sc_plugin: &str, sc_key: &str) -> Option<&'a ParamRangeSpec> {
    cfg.params
        .get(sc_plugin)?
        .iter()
        .find(|r| r.sc_key == sc_key)
}

/// Map PT `0x260F` automation `(param_name, param_id)` -> `(sc_param_key, pt_param_id_or_desc)`.
fn map_ptx_auto_param_key(sc_plugin: &str, name: &str, pid: &str) -> Option<&'static str> {
    let n = name.to_ascii_lowercase();
    let p = pid.to_ascii_lowercase();
    match sc_plugin {
        "eq_1band" => match p.as_str() {
            "gain" | "d_gain" => Some("gain"),
            "ctrf" | "freq" | "d_ctrf" => Some("freq"),
            "bndw" | "q" | "d_bndw" => Some("q"),
            "trim" | "d_trim" => Some("output_gain"),
            "type" | "l_type" => Some("type"),
            _ if n.contains("gain") && !n.contains("trim") => Some("gain"),
            _ if n.contains("freq") => Some("freq"),
            _ if n == "q" || n.contains("band") => Some("q"),
            _ if n.contains("trim") || n.contains("out") => Some("output_gain"),
            _ => None,
        },
        "eq_7band" => match p.as_str() {
            "inpt" | "d_inpt" => Some("input_gain"),
            "outp" | "d_outp" => Some("output_gain"),
            "in 1" | "l_in 1" => Some("hpf_on"),
            "frq1" | "d_frq1" => Some("hpf_freq"),
            "hpfs" | "l_hpfs" => Some("hpf_slope"),
            "frq2" | "d_frq2" => Some("low_shelf_freq"),
            "gai2" | "d_gai2" => Some("low_shelf_gain"),
            "bnd2" | "d_bnd2" => Some("low_shelf_q"),
            "frq3" | "d_frq3" => Some("low_mid_freq"),
            "gai3" | "d_gai3" => Some("low_mid_gain"),
            "bnd3" | "d_bnd3" => Some("low_mid_q"),
            "frq4" | "d_frq4" => Some("mid_freq"),
            "gai4" | "d_gai4" => Some("mid_gain"),
            "bnd4" | "d_bnd4" => Some("mid_q"),
            "frq5" | "d_frq5" => Some("high_mid_freq"),
            "gai5" | "d_gai5" => Some("high_mid_gain"),
            "bnd5" | "d_bnd5" => Some("high_mid_q"),
            "frq6" | "d_frq6" => Some("high_shelf_freq"),
            "gai6" | "d_gai6" => Some("high_shelf_gain"),
            "bnd6" | "d_bnd6" => Some("high_shelf_q"),
            "in 7" | "l_in 7" => Some("lpf_on"),
            "frq7" | "d_frq7" => Some("lpf_freq"),
            "lpfs" | "l_lpfs" => Some("lpf_slope"),
            _ => None,
        },
        "compressor" => {
            if n.contains("thresh") || p == "sldc" {
                Some("threshold")
            } else if n.contains("ratio") || p == "sld2" {
                Some("ratio")
            } else if n.contains("attack") || p == "sld1" {
                Some("attack")
            } else if n.contains("release") || p == "sld3" {
                Some("release")
            } else if n.contains("knee") || p == "sldd" {
                Some("knee")
            } else if n.contains("gain") || n.contains("makeup") || p == "sldg" {
                Some("makeup")
            } else if p == "lofe" {
                Some("sc_hpf_on")
            } else if p == "loff" {
                Some("sc_hpf_freq")
            } else {
                None
            }
        }
        "expander_gate" => {
            if n.contains("thresh") || p == "sldc" {
                Some("threshold")
            } else if n.contains("ratio") || p == "sld2" {
                Some("ratio")
            } else if n.contains("range") || p == "sld4" {
                Some("range")
            } else if n.contains("attack") || p == "sld1" {
                Some("attack")
            } else if n.contains("hold") || p == "sldh" {
                Some("hold")
            } else if n.contains("release") || p == "sld3" {
                Some("release")
            } else {
                None
            }
        }
        "de_esser" => {
            if n.contains("freq") {
                Some("freq")
            } else if n.contains("range") {
                Some("range")
            } else if n.contains("thresh") {
                Some("threshold")
            } else if n.contains("listen") {
                Some("listen")
            } else {
                None
            }
        }
        "maximizer" => {
            if n.contains("thresh") {
                Some("threshold")
            } else if n.contains("ceil") {
                Some("ceiling")
            } else if n.contains("release") {
                Some("release")
            } else {
                None
            }
        }
        "trim" => {
            if n.contains("gain") || p.contains("gain") {
                Some("gain")
            } else if n.contains("phase") || n.contains("invert") {
                Some("invert")
            } else {
                None
            }
        }
        "time_shift" => {
            if n.contains("delay") {
                Some("delay_samples")
            } else {
                None
            }
        }
        "auto_pan" => {
            if n.contains("output") || p == "outg" {
                Some("output")
            } else if n.contains("width") || p == "wdth" {
                Some("width")
            } else if n.contains("pos") || p == "posi" {
                Some("manual")
            } else if n.contains("rate") || p == "temp" {
                Some("rate")
            } else {
                None
            }
        }
        "channel_strip" => {
            if n == "input trim" {
                Some("input_gain")
            } else if n == "fader volume" {
                Some("output_gain")
            } else if n == "cmp in/out" {
                Some("comp_on")
            } else if n == "cmp threshold" {
                Some("comp_threshold")
            } else if n == "cmp ratio" {
                Some("comp_ratio")
            } else if n == "cmp attack time" {
                Some("comp_attack")
            } else if n == "cmp release time" {
                Some("comp_release")
            } else if n == "cmp gain makeup" {
                Some("comp_makeup")
            } else if n == "exp in/out" {
                Some("gate_on")
            } else if n == "exp threshold" {
                Some("gate_threshold")
            } else if n == "exp depth" {
                Some("gate_range")
            } else if n == "exp release time" {
                Some("gate_release")
            } else if n == "eq on/off" {
                Some("eq_on")
            } else if n == "filter 1 in/out" {
                Some("hpf_on")
            } else if n == "filter 1 frequency" {
                Some("hpf_freq")
            } else if n == "eq low gain" {
                Some("low_gain")
            } else if n == "eq low frequency" {
                Some("low_freq")
            } else if n == "eq low-mid gain" {
                Some("mid_gain")
            } else if n == "eq low-mid frequency" {
                Some("mid_freq")
            } else if n == "eq low-mid q" {
                Some("mid_q")
            } else if n == "eq high gain" {
                Some("high_gain")
            } else if n == "eq high frequency" {
                Some("high_freq")
            } else {
                None
            }
        }
        _ => None,
    }
}

/// Reverse map SoundCraft parameter id back to PT `(param_name, param_id, param_index)`.
fn map_sc_auto_param_to_pt(pt_name: &str, sc_key: &str) -> Option<(&'static str, &'static str, u32)> {
    match (pt_name, sc_key) {
        ("EQ3 1-Band", "gain") => Some(("Gain", "gain", 1)),
        ("EQ3 1-Band", "freq") => Some(("Freq", "ctrf", 2)),
        ("EQ3 1-Band", "q") => Some(("Q", "bndw", 3)),
        ("EQ3 1-Band", "output_gain") => Some(("Trim", "trim", 6)),
        ("EQ3 7-Band", "input_gain") => Some(("Input Gain", "inpt", 2)),
        ("EQ3 7-Band", "output_gain") => Some(("Output Gain", "outp", 3)),
        ("EQ3 7-Band", "hpf_freq") => Some(("HPF Freq", "frq1", 9)),
        ("EQ3 7-Band", "low_shelf_gain") => Some(("LF Gain", "gai2", 11)),
        ("EQ3 7-Band", "low_shelf_freq") => Some(("LF Freq", "frq2", 12)),
        ("EQ3 7-Band", "low_mid_gain") => Some(("LMF Gain", "gai3", 16)),
        ("EQ3 7-Band", "low_mid_freq") => Some(("LMF Freq", "frq3", 17)),
        ("EQ3 7-Band", "mid_gain") => Some(("MF Gain", "gai4", 20)),
        ("EQ3 7-Band", "mid_freq") => Some(("MF Freq", "frq4", 21)),
        ("EQ3 7-Band", "high_mid_gain") => Some(("HMF Gain", "gai5", 24)),
        ("EQ3 7-Band", "high_mid_freq") => Some(("HMF Freq", "frq5", 25)),
        ("EQ3 7-Band", "high_shelf_gain") => Some(("HF Gain", "gai6", 28)),
        ("EQ3 7-Band", "high_shelf_freq") => Some(("HF Freq", "frq6", 29)),
        ("EQ3 7-Band", "lpf_freq") => Some(("LPF Freq", "frq7", 35)),
        ("Dyn3 Compressor/Limiter", "makeup") => Some(("Gain", "sldG", 0)),
        ("Dyn3 Compressor/Limiter", "ratio") => Some(("Ratio", "sld2", 1)),
        ("Dyn3 Compressor/Limiter", "attack") => Some(("Attack", "sld1", 2)),
        ("Dyn3 Compressor/Limiter", "release") => Some(("Release", "sld3", 3)),
        ("Dyn3 Compressor/Limiter", "knee") => Some(("Knee", "sldD", 4)),
        ("Dyn3 Compressor/Limiter", "threshold") => Some(("Threshold", "sldC", 5)),
        ("Trim", "gain") => Some(("Gain", "gain", 0)),
        ("AutoPan", "output") => Some(("Output", "outg", 0)),
        ("AutoPan", "width") => Some(("Width", "wdth", 4)),
        ("AutoPan", "rate") => Some(("Rate", "temp", 8)),
        ("Time Adjuster", "delay_samples") => Some(("Delay", "dlyL", 6)),
        ("Channel Strip", "input_gain") => Some(("Input Trim", "Input Trim", 4)),
        ("Channel Strip", "output_gain") => Some(("Fader Volume", "Fader Volume", 5)),
        ("Channel Strip", "comp_on") => Some(("Cmp In/Out", "Cmp In/Out", 19)),
        ("Channel Strip", "comp_ratio") => Some(("Cmp Ratio", "Cmp Ratio", 20)),
        ("Channel Strip", "comp_attack") => Some(("Cmp Attack Time", "Cmp Attack Time", 22)),
        ("Channel Strip", "comp_release") => Some(("Cmp Release Time", "Cmp Release Time", 23)),
        ("Channel Strip", "comp_makeup") => Some(("Cmp Gain Makeup", "Cmp Gain Makeup", 24)),
        ("Channel Strip", "comp_threshold") => Some(("Cmp Threshold", "Cmp Threshold", 25)),
        ("Channel Strip", "gate_on") => Some(("Exp In/Out", "Exp In/Out", 27)),
        ("Channel Strip", "gate_release") => Some(("Exp Release Time", "Exp Release Time", 31)),
        ("Channel Strip", "gate_threshold") => Some(("Exp Threshold", "Exp Threshold", 32)),
        ("Channel Strip", "gate_range") => Some(("Exp Depth", "Exp Depth", 33)),
        ("Channel Strip", "eq_on") => Some(("EQ On/Off", "EQ On/Off", 8)),
        ("Channel Strip", "low_gain") => Some(("EQ Low Gain", "EQ Low Gain", 44)),
        ("Channel Strip", "low_freq") => Some(("EQ Low Frequency", "EQ Low Frequency", 45)),
        ("Channel Strip", "mid_gain") => Some(("EQ Low-Mid Gain", "EQ Low-Mid Gain", 49)),
        ("Channel Strip", "mid_freq") => Some(("EQ Low-Mid Frequency", "EQ Low-Mid Frequency", 50)),
        ("Channel Strip", "mid_q") => Some(("EQ Low-Mid Q", "EQ Low-Mid Q", 51)),
        ("Channel Strip", "high_gain") => Some(("EQ High Gain", "EQ High Gain", 60)),
        ("Channel Strip", "high_freq") => Some(("EQ High Frequency", "EQ High Frequency", 61)),
        ("Channel Strip", "hpf_on") => Some(("Filter 1 In/Out", "Filter 1 In/Out", 64)),
        ("Channel Strip", "hpf_freq") => Some(("Filter 1 Frequency", "Filter 1 Frequency", 66)),
        _ => None,
    }
}

fn trim_knots_norm_to_db(knots: &[[f64; 2]], u: f64, max_db: f64) -> f64 {
    if knots.is_empty() {
        return trim_norm_to_db(u, max_db);
    }
    let u = u.clamp(0.0, 1.0);
    if u <= knots[0][0] {
        return knots[0][1];
    }
    let last = knots[knots.len() - 1];
    if u >= last[0] {
        let span = (1.0 - last[0]).max(1e-9);
        return ((u - last[0]) / span) * max_db + last[1] * (1.0 - (u - last[0]) / span);
    }
    for w in knots.windows(2) {
        let (x0, y0) = (w[0][0], w[0][1]);
        let (x1, y1) = (w[1][0], w[1][1]);
        if u <= x1 {
            let t = if (x1 - x0).abs() < 1e-12 { 0.0 } else { (u - x0) / (x1 - x0) };
            return y0 + t * (y1 - y0);
        }
    }
    0.0
}

fn trim_knots_db_to_norm(knots: &[[f64; 2]], db: f64, max_db: f64) -> f64 {
    if knots.is_empty() {
        return trim_db_to_norm(db, max_db);
    }
    let min_db = knots[0][1];
    let last = knots[knots.len() - 1];
    if db <= min_db {
        return knots[0][0];
    }
    if db >= max_db {
        return 1.0;
    }
    if db >= last[1] {
        let span_db = (max_db - last[1]).max(1e-9);
        return last[0] + ((db - last[1]) / span_db) * (1.0 - last[0]);
    }
    for w in knots.windows(2) {
        let (x0, y0) = (w[0][0], w[0][1]);
        let (x1, y1) = (w[1][0], w[1][1]);
        if db <= y1 {
            let t = if (y1 - y0).abs() < 1e-12 { 0.0 } else { (db - y0) / (y1 - y0) };
            return (x0 + t * (x1 - x0)).clamp(0.0, 1.0);
        }
    }
    last[0]
}

/// Clamp physical parameter value to SoundCraft DSP's supported range for `(sc_plugin, sc_key)`.
fn clamp_sc_phys(sc_plugin: &str, sc_key: &str, val: f64) -> f64 {
    let (lo, hi) = match (sc_plugin, sc_key) {
        ("channel_strip", "input_gain" | "output_gain" | "low_gain" | "mid_gain" | "high_gain") => (-24.0, 24.0),
        ("channel_strip", "gate_range") => (0.0, 80.0),
        ("channel_strip", "comp_attack") => (0.01, 300.0),
        ("channel_strip", "comp_release") => (5.0, 3000.0),
        ("channel_strip", "comp_makeup") => (0.0, 40.0),
        ("channel_strip", "hpf_freq") => (10.0, 2000.0),
        ("channel_strip", "low_freq") => (20.0, 1000.0),
        ("channel_strip", "mid_freq") => (100.0, 8000.0),
        ("channel_strip", "mid_q") => (0.1, 10.0),
        ("channel_strip", "high_freq") => (1000.0, 20_000.0),
        ("eq_7band", "input_gain" | "output_gain" | "low_shelf_gain" | "low_mid_gain" | "mid_gain" | "high_mid_gain" | "high_shelf_gain") => (-24.0, 24.0),
        ("eq_7band", "hpf_freq" | "low_mid_freq") => (10.0, 2000.0),
        ("eq_7band", "low_shelf_freq") => (20.0, 1000.0),
        ("eq_7band", "mid_freq") => (100.0, 8000.0),
        ("eq_7band", "high_mid_freq") => (500.0, 20_000.0),
        ("eq_7band", "high_shelf_freq" | "lpf_freq") => (1000.0, 20_000.0),
        ("eq_7band", "low_shelf_q" | "high_shelf_q") => (0.3, 2.0),
        ("compressor", "knee") => (0.0, 24.0),
        ("compressor", "release") => (5.0, 3000.0),
        ("compressor", "makeup") => (0.0, 40.0),
        ("auto_pan", "rate") => (1.0, 960.0),
        _ => return val,
    };
    val.clamp(lo, hi)
}

/// Convert normalized PT automation `[0..1]` -> physical SoundCraft DSP value using `cfg`.
#[must_use]
pub fn pt_norm_to_phys_with(cfg: &PluginMapConfig, sc_plugin: &str, sc_key: &str, u: f64) -> f64 {
    let u = u.clamp(0.0, 1.0);
    if sc_plugin == "channel_strip" && sc_key == "gate_range" {
        return (1.0 - u) * 108.0;
    }
    let r = param_spec(cfg, sc_plugin, sc_key);
    if sc_plugin == "trim" && sc_key == "gain" {
        let max_db = r.map_or(12.0, |s| s.max);
        return trim_knots_norm_to_db(&cfg.trim_knots, u, max_db);
    }
    if let Some(spec) = r {
        if let Some(z) = spec.zero_db_norm
            && z > 0.0
            && z < 1.0
        {
            if u <= z {
                return spec.min + (u / z) * (-spec.min);
            }
            return ((u - z) / (1.0 - z)) * spec.max;
        }
        return match spec.taper {
            ParamTaper::Linear => spec.min + u * (spec.max - spec.min),
            ParamTaper::Log => norm_to_hz_log(u, spec.min, spec.max),
            ParamTaper::Toggle => {
                if u >= 0.5 { 1.0 } else { 0.0 }
            }
        };
    }
    if sc_plugin == "eq_7band" && (sc_key == "input_gain" || sc_key == "output_gain") {
        if u <= 0.769_231 {
            return -20.0 + (u / 0.769_231) * 20.0;
        }
        return ((u - 0.769_231) / (1.0 - 0.769_231)) * 6.0;
    }
    u
}

/// Inverse: convert physical SoundCraft value -> normalized `[0..1]` PT automation value using `cfg`.
#[must_use]
pub fn sc_phys_to_pt_norm_with(cfg: &PluginMapConfig, sc_plugin: &str, sc_key: &str, phys: f64) -> f64 {
    if sc_plugin == "channel_strip" && sc_key == "gate_range" {
        return (1.0 - (phys.clamp(0.0, 108.0) / 108.0)).clamp(0.0, 1.0);
    }
    let r = param_spec(cfg, sc_plugin, sc_key);
    if sc_plugin == "trim" && sc_key == "gain" {
        let max_db = r.map_or(12.0, |s| s.max);
        return trim_knots_db_to_norm(&cfg.trim_knots, phys, max_db);
    }
    if let Some(spec) = r {
        if let Some(z) = spec.zero_db_norm
            && z > 0.0
            && z < 1.0
        {
            let clamped = phys.clamp(spec.min, spec.max);
            if clamped <= 0.0 {
                return ((clamped - spec.min) / (-spec.min)) * z;
            }
            return z + (clamped / spec.max) * (1.0 - z);
        }
        return match spec.taper {
            ParamTaper::Linear => {
                if (spec.max - spec.min).abs() < 1e-12 {
                    0.0
                } else {
                    ((phys - spec.min) / (spec.max - spec.min)).clamp(0.0, 1.0)
                }
            }
            ParamTaper::Log => hz_log_norm(phys, spec.min, spec.max),
            ParamTaper::Toggle => {
                if phys >= 0.5 { 1.0 } else { 0.0 }
            }
        };
    }
    if sc_plugin == "eq_7band" && (sc_key == "input_gain" || sc_key == "output_gain") {
        let clamped = phys.clamp(-18.0, 6.0);
        if clamped <= 0.0 {
            return ((clamped + 18.0) / 18.0) * 0.769_231;
        }
        return 0.769_231 + (clamped / 6.0) * (1.0 - 0.769_231);
    }
    phys.clamp(0.0, 1.0)
}

/// Convert normalized PT automation `[0..1]` -> physical SoundCraft DSP value using embedded defaults.
#[must_use]
pub fn pt_norm_to_phys(sc_plugin: &str, sc_key: &str, u: f64) -> f64 {
    pt_norm_to_phys_with(default_config(), sc_plugin, sc_key, u)
}

/// Inverse: convert physical SoundCraft value -> normalized `[0..1]` PT automation value using embedded defaults.
#[must_use]
pub fn sc_phys_to_pt_norm(sc_plugin: &str, sc_key: &str, phys: f64) -> f64 {
    sc_phys_to_pt_norm_with(default_config(), sc_plugin, sc_key, phys)
}

struct LogSubdivCtx<'a> {
    cfg: &'a PluginMapConfig,
    sc_plugin: &'a str,
    sc_key: &'a str,
}

/// Recursive `PTX -> SC` subdivision so piecewise-linear physical segments track log ramps (`<= 0.5%`).
fn subdivide_ptx_log_segment(
    ctx: &LogSubdivCtx<'_>,
    p0: (Samples, f64),
    p1: (Samples, f64),
    depth: u8,
    out: &mut Vec<(Samples, f64)>,
) {
    let (t0, u0) = p0;
    let (t1, u1) = p1;
    if depth < LOG_SUBDIV_MAX_DEPTH && t1 > t0 + 1 && (u1 - u0).abs() > 1e-6 {
        let f0 = pt_norm_to_phys_with(ctx.cfg, ctx.sc_plugin, ctx.sc_key, u0);
        let f1 = pt_norm_to_phys_with(ctx.cfg, ctx.sc_plugin, ctx.sc_key, u1);
        let u_mid = 0.5 * (u0 + u1);
        let f_true = pt_norm_to_phys_with(ctx.cfg, ctx.sc_plugin, ctx.sc_key, u_mid);
        let f_lin = 0.5 * (f0 + f1);
        let err = (f_lin - f_true).abs();
        if err > LOG_SUBDIV_REL_TOL * f_true.abs().max(1e-4) {
            let t_mid = t0 + (t1 - t0) / 2;
            subdivide_ptx_log_segment(ctx, (t0, u0), (t_mid, u_mid), depth + 1, out);
            out.push((t_mid, f_true));
            subdivide_ptx_log_segment(ctx, (t_mid, u_mid), (t1, u1), depth + 1, out);
        }
    }
}

/// Recursive `SC -> PTX` subdivision so piecewise-linear normalized PT ramps track linear-Hz SC ramps (`<= 0.5%`).
fn subdivide_sc_log_segment(
    ctx: &LogSubdivCtx<'_>,
    p0: (u64, f64),
    p1: (u64, f64),
    depth: u8,
    out: &mut Vec<(u64, f64)>,
) {
    let (t0, f0) = p0;
    let (t1, f1) = p1;
    if depth < LOG_SUBDIV_MAX_DEPTH && t1 > t0 + 1 && (f1 - f0).abs() > 1e-6 {
        let u0 = sc_phys_to_pt_norm_with(ctx.cfg, ctx.sc_plugin, ctx.sc_key, f0);
        let u1 = sc_phys_to_pt_norm_with(ctx.cfg, ctx.sc_plugin, ctx.sc_key, f1);
        let f_mid = 0.5 * (f0 + f1);
        let u_mid = sc_phys_to_pt_norm_with(ctx.cfg, ctx.sc_plugin, ctx.sc_key, f_mid);
        let f_pt_lin = pt_norm_to_phys_with(ctx.cfg, ctx.sc_plugin, ctx.sc_key, 0.5 * (u0 + u1));
        let err = (f_pt_lin - f_mid).abs();
        if err > LOG_SUBDIV_REL_TOL * f_mid.abs().max(1e-4) {
            let t_mid = t0 + (t1 - t0) / 2;
            subdivide_sc_log_segment(ctx, (t0, f0), (t_mid, f_mid), depth + 1, out);
            out.push((t_mid, u_mid));
            subdivide_sc_log_segment(ctx, (t_mid, f_mid), (t1, f1), depth + 1, out);
        }
    }
}

/// Inputs to [`ptx_insert_to_sc`].
pub struct PtxInsertToScArgs<'a> {
    pub slot_idx: u8,
    pub ins: &'a PtxInsert,
    pub track_name: &'a str,
    pub track_is_ticks: bool,
    pub tempo: &'a TempoMap,
    pub sr: SampleRate,
    pub plugin_cfg: &'a PluginMapConfig,
}

fn eq7_band_enable_index(p_id: &str, p_name: &str) -> Option<usize> {
    let p = p_id.trim().to_ascii_lowercase();
    let n = p_name.trim().to_ascii_lowercase();
    match p.as_str() {
        "in 2" | "l_in 2" | "in2" => return Some(2),
        "in 3" | "l_in 3" | "in3" => return Some(3),
        "in 4" | "l_in 4" | "in4" => return Some(4),
        "in 5" | "l_in 5" | "in5" => return Some(5),
        "in 6" | "l_in 6" | "in6" => return Some(6),
        _ => {}
    }
    match n.as_str() {
        "lf in" => Some(2),
        "lmf in" => Some(3),
        "mf in" => Some(4),
        "hmf in" => Some(5),
        "hf in" => Some(6),
        _ => None,
    }
}

fn eval_step_bool(pts: &[(Samples, bool)], default: bool, t: Samples) -> bool {
    let mut cur = default;
    for &(pt_t, b) in pts {
        if pt_t <= t {
            cur = b;
        } else {
            break;
        }
    }
    cur
}

fn eval_linear_f64(pts: &[(Samples, f64)], default: f64, t: Samples) -> f64 {
    if pts.is_empty() {
        return default;
    }
    if t <= pts[0].0 {
        return pts[0].1;
    }
    for w in pts.windows(2) {
        let (t0, v0) = w[0];
        let (t1, v1) = w[1];
        if t <= t1 {
            if t1 == t0 {
                return v1;
            }
            let alpha = (t - t0) as f64 / (t1 - t0) as f64;
            return v0 + alpha * (v1 - v0);
        }
    }
    pts[pts.len() - 1].1
}

/// Convert a Pro Tools [`PtxInsert`] into a SoundCraft [`ScInsert`] + automation lanes + optional [`CarryInsert`].
pub fn ptx_insert_to_sc(
    args: &PtxInsertToScArgs<'_>,
    report: &mut ConversionReport,
) -> (Option<ScInsert>, Vec<AutomationLane>, Option<CarryInsert>) {
    let slot_idx = args.slot_idx;
    let ins = args.ins;
    let track_name = args.track_name;
    let track_is_ticks = args.track_is_ticks;
    let tempo = args.tempo;
    let sr = args.sr;
    let plugin_cfg = args.plugin_cfg;
    let pt_name = resolve_ptx_plugin_name(ins);
    let active = ins.active.unwrap_or(true);
    let mut bypass = ins.bypass.unwrap_or(false);
    let mut sc_params = BTreeMap::new();
    let mut approx_notes: Vec<&str> = Vec::new();
    let mut carry_needed = false;

    let sc_id: Option<&'static str> = match pt_name.as_str() {
        "EQ3 1-Band" => {
            if let Some(t) = json_i64(&ins.params, "l_type") {
                set_param(&mut sc_params, "type", eq1_pt_type_to_sc(t), 0.0, 6.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_ctrf") {
                set_param(&mut sc_params, "freq", v, 20.0, 20_000.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_gain") {
                set_param(&mut sc_params, "gain", v, -24.0, 24.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_bndw") {
                set_param(&mut sc_params, "q", v, 0.1, 10.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_trim") {
                set_param(&mut sc_params, "output_gain", v, -24.0, 24.0);
            }
            if json_i64(&ins.params, "l_slop").is_some_and(|s| s != 1)
                || json_i64(&ins.params, "l_Phse").is_some_and(|p| p != 0)
            {
                approx_notes.push("slope/phase options carried");
                carry_needed = true;
            }
            Some("eq_1band")
        }
        "EQ3 7-Band" => {
            if let Some(v) = json_f64(&ins.params, "d_inpt") {
                set_param(&mut sc_params, "input_gain", v, -24.0, 24.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_outp") {
                set_param(&mut sc_params, "output_gain", v, -24.0, 24.0);
            }
            if let Some(v) = json_i64(&ins.params, "l_in 1") {
                set_param(&mut sc_params, "hpf_on", if v != 0 { 1.0 } else { 0.0 }, 0.0, 1.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_frq1") {
                set_param(&mut sc_params, "hpf_freq", v, 10.0, 2000.0);
            }
            if let Some(v) = json_i64(&ins.params, "l_hpfs") {
                set_param(&mut sc_params, "hpf_slope", v as f64, 0.0, 3.0);
            }
            for (pt_idx, prefix, fmin, fmax, qmin, qmax) in [
                (2, "low_shelf", 20.0, 1000.0, 0.3, 2.0),
                (3, "low_mid", 20.0, 2000.0, 0.1, 10.0),
                (4, "mid", 100.0, 8000.0, 0.1, 10.0),
                (5, "high_mid", 500.0, 20_000.0, 0.1, 10.0),
                (6, "high_shelf", 1000.0, 20_000.0, 0.3, 2.0),
            ] {
                let enabled = json_i64(&ins.params, &format!("l_in {pt_idx}")).unwrap_or(1) != 0;
                if let Some(f) = json_f64(&ins.params, &format!("d_frq{pt_idx}")) {
                    set_param(&mut sc_params, &format!("{prefix}_freq"), f, fmin, fmax);
                }
                let raw_gain = json_f64(&ins.params, &format!("d_gai{pt_idx}")).unwrap_or(0.0);
                set_param(
                    &mut sc_params,
                    &format!("{prefix}_gain"),
                    if enabled { raw_gain } else { 0.0 },
                    -24.0,
                    24.0,
                );
                if let Some(q) = json_f64(&ins.params, &format!("d_bnd{pt_idx}")) {
                    set_param(&mut sc_params, &format!("{prefix}_q"), q, qmin, qmax);
                }
            }
            if let Some(v) = json_i64(&ins.params, "l_in 7") {
                set_param(&mut sc_params, "lpf_on", if v != 0 { 1.0 } else { 0.0 }, 0.0, 1.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_frq7") {
                set_param(&mut sc_params, "lpf_freq", v, 1000.0, 20_000.0);
            }
            if let Some(v) = json_i64(&ins.params, "l_lpfs") {
                set_param(&mut sc_params, "lpf_slope", v as f64, 0.0, 3.0);
            }
            carry_needed = true;
            Some("eq_7band")
        }
        "Dyn3 Compressor/Limiter" => {
            if let Some(v) = json_f64(&ins.params, "d_sldC") {
                set_param(&mut sc_params, "threshold", v, -60.0, 0.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_sld2") {
                set_param(&mut sc_params, "ratio", v, 1.0, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_sld1") {
                set_param(&mut sc_params, "attack", v * 1000.0, 0.01, 300.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_sld3") {
                set_param(&mut sc_params, "release", v * 1000.0, 5.0, 3000.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_sldD") {
                set_param(&mut sc_params, "knee", v, 0.0, 24.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_sldG") {
                set_param(&mut sc_params, "makeup", v, 0.0, 40.0);
            }
            if let Some(v) = json_i64(&ins.params, "l_LoFE") {
                set_param(&mut sc_params, "sc_hpf_on", if v != 0 { 1.0 } else { 0.0 }, 0.0, 1.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_LoFF") {
                set_param(&mut sc_params, "sc_hpf_freq", v, 20.0, 500.0);
            }
            approx_notes.push("dyn3 curve/sidechain differences");
            carry_needed = true;
            Some("compressor")
        }
        "Channel Strip" => {
            if let Some(v) = json_f64(&ins.params, "d_Input Trim") {
                set_param(&mut sc_params, "input_gain", v, -24.0, 24.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Fader Volume") {
                set_param(&mut sc_params, "output_gain", v, -24.0, 24.0);
            }
            if let Some(v) = json_i64(&ins.params, "l_Cmp In/Out") {
                set_param(&mut sc_params, "comp_on", if v != 0 { 1.0 } else { 0.0 }, 0.0, 1.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Cmp Threshold") {
                set_param(&mut sc_params, "comp_threshold", v, -60.0, 0.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Cmp Ratio") {
                set_param(&mut sc_params, "comp_ratio", v, 1.0, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Cmp Attack Time") {
                set_param(&mut sc_params, "comp_attack", v * 1000.0, 0.01, 300.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Cmp Release Time") {
                set_param(&mut sc_params, "comp_release", v * 1000.0, 5.0, 3000.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Cmp Gain Makeup") {
                set_param(&mut sc_params, "comp_makeup", v, 0.0, 40.0);
            }
            if let Some(v) = json_i64(&ins.params, "l_Exp In/Out") {
                set_param(&mut sc_params, "gate_on", if v != 0 { 1.0 } else { 0.0 }, 0.0, 1.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Exp Threshold") {
                set_param(&mut sc_params, "gate_threshold", v, -80.0, 0.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Exp Depth") {
                set_param(&mut sc_params, "gate_range", v.abs(), 0.0, 80.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Exp Release Time") {
                set_param(&mut sc_params, "gate_release", v * 1000.0, 1.0, 4000.0);
            }
            if let Some(v) = json_i64(&ins.params, "l_EQ On/Off") {
                set_param(&mut sc_params, "eq_on", if v != 0 { 1.0 } else { 0.0 }, 0.0, 1.0);
            }
            if let Some(v) = json_i64(&ins.params, "l_Filter 1 In/Out") {
                set_param(&mut sc_params, "hpf_on", if v != 0 { 1.0 } else { 0.0 }, 0.0, 1.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Filter 1 Frequency") {
                set_param(&mut sc_params, "hpf_freq", v, 10.0, 2000.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_EQ Low Gain") {
                set_param(&mut sc_params, "low_gain", v, -24.0, 24.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_EQ Low Frequency") {
                set_param(&mut sc_params, "low_freq", v, 20.0, 1000.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_EQ Low-Mid Gain") {
                set_param(&mut sc_params, "mid_gain", v, -24.0, 24.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_EQ Low-Mid Frequency") {
                set_param(&mut sc_params, "mid_freq", v, 100.0, 8000.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_EQ Low-Mid Q") {
                set_param(&mut sc_params, "mid_q", v, 0.1, 10.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_EQ High Gain") {
                set_param(&mut sc_params, "high_gain", v, -24.0, 24.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_EQ High Frequency") {
                set_param(&mut sc_params, "high_freq", v, 1000.0, 20_000.0);
            }
            approx_notes.push("4-band/Fader/Filter2 carried");
            carry_needed = true;
            Some("channel_strip")
        }
        "AutoPan" => {
            if let Some(v) = json_f64(&ins.params, "d_outg") {
                set_param(&mut sc_params, "output", v, -24.0, 12.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_wdth") {
                set_param(&mut sc_params, "width", v, 0.0, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_posi") {
                set_param(&mut sc_params, "manual", v, -100.0, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_temp") {
                set_param(&mut sc_params, "rate", v, 1.0, 960.0);
            }
            if let Some(v) = json_i64(&ins.params, "l_wave") {
                set_param(&mut sc_params, "waveform", v as f64, 0.0, 6.0);
            }
            if let Some(v) = json_i64(&ins.params, "l_dirn") {
                set_param(&mut sc_params, "path", v as f64, 0.0, 1.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_thrs") {
                set_param(&mut sc_params, "threshold", v, -60.0, -1.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_attk") {
                set_param(&mut sc_params, "attack", v, 0.1, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_rels") {
                set_param(&mut sc_params, "release", v, 5.0, 2000.0);
            }
            Some("auto_pan")
        }
        "Trim" => {
            if let Some(g) = json_f64(&ins.params, "gain_db") {
                set_param(&mut sc_params, "gain", g, -144.0, 12.0);
            } else if let Some(n) = json_f64(&ins.params, "gain_norm") {
                let rng = json_f64(&ins.params, "gain_range_db").unwrap_or(12.0);
                set_param(&mut sc_params, "gain", trim_norm_to_db(n, rng), -144.0, 12.0);
            }
            if let Some(b) = ins.params.get("phase_invert").and_then(|v| v.as_bool()) {
                set_param(&mut sc_params, "invert", if b { 1.0 } else { 0.0 }, 0.0, 1.0);
            }
            Some("trim")
        }
        "Time Adjuster" => {
            if let Some(d) = json_f64(&ins.params, "delay_samples") {
                set_param(&mut sc_params, "delay_samples", d, 0.0, 48_000.0);
            }
            carry_needed = true;
            Some("time_shift")
        }
        "D-Verb" => {
            if let Some(v) = json_f64(&ins.params, "mix") {
                set_param(&mut sc_params, "mix", v * 100.0, 0.0, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "diffusion") {
                set_param(&mut sc_params, "diffusion", v * 100.0, 0.0, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "size_norm") {
                set_param(&mut sc_params, "size", v * 100.0, 0.0, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "decay_norm") {
                set_param(&mut sc_params, "decay", norm_to_hz_log(v, 0.1, 20.0), 0.1, 20.0);
            }
            if let Some(v) = json_f64(&ins.params, "pre_delay_norm") {
                set_param(&mut sc_params, "pre_delay", v * 250.0, 0.0, 250.0);
            }
            approx_notes.push("D-Verb mapped to Room Reverb");
            carry_needed = true;
            let is_plate = json_f64(&ins.params, "algorithm_norm").is_some_and(|a| a > 0.4 && a < 0.7);
            Some(if is_plate { "plate_reverb" } else { "room_reverb" })
        }
        "Mod Delay III" => {
            if let Some(v) = json_f64(&ins.params, "delay_ms_l").or_else(|| json_f64(&ins.params, "delay_ms")) {
                set_param(&mut sc_params, "time", v, 1.0, 2000.0);
            }
            if let Some(v) = json_f64(&ins.params, "feedback_l").or_else(|| json_f64(&ins.params, "feedback")) {
                set_param(&mut sc_params, "feedback", v * 100.0, -99.0, 99.0);
            }
            if let Some(v) = json_f64(&ins.params, "mix_l").or_else(|| json_f64(&ins.params, "mix")) {
                set_param(&mut sc_params, "mix", v * 100.0, 0.0, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "depth_l").or_else(|| json_f64(&ins.params, "depth")) {
                set_param(&mut sc_params, "mod_depth", v * 100.0, 0.0, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "lpf_hz_l").or_else(|| json_f64(&ins.params, "lpf_hz")) {
                set_param(&mut sc_params, "lpf", v, 500.0, 20_000.0);
            }
            approx_notes.push("Mod Delay III L/R collapsed to linked mod_delay");
            carry_needed = true;
            Some("mod_delay")
        }
        "Lo-Fi" => {
            if let Some(v) = json_f64(&ins.params, "noise_norm") {
                set_param(&mut sc_params, "noise", v * 100.0, 0.0, 100.0);
            }
            approx_notes.push("Lo-Fi drive/saturation carried");
            carry_needed = true;
            Some("lofi")
        }
        "BF-76" => {
            approx_notes.push("BF-76 FET compressor approximated as compressor");
            carry_needed = true;
            Some("compressor")
        }
        "Dyn3 Expander/Gate" => {
            if let Some(v) = json_f64(&ins.params, "d_sldC") {
                set_param(&mut sc_params, "threshold", v, -80.0, 0.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_sld2") {
                set_param(&mut sc_params, "ratio", v, 1.0, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_sld4") {
                set_param(&mut sc_params, "range", v.abs(), 0.0, 80.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_sld1") {
                set_param(&mut sc_params, "attack", v * 1000.0, 0.01, 100.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_sldH") {
                set_param(&mut sc_params, "hold", v * 1000.0, 0.0, 2000.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_sld3") {
                set_param(&mut sc_params, "release", v * 1000.0, 1.0, 4000.0);
            }
            approx_notes.push("dyn3 expander sidechain/lookahead differences");
            carry_needed = true;
            Some("expander_gate")
        }
        "Dyn3 De-Esser" => {
            if let Some(v) = json_f64(&ins.params, "d_Freq") {
                set_param(&mut sc_params, "freq", v, 2000.0, 16_000.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Rang") {
                set_param(&mut sc_params, "range", v.abs(), 0.0, 40.0);
            }
            carry_needed = true;
            Some("de_esser")
        }
        "Maxim" => {
            if let Some(v) = json_f64(&ins.params, "d_Thrs") {
                set_param(&mut sc_params, "threshold", v, -30.0, 0.0);
            }
            if let Some(v) = json_f64(&ins.params, "d_Ceil") {
                set_param(&mut sc_params, "ceiling", v, -30.0, 0.0);
            }
            carry_needed = true;
            Some("maximizer")
        }
        "SansAmp PSA-1" => {
            approx_notes.push("SansAmp PSA-1 approximated as saturator");
            carry_needed = true;
            Some("saturator")
        }
        "Sci-Fi" => {
            approx_notes.push("Sci-Fi approximated as ring_mod");
            carry_needed = true;
            Some("ring_mod")
        }
        "Pitch II" => {
            if let Some(v) = json_f64(&ins.params, "mix_l").or_else(|| json_f64(&ins.params, "mix")) {
                set_param(&mut sc_params, "mix", v * 100.0, 0.0, 100.0);
            }
            approx_notes.push("Pitch II pitch settings carried");
            carry_needed = true;
            Some("pitch_shifter")
        }
        "Dither" | "POW-r Dither" => {
            carry_needed = true;
            Some("dither")
        }
        _ => {
            carry_needed = true;
            None
        }
    };

    let mut auto_lanes = Vec::new();
    let sc_id_str = sc_id.unwrap_or(pt_name.as_str());
    let to_samples = |raw_t: u64| -> Samples {
        let clean = plain_ticks(raw_t);
        if track_is_ticks {
            ptx_ticks_to_samples(clean, tempo, sr)
        } else {
            i64::try_from(clean).unwrap_or(i64::MAX)
        }
    };

    // Compose dynamic `EQ3 7-Band` `l_in 2..6` enable switches into effective `*_gain` lanes.
    let mut eq7_handled_gains: [bool; 5] = [false; 5];
    if sc_id_str == "eq_7band" {
        const BANDS: [(usize, &str, &str); 5] = [
            (2, "low_shelf_gain", "d_gai2"),
            (3, "low_mid_gain", "d_gai3"),
            (4, "mid_gain", "d_gai4"),
            (5, "high_mid_gain", "d_gai5"),
            (6, "high_shelf_gain", "d_gai6"),
        ];
        for (slot_b, &(band_idx, gain_key, pt_gain_param)) in BANDS.iter().enumerate() {
            let mut en_pts: Vec<(Samples, bool)> = Vec::new();
            let mut gain_pts: Vec<(Samples, f64)> = Vec::new();
            for (idx, pts) in ins.automation.iter().enumerate() {
                let meta = ins.automation_params.as_ref().and_then(|v| v.get(idx));
                let p_name = meta.and_then(|m| m[0].as_deref()).unwrap_or("");
                let p_id = meta.and_then(|m| m[1].as_deref()).unwrap_or("");
                if eq7_band_enable_index(p_id, p_name) == Some(band_idx) {
                    for &(raw_t, norm_u) in pts {
                        en_pts.push((to_samples(raw_t), norm_u >= 0.5));
                    }
                } else if map_ptx_auto_param_key("eq_7band", p_name, p_id) == Some(gain_key) {
                    for &(raw_t, norm_u) in pts {
                        gain_pts.push((
                            to_samples(raw_t),
                            pt_norm_to_phys_with(plugin_cfg, "eq_7band", gain_key, norm_u),
                        ));
                    }
                }
            }
            if !en_pts.is_empty() {
                en_pts.sort_by_key(|p| p.0);
                gain_pts.sort_by_key(|p| p.0);
                let static_en = json_i64(&ins.params, &format!("l_in {band_idx}")).unwrap_or(1) != 0;
                let static_gain = json_f64(&ins.params, pt_gain_param).unwrap_or(0.0);
                let mut times: Vec<Samples> = en_pts.iter().map(|p| p.0).collect();
                times.extend(gain_pts.iter().map(|p| p.0));
                // Insert a 1-sample pre-step guard before boolean toggle edges so gain steps cleanly.
                let mut prev = static_en;
                for &(t, cur) in &en_pts {
                    if cur != prev && t > 0 {
                        times.push(t - 1);
                    }
                    prev = cur;
                }
                times.sort_unstable();
                times.dedup();
                let mut lane = AutomationLane::new(AutoParam::Plugin {
                    slot: slot_idx,
                    param: gain_key.to_owned(),
                });
                for t in times {
                    let g = if eval_step_bool(&en_pts, static_en, t) {
                        eval_linear_f64(&gain_pts, static_gain, t)
                    } else {
                        0.0
                    };
                    lane.set_point(t, g as f32);
                }
                auto_lanes.push(lane);
                eq7_handled_gains[slot_b] = true;
                approx_notes.push("EQ3 7-Band dynamic band enable composed into gain");
            } else if !gain_pts.is_empty() {
                let static_en = json_i64(&ins.params, &format!("l_in {band_idx}")).unwrap_or(1) != 0;
                if !static_en {
                    gain_pts.sort_by_key(|p| p.0);
                    let mut lane = AutomationLane::new(AutoParam::Plugin {
                        slot: slot_idx,
                        param: gain_key.to_owned(),
                    });
                    for (t, _) in gain_pts {
                        lane.set_point(t, 0.0);
                    }
                    auto_lanes.push(lane);
                    eq7_handled_gains[slot_b] = true;
                }
            }
        }
    }

    for (idx, pts) in ins.automation.iter().enumerate() {
        let meta = ins.automation_params.as_ref().and_then(|v| v.get(idx));
        let p_name = meta.and_then(|m| m[0].as_deref()).unwrap_or("");
        let p_id = meta.and_then(|m| m[1].as_deref()).unwrap_or("");
        if p_id.eq_ignore_ascii_case("masterbypassid") || p_name.eq_ignore_ascii_case("master bypass") {
            if !pts.is_empty() {
                let mut sorted_mb: Vec<(Samples, bool)> = pts
                    .iter()
                    .map(|&(raw_t, norm_u)| (to_samples(raw_t), norm_u >= 0.5))
                    .collect();
                sorted_mb.sort_by_key(|p| p.0);
                let init_byp = sorted_mb[0].1;
                bypass = init_byp;
                if sorted_mb.iter().any(|&(_, b)| b != init_byp) {
                    approx_notes.push("dynamic Master Bypass automation approximated by initial t=0 state");
                    carry_needed = true;
                }
            }
            continue;
        }
        if sc_id_str == "eq_7band"
            && eq7_band_enable_index(p_id, p_name).is_some()
        {
            continue;
        }
        if let Some(sc_key) = map_ptx_auto_param_key(sc_id_str, p_name, p_id) {
            if sc_id_str == "eq_7band"
                && matches!(
                    (sc_key, eq7_handled_gains),
                    ("low_shelf_gain", [true, ..])
                        | ("low_mid_gain", [_, true, ..])
                        | ("mid_gain", [_, _, true, ..])
                        | ("high_mid_gain", [_, _, _, true, ..])
                        | ("high_shelf_gain", [.., true])
                )
            {
                continue;
            }
            let is_log = param_spec(plugin_cfg, sc_id_str, sc_key)
                .is_some_and(|s| s.taper == ParamTaper::Log);
            let mut lane = AutomationLane::new(AutoParam::Plugin {
                slot: slot_idx,
                param: sc_key.to_owned(),
            });
            let mut sorted_pts: Vec<(Samples, f64)> = pts
                .iter()
                .map(|&(raw_t, norm_u)| (to_samples(raw_t), norm_u))
                .collect();
            sorted_pts.sort_by_key(|p| p.0);
            if is_log && sorted_pts.len() >= 2 {
                let ctx = LogSubdivCtx {
                    cfg: plugin_cfg,
                    sc_plugin: sc_id_str,
                    sc_key,
                };
                let mut dense: Vec<(Samples, f64)> = Vec::new();
                for (i, w) in sorted_pts.windows(2).enumerate() {
                    let (t0, u0) = w[0];
                    let (t1, u1) = w[1];
                    if i == 0 {
                        dense.push((t0, pt_norm_to_phys_with(plugin_cfg, sc_id_str, sc_key, u0)));
                    }
                    subdivide_ptx_log_segment(&ctx, (t0, u0), (t1, u1), 0, &mut dense);
                    dense.push((t1, pt_norm_to_phys_with(plugin_cfg, sc_id_str, sc_key, u1)));
                }
                for (at, phys) in dense {
                    lane.set_point(at, clamp_sc_phys(sc_id_str, sc_key, phys) as f32);
                }
            } else {
                for (at, norm_u) in sorted_pts {
                    let phys = pt_norm_to_phys_with(plugin_cfg, sc_id_str, sc_key, norm_u);
                    lane.set_point(at, clamp_sc_phys(sc_id_str, sc_key, phys) as f32);
                }
            }
            if let Some(first_pt) = lane.points.first() {
                sc_params.insert(sc_key.to_owned(), first_pt.value);
            }
            auto_lanes.push(lane);
        } else if !pts.is_empty() {
            report.record(
                "plugin_automation",
                format!("{track_name}:slot{slot_idx}:{pt_name}:{p_name}"),
                Fidelity::Carry,
                Some("unmapped PT plugin automation parameter".to_owned()),
            );
        }
    }

    let fidelity = match (sc_id, approx_notes.is_empty()) {
        (Some(_), true) => Fidelity::Native,
        (Some(_), false) => Fidelity::Approx,
        (None, _) => Fidelity::Carry,
    };
    let note = if approx_notes.is_empty() && sc_id.is_some() {
        None
    } else if !approx_notes.is_empty() {
        Some(approx_notes.join("; "))
    } else {
        Some("opaque or unmapped AAX plugin preserved in carry sidecar".to_owned())
    };
    report.record(
        "plugins",
        format!("{track_name}:slot{slot_idx}:{pt_name}"),
        fidelity,
        note,
    );

    let carry = if carry_needed || sc_id.is_none() {
        Some(CarryInsert {
            slot_index: usize::from(slot_idx),
            plugin_name: pt_name,
            vendor_id: ins.vendor_id.clone(),
            bypass,
            active,
            multi_mono: ins.multi_mono,
            params: ins.params.clone(),
            values_i32: ins.values_i32.clone(),
            settings_file: ins.settings_file.clone(),
            preset: ins.preset.clone(),
        })
    } else {
        None
    };

    let sc_insert = sc_id.map(|id| ScInsert {
        plugin: id.to_owned(),
        params: sc_params,
        bypass,
        active,
        preset: ins.preset.clone().unwrap_or_default(),
        state: None,
        sample: None,
    });

    (sc_insert, auto_lanes, carry)
}

/// Inputs to [`sc_insert_to_ptx`].
pub struct ScInsertToPtxArgs<'a> {
    pub slot_idx: usize,
    pub ins: &'a ScInsert,
    pub track_name: &'a str,
    pub track_auto: &'a [AutomationLane],
    pub tempo: &'a TempoMap,
    pub sr: SampleRate,
    pub to_ticks: bool,
    pub carry_opt: Option<&'a CarryInsert>,
    pub plugin_cfg: &'a PluginMapConfig,
}

/// Convert a SoundCraft [`ScInsert`] (+ automation lanes) back to [`BuildInsert`].
#[must_use]
pub fn sc_insert_to_ptx(
    args: &ScInsertToPtxArgs<'_>,
    report: &mut ConversionReport,
) -> Option<BuildInsert> {
    let slot_idx = args.slot_idx;
    let ins = args.ins;
    let track_name = args.track_name;
    let track_auto = args.track_auto;
    let tempo = args.tempo;
    let sr = args.sr;
    let to_ticks = args.to_ticks;
    let carry_opt = args.carry_opt;
    let plugin_cfg = args.plugin_cfg;
    let mut pt_params = BTreeMap::new();
    let sc_id = ins.plugin.as_str();

    // Seed exact carried PT params first if same logical plugin, then overlay SC edits.
    let pt_name = if let Some(c) = carry_opt {
        for (k, v) in &c.params {
            if let Some(b) = v.as_bool() {
                pt_params.insert(k.clone(), BuildParamVal::Bool(b));
            } else if let Some(i) = v.as_i64() {
                pt_params.insert(k.clone(), BuildParamVal::Int(i as i32));
            } else if let Some(f) = v.as_f64() {
                pt_params.insert(k.clone(), BuildParamVal::Float(f));
            }
        }
        c.plugin_name.clone()
    } else {
        match sc_id {
            "eq_1band" => "EQ3 1-Band".to_owned(),
            "eq_7band" => "EQ3 7-Band".to_owned(),
            "channel_strip" => "Channel Strip".to_owned(),
            "compressor" => "Dyn3 Compressor/Limiter".to_owned(),
            "auto_pan" => "AutoPan".to_owned(),
            "trim" => "Trim".to_owned(),
            "time_shift" => "Time Adjuster".to_owned(),
            "room_reverb" | "plate_reverb" => "D-Verb".to_owned(),
            "mod_delay" => "Mod Delay III".to_owned(),
            "lofi" => "Lo-Fi".to_owned(),
            "saturator" => "SansAmp PSA-1".to_owned(),
            "ring_mod" => "Sci-Fi".to_owned(),
            "pitch_shifter" => "Pitch II".to_owned(),
            "dither" => "Dither".to_owned(),
            other => {
                report.record(
                    "plugins",
                    format!("{track_name}:slot{slot_idx}:{other}"),
                    Fidelity::Absent,
                    Some("SoundCraft-only plugin has no Pro Tools Intro equivalent".to_owned()),
                );
                return None;
            }
        }
    };

    if lookup_stock_plugin(&pt_name).is_none() {
        report.record(
            "plugins",
            format!("{track_name}:slot{slot_idx}:{pt_name}"),
            Fidelity::Carry,
            Some("3rd-party AAX plugin cannot be cleanly encoded from scratch; omitted".to_owned()),
        );
        return None;
    }

    match pt_name.as_str() {
        "EQ3 1-Band" => {
            if let Some(&v) = ins.params.get("type") {
                pt_params.insert("l_type".to_owned(), BuildParamVal::Int(eq1_sc_type_to_pt(f64::from(v))));
            }
            if let Some(&v) = ins.params.get("freq") {
                pt_params.insert("d_ctrf".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("gain") {
                pt_params.insert("d_gain".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("q") {
                pt_params.insert("d_bndw".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("output_gain") {
                pt_params.insert("d_trim".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            report.record("plugins", format!("{track_name}:slot{slot_idx}:EQ3 1-Band"), Fidelity::Native, None);
        }
        "EQ3 7-Band" => {
            let pairs = [
                ("input_gain", "d_inpt"), ("output_gain", "d_outp"),
                ("hpf_freq", "d_frq1"), ("low_shelf_gain", "d_gai2"), ("low_shelf_freq", "d_frq2"), ("low_shelf_q", "d_bnd2"),
                ("low_mid_gain", "d_gai3"), ("low_mid_freq", "d_frq3"), ("low_mid_q", "d_bnd3"),
                ("mid_gain", "d_gai4"), ("mid_freq", "d_frq4"), ("mid_q", "d_bnd4"),
                ("high_mid_gain", "d_gai5"), ("high_mid_freq", "d_frq5"), ("high_mid_q", "d_bnd5"),
                ("high_shelf_gain", "d_gai6"), ("high_shelf_freq", "d_frq6"), ("high_shelf_q", "d_bnd6"),
                ("lpf_freq", "d_frq7"),
            ];
            for (sc_k, pt_k) in pairs {
                if let Some(&v) = ins.params.get(sc_k) {
                    pt_params.insert(pt_k.to_owned(), BuildParamVal::Float(f64::from(v)));
                }
            }
            for (sc_k, pt_k) in [("hpf_on", "l_in 1"), ("lpf_on", "l_in 7"), ("hpf_slope", "l_hpfs"), ("lpf_slope", "l_lpfs")] {
                if let Some(&v) = ins.params.get(sc_k) {
                    pt_params.insert(pt_k.to_owned(), BuildParamVal::Int(v.round() as i32));
                }
            }
            for (sc_gain, pt_in) in [
                ("low_shelf_gain", "l_in 2"),
                ("low_mid_gain", "l_in 3"),
                ("mid_gain", "l_in 4"),
                ("high_mid_gain", "l_in 5"),
                ("high_shelf_gain", "l_in 6"),
            ] {
                let static_nz = ins.params.get(sc_gain).is_some_and(|v| v.abs() > 1e-4);
                let auto_nz = track_auto.iter().any(|l| {
                    matches!(&l.param, AutoParam::Plugin { slot, param } if usize::from(*slot) == slot_idx && param == sc_gain)
                        && l.points.iter().any(|p| p.value.abs() > 1e-4)
                });
                if static_nz || auto_nz {
                    pt_params.insert(pt_in.to_owned(), BuildParamVal::Int(1));
                }
            }
            report.record("plugins", format!("{track_name}:slot{slot_idx}:EQ3 7-Band"), Fidelity::Native, None);
        }
        "Dyn3 Compressor/Limiter" => {
            if let Some(&v) = ins.params.get("threshold") {
                pt_params.insert("d_sldC".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("ratio") {
                pt_params.insert("d_sld2".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("attack") {
                pt_params.insert("d_sld1".to_owned(), BuildParamVal::Float(f64::from(v) / 1000.0));
            }
            if let Some(&v) = ins.params.get("release") {
                pt_params.insert("d_sld3".to_owned(), BuildParamVal::Float(f64::from(v) / 1000.0));
            }
            if let Some(&v) = ins.params.get("knee") {
                pt_params.insert("d_sldD".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("makeup") {
                pt_params.insert("d_sldG".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            report.record("plugins", format!("{track_name}:slot{slot_idx}:Dyn3"), Fidelity::Approx, None);
        }
        "Channel Strip" => {
            if let Some(&v) = ins.params.get("input_gain") {
                pt_params.insert("d_Input Trim".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("output_gain") {
                pt_params.insert("d_Fader Volume".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("comp_on") {
                pt_params.insert("l_Cmp In/Out".to_owned(), BuildParamVal::Int(i32::from(v >= 0.5)));
            }
            if let Some(&v) = ins.params.get("comp_threshold") {
                pt_params.insert("d_Cmp Threshold".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("comp_ratio") {
                pt_params.insert("d_Cmp Ratio".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("comp_attack") {
                pt_params.insert("d_Cmp Attack Time".to_owned(), BuildParamVal::Float(f64::from(v) / 1000.0));
            }
            if let Some(&v) = ins.params.get("comp_release") {
                pt_params.insert("d_Cmp Release Time".to_owned(), BuildParamVal::Float(f64::from(v) / 1000.0));
            }
            if let Some(&v) = ins.params.get("comp_makeup") {
                pt_params.insert("d_Cmp Gain Makeup".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("gate_on") {
                pt_params.insert("l_Exp In/Out".to_owned(), BuildParamVal::Int(i32::from(v >= 0.5)));
            }
            if let Some(&v) = ins.params.get("gate_threshold") {
                pt_params.insert("d_Exp Threshold".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("gate_range") {
                pt_params.insert("d_Exp Depth".to_owned(), BuildParamVal::Float(-f64::from(v)));
            }
            if let Some(&v) = ins.params.get("gate_release") {
                pt_params.insert("d_Exp Release Time".to_owned(), BuildParamVal::Float(f64::from(v) / 1000.0));
            }
            if let Some(&v) = ins.params.get("eq_on") {
                pt_params.insert("l_EQ On/Off".to_owned(), BuildParamVal::Int(i32::from(v >= 0.5)));
            }
            if let Some(&v) = ins.params.get("hpf_on") {
                pt_params.insert("l_Filter 1 In/Out".to_owned(), BuildParamVal::Int(i32::from(v >= 0.5)));
            }
            if let Some(&v) = ins.params.get("hpf_freq") {
                pt_params.insert("d_Filter 1 Frequency".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("low_gain") {
                pt_params.insert("d_EQ Low Gain".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("low_freq") {
                pt_params.insert("d_EQ Low Frequency".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("mid_gain") {
                pt_params.insert("d_EQ Low-Mid Gain".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("mid_freq") {
                pt_params.insert("d_EQ Low-Mid Frequency".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("mid_q") {
                pt_params.insert("d_EQ Low-Mid Q".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("high_gain") {
                pt_params.insert("d_EQ High Gain".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("high_freq") {
                pt_params.insert("d_EQ High Frequency".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            report.record("plugins", format!("{track_name}:slot{slot_idx}:Channel Strip"), Fidelity::Approx, None);
        }
        "Trim" => {
            if let Some(&v) = ins.params.get("gain") {
                pt_params.insert("gain_db".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("invert") {
                pt_params.insert("phase_invert".to_owned(), BuildParamVal::Bool(v >= 0.5));
            }
            report.record("plugins", format!("{track_name}:slot{slot_idx}:Trim"), Fidelity::Native, None);
        }
        "AutoPan" => {
            if let Some(&v) = ins.params.get("output") {
                pt_params.insert("d_outg".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("width") {
                pt_params.insert("d_wdth".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("manual") {
                pt_params.insert("d_posi".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            if let Some(&v) = ins.params.get("rate") {
                pt_params.insert("d_temp".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            report.record("plugins", format!("{track_name}:slot{slot_idx}:AutoPan"), Fidelity::Native, None);
        }
        "Time Adjuster" => {
            if let Some(&v) = ins.params.get("delay_samples") {
                pt_params.insert("delay_samples".to_owned(), BuildParamVal::Float(f64::from(v)));
            }
            report.record("plugins", format!("{track_name}:slot{slot_idx}:Time Adjuster"), Fidelity::Native, None);
        }
        _ => {
            report.record("plugins", format!("{track_name}:slot{slot_idx}:{pt_name}"), Fidelity::Approx, None);
        }
    }

    let mut auto_lanes = Vec::new();
    for lane in track_auto {
        let AutoParam::Plugin { slot, param } = &lane.param else {
            continue;
        };
        if usize::from(*slot) != slot_idx {
            continue;
        }
        if let Some((pname, pid, pidx)) = map_sc_auto_param_to_pt(&pt_name, param) {
            let is_log = param_spec(plugin_cfg, sc_id, param)
                .is_some_and(|s| s.taper == ParamTaper::Log);
            let mut raw_pts: Vec<(u64, f64)> = lane
                .points
                .iter()
                .map(|pt| {
                    let t = if to_ticks {
                        samples_to_ptx_ticks(pt.at, tempo, sr)
                    } else {
                        u64::try_from(pt.at.max(0)).unwrap_or(0)
                    };
                    (t, f64::from(pt.value))
                })
                .collect();
            raw_pts.sort_by_key(|p| p.0);
            let points: Vec<(u64, f64)> = if is_log && raw_pts.len() >= 2 {
                let ctx = LogSubdivCtx {
                    cfg: plugin_cfg,
                    sc_plugin: sc_id,
                    sc_key: param,
                };
                let mut dense = Vec::new();
                for (i, w) in raw_pts.windows(2).enumerate() {
                    let (t0, f0) = w[0];
                    let (t1, f1) = w[1];
                    if i == 0 {
                        dense.push((t0, sc_phys_to_pt_norm_with(plugin_cfg, sc_id, param, f0)));
                    }
                    subdivide_sc_log_segment(&ctx, (t0, f0), (t1, f1), 0, &mut dense);
                    dense.push((t1, sc_phys_to_pt_norm_with(plugin_cfg, sc_id, param, f1)));
                }
                dense
            } else {
                raw_pts
                    .into_iter()
                    .map(|(t, f)| (t, sc_phys_to_pt_norm_with(plugin_cfg, sc_id, param, f)))
                    .collect()
            };
            auto_lanes.push(BuildInsertAutoLane {
                param_name: pname.to_owned(),
                param_id: pid.to_owned(),
                param_index: pidx,
                points,
            });
        }
    }

    Some(BuildInsert {
        slot_index: slot_idx,
        plugin_name: pt_name,
        bypass: ins.bypass,
        active: ins.active,
        multi_mono: carry_opt.is_some_and(|c| c.multi_mono),
        params: pt_params,
        automation: auto_lanes,
    })
}
