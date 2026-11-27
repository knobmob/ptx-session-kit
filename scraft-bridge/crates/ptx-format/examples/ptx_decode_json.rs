// Version: 0.7.0 (beta) | Date: 2026-11-27
//! Dump canonical decoded `.ptx` JSON for parity comparison against `tools/ptx_decode.py`.

use std::io::BufRead;
use std::path::PathBuf;
use std::process::ExitCode;

use ptx_format::decode::decode_file;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() {
        eprintln!("usage: ptx_decode_json <file.ptx> | --batch");
        return ExitCode::from(2);
    }
    if args[0] == "--batch" {
        let stdin = std::io::stdin();
        for line in stdin.lock().lines() {
            let Ok(p) = line else { break };
            let trimmed = p.trim();
            if trimmed.is_empty() {
                continue;
            }
            let out = match decode_file(&PathBuf::from(trimmed)) {
                Ok(doc) => match serde_json::to_value(&doc) {
                    Ok(v) => serde_json::json!({ "ok": true, "path": trimmed, "doc": v }),
                    Err(e) => serde_json::json!({ "ok": false, "path": trimmed, "error": e.to_string() }),
                },
                Err(e) => serde_json::json!({ "ok": false, "path": trimmed, "error": e.to_string() }),
            };
            println!("{out}");
        }
        return ExitCode::SUCCESS;
    }
    let path = PathBuf::from(&args[0]);
    match decode_file(&path) {
        Ok(doc) => match serde_json::to_string_pretty(&doc) {
            Ok(s) => {
                println!("{s}");
                ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("json error: {e}");
                ExitCode::FAILURE
            }
        },
        Err(e) => {
            eprintln!("decode error: {e}");
            ExitCode::FAILURE
        }
    }
}
