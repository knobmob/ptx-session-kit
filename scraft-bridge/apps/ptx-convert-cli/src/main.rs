// Version: 0.7.0 (beta) | Date: 2026-11-27
//! Clean-room CLI converter between Pro Tools (`.ptx`) and SoundCraft (`.scraft`/`.scraftz`).
#![deny(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::unimplemented,
    clippy::todo,
    clippy::unreachable
)]

use std::path::{Path, PathBuf};
use std::process::{self, Command};

use clap::{Parser, ValueEnum};
use ptx_scraft::{
    ConvertError, ConvertOptions, ConversionReport, LoopHandling, MediaMode, ScraftFormat,
    convert_ptx_to_scraft_file, convert_scraft_to_ptx_file,
};

#[derive(Debug, Clone, Copy, ValueEnum)]
enum MediaArg {
    Relative,
    Copy,
    Link,
}

impl From<MediaArg> for MediaMode {
    fn from(m: MediaArg) -> Self {
        match m {
            MediaArg::Relative => Self::Relative,
            MediaArg::Copy => Self::Copy,
            MediaArg::Link => Self::Link,
        }
    }
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum LoopArg {
    Faithful,
    Flatten,
}

impl From<LoopArg> for LoopHandling {
    fn from(l: LoopArg) -> Self {
        match l {
            LoopArg::Faithful => Self::Faithful,
            LoopArg::Flatten => Self::Flatten,
        }
    }
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum FormatArg {
    File,
    Dir,
    Bundle,
}

impl From<FormatArg> for ScraftFormat {
    fn from(f: FormatArg) -> Self {
        match f {
            FormatArg::File => Self::File,
            FormatArg::Dir => Self::Dir,
            FormatArg::Bundle => Self::Bundle,
        }
    }
}

#[derive(Debug, Parser)]
#[command(
    name = "ptxconv",
    version,
    about = "Clean-room bidirectional Pro Tools (.ptx) <-> SoundCraft (.scraft/.scraftz) converter"
)]
struct Cli {
    /// Input session file (.ptx, .scraft, or .scraftz)
    input: PathBuf,

    /// Output path (defaults to sibling <stem>.scraft / .scraftz / .ptx)
    #[arg(short, long)]
    out: Option<PathBuf>,

    /// Output container format when converting .ptx -> .scraft
    #[arg(long = "sc-format", value_enum, default_value_t = FormatArg::File)]
    sc_format: FormatArg,

    /// Audio asset handling strategy (default: zero-move relative)
    #[arg(long, value_enum, default_value_t = MediaArg::Relative)]
    media: MediaArg,

    /// Clip loop handling strategy
    #[arg(long = "loop-handling", value_enum, default_value_t = LoopArg::Faithful)]
    loop_handling: LoopArg,

    /// Refuse conversion if any item cannot be mapped natively or via documented approximation
    #[arg(long)]
    strict: bool,

    /// Disable reading/writing <stem>.ptxcarry.json lossless round-trip sidecar
    #[arg(long = "no-carry")]
    no_carry: bool,

    /// Inspect conversion fidelity & emit JSON report without writing session files
    #[arg(long = "dry-run")]
    dry_run: bool,

    /// Print full conversion report JSON to stdout (or write to PATH when provided)
    #[arg(long)]
    report: Option<Option<PathBuf>>,

    /// Export stems via an optional external stem-export script (`[tools] export_stems` in config.toml)
    #[arg(long = "render-opaque-stems")]
    render_opaque_stems: bool,

    /// Optional custom plugin parameter/taper JSON override (`plugin_map.json`)
    #[arg(long = "plugin-config")]
    plugin_config: Option<PathBuf>,
}

fn default_out_path(input: &Path, to_scraft: bool, sc_fmt: ScraftFormat) -> PathBuf {
    let dir = input.parent().unwrap_or_else(|| Path::new("."));
    let stem = input
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("session");
    if to_scraft {
        match sc_fmt {
            ScraftFormat::File => dir.join(format!("{stem}.scraft")),
            ScraftFormat::Dir => dir.join(format!("{stem}.scraft_project")),
            ScraftFormat::Bundle => dir.join(format!("{stem}.scraftz")),
        }
    } else {
        dir.join(format!("{stem}.ptx"))
    }
}

fn emit_report(report: &ConversionReport, report_arg: &Option<Option<PathBuf>>) -> Result<(), ConvertError> {
    if let Some(opt_path) = report_arg {
        let json = serde_json::to_string_pretty(report)?;
        if let Some(p) = opt_path {
            std::fs::write(p, json)?;
        } else {
            println!("{json}");
        }
    }
    Ok(())
}

fn find_export_stems_script() -> Option<PathBuf> {
    if let Ok(cfg) = std::env::var("PTX_CONFIG")
        && let Some(p) = stems_from_config(Path::new(&cfg))
    {
        return Some(p);
    }
    let mut bases = vec![PathBuf::from("."), PathBuf::from(".."), PathBuf::from("../..")];
    if let Ok(exe) = std::env::current_exe() {
        for anc in exe.ancestors().skip(1).take(5) {
            bases.push(anc.to_path_buf());
        }
    }
    for base in &bases {
        for fixed_name in ["config.toml", "ptx_config.toml"] {
            let fixed = base.join(fixed_name);
            if fixed.is_file()
                && let Some(p) = stems_from_config(&fixed)
            {
                return Some(p);
            }
        }
        if let Ok(rd) = std::fs::read_dir(base) {
            let mut cfgs: Vec<PathBuf> = rd
                .flatten()
                .map(|e| e.path())
                .filter(|p| {
                    p.file_name()
                        .and_then(|n| n.to_str())
                        .is_some_and(|n| n.starts_with("ptx_config_v") && n.ends_with(".toml"))
                })
                .collect();
            cfgs.sort();
            if let Some(newest) = cfgs.last()
                && let Some(p) = stems_from_config(newest)
            {
                return Some(p);
            }
        }
        let tools_dir = base.join("tools");
        if let Ok(rd) = std::fs::read_dir(&tools_dir) {
            let mut scripts: Vec<PathBuf> = rd
                .flatten()
                .map(|e| e.path())
                .filter(|p| {
                    p.file_name()
                        .and_then(|n| n.to_str())
                        .is_some_and(|n| n.starts_with("ptx_export_stems_v") && n.ends_with(".py"))
                })
                .collect();
            scripts.sort();
            if let Some(newest) = scripts.last()
                && newest.is_file()
            {
                return Some(newest.clone());
            }
        }
    }
    None
}

fn stems_from_config(cfg_path: &Path) -> Option<PathBuf> {
    let text = std::fs::read_to_string(cfg_path).ok()?;
    let kit_root = cfg_path.parent()?;
    for line in text.lines() {
        let trimmed = line.split('#').next().unwrap_or("").trim();
        if let Some(rest) = trimmed.strip_prefix("export_stems") {
            let rhs = rest.trim_start().strip_prefix('=')?.trim();
            let val = rhs.trim_matches(|c| c == '"' || c == '\'');
            if !val.is_empty() {
                let p = kit_root.join(val);
                if p.is_file() {
                    return Some(p);
                }
            }
        }
    }
    None
}

fn try_render_opaque_stems(input: &Path, report: &ConversionReport) {
    let opaque_count = report.summary.carry + report.summary.absent;
    if opaque_count == 0 {
        return;
    }
    let ext = input
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if ext == "ptx" {
        if let Some(script) = find_export_stems_script() {
            let stems_dir = input
                .parent()
                .unwrap_or_else(|| Path::new("."))
                .join("Stems");
            let status = Command::new("python3")
                .arg(script)
                .arg(input)
                .arg("--only-fx")
                .arg("--out")
                .arg(&stems_dir)
                .status();
            match status {
                Ok(s) if s.success() => eprintln!("exported opaque stems to {}", stems_dir.display()),
                Ok(s) => eprintln!("warning: ptx_export_stems exited with {s}"),
                Err(e) => eprintln!("warning: failed to launch ptx_export_stems: {e}"),
            }
        } else {
            eprintln!("warning: --render-opaque-stems requested ({opaque_count} carried/absent items) but export_stems tool was not found in kit config");
        }
    } else {
        let stems_dir = input
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join("Stems");
        let _ = std::fs::create_dir_all(&stems_dir);
        let out_wav = stems_dir.join("soundcraft_bounce.wav");
        let status = Command::new("soundcraft-cli")
            .arg("run")
            .arg("--in")
            .arg(input)
            .arg("--bounce")
            .arg(&out_wav)
            .status();
        match status {
            Ok(s) if s.success() => eprintln!("exported SoundCraft bounce to {}", out_wav.display()),
            Ok(s) => eprintln!("warning: soundcraft-cli exited with {s}"),
            Err(e) => eprintln!("warning: soundcraft-cli unavailable ({e})"),
        }
    }
}

fn run(cli: Cli) -> Result<(), ConvertError> {
    let ext = cli
        .input
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    let opts = ConvertOptions {
        media_mode: cli.media.into(),
        loop_handling: cli.loop_handling.into(),
        strict: cli.strict,
        carry: !cli.no_carry,
        scraft_format: cli.sc_format.into(),
        plugin_config: cli.plugin_config.clone(),
    };
    let write_outputs = !cli.dry_run;

    let report = match ext.as_str() {
        "ptx" => {
            let out = cli
                .out
                .clone()
                .unwrap_or_else(|| default_out_path(&cli.input, true, opts.scraft_format));
            let (_, rep, _) =
                convert_ptx_to_scraft_file(&cli.input, &out, &opts, write_outputs)?;
            rep
        }
        "scraft" | "scraftz" => {
            let out = cli
                .out
                .clone()
                .unwrap_or_else(|| default_out_path(&cli.input, false, opts.scraft_format));
            let (_, rep) = convert_scraft_to_ptx_file(&cli.input, &out, &opts, write_outputs)?;
            rep
        }
        other => {
            return Err(ConvertError::Audio(format!(
                "unsupported input extension '.{other}' (expected .ptx, .scraft, or .scraftz)"
            )));
        }
    };

    if cli.render_opaque_stems {
        try_render_opaque_stems(&cli.input, &report);
    }
    emit_report(&report, &cli.report)?;

    if cli.report.is_none() {
        println!(
            "{} -> {} [native={} approx={} carry={} absent={}]",
            report.source_path,
            report.target_path,
            report.summary.native,
            report.summary.approx,
            report.summary.carry,
            report.summary.absent,
        );
    }
    Ok(())
}

fn main() {
    let cli = Cli::parse();
    if let Err(err) = run(cli) {
        eprintln!("error: {err}");
        process::exit(1);
    }
}
