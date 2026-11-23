// Version: 0.7.0 (beta) | Date: 2026-11-23
//! Clean-room Pro Tools stock plug-in tables and state chunk packers (`elck`, `All `, `MD_3`, `PiII`).

use std::collections::BTreeMap;

use crate::encode::spec::BuildParamVal;
use crate::primitives::TRIM_KNOTS;
use crate::tree::encode_block;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StateFormat {
    Elck,
    All,
    Md3,
    Piii,
}

#[derive(Debug, Clone, Copy)]
pub struct StockPluginSpec {
    pub name: &'static str,
    pub vid: &'static str,
    pub mfr: &'static [u8; 4],
    pub prod: &'static [u8; 4],
    pub mono17: &'static [u8; 4],
    pub mono38: &'static [u8; 4],
    pub stereo17: &'static [u8; 4],
    pub stereo38: &'static [u8; 4],
    pub fmt: StateFormat,
    pub ver: i32,
    pub lat: u16,
    pub m2s: bool,
    pub force_stereo_1017: bool,
    pub be_len_override: Option<usize>,
}

/// Inverse of `trim_norm_to_db` (`dB` -> normalized `[0..1]`).
#[must_use]
pub fn trim_db_to_norm(db: f64, range_db: f64) -> f64 {
    if db <= -144.0 {
        return 0.0;
    }
    if db >= 0.0 {
        return (0.755 + (db / range_db.max(1.0)) * (1.0 - 0.755)).min(1.0);
    }
    for w in TRIM_KNOTS.windows(2) {
        let (x0, y0) = w[0];
        let (x1, y1) = w[1];
        if db <= y1 {
            return x0 + (db - y0) / (y1 - y0) * (x1 - x0);
        }
    }
    0.755
}

fn norm_to_be_i32(v: f64) -> i32 {
    let scaled = ((v - 0.5) * 4_294_967_296.0).round();
    if scaled >= f64::from(i32::MAX) {
        i32::MAX
    } else if scaled <= f64::from(i32::MIN) {
        i32::MIN
    } else {
        scaled as i32
    }
}

/// Look up a supported stock plug-in by Pro Tools display name or AAX code.
#[must_use]
pub fn lookup_stock_plugin(name: &str) -> Option<StockPluginSpec> {
    STOCK_PLUGINS.iter().copied().find(|s| s.name == name)
}

pub const STOCK_PLUGINS: &[StockPluginSpec] = &[
    StockPluginSpec {
        name: "EQ3 1-Band",
        vid: "com.digidesign.aax.eq3.1band",
        mfr: b"Digi",
        prod: b"1be3",
        mono17: b"1emr",
        mono38: b"1emr",
        stereo17: b"1esr",
        stereo38: b"1esr",
        fmt: StateFormat::Elck,
        ver: -1,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "EQ3 7-Band",
        vid: "com.digidesign.aax.eq3.7band",
        mfr: b"Digi",
        prod: b"47e3",
        mono17: b"7emr",
        mono38: b"7emr",
        stereo17: b"7esr",
        stereo38: b"7esr",
        fmt: StateFormat::Elck,
        ver: -1,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "Channel Strip",
        vid: "com.avid.aax.sdk.ChannelStrip",
        mfr: b"AVID",
        prod: b"ChSt",
        mono17: b"CMRT",
        mono38: b"CMRT",
        stereo17: b"CSRT",
        stereo38: b"CSRT",
        fmt: StateFormat::Elck,
        ver: -1,
        lat: 0x64,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "Dyn3 Compressor/Limiter",
        vid: "com.avid.aax.dyn3.Compressor",
        mfr: b"Digi",
        prod: b"dn3c",
        mono17: b"CMRT",
        mono38: b"CMRT",
        stereo17: b"CSRT",
        stereo38: b"CSRT",
        fmt: StateFormat::Elck,
        ver: -1,
        lat: 0x64,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "AutoPan",
        vid: "com.avid.aax.tl.AutoPan",
        mfr: b"TrLn",
        prod: b"APan",
        mono17: b"rtms",
        mono38: b"rtms",
        stereo17: b"rtss",
        stereo38: b"rtss",
        fmt: StateFormat::Elck,
        ver: -1,
        lat: 0x64,
        m2s: true,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "Click II",
        vid: "com.avid.aax.sdk.megaclick",
        mfr: b"Digi",
        prod: b"clik",
        mono17: b"CkRT",
        mono38: b"CkRT",
        stereo17: b"CkRT",
        stereo38: b"CkRT",
        fmt: StateFormat::Elck,
        ver: -1,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: Some(40),
    },
    StockPluginSpec {
        name: "Trim",
        vid: "com.avid.aax.trim",
        mfr: b"Digi",
        prod: b"Trim",
        mono17: b"TR11",
        mono38: b"TR11",
        stereo17: b"TR11",
        stereo38: b"TR11",
        fmt: StateFormat::All,
        ver: 2,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "D-Verb",
        vid: "com.avid.aax.dverb",
        mfr: b"Digi",
        prod: b"Rvrb",
        mono17: b"movh",
        mono38: b"movh",
        stereo17: b"stvh",
        stereo38: b"stvh",
        fmt: StateFormat::All,
        ver: 1,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "Dither",
        vid: "com.avid.aax.dither",
        mfr: b"Digi",
        prod: b"Dthr",
        mono17: b"msrd",
        mono38: b"msrd",
        stereo17: b"ssrd",
        stereo38: b"ssrd",
        fmt: StateFormat::All,
        ver: 1,
        lat: 0,
        m2s: false,
        force_stereo_1017: true,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "POW-r Dither",
        vid: "com.avid.aax.powr",
        mfr: b"Digi",
        prod: b"POWr",
        mono17: b"mmpr",
        mono38: b"mmpr",
        stereo17: b"sspr",
        stereo38: b"sspr",
        fmt: StateFormat::All,
        ver: 1,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "Time Adjuster",
        vid: "com.avid.aax.timeadjuster",
        mfr: b"Digi",
        prod: b"PIGD",
        mono17: b"11pl",
        mono38: b"11pl",
        stereo17: b"11pl",
        stereo38: b"11pl",
        fmt: StateFormat::All,
        ver: 3,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "BF-76",
        vid: "com.avid.aax.bf76",
        mfr: b"BFD ",
        prod: b"1176",
        mono17: b"mm76",
        mono38: b"mm76",
        stereo17: b"mm76",
        stereo38: b"mm76",
        fmt: StateFormat::All,
        ver: 10,
        lat: 0x64,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "Sci-Fi",
        vid: "com.avid.aax.scifi",
        mfr: b"Digi",
        prod: b"SciF",
        mono17: b"RMSF",
        mono38: b"stmo",
        stereo17: b"RMSF",
        stereo38: b"stmo",
        fmt: StateFormat::All,
        ver: 1,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "Lo-Fi",
        vid: "com.avid.aax.lofi",
        mfr: b"Digi",
        prod: b"LoFi",
        mono17: b"RMLF",
        mono38: b"ltmo",
        stereo17: b"RMLF",
        stereo38: b"ltmo",
        fmt: StateFormat::All,
        ver: 1,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "SansAmp PSA-1",
        vid: "com.avid.aax.sansamp",
        mfr: b"BFD ",
        prod: b"PSA1",
        mono17: b"mmps",
        mono38: b"mmps",
        stereo17: b"mmps",
        stereo38: b"mmps",
        fmt: StateFormat::All,
        ver: 5,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
    StockPluginSpec {
        name: "Mod Delay III",
        vid: "com.avid.aax.moddelay3",
        mfr: b"Avid",
        prod: b"mdl3",
        mono17: b"xmm3",
        mono38: b"xmm3",
        stereo17: b"xss3",
        stereo38: b"xss3",
        fmt: StateFormat::Md3,
        ver: 8,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: Some(96),
    },
    StockPluginSpec {
        name: "Pitch II",
        vid: "com.avid.aax.pitch",
        mfr: b"Digi",
        prod: b"Pish",
        mono17: b"mmPi",
        mono38: b"mmPi",
        stereo17: b"ssPi",
        stereo38: b"ssPi",
        fmt: StateFormat::Piii,
        ver: 1,
        lat: 0,
        m2s: false,
        force_stereo_1017: false,
        be_len_override: None,
    },
];

fn pack_elck(defaults: &[(&str, f64, bool)], ovr: &BTreeMap<String, BuildParamVal>, extra: &[u8]) -> Vec<u8> {
    let mut out = vec![0x01, 0x01, 0x01, 0x01];
    for &(name, def_val, is_float) in defaults {
        out.extend_from_slice(name.as_bytes());
        out.push(0);
        let pad = (4 - ((name.len() + 1) % 4)) % 4;
        out.extend(std::iter::repeat_n(0u8, pad));
        let override_v = ovr.get(name);
        if is_float {
            let fv = match override_v {
                Some(BuildParamVal::Float(f)) => *f,
                Some(BuildParamVal::Int(i)) => f64::from(*i),
                Some(BuildParamVal::Norm(n)) => *n,
                Some(BuildParamVal::Bool(b)) => {
                    if *b { 1.0 } else { 0.0 }
                }
                None => def_val,
            };
            out.extend_from_slice(&fv.to_be_bytes());
        } else {
            let iv = match override_v {
                Some(BuildParamVal::Int(i)) => *i,
                Some(BuildParamVal::Bool(b)) => i32::from(*b),
                Some(BuildParamVal::Float(f)) => *f as i32,
                Some(BuildParamVal::Norm(n)) => *n as i32,
                None => def_val as i32,
            };
            out.extend_from_slice(&iv.to_be_bytes());
        }
    }
    out.extend_from_slice(extra);
    out.extend_from_slice(&[0u8; 4]);
    out
}

fn default_elck_list(name: &str) -> &'static [(&'static str, f64, bool)] {
    match name {
        "EQ3 1-Band" => &[
            ("l_hak1", 0.0, false), ("d_gain", 0.0, true), ("d_ctrf", 1000.0, true),
            ("d_bndw", 1.0, true), ("l_slop", 1.0, false), ("l_type", 3.0, false),
            ("d_trim", 0.0, true), ("l_Phse", 0.0, false),
        ],
        "EQ3 7-Band" => &[
            ("l_hak3", 0.0, false), ("l_hak1", 0.0, false), ("d_inpt", 0.0, true), ("d_outp", 0.0, true),
            ("l_Phse", 0.0, false), ("l_hprg", 1.0, false), ("l_in 1", 0.0, false), ("d_hpfq", 1.0, true),
            ("l_hpfs", 0.0, false), ("d_frq1", 20.0, true), ("l_in 2", 1.0, false), ("d_gai2", 0.0, true),
            ("d_frq2", 100.0, true), ("d_bnd2", 1.0, true), ("l_lfrg", 1.0, false), ("l_in 3", 1.0, false),
            ("d_gai3", 0.0, true), ("d_frq3", 200.0, true), ("d_bnd3", 1.0, true), ("l_in 4", 1.0, false),
            ("d_gai4", 0.0, true), ("d_frq4", 1000.0, true), ("d_bnd4", 1.0, true), ("l_in 5", 1.0, false),
            ("d_gai5", 0.0, true), ("d_frq5", 2000.0, true), ("d_bnd5", 1.0, true), ("l_in 6", 1.0, false),
            ("d_gai6", 0.0, true), ("d_frq6", 6000.0, true), ("d_bnd6", 1.0, true), ("l_hfrg", 1.0, false),
            ("l_lprg", 1.0, false), ("l_in 7", 0.0, false), ("d_lpfq", 1.0, true), ("l_lpfs", 0.0, false),
            ("d_frq7", 20000.0, true), ("l_hak2", 0.0, false),
        ],
        "Dyn3 Compressor/Limiter" => &[
            ("d_sldG", 0.0, true), ("d_sld2", 3.0, true), ("d_sld1", 0.01, true), ("d_sld3", 0.08, true),
            ("d_sldD", 0.0, true), ("d_sldC", -24.0, true), ("l_Phse", 0.0, false), ("d_HiFF", 20000.0, true),
            ("l_HiRG", 1.0, false), ("l_HiFE", 0.0, false), ("d_LoFF", 20.0, true), ("l_LoRG", 1.0, false),
            ("l_LoFE", 0.0, false), ("l_sldE", 0.0, false),
        ],
        "AutoPan" => &[
            ("d_outg", 0.0, true), ("d_angl", 0.0, true), ("d_posi", 100.0, true), ("d_sprd", 75.0, true),
            ("d_wdth", 100.0, true), ("d_offs", 50.0, true), ("l_mods", 0.0, false), ("l_dirn", 0.0, false),
            ("d_temp", 120.0, true), ("l_wave", 0.0, false), ("l_mtrg", 0.0, false), ("l_ones", 0.0, false),
            ("l_mbck", 0.0, false), ("l_etrg", 0.0, false), ("l_dura", 12.0, false), ("d_thrs", -20.0, true),
            ("d_attk", 10.0, true), ("d_rels", 20.0, true), ("l_ukey", 0.0, false), ("d_stem", 120.0, true),
            ("l_ftem", 0.0, false), ("l_vers", 0.0, false),
        ],
        "Channel Strip" => &[
            ("l_Process Order", 0.0, false), ("l_Phase Switch In/Out", 0.0, false),
            ("d_Input Trim", 0.0, true), ("d_Fader Volume", 0.0, true), ("l_Fader Volume Pre/Post", 0.0, false),
            ("l_Fader Volume On/Off", 1.0, false), ("l_EQ On/Off", 1.0, false), ("l_Filters On/Off", 1.0, false),
            ("l_Dynamics On/Off", 1.0, false), ("l_Dynamics Range", 0.0, false), ("l_Dynamics Reveal", 0.0, false),
            ("l_EQ Range", 0.0, false), ("l_EQ Reveal", 0.0, false), ("l_Meters Tab", 0.0, false),
            ("l_Order Tab", 0.0, false), ("l_Dynamics Tab", 1.0, false), ("l_EQ Tab", 0.0, false),
            ("l_Cmp In/Out", 1.0, false), ("d_Cmp Ratio", 1.0, true), ("d_Cmp Knee", 0.0, true),
            ("d_Cmp Attack Time", 0.0001, true), ("d_Cmp Release Time", 0.2, true),
            ("d_Cmp Gain Makeup", 0.0, true), ("d_Cmp Threshold", -24.0, true), ("d_Cmp Depth", -36.0, true),
            ("l_Exp In/Out", 1.0, false), ("d_Exp Ratio", 1.0, true), ("d_Exp Knee", 0.0, true),
            ("d_Exp Attack Time", 2e-5, true), ("d_Exp Release Time", 0.2, true),
            ("d_Exp Threshold", -58.0, true), ("d_Exp Depth", -36.0, true),
            ("d_Exp Hold Time", 0.001, true), ("d_Exp Hysteresis", 0.0, true),
            ("l_Sc Filter In/Out", 1.0, false), ("l_Sc Filter Type", 0.0, false),
            ("d_Sc Filter Frequency", 20.0, true), ("l_Sc Listen In/Out", 0.0, false),
            ("l_Sc Source", 0.0, false), ("l_Sc Detector Type Avg/Pk", 1.0, false),
            ("l_EQ Low In/Out", 1.0, false), ("l_EQ Low Type", 0.0, false),
            ("d_EQ Low Gain", 0.0, true), ("d_EQ Low Frequency", 41.2, true), ("d_EQ Low Q", 0.5, true),
            ("l_EQ Low Listen In/Out", 0.0, false), ("l_EQ Low-Mid In/Out", 1.0, false),
            ("d_EQ Low-Mid Gain", 0.0, true), ("d_EQ Low-Mid Frequency", 329.0, true),
            ("d_EQ Low-Mid Q", 0.5, true), ("l_EQ Low-Mid Listen In/Out", 0.0, false),
            ("l_EQ High-Mid In/Out", 1.0, false), ("d_EQ High-Mid Gain", 0.0, true),
            ("d_EQ High-Mid Frequency", 2630.0, true), ("d_EQ High-Mid Q", 0.5, true),
            ("l_EQ High-Mid Listen In/Out", 0.0, false), ("l_EQ High In/Out", 1.0, false),
            ("l_EQ High Type", 0.0, false), ("d_EQ High Gain", 0.0, true),
            ("d_EQ High Frequency", 10500.0, true), ("d_EQ High Q", 0.5, true),
            ("l_EQ High Listen In/Out", 0.0, false), ("l_Filter 1 In/Out", 0.0, false),
            ("l_Filter 1 Type", 0.0, false), ("d_Filter 1 Frequency", 20.6, true),
            ("d_Filter 1 Q", 0.5, true), ("l_Filter 1 Slope 12/24dB", 0.0, false),
            ("l_Filter 1 Listen In/Out", 0.0, false), ("l_Filter 2 In/Out", 0.0, false),
            ("l_Filter 2 Type", 1.0, false), ("d_Filter 2 Frequency", 21000.0, true),
            ("d_Filter 2 Q", 0.5, true), ("l_Filter 2 Slope 12/24dB", 0.0, false),
            ("l_Filter 2 Listen In/Out", 0.0, false),
        ],
        "Click II" => &[("d_AcAt", 0.5, true), ("d_UnAt", 0.5, true)],
        _ => &[],
    }
}

fn default_all_values(name: &str) -> Vec<i32> {
    match name {
        "Trim" => vec![0x72bcaf28, i32::MIN, i32::MIN, i32::MIN, 0],
        "D-Verb" => vec![i32::MIN, i32::MAX, 0x20ffffff, i32::MAX, 0x60000000, 0, 0x40ab3680, i32::MAX, i32::MIN, 0, 0],
        "Dither" => vec![0, i32::MAX, i32::MAX, 0],
        "POW-r Dither" => vec![i32::MAX, i32::MIN, 0],
        "Time Adjuster" => vec![0, 0, 0, 0, 0, 0, 4, 4, 0],
        "BF-76" => vec![-558345749, 558345748, -730144512, 816043929, i32::MIN, i32::MAX, 0],
        "Sci-Fi" => vec![i32::MAX, i32::MIN, i32::MIN, i32::MIN, i32::MIN, i32::MIN, i32::MIN, 0],
        "Lo-Fi" => vec![i32::MAX, i32::MAX, i32::MAX, i32::MIN, i32::MIN, 0, i32::MIN, i32::MIN, 0],
        "SansAmp PSA-1" => vec![0, -1073741824, 0, -42949673, 858993459, 85899345, 644245094, 515396075, 747324309, 0],
        _ => Vec::new(),
    }
}

fn apply_all_overrides(name: &str, vals: &mut [i32], ovr: &BTreeMap<String, BuildParamVal>) {
    let as_bool = |v: &BuildParamVal| -> bool {
        match v {
            BuildParamVal::Bool(b) => *b,
            BuildParamVal::Int(i) => *i != 0,
            BuildParamVal::Float(f) | BuildParamVal::Norm(f) => *f > 0.0,
        }
    };
    let as_f64 = |v: &BuildParamVal| -> f64 {
        match v {
            BuildParamVal::Float(f) | BuildParamVal::Norm(f) => *f,
            BuildParamVal::Int(i) => f64::from(*i),
            BuildParamVal::Bool(b) => if *b { 1.0 } else { 0.0 },
        }
    };

    if name == "Trim" && vals.len() >= 5 {
        if let Some(v) = ovr.get("gain_range_db") {
            vals[3] = if as_f64(v) >= 12.0 { i32::MAX } else { i32::MIN };
        }
        let rng = if vals[3] > 0 { 12.0 } else { 6.0 };
        if let Some(v) = ovr.get("gain_db") {
            vals[0] = norm_to_be_i32(trim_db_to_norm(as_f64(v), rng));
        } else if let Some(v) = ovr.get("gain_norm") {
            vals[0] = norm_to_be_i32(as_f64(v));
        }
        if let Some(v) = ovr.get("phase_invert") {
            vals[1] = if as_bool(v) { i32::MAX } else { i32::MIN };
        }
        if let Some(v) = ovr.get("master_bypass") {
            vals[4] = if as_bool(v) { i32::MAX } else { 0 };
        }
    } else if name == "Time Adjuster" && vals.len() >= 9 {
        if let Some(v) = ovr.get("delay_samples") {
            let d = as_f64(v).round() as i32;
            vals[6] = d;
            vals[7] = d;
        }
        if let Some(v) = ovr.get("delay_samples_r") {
            vals[7] = as_f64(v).round() as i32;
        }
        if let Some(v) = ovr.get("master_bypass") {
            vals[8] = if as_bool(v) { i32::MAX } else { 0 };
        }
    } else if name == "Sci-Fi" && vals.len() >= 8 {
        for (idx, k) in [(0, "input_level"), (1, "effect_type"), (2, "effect_frequency"), (3, "effect_depth"), (4, "slot_4"), (5, "mod_depth"), (6, "mod_rate_slew_thresh")] {
            if let Some(v) = ovr.get(k) {
                vals[idx] = norm_to_be_i32(as_f64(v));
            }
        }
        if let Some(v) = ovr.get("master_bypass") {
            vals[7] = if as_bool(v) { i32::MAX } else { 0 };
        }
    } else if name == "Lo-Fi" && vals.len() >= 9 {
        for (idx, k) in [(0, "sample_rate_norm"), (1, "sample_size_norm"), (2, "anti_alias_norm"), (3, "noise_norm"), (6, "distortion"), (7, "saturation")] {
            if let Some(v) = ovr.get(k) {
                vals[idx] = norm_to_be_i32(as_f64(v));
            }
        }
        if let Some(v) = ovr.get("master_bypass") {
            vals[8] = if as_bool(v) { i32::MAX } else { 0 };
        }
    } else if name == "BF-76" && vals.len() >= 7 {
        for (idx, k) in [(0, "input"), (1, "output"), (2, "attack"), (3, "release"), (4, "ratio"), (5, "meter_mode")] {
            if let Some(v) = ovr.get(k) {
                vals[idx] = norm_to_be_i32(as_f64(v));
            }
        }
        if let Some(v) = ovr.get("master_bypass") {
            vals[6] = if as_bool(v) { i32::MAX } else { 0 };
        }
    } else if name == "D-Verb" && vals.len() >= 11 {
        for (idx, k) in [(0, "algorithm_norm"), (1, "size_norm"), (2, "decay_norm"), (3, "mix"), (4, "diffusion"), (8, "pre_delay_norm")] {
            if let Some(v) = ovr.get(k) {
                vals[idx] = norm_to_be_i32(as_f64(v));
            }
        }
        if let Some(v) = ovr.get("master_bypass") {
            vals[10] = if as_bool(v) { i32::MAX } else { 0 };
        }
    }
}

fn click_extra() -> Vec<u8> {
    let mut b = Vec::new();
    b.extend_from_slice(&224i32.to_be_bytes());
    b.extend_from_slice(&1i32.to_be_bytes());
    b.extend_from_slice(b"DigiclikCkRTAll ");
    b.extend_from_slice(&[0u8; 32]);
    b.extend_from_slice(&35i32.to_be_bytes());
    b.extend_from_slice(&36i32.to_be_bytes());
    let mut acc = [0u8; 60];
    acc[..17].copy_from_slice(b"Classic Click Acc");
    b.extend_from_slice(&acc);
    b.extend_from_slice(&17u32.to_be_bytes());
    let mut main = [0u8; 60];
    main[..13].copy_from_slice(b"Classic Click");
    b.extend_from_slice(&main);
    for v in [13i32, 2, i32::MIN, i32::MIN, 2, i32::MIN, i32::MIN, i32::MAX, i32::MAX] {
        b.extend_from_slice(&v.to_be_bytes());
    }
    b
}

/// Build `0x1017` entry for the session's `0x1018` plug-in table.
#[must_use]
pub fn build_1017(spec: &StockPluginSpec, use_stereo: bool) -> Vec<u8> {
    let is_st = use_stereo && (spec.stereo17 != spec.mono17 || spec.force_stereo_1017);
    let c17 = if use_stereo { spec.stereo17 } else { spec.mono17 };
    let nb = spec.name.as_bytes();
    let vb = spec.vid.as_bytes();

    let mut p = Vec::new();
    p.push(3); // effect
    p.extend_from_slice(&u32::try_from(nb.len()).unwrap_or(0).to_le_bytes());
    p.extend_from_slice(nb);
    for code in [spec.mfr, spec.prod, c17] {
        for &b in code.iter().rev() {
            p.push(b);
        }
    }
    let (mid_prefix, tail_prefix, ch_in, ch_out): ([u8; 4], [u8; 4], u32, u32) = if spec.m2s && !use_stereo {
        ([1, 0, 2, 1], [0, 1, 0, 1], 1, 2)
    } else if is_st {
        ([2, 1, 2, 1], [1, 1, 1, 1], 2, 2)
    } else {
        ([1, 0, 1, 0], [0, 0, 0, 0], 1, 1)
    };
    p.extend_from_slice(&mid_prefix);
    p.extend_from_slice(&spec.lat.to_le_bytes());
    p.push(0);
    p.extend_from_slice(&u32::try_from(vb.len()).unwrap_or(0).to_le_bytes());
    p.extend_from_slice(vb);
    p.extend_from_slice(&tail_prefix);
    p.extend_from_slice(&ch_in.to_le_bytes());
    p.extend_from_slice(&ch_out.to_le_bytes());
    encode_block(9, 0x1017, &p)
}

/// Build `0x260B` plug-in automation lane data (`01 46 01 00 ...`).
#[must_use]
pub fn build_plug_lane_body(is_ticks: bool, pts: &[(u64, f64)]) -> Vec<u8> {
    let enc = |v: f64| -> i32 {
        let s = ((v - 0.5) * 2_147_483_648.0).round();
        s.clamp(f64::from(i32::MIN), f64::from(i32::MAX)) as i32
    };
    let mut body = Vec::new();
    let tb = u16::from(is_ticks);
    body.extend_from_slice(&tb.to_le_bytes());
    body.extend_from_slice(&u32::try_from(pts.len()).unwrap_or(1).to_le_bytes());
    body.extend_from_slice(&4u16.to_le_bytes());
    body.extend_from_slice(&(pts.len().saturating_sub(1) as u16).to_le_bytes());
    let first_t = if is_ticks { crate::primitives::OFFSET_FORM } else { 0 };
    let v0 = pts.first().map_or(0.5, |p| p.1);
    body.extend_from_slice(&first_t.to_le_bytes());
    body.extend_from_slice(&enc(v0).to_le_bytes());
    for &(t, v) in pts.iter().skip(1) {
        body.extend_from_slice(&(t.min(u64::from(u32::MAX)) as u32).to_le_bytes());
        body.extend_from_slice(&enc(v).to_le_bytes());
    }
    let mut out = vec![0x01, 0x46, 0x01, 0x00];
    out.extend_from_slice(&u32::try_from(body.len()).unwrap_or(0).to_le_bytes());
    out.extend_from_slice(&body);
    out.extend_from_slice(&[0u8; 2]);
    out
}

/// Parameter automation lane specification for `build_filled_insert`.
pub struct InsertAutoLaneData {
    pub param_name: String,
    pub param_id: String,
    pub param_index: u32,
    pub is_ticks: bool,
    pub points: Vec<(u64, f64)>,
}

/// Inputs to `build_filled_insert`.
pub struct FilledInsertArgs<'a> {
    pub tidx: u16,
    pub spec: &'a StockPluginSpec,
    pub use_stereo: bool,
    pub ovr: &'a BTreeMap<String, BuildParamVal>,
    pub active: bool,
    pub bypass: bool,
    pub multi_mono: bool,
    pub auto_lanes: &'a [InsertAutoLaneData],
}

/// Build filled insert slot (`0x2616` or `0x2617` multi-mono wrapper).
#[must_use]
pub fn build_filled_insert(args: &FilledInsertArgs<'_>) -> Vec<u8> {
    let tidx = args.tidx;
    let spec = args.spec;
    let use_stereo = args.use_stereo;
    let ovr = args.ovr;
    let active = args.active;
    let bypass = args.bypass;
    let multi_mono = args.multi_mono;
    let auto_lanes = args.auto_lanes;
    let c38 = if use_stereo { spec.stereo38 } else { spec.mono38 };
    let (fmt_bytes, cname, body): (&[u8; 4], [u8; 32], Vec<u8>) = match spec.fmt {
        StateFormat::Elck => {
            let mut cn = [0u8; 32];
            cn[..23].copy_from_slice(b"Complete Controls State");
            let ex = if spec.name == "Click II" { click_extra() } else { Vec::new() };
            (b"elck", cn, pack_elck(default_elck_list(spec.name), ovr, &ex))
        }
        StateFormat::All => {
            let mut vals = default_all_values(spec.name);
            apply_all_overrides(spec.name, &mut vals, ovr);
            let mut b = Vec::with_capacity(vals.len() * 4);
            for v in vals {
                b.extend_from_slice(&v.to_be_bytes());
            }
            (b"All ", [0u8; 32], b)
        }
        StateFormat::Md3 => {
            let mut b = Vec::new();
            for v in [
                i32::MAX, i32::MAX, i32::MIN, i32::MIN, i32::MAX, i32::MAX,
                -0x73333333i32, -0x73333333i32, i32::MAX, i32::MAX, i32::MIN, i32::MIN,
            ] {
                b.extend_from_slice(&v.to_be_bytes());
            }
            b.extend_from_slice(&[0u8; 10]);
            for v in [-0x448676f3i32, -0x6739ce74i32, -0x6739ce74i32, i32::MIN, i32::MIN] {
                b.extend_from_slice(&v.to_be_bytes());
            }
            b.extend_from_slice(&[0u8; 11]);
            b.extend_from_slice(&[0x01, 0x00, 0x00]);
            b.extend_from_slice(&57u32.to_be_bytes());
            b.extend_from_slice(&8u32.to_be_bytes());
            b.extend_from_slice(b"Avidmdl3");
            b.extend_from_slice(c38);
            b.extend_from_slice(b"ShHi");
            b.extend_from_slice(&[0u8; 37]);
            (b"MD_3", [0u8; 32], b)
        }
        StateFormat::Piii => {
            let mut b = Vec::new();
            for v in [1u32, 0x0100_0000, 0x0100_0000, 3] {
                b.extend_from_slice(&v.to_be_bytes());
            }
            for d in [1.0f64, 0.03, 0.5] {
                b.extend_from_slice(&d.to_be_bytes());
            }
            b.extend_from_slice(&[0u8; 24]);
            for _ in 0..2 {
                b.extend_from_slice(&100.0f64.to_be_bytes());
                b.extend_from_slice(&[0u8; 8]);
                b.extend_from_slice(&0x40d5_887f_ffff_fffdu64.to_be_bytes());
                b.extend_from_slice(&[0u8; 20]);
            }
            (b"PiII", [0u8; 32], b)
        }
    };

    let be_sz = 52 + spec.be_len_override.unwrap_or(body.len());
    let mut d1038 = Vec::new();
    d1038.extend_from_slice(&1u32.to_le_bytes());
    d1038.extend_from_slice(&u32::try_from(52 + body.len()).unwrap_or(0).to_le_bytes());
    d1038.extend_from_slice(&u32::try_from(be_sz).unwrap_or(0).to_be_bytes());
    d1038.extend_from_slice(&spec.ver.to_be_bytes());
    d1038.extend_from_slice(spec.mfr);
    d1038.extend_from_slice(spec.prod);
    d1038.extend_from_slice(c38);
    d1038.extend_from_slice(fmt_bytes);
    d1038.extend_from_slice(&cname);
    d1038.extend_from_slice(&body);
    let b1038 = encode_block(2, 0x1038, &d1038);

    let mut d260e = vec![0xff, 0xff, 0x01, 0x01];
    d260e.extend_from_slice(&[0u8; 38]);
    d260e.extend_from_slice(&[0xffu8; 8]);
    d260e.push(0);
    d260e.extend_from_slice(&[0xffu8; 4]);
    d260e.extend_from_slice(&[0x00, 0x0c, 0x00, 0x00]);
    let b260e = encode_block(9, 0x260e, &d260e);

    let act = u8::from(active);
    let mut tail326 = Vec::new();
    tail326.push(act);
    tail326.extend_from_slice(&[0u8; 6]);
    tail326.extend_from_slice(&15u32.to_le_bytes());
    tail326.extend_from_slice(&[0u8; 56]);
    tail326.extend_from_slice(&15u32.to_le_bytes());
    tail326.extend_from_slice(&[0u8; 28]);
    tail326.extend_from_slice(&6u32.to_le_bytes());
    tail326.extend_from_slice(&[0u8; 10]);
    tail326.extend_from_slice(&6u32.to_le_bytes());
    tail326.extend_from_slice(&[0u8; 10]);
    tail326.extend_from_slice(&[0x01, 0x00, 0x00]);
    tail326.extend_from_slice(&[0x01u8; 64]);
    tail326.extend_from_slice(&[0x00u8; 64]);
    tail326.push(0x10);
    tail326.extend_from_slice(&[0u8; 33]);
    tail326.push(0x10);
    tail326.extend_from_slice(&[0u8; 33]);

    let mut d2613 = Vec::new();
    d2613.extend_from_slice(&0xFFFFu16.to_le_bytes());
    d2613.extend_from_slice(&b1038);
    d2613.extend_from_slice(&[act, 0, 0xff, 0xff]);
    d2613.extend_from_slice(&b260e);
    d2613.extend_from_slice(&tail326);
    let b2613 = encode_block(10, 0x2613, &d2613);

    let mut d2615 = Vec::new();
    d2615.extend_from_slice(&encode_block(1, 0x2626, &[]));
    d2615.extend_from_slice(&tidx.to_le_bytes());
    d2615.extend_from_slice(&b2613);
    let b2615 = encode_block(1, 0x2615, &d2615);

    let mut d2614 = Vec::new();
    d2614.extend_from_slice(&u32::try_from(auto_lanes.len()).unwrap_or(0).to_le_bytes());
    for lane_spec in auto_lanes {
        let lane = encode_block(
            1,
            0x260B,
            &build_plug_lane_body(lane_spec.is_ticks, &lane_spec.points),
        );
        let nb = lane_spec.param_name.as_bytes();
        let ib = lane_spec.param_id.as_bytes();
        let mut entry = Vec::new();
        entry.push(0x01);
        entry.extend_from_slice(&lane);
        entry.extend_from_slice(&u32::try_from(nb.len()).unwrap_or(0).to_le_bytes());
        entry.extend_from_slice(nb);
        entry.extend_from_slice(&lane_spec.param_index.to_le_bytes());
        entry.extend_from_slice(&[0x00, 0x01, 0x01, 0x00]);
        entry.extend_from_slice(&0u32.to_le_bytes());
        entry.extend_from_slice(&u32::try_from(ib.len()).unwrap_or(0).to_le_bytes());
        entry.extend_from_slice(ib);
        d2614.extend_from_slice(&encode_block(2, 0x260F, &entry));
    }
    let b2614 = encode_block(1, 0x2614, &d2614);

    let mut d2616 = Vec::new();
    d2616.extend_from_slice(&b2615);
    d2616.push(u8::from(bypass));
    d2616.extend_from_slice(&b2614);
    let b2616 = encode_block(1, 0x2616, &d2616);

    if multi_mono {
        let mut d2617 = b2616;
        d2617.push(0x02);
        encode_block(1, 0x2617, &d2617)
    } else {
        b2616
    }
}
